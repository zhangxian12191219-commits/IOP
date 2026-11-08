"""设备巡检服务

职责：
- 汇总资产库设备的最新采集指标与未确认告警，生成巡检结论和整改建议
- 使用 python-docx 生成 Word（.docx）巡检报告；缺少 python-docx 时明确报错，不伪造成功
- 保存/校验上传的自定义 Word 报告（仅 .docx，最大 50MB）
- 提供巡检调度循环：每 60 秒检查到期的启用任务并生成报告

报告文件统一保存在 data/inspection_reports（可用 INSPECTION_REPORT_DIR 覆盖），
数据库只保存纯文件名，下载时再次校验路径必须落在报告目录内，防止路径穿越。
"""
from __future__ import annotations

import asyncio
import io
import logging
import os
import re
import secrets
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..config import PROJECT_ROOT
from ..models.database import SessionLocal
from ..models.inspection import InspectionReport, InspectionTask
from ..models.models import Alert, Device, DeviceMetric
from ..models.virtualization import (
    VirtualHost, VirtualMachine, VirtualPlatform, VirtualizationAlert,
)
from . import settings as settings_service
from . import vendor_commands

logger = logging.getLogger(__name__)

REPORTS_DIR = Path(
    os.getenv("INSPECTION_REPORT_DIR", str(PROJECT_ROOT / "data" / "inspection_reports"))
)
MAX_UPLOAD_MB = 50
MAX_UPLOAD_BYTES = MAX_UPLOAD_MB * 1024 * 1024
DEFAULT_REPORT_RETENTION_DAYS = 15
MAX_REPORT_RETENTION_DAYS = 3650
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
ONLINE_WINDOW_SECONDS = 600
MAX_TASK_INTERVAL_HOURS = 24 * 365
MAX_ASSETS_PER_TASK = 500
MAX_CUSTOM_DEVICES = 100
SCHEDULER_INTERVAL_SECONDS = 60

ALERT_LEVEL_LABELS = {
    "info": "提示",
    "warning": "警告",
    "critical": "严重",
    "emergency": "紧急",
}
ALERT_LEVEL_COLORS = {
    "info": "2563EB",
    "warning": "D97706",
    "critical": "DC2626",
    "emergency": "B91C1C",
}
ALERT_TYPE_TEXT = {
    "cpu": "CPU使用率",
    "memory": "内存使用率",
    "temperature": "温度",
    "power": "电源状态",
    "offline": "设备离线",
    "down": "探测失败",
    "slow": "响应缓慢",
    "ssl_expired": "证书过期",
    "vm_cpu": "虚拟机 CPU",
    "vm_memory": "虚拟机内存",
    "vm_disk": "虚拟机磁盘",
    "vm_shutdown": "虚拟机已关机",
}


class DocxUnavailableError(RuntimeError):
    """python-docx 未安装，无法生成/校验 Word 报告"""


def docx_available() -> bool:
    try:
        import docx  # noqa: F401
    except Exception:  # noqa: BLE001
        return False
    return True


def _require_docx():
    try:
        from docx import Document  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        raise DocxUnavailableError(
            "服务器未安装 python-docx，无法生成 Word 巡检报告。"
            "请在部署环境执行 pip install python-docx 后重试。"
        ) from exc


# ==================== 文件与路径安全 ====================
_UNSAFE_CHARS = re.compile(r"[^0-9A-Za-z_\-.()（）\u4e00-\u9fa5]+")
_DAILY_TIME_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def ensure_reports_dir() -> Path:
    root = Path(REPORTS_DIR)
    root.mkdir(parents=True, exist_ok=True)
    return root


def _base_name(filename: Any) -> str:
    """只取文件名部分（同时兼容 / 与 \\），去掉路径与隐藏字符"""
    text = str(filename or "").replace("\\", "/").rsplit("/", 1)[-1]
    text = text.replace("\x00", "").strip()
    return text


def safe_display_name(filename: Any, fallback: str = "inspection") -> str:
    base = _base_name(filename)
    if not base:
        return fallback
    stem = Path(base).stem[:80] or fallback
    stem = _UNSAFE_CHARS.sub("_", stem).strip("._ ") or fallback
    return f"{stem}.docx"


def report_path(stored_filename: Any) -> Path:
    """把数据库里的纯文件名解析到报告目录，并校验路径边界"""
    raw = str(stored_filename or "").strip().replace("\\", "/")
    if not raw or raw in (".", "..") or "/" in raw or "\x00" in raw:
        raise FileNotFoundError("巡检报告文件名非法")
    root = ensure_reports_dir().resolve()
    candidate = (root / raw).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise FileNotFoundError("巡检报告文件路径非法") from exc
    if candidate.suffix.lower() != ".docx":
        raise FileNotFoundError("巡检报告不是 Word .docx 文件")
    return candidate


def _unique_report_name(prefix: str) -> str:
    stamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
    return f"{prefix}_{stamp}_{secrets.token_hex(4)}.docx"


def validate_docx_bytes(content: bytes) -> None:
    """校验内容是否为可打开的 Word .docx（先看 ZIP 结构，有 python-docx 时再实际打开）"""
    if not content:
        raise ValueError("上传文件为空")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValueError(f"文件超过 {MAX_UPLOAD_MB}MB 限制")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile as exc:
        raise ValueError("文件不是有效的 Word .docx（无法解析压缩包）") from exc
    if "word/document.xml" not in names:
        raise ValueError("文件不是有效的 Word .docx（缺少 word/document.xml）")
    if docx_available():
        try:
            from docx import Document

            Document(io.BytesIO(content))
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"无法解析该 .docx 文件：{exc}") from exc


# ==================== 设备快照 ====================
def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _age_seconds(value: Optional[datetime]) -> Optional[float]:
    if not value:
        return None
    return max(0.0, (datetime.utcnow() - value).total_seconds())


def _alert_dict(alert: Alert, device: Optional[Device] = None) -> Dict[str, Any]:
    return {
        "id": alert.id,
        "level": alert.alert_level,
        "level_label": alert.level_label
        or ALERT_LEVEL_LABELS.get(alert.alert_level, alert.alert_level),
        "type": alert.alert_type,
        "message": alert.message or "",
        "reason": alert.message or alert.alert_type or "",
        "value": alert.value,
        "threshold": alert.threshold,
        "created_at": _iso(alert.created_at),
        "device_id": getattr(device, "id", None),
        "device_name": getattr(device, "name", "") or "",
        "device_ip": getattr(device, "ip_address", "") or "",
    }


