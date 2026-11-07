"""AI 智能运维：只读统计、告警分析、外部模型对话和报告生成。

安全边界：
- 只读取资产、MIB、告警、虚拟化、巡检等统计；
- 不提供授权、用户、系统服务、系统配置、更新等写操作工具；
- AI 不能修改任何系统数据，唯一写入是本模块自己的报告记录。
"""
from __future__ import annotations

import json
import logging
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from ..config import PROJECT_ROOT
from ..models.ai_report import AiOpsReport
from ..models.certificate import ManagedCertificate
from ..models.config_backup import ConfigBackup
from ..models.inspection import InspectionReport, InspectionTask
from ..models.mib import MibFile, MibObject
from ..models.models import Alert, Device, DeviceConnection, DeviceCredential, DeviceMetric
from ..models.room import Cabinet, Room
from ..models.website import WebsiteAlert, WebsiteTarget
from ..models.virtualization import VirtualHost, VirtualMachine, VirtualPlatform, VirtualizationAlert
from . import settings as settings_service
from .virtualization_crypto import decrypt_password, encrypt_password

logger = logging.getLogger(__name__)
REPORT_DIR = Path(PROJECT_ROOT) / "data" / "ai_reports"
ALERT_LEVEL_LABELS = {"info": "提示", "warning": "警告", "critical": "严重", "emergency": "紧急"}
ALERT_TYPE_TEXT = {
    "cpu": "CPU 使用率", "memory": "内存使用率", "temperature": "温度",
    "power": "电源状态", "offline": "设备离线", "down": "探测失败",
    "slow": "响应缓慢", "ssl_expired": "证书过期", "warranty": "维保到期",
    "vm_cpu": "虚拟机 CPU", "vm_memory": "虚拟机内存",
    "vm_disk": "虚拟机磁盘", "vm_shutdown": "虚拟机关机",
    "platform_unreachable": "平台连接失败", "platform_auth_failed": "平台认证失败",
    "platform_sync_failed": "平台同步失败", "platform_sync_stale": "平台同步超时",
    "platform_storage": "平台存储", "platform_storage_health": "平台存储状态",
    "platform_storage_usage": "平台存储容量", "platform_ceph_health": "Ceph 集群健康",
    "platform_ceph_osd": "Ceph OSD 状态", "platform_ceph_pg": "Ceph PG 状态",
    "platform_ceph_mon": "Ceph MON 仲裁", "platform_ceph_device": "Ceph 设备健康",
}
CAUSE_TEXT = {
    "cpu": "业务流量突增、进程异常或设备性能不足",
    "memory": "业务负载升高、内存泄漏或分配不足",
    "temperature": "风扇/散热异常、机房温度过高或设备负载过高",
    "power": "电源模块故障、供电异常或电源冗余不足",
    "offline": "链路中断、设备断电、SNMP 配置变化或设备不可达",
    "down": "网站/端口探测失败、服务停止或网络不可达",
    "slow": "服务响应变慢、后端资源不足或网络延迟升高",
    "ssl_expired": "HTTPS 证书已过期或即将过期",
    "warranty": "设备维保/质保即将到期或已到期",
    "vm_cpu": "虚拟机业务负载升高或 vCPU 分配不足",
    "vm_memory": "虚拟机内存压力过大或内存分配不足",
    "vm_disk": "虚拟磁盘空间不足或磁盘 I/O 压力",
    "vm_shutdown": "虚拟机被关机、系统崩溃或平台任务异常",
}
SUGGESTION_TEXT = {
    "cpu": "检查高 CPU 进程和近期业务变化，必要时扩容或限流",
    "memory": "检查内存占用趋势和进程，确认是否存在泄漏并扩容",
    "temperature": "检查风扇、进排风和机房空调，清理灰尘并降低负载",
    "power": "检查电源模块和供电线路，确认冗余电源状态",
    "offline": "先检查网络链路和设备电源，再核对 SNMP 地址、Community 和 ACL",
    "down": "检查目标服务、端口、证书和网络链路，确认业务进程状态",
    "slow": "检查服务响应、后端资源和网络延迟，定位瓶颈",
    "ssl_expired": "更新或续签 HTTPS 证书，并检查自动续期任务",
    "warranty": "核对设备维保合同和到期时间，及时续保并更新维保信息",
    "vm_cpu": "检查虚拟机内进程和 CPU 就绪时间，评估 vCPU 扩容",
    "vm_memory": "检查内存使用和气球驱动/交换，评估内存扩容",
    "vm_disk": "清理磁盘或扩容虚拟磁盘，检查存储性能",
    "vm_shutdown": "确认是否为计划关机；检查平台任务和 Guest OS 日志",
}
FUNCTION_LIST = [
    "仪表盘与监控总览", "大屏展示", "资产管理与 SNMP 采集", "设备巡检",
    "设备配置备份", "自动发现", "即时通信", "系统工具", "MIB 管理",
    "机房与 3D 数字孪生", "网络拓扑", "虚拟化管理（VMware/CAS/KVM/Docker/Kubernetes）",
    "网站与证书监控", "告警中心", "告警渠道", "审计日志", "系统配置与授权信息",
]

DEVICE_TYPE_LABELS = {
    "router": "路由器", "switch": "交换机", "firewall": "防火墙",
    "security": "安全设备", "server": "服务器", "other": "其他",
}

# ==================== 多轮会话上下文 ====================
# 进程内会话记忆：按“用户名 + 会话ID”保存最近若干轮消息，供文字与语音对话共用。
# 服务由单个 uvicorn 进程运行（run_backend.py 未开启多 worker），进程内存储足够；
# 前端同时把最近消息作为兜底传入，进程重启后仍可从客户端历史恢复上下文。
SESSION_MAX_MESSAGES = 40          # 服务端最多保留的消息条数（约 20 轮）
MODEL_HISTORY_MESSAGES = 12        # 每次实际送给模型的历史消息条数（约 6 轮）
SESSION_TTL_SECONDS = 8 * 3600     # 会话闲置过期时间
SESSION_MAX_ENTRIES = 500          # 最多保留的会话数量

_SESSION_LOCK = threading.Lock()
_SESSIONS: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()

IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")
_SESSION_ID_RE = re.compile(r"^[A-Za-z0-9_.:-]{6,80}$")
_STOP_TOKENS = {
    "the", "and", "for", "with", "show", "list", "what", "why", "how",
    "cpu", "memory", "mem", "disk", "mib", "oid", "snmp", "api", "ai", "ops",
    "alert", "alerts", "status", "device", "devices", "network", "top", "ok",
    "hello", "hi", "help", "please", "now", "current", "recent",
}
# 厂商提示词 → 可能的库内写法，用于把口语中的厂商名映射到设备字段
_VENDOR_HINTS = {
    "华为": ["huawei", "华为"], "huawei": ["huawei"],
    "思科": ["cisco", "思科"], "cisco": ["cisco"],
    "华三": ["h3c", "华三"], "新华三": ["h3c"], "h3c": ["h3c"],
    "锐捷": ["ruijie", "锐捷"], "ruijie": ["ruijie"],
    "深信服": ["sangfor", "深信服"], "sangfor": ["sangfor"],
    "天融信": ["topsec", "天融信"], "topsec": ["topsec"],
    "中兴": ["zte", "中兴"], "zte": ["zte"],
    "浪潮": ["inspur", "浪潮"], "inspur": ["inspur"],
    "戴尔": ["dell", "戴尔"], "dell": ["dell"],
    "惠普": ["hp", "hpe", "惠普"], "hpe": ["hpe"], "hp": ["hp"],
    "联想": ["lenovo", "联想"], "lenovo": ["lenovo"],
    "山石": ["hillstone", "山石"], "hillstone": ["hillstone"],
    "飞塔": ["fortinet", "飞塔"], "fortinet": ["fortinet"],
}
_DEVICE_TYPE_WORDS = {
    "路由器": "router", "交换机": "switch", "防火墙": "firewall",
    "安全设备": "security", "服务器": "server",
}


def _clean_session_id(value: Any) -> str:
    text = str(value or "").strip()
    return text if _SESSION_ID_RE.match(text) else ""


def _session_key(username: str, session_id: str) -> str:
    return f"{(username or 'anonymous').strip()[:100]}::{session_id}"


def _prune_sessions_locked(now: float) -> None:
    stale = [key for key, item in _SESSIONS.items() if now - float(item.get("updated") or 0) > SESSION_TTL_SECONDS]
    for key in stale:
        _SESSIONS.pop(key, None)
    while len(_SESSIONS) > SESSION_MAX_ENTRIES:
        _SESSIONS.popitem(last=False)


def _sanitize_history(items: Any, limit: int = SESSION_MAX_MESSAGES) -> List[Dict[str, str]]:
    """只保留 user/assistant 的文本消息，过滤超长内容和非法角色。"""
    result: List[Dict[str, str]] = []
    for item in items or []:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip().lower()
        content = item.get("content")
        if role not in ("user", "assistant") or not isinstance(content, (str, int, float)):
            continue
        content = str(content).strip()
        if not content:
            continue
        result.append({"role": role, "content": content[:4000]})
    return result[-limit:]


def get_session_history(username: str, session_id: str) -> List[Dict[str, str]]:
    if not session_id:
        return []
    key = _session_key(username, session_id)
    now = time.monotonic()
    with _SESSION_LOCK:
        _prune_sessions_locked(now)
        item = _SESSIONS.get(key)
        if not item:
            return []
        item["updated"] = now
        _SESSIONS.move_to_end(key)
        return [dict(msg) for msg in item.get("messages") or []]


