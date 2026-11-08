"""网络设备配置备份 API"""
from __future__ import annotations

import csv
import difflib
import io
import re
import zipfile
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.config_backup import ConfigBackup
from ..models.database import SessionLocal, get_db
from ..models.models import Device
from ..models.user import Group
from ..services import asset_scope, audit
from ..services import config_backup as backup_service
from ..services import config_backup_storage
from ..services import settings as settings_service
from ..services import vendor_commands

router = APIRouter(prefix="/api/config-backups", tags=["配置备份"])

SETTING_KEYS = (
    "config_backup_enabled", "config_backup_interval_hours",
    "config_backup_retention_count", "config_backup_concurrency",
    "config_backup_timeout",
    "config_backup_storage_enabled", "config_backup_storage_type",
    "config_backup_webdav_url", "config_backup_webdav_username",
    "config_backup_webdav_password", "config_backup_webdav_path",
    "config_backup_webdav_verify_tls",
    "config_backup_sftp_host", "config_backup_sftp_port",
    "config_backup_sftp_username", "config_backup_sftp_password",
    "config_backup_sftp_path", "config_backup_sftp_timeout",
)


def _user(request: Request, db: Session):
    return asset_scope.get_current_user(db, request)


def _record_dict(row: ConfigBackup, include_config: bool = False) -> Dict[str, Any]:
    device = row.device
    data = {
        "id": row.id,
        "device_id": row.device_id,
        "device_name": device.name if device else "",
        "ip_address": device.ip_address if device else "",
        "status": row.status,
        "method": row.method,
        "size_bytes": row.size_bytes or 0,
        "sha256": row.sha256 or "",
        "command": row.command or "",
        "vendor_profile": row.vendor_profile or "",
        "error": row.error or "",
        "triggered_by": row.triggered_by or "",
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "duration_ms": row.duration_ms or 0,
        "storage_type": row.storage_type or "",
        "storage_key": row.storage_key or "",
        "storage_status": row.storage_status or "",
        "storage_error": row.storage_error or "",
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }
    if include_config:
        data["config_text"] = row.config_text or ""
    return data


def _device_dict(db: Session, device: Device) -> Dict[str, Any]:
    last = (
        db.query(ConfigBackup)
        .filter(ConfigBackup.device_id == device.id)
        .order_by(ConfigBackup.created_at.desc())
        .first()
    )
    group_name = ""
    if device.group_id:
        from ..models.user import Group
        group = db.query(Group).filter(Group.id == device.group_id).first()
        group_name = group.name if group else ""
    return {
        "id": device.id,
        "name": device.name,
        "ip_address": device.ip_address,
        "vendor": device.vendor or "",
        "model": device.model or "",
        "device_type": device.device_type,
        "group_id": device.group_id,
        "group_name": group_name,
        "backup_enabled": bool(device.backup_enabled),
        "credential_id": device.credential_id,
        "credential_name": device.credential.name if device.credential else "",
        "backup_username": device.backup_username or (device.credential.username if device.credential else "") or "",
        "backup_password_set": bool(device.backup_password or (device.credential.password if device.credential else "")),
        "backup_port": device.backup_port or (device.credential.port if device.credential else 22) or 22,
        "backup_command": device.backup_command or "",
        "backup_interval_hours": device.backup_interval_hours or 0,
        "last_backup": _record_dict(last) if last else None,
        "vendor_profile": vendor_commands.detect_vendor(device),
        "vendor_label": vendor_commands.get_profile(device)["label"],
        "auto_command": vendor_commands.get_profile(device)["backup_commands"][0],
    }


def _is_managed_device(device: Device) -> bool:
    """是否已加入配置备份（与资产管理中的资产独立）。"""
    return bool(device.backup_enabled or device.backup_username or device.backup_password or device.credential_id)


def _scoped_devices(db: Session, request: Request, query=None):
    return asset_scope.scope_device_query(db, request, query or db.query(Device))