def device_snapshot(db: Session, device: Device) -> Dict[str, Any]:
    """资产库设备的巡检快照：身份、在线状态、最新指标、未确认告警"""
    metric = (
        db.query(DeviceMetric)
        .filter(DeviceMetric.device_id == device.id)
        .order_by(DeviceMetric.collected_at.desc(), DeviceMetric.id.desc())
        .first()
    )
    alerts = (
        db.query(Alert)
        .filter(Alert.device_id == device.id, Alert.is_acknowledged.is_(False))
        .order_by(Alert.created_at.desc())
        .limit(20)
        .all()
    )
    age = _age_seconds(metric.collected_at) if metric else None
    if metric is None:
        online: Optional[bool] = None
    elif age is None:
        online = None
    else:
        online = age <= ONLINE_WINDOW_SECONDS
    custom = (metric.custom or {}) if metric else {}
    probe_alive = custom.get("probe_alive") if isinstance(custom, dict) else None
    if probe_alive in (0, "0", False):
        online = False
    probe_latency = custom.get("probe_latency_ms") if isinstance(custom, dict) else None
    return {
        "id": device.id,
        "name": device.name,
        "ip_address": device.ip_address,
        "device_type": device.device_type,
        "vendor": device.vendor or "",
        "model": device.model or "",
        "serial_number": device.serial_number or "",
        "location": device.location or "",
        "asset_no": device.asset_no or "",
        "monitor_type": device.monitor_type or "snmp",
        "is_enabled": bool(device.is_enabled),
        "managed": True,
        "online": online,
        "last_collected_at": _iso(metric.collected_at) if metric else None,
        "collect_age_seconds": round(age, 0) if age is not None else None,
        "cpu_usage": metric.cpu_usage if metric else None,
        "memory_usage": metric.memory_usage if metric else None,
        "memory_total": metric.memory_total if metric else None,
        "memory_used": metric.memory_used if metric else None,
        "disk_usage": metric.disk_usage if metric else None,
        "disk_total": metric.disk_total if metric else None,
        "disk_used": metric.disk_used if metric else None,
        "temperature": metric.temperature if metric else None,
        "power_status": metric.power_status if metric else None,
        "uptime": metric.uptime if metric else None,
        "probe_alive": probe_alive,
        "probe_latency_ms": probe_latency,
        "vendor_profile": vendor_commands.detect_vendor(device),
        "vendor_profile_label": vendor_commands.get_profile(device)["label"],
        "command_plan": vendor_commands.inspection_plan(device),
        "unack_alert_count": len(alerts),
        "alerts": [_alert_dict(item, device) for item in alerts[:20]],
    }


def custom_device_snapshot(item: Dict[str, Any]) -> Dict[str, Any]:
    """自定义设备没有采集数据，只纳入巡检清单并标记为未纳管"""
    vendor = str(item.get("vendor") or "").strip()
    custom_command = str(item.get("custom_command") or "").strip()
    matched = vendor_commands.profile_for_vendor(vendor) if vendor else None
    if matched:
        plan = [
            {"key": key, "label": label, "command": command}
            for key, label, command in matched["inspection"]
        ]
        profile_key = vendor_commands.match_vendor_text(vendor) or ""
        profile_label = matched["label"]
    elif custom_command:
        plan = [{"key": "custom", "label": "自定义巡检命令", "command": custom_command}]
        profile_key, profile_label = "custom", "自定义"
    else:
        plan, profile_key, profile_label = [], "", ""
    return {
        "id": None,
        "name": str(item.get("name") or "").strip(),
        "ip_address": str(item.get("ip_address") or "").strip(),
        "device_type": str(item.get("device_type") or "other").strip() or "other",
        "vendor": str(item.get("vendor") or "").strip(),
        "vendor_profile": profile_key,
        "vendor_profile_label": profile_label,
        "command_plan": plan,
        "inspection_commands": {
            "status": "not_requested",
            "error": "自定义设备未纳入采集，命令仅作巡检计划，不执行",
            "commands": [
                {"key": c["key"], "label": c["label"], "command": c["command"], "ok": False, "summary": "仅计划", "output": ""}
                for c in plan
            ],
            "log_findings": [],
        },
        "model": "",
        "serial_number": "",
        "location": "",
        "asset_no": "",
        "monitor_type": "custom",
        "is_enabled": True,
        "managed": False,
        "online": None,
        "last_collected_at": None,
        "collect_age_seconds": None,
        "cpu_usage": None,
        "memory_usage": None,
        "memory_total": None,
        "memory_used": None,
        "disk_usage": None,
        "disk_total": None,
        "disk_used": None,
        "temperature": None,
        "power_status": None,
        "uptime": None,
        "probe_alive": None,
        "probe_latency_ms": None,
        "unack_alert_count": 0,
        "alerts": [],
        "note": str(item.get("note") or "").strip(),
    }


def _virtual_alert_dict(alert: VirtualizationAlert, platform: VirtualPlatform) -> Dict[str, Any]:
    return {
        "id": alert.id,
        "platform_id": alert.platform_id or getattr(platform, "id", None),
        "platform_name": alert.platform_name or getattr(platform, "name", "") or "",
        "vm_name": alert.vm_name or "",
        "level": alert.alert_level or "warning",
        "level_label": ALERT_LEVEL_LABELS.get(alert.alert_level or "warning", alert.alert_level or "warning"),
        "type": alert.alert_type or "",
        "reason": alert.message or alert.alert_type or "",
        "message": alert.message or "",
        "value": alert.value,
        "threshold": alert.threshold,
        "created_at": _iso(alert.created_at),
    }


_VIRTUAL_TYPE_LABELS = {
    "vmware": "VMware vCenter",
    "cas": "H3C CAS",
    "kvm": "KVM / libvirt",
    "proxmox": "Proxmox VE",
    "docker": "Docker Engine",
    "kubernetes": "Kubernetes",
}


def virtualization_snapshot(db: Session) -> Dict[str, Any]:
    """汇总启用的虚拟化平台、宿主机、虚拟机和未确认虚拟化告警。"""
    platforms = (
        db.query(VirtualPlatform)
        .filter(VirtualPlatform.enabled.is_(True))
        .order_by(VirtualPlatform.name.asc())
        .all()
    )
    result: List[Dict[str, Any]] = []
    total_hosts = total_vms = total_alerts = 0
    for platform in platforms:
        hosts = (
            db.query(VirtualHost)
            .filter(VirtualHost.platform_id == platform.id)
            .order_by(VirtualHost.name.asc())
            .all()
        )
        vms = (
            db.query(VirtualMachine)
            .filter(VirtualMachine.platform_id == platform.id)
            .order_by(VirtualMachine.name.asc())
            .all()
        )
        alerts = (
            db.query(VirtualizationAlert)
            .filter(
                VirtualizationAlert.platform_id == platform.id,
                VirtualizationAlert.is_acknowledged.is_(False),
                VirtualizationAlert.resolved_at.is_(None),
            )
            .order_by(VirtualizationAlert.created_at.desc())
            .limit(50)
            .all()
        )
        total_hosts += len(hosts)
        total_vms += len(vms)
        total_alerts += len(alerts)
        result.append({
            "id": platform.id,
            "name": platform.name,
            "platform_type": platform.platform_type,
            "platform_type_label": _VIRTUAL_TYPE_LABELS.get(platform.platform_type, platform.platform_type),
            "address": platform.address,
            "port": platform.port,
            "last_sync_at": _iso(platform.last_sync_at),
            "last_sync_status": platform.last_sync_status or "never",
            "last_error": platform.last_error or "",
            "host_count": len(hosts),
            "host_online": sum(1 for host in hosts if (host.status or "") == "online"),
            "vm_count": len(vms),
            "vm_running": sum(1 for vm in vms if (vm.power_state or "") == "running"),
            "vm_stopped": sum(1 for vm in vms if (vm.power_state or "") in ("stopped", "paused")),
            "alerts": [_virtual_alert_dict(alert, platform) for alert in alerts],
            "hosts": [
                {
                    "name": host.name,
                    "ip_address": host.ip_address or "",
                    "cluster_name": host.cluster_name or "",
                    "status": host.status or "unknown",
                    "cpu_usage": host.cpu_usage,
                    "memory_usage": host.memory_usage,
                    "storage_usage": host.storage_usage,
                    "vm_count": host.vm_count or 0,
                }
                for host in hosts[:200]
            ],
            "vms": [
                {
                    "name": vm.name,
                    "power_state": vm.power_state or "unknown",
                    "primary_ip": vm.primary_ip or "",
                    "vcpu": vm.vcpu or 0,
                    "memory_mb": vm.memory_mb or 0,
                    "disk_usage": vm.disk_usage,
                }
                for vm in vms[:200]
            ],
        })
    return {
        "enabled": True,
        "platforms": result,
        "stats": {
            "platforms": len(result),
            "hosts": total_hosts,
            "vms": total_vms,
            "alerts": total_alerts,
        },
    }


