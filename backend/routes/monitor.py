"""监控路由 - 实时数据查询接口"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from urllib.parse import quote

from ..config import Config
from ..models.database import get_db
from ..models.models import Device, DeviceInterface, DeviceMetric, InterfaceMetric, Alert, AlertSuppression
from ..models.alert_rule import DeviceAlertRule
from ..models.website import WebsiteAlert, WebsiteTarget
from ..models.virtualization import VirtualizationAlert
from ..models.room import Cabinet, Room
from ..services import alert_io, asset_scope, alert_rules as alert_rule_service
from ..services import alert_suppression, audit as audit_service
from ..services import virtualization_alerts as vm_alert_service
from ..services import alert_lifecycle
from ..services.alert_recovery import reconcile_metric_alerts
from ..services.cache import invalidate_dashboard

router = APIRouter(prefix="/api/monitor", tags=["监控数据"])

DEVICE_TYPE_TEXT = {
    "router": "路由器", "switch": "交换机",
    "firewall": "防火墙", "security": "安全设备",
}
ALERT_TYPE_TEXT = {
    "cpu": "CPU", "memory": "内存", "temperature": "温度",
    "power": "电源", "offline": "离线", "down": "不可达", "slow": "响应慢",
    "warranty": "维保到期", "storage_disk_fault": "存储磁盘故障",
}
WEBSITE_ALERT_TYPE_TEXT = {
    "down": "网站不可达", "slow": "响应缓慢", "ssl_expired": "SSL 证书异常",
}
BUILTIN_ALERT_METRICS = {
    "cpu": {"key": "cpu_usage", "label": "CPU 使用率", "unit": "%"},
    "memory": {"key": "memory_usage", "label": "内存使用率", "unit": "%"},
    "temperature": {"key": "temperature", "label": "最高部件温度", "unit": "°C"},
    "disk": {"key": "disk_usage", "label": "磁盘使用率", "unit": "%"},
    "power": {"key": "power", "label": "电源状态", "unit": "", "state": "异常"},
    "offline": {"key": "offline", "label": "设备连通性", "unit": "", "state": "离线"},
    "warranty": {"key": "warranty_days_left", "label": "维保剩余天数", "unit": "天"},
    "storage_disk_fault": {"key": "storage_disk_fault", "label": "存储磁盘故障", "unit": "块"},
    "down": {"key": "availability", "label": "网站可用性", "unit": "", "state": "不可达"},
    "slow": {"key": "response_time", "label": "响应时间", "unit": "ms"},
    "ssl_expired": {"key": "ssl_expiry", "label": "SSL 证书", "unit": "天"},
}


def _custom_metric_meta(device: Optional[Device], key: Optional[str]) -> Dict[str, Any]:
    if not device or not key:
        return {}
    for source in (device.custom_metrics or [], device.server_sensors or []):
        for item in source:
            if isinstance(item, dict) and str(item.get("key") or "") == key:
                return item
    return {}


def _alert_metric_detail(
    alert: Alert,
    rule: Optional[DeviceAlertRule],
    device: Optional[Device],
) -> Dict[str, Any]:
    """把告警还原成明确的指标、触发值、阈值和触发条件。"""
    if rule:
        label = alert_rule_service.rule_metric_label(rule)
        unit = alert_rule_service.rule_unit(rule)
        if rule.metric == "custom":
            meta = _custom_metric_meta(device, rule.custom_key)
            label = str(meta.get("name") or label)
            unit = str(meta.get("unit") or unit)
        operator = rule.operator or "gt"
        return {
            "metric_key": rule.metric,
            "metric_label": label,
            "metric_unit": unit,
            "operator": operator,
            "operator_text": alert_rule_service.OPERATORS.get(operator, operator),
            "condition_text": alert_rule_service.condition_text(rule),
            "rule_name": rule.name,
        }

    meta = BUILTIN_ALERT_METRICS.get(alert.alert_type or "", {})
    label = meta.get("label") or ALERT_TYPE_TEXT.get(alert.alert_type or "", alert.alert_type or "告警")
    unit = meta.get("unit") or ""
    operator = "gt"
    if alert.alert_type == "warranty":
        threshold = alert.threshold if alert.threshold is not None else 5
        return {
            "metric_key": "warranty_days_left",
            "metric_label": "维保剩余天数",
            "metric_unit": "天",
            "operator": "lte",
            "operator_text": "≤",
            "condition_text": f"剩余 {threshold:g} 天及以内（当前 {alert.value if alert.value is not None else '-'} 天）",
            "rule_name": None,
        }
    if alert.threshold is not None:
        condition = f"{label} > {alert.threshold:g}{unit}"
    elif meta.get("state"):
        condition = f"{label}{meta['state']}"
    else:
        condition = label
    return {
        "metric_key": meta.get("key") or alert.alert_type,
        "metric_label": label,
        "metric_unit": unit,
        "operator": operator,
        "operator_text": ">",
        "condition_text": condition,
        "rule_name": None,
    }


def _get_scoped_device(db: Session, request: Request, device_id: int) -> Device:
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    asset_scope.require_device_access(db, request, device)
    return device


@router.get("/devices/{device_id}/overview")
def get_device_overview(device_id: int, request: Request, db: Session = Depends(get_db)):
    """获取设备监控总览（按群组校验）"""
    device = _get_scoped_device(db, request, device_id)
    
    # 最新指标
    metric = db.query(DeviceMetric).filter(
        DeviceMetric.device_id == device_id
    ).order_by(DeviceMetric.collected_at.desc()).first()
    
    # 接口列表
    interfaces = db.query(DeviceInterface).filter(
        DeviceInterface.device_id == device_id
    ).all()
    
    # 未确认告警（告警页使用）与全部未恢复告警（指标颜色使用）
    alerts = db.query(Alert).filter(
        Alert.device_id == device_id,
        Alert.is_acknowledged == False
    ).order_by(Alert.created_at.desc()).limit(10).all()
    active_alerts = db.query(Alert).filter(
        Alert.device_id == device_id,
        Alert.resolved_at.is_(None),
    ).order_by(Alert.created_at.desc()).limit(50).all()
    
    return {
        "device": {
            "id": device.id,
            "name": device.name,
            "ip_address": device.ip_address,
            "device_type": device.device_type,
            "is_enabled": device.is_enabled,
        },
        "metric": metric_to_dict(metric) if metric else None,
        "metric_thresholds": {
            "cpu_usage": Config.CPU_THRESHOLD,
            "memory_usage": Config.MEMORY_THRESHOLD,
            "temperature": Config.TEMPERATURE_THRESHOLD,
            "temperature_critical": Config.TEMPERATURE_CRITICAL_THRESHOLD,
            "disk_usage": Config.DISK_THRESHOLD,
        },
        "interfaces": [iface_to_dict(i) for i in interfaces],
        "alerts": _enrich_alerts(db, alerts),
        "active_alerts": _enrich_alerts(db, active_alerts),
    }


def _downsample(points: List[Dict[str, Any]], max_points: int = 1500) -> List[Dict[str, Any]]:
    """长时间范围下均匀抽样，避免图表点过多（保留首尾点）"""
    if len(points) <= max_points:
        return points
    step = len(points) / max_points
    sampled: List[Dict[str, Any]] = []
    last_index = -1
    for i in range(max_points):
        index = int(i * step)
        if index != last_index:
            sampled.append(points[index])
            last_index = index
    if sampled and sampled[-1] is not points[-1]:
        sampled.append(points[-1])
    return sampled


@router.get("/devices/{device_id}/history")
def get_metric_history(
    device_id: int,
    request: Request,
    metric_type: str = Query(
        "cpu_usage",
        pattern=r"^(cpu_usage|memory_usage|temperature|custom_[a-z0-9_]{1,30})$",
    ),
    hours: int = Query(24, ge=1, le=720),
    start: Optional[datetime] = Query(None, description="开始时间（UTC，ISO8601）"),
    end: Optional[datetime] = Query(None, description="结束时间（UTC，ISO8601）"),
    db: Session = Depends(get_db),
):
    """获取历史监控数据（支持标准指标与自定义指标 custom_xxx）

    可传 hours（最近 N 小时），或 start/end 指定任意时间范围（精确到秒）。
    """
    now = datetime.utcnow()
    _get_scoped_device(db, request, device_id)
    if start or end:
        end_dt = end or now
        start_dt = start or (end_dt - timedelta(hours=hours))
        if start_dt > end_dt:
            raise HTTPException(status_code=400, detail="开始时间不能晚于结束时间")
        if (end_dt - start_dt) > timedelta(days=366):
            raise HTTPException(status_code=400, detail="时间范围过大（最多 366 天）")
        query = db.query(DeviceMetric).filter(
            DeviceMetric.device_id == device_id,
            DeviceMetric.collected_at >= start_dt,
            DeviceMetric.collected_at <= end_dt,
        )
        since = start_dt
    else:
        since = now - timedelta(hours=hours)
        end_dt = now
        query = db.query(DeviceMetric).filter(
            DeviceMetric.device_id == device_id,
            DeviceMetric.collected_at >= since,
        )

    metrics = (
        query.order_by(DeviceMetric.collected_at.asc())
        .limit(200000)
        .all()
    )

    if metric_type.startswith("custom_"):
        custom_key = metric_type[len("custom_"):]

        def _value(metric):
            return (metric.custom or {}).get(custom_key)

        history = [
            {
                "collected_at": m.collected_at.isoformat() if m.collected_at else None,
                metric_type: _value(m),
            }
            for m in metrics
            if _value(m) is not None
        ]
    else:
        history = [
            {
                "collected_at": m.collected_at.isoformat() if m.collected_at else None,
                metric_type: getattr(m, metric_type, None),
            }
            for m in metrics
        ]

    total = len(history)
    history = _downsample(history)

    return {
        "metric_type": metric_type,
        "hours": hours,
        "start": since.isoformat() if since else None,
        "end": end_dt.isoformat() if end_dt else None,
        "count": total,
        "points": len(history),
        "data": history,
    }


@router.post("/devices/{device_id}/collect")
async def collect_now(device_id: int, request: Request, db: Session = Depends(get_db)):
    """立即采集一次指定设备（无需等待下一个采集周期）"""
    from ..snmp.collector import DataCollector

    device = _get_scoped_device(db, request, device_id)

    collector = DataCollector(db)
    metrics = await collector.collect_device(device)
    if metrics is None:
        return {"device_id": device_id, "success": False, "message": "采集失败：设备不可达"}
    return {"device_id": device_id, "success": True, "metrics": metrics}


@router.get("/interface-summaries")
def get_interface_summaries(
    request: Request,
    device_ids: Optional[str] = Query(None, description="逗号分隔的交换机设备 ID，留空表示全部可见交换机"),
    db: Session = Depends(get_db),
):
    """网络设备接口汇总指标，用于设备指标球型仪表盘配置。"""
    requested_ids: List[int] = []
    if device_ids:
        for part in str(device_ids).split(","):
            part = part.strip()
            if not part:
                continue
            try:
                requested_ids.append(int(part))
            except ValueError as exc:
                raise HTTPException(status_code=400, detail="device_ids 必须是逗号分隔的设备 ID") from exc
    if len(requested_ids) > 500:
        raise HTTPException(status_code=400, detail="一次最多查询 500 台设备")

    query = db.query(Device.id)
    visible_ids = asset_scope.visible_device_ids(db, request)
    if visible_ids is not None:
        query = query.filter(Device.id.in_(visible_ids))
    if requested_ids:
        query = query.filter(Device.id.in_(requested_ids))
    network_device_ids = [row[0] for row in query.all()]
    if not network_device_ids:
        return {"items": []}

    interfaces = (
        db.query(DeviceInterface)
        .filter(DeviceInterface.device_id.in_(network_device_ids))
        .all()
    )
    grouped: Dict[int, List[DeviceInterface]] = {device_id: [] for device_id in network_device_ids}
    for iface in interfaces:
        grouped.setdefault(iface.device_id, []).append(iface)

    items = []
    for device_id in network_device_ids:
        rows = grouped.get(device_id, [])
        total = len(rows)
        up = sum(1 for iface in rows if (iface.if_oper_status or "").lower() == "up")
        down = total - up
        in_bps = sum(float(iface.in_bps or 0) for iface in rows)
        out_bps = sum(float(iface.out_bps or 0) for iface in rows)
        errors = sum(int(iface.in_errors or 0) + int(iface.out_errors or 0) for iface in rows)
        capacity_bps = sum(float(iface.if_speed or 0) for iface in rows)
        max_util = 0.0
        for iface in rows:
            speed = float(iface.if_speed or 0)
            if speed > 0:
                util = (float(iface.in_bps or 0) + float(iface.out_bps or 0)) / speed * 100
                max_util = max(max_util, util)
        items.append({
            "device_id": device_id,
            "total": total,
            "up": up,
            "down": down,
            "available": round(up / total * 100, 1) if total else 0,
            "in_bps": round(in_bps, 1),
            "out_bps": round(out_bps, 1),
            "total_bps": round(in_bps + out_bps, 1),
            "capacity_bps": round(capacity_bps, 1),
            "errors": errors,
            "max_util": round(min(100, max_util), 1),
        })
    return {"items": items}


@router.get("/devices/{device_id}/interfaces")
def get_interfaces(device_id: int, request: Request, db: Session = Depends(get_db)):
    """获取设备接口信息（按群组校验）"""
    _get_scoped_device(db, request, device_id)
    interfaces = db.query(DeviceInterface).filter(
        DeviceInterface.device_id == device_id
    ).all()
    
    return [iface_to_dict(i) for i in interfaces]


@router.get("/devices/{device_id}/interfaces/{interface_id}/history")
def get_interface_history(
    device_id: int,
    interface_id: int,
    request: Request,
    hours: int = Query(24, ge=1, le=720),
    start: Optional[datetime] = Query(None, description="开始时间（UTC，ISO8601）"),
    end: Optional[datetime] = Query(None, description="结束时间（UTC，ISO8601）"),
    db: Session = Depends(get_db),
):
    """获取单个接口的流量历史（支持预设小时数或自定义起止时间）"""
    from datetime import timedelta

    _get_scoped_device(db, request, device_id)
    iface = (
        db.query(DeviceInterface)
        .filter(DeviceInterface.id == interface_id, DeviceInterface.device_id == device_id)
        .first()
    )
    if not iface:
        raise HTTPException(status_code=404, detail="接口不存在")

    now = datetime.utcnow()
    if start or end:
        end_dt = end or now
        start_dt = start or (end_dt - timedelta(hours=hours))
        if start_dt > end_dt:
            raise HTTPException(status_code=400, detail="开始时间不能晚于结束时间")
        if (end_dt - start_dt) > timedelta(days=30):
            raise HTTPException(status_code=400, detail="时间范围过大（最多 30 天）")
    else:
        end_dt = now
        start_dt = now - timedelta(hours=hours)

    rows = (
        db.query(InterfaceMetric)
        .filter(
            InterfaceMetric.device_id == device_id,
            InterfaceMetric.interface_id == interface_id,
            InterfaceMetric.collected_at >= start_dt,
            InterfaceMetric.collected_at <= end_dt,
        )
        .order_by(InterfaceMetric.collected_at.asc())
        .limit(20000)
        .all()
    )

    points = [
        {
            "collected_at": row.collected_at.isoformat() if row.collected_at else None,
            "in_bps": row.in_bps,
            "out_bps": row.out_bps,
            "in_octets": row.in_octets,
            "out_octets": row.out_octets,
            "in_errors": row.in_errors,
            "out_errors": row.out_errors,
            "oper_status": row.oper_status,
        }
        for row in rows
    ]
    # 刚升级或刚开始采集时还没有历史点，至少返回当前接口值，避免详情空白
    if not points and iface.updated_at and start_dt <= iface.updated_at <= end_dt:
        points.append({
            "collected_at": iface.updated_at.isoformat(),
            "in_bps": iface.in_bps,
            "out_bps": iface.out_bps,
            "in_octets": iface.in_octets,
            "out_octets": iface.out_octets,
            "in_errors": iface.in_errors,
            "out_errors": iface.out_errors,
            "oper_status": iface.if_oper_status,
        })
    points = _downsample(points, 1200)
    return {
        "interface": iface_to_dict(iface),
        "points": points,
        "start": start_dt.isoformat(),
        "end": end_dt.isoformat(),
    }


@router.get("/devices/{device_id}/alerts")
def get_alerts(
    device_id: int,
    request: Request,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """获取设备告警列表（按群组校验）"""
    _get_scoped_device(db, request, device_id)
    reconcile_metric_alerts(db, [device_id])
    query = db.query(Alert).filter(Alert.device_id == device_id).order_by(
        Alert.created_at.desc()
    )
    total = query.count()
    alerts = query.offset((page - 1) * size).limit(size).all()

    return {
        "total": total,
        "page": page,
        "size": size,
        "items": _enrich_alerts(db, alerts),
    }


@router.post("/alerts/{alert_id}/probe")
async def probe_alert_device(
    alert_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """再次探测告警关联设备；在线时自动关闭该设备未恢复的离线告警。"""
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="告警不存在")
    if not alert.device_id:
        raise HTTPException(status_code=400, detail="该告警不是设备告警，无法执行设备探测")
    device = _get_scoped_device(db, request, alert.device_id)
    from ..snmp.collector import DataCollector

    collector = DataCollector(db)
    result = await collector.recheck_device(device)
    db.refresh(alert)
    invalidate_dashboard()
    return {
        **result,
        "alert": alert_to_dict(db, alert),
        "message": (
            f"设备在线（{result.get('method', '').upper()}，{result.get('latency_ms', 0)}ms）"
            + (f"，已自动恢复 {result.get('recovered', 0)} 条离线告警" if result.get("recovered") else "")
            if result.get("alive")
            else f"设备仍不可达：{result.get('error') or '探测失败'}"
        ),
    }


@router.post("/alerts/{alert_id}/ack")
def acknowledge_alert(
    alert_id: int,
    request: Request,
    source: str = Query("device", pattern="^(device|website|virtualization)$"),
    db: Session = Depends(get_db),
):
    """确认告警（设备按群组校验 / 网站 / 虚拟化）"""
    if source == "virtualization":
        alert = db.query(VirtualizationAlert).filter(VirtualizationAlert.id == alert_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="虚拟机告警不存在")
        vm_alert_service.acknowledge_alert(db, alert)
        invalidate_dashboard()
        return {"message": "虚拟机告警已确认"}
    if source == "website":
        alert = db.query(WebsiteAlert).filter(WebsiteAlert.id == alert_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="网站告警不存在")
        alert.is_acknowledged = True
        alert.acknowledged_at = datetime.utcnow()
        db.commit()
        invalidate_dashboard()
        return {"message": "网站告警已确认"}

    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="告警不存在")
    if alert.device_id:
        _get_scoped_device(db, request, alert.device_id)

    alert.is_acknowledged = True
    alert.acknowledged_at = datetime.utcnow()
    db.commit()
    invalidate_dashboard()
    return {"message": "告警已确认"}


class SuppressionPayload(BaseModel):
    source: str = Field("device", pattern="^(device|website|all)$")
    device_id: Optional[int] = None
    website_target_id: Optional[int] = None
    alert_type: str = Field("", max_length=100)
    alert_level: Optional[str] = Field(None, pattern="^(info|warning|critical|emergency)$")
    reason: str = Field("", max_length=500)
    duration_minutes: int = Field(60, ge=0, le=43200)
    acknowledge_current: bool = True


def _suppression_items(db: Session) -> List[Dict[str, Any]]:
    rules = db.query(AlertSuppression).order_by(AlertSuppression.created_at.desc()).all()
    device_ids = {rule.device_id for rule in rules if rule.device_id}
    target_ids = {rule.website_target_id for rule in rules if rule.website_target_id}
    devices = {device.id: device.name for device in db.query(Device).filter(Device.id.in_(device_ids)).all()} if device_ids else {}
    targets = {target.id: target.name for target in db.query(WebsiteTarget).filter(WebsiteTarget.id.in_(target_ids)).all()} if target_ids else {}
    return [
        alert_suppression.suppression_to_dict(
            rule,
            device_name=devices.get(rule.device_id, ""),
            target_name=targets.get(rule.website_target_id, ""),
        )
        for rule in rules
    ]


def _create_suppression(
    db: Session,
    request: Request,
    *,
    source: str,
    device_id: Optional[int],
    website_target_id: Optional[int],
    alert_type: str,
    alert_level: Optional[str],
    reason: str,
    duration_minutes: int,
    acknowledge_current: bool,
) -> Dict[str, Any]:
    if source == "device":
        if device_id is not None:
            _get_scoped_device(db, request, device_id)
    elif source == "website":
        if website_target_id is None:
            raise HTTPException(status_code=400, detail="网站告警抑制必须指定网站目标")
        if not db.query(WebsiteTarget).filter(WebsiteTarget.id == website_target_id).first():
            raise HTTPException(status_code=404, detail="网站监控目标不存在")
    else:
        device_id = None
        website_target_id = None
    if not alert_type and source == "all":
        raise HTTPException(status_code=400, detail="抑制全部来源时必须指定告警类型")

    now = datetime.utcnow()
    rule = AlertSuppression(
        source=source,
        device_id=device_id,
        website_target_id=website_target_id,
        alert_type=alert_type or None,
        alert_level=alert_level or None,
        reason=reason.strip(),
        starts_at=now,
        ends_at=(now + timedelta(minutes=duration_minutes)) if duration_minutes > 0 else None,
        is_enabled=True,
        created_at=now,
    )
    db.add(rule)
    acknowledged = 0
    if acknowledge_current:
        acknowledged = alert_suppression.acknowledge_matching(
            db,
            source=source,
            device_id=device_id,
            website_target_id=website_target_id,
            alert_type=alert_type or None,
            alert_level=alert_level or None,
        )
    db.commit()
    db.refresh(rule)
    audit_service.record(
        db, request, module="alerts", action="update",
        target_type="alert_suppression", target_name=reason or alert_type or "告警抑制",
        after={
            "source": source, "device_id": device_id, "website_target_id": website_target_id,
            "alert_type": alert_type, "alert_level": alert_level,
            "ends_at": rule.ends_at.isoformat() if rule.ends_at else None,
        },
        message=f"创建告警抑制规则，确认当前同类告警 {acknowledged} 条",
    )
    invalidate_dashboard()
    item = alert_suppression.suppression_to_dict(rule)
    return {"suppression": item, "acknowledged": acknowledged}


@router.get("/suppressions")
def list_suppressions(request: Request, db: Session = Depends(get_db)):
    return {"items": _suppression_items(db)}


@router.post("/suppressions")
def create_suppression(payload: SuppressionPayload, request: Request, db: Session = Depends(get_db)):
    return _create_suppression(
        db, request,
        source=payload.source,
        device_id=payload.device_id,
        website_target_id=payload.website_target_id,
        alert_type=payload.alert_type,
        alert_level=payload.alert_level,
        reason=payload.reason,
        duration_minutes=payload.duration_minutes,
        acknowledge_current=payload.acknowledge_current,
    )


@router.post("/alerts/{alert_id}/suppress")
def suppress_alert(
    alert_id: int,
    request: Request,
    source: str = Query("device", pattern="^(device|website|virtualization)$"),
    duration_minutes: int = Query(60, ge=0, le=43200),
    reason: str = Query("", max_length=500),
    acknowledge_current: bool = Query(True),
    db: Session = Depends(get_db),
):
    """按某条告警一键抑制同类告警，并默认确认当前同类未确认告警。"""
    if source == "website":
        alert = db.query(WebsiteAlert).filter(WebsiteAlert.id == alert_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="网站告警不存在")
        return _create_suppression(
            db, request,
            source="website",
            device_id=None,
            website_target_id=alert.target_id,
            alert_type=alert.alert_type,
            alert_level=None,
            reason=reason,
            duration_minutes=duration_minutes,
            acknowledge_current=acknowledge_current,
        )
    alert = db.query(Alert).filter(Alert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="告警不存在")
    if alert.device_id:
        _get_scoped_device(db, request, alert.device_id)
    return _create_suppression(
        db, request,
        source="device",
        device_id=alert.device_id,
        website_target_id=None,
        alert_type=alert.alert_type,
        alert_level=None,
        reason=reason,
        duration_minutes=duration_minutes,
        acknowledge_current=acknowledge_current,
    )


@router.delete("/alerts/{alert_id}")
def delete_alert(
    alert_id: int,
    request: Request,
    source: str = Query("device", pattern="^(device|website|virtualization)$"),
    db: Session = Depends(get_db),
):
    """删除活动告警：设备/网站直接删除；虚拟化软删除以阻止条件未变时立即重建。"""
    now = datetime.utcnow()
    if source == "virtualization":
        alert = db.query(VirtualizationAlert).filter(VirtualizationAlert.id == alert_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="虚拟化告警不存在")
        target = alert.vm_name or alert.platform_name or f"虚拟化告警#{alert_id}"
        alert.resolved_at = now
        alert.resolution = "manual_deleted"
        alert.is_acknowledged = True
        alert.is_hidden = True
        message = "虚拟化告警已删除"
    elif source == "website":
        alert = db.query(WebsiteAlert).filter(WebsiteAlert.id == alert_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="网站告警不存在")
        target = f"网站告警#{alert_id}"
        db.delete(alert)
        message = "网站告警已删除"
    else:
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="告警不存在")
        if alert.device_id:
            _get_scoped_device(db, request, alert.device_id)
        target = f"设备告警#{alert_id}"
        db.delete(alert)
        message = "告警已删除"
    audit_service.record(
        db, request, module="alerts", action="delete",
        target_type=f"{source}_alert", target_id=alert_id, target_name=target,
        message=f"删除活动告警：{source}",
    )
    db.commit()
    invalidate_dashboard()
    return {"message": message, "deleted": 1}


class AlertDeleteItem(BaseModel):
    id: int
    source: str = "device"


class AlertBulkDeletePayload(BaseModel):
    items: List[AlertDeleteItem] = Field(default_factory=list)


@router.post("/alerts/bulk-delete")
def bulk_delete_alerts(
    payload: AlertBulkDeletePayload,
    request: Request,
    db: Session = Depends(get_db),
):
    """批量删除活动告警；虚拟化告警软删除，避免条件未变时立即重建。"""
    now = datetime.utcnow()
    deleted = 0
    skipped = 0
    for item in payload.items:
        source = item.source if item.source in ("device", "website", "virtualization") else "device"
        try:
            if source == "virtualization":
                alert = db.query(VirtualizationAlert).filter(VirtualizationAlert.id == item.id).first()
                if not alert:
                    skipped += 1
                    continue
                alert.resolved_at = now
                alert.resolution = "manual_deleted"
                alert.is_acknowledged = True
                alert.is_hidden = True
            elif source == "website":
                alert = db.query(WebsiteAlert).filter(WebsiteAlert.id == item.id).first()
                if not alert:
                    skipped += 1
                    continue
                db.delete(alert)
            else:
                alert = db.query(Alert).filter(Alert.id == item.id).first()
                if not alert:
                    skipped += 1
                    continue
                if alert.device_id:
                    _get_scoped_device(db, request, alert.device_id)
                db.delete(alert)
            deleted += 1
        except HTTPException:
            skipped += 1
    db.commit()
    invalidate_dashboard()
    audit_service.record(
        db, request, module="alerts", action="delete",
        target_type="alert_batch", target_name=f"{deleted} 条",
        message=f"批量删除活动告警：成功 {deleted} 条，跳过 {skipped} 条",
    )
    return {"message": "批量删除完成", "deleted": deleted, "skipped": skipped}


@router.get("/alerts/hidden")
def get_hidden_alerts(
    request: Request,
    source: Optional[str] = Query(None, pattern="^(device|website|virtualization)$"),
    db: Session = Depends(get_db),
):
    """已人工抑制的活动告警；用于恢复显示。"""
    alert_lifecycle.reconcile_active_alerts(db)
    items = _merged_alert_items(
        db, acknowledged=None, source=source, limit=20000, hidden=True,
        visible_device_ids=asset_scope.visible_device_ids(db, request),
    )
    items = [item for item in items if not item.get("resolved_at")]
    items.sort(key=lambda item: (item.get("created_at") or "", item.get("id") or 0), reverse=True)
    return items


def _set_alert_hidden(
    db: Session,
    request: Request,
    alert_id: int,
    source: str,
    hidden: bool,
) -> str:
    if source == "virtualization":
        alert = db.query(VirtualizationAlert).filter(VirtualizationAlert.id == alert_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="虚拟化告警不存在")
        target = alert.vm_name or alert.platform_name or f"虚拟化告警#{alert_id}"
    elif source == "website":
        alert = db.query(WebsiteAlert).filter(WebsiteAlert.id == alert_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="网站告警不存在")
        target = f"网站告警#{alert_id}"
    else:
        alert = db.query(Alert).filter(Alert.id == alert_id).first()
        if not alert:
            raise HTTPException(status_code=404, detail="告警不存在")
        if alert.device_id:
            _get_scoped_device(db, request, alert.device_id)
        target = f"设备告警#{alert_id}"
    alert.is_hidden = hidden
    db.commit()
    invalidate_dashboard()
    audit_service.record(
        db, request, module="alerts", action="suppress" if hidden else "restore",
        target_type=f"{source}_alert", target_id=alert_id, target_name=target,
        message=("抑制单条告警" if hidden else "恢复单条告警") + f"：{source}",
    )
    return target


@router.post("/alerts/{alert_id}/hide")
def hide_alert(
    alert_id: int,
    request: Request,
    source: str = Query("device", pattern="^(device|website|virtualization)$"),
    db: Session = Depends(get_db),
):
    """人工抑制指定告警：不再出现在活动告警和再提醒中，可通过恢复重新显示。"""
    _set_alert_hidden(db, request, alert_id, source, True)
    return {"message": "告警已抑制", "hidden": True}


@router.post("/alerts/{alert_id}/restore")
def restore_alert(
    alert_id: int,
    request: Request,
    source: str = Query("device", pattern="^(device|website|virtualization)$"),
    db: Session = Depends(get_db),
):
    """恢复被抑制的单条告警。"""
    _set_alert_hidden(db, request, alert_id, source, False)
    return {"message": "告警已恢复显示", "hidden": False}


@router.delete("/suppressions/{suppression_id}")
def delete_suppression(suppression_id: int, request: Request, db: Session = Depends(get_db)):
    rule = db.query(AlertSuppression).filter(AlertSuppression.id == suppression_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="抑制规则不存在")
    db.delete(rule)
    db.commit()
    audit_service.record(
        db, request, module="alerts", action="delete",
        target_type="alert_suppression", target_name=f"#{suppression_id}",
        message="删除告警抑制规则",
    )
    return {"message": "抑制规则已删除"}


def _alert_query(
    db: Session,
    alert_level: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    alert_type: Optional[str] = None,
    device_id: Optional[int] = None,
    search: Optional[str] = None,
    days: Optional[int] = None,
    visible_device_ids: Optional[List[int]] = None,
    hidden: Optional[bool] = None,
):
    """构造告警查询（供列表与导出复用；visible_device_ids=None 表示全部）"""
    query = db.query(Alert)
    if hidden is True:
        query = query.filter(Alert.is_hidden.is_(True))
    elif hidden is None:
        query = query.filter(Alert.is_hidden.isnot(True))

    if alert_level:
        query = query.filter(Alert.alert_level == alert_level)
    if acknowledged is not None:
        query = query.filter(Alert.is_acknowledged == acknowledged)
        if acknowledged is False:
            # 未确认列表只展示当前告警；已自动恢复的记录归入历史
            query = query.filter(Alert.resolved_at.is_(None))
    if alert_type:
        query = query.filter(Alert.alert_type == alert_type)
    if device_id:
        query = query.filter(Alert.device_id == device_id)
    if visible_device_ids is not None:
        query = query.filter(Alert.device_id.in_(visible_device_ids or [-1]))
    if days:
        query = query.filter(
            Alert.created_at >= datetime.utcnow() - timedelta(days=int(days))
        )
    if search:
        # 支持按告警内容 / 设备名称 / IP 搜索
        like = f"%{search}%"
        device_ids = [
            d.id for d in db.query(Device).filter(
                Device.name.like(like) | Device.ip_address.like(like)
            ).all()
        ]
        query = query.filter(
            Alert.message.like(like) | Alert.device_id.in_(device_ids or [-1])
        )

    return query.order_by(Alert.created_at.desc(), Alert.id.desc())


@router.get("/alerts")
def list_alerts(
    request: Request,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    alert_level: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    alert_type: Optional[str] = None,
    device_id: Optional[int] = None,
    search: Optional[str] = None,
    days: Optional[int] = None,
    source: Optional[str] = Query(None, pattern="^(device|website|virtualization)$"),
):
    """分页查询告警（设备告警按群组过滤，网站告警不分组）"""
    items = _merged_alert_items(
        db, alert_level, acknowledged, alert_type, device_id, search, days, source,
        visible_device_ids=asset_scope.visible_device_ids(db, request),
    )
    total = len(items)
    start = (page - 1) * size
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": items[start:start + size],
    }


@router.get("/alerts/export")
def export_alerts(
    request: Request,
    fmt: str = Query("xlsx", alias="format", pattern="^(xlsx|csv)$"),
    alert_level: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    alert_type: Optional[str] = None,
    device_id: Optional[int] = None,
    search: Optional[str] = None,
    days: Optional[int] = None,
    source: Optional[str] = Query(None, pattern="^(device|website|virtualization)$"),
    db: Session = Depends(get_db),
):
    """导出告警（设备 + 网站，xlsx / csv；设备告警按群组过滤）"""
    items = _merged_alert_items(
        db, alert_level, acknowledged, alert_type, device_id, search, days, source,
        visible_device_ids=asset_scope.visible_device_ids(db, request),
    )[:20000]

    stamp = datetime.now().strftime("%Y%m%d_%H%M")
    if fmt == "csv":
        content = alert_io.export_csv(items)
        filename = f"告警记录_{stamp}.csv"
        media_type = "text/csv; charset=utf-8"
    else:
        content = alert_io.export_xlsx(items)
        filename = f"告警记录_{stamp}.xlsx"
        media_type = (
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )

    headers = {
        "Content-Disposition": (
            f"attachment; filename=\"alerts\"; filename*=UTF-8''{quote(filename)}"
        )
    }
    return Response(content=content, media_type=media_type, headers=headers)


@router.get("/alerts/unacknowledged")
def get_unacknowledged_alerts(
    request: Request,
    source: Optional[str] = Query(None, pattern="^(device|website|virtualization)$"),
    db: Session = Depends(get_db),
):
    """获取所有未确认告警（设备/网站/虚拟化都按确认状态过滤）。"""
    return _merged_alert_items(
        db, acknowledged=False, source=source, limit=5000,
        visible_device_ids=asset_scope.visible_device_ids(db, request),
    )


@router.get("/alerts/active")
def get_active_alerts(
    request: Request,
    source: Optional[str] = Query(None, pattern="^(device|website|virtualization)$"),
    db: Session = Depends(get_db),
):
    """全部未恢复告警（设备+网站+虚拟化，包含已确认未恢复）。"""
    alert_lifecycle.reconcile_active_alerts(db)
    items = _merged_alert_items(
        db, acknowledged=None, source=source, limit=20000,
        visible_device_ids=asset_scope.visible_device_ids(db, request),
    )
    items = [item for item in items if not item.get("resolved_at")]
    items.sort(key=lambda item: (item.get("created_at") or "", item.get("id") or 0), reverse=True)
    return items


@router.get("/alerts/broadcast")
def get_broadcast_alerts(
    request: Request,
    db: Session = Depends(get_db),
):
    """全量播报专用：只播报未确认、未恢复告警。"""
    return _merged_alert_items(
        db, acknowledged=False, source=None, limit=100000,
        visible_device_ids=asset_scope.visible_device_ids(db, request),
    )


TEMPERATURE_KIND_LABELS = {
    "cpu": "CPU 温度", "board": "主板温度", "inlet": "进风温度",
    "exhaust": "排风温度", "ambient": "环境温度", "other": "其他温度",
}


def _temperature_info(metric_data: Optional[dict]) -> Dict[str, Any]:
    if not metric_data:
        return {}
    custom = metric_data.get("custom") or {}
    components = metric_data.get("components") or custom.get("server_components") or {}
    sensor = custom.get("temperature_sensor") if isinstance(custom, dict) else None
    if not isinstance(sensor, dict):
        temps = components.get("temperatures") if isinstance(components, dict) else []
        sensor = {}
        if temps:
            hottest = max(temps, key=lambda item: float(item.get("value") or 0))
            sensor = {"name": hottest.get("name"), "kind": hottest.get("kind"), "value": hottest.get("value")}
    kind = str(sensor.get("kind") or "other")
    name = str(sensor.get("name") or "").strip()
    return {
        "value": metric_data.get("temperature"),
        "name": name,
        "kind": kind,
        "kind_label": TEMPERATURE_KIND_LABELS.get(kind, "温度传感器"),
        "label": "最高部件温度" if name else "设备最高温度",
        "unit": "°C",
        "source": "server_components" if name else "snmp",
    }


def metric_to_dict(metric) -> Optional[dict]:
    """指标转字典"""
    if not metric:
        return None
    return {
        "id": metric.id,
        "cpu_usage": metric.cpu_usage,
        "memory_usage": metric.memory_usage,
        "memory_total": metric.memory_total,
        "memory_used": metric.memory_used,
        "disk_usage": metric.disk_usage,
        "disk_total": metric.disk_total,
        "disk_used": metric.disk_used,
        "temperature": metric.temperature,
        "temperature_info": _temperature_info({
            "temperature": metric.temperature,
            "custom": metric.custom or {},
            "components": (metric.custom or {}).get("server_components") or {},
        }),
        "power_status": metric.power_status,
        "uptime": metric.uptime,
        "custom": metric.custom or {},
        "components": (metric.custom or {}).get("server_components") or {},
        "collected_at": metric.collected_at.isoformat() if metric.collected_at else None,
    }


def iface_to_dict(iface: DeviceInterface) -> dict:
    """接口转字典（含流量速率）"""
    return {
        "id": iface.id,
        "index": iface.if_index,
        "name": iface.if_name,
        "type": iface.if_type,
        "mtu": iface.if_mtu,
        "speed": iface.if_speed,
        "oper_status": iface.if_oper_status,
        "admin_status": iface.if_admin_status,
        "description": iface.if_description,
        "in_octets": iface.in_octets,
        "out_octets": iface.out_octets,
        "in_bps": iface.in_bps,
        "out_bps": iface.out_bps,
        "in_errors": iface.in_errors,
        "out_errors": iface.out_errors,
        "updated_at": iface.updated_at.isoformat() if iface.updated_at else None,
    }


def _enrich_alerts(db: Session, alerts: List[Alert]) -> List[Dict[str, Any]]:
    """批量补充告警的设备/位置/机房/机柜/U位等上下文信息"""
    if not alerts:
        return []

    device_ids = {a.device_id for a in alerts if a.device_id}
    devices: Dict[int, Device] = {}
    if device_ids:
        devices = {
            d.id: d
            for d in db.query(Device).filter(Device.id.in_(device_ids)).all()
        }

    cabinet_ids = {d.cabinet_id for d in devices.values() if d.cabinet_id}
    cabinets: Dict[int, Cabinet] = {}
    if cabinet_ids:
        cabinets = {
            c.id: c
            for c in db.query(Cabinet).filter(Cabinet.id.in_(cabinet_ids)).all()
        }

    room_ids = {c.room_id for c in cabinets.values() if c.room_id}
    rooms: Dict[int, Room] = {}
    if room_ids:
        rooms = {
            r.id: r for r in db.query(Room).filter(Room.id.in_(room_ids)).all()
        }

    rule_ids = {a.rule_id for a in alerts if getattr(a, "rule_id", None)}
    rules: Dict[int, DeviceAlertRule] = {}
    if rule_ids:
        rules = {
            r.id: r
            for r in db.query(DeviceAlertRule).filter(DeviceAlertRule.id.in_(rule_ids)).all()
        }

    # 告警中心的“当前值”统一取资产最新一次采集值，而不是告警触发时的快照
    latest_metrics: Dict[int, DeviceMetric] = {}
    for device_id in device_ids:
        latest_metrics[device_id] = (
            db.query(DeviceMetric)
            .filter(DeviceMetric.device_id == device_id)
            .order_by(DeviceMetric.collected_at.desc(), DeviceMetric.id.desc())
            .first()
        )

    def current_value_for(alert: Alert, rule: Optional[DeviceAlertRule]) -> Optional[float]:
        metric = latest_metrics.get(alert.device_id)
        if not metric:
            return None
        metric_key = (rule.metric if rule else "") or ""
        if not metric_key:
            metric_key = {
                "cpu": "cpu_usage",
                "memory": "memory_usage",
                "temperature": "temperature",
                "disk": "disk_usage",
                "power": "power",
            }.get(alert.alert_type, "")
        if metric_key == "cpu_usage":
            return metric.cpu_usage
        if metric_key == "memory_usage":
            return metric.memory_usage
        if metric_key == "temperature":
            return metric.temperature
        if metric_key == "disk_usage":
            return metric.disk_usage
        if metric_key == "custom" and rule and rule.custom_key:
            values = metric.custom if isinstance(metric.custom, dict) else {}
            value = values.get(rule.custom_key)
            try:
                return float(value) if value is not None else None
            except (TypeError, ValueError):
                return None
        return None

    items: List[Dict[str, Any]] = []
    for a in alerts:
        device = devices.get(a.device_id)
        cabinet = cabinets.get(device.cabinet_id) if device and device.cabinet_id else None
        room = rooms.get(cabinet.room_id) if cabinet else None
        rule = rules.get(getattr(a, "rule_id", None))
        metric = _alert_metric_detail(a, rule, device)
        current_value = current_value_for(a, rule)

        items.append({
            "id": a.id,
            "source": "device",
            "source_text": "设备",
            "website_target_id": None,
            "device_id": a.device_id,
            "alert_type": a.alert_type,
            "alert_type_text": (
                (rule.name if rule and rule.name else None)
                or ALERT_TYPE_TEXT.get(a.alert_type, a.alert_type)
            ),
            "alert_level": a.alert_level,
            "level_label": getattr(a, "level_label", None),
            "rule_id": getattr(a, "rule_id", None),
            "message": a.message,
            "value": current_value if current_value is not None else a.value,
            "current_value": current_value,
            "current_collected_at": (
                latest_metrics.get(a.device_id).collected_at.isoformat()
                if latest_metrics.get(a.device_id) and latest_metrics[a.device_id].collected_at
                else None
            ),
            "threshold": a.threshold,
            **metric,
            "details": {},
            "is_acknowledged": a.is_acknowledged,
            "is_hidden": bool(a.is_hidden),
            "resolved_at": a.resolved_at.isoformat() if getattr(a, "resolved_at", None) else None,
            "resolution": getattr(a, "resolution", None),
            "is_resolved": bool(getattr(a, "resolved_at", None)),
            "created_at": a.created_at.isoformat() if a.created_at else None,
            # 设备上下文
            "device_name": device.name if device else None,
            "ip_address": device.ip_address if device else None,
            "device_type": device.device_type if device else None,
            "device_type_text": (
                DEVICE_TYPE_TEXT.get(device.device_type, device.device_type)
                if device else None
            ),
            "vendor": device.vendor if device else None,
            "model": device.model if device else None,
            "location": device.location if device else None,
            # 机柜/机房上下文
            "room_name": room.name if room else None,
            "room_floor": room.floor if room else None,
            "room_location": room.location if room else None,
            "cabinet_name": cabinet.name if cabinet else None,
            "u_position": device.u_position if device else None,
            "u_height": (device.u_height or 1) if device else None,
            "power_watts": device.power_watts if device else None,
        })
    return items


def alert_to_dict(db: Session, alert: Alert) -> dict:
    """单条告警转字典（含设备上下文）"""
    items = _enrich_alerts(db, [alert])
    return items[0] if items else {}


def _website_alert_items(db: Session, alerts: List[WebsiteAlert]) -> List[Dict[str, Any]]:
    """网站告警转统一告警结构（供告警中心/首页统一展示）"""
    target_ids = {a.target_id for a in alerts if a.target_id}
    targets: Dict[int, WebsiteTarget] = {}
    if target_ids:
        targets = {
            t.id: t
            for t in db.query(WebsiteTarget).filter(WebsiteTarget.id.in_(target_ids)).all()
        }

    items: List[Dict[str, Any]] = []
    for a in alerts:
        target = targets.get(a.target_id)
        details = a.details if isinstance(a.details, dict) else {}
        slow_threshold = float(target.slow_threshold_ms or 5000) if target else 5000
        if a.alert_type == "slow":
            metric = {
                "metric_key": "response_time",
                "metric_label": "响应时间",
                "metric_unit": "ms",
                "operator": "gt",
                "operator_text": ">",
                "condition_text": f"响应时间 > {slow_threshold:g}ms",
                "rule_name": None,
            }
            value = details.get("response_time")
            threshold = slow_threshold
        elif a.alert_type == "down":
            metric = {
                "metric_key": "availability",
                "metric_label": "网站可用性",
                "metric_unit": "",
                "operator": "eq",
                "operator_text": "=",
                "condition_text": "网站探测不可达",
                "rule_name": None,
            }
            value = None
            threshold = None
        elif a.alert_type == "ssl_expired":
            days_left = details.get("days_left", details.get("days_remaining"))
            metric = {
                "metric_key": "ssl_expiry",
                "metric_label": "SSL 证书剩余天数",
                "metric_unit": "天",
                "operator": "lt",
                "operator_text": "<",
                "condition_text": "SSL 证书已过期",
                "rule_name": None,
            }
            value = days_left
            threshold = 0
        else:
            metric = {
                "metric_key": a.alert_type,
                "metric_label": WEBSITE_ALERT_TYPE_TEXT.get(a.alert_type, a.alert_type),
                "metric_unit": "",
                "operator": "eq",
                "operator_text": "=",
                "condition_text": a.message,
                "rule_name": None,
            }
            value = details.get("response_time")
            threshold = None
        items.append({
            "id": a.id,
            "source": "website",
            "source_text": "网站",
            "website_target_id": a.target_id,
            "device_id": None,
            "alert_type": a.alert_type,
            "alert_type_text": WEBSITE_ALERT_TYPE_TEXT.get(a.alert_type, a.alert_type),
            "alert_level": a.alert_level,
            "level_label": getattr(a, "level_label", None),
            "rule_id": getattr(a, "rule_id", None),
            "message": a.message,
            "value": value,
            "threshold": threshold,
            **metric,
            "details": details,
            "is_acknowledged": a.is_acknowledged,
            "is_hidden": bool(a.is_hidden),
            "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
            "resolution": a.resolution,
            "is_resolved": bool(a.resolved_at),
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "device_name": target.name if target else None,
            "ip_address": (
                (target.domain or target.ip_address) if target else None
            ),
            "device_type": "website",
            "device_type_text": "网站",
            "vendor": None,
            "model": None,
            "location": None,
            "room_name": None,
            "cabinet_name": None,
            "u_position": None,
            "u_height": None,
            "power_watts": None,
            "url": target.url if target else None,
        })
    return items


def _website_alert_query(
    db: Session,
    alert_level: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    alert_type: Optional[str] = None,
    search: Optional[str] = None,
    days: Optional[int] = None,
    hidden: Optional[bool] = None,
):
    """构造网站告警查询"""
    query = db.query(WebsiteAlert)
    if hidden is True:
        query = query.filter(WebsiteAlert.is_hidden.is_(True))
    elif hidden is None:
        query = query.filter(WebsiteAlert.is_hidden.isnot(True))
    if alert_level:
        query = query.filter(WebsiteAlert.alert_level == alert_level)
    if acknowledged is not None:
        query = query.filter(WebsiteAlert.is_acknowledged == acknowledged)
        if acknowledged is False:
            query = query.filter(WebsiteAlert.resolved_at.is_(None))
    if alert_type:
        query = query.filter(WebsiteAlert.alert_type == alert_type)
    if days:
        query = query.filter(
            WebsiteAlert.created_at >= datetime.utcnow() - timedelta(days=int(days))
        )
    if search:
        like = f"%{search}%"
        target_ids = [
            t.id for t in db.query(WebsiteTarget).filter(
                WebsiteTarget.name.like(like)
                | WebsiteTarget.url.like(like)
                | WebsiteTarget.domain.like(like)
                | WebsiteTarget.ip_address.like(like)
            ).all()
        ]
        query = query.filter(
            WebsiteAlert.message.like(like)
            | WebsiteAlert.target_id.in_(target_ids or [-1])
        )
    return query.order_by(WebsiteAlert.created_at.desc(), WebsiteAlert.id.desc())


VM_ALERT_TYPE_TEXT = {
    "vm_cpu": "虚拟机 CPU", "vm_memory": "虚拟机内存",
    "vm_disk": "虚拟机磁盘", "vm_shutdown": "虚拟机已关机",
    "platform_unreachable": "平台连接失败",
    "platform_auth_failed": "平台认证失败",
    "platform_sync_failed": "平台同步失败",
    "platform_sync_stale": "平台同步超时",
    "platform_storage": "平台存储告警",
}
VM_ALERT_METRIC = {
    "vm_cpu": ("cpu_usage", "CPU 使用率", "%"),
    "vm_memory": ("memory_usage", "内存使用率", "%"),
    "vm_disk": ("disk_usage", "磁盘使用率", "%"),
    "vm_shutdown": ("power_state", "虚拟机电源状态", ""),
    "platform_unreachable": ("platform_status", "平台连接状态", ""),
    "platform_auth_failed": ("platform_auth", "平台认证状态", ""),
    "platform_sync_failed": ("platform_sync", "平台同步状态", ""),
    "platform_sync_stale": ("platform_sync", "平台同步状态", ""),
    "platform_storage": ("platform_storage_usage", "平台存储使用率", "%"),
}


def _virtualization_alert_query(
    db: Session,
    alert_level: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    alert_type: Optional[str] = None,
    search: Optional[str] = None,
    days: Optional[int] = None,
    hidden: Optional[bool] = None,
):
    query = db.query(VirtualizationAlert)
    if hidden is True:
        query = query.filter(VirtualizationAlert.is_hidden.is_(True))
    elif hidden is None:
        query = query.filter(VirtualizationAlert.is_hidden.isnot(True))
    if alert_level:
        query = query.filter(VirtualizationAlert.alert_level == alert_level)
    if acknowledged is not None:
        query = query.filter(VirtualizationAlert.is_acknowledged == acknowledged)
    if alert_type:
        query = query.filter(VirtualizationAlert.alert_type == alert_type)
    if days:
        query = query.filter(
            VirtualizationAlert.created_at >= datetime.utcnow() - timedelta(days=int(days))
        )
    if search:
        like = f"%{search}%"
        query = query.filter(
            VirtualizationAlert.message.like(like)
            | VirtualizationAlert.vm_name.like(like)
            | VirtualizationAlert.platform_name.like(like)
        )
    return query.order_by(VirtualizationAlert.created_at.desc(), VirtualizationAlert.id.desc())


def _virtualization_alert_items(db: Session, alerts: List[VirtualizationAlert]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    for a in alerts:
        key, metric_label, metric_unit = VM_ALERT_METRIC.get(
            a.alert_type, (a.alert_type, VM_ALERT_TYPE_TEXT.get(a.alert_type, a.alert_type), "")
        )
        items.append({
            "id": a.id,
            "source": "virtualization",
            "source_text": "虚拟化",
            "website_target_id": None,
            "device_id": None,
            "vm_id": a.vm_id,
            "platform_id": a.platform_id,
            "platform_name": a.platform_name or "",
            "alert_type": a.alert_type,
            "alert_type_text": VM_ALERT_TYPE_TEXT.get(a.alert_type, a.alert_type),
            "alert_level": a.alert_level or "warning",
            "level_label": vm_alert_service.ALERT_LEVEL_TEXT.get(a.alert_level or "warning", a.alert_level or "warning"),
            "rule_id": None,
            "message": a.message,
            "value": a.value,
            "threshold": a.threshold,
            "metric_key": key,
            "metric_label": metric_label,
            "metric_unit": metric_unit,
            "operator": "gt",
            "operator_text": ">",
            "condition_text": a.message,
            "details": {},
            "is_acknowledged": bool(a.is_acknowledged),
            "is_hidden": bool(a.is_hidden),
            "resolved_at": a.resolved_at.isoformat() if a.resolved_at else None,
            "resolution": a.resolution,
            "is_resolved": bool(a.resolved_at),
            "created_at": a.created_at.isoformat() if a.created_at else None,
            "updated_at": a.updated_at.isoformat() if a.updated_at else None,
            "device_name": a.vm_name or a.platform_name or "虚拟化平台",
            "ip_address": None,
            "device_type": "virtualization",
            "device_type_text": "虚拟机",
            "vendor": None,
            "model": None,
            "location": a.platform_name or "",
            "room_name": None,
            "cabinet_name": None,
            "u_position": None,
            "u_height": None,
            "power_watts": None,
        })
    return items


def _virtualization_active_items(
    db: Session,
    alert_level: Optional[str] = None,
    alert_type: Optional[str] = None,
    search: Optional[str] = None,
    days: Optional[int] = None,
    limit: int = 100000,
) -> List[Dict[str, Any]]:
    """虚拟化活动告警：只要求未恢复，已确认仍继续展示/播报。"""
    query = _virtualization_alert_query(
        db, alert_level, None, alert_type, search, days,
    ).filter(VirtualizationAlert.resolved_at.is_(None))
    return _virtualization_alert_items(db, query.limit(limit).all())


def _merged_alert_items(
    db: Session,
    alert_level: Optional[str] = None,
    acknowledged: Optional[bool] = None,
    alert_type: Optional[str] = None,
    device_id: Optional[int] = None,
    search: Optional[str] = None,
    days: Optional[int] = None,
    source: Optional[str] = None,
    visible_device_ids: Optional[List[int]] = None,
    limit: int = 20000,
    include_virtualization: bool = True,
    hidden: Optional[bool] = None,
) -> List[Dict[str, Any]]:
    """合并设备/网站/虚拟化告警，按时间倒序返回。"""
    if source not in ("website", "virtualization"):
        reconcile_metric_alerts(db, visible_device_ids)
    items: List[Dict[str, Any]] = []
    if source not in ("website", "virtualization"):
        device_alerts = _alert_query(
            db, alert_level, acknowledged, alert_type, device_id, search, days,
            visible_device_ids=visible_device_ids, hidden=hidden,
        ).limit(limit).all()
        items.extend(_enrich_alerts(db, device_alerts))
    if source not in ("device", "virtualization") and not device_id:
        website_alerts = _website_alert_query(
            db, alert_level, acknowledged, alert_type, search, days, hidden=hidden
        ).limit(limit).all()
        items.extend(_website_alert_items(db, website_alerts))
    if include_virtualization and source not in ("device", "website") and not device_id:
        vm_alerts = _virtualization_alert_query(
            db, alert_level, acknowledged, alert_type, search, days, hidden=hidden
        ).limit(limit).all()
        items.extend(_virtualization_alert_items(db, vm_alerts))
    items.sort(key=lambda item: (item.get("created_at") or "", item.get("id") or 0), reverse=True)
    return items
