"""告警指标恢复对账。

告警中心在读取列表时，也会按资产最新采集值做一次对账，避免采集器重启/离线导致
指标已经恢复但告警仍停留在未恢复状态。
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, Optional

from sqlalchemy.orm import Session

from ..config import Config
from ..models.alert_rule import DeviceAlertRule
from ..models.models import Alert, Device, DeviceMetric
from ..notify import notify_alert_sync
from . import alert_rules as alert_rule_service
from .cache import invalidate_dashboard

_METRIC_FIELDS = {
    "cpu": "cpu_usage",
    "memory": "memory_usage",
    "temperature": "temperature",
    "disk": "disk_usage",
}
_DEFAULT_THRESHOLDS = {
    "cpu": Config.CPU_THRESHOLD,
    "memory": Config.MEMORY_THRESHOLD,
    "temperature": Config.TEMPERATURE_THRESHOLD,
    "disk": getattr(Config, "DISK_THRESHOLD", 90),
}


def _metric_dict(metric: Optional[DeviceMetric]) -> Dict[str, Any]:
    if not metric:
        return {}
    return {
        "cpu_usage": metric.cpu_usage,
        "memory_usage": metric.memory_usage,
        "temperature": metric.temperature,
        "disk_usage": metric.disk_usage,
        "power_status": metric.power_status,
        "custom": metric.custom or {},
    }


def build_recovery_payload(
    alert: Alert,
    device: Optional[Device],
    rule: Optional[DeviceAlertRule],
    value: Any,
    recovered_at: datetime,
) -> Dict[str, Any]:
    """构建恢复通知负载；source_id 使用负值，避免和原始告警通知去重冲突。"""
    return {
        "source": "device",
        "source_id": -int(alert.id) if alert.id else None,
        "level": alert.alert_level,
        "device_name": device.name if device else f"设备#{alert.device_id}",
        "ip_address": device.ip_address if device else "",
        "room_name": (device.cabinet.room.name if device and device.cabinet and device.cabinet.room else ""),
        "cabinet_name": (device.cabinet.name if device and device.cabinet else ""),
        "room_floor": (device.cabinet.room.floor if device and device.cabinet and device.cabinet.room else ""),
        "room_location": (device.cabinet.room.location if device and device.cabinet and device.cabinet.room else ""),
        "alert_type": alert.alert_type,
        "message": alert.message,
        "value": value,
        "threshold": alert.threshold,
        "created_at": recovered_at.isoformat(timespec="seconds"),
        "recovered_at": recovered_at.isoformat(timespec="seconds"),
        "original_created_at": alert.created_at.isoformat(timespec="seconds") if alert.created_at else None,
        "recovery": True,
        "channel_ids": (rule.notify_channel_ids or []) if rule else None,
    }


def reconcile_metric_alerts(db: Session, device_ids: Optional[Iterable[int]] = None) -> int:
    """按最新 DeviceMetric 关闭已经恢复的设备指标告警；离线告警由采集器单独处理。"""
    query = db.query(Alert).filter(
        Alert.resolved_at.is_(None),
        Alert.alert_type != "offline",
    )
    ids = [int(item) for item in (device_ids or []) if item]
    if ids:
        query = query.filter(Alert.device_id.in_(ids))
    alerts = query.limit(20000).all()
    if not alerts:
        return 0

    device_ids = {alert.device_id for alert in alerts if alert.device_id}
    devices = {
        device.id: device
        for device in db.query(Device).filter(Device.id.in_(device_ids)).all()
    } if device_ids else {}
    latest: Dict[int, DeviceMetric] = {}
    for device_id in device_ids:
        latest[device_id] = (
            db.query(DeviceMetric)
            .filter(DeviceMetric.device_id == device_id)
            .order_by(DeviceMetric.collected_at.desc(), DeviceMetric.id.desc())
            .first()
        )
    rule_ids = {alert.rule_id for alert in alerts if alert.rule_id}
    rules = {
        rule.id: rule
        for rule in db.query(DeviceAlertRule).filter(DeviceAlertRule.id.in_(rule_ids)).all()
    } if rule_ids else {}
    # 自定义规则优先：旧内置告警在对应规则存在时直接判定为“已被规则取代”。
    enabled_rules = (
        db.query(DeviceAlertRule)
        .filter(DeviceAlertRule.device_id.in_(device_ids), DeviceAlertRule.enabled == True)  # noqa: E712
        .all()
    ) if device_ids else []
    custom_covered: Dict[int, set] = {}
    for rule in enabled_rules:
        covered = custom_covered.setdefault(rule.device_id, set())
        if rule.metric in ("cpu_usage", "memory_usage", "temperature", "disk_usage", "power"):
            covered.add(rule.metric)
        key = str(rule.custom_key or "")
        if rule.metric == "custom":
            if key in ("srv_cpu_temp", "srv_inlet_temp", "srv_exhaust_temp") or key.startswith("srv_component_temp_"):
                covered.add("temperature")
            elif key in ("srv_disk_usage", "srv_disk_used"):
                covered.add("disk_usage")
            elif key in ("srv_power_watts", "srv_power_voltage", "srv_power_current", "srv_power_status"):
                covered.add("power")

    recovered = 0
    recovered_items = []
    for alert in alerts:
        metric = latest.get(alert.device_id)
        if not metric:
            continue
        rule = rules.get(alert.rule_id)
        # 旧内置告警：自定义规则已接管该指标时不按默认 80/85 再判断，直接关闭。
        if rule is None and alert.alert_type in custom_covered.get(alert.device_id, set()):
            alert.resolved_at = datetime.utcnow()
            alert.resolution = "superseded_by_custom_rule"
            alert.is_acknowledged = True
            recovered += 1
            continue
        current_value = None
        if rule:
            if rule.metric == "offline":
                continue
            current_value = alert_rule_service.metric_value(rule, _metric_dict(metric))
            if current_value is None:
                continue
            if alert_rule_service.condition_matches(current_value, rule.operator or "gt", rule.threshold or 0):
                continue
        elif alert.alert_type == "power":
            if metric.power_status != "normal":
                continue
        elif alert.alert_type in _METRIC_FIELDS:
            current_value = getattr(metric, _METRIC_FIELDS[alert.alert_type], None)
            if current_value is None or float(current_value) > float(_DEFAULT_THRESHOLDS[alert.alert_type]):
                continue
        else:
            continue
        recovered_at = datetime.utcnow()
        alert.resolved_at = recovered_at
        alert.resolution = "metric_recovered"
        alert.is_acknowledged = True
        recovered_items.append((alert, rule, current_value, recovered_at))
        recovered += 1

    if recovered:
        db.commit()
        invalidate_dashboard()
        # 提交后发送恢复通知；每条告警只会在第一次恢复时发送
        for alert, rule, current_value, recovered_at in recovered_items:
            try:
                notify_alert_sync(build_recovery_payload(
                    alert, devices.get(alert.device_id), rule, current_value, recovered_at,
                ))
            except Exception:  # noqa: BLE001
                pass
    return recovered