# ==================== 结论与建议 ====================
def _metric_text(value: Any, unit: str = "") -> str:
    if value is None or value == "":
        return "未采集"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    text = f"{number:.1f}".rstrip("0").rstrip(".")
    return f"{text}{unit}"


def _uptime_text(seconds: Any) -> str:
    try:
        total = int(seconds or 0)
    except (TypeError, ValueError):
        return "未采集"
    if total <= 0:
        return "未采集"
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60
    if days:
        return f"{days} 天 {hours} 小时"
    if hours:
        return f"{hours} 小时 {minutes} 分钟"
    return f"{minutes} 分钟"


def _power_text(value: Any) -> str:
    return {"normal": "正常", "failure": "故障"}.get(str(value or ""), "未采集")


def _device_issues(snapshot: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    """返回 (级别, 问题描述, 建议)，级别：critical/warning/info"""
    issues: List[Tuple[str, str, str]] = []
    if not snapshot.get("managed"):
        issues.append(
            (
                "info",
                "自定义设备未纳管，无法获取实时指标",
                "将自定义设备纳管到资产管理后，可获取 CPU/内存/温度等实时指标与告警",
            )
        )
        return issues
    if snapshot.get("online") is False:
        issues.append(
            (
                "critical",
                "设备离线或采集数据已过期",
                "检查设备电源与网络链路，确认 SNMP/Ping/TCP 采集参数后重新采集",
            )
        )
    if snapshot.get("last_collected_at") is None:
        issues.append(
            (
                "warning",
                "暂无采集数据",
                "确认设备已启用监控且采集参数配置正确，等待下一轮采集后再复检",
            )
        )
    cpu = snapshot.get("cpu_usage")
    if cpu is not None and float(cpu) >= 90:
        issues.append(
            ("critical", f"CPU 使用率过高（{_metric_text(cpu, '%')}）",
             "排查异常进程或突发流量，必要时扩容、限速或调整业务部署")
        )
    elif cpu is not None and float(cpu) >= 80:
        issues.append(
            ("warning", f"CPU 使用率偏高（{_metric_text(cpu, '%')}）",
             "持续观察 CPU 趋势，排查高负载进程与流量峰值")
        )
    memory = snapshot.get("memory_usage")
    if memory is not None and float(memory) >= 90:
        issues.append(
            ("critical", f"内存使用率过高（{_metric_text(memory, '%')}）",
             "检查内存占用进程与内存泄漏，必要时扩容或重启相关服务")
        )
    elif memory is not None and float(memory) >= 85:
        issues.append(
            ("warning", f"内存使用率偏高（{_metric_text(memory, '%')}）",
             "关注内存增长趋势，清理无用进程或评估扩容")
        )
    temperature = snapshot.get("temperature")
    if temperature is not None and float(temperature) >= 80:
        issues.append(
            ("critical", f"设备温度过高（{_metric_text(temperature, '°C')}）",
             "立即检查风扇、环境温度与散热通道，避免设备过热宕机")
        )
    elif temperature is not None and float(temperature) >= 70:
        issues.append(
            ("warning", f"设备温度偏高（{_metric_text(temperature, '°C')}）",
             "检查机房空调、风扇转速与设备进出风口是否堵塞")
        )
    disk = snapshot.get("disk_usage")
    if disk is not None and float(disk) >= 90:
        issues.append(
            ("critical", f"磁盘使用率过高（{_metric_text(disk, '%')}）",
             "清理日志/临时文件或扩容磁盘，避免影响业务写入")
        )
    elif disk is not None and float(disk) >= 80:
        issues.append(
            ("warning", f"磁盘使用率偏高（{_metric_text(disk, '%')}）",
             "规划日志轮转与容量扩容，持续关注磁盘增长")
        )
    if str(snapshot.get("power_status") or "") == "failure":
        issues.append(
            ("critical", "电源状态异常",
             "检查电源模块、供电线路与冗余电源状态，尽快更换故障电源")
        )
    critical_alerts = [
        alert
        for alert in snapshot.get("alerts") or []
        if alert.get("level") in ("critical", "emergency")
    ]
    if critical_alerts:
        issues.append(
            (
                "critical",
                f"存在 {len(critical_alerts)} 条严重/紧急未确认告警",
                "优先处理严重/紧急级别告警，定位根因并确认恢复后再关闭告警",
            )
        )
    return issues


def _build_conclusion(
    snapshots: List[Dict[str, Any]], issues: Dict[int, List[Tuple[str, str, str]]]
) -> str:
    managed = [item for item in snapshots if item.get("managed")]
    custom = [item for item in snapshots if not item.get("managed")]
    total = len(snapshots)
    online = sum(1 for item in managed if item.get("online"))
    offline = sum(1 for item in managed if item.get("online") is False)
    unknown = len(managed) - online - offline
    critical = sum(
        1
        for items in issues.values()
        for level, _desc, _rec in items
        if level == "critical"
    )
    warning = sum(
        1
        for items in issues.values()
        for level, _desc, _rec in items
        if level == "warning"
    )
    parts = [
        f"本次巡检共 {total} 台设备（资产库 {len(managed)} 台，自定义 {len(custom)} 台）："
        f"在线 {online} 台，离线 {offline} 台，状态未知 {unknown} 台。"
    ]
    if critical:
        parts.append(f"发现 {critical} 项严重问题，建议立即处理。")
    elif warning:
        parts.append(f"发现 {warning} 项预警项，建议按整改建议逐项处理。")
    else:
        parts.append("本次巡检未发现需要立即处理的异常，整体运行状态良好。")
    if custom:
        parts.append("自定义设备未纳管，无法获取实时指标，仅供参考。")
    return "".join(parts)


def _build_recommendations(
    issues: Dict[int, List[Tuple[str, str, str]]]
) -> List[str]:
    ordered: List[str] = []
    for items in issues.values():
        for _level, _desc, rec in items:
            if rec and rec not in ordered:
                ordered.append(rec)
    if not ordered:
        return [
            "本次巡检未发现需要整改的问题，建议保持定期巡检。",
            "保持巡检任务定时执行，持续跟踪设备运行趋势。",
        ]
    ordered.append("对本次巡检发现的问题整改后进行复检，确认指标恢复正常")
    return ordered[:10]


def build_task_payload(
    db: Session, task: InspectionTask, devices: List[Device], custom_devices: List[Dict[str, Any]]
) -> Dict[str, Any]:
    snapshots = [device_snapshot(db, device) for device in devices]
    snapshots.extend(custom_device_snapshot(item) for item in custom_devices)
    issues: Dict[int, List[Tuple[str, str, str]]] = {}
    for index, snapshot in enumerate(snapshots):
        issues[index] = _device_issues(snapshot)

    # 厂商巡检命令：仅对启用了“执行厂商巡检命令”的任务，使用设备备份 SSH 凭据执行。
    run_commands = bool(getattr(task, "run_commands", False))
    for index, device in enumerate(devices):
        snapshot = snapshots[index]
        snapshot["inspection_commands"] = {
            "profile": snapshot.get("vendor_profile"),
            "profile_label": snapshot.get("vendor_profile_label"),
            "status": "not_requested" if not run_commands else "skipped",
            "error": "" if run_commands else "任务未启用厂商巡检命令",
            "commands": [],
            "log_findings": [],
        }
        if not run_commands:
            continue
        result = vendor_commands.run_inspection_commands(device)
        snapshot["inspection_commands"] = result
        if result.get("status") == "failed":
            issues[index].append((
                "warning",
                f"厂商巡检命令执行失败：{result.get('error') or '未知错误'}",
                "检查设备备份 SSH 用户名/密码与网络连通性，或改为仅使用 SNMP 指标巡检",
            ))
        findings = result.get("log_findings") or []
        if findings:
            issues[index].append((
                "warning",
                f"日志中发现 {len(findings)} 条疑似异常记录",
                "登录设备查看日志上下文，确认是否为链路抖动、认证失败、硬件或协议异常",
            ))
        if result.get("status") == "skipped" and result.get("error"):
            issues[index].append(("info", result["error"], "可在设备备份配置中补充 SSH 凭据后重新巡检"))
    for index, snapshot in enumerate(snapshots):
        snapshot["issues"] = [
            {"level": level, "description": desc, "recommendation": rec}
            for level, desc, rec in issues[index]
        ]
    include_virtualization = bool(getattr(task, "include_virtualization", False))
    virtualization = (
        virtualization_snapshot(db)
        if include_virtualization
        else {"enabled": False, "platforms": [], "stats": {"platforms": 0, "hosts": 0, "vms": 0, "alerts": 0}}
    )
    virtual_alerts = [
        alert
        for platform in virtualization.get("platforms") or []
        for alert in platform.get("alerts") or []
    ]
    conclusion = _build_conclusion(snapshots, issues)
    if include_virtualization:
        vstats = virtualization.get("stats") or {}
        conclusion += (
            f"虚拟化平台巡检 {vstats.get('platforms', 0)} 个，"
            f"宿主机 {vstats.get('hosts', 0)} 台，虚拟机 {vstats.get('vms', 0)} 台，"
            f"未确认虚拟化告警 {vstats.get('alerts', 0)} 条。"
        )
    recommendations = _build_recommendations(issues)
    if virtual_alerts:
        critical_virtual = sum(1 for alert in virtual_alerts if alert.get("level") in ("critical", "emergency"))
        if critical_virtual:
            recommendations.append("优先处理虚拟化平台严重/紧急告警，确认宿主机和虚拟机恢复后再关闭告警")
        else:
            recommendations.append("检查虚拟化平台告警对应的宿主机资源与虚拟机运行状态")
        recommendations = recommendations[:10]
    unack = sum(int(item.get("unack_alert_count") or 0) for item in snapshots) + len(virtual_alerts)
    managed = [item for item in snapshots if item.get("managed")]
    return {
        "generated_at": _iso(datetime.utcnow()),
        "task": {
            "id": task.id if task else None,
            "name": task.name if task else "",
            "schedule_type": task.schedule_type if task else "manual",
            "interval_hours": task.interval_hours if task else None,
            "daily_time": task.daily_time if task else None,
            "include_virtualization": include_virtualization,
        },
        "stats": {
            "total": len(snapshots),
            "managed": len(managed),
            "custom": len(snapshots) - len(managed),
            "online": sum(1 for item in managed if item.get("online")),
            "offline": sum(1 for item in managed if item.get("online") is False),
            "unknown": sum(1 for item in managed if item.get("online") is None),
            "unack_alerts": unack,
            "virtualization_alerts": len(virtual_alerts),
        },
        "devices": snapshots,
        "virtualization": virtualization,
        "conclusion": conclusion,
        "recommendations": recommendations,
    }


# ==================== Word 报告 ====================
def _docx_set_cn_font(run, size: Optional[float] = None, bold: Optional[bool] = None) -> None:
    try:
        from docx.oxml.ns import qn
        from docx.shared import Pt

        run.font.name = "Microsoft YaHei"
        run._element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
        if size:
            run.font.size = Pt(size)
        if bold is not None:
            run.bold = bold
    except Exception:  # noqa: BLE001 - 字体美化失败不影响正文
        pass


def _docx_set_run_color(run, level: str) -> None:
    try:
        from docx.shared import RGBColor
        run.font.color.rgb = RGBColor.from_string(ALERT_LEVEL_COLORS.get(str(level).lower(), "334155"))
        run.font.bold = True
    except Exception:  # noqa: BLE001
        pass


def _docx_write_issue(document, issue: Dict[str, Any]) -> None:
    from docx.shared import Pt
    level = str(issue.get("level") or "info").lower()
    label = ALERT_LEVEL_LABELS.get(level, level)
    paragraph = document.add_paragraph(style="List Bullet")
    prefix = paragraph.add_run(f"[{label}] ")
    _docx_set_cn_font(prefix, size=10, bold=True)
    _docx_set_run_color(prefix, level)
    body = paragraph.add_run(str(issue.get("description") or ""))
    _docx_set_cn_font(body, size=10)
    body.font.size = Pt(10)


def _docx_kv_table(document, rows: List[Tuple[str, str]]):
    from docx.shared import Pt

    table = document.add_table(rows=0, cols=2)
    table.style = "Table Grid"
    for key, value in rows:
        cells = table.add_row().cells
        for cell, text, bold in (
            (cells[0], str(key), True),
            (cells[1], str(value), False),
        ):
            cell.text = ""
            paragraph = cell.paragraphs[0]
            run = paragraph.add_run(text)
            _docx_set_cn_font(run, size=10, bold=bold)
            run.font.size = Pt(10)
    return table


def _alert_reason(alert: Dict[str, Any]) -> str:
    return (
        str(alert.get("reason") or alert.get("message") or "").strip()
        or ALERT_TYPE_TEXT.get(str(alert.get("type") or ""), str(alert.get("type") or "告警"))
    )


def _alert_time_text(value: Any) -> str:
    if not value:
        return "-"
    try:
        text = str(value).replace("Z", "+00:00")
        return datetime.fromisoformat(text).strftime("%Y-%m-%d %H:%M:%S")
    except (TypeError, ValueError):
        return str(value)


def _docx_write_alert(document, alert: Dict[str, Any], fallback_target: str = "") -> None:
    """按告警级别写入彩色加粗的告警明细。"""
    from docx.shared import RGBColor

    level = str(alert.get("level") or "warning").lower()
    label = alert.get("level_label") or ALERT_LEVEL_LABELS.get(level, level)
    target = (
        alert.get("device_name")
        or alert.get("vm_name")
        or alert.get("platform_name")
        or fallback_target
        or "未知对象"
    )
    ip = str(alert.get("device_ip") or "").strip()
    target_text = f"{target}（{ip}）" if ip else target
    reason = _alert_reason(alert)
    paragraph = document.add_paragraph(style="List Bullet")
    run = paragraph.add_run(
        f"[{label}] 告警对象：{target_text}｜时间：{_alert_time_text(alert.get('created_at'))}｜告警原因：{reason}"
    )
    _docx_set_cn_font(run, size=10, bold=True)
    try:
        run.font.bold = True
        run.font.color.rgb = RGBColor.from_string(ALERT_LEVEL_COLORS.get(level, "334155"))
    except Exception:  # noqa: BLE001
        pass


def _docx_data_table(document, headers: List[str], rows: List[List[str]]):
    if not rows:
        return
    from docx.shared import Pt

    table = document.add_table(rows=1, cols=len(headers))
    table.style = "Table Grid"
    for index, header in enumerate(headers):
        cell = table.rows[0].cells[index]
        cell.text = ""
        run = cell.paragraphs[0].add_run(str(header))
        _docx_set_cn_font(run, size=9, bold=True)
    for row in rows:
        cells = table.add_row().cells
        for index, value in enumerate(row):
            cells[index].text = ""
            run = cells[index].paragraphs[0].add_run(str(value if value is not None else "-"))
            _docx_set_cn_font(run, size=9)
            try:
                run.font.size = Pt(9)
            except Exception:  # noqa: BLE001
                pass
    return table


def _write_builtin_docx(payload: Dict[str, Any], title: str, path: Path) -> None:
    _require_docx()
    from docx import Document
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.shared import Pt

    document = Document()
    style = document.styles["Normal"]
    try:
        style.font.name = "Microsoft YaHei"
        style.font.size = Pt(10.5)
        from docx.oxml.ns import qn

        style.element.rPr.rFonts.set(qn("w:eastAsia"), "Microsoft YaHei")
    except Exception:  # noqa: BLE001
        pass

    heading = document.add_paragraph()
    heading.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = heading.add_run(title)
    _docx_set_cn_font(run, size=18, bold=True)

    meta = document.add_paragraph()
    meta.alignment = WD_ALIGN_PARAGRAPH.CENTER
    meta_run = meta.add_run(
        f"生成时间：{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}（服务器本地时间）"
    )
    _docx_set_cn_font(meta_run, size=9)

    task_info = payload.get("task") or {}
    stats = payload.get("stats") or {}
    virtualization = payload.get("virtualization") or {}
    virt_stats = virtualization.get("stats") or {}
    trigger_value = str(payload.get("trigger") or "")
    if trigger_value == "scheduled":
        trigger_label = "定时巡检"
    elif trigger_value == "upload":
        trigger_label = "上传报告"
    else:
        trigger_label = "手动巡检"
    _docx_kv_table(
        document,
        [
            ("巡检任务", task_info.get("name") or "即时巡检"),
            ("执行方式", trigger_label),
            ("设备数量", f"{stats.get('total', 0)} 台"),
            (
                "在线情况",
                f"在线 {stats.get('online', 0)} 台 / 离线 {stats.get('offline', 0)} 台"
                f" / 未知 {stats.get('unknown', 0)} 台",
            ),
            ("未确认告警", f"{stats.get('unack_alerts', 0)} 条"),
            *([("虚拟化平台", f"{virt_stats.get('platforms', 0)} 个 / 宿主机 {virt_stats.get('hosts', 0)} 台 / 虚拟机 {virt_stats.get('vms', 0)} 台")] if virtualization.get("enabled") else []),
        ],
    )

    document.add_heading("一、巡检结论", level=1)
    document.add_paragraph(payload.get("conclusion") or "无")

    document.add_heading("二、设备明细", level=1)
    devices = payload.get("devices") or []
    if not devices:
        document.add_paragraph("本次巡检没有设备。")
    for item in devices:
        name = item.get("name") or "未命名设备"
        ip = item.get("ip_address") or "-"
        document.add_heading(f"{name}（{ip}）", level=2)
        if not item.get("managed"):
            _docx_kv_table(
                document,
                [
                    ("设备类型", item.get("device_type") or "-"),
                    ("巡检状态", "未纳管（无实时指标）"),
                    ("备注", item.get("note") or "-"),
                ],
            )
            continue
        status = "在线" if item.get("online") else ("离线" if item.get("online") is False else "状态未知")
        _docx_kv_table(
            document,
            [
                ("设备类型", item.get("device_type") or "-"),
                ("厂商 / 型号", f"{item.get('vendor') or '-'} / {item.get('model') or '-'}"),
                ("位置 / 资产编号", f"{item.get('location') or '-'} / {item.get('asset_no') or '-'}"),
                ("在线状态", status),
                ("最近采集", item.get("last_collected_at") or "无采集记录"),
            ],
        )
        document.add_paragraph()
        _docx_kv_table(
            document,
            [
                ("CPU 使用率", _metric_text(item.get("cpu_usage"), "%")),
                ("内存使用率", _metric_text(item.get("memory_usage"), "%")),
                ("温度", _metric_text(item.get("temperature"), "°C")),
                ("磁盘使用率", _metric_text(item.get("disk_usage"), "%")),
                ("电源状态", _power_text(item.get("power_status"))),
                ("运行时间", _uptime_text(item.get("uptime"))),
                ("未确认告警", f"{item.get('unack_alert_count', 0)} 条"),
            ],
        )
        alerts = item.get("alerts") or []
        if alerts:
            paragraph = document.add_paragraph()
            _docx_set_cn_font(paragraph.add_run("未确认告警："), size=10, bold=True)
            for alert in alerts[:20]:
                _docx_write_alert(document, alert, fallback_target=name)
        issues = item.get("issues") or []
        if issues:
            document.add_paragraph("发现问题：")
            for issue in issues:
                _docx_write_issue(document, issue)
        commands = item.get("inspection_commands") or {}
        if commands.get("commands"):
            document.add_heading("厂商巡检命令", level=3)
            _docx_data_table(
                document,
                ["检查项", "命令", "执行状态", "返回摘要"],
                [[
                    cmd.get("label") or cmd.get("key") or "-",
                    cmd.get("command") or "-",
                    "成功" if cmd.get("ok") else "失败/无返回",
                    cmd.get("summary") or "-",
                ] for cmd in commands.get("commands") or []],
            )
            if commands.get("error"):
                document.add_paragraph(f"命令说明：{commands.get('error')}")
            findings = commands.get("log_findings") or []
            if findings:
                document.add_paragraph("日志异常提示：")
                for finding in findings[:10]:
                    document.add_paragraph(finding.get("line") or "", style="List Bullet")

    if virtualization.get("enabled"):
        document.add_heading("三、虚拟化平台巡检", level=1)
        platforms = virtualization.get("platforms") or []
        if not platforms:
            document.add_paragraph("已开启虚拟化平台巡检，但当前没有启用的虚拟化平台。")
        else:
            document.add_paragraph(
                f"本次共巡检虚拟化平台 {virt_stats.get('platforms', 0)} 个，"
                f"宿主机 {virt_stats.get('hosts', 0)} 台，虚拟机 {virt_stats.get('vms', 0)} 台，"
                f"未确认虚拟化告警 {virt_stats.get('alerts', 0)} 条。"
            )
        for platform in platforms:
            document.add_heading(
                f"{platform.get('name') or '未命名平台'}（{platform.get('platform_type_label') or platform.get('platform_type') or '-'}）",
                level=2,
            )
            _docx_kv_table(
                document,
                [
                    ("管理地址", f"{platform.get('address') or '-'}:{platform.get('port') or '-'}"),
                    ("最后同步", platform.get("last_sync_at") or "从未同步"),
                    ("同步状态", platform.get("last_sync_status") or "never"),
                    ("宿主机", f"{platform.get('host_count', 0)} 台，在线 {platform.get('host_online', 0)} 台"),
                    ("虚拟机", f"{platform.get('vm_count', 0)} 台，运行中 {platform.get('vm_running', 0)} 台"),
                    ("未确认告警", f"{len(platform.get('alerts') or [])} 条"),
                ],
            )
            hosts = platform.get("hosts") or []
            if hosts:
                document.add_heading("宿主机", level=3)
                _docx_data_table(
                    document,
                    ["名称", "IP", "状态", "CPU%", "内存%", "存储%", "虚拟机"],
                    [[
                        host.get("name") or "-", host.get("ip_address") or "-",
                        host.get("status") or "unknown", _metric_text(host.get("cpu_usage"), "%"),
                        _metric_text(host.get("memory_usage"), "%"),
                        _metric_text(host.get("storage_usage"), "%"),
                        host.get("vm_count", 0),
                    ] for host in hosts],
                )
            vms = platform.get("vms") or []
            if vms:
                document.add_heading("虚拟机", level=3)
                _docx_data_table(
                    document,
                    ["名称", "状态", "IP", "vCPU", "内存(MB)", "磁盘%"],
                    [[
                        vm.get("name") or "-", vm.get("power_state") or "unknown",
                        vm.get("primary_ip") or "-", vm.get("vcpu", 0),
                        _metric_text(vm.get("memory_mb"), ""),
                        _metric_text(vm.get("disk_usage"), "%"),
                    ] for vm in vms],
                )
            alerts = platform.get("alerts") or []
            if alerts:
                paragraph = document.add_paragraph()
                _docx_set_cn_font(paragraph.add_run("未确认虚拟化告警："), size=10, bold=True)
                for alert in alerts:
                    _docx_write_alert(document, alert, fallback_target=platform.get("name") or "")
        recommendation_heading = "四、整改建议"
    else:
        recommendation_heading = "三、整改建议"

    document.add_heading(recommendation_heading, level=1)
    recommendations = payload.get("recommendations") or []
    if recommendations:
        for index, text in enumerate(recommendations, 1):
            document.add_paragraph(f"{index}. {text}")
    else:
        document.add_paragraph("本次巡检未发现需要整改的问题，建议保持定期巡检。")

    document.add_paragraph()
    footer = document.add_paragraph()
    footer.alignment = WD_ALIGN_PARAGRAPH.CENTER
    footer_run = footer.add_run("本报告由智能运维服务平台自动生成")
    _docx_set_font_helper(footer_run)

    path.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(path))


