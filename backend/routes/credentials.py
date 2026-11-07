"""设备凭据：统一维护 SSH 凭据并分配给资产，供巡检和备份复用。"""
from __future__ import annotations

import csv
import io
import re
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from openpyxl import Workbook, load_workbook
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..models.models import Device, DeviceCredential
from ..models.user import User
from ..services import asset_scope, audit
from ..services import auth as auth_service

router = APIRouter(prefix="/api/credentials", tags=["设备凭据"])


def _user(request: Request, db: Session, write: bool = False) -> User:
    user = asset_scope.get_current_user(db, request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    permission = "credentials:edit" if write else "credentials:view"
    if not auth_service.has_permission(user, permission):
        raise HTTPException(status_code=403, detail=f"无权限执行该操作（{permission}）")
    return user


def _dict(db: Session, row: DeviceCredential) -> Dict[str, Any]:
    devices = db.query(Device).filter(Device.credential_id == row.id).order_by(Device.name.asc()).all()
    return {
        "id": row.id,
        "name": row.name,
        "username": row.username,
        "password_set": bool(row.password),
        "port": row.port or 22,
        "description": row.description or "",
        "asset_ids": [device.id for device in devices],
        "assets": [{"id": device.id, "name": device.name, "ip_address": device.ip_address} for device in devices],
        "asset_count": len(devices),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _payload(payload: Dict[str, Any], existing: DeviceCredential | None = None) -> Dict[str, Any]:
    name = str(payload.get("name") or "").strip()
    username = str(payload.get("username") or "").strip()
    password = payload.get("password")
    port = payload.get("port", 22)
    description = str(payload.get("description") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="请填写凭据名称")
    if not username:
        raise HTTPException(status_code=400, detail="请填写 SSH 用户名")
    try:
        port = int(port or 22)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="SSH 端口格式不正确") from None
    if not 1 <= port <= 65535:
        raise HTTPException(status_code=400, detail="SSH 端口应为 1~65535")
    if len(name) > 120 or len(username) > 120 or len(description) > 500:
        raise HTTPException(status_code=400, detail="凭据字段长度超出限制")
    values: Dict[str, Any] = {
        "name": name,
        "username": username,
        "port": port,
        "description": description,
    }
    if password is not None and str(password) != "":
        values["password"] = str(password)
    elif existing is None:
        values["password"] = ""
    return values


def _assign(db: Session, credential: DeviceCredential, asset_ids: List[int]) -> None:
    # 先清除该凭据下已移除的设备
    db.query(Device).filter(
        Device.credential_id == credential.id,
        ~Device.id.in_(asset_ids) if asset_ids else True,
    ).update({"credential_id": None}, synchronize_session=False)
    if not asset_ids:
        return
    devices = db.query(Device).filter(Device.id.in_(asset_ids)).all()
    for device in devices:
        device.credential_id = credential.id


def _asset_ids(payload: Dict[str, Any], db: Session, request: Request) -> List[int]:
    raw = payload.get("asset_ids") or []
    if not isinstance(raw, list):
        raise HTTPException(status_code=400, detail="资产列表格式不正确")
    ids: List[int] = []
    for value in raw:
        try:
            item = int(value)
        except (TypeError, ValueError):
            continue
        if item not in ids:
            ids.append(item)
    if ids:
        scoped = asset_scope.scope_device_query(db, request, db.query(Device.id).filter(Device.id.in_(ids)))
        found = {row[0] for row in scoped.all()}
        if any(item not in found for item in ids):
            raise HTTPException(status_code=403, detail="包含无权访问的资产")
    return ids


@router.get("")
def list_credentials(
    request: Request,
    page: int = 1,
    size: int = 20,
    keyword: str = "",
    db: Session = Depends(get_db),
):
    _user(request, db)
    query = db.query(DeviceCredential)
    keyword = (keyword or "").strip()
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            (DeviceCredential.name.like(like))
            | (DeviceCredential.username.like(like))
            | (DeviceCredential.description.like(like))
        )
    total = query.count()
    page = max(1, int(page or 1))
    size = max(1, min(200, int(size or 20)))
    rows = query.order_by(DeviceCredential.name.asc()).offset((page - 1) * size).limit(size).all()
    return {"items": [_dict(db, row) for row in rows], "total": total, "page": page, "page_size": size}


