"""仪表盘 / 拓扑图 / 大屏共享与编辑申请。"""
from __future__ import annotations

import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..models.sharing import SharedEditRequest, SharedResource, SharedResourceMember
from ..models.user import User
from ..services.auth import get_current_user

router = APIRouter(prefix="/api/sharing", tags=["共享"])

RESOURCE_TYPES = {"dashboard", "topology", "bigscreen"}
MAX_CONFIG_BYTES = 2 * 1024 * 1024


def _user_dict(user: Optional[User]) -> Dict[str, Any]:
    if not user:
        return {}
    return {
        "id": user.id,
        "username": user.username,
        "real_name": user.real_name or user.username,
        "is_superuser": bool(user.is_superuser),
    }


def _parse_config(resource: SharedResource) -> Any:
    try:
        return json.loads(resource.config_json or "{}")
    except (TypeError, ValueError):
        return {}


def _member(resource: SharedResource, user_id: int) -> Optional[SharedResourceMember]:
    return next((member for member in resource.members if member.user_id == user_id), None)


def _pending_request(resource_id: int, user_id: int, db: Session) -> Optional[SharedEditRequest]:
    return (
        db.query(SharedEditRequest)
        .filter(
            SharedEditRequest.resource_id == resource_id,
            SharedEditRequest.user_id == user_id,
            SharedEditRequest.status == "pending",
        )
        .order_by(SharedEditRequest.id.desc())
        .first()
    )