def _docx_set_font_helper(run) -> None:
    _docx_set_cn_font(run, size=8)


def create_builtin_report(
    db: Session,
    task: InspectionTask,
    payload: Dict[str, Any],
    trigger: str = "manual",
    username: str = "",
) -> InspectionReport:
    """生成内置巡检报告的 Word 文件与数据库记录（不提交事务）"""
    stored_name = _unique_report_name(f"inspection_{task.id if task else 'adhoc'}")
    path = report_path(stored_name)
    task_name = task.name if task else "即时巡检"
    title = f"{task_name}报告" if task_name.endswith("巡检") else f"{task_name}巡检报告"
    payload = dict(payload or {})
    payload["trigger"] = trigger
    try:
        _write_builtin_docx(payload, title, path)
        size = path.stat().st_size
        if size <= 0:
            raise RuntimeError("Word 报告生成失败：文件为空")
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    stats = payload.get("stats") or {}
    report = InspectionReport(
        task_id=task.id if task else None,
        task_name=(task.name if task else "")[:200],
        title=title[:300],
        source="builtin",
        trigger=trigger,
        status="success",
        device_count=int(stats.get("total") or 0),
        online_count=int(stats.get("online") or 0),
        alert_count=int(stats.get("unack_alerts") or 0),
        summary=(payload.get("conclusion") or "")[:2000],
        conclusion=payload.get("conclusion") or "",
        recommendations=payload.get("recommendations") or [],
        payload=payload,
        filename=stored_name,
        original_filename=safe_display_name(title, "inspection"),
        file_size=size,
        content_type=DOCX_MIME,
        created_by=(username or "")[:100],
        created_at=datetime.utcnow(),
    )
    db.add(report)
    db.flush()
    if task:
        task.last_run_at = datetime.utcnow()
        task.last_status = "success"
        task.last_message = f"巡检完成，已生成报告 #{report.id}"
        task.last_report_id = report.id
    return report


