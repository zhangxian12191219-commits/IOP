"""虚拟机告警规则与事件评估。"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models.settings import SystemSetting
from ..models.virtualization import (
    VirtualHost,
    VirtualMachine,
    VirtualPlatform,
    VirtualizationAlert,
)
from .alert_recovery import build_generic_recovery_payload
from . import settings as settings_service

logger = logging.getLogger(__name__)

ALERT_TYPE_TEXT = {
    "vm_cpu": "CPU 使用率",
    "vm_memory": "内存使用率",
    "vm_disk": "磁盘使用率",
    "vm_shutdown": "虚拟机已关机",
    "platform_unreachable": "平台连接失败",
    "platform_auth_failed": "平台认证失败",
    "platform_sync_failed": "平台同步失败",
    "platform_sync_stale": "平台同步超时",
    "platform_storage": "平台存储使用率",
    "platform_ceph_health": "Ceph 集群健康",
    "platform_ceph_osd": "Ceph OSD 状态",
    "platform_ceph_pg": "Ceph PG 状态",
    "platform_ceph_mon": "Ceph MON 仲裁",
    "platform_ceph_device": "Ceph 磁盘/设备健康",
    "platform_storage_health": "平台存储状态",
    "platform_storage_usage": "平台存储容量",
}

PLATFORM_ALERT_TYPES = {
    "platform_unreachable", "platform_auth_failed",
    "platform_sync_failed", "platform_sync_stale", "platform_storage",
    "platform_ceph_health", "platform_ceph_osd", "platform_ceph_pg",
    "platform_ceph_mon", "platform_ceph_device",
    "platform_storage_health", "platform_storage_usage",
}

DEFAULT_PLATFORM_STORAGE_THRESHOLD = 85
AUTH_ERROR_TOKENS = (
    "401", "403", "unauthorized", "forbidden", "authentication", "auth failed",
    "invalidlogin", "invalid login", "cannot complete login",
    "incorrect user name or password", "login failed", "login denied",
    "credential", "permission denied", "access denied", "token",
    "认证", "登录", "用户名或密码", "密码错误", "凭证", "鉴权", "权限不足",
)

ALERT_LEVELS = ("info", "warning", "critical", "emergency")
ALERT_LEVEL_TEXT = {
    "info": "提示",
    "warning": "警告",
    "critical": "严重",
    "emergency": "紧急",
}
RULE_KEYS = (
    "vm_alert_cpu_enabled", "vm_alert_cpu_threshold",
    "vm_alert_memory_enabled", "vm_alert_memory_threshold",
    "vm_alert_disk_enabled", "vm_alert_disk_threshold",
    "vm_alert_shutdown_enabled",
    "vm_alert_platform_enabled", "vm_alert_storage_enabled",
    "vm_alert_storage_threshold",
)


def _raw_setting(db: Session, key: str) -> Optional[str]:
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if row is None or row.value is None:
        return None
    return row.value


def _setting_bool(db: Session, key: str, default: bool) -> bool:
    raw = _raw_setting(db, key)
    if raw is None:
        return default
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def _setting_int(db: Session, key: str, default: int) -> int:
    raw = _raw_setting(db, key)
    try:
        return int(raw) if raw is not None else default
    except (TypeError, ValueError):
        return default


def get_rules(db: Session) -> Dict[str, Any]:
    values = settings_service.get_all(db)
    storage_threshold = _setting_int(
        db, "vm_alert_storage_threshold", DEFAULT_PLATFORM_STORAGE_THRESHOLD
    )
    return {
        "cpu_enabled": bool(values.get("vm_alert_cpu_enabled", True)),
        "cpu_threshold": int(values.get("vm_alert_cpu_threshold") or 80),
        "memory_enabled": bool(values.get("vm_alert_memory_enabled", True)),
        "memory_threshold": int(values.get("vm_alert_memory_threshold") or 85),
        "disk_enabled": bool(values.get("vm_alert_disk_enabled", True)),
        "disk_threshold": int(values.get("vm_alert_disk_threshold") or 85),
        "shutdown_enabled": bool(values.get("vm_alert_shutdown_enabled", True)),
        "platform_enabled": _setting_bool(db, "vm_alert_platform_enabled", True),
        "storage_enabled": _setting_bool(db, "vm_alert_storage_enabled", True),
        "storage_threshold": max(1, min(100, storage_threshold)),
    }


def save_rules(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
    values = {
        "vm_alert_cpu_enabled": bool(payload.get("cpu_enabled", True)),
        "vm_alert_cpu_threshold": int(payload.get("cpu_threshold") or 80),
        "vm_alert_memory_enabled": bool(payload.get("memory_enabled", True)),
        "vm_alert_memory_threshold": int(payload.get("memory_threshold") or 85),
        "vm_alert_disk_enabled": bool(payload.get("disk_enabled", True)),
        "vm_alert_disk_threshold": int(payload.get("disk_threshold") or 85),
        "vm_alert_shutdown_enabled": bool(payload.get("shutdown_enabled", True)),
        "vm_alert_platform_enabled": bool(payload.get("platform_enabled", True)),
        "vm_alert_storage_enabled": bool(payload.get("storage_enabled", True)),
        "vm_alert_storage_threshold": max(
            1, min(100, int(payload.get("storage_threshold") or DEFAULT_PLATFORM_STORAGE_THRESHOLD))
        ),
    }
    settings_service.save(db, values)
    return get_rules(db)


def alert_to_dict(alert: VirtualizationAlert) -> Dict[str, Any]:
    level = alert.alert_level or "warning"
    return {
        "id": alert.id,
        "platform_id": alert.platform_id,
        "platform_name": alert.platform_name or "",
        "vm_id": alert.vm_id,
        "vm_name": alert.vm_name or "",
        "target_type": "platform" if alert.vm_id is None else "vm",
        "target_name": alert.vm_name or alert.platform_name or "虚拟化对象",
        "alert_type": alert.alert_type,
        "alert_type_text": ALERT_TYPE_TEXT.get(alert.alert_type, alert.alert_type),
        "alert_level": level,
        "alert_level_text": ALERT_LEVEL_TEXT.get(level, level),
        # 历史数据 NULL 视为开启，保持升级前的通知行为
        "send_notification": alert.send_notification is not False,
        "message": alert.message,
        "value": alert.value,
        "threshold": alert.threshold,
        "is_acknowledged": bool(alert.is_acknowledged),
        "is_hidden": bool(getattr(alert, "is_hidden", False)),
        "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
        "resolution": alert.resolution,
        "is_resolved": bool(alert.resolved_at),
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
        "updated_at": alert.updated_at.isoformat() if alert.updated_at else None,
    }


def normalize_alert_level(level: Optional[str]) -> Optional[str]:
    """校验告警级别；None/空串表示保持原级别。"""
    if level is None:
        return None
    text = str(level).strip().lower()
    if not text:
        return None
    if text not in ALERT_LEVELS:
        raise ValueError(f"告警级别仅支持 {', '.join(ALERT_LEVELS)}")
    return text


def _apply_alert_settings(
    alert: VirtualizationAlert,
    alert_level: Optional[str] = None,
    send_notification: Optional[bool] = None,
) -> bool:
    """把用户选择写回告警对象，返回是否有变化。"""
    changed = False
    level = normalize_alert_level(alert_level)
    if level is not None and (alert.alert_level or "warning") != level:
        alert.alert_level = level
        changed = True
    if send_notification is not None:
        current = alert.send_notification is not False
        wanted = bool(send_notification)
        if current != wanted:
            alert.send_notification = wanted
            changed = True
    return changed


def _alert_notification_payload(alert: VirtualizationAlert) -> Dict[str, Any]:
    platform_name = alert.platform_name or ""
    if alert.vm_id is None:
        display_name = f"虚拟化平台 {platform_name or '未知平台'}"
    else:
        display_name = f"虚拟机 {alert.vm_name or '未知虚拟机'}" + (f"（{platform_name}）" if platform_name else "")
    return {
        "source": "virtualization",
        "source_id": alert.id,
        "level": alert.alert_level or "warning",
        "device_name": display_name,
        "alert_type": ALERT_TYPE_TEXT.get(alert.alert_type, alert.alert_type),
        "message": alert.message,
        "value": alert.value,
        "threshold": alert.threshold,
        "created_at": alert.created_at.isoformat(timespec="seconds") if alert.created_at else None,
    }


def dispatch_alert_notification(alert: Optional[VirtualizationAlert]) -> bool:
    """按 send_notification 开关把新产生的虚拟机告警发送到告警渠道。

    渠道最低级别过滤由 backend.notify.dispatcher 统一处理（level_allows），
    没有配置渠道时 dispatch 会快速返回，不影响告警评估主流程。
    """
    if alert is None or alert.resolved_at is not None:
        return False
    if alert.send_notification is False:
        return False
    try:
        # 延迟导入，避免与 models.database 的模型注册产生循环导入
        from ..notify import notify_alert_sync

        notify_alert_sync(_alert_notification_payload(alert))
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("虚拟机告警通知发送失败（告警 %s）: %s", alert.id, exc)
        return False


def acknowledge_alert(
    db: Session,
    alert: VirtualizationAlert,
    alert_level: Optional[str] = None,
    send_notification: Optional[bool] = None,
) -> bool:
    """确认单条告警，可同时更新级别与通知开关。"""
    notification_was_enabled = alert.send_notification is not False
    changed = _apply_alert_settings(alert, alert_level, send_notification)
    if not alert.is_acknowledged:
        alert.is_acknowledged = True
        alert.acknowledged_at = datetime.utcnow()
        changed = True
    if changed:
        alert.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(alert)
        # 用户显式把通知开关从“关闭”改为“开启”时，立即补发一次
        if alert.send_notification is not False and not notification_was_enabled:
            dispatch_alert_notification(alert)
    return changed


def update_alert(
    db: Session,
    alert: VirtualizationAlert,
    alert_level: Optional[str] = None,
    send_notification: Optional[bool] = None,
) -> bool:
    """更新告警级别/通知开关（不改变确认状态）。"""
    notification_was_enabled = alert.send_notification is not False
    changed = _apply_alert_settings(alert, alert_level, send_notification)
    if changed:
        alert.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(alert)
        # 显式重新开启通知时补发一次；已成功发送过的渠道由 dispatcher 去重
        if alert.send_notification is not False and not notification_was_enabled:
            dispatch_alert_notification(alert)
    return changed


def bulk_acknowledge(
    db: Session,
    alerts: List[VirtualizationAlert],
    alert_level: Optional[str] = None,
    send_notification: Optional[bool] = None,
) -> Dict[str, int]:
    """批量确认告警，可同时统一设置级别与通知开关。

    返回 updated（实际被修改的告警数）与 acknowledged（本次新确认的告警数）。
    """
    level = normalize_alert_level(alert_level)
    now = datetime.utcnow()
    updated = 0
    acknowledged = 0
    to_notify: List[VirtualizationAlert] = []
    for alert in alerts:
        notification_was_enabled = alert.send_notification is not False
        changed = False
        if not alert.is_acknowledged:
            alert.is_acknowledged = True
            alert.acknowledged_at = now
            acknowledged += 1
            changed = True
        # 批量确认与单条确认语义不同：批量确认后从活动列表隐藏。
        if not getattr(alert, "is_hidden", False):
            alert.is_hidden = True
            changed = True
        if level is not None and (alert.alert_level or "warning") != level:
            alert.alert_level = level
            changed = True
        if send_notification is not None:
            current = alert.send_notification is not False
            if current != bool(send_notification):
                alert.send_notification = bool(send_notification)
                changed = True
        if changed:
            alert.updated_at = now
            updated += 1
        if alert.send_notification is not False and not notification_was_enabled:
            to_notify.append(alert)
    if updated:
        db.commit()
    if to_notify:
        for alert in to_notify:
            dispatch_alert_notification(alert)
    return {"updated": updated, "acknowledged": acknowledged}


def _rule_specs(vm: VirtualMachine, rules: Dict[str, Any], platform_type: str = "") -> List[Tuple[str, str, Optional[float], Optional[float], str]]:
    specs: List[Tuple[str, str, Optional[float], Optional[float], str]] = []
    if rules["cpu_enabled"] and vm.cpu_usage is not None and float(vm.cpu_usage) > rules["cpu_threshold"]:
        specs.append(("vm_cpu", "warning", float(vm.cpu_usage), float(rules["cpu_threshold"]),
                      f"虚拟机 CPU 使用率 {float(vm.cpu_usage):.1f}% 超过阈值 {rules['cpu_threshold']}%"))
    if rules["memory_enabled"] and vm.memory_usage is not None and float(vm.memory_usage) > rules["memory_threshold"]:
        specs.append(("vm_memory", "warning", float(vm.memory_usage), float(rules["memory_threshold"]),
                      f"虚拟机内存使用率 {float(vm.memory_usage):.1f}% 超过阈值 {rules['memory_threshold']}%"))
    if rules["disk_enabled"] and vm.disk_usage is not None and float(vm.disk_usage) > rules["disk_threshold"]:
        specs.append(("vm_disk", "warning", float(vm.disk_usage), float(rules["disk_threshold"]),
                      f"虚拟机磁盘使用率 {float(vm.disk_usage):.1f}% 超过阈值 {rules['disk_threshold']}%"))
    if (
        rules["shutdown_enabled"]
        and platform_type not in ("docker", "kubernetes")
        and (vm.power_state or "").lower() == "stopped"
    ):
        specs.append(("vm_shutdown", "critical", None, None, "虚拟机已关机（Powered Off / Shutoff）"))
    return specs


def _platform_storage_spec(
    db: Session, platform: VirtualPlatform, threshold: int
) -> Optional[Dict[str, Any]]:
    """汇总平台下宿主机的存储使用率，超过阈值时生成平台存储告警。

    优先按容量加权计算（已用容量 / 总容量），宿主机未提供容量时回退为
    各宿主机 storage_usage 的算术平均；日志中同时给出使用率最高的宿主机，
    便于定位具体节点。
    """
    if not platform.enabled:
        return None
    hosts = (
        db.query(VirtualHost)
        .filter(VirtualHost.platform_id == platform.id)
        .all()
    )
    if not hosts:
        return None
    total_gb = 0.0
    used_gb = 0.0
    weighted = False
    percentages: List[float] = []
    max_host: Optional[Tuple[str, float]] = None
    for host in hosts:
        try:
            if host.storage_usage is not None:
                usage = float(host.storage_usage)
                percentages.append(usage)
                if max_host is None or usage > max_host[1]:
                    max_host = (host.name or host.ip_address or "宿主机", usage)
        except (TypeError, ValueError):
            pass
        try:
            total = float(host.storage_total_gb or 0)
            used = float(host.storage_used_gb or 0)
            if total > 0 and host.storage_used_gb is not None:
                total_gb += total
                used_gb += used
                weighted = True
        except (TypeError, ValueError):
            continue
    if weighted and total_gb > 0:
        usage_value = used_gb / total_gb * 100
    elif percentages:
        usage_value = sum(percentages) / len(percentages)
    else:
        return None
    usage_value = round(usage_value, 2)
    if usage_value <= threshold:
        return None
    message = (
        f"虚拟化平台 {platform.name} 宿主机存储汇总使用率 {usage_value:.1f}% "
        f"超过阈值 {threshold}%（{len(hosts)} 台宿主机）"
    )
    if max_host and max_host[1] > usage_value:
        message += f"，最高 {max_host[0]} 为 {max_host[1]:.1f}%"
    return {
        "alert_type": "platform_storage",
        "alert_level": "warning",
        "message": message,
        "value": usage_value,
        "threshold": float(threshold),
    }


def _storage_alert_specs(platform: VirtualPlatform, rules: Dict[str, Any]) -> List[Dict[str, Any]]:
    """平台接入存储（iSCSI/FC-LVM/NFS/RBD/CephFS 等）状态与容量告警。"""
    if not rules.get("storage_enabled", True):
        return []
    health = (platform.last_health or {}).get("storage") if isinstance(platform.last_health, dict) else None
    if not isinstance(health, dict) or not health.get("available"):
        return []
    items = health.get("items") if isinstance(health.get("items"), list) else []
    threshold = float(rules.get("storage_threshold") or 85)
    specs: List[Dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "未命名存储")
        storage_type = str(item.get("type") or "unknown")
        type_text = {
            "iscsi": "iSCSI", "lvm": "LVM/FC", "lvmthin": "LVM-Thin/FC",
            "nfs": "NFS", "rbd": "Ceph RBD", "cephfs": "CephFS",
            "dir": "目录存储", "zfspool": "ZFS", "pbs": "Proxmox Backup",
        }.get(storage_type, storage_type)
        if str(item.get("status") or "").lower() not in ("available", "active", "ok"):
            specs.append({
                "alert_type": "platform_storage_health",
                "alert_level": "critical",
                "message": f"虚拟化平台 {platform.name} 存储「{name}」（{type_text}）状态为 {item.get('status') or '异常'}"
                           + (f"，节点：{', '.join(item.get('nodes') or [])}" if item.get("nodes") else ""),
                "value": None,
                "threshold": None,
            })
        usage = item.get("usage")
        try:
            usage = float(usage) if usage is not None else None
        except (TypeError, ValueError):
            usage = None
        if usage is not None and usage > threshold:
            specs.append({
                "alert_type": "platform_storage_usage",
                "alert_level": "warning",
                "message": f"虚拟化平台 {platform.name} 存储「{name}」（{type_text}）使用率 {usage:.1f}% 超过阈值 {threshold:g}%",
                "value": usage,
                "threshold": threshold,
            })
    return specs


def _ceph_alert_specs(platform: VirtualPlatform) -> List[Dict[str, Any]]:
    """把 PVE Ceph 健康快照转换为平台告警规格。"""
    health = (platform.last_health or {}).get("ceph") if isinstance(platform.last_health, dict) else None
    if not isinstance(health, dict) or not health.get("available"):
        return []
    specs: List[Dict[str, Any]] = []
    status = str(health.get("status") or "UNKNOWN").upper()
    checks = health.get("checks") if isinstance(health.get("checks"), list) else []
    active_checks = [item for item in checks if isinstance(item, dict) and not item.get("muted")]
    down_osds = health.get("down_osds") if isinstance(health.get("down_osds"), list) else []
    osd_down = int(health.get("osd_down") or 0)
    osd_out = int(health.get("osd_out") or 0)
    pg_degraded = int(health.get("pg_degraded") or 0)
    mon_total = int(health.get("mon_total") or 0)
    quorum_count = int(health.get("quorum_count") or 0)
    spurious = health.get("spurious_read_errors") if isinstance(health.get("spurious_read_errors"), list) else []
    crashes = health.get("recent_crash") if isinstance(health.get("recent_crash"), list) else []

    if status in ("HEALTH_ERR", "HEALTH_WARN"):
        level = "critical" if status == "HEALTH_ERR" else "warning"
        summaries = [str(item.get("summary") or item.get("name") or "") for item in active_checks]
        summaries = [value for value in summaries if value]
        message = f"虚拟化平台 {platform.name} Ceph 健康状态为 {status}"
        if summaries:
            message += "：" + "；".join(summaries[:4])
        specs.append({
            "alert_type": "platform_ceph_health",
            "alert_level": level,
            "message": message[:1200],
            "value": None,
            "threshold": None,
        })

    if osd_down or osd_out:
        names = []
        for item in down_osds[:8]:
            if isinstance(item, dict):
                label = item.get("name") or f"osd.{item.get('id')}"
                host = item.get("host") or ""
                names.append(f"{label}{'@' + host if host else ''}")
        detail = "、".join(names) if names else f"{osd_down} 个 down，{osd_out} 个 out"
        specs.append({
            "alert_type": "platform_ceph_osd",
            "alert_level": "critical",
            "message": f"虚拟化平台 {platform.name} Ceph OSD 异常：{detail}（共 {health.get('osd_total') or '-'} 个 OSD）",
            "value": float(max(osd_down, osd_out)),
            "threshold": 0.0,
        })

    if pg_degraded > 0:
        specs.append({
            "alert_type": "platform_ceph_pg",
            "alert_level": "critical" if status == "HEALTH_ERR" else "warning",
            "message": f"虚拟化平台 {platform.name} Ceph 有 {pg_degraded} 个 PG 非 active+clean（共 {health.get('pg_total') or '-'} 个）",
            "value": float(pg_degraded),
            "threshold": 0.0,
        })

    if mon_total and quorum_count < mon_total:
        specs.append({
            "alert_type": "platform_ceph_mon",
            "alert_level": "critical",
            "message": f"虚拟化平台 {platform.name} Ceph MON 仲裁不足：{quorum_count}/{mon_total} 个 MON 在 quorum",
            "value": float(quorum_count),
            "threshold": float(mon_total),
        })

    if spurious or crashes:
        parts = []
        if spurious:
            parts.append("磁盘读错误：" + "；".join(str(item) for item in spurious[:3]))
        if crashes:
            parts.append("近期 daemon crash：" + "；".join(str(item) for item in crashes[:3]))
        specs.append({
            "alert_type": "platform_ceph_device",
            "alert_level": "warning",
            "message": f"虚拟化平台 {platform.name} Ceph 设备异常：" + "；".join(parts),
            "value": float(len(spurious) + len(crashes)),
            "threshold": 0.0,
        })
    return specs


def _platform_alert_spec(platform: VirtualPlatform, now: datetime) -> Optional[Dict[str, Any]]:
    """根据平台最近同步状态生成平台级告警。"""
    if not platform.enabled:
        return None
    status = (platform.last_sync_status or "").lower()
    error = (platform.last_error or "").strip()
    lowered = error.lower()
    if status == "failed":
        detail = error[:240] or "未知错误"
        if any(token in lowered for token in AUTH_ERROR_TOKENS):
            alert_type, level = "platform_auth_failed", "critical"
            message = f"虚拟化平台 {platform.name} 认证/登录失败，请检查账号、密码或 Token：{detail}"
        elif any(token in lowered for token in ("ssl", "certificate", "证书", "tls")):
            alert_type, level = "platform_unreachable", "critical"
            message = f"虚拟化平台 {platform.name} TLS/证书校验失败：{detail}"
        elif any(token in lowered for token in ("timeout", "timed out", "unreachable", "refused", "connect", "连接", "超时", "不可达")):
            alert_type, level = "platform_unreachable", "critical"
            message = f"虚拟化平台 {platform.name} 无法连接（{platform.address}:{platform.port}）：{detail}"
        else:
            alert_type, level = "platform_sync_failed", "warning"
            message = f"虚拟化平台 {platform.name} 同步失败：{detail}"
        return {
            "alert_type": alert_type,
            "alert_level": level,
            "message": message,
            "value": None,
            "threshold": None,
        }
    # 从未成功同步时不制造告警；已有成功记录后超过 3 个同步周期视为同步超时
    if platform.last_sync_at is not None and status == "success":
        interval = max(1, int(platform.sync_interval_minutes or 5))
        if now - platform.last_sync_at > timedelta(minutes=max(10, interval * 3)):
            return {
                "alert_type": "platform_sync_stale",
                "alert_level": "warning",
                "message": f"虚拟化平台 {platform.name} 已超过 {max(10, interval * 3)} 分钟未成功同步",
                "value": None,
                "threshold": None,
            }
    return None


def evaluate_platform(db: Session, platform_id: int, now: Optional[datetime] = None) -> Dict[str, int]:
    """重新评估一个平台所有虚拟机的告警，自动创建/更新/恢复。"""
    now = now or datetime.utcnow()
    platform = db.query(VirtualPlatform).filter(VirtualPlatform.id == platform_id).first()
    if not platform:
        return {"created": 0, "resolved": 0, "active": 0}
    rules = get_rules(db)
    vms = db.query(VirtualMachine).filter(VirtualMachine.platform_id == platform_id).all()
    wanted: Dict[Tuple[int, str], Dict[str, Any]] = {}
    for vm in vms:
        for alert_type, level, value, threshold, message in _rule_specs(vm, rules, platform.platform_type or ""):
            wanted[(vm.id, alert_type)] = {
                "platform_id": platform.id,
                "vm_id": vm.id,
                "vm_name": vm.name,
                "platform_name": platform.name,
                "alert_type": alert_type,
                "alert_level": level,
                "message": message,
                "value": value,
                "threshold": threshold,
            }

    platform_specs: List[Dict[str, Any]] = []
    if rules.get("platform_enabled", True):
        platform_spec = _platform_alert_spec(platform, now)
        if platform_spec:
            platform_specs.append(platform_spec)
        platform_specs.extend(_ceph_alert_specs(platform))
        platform_specs.extend(_storage_alert_specs(platform, rules))
    if rules.get("storage_enabled", True):
        storage_spec = _platform_storage_spec(
            db, platform, int(rules.get("storage_threshold") or DEFAULT_PLATFORM_STORAGE_THRESHOLD)
        )
        if storage_spec:
            platform_specs.append(storage_spec)
    for platform_spec in platform_specs:
        wanted[(None, platform_spec["alert_type"])] = {
            "platform_id": platform.id,
            "vm_id": None,
            "vm_name": "",
            "platform_name": platform.name,
            **{key: platform_spec[key] for key in ("alert_type", "alert_level", "message", "value", "threshold")},
        }

    active = (
        db.query(VirtualizationAlert)
        .filter(
            VirtualizationAlert.platform_id == platform_id,
            VirtualizationAlert.resolved_at.is_(None),
        )
        .all()
    )
    by_key = {(alert.vm_id, alert.alert_type): alert for alert in active}
    dismissed = (
        db.query(VirtualizationAlert)
        .filter(
            VirtualizationAlert.platform_id == platform_id,
            VirtualizationAlert.resolution == "manual_deleted",
        )
        .all()
    )
    dismissed_keys = {(alert.vm_id, alert.alert_type) for alert in dismissed}
    dismissed_cleared = 0
    for alert in dismissed:
        if (alert.vm_id, alert.alert_type) not in wanted:
            alert.resolution = "manual_deleted_cleared"
            dismissed_cleared += 1
    created = 0
    updated = 0
    new_alerts: List[VirtualizationAlert] = []
    for key, data in wanted.items():
        if key in dismissed_keys:
            continue
        alert = by_key.get(key)
        if alert is None:
            alert = VirtualizationAlert(
                **data,
                is_acknowledged=False,
                created_at=now,
                updated_at=now,
            )
            db.add(alert)
            new_alerts.append(alert)
            created += 1
            continue
        changed = False
        # 不覆盖 alert_level：保留用户在页面手动调整过的告警级别
        for field in ("vm_name", "platform_name", "message", "value", "threshold"):
            value = data.get(field)
            if getattr(alert, field) != value:
                setattr(alert, field, value)
                changed = True
        if changed:
            alert.updated_at = now
            updated += 1

    resolved = 0
    resolved_alerts: List[VirtualizationAlert] = []
    for key, alert in by_key.items():
        if key in wanted:
            continue
        alert.resolved_at = now
        alert.resolution = "auto_recovered"
        alert.is_acknowledged = True
        alert.updated_at = now
        resolved_alerts.append(alert)
        resolved += 1

    if created or updated or resolved or dismissed_cleared:
        db.commit()
    # 新产生的告警按 send_notification 开关分发到告警渠道
    for alert in new_alerts:
        try:
            dispatch_alert_notification(alert)
        except Exception as exc:  # noqa: BLE001
            logger.warning("虚拟机告警通知分发异常（告警 %s）: %s", alert.id, exc)
    # 条件消失的告警发送恢复通知；source_id 为负值，避免与原告警去重
    for alert in resolved_alerts:
        if alert.send_notification is False:
            continue
        try:
            name = alert.vm_name or alert.platform_name or f"虚拟化告警#{alert.id}"
            notify_alert_sync(build_generic_recovery_payload(
                source="virtualization",
                alert_id=alert.id,
                name=name,
                alert_type=alert.alert_type,
                message=alert.message,
                level=alert.alert_level,
                value=alert.value,
                threshold=alert.threshold,
                recovered_at=alert.resolved_at,
                original_created_at=alert.created_at,
            ))
        except Exception as exc:  # noqa: BLE001
            logger.warning("虚拟机告警恢复通知分发异常（告警 %s）: %s", alert.id, exc)
    active_count = (
        db.query(VirtualizationAlert)
        .filter(
            VirtualizationAlert.platform_id == platform_id,
            VirtualizationAlert.resolved_at.is_(None),
        )
        .count()
    )
    return {"created": created, "resolved": resolved, "active": active_count}


def evaluate_all(db: Session) -> Dict[str, int]:
    platforms = db.query(VirtualPlatform).all()
    created = resolved = active = 0
    for platform in platforms:
        try:
            result = evaluate_platform(db, platform.id)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.warning("评估虚拟机告警失败 %s: %s", platform.name, exc)
            continue
        created += result["created"]
        resolved += result["resolved"]
        active += result["active"]
    return {"created": created, "resolved": resolved, "active": active}


def counts(db: Session, target_type: Optional[str] = None) -> Dict[str, int]:
    def _scope(query):
        if target_type == "platform":
            return query.filter(VirtualizationAlert.vm_id.is_(None))
        if target_type == "vm":
            return query.filter(VirtualizationAlert.vm_id.is_not(None))
        return query

    active = _scope(
        db.query(VirtualizationAlert).filter(
            VirtualizationAlert.resolved_at.is_(None),
            VirtualizationAlert.is_hidden.isnot(True),
        )
    ).count()
    unack = _scope(
        db.query(VirtualizationAlert).filter(
            VirtualizationAlert.resolved_at.is_(None),
            VirtualizationAlert.is_hidden.isnot(True),
            VirtualizationAlert.is_acknowledged == False,  # noqa: E712
        )
    ).count()
    history = _scope(
        db.query(VirtualizationAlert).filter(
            VirtualizationAlert.resolved_at.is_not(None),
            VirtualizationAlert.is_hidden.isnot(True),
        )
    ).count()
    return {"active": active, "unacknowledged": unack, "history": history}
