"""资产群组访问范围

规则：
- 超级管理员：可见全部设备
- 普通用户：可见其所属群组的设备；没有加入任何群组时，只能看到未分组设备
"""
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models.models import Device
from ..models.user import User


def get_current_user(db: Session, request) -> Optional[User]:
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        return None
    return db.query(User).filter(User.id == int(user_id)).first()


def allowed_group_ids(db: Session, request) -> Optional[List[int]]:
    """返回 None 表示不受限（超级管理员）"""
    user = get_current_user(db, request)
    if user is None or user.is_superuser:
        return None
    return [group.id for group in user.groups]


def scope_device_query(db: Session, request, query=None):
    query = query if query is not None else db.query(Device)
    group_ids = allowed_group_ids(db, request)
    if group_ids is None:
        return query
    if group_ids:
        return query.filter(Device.group_id.in_(group_ids))
    return query.filter(Device.group_id.is_(None))


def can_access_device(db: Session, request, device: Device) -> bool:
    group_ids = allowed_group_ids(db, request)
    if group_ids is None:
        return True
    if group_ids:
        return device.group_id in group_ids
    return device.group_id is None


def require_device_access(db: Session, request, device: Device) -> None:
    if not can_access_device(db, request, device):
        raise HTTPException(status_code=403, detail="无权访问该群组的设备")


def can_access_device_for_user(db: Session, user: Optional[User], device: Device) -> bool:
    """按用户所属群组判断设备可见性（供 WebSocket 等无 request 场景使用）。"""
    if user is None:
        return False
    if user.is_superuser:
        return True
    group_ids = [group.id for group in user.groups]
    if group_ids:
        return device.group_id in group_ids
    return device.group_id is None


def visible_device_ids(db: Session, request) -> Optional[List[int]]:
    """返回可见设备 ID；None 表示全部可见"""
    group_ids = allowed_group_ids(db, request)
    if group_ids is None:
        return None
    query = db.query(Device.id)
    if group_ids:
        query = query.filter(Device.group_id.in_(group_ids))
    else:
        query = query.filter(Device.group_id.is_(None))
    return [row[0] for row in query.all()]