def resolve_task_targets(
    db: Session, task: InspectionTask
) -> Tuple[List[Device], List[Dict[str, Any]]]:
    asset_ids: List[int] = []
    for raw in task.asset_ids or []:
        try:
            asset_ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    devices: List[Device] = []
    if asset_ids:
        devices = (
            db.query(Device)
            .filter(Device.id.in_(asset_ids))
            .order_by(Device.name.asc())
            .all()
        )
    custom: List[Dict[str, Any]] = []
    for item in task.custom_devices or []:
        if isinstance(item, dict) and (item.get("name") or item.get("ip_address")):
            custom.append(item)
    return devices, custom


def generate_task_report(
    db: Session, task: InspectionTask, trigger: str = "manual", username: str = ""
) -> InspectionReport:
    """为巡检任务生成报告并提交事务；失败时回滚且不留下半成品文件"""
    if not task:
        raise ValueError("巡检任务不存在")
    devices, custom = resolve_task_targets(db, task)
    if not devices and not custom:
        if not (bool(getattr(task, "include_virtualization", False)) and db.query(VirtualPlatform).count() > 0):
            raise ValueError("巡检任务没有可巡检对象，请先选择资产、添加自定义设备，或配置虚拟化平台")
    payload = build_task_payload(db, task, devices, custom)
    try:
        report = create_builtin_report(db, task, payload, trigger=trigger, username=username)
        db.commit()
        return report
    except Exception:
        db.rollback()
        raise


