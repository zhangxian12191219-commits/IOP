"""告警抑制规则匹配与序列化。"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from ..models.models import AlertSuppression


def suppression_status(rule: AlertSuppression, now: Optional[datetime] = None) -> str:
    current = now or datetime.utcnow()
    if not rule.is_enabled:
        return "disabled"
    if rule.starts_at and rule.starts_at > current:
        return "scheduled"
    if rule.ends_at and rule.ends_at <= current:
        return "expired"
    return "active"


def suppression_to_dict(rule: AlertSuppression, device_name: str = "", target_name: str = "") -> dict:
    status = suppression_status(rule)
    if rule.source == "website":
        target_label = target_name or (f"网站 #{rule.website_target_id}" if rule.website_target_id else "全部网站")
    elif rule.source == "device":
        target_label = device_name or (f"设备 #{rule.device_id}" if rule.device_id else "全部设备")
    else:
        target_label = "全部来源"
    return {
        "id": rule.id,
        "source": rule.source or "device",
        "device_id": rule.device_id,
        "website_target_id": rule.website_target_id,
        "alert_type": rule.alert_type or "",
        "alert_level": rule.alert_level or "",
        "reason": rule.reason or "",
        "starts_at": rule.starts_at.isoformat() if rule.starts_at else None,
        "ends_at": rule.ends_at.isoformat() if rule.ends_at else None,
        "is_enabled": bool(rule.is_enabled),
        "status": status,
        "target_label": target_label,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
    }


def is_suppressed(
    db: Session,
    source: str,
    device_id: Optional[int] = None,
    website_target_id: Optional[int] = None,
    alert_type: Optional[str] = None,
    alert_level: Optional[str] = None,
) -> Optional[AlertSuppression]:
    """返回命中的生效抑制规则；未命中返回 None。"""
    now = datetime.utcnow()
    rules = db.query(AlertSuppression).filter(AlertSuppression.is_enabled == True).all()  # noqa: E712
    for rule in rules:
        if suppression_status(rule, now) != "active":
            continue
        rule_source = rule.source or "device"
        if rule_source not in ("all", source):
            continue
        if rule_source == "device" and rule.device_id is not None and rule.device_id != device_id:
            continue
        if rule_source == "website" and rule.website_target_id is not None and rule.website_target_id != website_target_id:
            continue
        if rule.alert_type and alert_type and rule.alert_type != alert_type:
            continue
        if rule.alert_level and alert_level and rule.alert_level != alert_level:
            continue
        return rule
    return None


def acknowledge_matching(
    db: Session,
    *,
    source: str,
    device_id: Optional[int] = None,
    website_target_id: Optional[int] = None,
    alert_type: Optional[str] = None,
    alert_level: Optional[str] = None,
) -> int:
    """确认当前匹配的未确认告警，返回影响条数。"""
    from ..models.models import Alert
    from ..models.website import WebsiteAlert

    count = 0
    if source in ("device", "all"):
        query = db.query(Alert).filter(Alert.is_acknowledged == False)  # noqa: E712
        if device_id is not None:
            query = query.filter(Alert.device_id == device_id)
        if alert_type:
            query = query.filter(Alert.alert_type == alert_type)
        if alert_level:
            query = query.filter(Alert.alert_level == alert_level)
        count += query.update({Alert.is_acknowledged: True}, synchronize_session=False)
    if source in ("website", "all"):
        query = db.query(WebsiteAlert).filter(WebsiteAlert.is_acknowledged == False)  # noqa: E712
        if website_target_id is not None:
            query = query.filter(WebsiteAlert.target_id == website_target_id)
        if alert_type:
            query = query.filter(WebsiteAlert.alert_type == alert_type)
        if alert_level:
            query = query.filter(WebsiteAlert.alert_level == alert_level)
        count += query.update({WebsiteAlert.is_acknowledged: True}, synchronize_session=False)
    return count