def _selected_ids(ids: str = "", raw_ids: List[Any] | None = None) -> List[int]:
    values = list(raw_ids or [])
    if ids:
        values.extend(str(ids).split(","))
    result: List[int] = []
    for value in values:
        try:
            item = int(value)
        except (TypeError, ValueError):
            continue
        if item not in result:
            result.append(item)
    return result


@router.get("/export")
def export_credentials(
    request: Request,
    ids: str = "",
    include_password: bool = False,
    db: Session = Depends(get_db),
):
    """导出凭据为 Excel；默认不导出密码，显式 include_password 才包含。"""
    _user(request, db)
    query = db.query(DeviceCredential)
    selected = _selected_ids(ids)
    if selected:
        query = query.filter(DeviceCredential.id.in_(selected))
    rows = query.order_by(DeviceCredential.name.asc()).all()
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "设备凭据"
    headers = ["凭据名称", "SSH用户名", "SSH密码", "端口", "说明", "关联资产"]
    sheet.append(headers)
    for row in rows:
        devices = db.query(Device).filter(Device.credential_id == row.id).order_by(Device.name.asc()).all()
        assets = ";".join(f"{item.name}({item.ip_address})" for item in devices)
        sheet.append([
            row.name, row.username,
            row.password if include_password else "",
            row.port or 22, row.description or "", assets,
        ])
    sheet.column_dimensions["A"].width = 26
    sheet.column_dimensions["B"].width = 18
    sheet.column_dimensions["C"].width = 22
    sheet.column_dimensions["D"].width = 10
    sheet.column_dimensions["E"].width = 32
    sheet.column_dimensions["F"].width = 46
    output = io.BytesIO()
    workbook.save(output)
    suffix = "with-password" if include_password else "no-password"
    filename = f"device-credentials-{suffix}-{datetime.now().strftime('%Y%m%d')}.xlsx"
    return Response(
        content=output.getvalue(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _import_rows(content: bytes, filename: str) -> List[Dict[str, Any]]:
    suffix = (filename or "").lower().rsplit(".", 1)[-1]
    rows: List[Dict[str, Any]] = []
    if suffix in ("xlsx", "xlsm"):
        workbook = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        sheet = workbook.active
        values = list(sheet.iter_rows(values_only=True))
        if not values:
            return []
        headers = [str(value or "").strip() for value in values[0]]
        for raw in values[1:]:
            rows.append({headers[i]: raw[i] for i in range(min(len(headers), len(raw)))})
    elif suffix == "csv":
        text = content.decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        rows = [dict(item) for item in reader]
    else:
        raise HTTPException(status_code=400, detail="仅支持 .xlsx 或 .csv 文件")
    return rows


def _cell(row: Dict[str, Any], *keys: str) -> str:
    for key in keys:
        if key in row and row[key] is not None:
            return str(row[key]).strip()
    return ""


@router.post("/import")
async def import_credentials(
    request: Request,
    file: UploadFile = File(...),
    mode: str = Form("skip"),
    db: Session = Depends(get_db),
):
    """批量导入凭据；按凭据名称匹配，mode=skip 跳过，mode=update 更新。"""
    _user(request, db, write=True)
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="导入文件不能超过 10MB")
    try:
        rows = _import_rows(content, file.filename or "")
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"读取导入文件失败：{exc}") from exc
    mode = "update" if str(mode).lower() == "update" else "skip"
    created = updated = skipped = 0
    errors: List[Dict[str, Any]] = []
    for index, item in enumerate(rows, start=2):
        name = _cell(item, "凭据名称", "name", "名称")
        username = _cell(item, "SSH用户名", "username", "用户名")
        if not name or not username:
            errors.append({"row": index, "message": "凭据名称和 SSH 用户名不能为空"})
            continue
        password = _cell(item, "SSH密码", "password", "密码")
        try:
            port = int(_cell(item, "端口", "port") or 22)
        except ValueError:
            errors.append({"row": index, "message": "端口格式不正确"})
            continue
        if not 1 <= port <= 65535:
            errors.append({"row": index, "message": "端口应为 1~65535"})
            continue
        description = _cell(item, "说明", "description")
        existing = db.query(DeviceCredential).filter(DeviceCredential.name == name).first()
        if existing and mode == "skip":
            skipped += 1
            continue
        if existing:
            existing.username = username[:120]
            existing.port = port
            existing.description = description[:500]
            if password:
                existing.password = password[:500]
            row = existing
            updated += 1
        else:
            row = DeviceCredential(
                name=name[:120], username=username[:120], password=password[:500],
                port=port, description=description[:500],
            )
            db.add(row)
            db.flush()
            created += 1
        asset_text = _cell(item, "关联资产", "assets", "资产")
        if asset_text:
            tokens = [value.strip() for value in re.split(r"[,;，；\n]+", asset_text) if value.strip()]
            devices = []
            for token in tokens:
                if "(" in token and token.endswith(")"):
                    token = token.rsplit("(", 1)[0].strip()
                device = db.query(Device).filter(
                    (Device.ip_address == token) | (Device.name == token)
                ).first()
                if device:
                    devices.append(device)
            if devices:
                scoped = asset_scope.scope_device_query(
                    db, request, db.query(Device).filter(Device.id.in_([d.id for d in devices]))
                ).all()
                allowed = {d.id for d in scoped}
                for device in devices:
                    if device.id in allowed:
                        device.credential_id = row.id
    db.commit()
    audit.record(
        db, request, module="credentials", action="import",
        target_type="device_credential", target_name=file.filename or "导入文件",
        after={"created": created, "updated": updated, "skipped": skipped, "errors": len(errors)},
        message=f"批量导入设备凭据：新增 {created}，更新 {updated}，跳过 {skipped}",
    )
    return {
        "message": f"导入完成：新增 {created}，更新 {updated}，跳过 {skipped}",
        "created": created, "updated": updated, "skipped": skipped,
        "errors": errors[:100], "total": len(rows),
    }


