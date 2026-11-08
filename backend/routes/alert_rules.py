"""自定义告警规则接口"""
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..models.alert_rule import DeviceAlertRule
from ..models.database import get_db
from ..models.models import Device
from ..models.notifications import NotificationChannel
from ..models.user import User
from ..services import alert_rules as rule_service
from ..services import asset_scope
from ..services import auth as auth_service

router = APIRouter(prefix="/api/alert-rules", tags=["资产告警规则"])


class AlertRulePayload(BaseModel):
    device_id: int
    name: str = Field(..., min_length=1, max_length=100)
    metric: str
    custom_key: Optional[str] = Field(None, max_length=100)
    operator: str = "gt"
    threshold: float
    level: str = "warning"
    level_label: Optional[str] = Field(None, max_length=50)
    notify_channel_ids: List[int] = Field(default_factory=list, max_length=100)
    enabled: bool = True


def _require(current: User, write: bool = False) -> None:
    permission = "assets:edit" if write else "assets:view"
    if not auth_service.has_permission(current, permission):
        raise HTTPException(status_code=403, detail=f"无权限执行该操作（{permission}）")


def _validate_device(db: Session, request: Request, device_id: int) -> Device:
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    asset_scope.require_device_access(db, request, device)
    return device


def _validate_payload(db: Session, payload: AlertRulePayload) -> AlertRulePayload:
    if payload.metric not in rule_service.METRICS:
        raise HTTPException(status_code=400, detail="不支持的告警指标")
    if payload.operator not in rule_service.OPERATORS:
        raise HTTPException(status_code=400, detail="不支持的比较条件")
    if payload.level not in rule_service.LEVELS:
        raise HTTPException(status_code=400, detail="不支持的告警级别")
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="规则名称不能为空")
    if rule_service.METRICS[payload.metric].get("requires_key") and not (payload.custom_key or "").strip():
        raise HTTPException(status_code=400, detail="自定义指标必须填写指标 key")
    if payload.notify_channel_ids:
        unique_ids = list(dict.fromkeys(int(item) for item in payload.notify_channel_ids))
        exists = db.query(NotificationChannel.id).filter(NotificationChannel.id.in_(unique_ids)).all()
        found = {row[0] for row in exists}
        missing = [item for item in unique_ids if item not in found]
        if missing:
            raise HTTPException(status_code=400, detail=f"通知通道不存在：{missing}")
        payload.notify_channel_ids = unique_ids
    else:
        payload.notify_channel_ids = []
    payload.metric = payload.metric.strip()
    payload.custom_key = (payload.custom_key or "").strip() or None
    payload.name = payload.name.strip()
    return payload


def _rule(db: Session, rule_id: int, request: Request) -> DeviceAlertRule:
    rule = db.query(DeviceAlertRule).filter(DeviceAlertRule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="告警规则不存在")
    _validate_device(db, request, rule.device_id)
    return rule


@router.get("/channels")
def list_rule_channels(
    db: Session = Depends(get_db),
    current: User = Depends(auth_service.get_current_user),
):
    _require(current)
    channels = db.query(NotificationChannel).order_by(NotificationChannel.id).all()
    return [
        {
            "id": channel.id,
            "name": channel.name,
            "channel_type": channel.channel_type,
            "enabled": bool(channel.enabled),
            "min_level": channel.min_level,
        }
        for channel in channels
    ]


@router.get("")
def list_rules(
    device_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(auth_service.get_current_user),
):
    _require(current)
    _validate_device(db, request, device_id)
    rules = (
        db.query(DeviceAlertRule)
        .filter(DeviceAlertRule.device_id == device_id)
        .order_by(DeviceAlertRule.id.desc())
        .all()
    )
    return [rule_service.rule_to_dict(rule) for rule in rules]


@router.post("")
def create_rule(
    payload: AlertRulePayload,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(auth_service.get_current_user),
):
    _require(current, write=True)
    _validate_device(db, request, payload.device_id)
    _validate_payload(db, payload)
    rule = DeviceAlertRule(
        device_id=payload.device_id,
        name=payload.name,
        metric=payload.metric,
        custom_key=payload.custom_key,
        operator=payload.operator,
        threshold=payload.threshold,
        level=payload.level,
        level_label=payload.level_label,
        notify_channel_ids=payload.notify_channel_ids,
        enabled=payload.enabled,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule_service.rule_to_dict(rule)


@router.put("/{rule_id}")
def update_rule(
    rule_id: int,
    payload: AlertRulePayload,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(auth_service.get_current_user),
):
    _require(current, write=True)
    rule = _rule(db, rule_id, request)
    if payload.device_id != rule.device_id:
        _validate_device(db, request, payload.device_id)
    _validate_payload(db, payload)
    rule.name = payload.name
    rule.metric = payload.metric
    rule.custom_key = payload.custom_key
    rule.operator = payload.operator
    rule.threshold = payload.threshold
    rule.level = payload.level
    rule.level_label = payload.level_label
    rule.notify_channel_ids = payload.notify_channel_ids
    rule.enabled = payload.enabled
    db.commit()
    db.refresh(rule)
    return rule_service.rule_to_dict(rule)


@router.delete("/{rule_id}")
def delete_rule(
    rule_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(auth_service.get_current_user),
):
    _require(current, write=True)
    rule = _rule(db, rule_id, request)
    db.delete(rule)
    db.commit()
    return {"deleted": 1}
