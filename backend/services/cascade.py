"""总部/分支级联：数据快照、节点登记、隧道会话加密和级联消息。"""
from __future__ import annotations

import base64
import hashlib
import json
import secrets
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.cascade import CascadeMessage, CascadeNode
from ..models.inspection import InspectionReport, InspectionTask
from ..models.models import Alert, Device, DeviceMetric
from ..models.virtualization import VirtualHost, VirtualMachine, VirtualPlatform, VirtualizationAlert
from ..models.website import WebsiteTarget
from ..services import settings as settings_service
from ..services.virtualization_crypto import decrypt_password, encrypt_password

LEVEL_LABELS = {"info": "提示", "warning": "警告", "critical": "严重", "emergency": "紧急"}
ALERT_TYPE_TEXT = {
    "cpu": "CPU 使用率", "memory": "内存使用率", "temperature": "温度",
    "power": "电源状态", "offline": "设备离线", "warranty": "维保到期",
    "vm_cpu": "虚拟机 CPU", "vm_memory": "虚拟机内存", "vm_disk": "虚拟机磁盘",
    "vm_shutdown": "虚拟机关机",
}
SNAPSHOT_VERSION = 1


def token_hash(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _fernet(token: str) -> Fernet:
    key = base64.urlsafe_b64encode(hashlib.sha256(str(token or "").encode("utf-8")).digest())
    return Fernet(key)


def encrypt_frame(token: str, payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), default=str).encode("utf-8")
    return _fernet(token).encrypt(raw).decode("ascii")


