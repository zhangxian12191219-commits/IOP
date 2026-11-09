"""厂商库 API：资产表单厂商来源，支持查询、新增、修改、停用和删除。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import String, cast, func, or_
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..models.models import Device
from ..models.mib import MibFile
from ..models.user import User
from ..models.vendor import Vendor
from ..services import audit
from ..services.auth import get_current_user, has_permission
from ..services.vendor_library import CATEGORY_LABELS, ensure_builtin_vendors, usage_counts, vendor_to_dict

router = APIRouter(prefix="/api/vendors", tags=["厂商库"])


class VendorPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    aliases: Optional[List[str]] = None
    category: str = "other"
    note: Optional[str] = None
    is_enabled: bool = True


class VendorUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=80)
    aliases: Optional[List[str]] = None
    category: Optional[str] = None
    note: Optional[str] = None
    is_enabled: Optional[bool] = None


def _can_view(user: User) -> bool:
    return bool(user.is_superuser or has_permission(user, "assets:view") or has_permission(user, "mib:view"))


def _can_edit(user: User) -> bool:
    return bool(user.is_superuser or has_permission(user, "assets:edit") or has_permission(user, "mib:edit"))


def _check_category(category: str) -> str:
    value = str(category or "other").strip().lower()
    if value not in CATEGORY_LABELS:
        raise HTTPException(status_code=400, detail="厂商分类不合法")
    return value


def _normalize_aliases(values: Optional[List[str]]) -> List[str]:
    result = []
    for item in values or []:
        text = str(item or "").strip()
        if text and text not in result and len(text) <= 60:
            result.append(text)
    return result[:20]


def _name_exists(db: Session, name: str, exclude_id: Optional[int] = None) -> bool:
    query = db.query(Vendor).filter(func.lower(Vendor.name) == str(name or "").strip().lower())
    if exclude_id:
        query = query.filter(Vendor.id != exclude_id)
    return query.first() is not None


@router.get("/options")
def vendor_options(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """资产表单使用的启用厂商列表；普通资产查看权限即可读取。"""
    if not _can_view(current):
        raise HTTPException(status_code=403, detail="无权查看厂商库")
    ensure_builtin_vendors(db)
    rows = (
        db.query(Vendor)
        .filter(Vendor.is_enabled == True)  # noqa: E712
        .order_by(Vendor.sort_order.asc(), Vendor.name.asc())
        .all()
    )
    return {
        "total": len(rows),
        "items": [
            {
                "id": row.id,
                "name": row.name,
                "aliases": row.aliases or [],
                "category": row.category,
                "category_label": CATEGORY_LABELS.get(row.category or "other", "其他"),
                "is_builtin": bool(row.is_builtin),
            }
            for row in rows
        ],
    }


@router.get("/categories")
def vendor_categories(current: User = Depends(get_current_user)):
    return [{"value": key, "label": value} for key, value in CATEGORY_LABELS.items()]


@router.get("")
def list_vendors(
    keyword: str = "",
    category: str = "",
    enabled: Optional[bool] = None,
    page: int = Query(1, ge=1),
    size: int = Query(30, ge=1, le=500),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if not _can_view(current):
        raise HTTPException(status_code=403, detail="无权查看厂商库")
    ensure_builtin_vendors(db)
    query = db.query(Vendor)
    text = (keyword or "").strip()
    if text:
        like = f"%{text}%"
        query = query.filter(or_(
            Vendor.name.ilike(like),
            Vendor.note.ilike(like),
            cast(Vendor.aliases, String).ilike(like),
        ))
    if category:
        query = query.filter(Vendor.category == _check_category(category))
    if enabled is not None:
        query = query.filter(Vendor.is_enabled == bool(enabled))
    total = query.count()
    rows = (
        query.order_by(Vendor.sort_order.asc(), Vendor.name.asc())
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [vendor_to_dict(db, row) for row in rows],
    }


@router.post("")
def create_vendor(
    payload: VendorPayload,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if not _can_edit(current):
        raise HTTPException(status_code=403, detail="无权维护厂商库")
    ensure_builtin_vendors(db)
    name = str(payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="厂商名称不能为空")
    if _name_exists(db, name):
        raise HTTPException(status_code=409, detail="厂商已存在，可直接在列表中选择")
    vendor = Vendor(
        name=name,
        aliases=_normalize_aliases(payload.aliases),
        category=_check_category(payload.category),
        note=(payload.note or "").strip() or None,
        is_builtin=False,
        is_enabled=bool(payload.is_enabled),
        sort_order=500,
    )
    db.add(vendor)
    db.commit()
    db.refresh(vendor)
    audit.record(
        db, request, module="assets", action="create",
        target_type="vendor", target_id=vendor.id, target_name=vendor.name,
        after={"name": vendor.name, "aliases": vendor.aliases, "category": vendor.category},
        message=f"新增厂商库厂商 {vendor.name}",
    )
    return vendor_to_dict(db, vendor)


@router.put("/{vendor_id}")
def update_vendor(
    vendor_id: int,
    payload: VendorUpdate,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if not _can_edit(current):
        raise HTTPException(status_code=403, detail="无权维护厂商库")
    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="厂商不存在")
    old_name = vendor.name
    new_name = (payload.name if payload.name is not None else vendor.name) or ""
    new_name = str(new_name).strip()
    if not new_name:
        raise HTTPException(status_code=400, detail="厂商名称不能为空")
    if new_name != old_name and vendor.is_builtin:
        raise HTTPException(status_code=400, detail="内置厂商名称不可修改，可修改别名/分类或停用")
    if new_name != old_name and _name_exists(db, new_name, vendor.id):
        raise HTTPException(status_code=409, detail="厂商名称已存在")
    if new_name != old_name:
        # 修正录入错误时同步资产和 MIB，避免出现两个厂商。
        db.query(Device).filter(Device.vendor == old_name).update({"vendor": new_name}, synchronize_session=False)
        db.query(MibFile).filter(MibFile.vendor == old_name).update({"vendor": new_name}, synchronize_session=False)
        vendor.name = new_name
    if payload.aliases is not None:
        vendor.aliases = _normalize_aliases(payload.aliases)
    if payload.category is not None:
        vendor.category = _check_category(payload.category)
    if payload.note is not None:
        vendor.note = (payload.note or "").strip() or None
    if payload.is_enabled is not None:
        vendor.is_enabled = bool(payload.is_enabled)
    vendor.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(vendor)
    audit.record(
        db, request, module="assets", action="update",
        target_type="vendor", target_id=vendor.id, target_name=vendor.name,
        before={"name": old_name}, after={"name": vendor.name, "aliases": vendor.aliases, "category": vendor.category, "is_enabled": vendor.is_enabled},
        message=f"更新厂商库厂商 {vendor.name}",
    )
    return vendor_to_dict(db, vendor)


@router.delete("/{vendor_id}")
def delete_vendor(
    vendor_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    if not _can_edit(current):
        raise HTTPException(status_code=403, detail="无权维护厂商库")
    vendor = db.query(Vendor).filter(Vendor.id == vendor_id).first()
    if not vendor:
        raise HTTPException(status_code=404, detail="厂商不存在")
    if vendor.is_builtin:
        raise HTTPException(status_code=400, detail="内置厂商不可删除，可停用")
    usage = usage_counts(db, vendor.name)
    if usage["total"]:
        raise HTTPException(
            status_code=409,
            detail=f"该厂商仍被 {usage['devices']} 台资产、{usage['mibs']} 个 MIB 使用；请先改名或停用，不能直接删除",
        )
    audit.record(
        db, request, module="assets", action="delete",
        target_type="vendor", target_id=vendor.id, target_name=vendor.name,
        after={"name": vendor.name},
        message=f"删除厂商库厂商 {vendor.name}",
    )
    db.delete(vendor)
    db.commit()
    return {"message": f"已删除厂商 {vendor.name}"}
