"""维保到期告警。

规则：
- 距维保到期 5 天（含）内、但超过 3 天：warning（警告）
- 距维保到期 3 天（含）内，含已过期：critical（严重）
- 距到期超过 5 天或维保日期被清空/改远：自动恢复原维保告警
同一设备同一时间只保留一条未恢复的 warranty 告警，进入严重阶段时升级原告警。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

from sqlalchemy.orm import Session

from ..models.models import Alert, Device
from ..models.room import Cabinet, Room
from .alert_recovery import build_generic_recovery_payload

WARRANTY_WARNING_DAYS = 5
WARRANTY_CRITICAL_DAYS = 3


def _days_left(device: Device) -> Optional[int]:
    raw = str(getattr(device, "warranty_until", "") or "").strip()
    if not raw:
        return None
    try:
        expire = datetime.strptime(raw[:10], "%Y-%m-%d").date()
    except ValueError:
        return None
    return (expire - datetime.utcnow().date()).days


def _warranty_message(device: Device, days_left: int) -> str:
    date_text = str(device.warranty_until or "")[:10]
    if days_left < 0:
        return f"维保已于 {date_text} 到期，已过期 {abs(days_left)} 天"
    return f"维保将于 {date_text} 到期，剩余 {days_left} 天"


def _location_context(db: Session, device: Device) -> Dict[str, Any]:
    cabinet = db.query(Cabinet).filter(Cabinet.id == device.cabinet_id).first() if device.cabinet_id else None
    room = db.query(Room).filter(Room.id == cabinet.room_id).first() if cabinet else None
    return {
        "room_name": room.name if room else "",
        "cabinet_name": cabinet.name if cabinet else "",
        "room_floor": room.floor if room else "",
        "room_location": room.location if room else "",
    }


def check_warranty_alerts(
    db: Session,
    device_ids: Optional[Iterable[int]] = None,
) -> List[Dict[str, Any]]:
    """扫描维保日期并创建/升级/恢复告警，返回需要通知的新告警 payload。"""
    query = db.query(Device).filter(Device.warranty_until.isnot(None))
    ids = [int(item) for item in (device_ids or []) if item]
    if ids:
        query = query.filter(Device.id.in_(ids))
    devices = query.all()
    if not devices:
        return []

    notifications: List[Dict[str, Any]] = []
    for device in devices:
        active = (
            db.query(Alert)
            .filter(
                Alert.device_id == device.id,
                Alert.alert_type == "warranty",
                Alert.resolved_at.is_(None),
            )
            .order_by(Alert.created_at.desc())
            .all()
        )
        days_left = _days_left(device)
        if days_left is None or days_left > WARRANTY_WARNING_DAYS:
            for alert in active:
                recovered_at = datetime.utcnow()
                alert.resolved_at = recovered_at
                alert.resolution = "warranty_no_longer_expiring"
                notifications.append(build_generic_recovery_payload(
                    source="device",
                    alert_id=alert.id,
                    name=device.name,
                    ip_address=device.ip_address,
                    alert_type="warranty",
                    message=alert.message,
                    level=alert.alert_level,
                    value=days_left,
                    threshold=alert.threshold,
                    recovered_at=recovered_at,
                    original_created_at=alert.created_at,
                    extra=_location_context(db, device),
                ))
            continue

        is_critical = days_left <= WARRANTY_CRITICAL_DAYS
        level = "critical" if is_critical else "warning"
        threshold = WARRANTY_CRITICAL_DAYS if is_critical else WARRANTY_WARNING_DAYS
        message = _warranty_message(device, days_left)
        alert = active[0] if active else None
        if alert:
            # 清理历史重复的未恢复维保告警
            for extra in active[1:]:
                extra.resolved_at = datetime.utcnow()
                extra.resolution = "warranty_duplicate"
            upgraded = alert.alert_level != level
            alert.alert_level = level
            alert.value = float(days_left)
            alert.threshold = float(threshold)
            alert.message = message
            if upgraded:
                alert.is_acknowledged = False
            if upgraded:
                notifications.append({
                    **_location_context(db, device),
                    "source": "device",
                    "source_id": alert.id,
                    "level": level,
                    "device_name": device.name,
                    "ip_address": device.ip_address,
                    "alert_type": "warranty",
                    "message": message,
                    "value": days_left,
                    "threshold": threshold,
                    "created_at": datetime.utcnow().isoformat(timespec="seconds"),
                })
        else:
            alert = Alert(
                device_id=device.id,
                alert_type="warranty",
                alert_level=level,
                message=message,
                value=float(days_left),
                threshold=float(threshold),
                created_at=datetime.utcnow(),
            )
            db.add(alert)
            db.flush()
            notifications.append({
                **_location_context(db, device),
                "source": "device",
                "source_id": alert.id,
                "level": level,
                "device_name": device.name,
                "ip_address": device.ip_address,
                "alert_type": "warranty",
                "message": message,
                "value": days_left,
                "threshold": threshold,
                "created_at": datetime.utcnow().isoformat(timespec="seconds"),
            })

    db.commit()
    return notifications
