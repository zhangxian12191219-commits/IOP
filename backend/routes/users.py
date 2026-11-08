"""用户 / 角色 / 群组 管理接口"""
from datetime import datetime
from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..models.schemas import (
    GroupCreate, GroupUpdate, RoleCreate, RoleUpdate, UserCreate, UserUpdate,
)
from ..models.user import Group, Role, User
from ..services.auth import (
    ALL_PERMISSIONS, PERMISSIONS, get_current_user, hash_password,
    user_permission_set, user_to_dict, verify_password,
)
from ..services import audit
from ..services import password_policy
from ..services import settings as settings_service

users_router = APIRouter(prefix="/api/users", tags=["用户管理"])
roles_router = APIRouter(prefix="/api/roles", tags=["角色管理"])
groups_router = APIRouter(prefix="/api/groups", tags=["群组管理"])


# ==================== 工具 ====================
def _require_superuser(current: User = Depends(get_current_user)) -> User:
    if not current.is_superuser:
        raise HTTPException(status_code=403, detail="用户/角色/群组管理仅超级管理员可操作")
    return current


def _role_to_dict(role: Role) -> dict:
    return {
        "id": role.id,
        "name": role.name,
        "code": role.code,
        "description": role.description,
        "permissions": role.permissions or [],
        "is_builtin": bool(role.is_builtin),
        "user_count": len(role.users or []),
        "created_at": role.created_at.isoformat() if role.created_at else None,
    }


def _group_to_dict(group: Group) -> dict:
    return {
        "id": group.id,
        "name": group.name,
        "code": group.code,
        "description": group.description,
        "user_count": len(group.users or []),
        "created_at": group.created_at.isoformat() if group.created_at else None,
    }


def _get_user(db: Session, user_id: int) -> User:
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    return user


def _bind_roles(db: Session, user: User, role_ids: List[int]) -> None:
    if not role_ids:
        user.roles = []
        return
    roles = db.query(Role).filter(Role.id.in_(role_ids)).all()
    if len(roles) != len(set(role_ids)):
        raise HTTPException(status_code=400, detail="部分角色不存在")
    user.roles = roles


def _bind_groups(db: Session, user: User, group_ids: List[int]) -> None:
    if not group_ids:
        user.groups = []
        return
    groups = db.query(Group).filter(Group.id.in_(group_ids)).all()
    if len(groups) != len(set(group_ids)):
        raise HTTPException(status_code=400, detail="部分群组不存在")
    user.groups = groups


def _guard_superuser_count(db: Session, exclude_id: Optional[int] = None) -> int:
    query = db.query(User).filter(User.is_superuser == True)  # noqa: E712
    if exclude_id is not None:
        query = query.filter(User.id != exclude_id)
    return query.count()


def _user_audit_snapshot(user: User) -> dict:
    """用户审计快照（不含密码哈希）"""
    return {
        "username": user.username,
        "real_name": user.real_name,
        "email": user.email,
        "phone": user.phone,
        "is_active": bool(user.is_active),
        "is_superuser": bool(user.is_superuser),
        "role_ids": sorted(r.id for r in (user.roles or [])),
        "group_ids": sorted(g.id for g in (user.groups or [])),
    }


# ==================== 权限点目录 ====================
@users_router.get("/permissions")
def list_permissions(current: User = Depends(_require_superuser)):
    """权限点目录（仅超级管理员，按模块分组，供角色配置）"""
    grouped: Dict[str, List[dict]] = {}
    for item in PERMISSIONS:
        grouped.setdefault(item["module"], []).append({
            "code": item["code"],
            "name": item["name"],
            "module": item["module"],
            "description": item.get("description", ""),
        })
    return {
        "all": PERMISSIONS,
        "grouped": [{"module": k, "permissions": v} for k, v in grouped.items()],
        "special": [{"code": "*", "name": "全部权限（超级角色）"}],
        "total": len(ALL_PERMISSIONS),
    }


# ==================== 用户 ====================
@users_router.get("")
def list_users(
    db: Session = Depends(get_db),
    keyword: Optional[str] = None,
    group_id: Optional[int] = None,
    role_id: Optional[int] = None,
    current: User = Depends(_require_superuser),
):
    """用户列表（仅超级管理员）"""
    query = db.query(User)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(User.username.like(like) | User.real_name.like(like))
    if group_id:
        query = query.filter(User.groups.any(Group.id == group_id))
    if role_id:
        query = query.filter(User.roles.any(Role.id == role_id))

    users = query.order_by(User.id).all()
    return {
        "total": len(users),
        "items": [user_to_dict(u) for u in users],
    }