@router.get("/overview")
def overview(request: Request, db: Session = Depends(get_db)):
    devices = [
        item for item in _scoped_devices(db, request).all()
        if _is_managed_device(item)
    ]
    enabled = sum(1 for item in devices if item.backup_enabled)
    configured = sum(1 for item in devices if item.backup_username and item.backup_password)
    device_ids = [item.id for item in devices]
    latest_success = 0
    latest_failed = 0
    if device_ids:
        latest_success = db.query(ConfigBackup).filter(
            ConfigBackup.device_id.in_(device_ids), ConfigBackup.status == "success"
        ).count()
        latest_failed = db.query(ConfigBackup).filter(
            ConfigBackup.device_id.in_(device_ids), ConfigBackup.status == "failed"
        ).count()
    values = settings_service.get_all(db)
    return {
        "settings": {key: values.get(key) for key in SETTING_KEYS},
        "scheduler": backup_service.scheduler.status(),
        "stats": {
            "devices": len(devices),
            "enabled": enabled,
            "configured": configured,
            "success": latest_success,
            "failed": latest_failed,
        },
    }


@router.get("/devices")
def list_devices(
    request: Request,
    group_id: Optional[int] = None,
    keyword: str = "",
    status: str = "",
    include_unmanaged: bool = False,
    page: int = 1,
    page_size: int = 12,
    db: Session = Depends(get_db),
):
    query = _scoped_devices(db, request)
    if group_id is not None:
        query = query.filter(Device.group_id == group_id)
    if keyword.strip():
        like = f"%{keyword.strip()}%"
        query = query.filter((Device.name.like(like)) | (Device.ip_address.like(like)))
    items = [_device_dict(db, device) for device in query.order_by(Device.name.asc()).all()]
    if not include_unmanaged:
        # 备份页只展示“已加入备份”的设备，删除备份配置后设备从本页消失，
        # 但资产仍保留在资产管理中。
        items = [item for item in items if item["backup_enabled"] or item["backup_username"] or item["backup_password_set"]]
    if status == "enabled":
        items = [item for item in items if item["backup_enabled"]]
    elif status == "unconfigured":
        items = [item for item in items if not item["backup_password_set"]]
    elif status == "failed":
        items = [item for item in items if item["last_backup"] and item["last_backup"]["status"] == "failed"]
    elif status == "managed":
        items = [item for item in items if item["backup_enabled"] or item["backup_username"] or item["backup_password_set"]]
    elif status == "unmanaged":
        items = [item for item in items if not (item["backup_enabled"] or item["backup_username"] or item["backup_password_set"])]
    total = len(items)
    page = max(1, int(page or 1))
    page_size = max(1, min(200, int(page_size or 12)))
    start = (page - 1) * page_size
    return {
        "items": items[start:start + page_size],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.put("/devices/{device_id}")
def update_device_backup(
    device_id: int,
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    device = _scoped_devices(db, request).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在或无权访问")
    enabled = bool(payload.get("backup_enabled"))
    username = str(payload.get("backup_username") or "").strip()
    password = payload.get("backup_password")
    port = payload.get("backup_port") or 22
    command = str(payload.get("backup_command") or "").strip()
    interval = payload.get("backup_interval_hours") or 0
    try:
        port = int(port)
        interval = int(interval)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="SSH 端口或备份间隔格式不正确") from exc
    if port < 1 or port > 65535:
        raise HTTPException(status_code=400, detail="SSH 端口应为 1~65535")
    if interval < 0 or interval > 168:
        raise HTTPException(status_code=400, detail="设备备份间隔应为 0~168 小时")
    if len(command) > 200:
        raise HTTPException(status_code=400, detail="自定义命令不能超过 200 个字符")
    if enabled and not username and not device.credential_id:
        raise HTTPException(status_code=400, detail="启用配置备份需要填写 SSH 用户名或关联设备凭据")
    if enabled and not (device.backup_password or password or device.credential_id):
        raise HTTPException(status_code=400, detail="启用配置备份需要填写 SSH 密码或关联设备凭据")
    device.backup_enabled = enabled
    device.backup_username = username
    device.backup_port = port
    device.backup_command = command
    device.backup_interval_hours = interval
    if password is not None and str(password) != "":
        device.backup_password = str(password)
    device.updated_at = datetime.utcnow()
    audit.record(
        db, request, module="config_backup", action="update",
        target_type="device", target_id=device.id, target_name=device.name,
        after={"backup_enabled": enabled, "backup_username": username, "backup_port": port},
        message="更新设备配置备份参数",
    )
    db.commit()
    return {"message": "配置已保存", "device": _device_dict(db, device)}


@router.post("/devices/batch-add")
def batch_add_devices(request: Request, payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    raw_ids = payload.get("device_ids") or []
    if not isinstance(raw_ids, list) or not raw_ids:
        raise HTTPException(status_code=400, detail="请选择要加入备份的设备")
    try:
        ids = [int(item) for item in raw_ids]
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="设备 ID 不合法") from exc
    username = str(payload.get("backup_username") or "").strip()
    password = str(payload.get("backup_password") or "")
    shared_command = str(payload.get("backup_command") or "").strip()
    raw_commands = payload.get("device_commands") or {}
    device_commands = raw_commands if isinstance(raw_commands, dict) else {}
    try:
        port = int(payload.get("backup_port") or 22)
        interval = int(payload.get("backup_interval_hours") or 0)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="SSH 端口或备份间隔格式不正确") from exc
    if port < 1 or port > 65535:
        raise HTTPException(status_code=400, detail="SSH 端口应为 1~65535")
    if interval < 0 or interval > 168:
        raise HTTPException(status_code=400, detail="备份间隔应为 0~168 小时")
    devices = _scoped_devices(db, request).filter(Device.id.in_(ids)).all()
    if not username or not password:
        missing_credential = [device for device in devices if not device.credential_id]
        if missing_credential:
            raise HTTPException(status_code=400, detail="部分设备未关联设备凭据，请填写统一 SSH 用户名和密码")
    enabled = bool(payload.get("backup_enabled", True))
    for device in devices:
        device.backup_enabled = enabled
        # 已关联设备凭据的资产不被统一 SSH 参数覆盖，确保凭据模块优先。
        if not device.credential_id:
            if username:
                device.backup_username = username
            if password:
                device.backup_password = password
            if port:
                device.backup_port = port
        per_device = device_commands.get(str(device.id), device_commands.get(device.id))
        command = str(per_device if per_device is not None else shared_command).strip()
        device.backup_command = command[:200]
        device.backup_interval_hours = interval
        device.updated_at = datetime.utcnow()
    audit.record(
        db, request, module="config_backup", action="update",
        target_type="config_backup_batch", target_name="批量加入备份设备",
        after={"device_ids": ids, "enabled": enabled},
        message=f"批量加入配置备份设备 {len(devices)} 台",
    )
    db.commit()
    return {"message": f"已加入 {len(devices)} 台设备", "changed": len(devices), "skipped": len(ids) - len(devices)}


