"""上级平台告警汇聚服务。

下级节点使用 notification channel_type=upstream 调用本文件的 ingest 逻辑；
上级节点只使用本机的邮件/Webhook/短信通道外发，不再转发给另一个上级，
避免多级配置形成告警回环。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models.notifications import NotificationChannel
from ..models.upstream import UpstreamReceivedAlert
from ..notify import dispatcher
from . import settings as settings_service

logger = logging.getLogger(__name__)
TOKEN_KEY = "upstream_ingest_token"
PROTOCOL = "snmp-monitor-alert-v1"
MAX_TEXT = 8000


def get_token(db: Session) -> str:
    return str(settings_service.get_value(db, TOKEN_KEY) or "").strip()


def generate_token(db: Session) -> str:
    token = "nmsup_" + secrets.token_urlsafe(32)
    settings_service.save(db, {TOKEN_KEY: token})
    return token


def token_matches(db: Session, supplied: str) -> bool:
    expected = get_token(db)
    if not expected or not supplied:
        return False
    return hmac.compare_digest(expected, supplied)


def _fallback_event_id(payload: Dict[str, Any]) -> str:
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)[:20000]
    return "evt-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()


def _clip(value: Any, limit: int = MAX_TEXT) -> str:
    return str(value or "")[:limit]


async def ingest(db: Session, payload: Dict[str, Any], remote_ip: str = "") -> Dict[str, Any]:
    """接收下级告警并交给本机非 upstream 通道外发。"""
    protocol = str(payload.get("protocol") or "").strip()
    if protocol != PROTOCOL:
        raise ValueError("不支持的上级平台协议，仅支持本系统 snmp-monitor-alert-v1")
    event_id = _clip(payload.get("event_id"), 120).strip() or _fallback_event_id(payload)
    existing = db.query(UpstreamReceivedAlert).filter(
        UpstreamReceivedAlert.event_id == event_id
    ).first()
    if existing:
        return {
            "ok": True, "duplicate": True, "event_id": event_id,
            "forwarded": 0, "status": existing.status,
        }

    node_id = _clip(payload.get("source_node_id"), 120).strip()
    node_name = _clip(payload.get("source_node_name"), 200).strip()
    if not node_id or not node_name:
        raise ValueError("缺少来源节点标识或来源节点名称")
    is_test = bool(payload.get("test"))
    level = _clip(payload.get("level"), 20) or "warning"
    alert_type = _clip(payload.get("alert_type"), 50) or "alert"
    device_name = _clip(payload.get("device_name") or payload.get("ip_address"), 300)
    message = _clip(payload.get("message") or payload.get("text"), MAX_TEXT)

    record = UpstreamReceivedAlert(
        event_id=event_id,
        source_node_id=node_id,
        source_node_name=node_name,
        source_instance=_clip(payload.get("source_instance"), 120),
        source_ip=_clip(remote_ip, 64),
        origin_source=_clip(payload.get("origin_source") or payload.get("source"), 20),
        level=level,
        alert_type=alert_type,
        title=_clip(payload.get("title") or message, 300),
        message=message,
        payload=payload,
        status="testing" if is_test else "receiving",
        received_at=datetime.utcnow(),
    )
    db.add(record)
    try:
        db.commit()
        db.refresh(record)
    except IntegrityError:
        db.rollback()
        existing = db.query(UpstreamReceivedAlert).filter(
            UpstreamReceivedAlert.event_id == event_id
        ).first()
        return {
            "ok": True, "duplicate": True, "event_id": event_id,
            "forwarded": 0, "status": existing.status if existing else "received",
        }

    if is_test:
        record.status = "test_ok"
        record.forwarded_count = 0
        db.commit()
        return {"ok": True, "test": True, "event_id": event_id, "forwarded": 0, "status": "test_ok"}

    dispatch_payload = {
        "source": "upstream",
        "source_id": None,
        "event_id": event_id,
        "source_node_id": node_id,
        "source_node_name": node_name,
        "source_instance": payload.get("source_instance") or "",
        "source_url": payload.get("source_url") or "",
        "origin_source": payload.get("origin_source") or payload.get("source") or "device",
        "level": level,
        "alert_type": alert_type,
        "device_name": device_name,
        "ip_address": _clip(payload.get("ip_address"), 100),
        "value": payload.get("value"),
        "threshold": payload.get("threshold"),
        "message": message,
        "created_at": payload.get("created_at"),
        "recovery": bool(payload.get("recovery")),
    }
    try:
        results = await dispatcher.dispatch(
            dispatch_payload, exclude_channel_types={"upstream"}
        )
        forwarded = sum(1 for item in results if item.get("status") == "success")
        failures = [item for item in results if item.get("status") != "success"]
        record.forwarded_count = forwarded
        record.status = "forwarded" if forwarded else "received"
        record.error = (
            "; ".join(f"{item.get('channel')}: {item.get('error')}" for item in failures)[:3000]
            if failures else ""
        )
        db.commit()
        return {
            "ok": True, "duplicate": False, "event_id": event_id,
            "forwarded": forwarded, "status": record.status,
        }
    except Exception as exc:  # noqa: BLE001
        record.status = "failed"
        record.error = str(exc)[:3000]
        db.commit()
        logger.exception("上级平台告警外发失败 event=%s", event_id)
        return {
            "ok": True, "duplicate": False, "event_id": event_id,
            "forwarded": 0, "status": "failed", "detail": str(exc)[:500],
        }


def settings_info(db: Session) -> Dict[str, Any]:
    token = get_token(db)
    total = db.query(UpstreamReceivedAlert).count()
    last = (
        db.query(UpstreamReceivedAlert)
        .order_by(UpstreamReceivedAlert.received_at.desc(), UpstreamReceivedAlert.id.desc())
        .first()
    )
    channels = (
        db.query(NotificationChannel)
        .filter(
            NotificationChannel.channel_type != "upstream",
            NotificationChannel.enabled == True,  # noqa: E712
        )
        .count()
    )
    return {
        "token": token,
        "configured": bool(token),
        "endpoint": "/api/notifications/upstream/ingest",
        "protocol": PROTOCOL,
        "local_channel_count": channels,
        "received_count": total,
        "last_received_at": last.received_at.isoformat() if last and last.received_at else None,
        "last_source_node": last.source_node_name if last else "",
    }


def recent_received(db: Session, limit: int = 20) -> list[Dict[str, Any]]:
    rows = (
        db.query(UpstreamReceivedAlert)
        .order_by(UpstreamReceivedAlert.received_at.desc(), UpstreamReceivedAlert.id.desc())
        .limit(max(1, min(100, limit)))
        .all()
    )
    return [
        {
            "id": row.id,
            "event_id": row.event_id,
            "source_node_id": row.source_node_id,
            "source_node_name": row.source_node_name,
            "origin_source": row.origin_source,
            "level": row.level,
            "alert_type": row.alert_type,
            "title": row.title,
            "message": row.message,
            "forwarded_count": row.forwarded_count,
            "status": row.status,
            "error": row.error,
            "received_at": row.received_at.isoformat() if row.received_at else None,
        }
        for row in rows
    ]