def run_task_now(db: Session, task: InspectionTask, username: str = "") -> InspectionReport:
    """立即执行巡检（不影响定时计划的 next_run_at）"""
    return generate_task_report(db, task, trigger="manual", username=username)


# ==================== 上传自定义报告 ====================
def save_uploaded_report(
    db: Session,
    *,
    content: bytes,
    original_filename: str,
    title: str = "",
    note: str = "",
    task: Optional[InspectionTask] = None,
    username: str = "",
) -> InspectionReport:
    """保存上传的 Word 报告（仅 .docx），下载时原样提供"""
    original = _base_name(original_filename) or "upload.docx"
    suffix = Path(original).suffix.lower()
    if suffix == ".doc":
        raise ValueError(
            "暂不支持旧版 .doc：该格式无法直接作为 Word .docx 下载。"
            "请在 Word/WPS 中另存为 .docx 后重新上传，或使用巡检任务自动生成 .docx 报告。"
        )
    if suffix != ".docx":
        raise ValueError("仅支持上传 .docx 格式的 Word 巡检报告（旧版 .doc 请先另存为 .docx）")
    validate_docx_bytes(content)

    root = ensure_reports_dir()
    stored_name = _unique_report_name("upload")
    path = report_path(stored_name)
    try:
        path.write_bytes(content)
        size = path.stat().st_size
    except Exception:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise

    display_title = (title or "").strip() or Path(original).stem[:300] or "上传巡检报告"
    note_text = (note or "").strip()
    summary = f"上传的自定义巡检报告：{original}"
    if note_text:
        summary = f"{summary}。说明：{note_text}"
    payload = {
        "kind": "upload",
        "original_filename": original,
        "note": note_text,
        "size": size,
        "uploaded_at": _iso(datetime.utcnow()),
    }
    report = InspectionReport(
        task_id=task.id if task else None,
        task_name=(task.name if task else "")[:200],
        title=display_title[:300],
        source="upload",
        trigger="upload",
        status="success",
        device_count=0,
        online_count=0,
        alert_count=0,
        summary=summary[:2000],
        conclusion=note_text,
        recommendations=[],
        payload=payload,
        filename=stored_name,
        original_filename=original[:255],
        file_size=size,
        content_type=DOCX_MIME,
        created_by=(username or "")[:100],
        created_at=datetime.utcnow(),
    )
    try:
        db.add(report)
        db.commit()
    except Exception:
        db.rollback()
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return report


