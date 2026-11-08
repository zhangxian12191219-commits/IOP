"""活动告警生命周期对账。

确认只表示“知道”，不表示“恢复”。本模块按最新采集状态关闭条件已消失的告警，
避免设备/网站/虚拟机已经正常但活动告警仍长期存在。
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from ..models.models import Alert, Device, DeviceMetric
from ..models.virtualization import VirtualizationAlert, VirtualMachine
from ..models.website import WebsiteAlert, WebsiteCheckHistory, WebsiteTarget
from .alert_recovery import reconcile_metric_alerts
from .cache import invalidate_dashboard

logger = logging.getLogger(__name__)


def _resolve(row, reason: str) -> None:
    row.resolved_at = datetime.utcnow()
    row.resolution = reason
    row.is_acknowledged = True


def _cert_healthy(target: WebsiteTarget, cert_info: Optional[dict]) -> bool:
    if target.cert_monitor_enabled is False:
        return True
    if not isinstance(cert_info, dict):
        return False
    candidates = [cert_info]
    candidates.extend(cert_info.get("extra_certificates") or [])
    valid = [item for item in candidates if isinstance(item, dict) and item.get("error") is None and item.get("days_left") is not None]
    if not valid:
        return False
    try:
        threshold = int(target.cert_expiry_days if target.cert_expiry_days is not None else 30)
    except (TypeError, ValueError):
        threshold = 30
    return all(int(item.get("days_left") or 0) > threshold for item in valid)


def _reconcile_website(db: Session) -> int:
    alerts = db.query(WebsiteAlert).filter(WebsiteAlert.resolved_at.is_(None)).all()
    if not alerts:
        return 0
    targets = {
        row.id: row
        for row in db.query(WebsiteTarget).filter(
            WebsiteTarget.id.in_({a.target_id for a in alerts})
        ).all()
    }
    count = 0
    for alert in alerts:
        target = targets.get(alert.target_id)
        if not target:
            continue
        latest = (
            db.query(WebsiteCheckHistory)
            .filter(WebsiteCheckHistory.target_id == target.id)
            .order_by(WebsiteCheckHistory.checked_at.desc(), WebsiteCheckHistory.id.desc())
            .first()
        )
        if not latest:
            continue
        if alert.alert_type == "down" and latest.is_alive:
            _resolve(alert, "condition_recovered")
            count += 1
        elif alert.alert_type == "slow" and latest.is_alive:
            threshold = float(target.slow_threshold_ms or 5000)
            if latest.response_time is not None and float(latest.response_time) <= threshold:
                _resolve(alert, "condition_recovered")
                count += 1
        elif alert.alert_type == "ssl_expired" and _cert_healthy(target, latest.cert_info or {}):
            _resolve(alert, "condition_recovered")
            count += 1
    return count


def _reconcile_virtualization(db: Session) -> int:
    alerts = db.query(VirtualizationAlert).filter(VirtualizationAlert.resolved_at.is_(None)).all()
    if not alerts:
        return 0
    vms = {
        row.id: row
        for row in db.query(VirtualMachine).filter(
            VirtualMachine.id.in_({a.vm_id for a in alerts if a.vm_id})
        ).all()
    }
    count = 0
    for alert in alerts:
        vm = vms.get(alert.vm_id) if alert.vm_id else None
        if not vm:
            continue
        power = str(vm.power_state or "").lower()
        running = any(word in power for word in ("running", "poweredon", "powered_on", "on"))
        if alert.alert_type == "vm_shutdown" and running:
            _resolve(alert, "condition_recovered")
            count += 1
            continue
        current = {
            "vm_cpu": vm.cpu_usage,
            "vm_memory": vm.memory_usage,
            "vm_disk": vm.disk_usage,
        }.get(alert.alert_type)
        if current is not None and alert.threshold is not None and float(current) <= float(alert.threshold):
            _resolve(alert, "condition_recovered")
            count += 1
    return count


def _reconcile_storage_disks(db: Session) -> int:
    alerts = db.query(Alert).filter(
        Alert.resolved_at.is_(None),
        Alert.alert_type == "storage_disk_fault",
    ).all()
    if not alerts:
        return 0
    latest = {}
    for alert in alerts:
        metric = (
            db.query(DeviceMetric)
            .filter(DeviceMetric.device_id == alert.device_id)
            .order_by(DeviceMetric.collected_at.desc(), DeviceMetric.id.desc())
            .first()
        )
        latest[alert.id] = metric
    count = 0
    devices = {
        row.id: row
        for row in db.query(Device).filter(Device.id.in_({a.device_id for a in alerts})).all()
    }
    for alert in alerts:
        device = devices.get(alert.device_id)
        # storage_disk_fault 只允许真实存储设备；历史误报（服务器）直接清理。
        if not device or str(device.device_type or "").lower() != "storage":
            _resolve(alert, "false_positive_cleanup")
            count += 1
            continue
        metric = latest.get(alert.id)
        components = (metric.custom or {}).get("server_components") if metric else None
        disks = components.get("disks") if isinstance(components, dict) else None
        if not isinstance(disks, list):
            continue
        faults = [item for item in disks if str(item.get("status") or "") == "fault"]
        if not faults:
            _resolve(alert, "condition_recovered")
            count += 1
    return count


def reconcile_active_alerts(db: Session) -> int:
    """关闭所有条件已消失的活动告警；返回关闭数量。"""
    count = 0
    try:
        count += reconcile_metric_alerts(db)
    except Exception as exc:  # noqa: BLE001
        logger.warning("设备指标活动告警对账失败: %s", exc)
        db.rollback()
    for fn, label in ((_reconcile_website, "网站"), (_reconcile_virtualization, "虚拟化"), (_reconcile_storage_disks, "存储磁盘")):
        try:
            count += fn(db)
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s活动告警对账失败: %s", label, exc)
            db.rollback()
    if count:
        db.commit()
        invalidate_dashboard()
        logger.info("活动告警条件对账已关闭 %s 条", count)
    return count