def _resource_payload(
    resource: SharedResource,
    current: User,
    db: Session,
    *,
    include_members: bool = False,
) -> Dict[str, Any]:
    is_owner = resource.owner_id == current.id
    member = _member(resource, current.id)
    pending = _pending_request(resource.id, current.id, db)
    if not is_owner and not member:
        raise HTTPException(status_code=403, detail="没有该共享资源的访问权限")
    payload: Dict[str, Any] = {
        "id": resource.id,
        "resource_type": resource.resource_type,
        "resource_key": resource.resource_key,
        "title": resource.title or "",
        "owner": _user_dict(db.query(User).filter(User.id == resource.owner_id).first()),
        "is_owner": is_owner,
        "can_edit": bool(is_owner or (member and member.can_edit)),
        "config": _parse_config(resource),
        "created_at": resource.created_at.isoformat() if resource.created_at else None,
        "updated_at": resource.updated_at.isoformat() if resource.updated_at else None,
        "pending_request": (
            {
                "id": pending.id,
                "status": pending.status,
                "created_at": pending.created_at.isoformat() if pending.created_at else None,
            }
            if pending and not is_owner else None
        ),
        "member_count": len(resource.members),
    }
    if include_members and is_owner:
        payload["members"] = [
            {
                "user": _user_dict(db.query(User).filter(User.id == member.user_id).first()),
                "can_edit": bool(member.can_edit),
                "created_at": member.created_at.isoformat() if member.created_at else None,
            }
            for member in resource.members
        ]
        requests = (
            db.query(SharedEditRequest)
            .filter(SharedEditRequest.resource_id == resource.id, SharedEditRequest.status == "pending")
            .order_by(SharedEditRequest.created_at.asc())
            .all()
        )
        payload["requests"] = [
            {
                "id": item.id,
                "user": _user_dict(db.query(User).filter(User.id == item.user_id).first()),
                "message": item.message or "",
                "status": item.status,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in requests
        ]
    return payload


def _get_resource(resource_id: int, db: Session) -> SharedResource:
    resource = db.query(SharedResource).filter(SharedResource.id == resource_id).first()
    if not resource:
        raise HTTPException(status_code=404, detail="共享资源不存在")
    return resource


@router.get("/users")
def list_share_users(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    users = (
        db.query(User)
        .filter(User.is_active.is_(True), User.id != current.id)
        .order_by(User.username.asc())
        .all()
    )
    return {"items": [_user_dict(user) for user in users]}


@router.post("/resources")
def create_or_update_resource(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    resource_type = str(payload.get("resource_type") or "").strip()
    resource_key = str(payload.get("resource_key") or "").strip()
    if resource_type not in RESOURCE_TYPES:
        raise HTTPException(status_code=400, detail="不支持的共享资源类型")
    if not resource_key or len(resource_key) > 100:
        raise HTTPException(status_code=400, detail="资源标识不能为空且不能超过 100 字符")
    title = str(payload.get("title") or "").strip()[:200]
    config = payload.get("config", {})
    if config is not None:
        try:
            config_text = json.dumps(config, ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="共享配置无法序列化") from exc
        if len(config_text.encode("utf-8")) > MAX_CONFIG_BYTES:
            raise HTTPException(status_code=400, detail="共享配置不能超过 2MB")
    else:
        config_text = None

    resource = (
        db.query(SharedResource)
        .filter(
            SharedResource.resource_type == resource_type,
            SharedResource.resource_key == resource_key,
            SharedResource.owner_id == current.id,
        )
        .first()
    )
    if not resource:
        resource = SharedResource(
            resource_type=resource_type,
            resource_key=resource_key,
            owner_id=current.id,
            title=title,
            config_json=config_text or "{}",
        )
        db.add(resource)
    else:
        if title:
            resource.title = title
        if config_text is not None:
            resource.config_json = config_text
        resource.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(resource)
    return {"resource": _resource_payload(resource, current, db, include_members=True)}


@router.get("/owned")
def list_owned_resources(
    resource_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if resource_type and resource_type not in RESOURCE_TYPES:
        raise HTTPException(status_code=400, detail="不支持的共享资源类型")
    query = db.query(SharedResource).filter(SharedResource.owner_id == current.id)
    if resource_type:
        query = query.filter(SharedResource.resource_type == resource_type)
    resources = query.order_by(SharedResource.updated_at.desc()).all()
    return {
        "items": [
            _resource_payload(resource, current, db, include_members=True)
            for resource in resources
        ]
    }


@router.get("/shared-with-me")
def list_shared_with_me(
    resource_type: Optional[str] = Query(None),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if resource_type and resource_type not in RESOURCE_TYPES:
        raise HTTPException(status_code=400, detail="不支持的共享资源类型")
    query = (
        db.query(SharedResource)
        .join(SharedResourceMember, SharedResourceMember.resource_id == SharedResource.id)
        .filter(SharedResourceMember.user_id == current.id)
    )
    if resource_type:
        query = query.filter(SharedResource.resource_type == resource_type)
    resources = query.order_by(SharedResource.updated_at.desc()).all()
    return {
        "items": [
            {
                **_resource_payload(resource, current, db),
                "config": None,
            }
            for resource in resources
        ]
    }


@router.get("/requests")
def list_edit_requests(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    resources = db.query(SharedResource).filter(SharedResource.owner_id == current.id).all()
    ids = [resource.id for resource in resources]
    if not ids:
        return {"items": []}
    requests = (
        db.query(SharedEditRequest)
        .filter(SharedEditRequest.resource_id.in_(ids))
        .order_by(SharedEditRequest.status.asc(), SharedEditRequest.created_at.desc())
        .limit(100)
        .all()
    )
    resource_map = {resource.id: resource for resource in resources}
    return {
        "items": [
            {
                "id": item.id,
                "resource_id": item.resource_id,
                "resource_title": resource_map[item.resource_id].title,
                "resource_type": resource_map[item.resource_id].resource_type,
                "user": _user_dict(db.query(User).filter(User.id == item.user_id).first()),
                "message": item.message or "",
                "status": item.status,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in requests
        ]
    }


@router.get("/resources/{resource_id}")
def get_resource(
    resource_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    resource = _get_resource(resource_id, db)
    payload = _resource_payload(resource, current, db, include_members=True)
    if not payload.get("is_owner"):
        payload.pop("members", None)
        payload.pop("requests", None)
    return {"resource": payload}


@router.put("/resources/{resource_id}")
def update_resource(
    resource_id: int,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    resource = _get_resource(resource_id, db)
    member = _member(resource, current.id)
    if resource.owner_id != current.id and not (member and member.can_edit):
        raise HTTPException(status_code=403, detail="没有编辑该共享资源的权限")
    if "config" in payload:
        try:
            config_text = json.dumps(payload.get("config"), ensure_ascii=False, separators=(",", ":"))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="共享配置无法序列化") from exc
        if len(config_text.encode("utf-8")) > MAX_CONFIG_BYTES:
            raise HTTPException(status_code=400, detail="共享配置不能超过 2MB")
        resource.config_json = config_text
    if "title" in payload:
        resource.title = str(payload.get("title") or "").strip()[:200]
    resource.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(resource)
    return {"resource": _resource_payload(resource, current, db, include_members=True)}


@router.delete("/resources/{resource_id}")
def delete_resource(
    resource_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    resource = _get_resource(resource_id, db)
    if resource.owner_id != current.id:
        raise HTTPException(status_code=403, detail="只有所有者可以删除共享资源")
    db.delete(resource)
    db.commit()
    return {"message": "共享资源已删除"}


@router.post("/resources/{resource_id}/members")
def update_members(
    resource_id: int,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    resource = _get_resource(resource_id, db)
    if resource.owner_id != current.id:
        raise HTTPException(status_code=403, detail="只有所有者可以管理共享成员")
    raw_ids = payload.get("user_ids") or []
    if not isinstance(raw_ids, list):
        raise HTTPException(status_code=400, detail="user_ids 必须是数组")
    user_ids = []
    for item in raw_ids:
        try:
            uid = int(item)
        except (TypeError, ValueError):
            continue
        if uid and uid != current.id and uid not in user_ids:
            user_ids.append(uid)
    users = db.query(User).filter(User.id.in_(user_ids), User.is_active.is_(True)).all() if user_ids else []
    valid_ids = {user.id for user in users}
    existing = {member.user_id for member in resource.members}
    for user_id in valid_ids - existing:
        db.add(SharedResourceMember(resource_id=resource.id, user_id=user_id, can_edit=False))
    for member in list(resource.members):
        if member.user_id not in valid_ids:
            db.delete(member)
    db.commit()
    db.refresh(resource)
    return {"resource": _resource_payload(resource, current, db, include_members=True)}


@router.delete("/resources/{resource_id}/members/{user_id}")
def remove_member(
    resource_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    resource = _get_resource(resource_id, db)
    if resource.owner_id != current.id:
        raise HTTPException(status_code=403, detail="只有所有者可以管理共享成员")
    member = _member(resource, user_id)
    if member:
        db.delete(member)
        db.query(SharedEditRequest).filter(
            SharedEditRequest.resource_id == resource.id,
            SharedEditRequest.user_id == user_id,
            SharedEditRequest.status == "pending",
        ).delete(synchronize_session=False)
        db.commit()
    return {"message": "成员已移除"}


@router.post("/resources/{resource_id}/edit-request")
def request_edit(
    resource_id: int,
    payload: Dict[str, Any] = Body(default={}),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    resource = _get_resource(resource_id, db)
    if resource.owner_id == current.id:
        raise HTTPException(status_code=400, detail="所有者无需申请编辑权限")
    member = _member(resource, current.id)
    if not member:
        raise HTTPException(status_code=403, detail="没有该共享资源的访问权限")
    if member.can_edit:
        return {"request": None, "message": "已拥有编辑权限"}
    existing = _pending_request(resource.id, current.id, db)
    if existing:
        return {"request": {"id": existing.id, "status": existing.status}, "message": "编辑申请已提交，等待所有者审批"}
    item = SharedEditRequest(
        resource_id=resource.id,
        user_id=current.id,
        status="pending",
        message=str(payload.get("message") or "").strip()[:500],
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return {"request": {"id": item.id, "status": item.status}, "message": "编辑申请已提交"}


@router.post("/requests/{request_id}/approve")
def approve_request(
    request_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    item = db.query(SharedEditRequest).filter(SharedEditRequest.id == request_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="编辑申请不存在")
    resource = _get_resource(item.resource_id, db)
    if resource.owner_id != current.id:
        raise HTTPException(status_code=403, detail="只有所有者可以审批编辑申请")
    item.status = "approved"
    item.decided_at = datetime.utcnow()
    item.reviewer_id = current.id
    member = _member(resource, item.user_id)
    if member:
        member.can_edit = True
    else:
        db.add(SharedResourceMember(resource_id=resource.id, user_id=item.user_id, can_edit=True))
    db.commit()
    return {"message": "已同意编辑申请"}


@router.post("/requests/{request_id}/reject")
def reject_request(
    request_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    item = db.query(SharedEditRequest).filter(SharedEditRequest.id == request_id).first()
    if not item:
        raise HTTPException(status_code=404, detail="编辑申请不存在")
    resource = _get_resource(item.resource_id, db)
    if resource.owner_id != current.id:
        raise HTTPException(status_code=403, detail="只有所有者可以审批编辑申请")
    item.status = "rejected"
    item.decided_at = datetime.utcnow()
    item.reviewer_id = current.id
    db.commit()
    return {"message": "已拒绝编辑申请"}