def delete_report_file(report: InspectionReport) -> None:
    """删除报告文件（路径必须位于报告目录内）"""
    if not report.filename:
        return
    try:
        path = report_path(report.filename)
    except FileNotFoundError:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:  # noqa: BLE001
        logger.warning("删除巡检报告文件失败 %s: %s", path, exc)


def normalize_retention_days(value: Any) -> int:
    try:
        days = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("报告保留天数必须是整数") from exc
    if days < 0 or days > MAX_REPORT_RETENTION_DAYS:
        raise ValueError(f"报告保留天数应为 0~{MAX_REPORT_RETENTION_DAYS} 天（0 表示永久保留）")
    return days


def report_retention_days(db: Session) -> int:
    raw = settings_service.get_value(db, "inspection_report_retention_days")
    if raw is None or raw == "":
        return DEFAULT_REPORT_RETENTION_DAYS
    try:
        return normalize_retention_days(raw)
    except ValueError:
        return DEFAULT_REPORT_RETENTION_DAYS


def cleanup_expired_reports(db: Session) -> int:
    """删除超过保留期的巡检报告及其 Word 文件；0 天表示永久保留。"""
    days = report_retention_days(db)
    if days <= 0:
        return 0
    cutoff = datetime.utcnow() - timedelta(days=days)
    rows = db.query(InspectionReport).filter(InspectionReport.created_at < cutoff).all()
    if not rows:
        return 0
    for report in rows:
        delete_report_file(report)
        db.delete(report)
    db.commit()
    logger.info("巡检报告到期清理 %s 条（保留 %s 天）", len(rows), days)
    return len(rows)


# ==================== 调度 ====================
def _schedule_timezone(db: Session):
    """读取系统配置时区，失败时回退服务器本地时区"""
    try:
        name = str(settings_service.get_value(db, "timezone") or "").strip()
    except Exception:  # noqa: BLE001
        name = ""
    if name:
        try:
            from zoneinfo import ZoneInfo

            return ZoneInfo(name)
        except Exception:  # noqa: BLE001
            pass
    return datetime.now().astimezone().tzinfo or timezone.utc


def _parse_daily_time(value: Any) -> Tuple[int, int]:
    matched = _DAILY_TIME_RE.match(str(value or "").strip())
    if not matched:
        raise ValueError("每日执行时间格式应为 HH:mm")
    return int(matched.group(1)), int(matched.group(2))


def compute_next_run(
    db: Session, task: InspectionTask, base_utc: Optional[datetime] = None
) -> Optional[datetime]:
    """计算下次执行时间（UTC 朴素时间）；未启用返回 None"""
    if not task or not task.enabled:
        return None
    base = base_utc or datetime.utcnow()
    if str(task.schedule_type or "interval") == "daily":
        hour, minute = _parse_daily_time(task.daily_time)
        tz = _schedule_timezone(db)
        local_now = datetime.now(tz)
        candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= local_now:
            candidate = candidate + timedelta(days=1)
        return candidate.astimezone(timezone.utc).replace(tzinfo=None)
    try:
        hours = int(task.interval_hours or 24)
    except (TypeError, ValueError):
        hours = 24
    hours = max(1, min(MAX_TASK_INTERVAL_HOURS, hours))
    return base + timedelta(hours=hours)


def schedule_text(task: InspectionTask) -> str:
    if not task:
        return ""
    if str(task.schedule_type or "interval") == "daily":
        return f"每天 {task.daily_time or '02:00'}"
    try:
        hours = int(task.interval_hours or 24)
    except (TypeError, ValueError):
        hours = 24
    return f"每 {max(1, hours)} 小时"


def normalize_daily_time(value: Any) -> str:
    """校验并归一化每日执行时间为 HH:mm"""
    hour, minute = _parse_daily_time(value)
    return f"{hour:02d}:{minute:02d}"


def validate_schedule(task: InspectionTask) -> None:
    schedule_type = str(task.schedule_type or "interval")
    if schedule_type not in ("interval", "daily"):
        raise ValueError("调度方式仅支持 interval（每 N 小时）或 daily（每天 HH:mm）")
    if schedule_type == "interval":
        try:
            hours = int(task.interval_hours or 0)
        except (TypeError, ValueError) as exc:
            raise ValueError("巡检间隔必须是整数小时") from exc
        if hours < 1 or hours > MAX_TASK_INTERVAL_HOURS:
            raise ValueError(f"巡检间隔应为 1~{MAX_TASK_INTERVAL_HOURS} 小时")
        task.interval_hours = hours
    else:
        task.daily_time = normalize_daily_time(task.daily_time)