def _save_session_history(username: str, session_id: str, messages: List[Dict[str, str]]) -> None:
    if not session_id:
        return
    key = _session_key(username, session_id)
    now = time.monotonic()
    with _SESSION_LOCK:
        _prune_sessions_locked(now)
        _SESSIONS[key] = {
            "messages": messages[-SESSION_MAX_MESSAGES:],
            "updated": now,
        }
        _SESSIONS.move_to_end(key)


def reset_session(username: str, session_id: str = "") -> None:
    sid = _clean_session_id(session_id)
    if not sid:
        return
    with _SESSION_LOCK:
        _SESSIONS.pop(_session_key(username, sid), None)


def _merge_histories(stored: List[Dict[str, str]], client: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """合并服务端会话记忆与前端历史：客户端是超集时用客户端，否则拼接去重。"""
    if not stored:
        return client[-SESSION_MAX_MESSAGES:]
    if not client:
        return stored[-SESSION_MAX_MESSAGES:]
    if len(client) >= len(stored) and client[-len(stored):] == stored[-len(client):]:
        return client[-SESSION_MAX_MESSAGES:]
    combined = stored + client
    merged: List[Dict[str, str]] = []
    for item in combined:
        if merged and merged[-1] == item:
            continue
        merged.append(item)
    return merged[-SESSION_MAX_MESSAGES:]



def _setting(config: Dict[str, Any], key: str, default: Any = "") -> Any:
    value = config.get(key)
    return default if value is None or value == "" else value


def get_config(db: Session) -> Dict[str, Any]:
    values = settings_service.get_all(db)
    key_enc = str(values.get("ai_api_key_enc") or "")
    key = ""
    if key_enc:
        try:
            key = decrypt_password(key_enc)
        except Exception:  # noqa: BLE001
            key = ""
    tts_key_enc = str(values.get("ai_tts_api_key_enc") or "")
    tts_key = ""
    if tts_key_enc:
        try:
            tts_key = decrypt_password(tts_key_enc)
        except Exception:  # noqa: BLE001
            tts_key = ""
    return {
        "enabled": bool(values.get("ai_enabled")),
        "base_url": str(values.get("ai_base_url") or "https://api.openai.com/v1").strip(),
        "model": str(values.get("ai_model") or "gpt-4o-mini").strip(),
        "api_key": key,
        "has_key": bool(key),
        "temperature": str(values.get("ai_temperature") or "0.2"),
        "max_tokens": int(values.get("ai_max_tokens") or 1200),
        "wake_word": str(values.get("ai_wake_word") or "你好玄武").strip() or "你好玄武",
        "name": str(values.get("ai_name") or "玄武").strip()[:20] or "玄武",
        "voice_gender": str(values.get("ai_voice_gender") or "male").strip().lower()[:10],
        "voice_name": str(values.get("ai_voice_name") or "").strip()[:120],
        "tts_enabled": bool(values.get("ai_tts_enabled")),
        "tts_base_url": str(values.get("ai_tts_base_url") or "").strip()[:500],
        "tts_model": str(values.get("ai_tts_model") or "tts-1").strip()[:120],
        "tts_voice": str(values.get("ai_tts_voice") or "alloy").strip()[:120],
        "tts_api_key": tts_key,
        "tts_has_key": bool(tts_key),
    }


def public_config(config: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "enabled": config["enabled"],
        "base_url": config["base_url"],
        "model": config["model"],
        "has_key": config["has_key"],
        "configured": bool(config["enabled"] and config["base_url"] and config["model"] and config["has_key"]),
        "temperature": config["temperature"],
        "max_tokens": config["max_tokens"],
        "wake_word": config["wake_word"],
        "name": config["name"],
        "voice_gender": config["voice_gender"] if config["voice_gender"] in ("male", "female") else "male",
        "voice_name": config["voice_name"],
        "tts_enabled": config["tts_enabled"],
        "tts_base_url": config["tts_base_url"],
        "tts_model": config["tts_model"],
        "tts_voice": config["tts_voice"],
        "tts_has_key": config["tts_has_key"],
    }


def save_config(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
    """兼容 AI 页面的友好字段名和内部 ai_ 前缀字段名。"""
    def pick(*names: str, default: Any = None) -> Any:
        for name in names:
            if name in payload:
                return payload.get(name)
        return default

    values: Dict[str, Any] = {}
    enabled = pick("ai_enabled", "enabled", default=None)
    if enabled is not None:
        values["ai_enabled"] = bool(enabled)
    for internal, friendly in (
        ("ai_base_url", "base_url"), ("ai_model", "model"),
        ("ai_temperature", "temperature"), ("ai_wake_word", "wake_word"),
    ):
        value = pick(internal, friendly, default=None)
        if value is not None:
            values[internal] = str(value or "").strip()
    name = pick("ai_name", "name", default=None)
    if name is not None:
        name = str(name or "").strip()
        if not name:
            raise ValueError("AI 名称不能为空")
        if len(name) > 20:
            raise ValueError("AI 名称最多 20 个字符")
        values["ai_name"] = name
    voice_gender = pick("ai_voice_gender", "voice_gender", default=None)
    if voice_gender is not None:
        voice_gender = str(voice_gender or "male").strip().lower()
        if voice_gender not in ("male", "female"):
            raise ValueError("音色性别只能是 male 或 female")
        values["ai_voice_gender"] = voice_gender
    voice_name = pick("ai_voice_name", "voice_name", default=None)
    if voice_name is not None:
        values["ai_voice_name"] = str(voice_name or "").strip()[:120]
    max_tokens = pick("ai_max_tokens", "max_tokens", default=None)
    if max_tokens is not None:
        values["ai_max_tokens"] = max(100, min(8000, int(max_tokens or 1200)))
    tts_enabled = pick("ai_tts_enabled", "tts_enabled", default=None)
    if tts_enabled is not None:
        values["ai_tts_enabled"] = bool(tts_enabled)
    for internal, friendly in (
        ("ai_tts_base_url", "tts_base_url"), ("ai_tts_model", "tts_model"),
        ("ai_tts_voice", "tts_voice"),
    ):
        value = pick(internal, friendly, default=None)
        if value is not None:
            values[internal] = str(value or "").strip()[:500]
    if payload.get("clear_tts_key"):
        values["ai_tts_api_key_enc"] = ""
    else:
        tts_key = str(pick("ai_tts_api_key", "tts_api_key", default="") or "").strip()
        if tts_key:
            values["ai_tts_api_key_enc"] = encrypt_password(tts_key)
    if payload.get("clear_key"):
        values["ai_api_key_enc"] = ""
    else:
        api_key = str(pick("ai_api_key", "api_key", default="") or "").strip()
        if api_key:
            values["ai_api_key_enc"] = encrypt_password(api_key)
    if values:
        settings_service.save(db, values)
    return public_config(get_config(db))


def _alert_items(
    db: Session,
    limit: int = 20,
    device_ids: Optional[List[int]] = None,
    levels: Optional[List[str]] = None,
    only_unack: bool = False,
    device_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    query = (
        db.query(Alert, Device)
        .outerjoin(Device, Alert.device_id == Device.id)
        .filter(Alert.resolved_at.is_(None), Alert.is_hidden.isnot(True))
    )
    if device_ids is not None:
        query = query.filter(Alert.device_id.in_(device_ids))
    if device_id is not None:
        query = query.filter(Alert.device_id == device_id)
    if levels:
        query = query.filter(Alert.alert_level.in_(levels))
    if only_unack:
        query = query.filter(Alert.is_acknowledged.is_(False))
    rows = query.order_by(Alert.created_at.desc()).limit(max(1, min(100, limit))).all()
    result = []
    for alert, device in rows:
        result.append({
            "id": alert.id,
            "source": "device",
            "is_acknowledged": bool(alert.is_acknowledged),
            "device_name": device.name if device else f"设备#{alert.device_id}",
            "device_ip": device.ip_address if device else "",
            "level": alert.alert_level,
            "level_label": alert.level_label or ALERT_LEVEL_LABELS.get(alert.alert_level, alert.alert_level),
            "type": alert.alert_type,
            "type_label": ALERT_TYPE_TEXT.get(alert.alert_type, alert.alert_type),
            "message": alert.message or "",
            "reason": alert.message or ALERT_TYPE_TEXT.get(alert.alert_type, alert.alert_type),
            "value": alert.value,
            "threshold": alert.threshold,
            "created_at": alert.created_at.isoformat() if alert.created_at else None,
        })
    return result


def _virtual_alerts(db: Session, limit: int = 20) -> List[Dict[str, Any]]:
    rows = (
        db.query(VirtualizationAlert)
        .filter(
            VirtualizationAlert.resolved_at.is_(None),
            VirtualizationAlert.is_hidden.isnot(True),
        )
        .order_by(VirtualizationAlert.created_at.desc())
        .limit(max(1, min(100, limit)))
        .all()
    )
    return [{
        "id": row.id,
        "source": "virtualization",
        "is_acknowledged": bool(row.is_acknowledged),
        "device_name": row.vm_name or row.platform_name or "虚拟化对象",
        "device_ip": "",
        "level": row.alert_level,
        "level_label": ALERT_LEVEL_LABELS.get(row.alert_level, row.alert_level),
        "type": row.alert_type,
        "type_label": ALERT_TYPE_TEXT.get(row.alert_type, row.alert_type),
        "message": row.message or "",
        "reason": row.message or ALERT_TYPE_TEXT.get(row.alert_type, row.alert_type),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "platform_name": row.platform_name or "",
    } for row in rows]


def _website_alerts(db: Session, limit: int = 20) -> List[Dict[str, Any]]:
    rows = (
        db.query(WebsiteAlert, WebsiteTarget)
        .outerjoin(WebsiteTarget, WebsiteAlert.target_id == WebsiteTarget.id)
        .filter(WebsiteAlert.resolved_at.is_(None), WebsiteAlert.is_hidden.isnot(True))
        .order_by(WebsiteAlert.created_at.desc())
        .limit(max(1, min(100, limit)))
        .all()
    )
    return [{
        "id": alert.id,
        "source": "website",
        "is_acknowledged": bool(alert.is_acknowledged),
        "device_name": target.name if target else f"网站#{alert.target_id}",
        "device_ip": (target.ip_address or target.url) if target else "",
        "level": alert.alert_level,
        "level_label": alert.level_label or ALERT_LEVEL_LABELS.get(alert.alert_level, alert.alert_level),
        "type": alert.alert_type,
        "type_label": ALERT_TYPE_TEXT.get(alert.alert_type, alert.alert_type),
        "message": alert.message or "",
        "reason": alert.message or ALERT_TYPE_TEXT.get(alert.alert_type, alert.alert_type),
        "value": None,
        "threshold": None,
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
    } for alert, target in rows]


def overview(
    db: Session,
    device_ids: Optional[List[int]] = None,
    include_virtualization: bool = True,
) -> Dict[str, Any]:
    device_query = db.query(Device)
    if device_ids is not None:
        device_query = device_query.filter(Device.id.in_(device_ids))
    assets_total = device_query.count()
    assets_enabled = device_query.filter(Device.is_enabled.is_(True)).count()
    by_type_rows = device_query.with_entities(Device.device_type, func.count(Device.id)).group_by(Device.device_type).all()
    by_type = [{"type": row[0] or "other", "count": int(row[1])} for row in by_type_rows]

    active_alerts = db.query(Alert).filter(Alert.resolved_at.is_(None), Alert.is_hidden.isnot(True))
    if device_ids is not None:
        active_alerts = active_alerts.filter(Alert.device_id.in_(device_ids))
    device_active = active_alerts.count()
    device_unack = active_alerts.filter(Alert.is_acknowledged.is_(False)).count()
    device_level_rows = active_alerts.with_entities(Alert.alert_level, func.count(Alert.id)).group_by(Alert.alert_level).all()
    device_type_rows = active_alerts.with_entities(Alert.alert_type, func.count(Alert.id)).group_by(Alert.alert_type).all()

    website_active = db.query(WebsiteAlert).filter(
        WebsiteAlert.resolved_at.is_(None), WebsiteAlert.is_hidden.isnot(True)
    ).count()
    website_unack = db.query(WebsiteAlert).filter(
        WebsiteAlert.resolved_at.is_(None), WebsiteAlert.is_acknowledged.is_(False)
    ).count()
    website_level_rows = db.query(WebsiteAlert.alert_level, func.count(WebsiteAlert.id)).filter(
        WebsiteAlert.resolved_at.is_(None)
    ).group_by(WebsiteAlert.alert_level).all()
    website_type_rows = db.query(WebsiteAlert.alert_type, func.count(WebsiteAlert.id)).filter(
        WebsiteAlert.resolved_at.is_(None)
    ).group_by(WebsiteAlert.alert_type).all()

    virtual_active = 0
    virtual_unack = 0
    virtual_level_rows = []
    virtual_type_rows = []
    if include_virtualization:
        virtual_query = db.query(VirtualizationAlert).filter(
            VirtualizationAlert.resolved_at.is_(None),
            VirtualizationAlert.is_hidden.isnot(True),
        )
        virtual_active = virtual_query.count()
        virtual_unack = virtual_query.filter(VirtualizationAlert.is_acknowledged.is_(False)).count()
        virtual_level_rows = virtual_query.with_entities(
            VirtualizationAlert.alert_level, func.count(VirtualizationAlert.id)
        ).group_by(VirtualizationAlert.alert_level).all()
        virtual_type_rows = virtual_query.with_entities(
            VirtualizationAlert.alert_type, func.count(VirtualizationAlert.id)
        ).group_by(VirtualizationAlert.alert_type).all()

    alert_total = device_active + website_active + virtual_active
    alert_unack = device_unack + website_unack + virtual_unack
    by_level: Dict[str, int] = {}
    for rows in (device_level_rows, website_level_rows, virtual_level_rows):
        for level, count in rows:
            key = str(level or "warning")
            by_level[key] = by_level.get(key, 0) + int(count)
    type_counts: Dict[str, int] = {}
    for rows in (device_type_rows, website_type_rows, virtual_type_rows):
        for alert_type, count in rows:
            key = str(alert_type or "unknown")
            type_counts[key] = type_counts.get(key, 0) + int(count)
    by_alert_type = [
        {"type": key, "label": ALERT_TYPE_TEXT.get(key, key), "count": count}
        for key, count in sorted(type_counts.items(), key=lambda item: -item[1])
    ]
    recent_device_alerts = _alert_items(db, 12, device_ids)
    recent_website_alerts = _website_alerts(db, 8)
    recent_virtual_alerts = _virtual_alerts(db, 8) if include_virtualization else []

    mib_files = db.query(MibFile).count()
    mib_objects = db.query(MibObject).count()
    category_rows = (
        db.query(MibObject.category, func.count(MibObject.id))
        .filter(MibObject.category.isnot(None), MibObject.category != "")
        .group_by(MibObject.category)
        .order_by(func.count(MibObject.id).desc())
        .limit(12)
        .all()
    )
    mib_categories = [{"category": row[0], "count": int(row[1])} for row in category_rows]

    virtual_platforms = db.query(VirtualPlatform).count() if include_virtualization else 0
    virtual_hosts = db.query(VirtualHost).count() if include_virtualization else 0
    virtual_vms = db.query(VirtualMachine).count() if include_virtualization else 0
    virtual_alerts = virtual_unack
    inspection_tasks = db.query(InspectionTask).count()
    inspection_reports = db.query(InspectionReport).count()

    scope_devices = (db.query(Device) if device_ids is None else db.query(Device).filter(Device.id.in_(device_ids or [-1]))).all()
    linked_ids = set()
    for link in db.query(DeviceConnection).all():
        linked_ids.add(link.source_device_id)
        linked_ids.add(link.dest_device_id)
    cabinets = db.query(Cabinet).all()
    total_u = sum(int(c.u_capacity or 42) for c in cabinets)
    used_u = sum(int(d.u_height or 1) for d in scope_devices if d.cabinet_id)
    certificates = db.query(ManagedCertificate).all()
    cert_issues = [c for c in certificates if str(c.status or "") in ("expiring", "expired", "error")]
    failed_backups = (
        db.query(ConfigBackup).filter(ConfigBackup.status == "failed")
        .order_by(ConfigBackup.created_at.desc()).limit(10).all()
    )
    values = settings_service.get_all(db) or {}
    module_stats = {
        "backups": {
            "global_enabled": bool(values.get("config_backup_enabled")),
            "global_interval_hours": int(values.get("config_backup_interval_hours") or 24),
            "enabled_devices": len([d for d in scope_devices if d.backup_enabled]),
            "failed": len(failed_backups),
            "disabled_names": [d.name for d in scope_devices if not d.backup_enabled][:10],
        },
        "credentials": {
            "devices": len(scope_devices),
            "configured": len([d for d in scope_devices if d.credential_id or (d.backup_username and d.backup_password)]),
            "missing": len([d for d in scope_devices if not d.credential_id and not (d.backup_username and d.backup_password)]),
            "missing_names": [d.name for d in scope_devices if not d.credential_id and not (d.backup_username and d.backup_password)][:10],
        },
        "mib_coverage": {
            "devices": len(scope_devices),
            "bound": len([d for d in scope_devices if d.mib_id or d.custom_metrics]),
            "unbound": len([d for d in scope_devices if not d.mib_id and not d.custom_metrics]),
            "unbound_names": [d.name for d in scope_devices if not d.mib_id and not d.custom_metrics][:10],
        },
        "topology": {
            "devices": len(scope_devices), "links": int(db.query(DeviceConnection).count()),
            "isolated": len([d for d in scope_devices if d.id not in linked_ids]),
            "isolated_names": [d.name for d in scope_devices if d.id not in linked_ids][:10],
        },
        "rooms": {
            "rooms": int(db.query(Room).count()), "cabinets": len(cabinets),
            "total_u": total_u, "used_u": used_u,
            "u_usage_percent": round(used_u / total_u * 100, 1) if total_u else 0,
            "power_capacity_w": sum(float(c.power_capacity_w or 0) for c in cabinets),
        },
        "website": {
            "targets": int(db.query(WebsiteTarget).count()),
            "active_alerts": int(website_active),
            "certificates": len(certificates), "certificate_issues": len(cert_issues),
        },
        "health": {
            "asset_enabled_percent": round(assets_enabled / assets_total * 100, 1) if assets_total else 0,
            "mib_coverage_percent": round(len([d for d in scope_devices if d.mib_id or d.custom_metrics]) / len(scope_devices) * 100, 1) if scope_devices else 0,
            "credential_coverage_percent": round(len([d for d in scope_devices if d.credential_id or (d.backup_username and d.backup_password)]) / len(scope_devices) * 100, 1) if scope_devices else 0,
            "backup_coverage_percent": round(len([d for d in scope_devices if d.backup_enabled]) / len(scope_devices) * 100, 1) if scope_devices else 0,
        },
    }

    return {
        "time": datetime.now().isoformat(timespec="seconds"),
        "assets": {"total": assets_total, "enabled": assets_enabled, "by_type": by_type},
        "alerts": {
            "active": alert_total,
            "unacknowledged": alert_unack,
            "by_level": by_level,
            "by_type": by_alert_type,
            "recent": recent_device_alerts,
            "website_recent": recent_website_alerts,
            "virtual_recent": recent_virtual_alerts,
            "device_active": device_active,
            "website_active": website_active,
            "virtual_active": virtual_active,
        },
        "mibs": {"files": mib_files, "objects": mib_objects, "categories": mib_categories},
        "virtualization": {
            "platforms": virtual_platforms, "hosts": virtual_hosts,
            "vms": virtual_vms, "alerts": virtual_alerts,
        },
        "inspection": {"tasks": inspection_tasks, "reports": inspection_reports},
        "module_stats": module_stats,
        "functions": FUNCTION_LIST,
    }


def _alert_analysis(data: Dict[str, Any]) -> Dict[str, Any]:
    alerts = data["alerts"]
    recent = alerts["recent"] + alerts.get("website_recent", []) + alerts["virtual_recent"]
    by_type: Dict[str, int] = {
        str(item.get("type") or "unknown"): int(item.get("count") or 0)
        for item in alerts.get("by_type", [])
    }
    causes = []
    suggestions = []
    seen = set()
    for item in recent:
        key = item.get("type") or "unknown"
        if key in seen:
            continue
        seen.add(key)
        causes.append({"type": key, "label": ALERT_TYPE_TEXT.get(key, key), "cause": CAUSE_TEXT.get(key, "需要结合设备日志和网络链路进一步定位"), "count": by_type.get(key, 0)})
        suggestions.append({"type": key, "suggestion": SUGGESTION_TEXT.get(key, "检查相关设备和告警详情，确认影响范围")})
    summary = (
        f"当前未恢复告警 {alerts['active']} 条，其中未确认 {alerts['unacknowledged']} 条；"
        f"设备 {alerts.get('device_active', 0)} 条、网站 {alerts.get('website_active', 0)} 条、"
        f"虚拟化 {alerts.get('virtual_active', 0)} 条。"
    )
    return {"summary": summary, "by_type": by_type, "causes": causes, "suggestions": suggestions}


# ==================== 实时只读查询上下文 ====================

ALERT_INTENT_WORDS = (
    "告警", "报警", "故障", "异常", "原因", "处理建议", "怎么处理", "严重", "紧急",
    "未确认", "未处理", "离线", "宕机", "告警研判",
)
DEVICE_DETAIL_WORDS = (
    "这台", "那台", "该设备", "这个设备", "设备详情", "设备状态", "主机", "型号",
    "厂商", "序列号", "维保", "在线吗", "离线吗", "怎么样", "状态如何",
)


def _device_lookup_expected(question: str) -> bool:
    """问题是否明确指向“某台设备”（IP/指示代词/厂商或类型清单），
    用于决定查不到设备时是否要回复“未匹配到”，避免把泛泛的概览问题误判为设备查询。"""
    if IPV4_RE.search(question):
        return True
    if any(word in question for word in (
        "这台", "那台", "该设备", "这个设备", "这台设备", "那台设备",
    )):
        return True
    lowered = question.lower()
    asks_list = any(word in question for word in ("有哪些", "哪些", "列出"))
    return bool(
        asks_list
        and (
            any(hint in lowered for hint in _VENDOR_HINTS)
            or any(word in question for word in _DEVICE_TYPE_WORDS)
        )
    )


def _parse_date(value: Any):
    text = str(value or "").strip()[:10]
    if not text:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _latest_metric_map(db: Session, device_ids: List[int]) -> Dict[int, DeviceMetric]:
    """批量取设备最新一条监控指标，避免逐台查询。"""
    if not device_ids:
        return {}
    try:
        latest = (
            db.query(DeviceMetric.device_id, func.max(DeviceMetric.collected_at).label("collected_at"))
            .filter(DeviceMetric.device_id.in_(device_ids))
            .group_by(DeviceMetric.device_id)
            .subquery()
        )
        rows = (
            db.query(DeviceMetric)
            .join(
                latest,
                and_(
                    DeviceMetric.device_id == latest.c.device_id,
                    DeviceMetric.collected_at == latest.c.collected_at,
                ),
            )
            .all()
        )
        return {row.device_id: row for row in rows}
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI 查询设备最新指标失败: %s", exc)
        return {}


def _metric_dict(metric: Optional[DeviceMetric]) -> Dict[str, Any]:
    if metric is None:
        return {}
    result: Dict[str, Any] = {}
    for key in ("cpu_usage", "memory_usage", "disk_usage", "temperature", "power_status", "uptime"):
        value = getattr(metric, key, None)
        if value is not None:
            result[key] = value
    if metric.collected_at:
        result["collected_at"] = metric.collected_at.isoformat(timespec="seconds")
    return result


def _device_snapshot(device: Device, metric: Optional[DeviceMetric], active_alerts: int) -> Dict[str, Any]:
    """只输出可对模型公开的资产字段，绝不包含 Community、密码、Token 等凭据。"""
    return {
        "name": device.name,
        "ip": device.ip_address,
        "type": device.device_type,
        "type_label": DEVICE_TYPE_LABELS.get(device.device_type, device.device_type),
        "vendor": device.vendor or "",
        "model": device.model or "",
        "serial_number": device.serial_number or "",
        "location": device.location or "",
        "asset_no": device.asset_no or "",
        "enabled": bool(device.is_enabled),
        "monitor_type": device.monitor_type or "snmp",
        "warranty_until": device.warranty_until or "",
        "active_alerts": int(active_alerts or 0),
        "latest_metrics": _metric_dict(metric),
    }


def _should_lookup_devices(question: str) -> bool:
    if _device_lookup_expected(question):
        return True
    return any(word in question for word in DEVICE_DETAIL_WORDS)


def _match_devices(db: Session, question: str, device_ids: Optional[List[int]], limit: int = 5) -> List[Device]:
    """按问题中的 IP、名称/型号片段、厂商、设备类型做真实库内匹配（最多 5 台）。"""
    ors = []
    for ip in IPV4_RE.findall(question):
        ors.append(Device.ip_address == ip)
    for token in re.findall(r"[A-Za-z][A-Za-z0-9._-]{2,40}", question):
        if token.lower() in _STOP_TOKENS:
            continue
        like = f"%{token}%"
        ors.extend([
            Device.name.ilike(like),
            Device.ip_address.ilike(like),
            Device.vendor.ilike(like),
            Device.model.ilike(like),
            Device.asset_no.ilike(like),
        ])
    lowered = question.lower()
    for hint, candidates in _VENDOR_HINTS.items():
        if hint in lowered:
            for candidate in candidates:
                ors.append(Device.vendor.ilike(f"%{candidate}%"))
    for word, device_type in _DEVICE_TYPE_WORDS.items():
        if word in question:
            ors.append(Device.device_type == device_type)
    try:
        query = db.query(Device)
        if device_ids is not None:
            query = query.filter(Device.id.in_(device_ids))
        # 中文设备名无法通过 ASCII 分词匹配：直接与可见资产名做子串匹配。
        for (name,) in query.with_entities(Device.name).limit(2000).all():
            if name and len(name) >= 2 and name in question:
                ors.append(Device.name == name)
        if not ors:
            return []
        return (
            query.filter(or_(*ors))
            .order_by(Device.is_enabled.desc(), Device.id.asc())
            .limit(max(1, min(10, limit)))
            .all()
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI 匹配设备失败: %s", exc)
        return []


def _alert_level_filter(question: str) -> List[str]:
    if any(word in question for word in ("紧急", "emergency")):
        return ["emergency"]
    if any(word in question for word in ("严重", "critical", "高优")):
        return ["critical", "emergency"]
    if "警告" in question:
        return ["warning"]
    return []


def _asset_stats(db: Session, device_ids: Optional[List[int]]) -> Dict[str, Any]:
    """资产统计：类型分布、厂商分布、启用状态、维保到期（全部来自数据库）。"""
    query = db.query(Device)
    if device_ids is not None:
        query = query.filter(Device.id.in_(device_ids))
    total = query.count()
    enabled = query.filter(Device.is_enabled.is_(True)).count()
    type_rows = (
        query.with_entities(Device.device_type, func.count(Device.id))
        .group_by(Device.device_type)
        .all()
    )
    by_type = [
        {
            "type": row[0] or "other",
            "label": DEVICE_TYPE_LABELS.get(row[0] or "other", row[0] or "other"),
            "count": int(row[1]),
        }
        for row in type_rows
    ]
    by_type.sort(key=lambda item: item["count"], reverse=True)
    vendor_rows = (
        query.with_entities(Device.vendor, func.count(Device.id))
        .filter(Device.vendor.isnot(None), Device.vendor != "")
        .group_by(Device.vendor)
        .order_by(func.count(Device.id).desc())
        .limit(8)
        .all()
    )
    by_vendor = [{"vendor": row[0], "count": int(row[1])} for row in vendor_rows]

    today = datetime.now().date()
    expired, expiring = [], []
    try:
        warranty_rows = (
            query.with_entities(Device.name, Device.ip_address, Device.warranty_until)
            .filter(Device.warranty_until.isnot(None), Device.warranty_until != "")
            .limit(2000)
            .all()
        )
        for name, ip, warranty_until in warranty_rows:
            date = _parse_date(warranty_until)
            if not date:
                continue
            item = {"name": name, "ip": ip, "warranty_until": date.isoformat()}
            if date < today:
                expired.append(item)
            elif (date - today).days <= 30:
                expiring.append(item)
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI 查询维保数据失败: %s", exc)
    expiring.sort(key=lambda item: item["warranty_until"])
    expired.sort(key=lambda item: item["warranty_until"], reverse=True)
    return {
        "total": total,
        "enabled": enabled,
        "disabled": max(0, total - enabled),
        "by_type": by_type,
        "by_vendor": by_vendor,
        "warranty_expired_count": len(expired),
        "warranty_expiring_30d_count": len(expiring),
        "warranty_expired_list": expired[:5],
        "warranty_expiring_list": expiring[:5],
    }


def _chat_query_context(
    db: Session,
    question: str,
    device_ids: Optional[List[int]] = None,
    include_virtualization: bool = True,
) -> Dict[str, Any]:
    """为一次对话组装“真实查询结果”上下文：总览 + 按问题意图补充明细。"""
    data = overview(db, device_ids=device_ids, include_virtualization=include_virtualization)
    data["alert_analysis"] = _alert_analysis(data)
    intents: List[str] = []

    try:
        data["asset_stats"] = _asset_stats(db, device_ids)
        intents.append("assets")
    except Exception as exc:  # noqa: BLE001
        logger.warning("AI 查询资产统计失败: %s", exc)

    alert_details: List[Dict[str, Any]] = []
    if any(word in question for word in ALERT_INTENT_WORDS) or _should_lookup_devices(question):
        try:
            level_filter = _alert_level_filter(question)
            only_unack = any(word in question for word in ("未确认", "未处理", "未恢复"))
            alert_details = _alert_items(
                db, 10, device_ids,
                levels=level_filter, only_unack=only_unack,
            )
            if include_virtualization:
                alert_details += _virtual_alerts(db, 20)
            alert_details += _website_alerts(db, 20)
            if level_filter:
                alert_details = [item for item in alert_details if item.get("level") in level_filter]
            if only_unack:
                alert_details = [item for item in alert_details if not item.get("is_acknowledged")]
            alert_details.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
            intents.append("alerts")
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI 查询告警明细失败: %s", exc)

    device_details: List[Dict[str, Any]] = []
    if _should_lookup_devices(question):
        try:
            matched = _match_devices(db, question, device_ids)
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI 匹配设备失败: %s", exc)
            matched = []
        metric_map = _latest_metric_map(db, [device.id for device in matched])
        for device in matched:
            active = (
                db.query(func.count(Alert.id))
                .filter(Alert.device_id == device.id, Alert.resolved_at.is_(None))
                .scalar()
                or 0
            )
            device_details.append(_device_snapshot(device, metric_map.get(device.id), active))
            if len(alert_details) < 10:
                try:
                    alert_details.extend(_alert_items(db, 3, device_ids, device_id=device.id))
                except Exception:  # noqa: BLE001
                    pass
        if device_details:
            intents.append("devices")
        elif _device_lookup_expected(question):
            data["device_lookup"] = {
                "matched": 0,
                "note": "按问题中的 IP/名称/厂商/类型未在当前可见资产中匹配到设备",
            }
            intents.append("devices_not_found")
    # 去重，保持最近顺序
    if alert_details:
        seen_ids = set()
        deduped = []
        for item in alert_details:
            key = f"{item.get('source') or 'device'}:{item.get('id')}"
            if key in seen_ids:
                continue
            seen_ids.add(key)
            deduped.append(item)
        data["alert_details"] = deduped[:10]

    data["device_details"] = device_details
    capability = any(word in question for word in ("功能", "能做什么", "帮助", "能力", "支持"))
    if capability:
        intents.append("capability")
    else:
        data.pop("functions", None)
    if data.get("device_details") and not data.get("alert_details"):
        data.pop("alert_details", None)
    data["query_meta"] = {
        "data_time": data.get("time"),
        "readonly": True,
        "intent": intents,
        "scope": "全部可见资产" if device_ids is None else f"当前账号可见的 {len(device_ids)} 台设备",
        "boundary": "本上下文由后端数据库实时只读查询生成；未出现的数据视为系统不可查询，禁止编造。",
    }
    return data


def _context_text(data: Dict[str, Any]) -> str:
    """按重要性排序后序列化：保证数据时间、查询边界、告警/设备明细不会被截断。"""
    ordered: Dict[str, Any] = {}
    for key in (
        "time", "query_meta", "assets", "asset_stats", "alert_analysis", "alerts",
        "device_details", "alert_details", "device_lookup", "mibs",
        "virtualization", "inspection", "functions",
    ):
        if key in data:
            ordered[key] = data[key]
    alerts = ordered.get("alerts")
    if isinstance(alerts, dict):
        if ordered.get("alert_details"):
            alerts = dict(alerts)
            alerts["recent"] = list(alerts.get("recent") or [])[:6]
            alerts["virtual_recent"] = list(alerts.get("virtual_recent") or [])[:4]
            ordered["alerts"] = alerts
    text = json.dumps(ordered, ensure_ascii=False, default=str)
    return text[:12000]


def _local_answer(question: str, data: Dict[str, Any], history: Optional[List[Dict[str, Any]]] = None, assistant_name: str = "玄武") -> str:
    text = (question or "").strip()
    assistant_name = str(assistant_name or "玄武").strip() or "玄武"
    history = history or []
    last_user = next(
        (str(item.get("content") or "").strip() for item in reversed(history) if str(item.get("role") or "") == "user"),
        "",
    )
    # 本地模式也要支持最常见的追问/寒暄，避免每句话都像冷启动。
    if text and any(word in text for word in ("你好", "您好", "在吗", "嗨")):
        return f"你好，我是{assistant_name}。当前可以通过文字或连续语音询问资产、告警、MIB、虚拟化和巡检情况。"
    if text and any(word in text for word in ("谢谢", "感谢", "辛苦")):
        return "不客气。需要继续看告警、资产或指标时直接说即可。"
    if text and any(word in text for word in (
        "刚才", "继续", "详细", "为什么", "然后", "再说", "它", "它们",
        "这个设备", "该设备", "还有", "接着", "上面", "这些",
    )) and last_user:
        text = f"{last_user} {text}"
    analysis = _alert_analysis(data)
    details = data.get("device_details") or []
    alert_details = data.get("alert_details") or []
    # 设备级真实查询结果优先回答，避免本地模式编造设备信息。
    if details:
        lines = [f"系统只读查询到 {len(details)} 台匹配设备（数据时间：{data.get('time')}）："]
        for item in details[:5]:
            metrics = item.get("latest_metrics") or {}
            metric_bits = []
            if metrics.get("cpu_usage") is not None:
                metric_bits.append(f"CPU {metrics['cpu_usage']}%")
            if metrics.get("memory_usage") is not None:
                metric_bits.append(f"内存 {metrics['memory_usage']}%")
            if metrics.get("temperature") is not None:
                metric_bits.append(f"温度 {metrics['temperature']}℃")
            if metrics.get("disk_usage") is not None:
                metric_bits.append(f"磁盘 {metrics['disk_usage']}%")
            if metrics.get("power_status"):
                metric_bits.append(f"电源 {metrics['power_status']}")
            line = (
                f"- {item.get('name')}（{item.get('ip')}，{item.get('type_label')}，"
                f"{'已启用监控' if item.get('enabled') else '已停用监控'}，"
                f"未恢复告警 {item.get('active_alerts', 0)} 条）"
            )
            if item.get("vendor") or item.get("model"):
                line += f"，厂商/型号：{item.get('vendor') or '-'}/{item.get('model') or '-'}"
            if metric_bits:
                line += "；最新指标：" + "，".join(metric_bits)
            lines.append(line)
        lines.append("以上数据来自系统实时只读查询；接口明细与历史趋势请到设备详情页查看。")
        return "\n".join(lines)
    lookup = data.get("device_lookup")
    if lookup and not details:
        return (
            "未在当前账号可见的资产中匹配到对应设备。请提供准确的 IP 或设备名称，"
            "或到「资产管理」页面确认设备是否已纳管；AI 不会编造设备数据。"
        )
    if alert_details and any(word in text for word in (
        "严重", "紧急", "未确认", "未处理", "哪些", "列表", "明细", "详情", "告警",
    )):
        lines = [
            f"当前未恢复告警 {data['alerts']['active']} 条（未确认 {data['alerts']['unacknowledged']} 条），"
            f"以下是系统实时查询到的明细（数据时间：{data.get('time')}）："
        ]
        for item in alert_details[:8]:
            value = item.get("value")
            threshold = item.get("threshold")
            value_text = ""
            if value is not None and threshold is not None:
                value_text = f"，当前值 {value} / 阈值 {threshold}"
            lines.append(
                f"- [{item.get('level_label')}] {item.get('device_name')}"
                f"（{item.get('device_ip') or '-'}）{item.get('type_label')}{value_text}："
                f"{item.get('reason') or item.get('message') or '-'}"
            )
        lines.append("处理建议：先确认告警是否仍在持续，再按类型排查链路、电源、性能或配置；需要确认或处理请到「告警中心」。")
        return "\n".join(lines)
    if any(word in text for word in ("怎么样", "概况", "总体", "运行状态", "系统状态")):
        a = data["assets"]
        alerts = data["alerts"]
        return (
            f"当前资产 {a['total']} 台，启用 {a['enabled']} 台；"
            f"未恢复告警 {alerts['active']} 条，其中未确认 {alerts['unacknowledged']} 条。"
            "你可以继续问“严重告警有哪些”或“分析告警原因”。"
        )
    if any(word in text for word in ("告警", "故障", "异常", "处理", "原因")):
        lines = [analysis["summary"], ""]
        if analysis["causes"]:
            lines.append("可能原因：")
            for item in analysis["causes"][:6]:
                lines.append(f"- {item['label']}：{item['cause']}")
            lines.append("")
            lines.append("处理建议：")
            for item in analysis["suggestions"][:6]:
                lines.append(f"- {item['suggestion']}")
        else:
            lines.append("当前没有未恢复告警，建议保持巡检和告警渠道测试。")
        return "\n".join(lines)
    if any(word in text.lower() for word in ("mib", "指标", "oid", "采集")):
        m = data["mibs"]
        cats = "、".join(f"{item['category']} {item['count']}" for item in m["categories"][:8]) or "暂无分类"
        return (
            f"当前已导入 MIB {m['files']} 个、OID 对象 {m['objects']} 个。\n"
            f"主要指标分类：{cats}。\n"
            "如需调整采集 OID，请到「MIB 管理」查看对象并选择只读指标；AI 不会直接修改设备采集配置。"
        )
    if any(word in text for word in ("资产", "设备", "盘点")):
        a = data["assets"]
        stats = data.get("asset_stats") or {}
        by_type = stats.get("by_type") or a["by_type"]
        types = "、".join(
            f"{item.get('label') or item.get('type')} {item['count']}" for item in by_type[:8]
        ) or "暂无分类"
        lines = [f"当前资产 {a['total']} 台，启用 {a['enabled']} 台。", f"设备类型分布：{types}。"]
        vendors = stats.get("by_vendor") or []
        if vendors:
            lines.append("厂商分布：" + "、".join(f"{item['vendor']} {item['count']}" for item in vendors))
        if stats.get("warranty_expiring_30d_count"):
            items = stats.get("warranty_expiring_list") or []
            detail = "、".join(f"{item['name']}（{item['warranty_until']}）" for item in items[:5])
            lines.append(f"30 天内维保到期 {stats['warranty_expiring_30d_count']} 台：{detail}。")
        if stats.get("warranty_expired_count"):
            lines.append(f"已过保 {stats['warranty_expired_count']} 台，建议尽快续保。")
        return "\n".join(lines)
    if any(word in text for word in ("虚拟", "容器", "docker", "kubernetes", "k8s")):
        v = data["virtualization"]
        return f"当前虚拟化平台 {v['platforms']} 个，宿主机 {v['hosts']} 台，虚拟机/容器 {v['vms']} 个，未确认虚拟化告警 {v['alerts']} 条。"
    if any(word in text for word in ("报告", "总结", "汇总")):
        return "可以点击「AI 生成报告」生成当前运维报告。报告会汇总资产、告警、MIB、虚拟化和巡检统计，并通过 Word 下载。"
    if any(word in text for word in ("功能", "能做什么", "帮助", "能力")):
        return "本系统包含：\n" + "\n".join(f"- {item}" for item in FUNCTION_LIST) + "\n\nAI 仅提供这些功能的查询、统计、告警分析和报告辅助，不执行授权、用户、服务或系统关键配置的修改。"
    return (
        f"我是{assistant_name} AI 运维助手，可以帮你做资产统计、MIB 指标统计、告警分析、虚拟化巡检查询和运维报告生成。\n"
        "你可以问：当前有哪些严重告警？MIB 指标有哪些分类？帮我生成运维报告。"
    )


def recommend_mib(db: Session, device: Dict[str, Any], candidates: List[Dict[str, Any]]) -> Dict[str, Any]:
    """让外部模型在现有候选 MIB 中排序并解释，不执行绑定。"""
    config = get_config(db)
    if not (config.get("enabled") and config.get("api_key") and config.get("base_url") and config.get("model")):
        raise ValueError("外部 AI 模型未配置")
    safe_candidates = []
    for item in candidates[:6]:
        safe_candidates.append({
            "mib_id": item.get("mib_id"),
            "module": item.get("module_name") or item.get("filename"),
            "filename": item.get("filename"),
            "vendor": item.get("vendor") or "",
            "device_model": item.get("device_model") or "",
            "categories": item.get("categories") or [],
            "valid_count": item.get("valid_count", 0),
            "tested_count": item.get("tested_count", 0),
            "confidence": item.get("confidence", 0),
            "metrics": [
                {
                    "name": metric.get("name"),
                    "category": metric.get("category"),
                    "valid": bool(metric.get("valid")),
                    "value": metric.get("value"),
                    "reason": metric.get("reason"),
                }
                for metric in (item.get("metrics") or [])[:10]
            ],
        })
    prompt = (
        "你是网络设备 MIB 匹配专家。只能从给定的候选 MIB 中选择，不要编造 mib_id。"
        "根据设备厂商、型号、sysDescr、sysObjectID，以及候选 MIB 的分类和真实 OID 校验结果，"
        "选出一个最适合的候选并解释原因。只返回严格 JSON，不要 Markdown："
        '{"recommended_mib_id": 数字, "confidence": 0-100, "reason": "不超过200字"}\n'
        f"设备：{json.dumps(device, ensure_ascii=False)[:2000]}\n"
        f"候选：{json.dumps(safe_candidates, ensure_ascii=False)[:9000]}"
    )
    reply = _call_model(config, [
        {"role": "system", "content": "你只做只读 MIB 候选排序，不能执行绑定、修改设备或访问授权信息。"},
        {"role": "user", "content": prompt},
    ])
    text = str(reply or "").strip()
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("AI 返回不是有效 JSON")
    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError as exc:
        raise ValueError("AI 返回 JSON 解析失败") from exc
    try:
        mib_id = int(data.get("recommended_mib_id"))
        confidence = max(0, min(100, int(data.get("confidence") or 0)))
    except (TypeError, ValueError):
        raise ValueError("AI 返回的推荐 MIB 编号无效") from None
    allowed = {int(item.get("mib_id")) for item in candidates if item.get("mib_id") is not None}
    if mib_id not in allowed:
        raise ValueError("AI 推荐的 MIB 不在候选列表中，已忽略")
    selected = next((item for item in candidates if int(item.get("mib_id")) == mib_id), None)
    return {
        "recommended_mib_id": mib_id,
        "mib_name": (selected or {}).get("module_name") or (selected or {}).get("filename") or f"MIB #{mib_id}",
        "confidence": confidence,
        "reason": str(data.get("reason") or "")[:500],
        "model": config.get("model") or "",
    }


def _tts_url(base_url: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    if base.endswith("/audio/speech"):
        return base
    return base + "/audio/speech"


def synthesize_speech(config: Dict[str, Any], text: str) -> tuple[bytes, str, str]:
    """调用 OpenAI 兼容 /audio/speech；返回音频字节、Content-Type 和错误。"""
    content = str(text or "").strip()
    if not content:
        raise ValueError("TTS 文本为空")
    if len(content) > 2000:
        content = content[:2000]
    if not config.get("tts_enabled"):
        raise ValueError("TTS 语音模型未启用")
    base_url = str(config.get("tts_base_url") or config.get("base_url") or "").strip()
    model = str(config.get("tts_model") or "").strip()
    voice = str(config.get("tts_voice") or "alloy").strip()
    api_key = str(config.get("tts_api_key") or config.get("api_key") or "").strip()
    if not base_url or not model:
        raise ValueError("TTS 地址或模型未配置")
    body = {
        "model": model, "input": content, "voice": voice,
        "response_format": "mp3", "speed": 0.98,
    }
    headers = {"Content-Type": "application/json", "User-Agent": "SNMP-NMS-AI-TTS/1.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        _tts_url(base_url), data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers, method="POST",
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        audio = response.read()
        media_type = response.headers.get("Content-Type") or "audio/mpeg"
    if not audio:
        raise RuntimeError("TTS 返回空音频")
    return audio, media_type, ""


def _model_url(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def _call_model(config: Dict[str, Any], messages: List[Dict[str, str]], timeout: int = 60) -> str:
    if not config.get("base_url") or not config.get("model") or not config.get("api_key"):
        raise ValueError("AI 模型未配置")
    body = {
        "model": config["model"],
        "messages": messages,
        "temperature": float(config.get("temperature") or 0.2),
        "max_tokens": int(config.get("max_tokens") or 1200),
    }
    request = urllib.request.Request(
        _model_url(config["base_url"]),
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config['api_key']}",
            "User-Agent": "SNMP-NMS-AI-Ops/1.0",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        payload = json.loads(response.read().decode("utf-8", errors="replace"))
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError("模型没有返回 choices")
    content = choices[0].get("message", {}).get("content")
    if not content:
        raise RuntimeError("模型返回内容为空")
    return str(content).strip()


SYSTEM_PROMPT = """你是“{assistant_name}”AI 智能运维助手，只服务当前智能运维平台。

【平台数据边界】
1. 你的依据只有两部分：本次消息中提供的“实时只读查询结果”，以及对话历史。查询结果由平台后端数据库生成，包含资产、告警、MIB、虚拟化、巡检等统计数据。
2. 只能回答查询结果或对话历史中出现过的信息。查询结果没有的设备、IP、告警、数值、时间、人员、配置，一律回答“系统当前查询不到”或“不在可查询范围”，并给出可查看的页面（资产管理/告警中心/MIB 管理/虚拟化管理/巡检报告/系统配置），严禁编造、猜测或用通用经验补全。
3. 不要输出或推测 SNMP Community、v3 认证/加密密码、SSH 密码、API Key、Token 等任何凭据，也不要尝试访问设备命令行、文件系统或凭据。
4. 涉及其他群组或无权查看的资产时，说明当前账号只能看到其权限范围内的数据。

【只读约束】
允许：查询/统计/分析、告警研判、解释本系统已有功能、给处理建议。
禁止：修改授权/用户/角色、修改系统配置、启动/停止/重启服务、升级、删除数据、执行任意写操作，或给出绕过权限的方法。
用户要求禁止事项时明确拒绝，并说明只能由有权限的管理员在对应页面操作。

【回答要求】
1. 只使用中文回答。
2. 先给结论，再给依据；引用具体设备名、IP、数值、级别、时间等可核对信息。
3. 多轮对话要结合历史理解“它、这台、刚才、继续、还有呢”等指代；指代不明确时先追问，不要重复上一轮整段内容。
4. 数据时间以查询结果中的 data_time/query_meta.data_time 为准，需要时说明“截至某时间”。
5. 简洁、可操作；不要输出大段原始 JSON 或凭空扩展表格。"""

VOICE_STYLE_PROMPT = """
【当前为连续语音对话】请用简短口语化中文回答，建议不超过 150 字；不要使用 Markdown 表格、代码块或长列表，先说结论，最多给 3 条处理建议。"""


FOLLOWUP_WORDS = (
    "详细", "继续", "刚才", "上面", "刚才说", "还有", "接着", "它", "它们",
    "这台", "那台", "该设备", "这个设备", "再说", "然后", "为什么", "展开",
)


def _is_followup(question: str) -> bool:
    text = str(question or "").strip()
    if not text or len(text) > 30:
        return False
    return any(word in text for word in FOLLOWUP_WORDS)


def _last_user_question(history: List[Dict[str, str]]) -> str:
    for item in reversed(history or []):
        if item.get("role") == "user":
            return str(item.get("content") or "").strip()
    return ""


def _build_system_prompt(assistant_name: str, channel: str = "text") -> str:
    prompt = SYSTEM_PROMPT.replace("{assistant_name}", assistant_name or "玄武")
    if str(channel or "").strip().lower() in ("voice", "speech", "audio"):
        prompt += VOICE_STYLE_PROMPT
    return prompt


def _trim_for_model(history: List[Dict[str, str]]) -> List[Dict[str, str]]:
    messages: List[Dict[str, str]] = []
    for item in history[-MODEL_HISTORY_MESSAGES:]:
        content = str(item.get("content") or "").strip()
        if not content:
            continue
        messages.append({"role": item.get("role") or "user", "content": content[:1600]})
    return messages


def _persist_turn(
    username: str,
    session_id: str,
    history: List[Dict[str, str]],
    question: str,
    reply: str,
) -> None:
    messages = list(history) + [
        {"role": "user", "content": question[:4000]},
        {"role": "assistant", "content": str(reply or "")[:4000]},
    ]
    _save_session_history(username, session_id, messages)


def chat(
    db: Session,
    question: str,
    history: Optional[List[Dict[str, Any]]] = None,
    device_ids: Optional[List[int]] = None,
    include_virtualization: bool = True,
    session_id: str = "",
    username: str = "",
    channel: str = "text",
) -> Dict[str, Any]:
    question = str(question or "").strip()
    if not question:
        raise ValueError("请输入问题")
    if len(question) > 2000:
        raise ValueError("问题过长")

    # 1) 合并服务端会话记忆与客户端历史，保留最近消息序列（多轮/语音共用）。
    clean_sid = _clean_session_id(session_id)
    sid = clean_sid or secrets.token_hex(12)
    client_history = _sanitize_history(history)
    stored_history = get_session_history(username, sid) if clean_sid else []
    merged_history = _merge_histories(stored_history, client_history)

    # 2) 用后端真实只读查询结果组装本轮上下文（资产统计、告警明细、设备明细等）。
    # 追问（“详细说说/它呢/这台”）沿用上一轮用户问题做检索，避免上下文断层。
    retrieval_question = question
    if _is_followup(question):
        previous_question = _last_user_question(merged_history)
        if previous_question and previous_question not in question:
            retrieval_question = f"{previous_question} {question}"
    data = _chat_query_context(
        db, retrieval_question, device_ids=device_ids,
        include_virtualization=include_virtualization,
    )
    context = _context_text(data)
    config = get_config(db)
    assistant_name = str(config.get("name") or "玄武")

    if config["enabled"] and config["has_key"]:
        messages = [{"role": "system", "content": _build_system_prompt(assistant_name, channel)}]
        messages.extend(_trim_for_model(merged_history))
        messages.append({
            "role": "user",
            "content": (
                "以下是平台后端实时只读查询结果（JSON，可能被截断；未出现的数据视为不可查询）：\n"
                f"{context}\n\n【本次用户问题】\n{question}"
            ),
        })
        try:
            reply = _call_model(config, messages)
            _persist_turn(username, sid, merged_history, question, reply)
            return {
                "reply": reply,
                "mode": "model",
                "model": config["model"],
                "session_id": sid,
                "history_used": len(merged_history),
                "context": data,
            }
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI 模型调用失败，回退本地统计: %s", exc)
            reply = _local_answer(question, data, merged_history, assistant_name)
            _persist_turn(username, sid, merged_history, question, reply)
            return {
                "reply": reply,
                "mode": "local",
                "model": config["model"],
                "model_error": str(exc)[:300],
                "session_id": sid,
                "history_used": len(merged_history),
                "context": data,
            }

    reply = _local_answer(question, data, merged_history, assistant_name)
    _persist_turn(username, sid, merged_history, question, reply)
    return {
        "reply": reply,
        "mode": "local",
        "session_id": sid,
        "history_used": len(merged_history),
        "context": data,
    }


def _report_markdown(db: Session, data: Dict[str, Any], topic: str, ai_text: str = "", assistant_name: str = "玄武") -> str:
    analysis = _alert_analysis(data)
    alerts = data["alerts"]
    modules = data.get("module_stats") or {}
    health = modules.get("health") or {}
    backups = modules.get("backups") or {}
    credentials = modules.get("credentials") or {}
    mib_cov = modules.get("mib_coverage") or {}
    topology = modules.get("topology") or {}
    rooms = modules.get("rooms") or {}
    website = modules.get("website") or {}
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    high = int((alerts.get("by_level") or {}).get("critical", 0)) + int((alerts.get("by_level") or {}).get("emergency", 0))
    risk_score = max(0, min(100, 100 - high * 8 - max(0, int(alerts.get("active", 0)) - high) * 2
                          - (10 if not backups.get("global_enabled") else 0)))
    risk_level = "高风险" if high >= 3 else "中风险" if alerts.get("active", 0) else "低风险"
    lines = [
        f"# {topic or '智能运维分析报告'}",
        "",
        f"**生成时间：** {now}　　**数据范围：** 当前账号可见资产与平台统计",
        f"**综合风险评分：** {risk_score}/100　　**风险等级：** {risk_level}",
        "",
        "## 一、执行摘要",
        f"- 纳管资产 {data['assets']['total']} 台，启用 {data['assets']['enabled']} 台，资产启用率 {health.get('asset_enabled_percent', 0)}%。",
        f"- 未恢复告警 {alerts['active']} 条，其中严重/紧急 {high} 条，未确认 {alerts['unacknowledged']} 条。",
        f"- MIB 绑定覆盖 {mib_cov.get('bound', 0)}/{mib_cov.get('devices', 0)} 台（{health.get('mib_coverage_percent', 0)}%），设备凭据覆盖 {credentials.get('configured', 0)}/{credentials.get('devices', 0)} 台。",
        f"- 配置备份：全局{'已开启' if backups.get('global_enabled') else '未开启'}，{backups.get('enabled_devices', 0)} 台设备开启自动备份，全局间隔 {backups.get('global_interval_hours', 24)} 小时。",
        "",
        "## 二、资产与采集健康",
        "| 指标 | 数值 | 说明 |",
        "| --- | --- | --- |",
        f"| 资产总数 / 启用 | {data['assets']['total']} / {data['assets']['enabled']} | 启用率 {health.get('asset_enabled_percent', 0)}% |",
        f"| 设备凭据覆盖 | {credentials.get('configured', 0)} / {credentials.get('devices', 0)} | 缺失 {credentials.get('missing', 0)} 台 |",
        f"| MIB/自定义指标覆盖 | {mib_cov.get('bound', 0)} / {mib_cov.get('devices', 0)} | 未绑定 {mib_cov.get('unbound', 0)} 台 |",
        f"| 自动备份覆盖 | {backups.get('enabled_devices', 0)} / {data['assets']['total']} | 全局{'开启' if backups.get('global_enabled') else '关闭'} |",
        "",
        "设备类型分布：" + ("、".join(f"{x['type']} {x['count']} 台" for x in data['assets'].get('by_type', [])) or "暂无数据") + "。",
        "",
        "## 三、告警态势",
        f"- 设备告警 {alerts.get('device_active', 0)} 条；网站告警 {alerts.get('website_active', 0)} 条；虚拟化告警 {alerts.get('virtual_active', 0)} 条。",
        "",
        "| 级别 | 数量 |",
        "| --- | --- |",
    ]
    for level, label in (("emergency", "紧急"), ("critical", "严重"), ("warning", "警告"), ("info", "提示")):
        lines.append(f"| {label} | {int((alerts.get('by_level') or {}).get(level, 0))} |")
    lines += ["", "### 告警类型 Top 10", "| 类型 | 数量 |", "| --- | --- |"]
    for item in (alerts.get("by_type") or [])[:10]:
        lines.append(f"| {item.get('label') or item.get('type')} | {item.get('count')} |")
    recent = (alerts.get("recent") or []) + (alerts.get("website_recent") or []) + (alerts.get("virtual_recent") or [])
    recent = sorted(recent, key=lambda x: str(x.get("created_at") or ""), reverse=True)[:12]
    lines += ["", "### 最近告警明细", "| 时间 | 级别 | 对象 | 类型 | 内容 |", "| --- | --- | --- | --- | --- |"]
    for item in recent:
        msg = str(item.get("message") or item.get("reason") or "").replace("|", "/")[:120]
        obj = str(item.get("device_name") or item.get("device_ip") or "-").replace("|", "/")
        lines.append(f"| {str(item.get('created_at') or '')[:19]} | {item.get('level_label') or item.get('level')} | {obj} | {item.get('type_label') or item.get('type')} | {msg} |")
    if not recent:
        lines.append("| - | - | - | - | 当前没有未恢复告警 |")
    lines += ["", "## 四、MIB 与指标覆盖", f"- MIB 文件 {data['mibs']['files']} 个，OID 对象 {data['mibs']['objects']} 个。",
              f"- 已绑定 MIB/自定义指标设备 {mib_cov.get('bound', 0)} 台，未绑定 {mib_cov.get('unbound', 0)} 台。"]
    cats = data["mibs"].get("categories") or []
    lines.append("- 主要指标分类：" + ("、".join(f"{x['category']}({x['count']})" for x in cats[:12]) if cats else "暂未识别分类"))
    lines += ["", "## 五、虚拟化资源",
              f"- 平台 {data['virtualization']['platforms']} 个，宿主机 {data['virtualization']['hosts']} 台，虚拟机/容器 {data['virtualization']['vms']} 个，活动告警 {data['virtualization']['alerts']} 条。",
              "", "## 六、网站与证书",
              f"- 网站监控 {website.get('targets', 0)} 个，活动告警 {website.get('active_alerts', 0)} 条；证书 {website.get('certificates', 0)} 个，异常/即将到期 {website.get('certificate_issues', 0)} 个。",
              "", "## 七、拓扑、机房与容量",
              f"- 拓扑节点 {topology.get('devices', 0)} 个，链路 {topology.get('links', 0)} 条，孤立设备 {topology.get('isolated', 0)} 台。",
              f"- 机房 {rooms.get('rooms', 0)} 个，机柜 {rooms.get('cabinets', 0)} 个，U 位使用 {rooms.get('used_u', 0)}/{rooms.get('total_u', 0)}（{rooms.get('u_usage_percent', 0)}%），机柜额定功率合计 {rooms.get('power_capacity_w', 0)} W。",
              "", "## 八、备份与巡检",
              f"- 配置备份：全局{'开启' if backups.get('global_enabled') else '关闭'}，{backups.get('enabled_devices', 0)} 台设备开启，最近失败记录 {backups.get('failed', 0)} 条。",
              f"- 巡检任务 {data['inspection']['tasks']} 个，巡检报告 {data['inspection']['reports']} 份。",
              "", "## 九、风险清单"]
    risks = []
    if high:
        risks.append((f"存在 {high} 条严重/紧急告警，可能影响业务连续性", "P0", "立即按告警明细逐台定位并恢复"))
    if alerts.get("active", 0):
        risks.append((f"仍有 {alerts.get('active', 0)} 条未恢复告警", "P1", "按严重级别和设备影响范围排期处理"))
    if not backups.get("global_enabled"):
        risks.append(("全局自动备份未开启，配置变更后缺少可回滚基线", "P1", "在「自动备份设置」开启全局备份并校准间隔"))
    if credentials.get("missing", 0):
        risks.append((f"{credentials.get('missing', 0)} 台设备缺少统一凭据，影响备份和巡检", "P1", "补充设备凭据或 SSH 参数"))
    if mib_cov.get("unbound", 0):
        risks.append((f"{mib_cov.get('unbound', 0)} 台设备未绑定 MIB 或自定义指标，采集覆盖不完整", "P2", "使用 MIB 智能匹配逐台补全"))
    if website.get("certificate_issues", 0):
        risks.append((f"{website.get('certificate_issues', 0)} 个证书异常或即将到期", "P1", "检查证书有效期并续签/替换"))
    if rooms.get("u_usage_percent", 0) >= 85:
        risks.append(("机柜 U 位使用率超过 85%，扩容空间不足", "P2", "规划新机柜或迁移低密度设备"))
    if topology.get("isolated", 0):
        risks.append((f"{topology.get('isolated', 0)} 台设备在拓扑中孤立，链路关系可能缺失", "P2", "补充拓扑连接关系"))
    if not risks:
        lines.append("- 当前未发现需要立即处理的高风险项。")
    else:
        lines += ["| 风险 | 优先级 | 建议 |", "| --- | --- | --- |"]
        for risk, priority, suggestion in risks:
            lines.append(f"| {risk} | {priority} | {suggestion} |")
    lines += ["", "### 重点待补全设备", "| 类别 | 设备 |", "| --- | --- |"]
    for name in (mib_cov.get("unbound_names") or [])[:10]:
        lines.append(f"| MIB 未绑定 | {name} |")
    for name in (credentials.get("missing_names") or [])[:10]:
        lines.append(f"| 凭据缺失 | {name} |")
    for name in (backups.get("disabled_names") or [])[:10]:
        lines.append(f"| 自动备份未开启 | {name} |")
    for name in (topology.get("isolated_names") or [])[:10]:
        lines.append(f"| 拓扑孤立 | {name} |")
    lines += ["", "## 十、处置建议"]
    if analysis["suggestions"]:
        for index, item in enumerate(analysis["suggestions"][:8], 1):
            lines.append(f"{index}. {item['suggestion']}")
    else:
        lines.append("1. 保持告警渠道、采集任务和备份任务可用，按周复核高风险设备。")
    lines.append("2. 对严重/紧急告警建立处置闭环，记录根因、恢复时间和后续预防措施。")
    lines.append("3. 对未绑定 MIB、缺少凭据和未开启备份的设备制定批量补全计划。")
    if ai_text:
        lines += ["", "## 十一、AI 深度分析", ai_text.strip()[:16000]]
    lines += ["", "---", f"本报告由{str(assistant_name or 'AI').strip() or 'AI'} AI 智能运维根据平台实时只读数据生成；涉及设备写操作需人工确认。"]
    return "\n".join(lines)

def generate_report(
    db: Session,
    topic: str = "",
    username: str = "",
    device_ids: Optional[List[int]] = None,
    include_virtualization: bool = True,
) -> Dict[str, Any]:
    data = overview(db, device_ids=device_ids, include_virtualization=include_virtualization)
    data["alert_analysis"] = _alert_analysis(data)
    config = get_config(db)
    ai_text = ""
    mode = "local"
    if config["enabled"] and config["has_key"]:
        prompt = (
            "请根据以下只读统计生成一份专业、详细的中文运维分析报告。至少覆盖：执行摘要、"
            "资产与采集健康、告警态势与根因、MIB 覆盖、虚拟化、网站证书、拓扑机房、备份巡检、"
            "风险分级、P0/P1/P2 处置计划和后续改进。引用具体数字，禁止编造未提供的数据。\n"
            f"统计：{_context_text(data)}"
        )
        try:
            report_config = dict(config)
            report_config["max_tokens"] = max(1800, int(config.get("max_tokens") or 1200))
            ai_text = _call_model(report_config, [
                {"role": "system", "content": _build_system_prompt(config.get("name") or "玄武")},
                {"role": "user", "content": prompt},
            ], timeout=120)
            ai_text = re.sub(r"<think[^>]*>.*?</think\s*>", "", ai_text, flags=re.I | re.S).strip()
            mode = "model"
        except Exception as exc:  # noqa: BLE001
            logger.warning("AI 报告模型调用失败，使用本地模板: %s", exc)
            ai_text = ""
    title = (topic or "智能运维分析报告").strip()[:300]
    markdown = _report_markdown(db, data, title, ai_text, str(config.get("name") or "玄武"))
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"ai-report-{datetime.now().strftime('%Y%m%d-%H%M%S')}.docx"
    path = REPORT_DIR / filename
    try:
        from docx import Document
        document = Document()
        document.styles["Normal"].font.name = "Microsoft YaHei"
        lines = markdown.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            # Markdown 表格转 Word 表格，避免报告里出现一排竖线。
            if line.strip().startswith("|") and i + 1 < len(lines) and set(lines[i + 1].strip()) <= set("|-: "):
                header = [cell.strip() for cell in line.strip().strip("|").split("|")]
                rows = []
                i += 2
                while i < len(lines) and lines[i].strip().startswith("|"):
                    rows.append([cell.strip() for cell in lines[i].strip().strip("|").split("|")])
                    i += 1
                table = document.add_table(rows=1, cols=max(1, len(header)))
                table.style = "Table Grid"
                for index, text in enumerate(header):
                    table.rows[0].cells[index].text = text
                for row in rows:
                    cells = table.add_row().cells
                    for index, text in enumerate(row[:len(cells)]):
                        cells[index].text = text
                document.add_paragraph("")
                continue
            if line.startswith("# "):
                document.add_heading(line[2:], level=0)
            elif line.startswith("## "):
                document.add_heading(line[3:], level=1)
            elif line.startswith("### "):
                document.add_heading(line[4:], level=2)
            elif line.startswith("- "):
                document.add_paragraph(line[2:], style="List Bullet")
            elif line.strip() == "---":
                document.add_paragraph("—" * 24)
            elif line.strip():
                document.add_paragraph(line)
            i += 1
        document.save(str(path))
    except Exception:  # noqa: BLE001
        filename = filename.rsplit(".", 1)[0] + ".md"
        path = REPORT_DIR / filename
        path.write_text(markdown, encoding="utf-8")
    report = AiOpsReport(
        title=title, filename=filename, content=markdown,
        model=config["model"] if mode == "model" else "本地统计",
        mode=mode, created_by=(username or "")[:100],
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return {
        "id": report.id,
        "title": report.title,
        "filename": filename,
        "content": markdown,
        "mode": mode,
        "download_url": f"/api/ai/reports/{report.id}/download",
        "created_at": report.created_at.isoformat() if report.created_at else None,
    }


def list_reports(db: Session, limit: int = 20, username: Optional[str] = None) -> List[Dict[str, Any]]:
    query = db.query(AiOpsReport)
    if username:
        query = query.filter(AiOpsReport.created_by == username)
    rows = query.order_by(AiOpsReport.created_at.desc(), AiOpsReport.id.desc()).limit(max(1, min(100, limit))).all()
    return [{
        "id": row.id, "title": row.title, "filename": row.filename,
        "model": row.model, "mode": row.mode, "created_by": row.created_by,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "download_url": f"/api/ai/reports/{row.id}/download",
    } for row in rows]


def report_path(filename: str) -> Path:
    path = (REPORT_DIR / Path(filename).name).resolve()
    root = REPORT_DIR.resolve()
    if root not in path.parents and path != root:
        raise FileNotFoundError("报告路径不合法")
    if not path.is_file():
        raise FileNotFoundError("报告文件不存在")
    return path