@router.post("/batch-delete")
def batch_delete_credentials(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    _user(request, db, write=True)
    ids = _selected_ids("", payload.get("ids") or [])
    if not ids:
        raise HTTPException(status_code=400, detail="请选择凭据")
    rows = db.query(DeviceCredential).filter(DeviceCredential.id.in_(ids)).all()
    names = [row.name for row in rows]
    for row in rows:
        db.query(Device).filter(Device.credential_id == row.id).update({"credential_id": None}, synchronize_session=False)
        db.delete(row)
    audit.record(
        db, request, module="credentials", action="delete",
        target_type="device_credential_batch", target_name="批量删除设备凭据",
        after={"ids": ids, "names": names}, message=f"批量删除 {len(rows)} 个设备凭据",
    )
    db.commit()
    return {"message": f"已删除 {len(rows)} 个设备凭据，关联资产保留", "deleted": len(rows)}


@router.post("")
def create_credential(request: Request, payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    _user(request, db, write=True)
    values = _payload(payload)
    asset_ids = _asset_ids(payload, db, request)
    row = DeviceCredential(**values)
    db.add(row)
    db.flush()
    _assign(db, row, asset_ids)
    audit.record(db, request, module="credentials", action="create", target_type="device_credential",
                 target_id=row.id, target_name=row.name, message="创建设备凭据")
    db.commit()
    db.refresh(row)
    return {"message": "设备凭据已创建", "credential": _dict(db, row)}


@router.put("/{credential_id}")
def update_credential(credential_id: int, request: Request, payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    _user(request, db, write=True)
    row = db.query(DeviceCredential).filter(DeviceCredential.id == credential_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="设备凭据不存在")
    values = _payload(payload, existing=row)
    for key, value in values.items():
        setattr(row, key, value)
    if "asset_ids" in payload:
        _assign(db, row, _asset_ids(payload, db, request))
    row.updated_at = datetime.utcnow()
    audit.record(db, request, module="credentials", action="update", target_type="device_credential",
                 target_id=row.id, target_name=row.name, message="更新设备凭据")
    db.commit()
    db.refresh(row)
    return {"message": "设备凭据已保存", "credential": _dict(db, row)}


@router.delete("/{credential_id}")
def delete_credential(credential_id: int, request: Request, db: Session = Depends(get_db)):
    _user(request, db, write=True)
    row = db.query(DeviceCredential).filter(DeviceCredential.id == credential_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="设备凭据不存在")
    db.query(Device).filter(Device.credential_id == row.id).update({"credential_id": None}, synchronize_session=False)
    name = row.name
    db.delete(row)
    audit.record(db, request, module="credentials", action="delete", target_type="device_credential",
                 target_id=credential_id, target_name=name, message="删除设备凭据")
    db.commit()
    return {"message": "设备凭据已删除，关联资产保留"}