def validate_custom_devices(items: Any) -> List[Dict[str, Any]]:
    if items is None:
        return []
    if not isinstance(items, list):
        raise ValueError("自定义设备格式不正确")
    if len(items) > MAX_CUSTOM_DEVICES:
        raise ValueError(f"自定义设备最多 {MAX_CUSTOM_DEVICES} 台")
    result: List[Dict[str, Any]] = []
    for index, item in enumerate(items, 1):
        if not isinstance(item, dict):
            raise ValueError(f"第 {index} 个自定义设备格式不正确")
        name = str(item.get("name") or "").strip()
        ip_address = str(item.get("ip_address") or "").strip()
        device_type = str(item.get("device_type") or "other").strip() or "other"
        vendor = str(item.get("vendor") or "").strip()
        custom_command = str(item.get("custom_command") or "").strip()
        note = str(item.get("note") or "").strip()
        if not name:
            raise ValueError(f"第 {index} 个自定义设备未填写名称")
        if not ip_address:
            raise ValueError(f"自定义设备「{name}」未填写 IP/地址")
        if len(name) > 120 or len(ip_address) > 120 or len(note) > 500 or len(vendor) > 100 or len(custom_command) > 200:
            raise ValueError("自定义设备的名称/IP/厂商/命令/备注长度超出限制")
        if len(device_type) > 50:
            raise ValueError("自定义设备类型过长")
        result.append(
            {
                "name": name,
                "ip_address": ip_address,
                "device_type": device_type,
                "vendor": vendor,
                "custom_command": custom_command,
                "note": note,
            }
        )
    return result


def run_due_tasks(now: Optional[datetime] = None) -> int:
    """执行所有到期的启用巡检任务，返回生成报告数量"""
    now = now or datetime.utcnow()
    db = SessionLocal()
    created = 0
    try:
        due = (
            db.query(InspectionTask)
            .filter(
                InspectionTask.enabled.is_(True),
                InspectionTask.next_run_at.isnot(None),
                InspectionTask.next_run_at <= now,
            )
            .order_by(InspectionTask.next_run_at.asc())
            .limit(20)
            .all()
        )
        for task in due:
            if task.last_status == "running" and task.last_run_at:
                if (now - task.last_run_at).total_seconds() < 600:
                    continue
            task.last_status = "running"
            task.last_run_at = now
            task.last_message = "巡检执行中"
            db.commit()
            try:
                report = generate_task_report(db, task, trigger="scheduled", username="scheduler")
                created += 1
                logger.info("定时巡检完成: task=%s report=%s", task.id, report.id)
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                logger.exception("定时巡检失败: task=%s", task.id)
                task = db.query(InspectionTask).filter(InspectionTask.id == task.id).first()
                if task:
                    task.last_status = "failed"
                    task.last_message = f"巡检失败：{str(exc)[:800]}"
            finally:
                if task:
                    task.last_run_at = now
                    task.next_run_at = compute_next_run(db, task, now)
                    db.commit()
    finally:
        db.close()
    return created


_scheduler_state: Dict[str, Any] = {
    "started_at": None,
    "last_tick_at": None,
    "last_generated": 0,
    "last_cleaned": 0,
    "last_cleanup_mono": 0,
    "last_error": "",
}


def scheduler_status() -> Dict[str, Any]:
    return {
        "running": bool(_scheduler_state.get("started_at")),
        "started_at": _scheduler_state.get("started_at"),
        "last_tick_at": _scheduler_state.get("last_tick_at"),
        "last_generated": int(_scheduler_state.get("last_generated") or 0),
        "last_error": _scheduler_state.get("last_error") or "",
        "interval_seconds": SCHEDULER_INTERVAL_SECONDS,
    }


async def scheduler_loop() -> None:
    """监督循环：每 60 秒检查一次到期任务；由 app.py 的 _supervised 包装并随进程取消"""
    _scheduler_state["started_at"] = datetime.utcnow().isoformat()
    try:
        await asyncio.sleep(5)
        while True:
            started = time.monotonic()
            try:
                created = await asyncio.to_thread(run_due_tasks)
                _scheduler_state["last_generated"] = created
                # 每小时最多清理一次过期报告（0 天表示永久保留）
                now_mono = time.monotonic()
                if now_mono - float(_scheduler_state.get("last_cleanup_mono") or 0) >= 3600:
                    cleanup_db = SessionLocal()
                    try:
                        _scheduler_state["last_cleaned"] = cleanup_expired_reports(cleanup_db)
                    finally:
                        cleanup_db.close()
                    _scheduler_state["last_cleanup_mono"] = now_mono
                _scheduler_state["last_error"] = ""
            except asyncio.CancelledError:  # pragma: no cover - 进程关闭
                raise
            except Exception as exc:  # noqa: BLE001
                _scheduler_state["last_error"] = str(exc)[:500]
                logger.exception("设备巡检调度异常")
            finally:
                _scheduler_state["last_tick_at"] = datetime.utcnow().isoformat()
            elapsed = time.monotonic() - started
            await asyncio.sleep(max(1.0, SCHEDULER_INTERVAL_SECONDS - elapsed))
    finally:
        _scheduler_state["started_at"] = None


def render_docx_preview(path: Path) -> str:
    """将 Word 报告转换为安全的在线预览 HTML（保留告警字体颜色）。"""
    _require_docx()
    import html as html_module
    from docx import Document

    document = Document(str(path))

    def run_html(run) -> str:
        text = html_module.escape(run.text or "")
        if not text:
            return ""
        try:
            color = run.font.color.rgb
            if color is not None:
                return f'<span style="color:#{color}">{text}</span>'
        except Exception:  # noqa: BLE001
            pass
        return text

    parts: List[str] = []
    for paragraph in document.paragraphs:
        text = (paragraph.text or "").strip()
        if not text:
            continue
        style = (paragraph.style.name if paragraph.style else "") or ""
        tag = "h3" if "Heading" in style else "p"
        inner = "".join(run_html(run) for run in paragraph.runs) or html_module.escape(text)
        parts.append(f"<{tag}>{inner}</{tag}>")
    for table in document.tables:
        rows = []
        for row in table.rows:
            cells = []
            for cell in row.cells:
                inner = "".join(run_html(run) for paragraph in cell.paragraphs for run in paragraph.runs)
                cells.append(f"<td>{inner or html_module.escape((cell.text or '').strip())}</td>")
            rows.append(f"<tr>{''.join(cells)}</tr>")
        if rows:
            parts.append("<table>" + "".join(rows) + "</table>")
    return "\n".join(parts) or "<p>报告没有可预览的文本内容。</p>"

    document = Document(str(path))
    parts: List[str] = []
    for paragraph in document.paragraphs:
        text = (paragraph.text or "").strip()
        if not text:
            continue
        style = (paragraph.style.name if paragraph.style else "") or ""
        tag = "h3" if "Heading" in style else "p"
        parts.append(f"<{tag}>{html_module.escape(text)}</{tag}>")
    for table in document.tables:
        rows = []
        for row in table.rows:
            cells = "".join(
                f"<td>{html_module.escape((cell.text or '').strip())}</td>"
                for cell in row.cells
            )
            rows.append(f"<tr>{cells}</tr>")
        if rows:
            parts.append("<table>" + "".join(rows) + "</table>")
    return "\n".join(parts) or "<p>报告没有可预览的文本内容。</p>"
