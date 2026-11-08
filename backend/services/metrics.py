"""Prometheus /metrics 指标采集（纯文本 exposition format）"""
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from ..models.models import Alert, Device, DeviceInterface, DeviceMetric, DeviceConnection
from . import backup as backup_service
from .cache import cache

VERSION = "1.1.0"


def _escape(value: Any) -> str:
    text = str(value or "")
    return text.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


def _labels(**labels) -> str:
    if not labels:
        return ""
    inner = ",".join(f'{key}="{_escape(value)}"' for key, value in labels.items())
    return "{" + inner + "}"


def _sample(lines: List[str], name: str, value: Any, labels: Dict[str, Any] = None,
            help_text: str = "", metric_type: str = "gauge") -> None:
    if help_text:
        lines.append(f"# HELP {name} {help_text}")
        lines.append(f"# TYPE {name} {metric_type}")
    lines.append(f"{name}{_labels(**(labels or {}))} {value}")


def _latest_metrics(db: Session, devices: List[Device]) -> Dict[int, DeviceMetric]:
    ids = [device.id for device in devices]
    if not ids:
        return {}
    latest = (
        db.query(
            DeviceMetric.device_id.label("device_id"),
            func.max(DeviceMetric.collected_at).label("max_at"),
        )
        .filter(DeviceMetric.device_id.in_(ids))
        .group_by(DeviceMetric.device_id)
        .subquery()
    )
    rows = (
        db.query(DeviceMetric)
        .join(
            latest,
            and_(
                DeviceMetric.device_id == latest.c.device_id,
                DeviceMetric.collected_at == latest.c.max_at,
            ),
        )
        .all()
    )
    return {row.device_id: row for row in rows}


def collect(
    db: Session,
    uptime_seconds: float,
    collector_running: bool,
    scheduler_running: bool,
    db_ok: bool = True,
    instance_id: str = "",
    background_tasks: bool = True,
) -> str:
    lines: List[str] = []
    now = datetime.utcnow()

    _sample(lines, "snmp_nms_up", 1, help_text="Service is up")
    _sample(
        lines, "snmp_nms_info", 1,
        labels={"version": VERSION, "instance": instance_id,
                "database": db.bind.dialect.name if db.bind else "unknown"},
        help_text="Build/instance information",
    )
    _sample(lines, "snmp_nms_uptime_seconds", round(uptime_seconds, 1),
            help_text="Process uptime in seconds")
    _sample(lines, "snmp_nms_database_up", 1 if db_ok else 0,
            help_text="Database reachable (1=up)")
    _sample(lines, "snmp_nms_collector_running", 1 if collector_running else 0,
            help_text="SNMP collector running")
    _sample(lines, "snmp_nms_website_scheduler_running", 1 if scheduler_running else 0,
            help_text="Website monitor scheduler running")
    _sample(lines, "snmp_nms_background_tasks_enabled", 1 if background_tasks else 0,
            help_text="Background tasks enabled on this instance")

    devices = db.query(Device).all()
    latest = _latest_metrics(db, devices)
    enabled = [device for device in devices if device.is_enabled]
    offline = 0
    for device in enabled:
        metric = latest.get(device.id)
        if not metric or not metric.collected_at:
            offline += 1
        elif (now - metric.collected_at).total_seconds() > 300:
            offline += 1

    _sample(lines, "snmp_nms_devices_total", len(devices), help_text="Total devices")
    _sample(lines, "snmp_nms_devices_enabled", len(enabled), help_text="Enabled devices")
    _sample(lines, "snmp_nms_devices_offline", offline, help_text="Enabled devices without fresh metrics")

    unack = db.query(Alert).filter(Alert.is_acknowledged == False).count()  # noqa: E712
    recent = (
        db.query(Alert)
        .filter(Alert.created_at >= now - timedelta(hours=24))
        .count()
    )
    _sample(lines, "snmp_nms_alerts_unacknowledged", unack,
            help_text="Unacknowledged alerts")
    _sample(lines, "snmp_nms_alerts_24h", recent,
            help_text="Alerts created in last 24 hours")

    interfaces = db.query(DeviceInterface).all()
    up = sum(1 for item in interfaces if (item.if_oper_status or "") == "up")
    down = sum(1 for item in interfaces if (item.if_oper_status or "") == "down")
    _sample(lines, "snmp_nms_interfaces_total", len(interfaces),
            help_text="Total interfaces")
    _sample(lines, "snmp_nms_interfaces_up", up, help_text="Interfaces up")
    _sample(lines, "snmp_nms_interfaces_down", down, help_text="Interfaces down")
    _sample(lines, "snmp_nms_topology_connections",
            db.query(DeviceConnection).count(), help_text="Topology connections")

    info = cache.info()
    stats = info.get("stats") or {}
    _sample(lines, "snmp_nms_cache_hits_total", stats.get("hits", 0),
            help_text="Cache hits", metric_type="counter")
    _sample(lines, "snmp_nms_cache_misses_total", stats.get("misses", 0),
            help_text="Cache misses", metric_type="counter")
    _sample(lines, "snmp_nms_cache_redis_up",
            1 if info.get("backend") == "redis" else 0,
            help_text="Redis cache active (1=redis, 0=memory)")

    latest_backup = backup_service.latest_backup()
    backup_ts = 0
    if latest_backup:
        try:
            backup_ts = datetime.fromisoformat(latest_backup["created_at"]).timestamp()
        except (ValueError, TypeError):
            backup_ts = 0
    _sample(lines, "snmp_nms_backup_last_success_timestamp_seconds", round(backup_ts),
            help_text="Unix timestamp of latest database backup")

    for device in devices:
        metric = latest.get(device.id)
        labels = {
            "device_id": device.id,
            "name": device.name or "",
            "ip": device.ip_address or "",
            "type": device.device_type or "",
        }
        if metric:
            if metric.cpu_usage is not None:
                _sample(lines, "snmp_nms_device_cpu_percent", metric.cpu_usage,
                        labels=labels, help_text="Device CPU usage percent")
            if metric.memory_usage is not None:
                _sample(lines, "snmp_nms_device_memory_percent", metric.memory_usage,
                        labels=labels, help_text="Device memory usage percent")
            if metric.temperature is not None:
                _sample(lines, "snmp_nms_device_temperature_celsius", metric.temperature,
                        labels=labels, help_text="Device temperature celsius")
            _sample(
                lines, "snmp_nms_device_power_ok",
                1 if metric.power_status == "normal" else 0,
                labels=labels, help_text="Device power status (1=normal)",
            )
            if metric.collected_at:
                _sample(
                    lines, "snmp_nms_device_last_collected_timestamp_seconds",
                    round(metric.collected_at.timestamp()),
                    labels=labels, help_text="Last metric collection timestamp",
                )
        custom_values = (metric.custom or {}) if metric else {}
        for key, value in custom_values.items():
            if isinstance(value, (int, float)):
                _sample(
                    lines, "snmp_nms_device_custom_metric", value,
                    labels={**labels, "metric": key},
                    help_text="Device custom metric value",
                )

    return "\n".join(lines) + "\n"