@users_router.post("")
def create_user(
    payload: UserCreate,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(_require_superuser),
):
    """新增用户（仅超级管理员）"""
    username = payload.username.strip()
    if db.query(User).filter(User.username == username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    if payload.is_superuser and not current.is_superuser:
        raise HTTPException(status_code=403, detail="只有超级管理员可以创建超级管理员")

    password_policy.validate_password(db, payload.password)
    user = User(
        username=username,
        password_hash=hash_password(payload.password),
        real_name=payload.real_name,
        email=payload.email,
        phone=payload.phone,
        is_active=payload.is_active,
        is_superuser=payload.is_superuser,
        password_changed_at=datetime.utcnow(),
        must_change_password=bool(settings_service.get_value(db, "first_login_password_change")),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    _bind_roles(db, user, payload.role_ids)
    _bind_groups(db, user, payload.group_ids)
    db.add(user)
    db.commit()
    db.refresh(user)
    audit.record(
        db, request, module="users", action="create",
        target_type="user", target_id=user.id, target_name=user.username,
        after=_user_audit_snapshot(user),
        message=f"新增用户 {user.username}",
    )
    return user_to_dict(user)


@users_router.get("/me")
def get_my_account(current: User = Depends(get_current_user)):
    """当前登录用户自己的账号信息。"""
    return user_to_dict(current)


@users_router.put("/me")
def update_my_account(
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """普通用户只能修改自己的用户名和密码；必须验证当前密码。"""
    data = payload.model_dump(exclude_unset=True)
    allowed = {"username", "password", "old_password"}
    extra = set(data) - allowed
    if extra:
        raise HTTPException(status_code=403, detail="只能修改自己的用户名和密码")
    if not data.get("username") and not data.get("password"):
        raise HTTPException(status_code=400, detail="请填写新的用户名或密码")

    if not data.get("old_password") or not verify_password(data["old_password"], current.password_hash):
        raise HTTPException(status_code=400, detail="当前密码不正确")

    before = _user_audit_snapshot(current)
    username = data.get("username")
    if username is not None:
        username = str(username).strip()
        if len(username) < 2 or len(username) > 64:
            raise HTTPException(status_code=400, detail="用户名长度需为 2~64 个字符")
        if db.query(User).filter(User.username == username, User.id != current.id).first():
            raise HTTPException(status_code=400, detail="用户名已存在")
        current.username = username
    if data.get("password"):
        password_policy.validate_password(db, data["password"])
        current.password_hash = hash_password(data["password"])
        current.password_changed_at = datetime.utcnow()
        current.must_change_password = False
    current.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(current)

    after = _user_audit_snapshot(current)
    if data.get("password"):
        after["password"] = "******"
    audit.record(
        db, request, module="users", action="update",
        target_type="user", target_id=current.id, target_name=current.username,
        before=before, after=after,
        message="用户修改了自己的账号密码",
    )
    return user_to_dict(current)


@users_router.put("/{user_id}")
def update_user(
    user_id: int,
    payload: UserUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """更新用户（密码留空表示不修改）"""
    user = _get_user(db, user_id)
    before = _user_audit_snapshot(user)
    data = payload.model_dump(exclude_unset=True)

    if not current.is_superuser:
        if user.id != current.id:
            raise HTTPException(status_code=403, detail="普通用户只能修改自己的账号")
        extra = set(data) - {"username", "password", "old_password"}
        if extra:
            raise HTTPException(status_code=403, detail="普通用户只能修改自己的用户名和密码")
        if not data.get("old_password") or not verify_password(data["old_password"], current.password_hash):
            raise HTTPException(status_code=400, detail="当前密码不正确")

    if data.get("username") is not None:
        username = str(data["username"]).strip()
        if len(username) < 2 or len(username) > 64:
            raise HTTPException(status_code=400, detail="用户名长度需为 2~64 个字符")
        if db.query(User).filter(User.username == username, User.id != user.id).first():
            raise HTTPException(status_code=400, detail="用户名已存在")
        user.username = username

    if "is_superuser" in data:
        if not current.is_superuser:
            raise HTTPException(status_code=403, detail="只有超级管理员可以调整超级管理员身份")
        if user.is_superuser and not data["is_superuser"]:
            if _guard_superuser_count(db, exclude_id=user.id) == 0:
                raise HTTPException(status_code=400, detail="系统至少需要保留一个超级管理员")
        user.is_superuser = bool(data["is_superuser"])

    if "is_active" in data:
        if user.id == current.id and not data["is_active"]:
            raise HTTPException(status_code=400, detail="不能禁用当前登录的账号")
        if user.is_superuser and not data["is_active"]:
            if _guard_superuser_count(db, exclude_id=user.id) == 0:
                raise HTTPException(status_code=400, detail="系统至少需要保留一个启用的超级管理员")
        user.is_active = bool(data["is_active"])

    for field in ("real_name", "email", "phone"):
        if field in data:
            setattr(user, field, data[field])

    if data.get("password"):
        password_policy.validate_password(db, data["password"])
        user.password_hash = hash_password(data["password"])
        user.password_changed_at = datetime.utcnow()
        if user.id == current.id:
            user.must_change_password = False
        else:
            user.must_change_password = bool(
                settings_service.get_value(db, "first_login_password_change")
            )
    if "role_ids" in data:
        _bind_roles(db, user, data["role_ids"] or [])
    if "group_ids" in data:
        _bind_groups(db, user, data["group_ids"] or [])

    user.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(user)
    after = _user_audit_snapshot(user)
    if data.get("password"):
        after["password"] = "******"
    audit.record(
        db, request, module="users", action="update",
        target_type="user", target_id=user.id, target_name=user.username,
        before=before, after=after,
        message=f"更新用户 {user.username}",
    )
    return user_to_dict(user)


@users_router.post("/{user_id}/reset-password")
def reset_password(
    user_id: int,
    payload: dict,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(_require_superuser),
):
    """管理员重置用户密码（仅超级管理员）"""
    password = (payload or {}).get("password") or ""
    password_policy.validate_password(db, password)
    user = _get_user(db, user_id)
    user.password_hash = hash_password(password)
    user.password_changed_at = datetime.utcnow()
    user.must_change_password = bool(settings_service.get_value(db, "first_login_password_change"))
    user.updated_at = datetime.utcnow()
    db.commit()
    audit.record(
        db, request, module="users", action="update",
        target_type="user", target_id=user.id, target_name=user.username,
        after={"password": "******"},
        message=f"管理员重置了用户 {user.username} 的密码",
    )
    return {"message": "密码已重置"}


@users_router.delete("/{user_id}")
def delete_user(
    user_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(_require_superuser),
):
    """删除用户（仅超级管理员）"""
    if user_id == current.id:
        raise HTTPException(status_code=400, detail="不能删除当前登录的账号")
    user = _get_user(db, user_id)
    if user.is_superuser and _guard_superuser_count(db, exclude_id=user.id) == 0:
        raise HTTPException(status_code=400, detail="系统至少需要保留一个超级管理员")

    before = _user_audit_snapshot(user)
    username = user.username
    user.roles = []
    user.groups = []
    db.delete(user)
    db.commit()
    audit.record(
        db, request, module="users", action="delete",
        target_type="user", target_id=user_id, target_name=username,
        before=before, message=f"删除用户 {username}",
    )
    return {"message": "用户已删除"}


# ==================== 角色 ====================
@roles_router.get("")
def list_roles(db: Session = Depends(get_db), current: User = Depends(_require_superuser)):
    """角色列表（仅超级管理员）"""
    roles = db.query(Role).order_by(Role.id).all()
    return {
        "total": len(roles),
        "items": [_role_to_dict(r) for r in roles],
    }


@roles_router.post("")
def create_role(
    payload: RoleCreate,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(_require_superuser),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="角色名称不能为空")
    if db.query(Role).filter(Role.name == name).first():
        raise HTTPException(status_code=400, detail="角色名称已存在")

    perms = payload.permissions or []
    unknown = [p for p in perms if p != "*" and p not in ALL_PERMISSIONS]
    if unknown:
        raise HTTPException(status_code=400, detail=f"未知权限点: {', '.join(unknown)}")

    role = Role(
        name=name,
        code=(payload.code or None),
        description=payload.description,
        permissions=perms,
        is_builtin=False,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(role)
    db.commit()
    db.refresh(role)
    audit.record(
        db, request, module="roles", action="create",
        target_type="role", target_id=role.id, target_name=role.name,
        after={"name": role.name, "code": role.code,
               "description": role.description, "permissions": role.permissions},
        message=f"新增角色 {role.name}",
    )
    return _role_to_dict(role)


@roles_router.put("/{role_id}")
def update_role(
    role_id: int,
    payload: RoleUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(_require_superuser),
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")

    before = {
        "name": role.name, "code": role.code,
        "description": role.description, "permissions": list(role.permissions or []),
    }
    data = payload.model_dump(exclude_unset=True)

    if "permissions" in data:
        if role.code == "admin":
            raise HTTPException(status_code=400, detail="内置超级管理员角色的权限不可修改")
        perms = data["permissions"] or []
        unknown = [p for p in perms if p != "*" and p not in ALL_PERMISSIONS]
        if unknown:
            raise HTTPException(status_code=400, detail=f"未知权限点: {', '.join(unknown)}")
        role.permissions = perms

    if "name" in data and data["name"]:
        name = data["name"].strip()
        dup = db.query(Role).filter(Role.name == name, Role.id != role.id).first()
        if dup:
            raise HTTPException(status_code=400, detail="角色名称已存在")
        role.name = name
    if "description" in data:
        role.description = data["description"]
    if "code" in data and not role.is_builtin:
        role.code = data["code"]

    role.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(role)
    audit.record(
        db, request, module="roles", action="update",
        target_type="role", target_id=role.id, target_name=role.name,
        before=before,
        after={
            "name": role.name, "code": role.code,
            "description": role.description,
            "permissions": list(role.permissions or []),
        },
        message=f"更新角色 {role.name}",
    )
    return _role_to_dict(role)


@roles_router.delete("/{role_id}")
def delete_role(
    role_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(_require_superuser),
):
    role = db.query(Role).filter(Role.id == role_id).first()
    if not role:
        raise HTTPException(status_code=404, detail="角色不存在")
    if role.is_builtin:
        raise HTTPException(status_code=400, detail="内置角色不允许删除")
    if role.users:
        raise HTTPException(
            status_code=400,
            detail=f"该角色下还有 {len(role.users)} 个用户，请先移除后再删除",
        )
    before = {"name": role.name, "code": role.code,
              "permissions": list(role.permissions or [])}
    name = role.name
    db.delete(role)
    db.commit()
    audit.record(
        db, request, module="roles", action="delete",
        target_type="role", target_id=role_id, target_name=name,
        before=before, message=f"删除角色 {name}",
    )
    return {"message": "角色已删除"}


# ==================== 群组 ====================
@groups_router.get("")
def list_groups(db: Session = Depends(get_db), current: User = Depends(_require_superuser)):
    """群组列表（仅超级管理员）"""
    groups = db.query(Group).order_by(Group.id).all()
    return {
        "total": len(groups),
        "items": [_group_to_dict(g) for g in groups],
    }


@groups_router.post("")
def create_group(
    payload: GroupCreate,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(_require_superuser),
):
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="群组名称不能为空")
    if db.query(Group).filter(Group.name == name).first():
        raise HTTPException(status_code=400, detail="群组名称已存在")
    group = Group(
        name=name,
        code=(payload.code or None),
        description=payload.description,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    audit.record(
        db, request, module="groups", action="create",
        target_type="group", target_id=group.id, target_name=group.name,
        after={"name": group.name, "code": group.code, "description": group.description},
        message=f"新增群组 {group.name}",
    )
    return _group_to_dict(group)


@groups_router.put("/{group_id}")
def update_group(
    group_id: int,
    payload: GroupUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(_require_superuser),
):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="群组不存在")
    before = {"name": group.name, "code": group.code, "description": group.description}
    data = payload.model_dump(exclude_unset=True)
    if "name" in data and data["name"]:
        name = data["name"].strip()
        dup = db.query(Group).filter(Group.name == name, Group.id != group.id).first()
        if dup:
            raise HTTPException(status_code=400, detail="群组名称已存在")
        group.name = name
    if "code" in data:
        group.code = data["code"]
    if "description" in data:
        group.description = data["description"]
    group.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(group)
    audit.record(
        db, request, module="groups", action="update",
        target_type="group", target_id=group.id, target_name=group.name,
        before=before,
        after={"name": group.name, "code": group.code, "description": group.description},
        message=f"更新群组 {group.name}",
    )
    return _group_to_dict(group)


@groups_router.delete("/{group_id}")
def delete_group(
    group_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(_require_superuser),
):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="群组不存在")
    if group.users:
        raise HTTPException(
            status_code=400,
            detail=f"该群组下还有 {len(group.users)} 个用户，请先移除后再删除",
        )
    before = {"name": group.name, "code": group.code}
    name = group.name
    db.delete(group)
    db.commit()
    audit.record(
        db, request, module="groups", action="delete",
        target_type="group", target_id=group_id, target_name=name,
        before=before, message=f"删除群组 {name}",
    )
    return {"message": "群组已删除"}