def decrypt_frame(token: str, frame: str) -> Dict[str, Any]:
    try:
        raw = _fernet(token).decrypt(str(frame or "").encode("ascii"))
        data = json.loads(raw.decode("utf-8"))
    except (InvalidToken, ValueError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError("级联隧道数据解密失败") from exc
    if not isinstance(data, dict):
        raise ValueError("级联隧道数据格式不正确")
    return data


def get_config(db: Session) -> Dict[str, Any]:
    values = settings_service.get_all(db)
    token = ""
    if values.get("cascade_token_enc"):
        try:
            token = decrypt_password(values["cascade_token_enc"])
        except ValueError:
            token = ""
    return {
        "enabled": bool(values.get("cascade_enabled")),
        "role": str(values.get("cascade_role") or "standalone"),
        "node_name": str(values.get("cascade_node_name") or ""),
        "hq_url": str(values.get("cascade_hq_url") or ""),
        "token": token,
        "has_token": bool(token),
        "sync_interval": max(30, min(3600, int(values.get("cascade_sync_interval") or 60))),
        "verify_tls": bool(values.get("cascade_verify_tls", True)),
        "tunnel_port": max(1, int(values.get("cascade_tunnel_port") or 9527)),
    }


def public_config(config: Dict[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in config.items() if key != "token"}


def save_config(db: Session, payload: Dict[str, Any]) -> Dict[str, Any]:
    values: Dict[str, Any] = {}
    if "enabled" in payload:
        values["cascade_enabled"] = bool(payload["enabled"])
    if "role" in payload:
        role = str(payload["role"] or "standalone")
        if role not in ("standalone", "hq", "branch"):
            raise ValueError("级联角色只支持 standalone / hq / branch")
        values["cascade_role"] = role
    if "node_name" in payload:
        values["cascade_node_name"] = str(payload["node_name"] or "").strip()[:160]
    if "hq_url" in payload:
        values["cascade_hq_url"] = str(payload["hq_url"] or "").strip()[:1000]
    if "sync_interval" in payload:
        values["cascade_sync_interval"] = max(30, min(3600, int(payload["sync_interval"] or 60)))
    if "verify_tls" in payload:
        values["cascade_verify_tls"] = bool(payload["verify_tls"])
    if "tunnel_port" in payload:
        try:
            port = int(payload["tunnel_port"])
        except (TypeError, ValueError):
            raise ValueError("级联隧道端口必须是整数") from None
        if not 1 <= port <= 65535:
            raise ValueError("级联隧道端口必须在 1~65535 之间")
        values["cascade_tunnel_port"] = port
    if payload.get("clear_token"):
        values["cascade_token_enc"] = ""
    elif str(payload.get("token") or "").strip():
        values["cascade_token_enc"] = encrypt_password(str(payload["token"]).strip())
    if values:
        settings_service.save(db, values)
    return public_config(get_config(db))


def create_node(db: Session, name: str) -> Dict[str, Any]:
    name = str(name or "").strip()[:160]
    if not name:
        raise ValueError("请填写分支名称")
    token = secrets.token_urlsafe(32)
    node = CascadeNode(
        node_key=secrets.token_hex(8),
        name=name,
        token_hash=token_hash(token),
        token_enc=encrypt_password(token),
        status="offline",
    )
    db.add(node)
    db.flush()
    return {"id": node.id, "node_key": node.node_key, "name": node.name, "token": token}


def authenticate_node(db: Session, token: str) -> Optional[CascadeNode]:
    if not token:
        return None
    return db.query(CascadeNode).filter(CascadeNode.token_hash == token_hash(token)).first()


def node_token(node: CascadeNode) -> str:
    if not node or not node.token_enc:
        return ""
    try:
        return decrypt_password(node.token_enc)
    except ValueError:
        return ""


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def node_online(node: CascadeNode) -> bool:
    if not node.last_seen:
        return False
    return (datetime.utcnow() - node.last_seen).total_seconds() <= 120


def node_dict(node: CascadeNode) -> Dict[str, Any]:
    snapshot = node.snapshot if isinstance(node.snapshot, dict) else {}
    stats = snapshot.get("stats") if isinstance(snapshot.get("stats"), dict) else {}
    return {
        "id": node.id,
        "node_key": node.node_key,
        "name": node.name,
        "address": node.address or "",
        "version": node.version or "",
        "status": "online" if node_online(node) else "offline",
        "online": node_online(node),
        "last_seen": _iso(node.last_seen),
        "last_sync": _iso(node.last_sync),
        "snapshot_updated_at": _iso(node.snapshot_updated_at),
        "stats": stats,
        "created_at": _iso(node.created_at),
    }


def _device_rows(db: Session, limit: int = 5000) -> List[Dict[str, Any]]:
    latest_ids = (
        db.query(func.max(DeviceMetric.id))
        .group_by(DeviceMetric.device_id)
        .subquery()
    )
    rows = (
        db.query(Device, DeviceMetric)
        .outerjoin(DeviceMetric, DeviceMetric.id.in_(latest_ids.select()))
        .order_by(Device.id.asc())
        .limit(limit)
        .all()
    )
    result = []
    for device, metric in rows:
        result.append({
            "id": device.id,
            "name": device.name,
            "ip_address": device.ip_address,
            "device_type": device.device_type,
            "vendor": device.vendor or "",
            "model": device.model or "",
            "location": device.location or "",
            "group_id": device.group_id,
            "enabled": bool(device.is_enabled),
            "status": "online" if (metric and metric.collected_at and (datetime.utcnow() - metric.collected_at).total_seconds() < 600) else "unknown",
            "cpu_usage": metric.cpu_usage if metric else None,
            "memory_usage": metric.memory_usage if metric else None,
            "temperature": metric.temperature if metric else None,
            "disk_usage": metric.disk_usage if metric else None,
            "power_status": metric.power_status if metric else None,
            "collected_at": _iso(metric.collected_at if metric else None),
        })
    return result


def _alert_rows(db: Session, limit: int = 2000) -> List[Dict[str, Any]]:
    rows = (
        db.query(Alert, Device)
        .outerjoin(Device, Alert.device_id == Device.id)
        .filter(Alert.resolved_at.is_(None))
        .order_by(Alert.created_at.desc())
        .limit(limit)
        .all()
    )
    return [{
        "id": alert.id,
        "device_name": device.name if device else f"设备#{alert.device_id}",
        "device_ip": device.ip_address if device else "",
        "level": alert.alert_level,
        "level_label": alert.level_label or LEVEL_LABELS.get(alert.alert_level, alert.alert_level),
        "type": alert.alert_type,
        "type_label": ALERT_TYPE_TEXT.get(alert.alert_type, alert.alert_type),
        "message": alert.message or "",
        "value": alert.value,
        "threshold": alert.threshold,
        "created_at": _iso(alert.created_at),
    } for alert, device in rows]


def build_snapshot(db: Session) -> Dict[str, Any]:
    devices = _device_rows(db)
    alerts = _alert_rows(db)
    websites = [
        {"id": target.id, "name": target.name, "url": target.url, "enabled": bool(target.is_enabled)}
        for target in db.query(WebsiteTarget).order_by(WebsiteTarget.id.asc()).limit(500).all()
    ]
    virtual_platforms = db.query(VirtualPlatform).count()
    virtual_hosts = db.query(VirtualHost).count()
    virtual_vms = db.query(VirtualMachine).count()
    virtual_alerts = db.query(VirtualizationAlert).filter(
        VirtualizationAlert.resolved_at.is_(None),
        VirtualizationAlert.is_acknowledged.is_(False),
    ).count()
    inspection_tasks = db.query(InspectionTask).count()
    inspection_reports = db.query(InspectionReport).count()
    try:
        from .version_info import get_version_info
        version = get_version_info(db).get("effective", {}).get("display_version", "")
    except Exception:  # noqa: BLE001
        version = ""
    return {
        "schema": SNAPSHOT_VERSION,
        "generated_at": _iso(datetime.utcnow()),
        "version": version,
        "assets": devices,
        "alerts": alerts,
        "websites": websites,
        "virtualization": {
            "platforms": virtual_platforms,
            "hosts": virtual_hosts,
            "vms": virtual_vms,
            "alerts": virtual_alerts,
        },
        "inspection": {"tasks": inspection_tasks, "reports": inspection_reports},
        "stats": {
            "assets": len(devices),
            "alerts": len(alerts),
            "websites": len(websites),
            "virtual_platforms": virtual_platforms,
            "virtual_vms": virtual_vms,
            "inspection_reports": inspection_reports,
        },
    }


def record_snapshot(db: Session, node: CascadeNode, snapshot: Dict[str, Any]) -> None:
    if not isinstance(snapshot, dict):
        return
    # 防止恶意/异常分支用超大 JSON 撑爆总部数据库
    encoded = json.dumps(snapshot, ensure_ascii=False, default=str)
    if len(encoded.encode("utf-8")) > 12 * 1024 * 1024:
        raise ValueError("分支快照超过 12MB 限制")
    now = datetime.utcnow()
    node.snapshot = snapshot
    node.snapshot_updated_at = now
    node.last_sync = now
    node.status = "online"
    node.last_seen = now
    db.commit()


def touch_node(db: Session, node: CascadeNode, name: str = "", version: str = "", address: str = "") -> None:
    node.last_seen = datetime.utcnow()
    node.status = "online"
    if name:
        node.name = str(name)[:160]
    if version:
        node.version = str(version)[:80]
    if address:
        node.address = str(address)[:255]
    db.commit()


def list_messages(db: Session, node_key: str = "", limit: int = 100) -> List[Dict[str, Any]]:
    query = db.query(CascadeMessage)
    if node_key:
        query = query.filter(CascadeMessage.node_key == node_key)
    rows = query.order_by(CascadeMessage.created_at.desc(), CascadeMessage.id.desc()).limit(max(1, min(200, limit))).all()
    rows.reverse()
    return [{
        "id": row.id, "node_key": row.node_key, "sender": row.sender,
        "direction": row.direction, "content": row.content,
        "delivered": bool(row.delivered), "created_at": _iso(row.created_at),
    } for row in rows]


def add_message(db: Session, node_key: str, sender: str, content: str, direction: str, delivered: bool = False) -> CascadeMessage:
    content = str(content or "").strip()
    if not content:
        raise ValueError("消息内容不能为空")
    if len(content) > 4000:
        raise ValueError("消息不能超过 4000 个字符")
    row = CascadeMessage(
        node_key=node_key[:80], sender=str(sender or "")[:160],
        content=content, direction=direction, delivered=delivered,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def status(db: Session) -> Dict[str, Any]:
    config = get_config(db)
    nodes = db.query(CascadeNode).order_by(CascadeNode.last_seen.desc(), CascadeNode.id.asc()).all()
    serialized = [node_dict(node) for node in nodes]
    online = [node for node in serialized if node["online"]]
    assets = sum(int(node.get("stats", {}).get("assets") or 0) for node in serialized)
    alerts = sum(int(node.get("stats", {}).get("alerts") or 0) for node in serialized)
    return {
        "config": public_config(config),
        "summary": {
            "role": config["role"],
            "total": len(serialized),
            "online": len(online),
            "offline": len(serialized) - len(online),
            "assets": assets,
            "alerts": alerts,
        },
        "nodes": serialized,
    }


def cleanup_old_messages(db: Session, days: int = 30) -> int:
    cutoff = datetime.utcnow() - timedelta(days=max(1, days))
    return db.query(CascadeMessage).filter(CascadeMessage.created_at < cutoff).delete(synchronize_session=False)