@router.post("/devices/batch-remove")
def batch_remove_devices(request: Request, payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    raw_ids = payload.get("device_ids") or []
    if not isinstance(raw_ids, list) or not raw_ids:
        raise HTTPException(status_code=400, detail="请选择要移除的设备")
    try:
        ids = [int(item) for item in raw_ids]
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="设备 ID 不合法") from exc
    devices = _scoped_devices(db, request).filter(Device.id.in_(ids)).all()
    for device in devices:
        device.backup_enabled = False
        device.backup_username = None
        device.backup_password = None
        device.backup_command = None
        device.backup_interval_hours = 0
        device.updated_at = datetime.utcnow()
    audit.record(
        db, request, module="config_backup", action="update",
        target_type="config_backup_batch", target_name="批量移除备份设备",
        after={"device_ids": ids}, message=f"从配置备份移除 {len(devices)} 台设备（保留历史记录和资产）",
    )
    db.commit()
    return {"message": f"已移除 {len(devices)} 台设备，历史备份和资产保留", "changed": len(devices)}


@router.post("/devices/{device_id}/run")
def run_device_backup(
    device_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    device = _scoped_devices(db, request).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在或无权访问")
    credential = getattr(device, "credential", None)
    if not (device.backup_username or (credential.username if credential else "")) or not (device.backup_password or (credential.password if credential else "")):
        raise HTTPException(status_code=400, detail="请先配置 SSH 用户名和密码，或关联设备凭据")
    user = _user(request, db)
    record = backup_service.perform_backup(
        db, device.id, "manual", getattr(user, "username", "system")
    )
    if not record:
        raise HTTPException(status_code=500, detail="备份任务未能创建")
    audit.record(
        db, request, module="config_backup", action="create",
        target_type="config_backup", target_id=record.id, target_name=device.name,
        status="success" if record.status == "success" else "failed",
        message=f"手动配置备份：{record.status}",
    )
    db.commit()
    return {"message": "备份完成" if record.status == "success" else "备份失败", "record": _record_dict(record)}


def _queue_backup(device_id: int, username: str):
    db = SessionLocal()
    try:
        backup_service.perform_backup(db, device_id, "manual", username)
    finally:
        db.close()


@router.post("/batch/run")
def batch_run(
    request: Request,
    background: BackgroundTasks,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    raw_ids = payload.get("device_ids") or []
    if not isinstance(raw_ids, list) or not raw_ids:
        raise HTTPException(status_code=400, detail="请选择设备")
    try:
        ids = [int(item) for item in raw_ids]
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="设备 ID 不合法") from exc
    allowed = _scoped_devices(db, request).filter(Device.id.in_(ids)).all()
    user = _user(request, db)
    queued = 0
    for device in allowed:
        if (device.backup_username or device.credential_id) and (device.backup_password or device.credential_id):
            background.add_task(_queue_backup, device.id, getattr(user, "username", "system"))
            queued += 1
    audit.record(
        db, request, module="config_backup", action="create",
        target_type="config_backup_batch", target_name="批量手动备份",
        after={"device_ids": [item.id for item in allowed], "queued": queued},
        message=f"排队批量配置备份 {queued} 台",
    )
    db.commit()
    return {"message": f"已排队 {queued} 台设备", "queued": queued, "skipped": len(allowed) - queued}


@router.post("/batch/toggle")
def batch_toggle(request: Request, payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    raw_ids = payload.get("device_ids") or []
    enabled = bool(payload.get("backup_enabled"))
    if not isinstance(raw_ids, list) or not raw_ids:
        raise HTTPException(status_code=400, detail="请选择设备")
    try:
        ids = [int(item) for item in raw_ids]
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="设备 ID 不合法") from exc
    devices = _scoped_devices(db, request).filter(Device.id.in_(ids)).all()
    changed = 0
    for device in devices:
        if enabled and not device.credential_id and (not device.backup_username or not device.backup_password):
            continue
        device.backup_enabled = enabled
        changed += 1
    audit.record(
        db, request, module="config_backup", action="update",
        target_type="config_backup_batch", target_name="批量启用/停用",
        after={"device_ids": [item.id for item in devices], "enabled": enabled, "changed": changed},
        message=f"批量{'启用' if enabled else '停用'}配置备份 {changed} 台",
    )
    db.commit()
    return {"message": f"已更新 {changed} 台", "changed": changed}


@router.get("/records")
def list_records(
    request: Request,
    device_id: Optional[int] = None,
    status: str = "",
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    visible = asset_scope.visible_device_ids(db, request)
    query = db.query(ConfigBackup).join(Device)
    if visible is not None:
        query = query.filter(ConfigBackup.device_id.in_(visible))
    if device_id:
        query = query.filter(ConfigBackup.device_id == device_id)
    if status:
        query = query.filter(ConfigBackup.status == status)
    total = query.count()
    page = max(1, int(page or 1))
    page_size = max(1, min(200, int(page_size or 50)))
    rows = query.order_by(ConfigBackup.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": [_record_dict(item) for item in rows], "total": total, "page": page, "page_size": page_size}


def _record_for(db: Session, request: Request, record_id: int) -> ConfigBackup:
    row = db.query(ConfigBackup).filter(ConfigBackup.id == record_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="备份记录不存在")
    asset_scope.require_device_access(db, request, row.device)
    return row


@router.get("/records/grouped")
def list_grouped_records(
    request: Request,
    device_id: Optional[int] = None,
    status: str = "",
    order: str = "desc",
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
):
    """按资产分组返回备份记录；分页以资产为单位。"""
    visible = asset_scope.visible_device_ids(db, request)
    query = db.query(ConfigBackup).join(Device)
    if visible is not None:
        query = query.filter(ConfigBackup.device_id.in_(visible))
    if device_id:
        query = query.filter(ConfigBackup.device_id == device_id)
    if status:
        query = query.filter(ConfigBackup.status == status)
    page = max(1, int(page or 1))
    page_size = max(1, min(50, int(page_size or 10)))
    ascending = str(order or "desc").lower() == "asc"
    latest_at = func.max(ConfigBackup.created_at)
    grouped = (
        query.with_entities(ConfigBackup.device_id, latest_at.label("latest_at"))
        .group_by(ConfigBackup.device_id)
        .order_by(latest_at.asc() if ascending else latest_at.desc())
    )
    total = grouped.count()
    asset_rows = grouped.offset((page - 1) * page_size).limit(page_size).all()
    groups: List[Dict[str, Any]] = []
    for asset_id, latest_at in asset_rows:
        rows = (
            query.filter(ConfigBackup.device_id == asset_id)
            .order_by(ConfigBackup.created_at.asc() if ascending else ConfigBackup.created_at.desc())
            .limit(20)
            .all()
        )
        if not rows:
            continue
        device = rows[0].device
        group_name = ""
        if device and device.group_id:
            group_name = db.query(Group.name).filter(Group.id == device.group_id).scalar() or ""
        groups.append({
            "device_id": asset_id,
            "device_name": device.name if device else "",
            "ip_address": device.ip_address if device else "",
            "group_name": group_name,
            "vendor": device.vendor if device else "",
            "total": query.filter(ConfigBackup.device_id == asset_id).count(),
            "latest_at": latest_at.isoformat() if latest_at else None,
            "records": [_record_dict(item) for item in rows],
        })
    return {"groups": groups, "total": total, "page": page, "page_size": page_size, "order": "asc" if ascending else "desc"}


@router.get("/records/{record_id}")
def get_record(record_id: int, request: Request, db: Session = Depends(get_db)):
    row = _record_for(db, request, record_id)
    return _record_dict(row, include_config=True)


@router.delete("/records/{record_id}")
def delete_record(record_id: int, request: Request, db: Session = Depends(get_db)):
    row = _record_for(db, request, record_id)
    name = row.device.name
    if row.storage_key:
        config_backup_storage.delete(settings_service.get_all(db), row.storage_key)
    db.delete(row)
    audit.record(
        db, request, module="config_backup", action="delete",
        target_type="config_backup", target_id=record_id, target_name=name,
        message="删除配置备份记录",
    )
    db.commit()
    return {"message": "备份记录已删除"}


@router.get("/records/{record_id}/download")
def download_record(record_id: int, request: Request, db: Session = Depends(get_db)):
    row = _record_for(db, request, record_id)
    content = row.config_text or ""
    if row.status != "success" or not content:
        values = settings_service.get_all(db)
        content = config_backup_storage.download(values, row.storage_key) or ""
    if not content:
        raise HTTPException(status_code=400, detail="该记录没有可下载的配置")
    filename = f"{row.device.name}-{row.id}.cfg".replace("/", "_").replace("\\", "_")
    return Response(
        content=content,
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"},
    )


def _diff(a: str, b: str) -> List[Dict[str, Any]]:
    old_lines = a.splitlines()
    new_lines = b.splitlines()
    matcher = difflib.SequenceMatcher(None, old_lines, new_lines)
    rows: List[Dict[str, Any]] = []
    old_no = new_no = 1
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(i2 - i1):
                rows.append({"type": "equal", "text": old_lines[i1 + offset], "old_no": old_no, "new_no": new_no})
                old_no += 1
                new_no += 1
        elif tag == "delete":
            for offset in range(i2 - i1):
                rows.append({"type": "delete", "text": old_lines[i1 + offset], "old_no": old_no, "new_no": None})
                old_no += 1
        elif tag == "insert":
            for offset in range(j2 - j1):
                rows.append({"type": "add", "text": new_lines[j1 + offset], "old_no": None, "new_no": new_no})
                new_no += 1
        else:  # replace
            for offset in range(i2 - i1):
                rows.append({"type": "delete", "text": old_lines[i1 + offset], "old_no": old_no, "new_no": None})
                old_no += 1
            for offset in range(j2 - j1):
                rows.append({"type": "add", "text": new_lines[j1 + offset], "old_no": None, "new_no": new_no})
                new_no += 1
    return rows


@router.get("/diff")
def compare_records(
    request: Request,
    a_id: int,
    b_id: int,
    db: Session = Depends(get_db),
):
    old = _record_for(db, request, a_id)
    new = _record_for(db, request, b_id)
    if old.status != "success" or new.status != "success":
        raise HTTPException(status_code=400, detail="只能对比成功的配置记录")
    if old.device_id != new.device_id:
        raise HTTPException(status_code=400, detail="只能对比同一资产的两条备份记录")
    rows = _diff(old.config_text or "", new.config_text or "")
    return {
        "a": _record_dict(old),
        "b": _record_dict(new),
        "lines": rows,
        "stats": {
            "add": sum(1 for item in rows if item["type"] == "add"),
            "delete": sum(1 for item in rows if item["type"] == "delete"),
            "equal": sum(1 for item in rows if item["type"] == "equal"),
        },
    }


@router.get("/export")
def export_configs(
    request: Request,
    device_id: Optional[int] = None,
    a_id: Optional[int] = None,
    b_id: Optional[int] = None,
    ids: Optional[str] = None,
    db: Session = Depends(get_db),
):
    visible = asset_scope.visible_device_ids(db, request)
    query = db.query(ConfigBackup).join(Device).filter(ConfigBackup.status == "success")
    if visible is not None:
        query = query.filter(ConfigBackup.device_id.in_(visible))
    if device_id:
        query = query.filter(ConfigBackup.device_id == device_id)
    if ids:
        try:
            wanted_ids = [int(item) for item in ids.split(",") if item.strip()]
        except ValueError as exc:
            raise HTTPException(status_code=400, detail="导出记录 ID 不合法") from exc
        query = query.filter(ConfigBackup.id.in_(wanted_ids))
    rows = query.order_by(ConfigBackup.created_at.desc()).all()
    if a_id or b_id:
        wanted = {item for item in (a_id, b_id) if item}
        rows = [item for item in rows if item.id in wanted]
    if not rows:
        raise HTTPException(status_code=404, detail="没有可导出的成功配置")
    output = io.BytesIO()
    manifest = io.StringIO()
    writer = csv.writer(manifest)
    writer.writerow(["设备", "IP", "备份ID", "备份时间", "大小(字节)", "SHA256", "厂商适配"])
    used = set()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        for row in rows:
            safe = re.sub(r"[^0-9A-Za-z_.\-\u4e00-\u9fa5]+", "_", row.device.name)[:40] or "device"
            name = f"{safe}-{row.id}.cfg"
            if name in used:
                name = f"{safe}-{row.id}-{row.id}.cfg"
            used.add(name)
            archive.writestr(name, row.config_text or "")
            writer.writerow([
                row.device.name, row.device.ip_address, row.id,
                row.created_at.isoformat() if row.created_at else "",
                row.size_bytes or 0, row.sha256 or "", row.vendor_profile or "",
            ])
        archive.writestr("manifest.csv", "\ufeff" + manifest.getvalue())
    filename = f"config-backups-{datetime.utcnow().strftime('%Y%m%d-%H%M%S')}.zip"
    return Response(
        content=output.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


@router.get("/settings")
def get_settings(request: Request, db: Session = Depends(get_db)):
    values = settings_service.get_all(db)
    return {key: values.get(key) for key in SETTING_KEYS}


@router.put("/settings")
def update_settings(request: Request, payload: Dict[str, Any] = Body(...), db: Session = Depends(get_db)):
    current = _user(request, db)
    if not current or not current.is_superuser:
        raise HTTPException(status_code=403, detail="全局配置备份设置仅超级管理员可修改")
    data = {key: payload.get(key) for key in SETTING_KEYS if key in payload}
    normalized, errors = settings_service.validate(data)
    if errors:
        raise HTTPException(status_code=400, detail="；".join(errors))
    before = settings_service.get_all(db)
    updated = settings_service.save(db, normalized)
    audit.record(
        db, request, module="config_backup", action="update",
        target_type="config_backup_settings", target_name="配置备份设置",
        before={key: before.get(key) for key in normalized},
        after=normalized,
        message="更新全局配置备份设置",
    )
    return {"message": "配置备份设置已保存", "settings": {key: updated.get(key) for key in SETTING_KEYS}}
