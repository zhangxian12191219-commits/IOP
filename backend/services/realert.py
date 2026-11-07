"""严重/紧急告警确认后的定时再告警。

规则：
- 处理所有未恢复告警（info/warning/critical/emergency）；
- 人工确认后冷却 N 分钟（默认 30）；
- 到期仍未恢复：复制一条新的未确认告警，旧记录标记为已被再提醒替换；
- 新记录使用新 ID，现有通知渠道会重新发送，不受同告警去重影响。
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from ..config import Config
from ..models.database import SessionLocal
from ..models.models import Alert, Device
from ..models.virtualization import VirtualizationAlert
from ..models.website import WebsiteAlert, WebsiteTarget
from ..notify import notify_alert
from .cache import invalidate_dashboard
from .settings import get_value
from .alert_lifecycle import reconcile_active_alerts
from .virtualization_alerts import dispatch_alert_notification

logger = logging.getLogger(__name__)
REALERT_LEVELS = ("info", "warning", "critical", "emergency")


def _interval_minutes(db: Session) -> int:
    try:
        value = int(get_value(db, "alert_realert_minutes"))
    except Exception:
        try:
            value = int(Config.SEVERE_ALERT_REALERT_MINUTES)
        except (TypeError, ValueError):
            value = 30
    return max(1, min(1440, value))


def _initialise_legacy_ack_times(db: Session) -> int:
    """旧版本确认的告警没有确认时间；首次运行从当前时间开始计时，避免升级即集中重发。"""
    now = datetime.utcnow()
    changed = 0
    for model in (Alert, WebsiteAlert, VirtualizationAlert):
        rows = (
            db.query(model)
            .filter(
                model.is_acknowledged.is_(True),
                model.resolved_at.is_(None),
                model.is_hidden.isnot(True),
                model.alert_level.in_(REALERT_LEVELS),
                model.acknowledged_at.is_(None),
            )
            .all()
        )
        for row in rows:
            row.acknowledged_at = now
            changed += 1
    if changed:
        db.commit()
        logger.info("已为 %s 条历史严重/紧急确认告警初始化冷却时间", changed)
    return changed


def _device_payload(alert: Alert) -> Dict[str, Any]:
    device = alert.device
    return {
        "source": "device",
        "source_id": alert.id,
        "level": alert.alert_level,
        "level_label": alert.level_label,
        "device_name": device.name if device else f"设备#{alert.device_id}",
        "ip_address": device.ip_address if device else "",
        "alert_type": alert.alert_type,
        "message": alert.message,
        "value": alert.value,
        "threshold": alert.threshold,
        "created_at": alert.created_at.isoformat(timespec="seconds") if alert.created_at else None,
    }


def _website_payload(alert: WebsiteAlert) -> Dict[str, Any]:
    target = alert.target
    return {
        "source": "website",
        "source_id": alert.id,
        "level": alert.alert_level,
        "level_label": alert.level_label,
        "device_name": target.name if target else f"网站#{alert.target_id}",
        "ip_address": (target.domain or target.ip_address) if target else "",
        "alert_type": alert.alert_type,
        "message": alert.message,
        "created_at": alert.created_at.isoformat(timespec="seconds") if alert.created_at else None,
    }


def _copy_device_alert(alert: Alert, now: datetime) -> Alert:
    return Alert(
        device_id=alert.device_id,
        alert_type=alert.alert_type,
        alert_level=alert.alert_level,
        level_label=alert.level_label,
        rule_id=alert.rule_id,
        message=alert.message,
        value=alert.value,
        threshold=alert.threshold,
        is_acknowledged=False,
        created_at=now,
    )


def _copy_website_alert(alert: WebsiteAlert, now: datetime) -> WebsiteAlert:
    return WebsiteAlert(
        target_id=alert.target_id,
        alert_type=alert.alert_type,
        alert_level=alert.alert_level,
        level_label=alert.level_label,
        message=alert.message,
        details=alert.details,
        is_acknowledged=False,
        created_at=now,
    )


def _copy_vm_alert(alert: VirtualizationAlert, now: datetime) -> VirtualizationAlert:
    return VirtualizationAlert(
        platform_id=alert.platform_id,
        vm_id=alert.vm_id,
        platform_name=alert.platform_name,
        vm_name=alert.vm_name,
        alert_type=alert.alert_type,
        alert_level=alert.alert_level,
        send_notification=alert.send_notification is not False,
        message=alert.message,
        value=alert.value,
        threshold=alert.threshold,
        is_acknowledged=False,
        is_hidden=False,
        created_at=now,
        updated_at=now,
    )


def reopen_due_alerts(db: Session) -> int:
    """执行一次再提醒；返回新建的再提醒告警数量。"""
    _initialise_legacy_ack_times(db)
    cutoff = datetime.utcnow() - timedelta(minutes=_interval_minutes(db))
    now = datetime.utcnow()
    total = 0

    due_device = (
        db.query(Alert)
        .filter(
            Alert.is_acknowledged.is_(True),
            Alert.resolved_at.is_(None),
            Alert.alert_level.in_(REALERT_LEVELS),
            Alert.acknowledged_at.is_not(None),
            Alert.acknowledged_at <= cutoff,
        )
        .all()
    )
    for old in due_device:
        active = (
            db.query(Alert)
            .filter(
                Alert.device_id == old.device_id,
                Alert.alert_type == old.alert_type,
                Alert.resolved_at.is_(None),
                Alert.id != old.id,
            )
            .first()
        )
        if active is None:
            new = _copy_device_alert(old, now)
            db.add(new)
            db.flush()
            notify_alert(_device_payload(new))
            total += 1
        old.resolved_at = now
        old.resolution = "realert_superseded"
        old.is_acknowledged = True
        old.acknowledged_at = None

    due_website = (
        db.query(WebsiteAlert)
        .filter(
            WebsiteAlert.is_acknowledged.is_(True),
            WebsiteAlert.resolved_at.is_(None),
            WebsiteAlert.alert_level.in_(REALERT_LEVELS),
            WebsiteAlert.acknowledged_at.is_not(None),
            WebsiteAlert.acknowledged_at <= cutoff,
        )
        .all()
    )
    for old in due_website:
        active = (
            db.query(WebsiteAlert)
            .filter(
                WebsiteAlert.target_id == old.target_id,
                WebsiteAlert.alert_type == old.alert_type,
                WebsiteAlert.resolved_at.is_(None),
                WebsiteAlert.id != old.id,
            )
            .first()
        )
        if active is None:
            new = _copy_website_alert(old, now)
            db.add(new)
            db.flush()
            notify_alert(_website_payload(new))
            total += 1
        old.resolved_at = now
        old.resolution = "realert_superseded"
        old.is_acknowledged = True
        old.acknowledged_at = None

    due_vm = (
        db.query(VirtualizationAlert)
        .filter(
            VirtualizationAlert.is_acknowledged.is_(True),
            VirtualizationAlert.resolved_at.is_(None),
            VirtualizationAlert.alert_level.in_(REALERT_LEVELS),
            VirtualizationAlert.acknowledged_at.is_not(None),
            VirtualizationAlert.acknowledged_at <= cutoff,
        )
        .all()
    )
    for old in due_vm:
        active = (
            db.query(VirtualizationAlert)
            .filter(
                VirtualizationAlert.platform_id == old.platform_id,
                VirtualizationAlert.vm_id == old.vm_id,
                VirtualizationAlert.alert_type == old.alert_type,
                VirtualizationAlert.resolved_at.is_(None),
                VirtualizationAlert.id != old.id,
            )
            .first()
        )
        if active is None:
            new = _copy_vm_alert(old, now)
            db.add(new)
            db.flush()
            dispatch_alert_notification(new)
            total += 1
        old.resolved_at = now
        old.resolution = "realert_superseded"
        old.is_acknowledged = True
        old.acknowledged_at = None

    if total or due_device or due_website or due_vm:
        db.commit()
        invalidate_dashboard()
        logger.info("严重/紧急告警再提醒：新增 %s 条，处理确认告警 %s 条", total, len(due_device) + len(due_website) + len(due_vm))
    return total


async def realert_loop(shutdown_event: asyncio.Event) -> None:
    while not shutdown_event.is_set():
        db = SessionLocal()
        try:
            reconcile_active_alerts(db)
            reopen_due_alerts(db)
        except Exception as exc:  # noqa: BLE001
            logger.exception("严重/紧急告警再提醒检查失败: %s", exc)
            try:
                db.rollback()
            except Exception:
                pass
        finally:
            db.close()
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=60)
        except asyncio.TimeoutError:
            continue
