"""设备巡检 API

- 巡检任务：列表 / 新建 / 修改 / 删除 / 立即巡检
- 巡检报告：列表 / 详情 / 下载（统一 Word .docx）/ 上传（.docx）/ 删除
- 权限：查看需要 inspection:view，任务与报告写操作需要 inspection:edit
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import requests
from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..models.inspection import InspectionReport, InspectionTask
from ..models.virtualization import VirtualPlatform
from ..models.models import Device
from ..models.user import User
from ..services import asset_scope, audit
from ..services import auth as auth_service
from ..services import inspection as inspection_service
from ..services import inspection_office
from ..services import vendor_commands
from ..services import settings as settings_service

router = APIRouter(prefix="/api/inspection", tags=["设备巡检"])


# ==================== 公共依赖 ====================
def _require_user(request: Request, db: Session, write: bool = False) -> User:
    user = asset_scope.get_current_user(db, request)
    if not user:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    permission = "inspection:edit" if write else "inspection:view"
    if not auth_service.has_permission(user, permission):
        raise HTTPException(status_code=403, detail=f"无权限执行该操作（{permission}）")
    return user


def _task_or_404(db: Session, task_id: int) -> InspectionTask:
    task = db.query(InspectionTask).filter(InspectionTask.id == task_id).first()
    if not task:
        raise HTTPException(status_code=404, detail="巡检任务不存在")
    return task


def _report_or_404(db: Session, report_id: int) -> InspectionReport:
    report = db.query(InspectionReport).filter(InspectionReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="巡检报告不存在")
    return report


def _report_device_ids(db: Session, report: InspectionReport) -> List[int]:
    ids: List[int] = []
    if report.task_id:
        task = db.query(InspectionTask).filter(InspectionTask.id == report.task_id).first()
        if task:
            ids = _asset_ids(task)
    payload = report.payload if isinstance(report.payload, dict) else {}
    for item in payload.get("devices") or []:
        if not isinstance(item, dict):
            continue
        try:
            value = int(item.get("id"))
        except (TypeError, ValueError):
            continue
        if value not in ids:
            ids.append(value)
    return ids


def _can_access_report(db: Session, request: Request, report: InspectionReport, user: User) -> bool:
    if user.is_superuser:
        return True
    # 上传报告或虚拟化专用报告没有设备范围时，仅创建者可见
    if report.created_by and report.created_by == user.username:
        return True
    ids = _report_device_ids(db, report)
    if not ids:
        return False
    visible = asset_scope.visible_device_ids(db, request)
    if visible is None:
        return True
    return set(ids).issubset(set(visible))


def _asset_ids(task: InspectionTask) -> List[int]:
    result: List[int] = []
    for raw in task.asset_ids or []:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value not in result:
            result.append(value)
    return result


def _task_dict(db: Session, request: Request, task: InspectionTask) -> Dict[str, Any]:
    ids = _asset_ids(task)
    target_assets: List[Dict[str, Any]] = []
    if ids:
        query = asset_scope.scope_device_query(
            db, request, db.query(Device).filter(Device.id.in_(ids))
        )
        target_assets = [
            {"id": item.id, "name": item.name, "ip_address": item.ip_address}
            for item in query.order_by(Device.name.asc()).all()
        ]
    custom_devices = [item for item in (task.custom_devices or []) if isinstance(item, dict)]
    return {
        "id": task.id,
        "name": task.name,
        "enabled": bool(task.enabled),
        "target_mode": task.target_mode or "assets",
        "asset_ids": ids,
        "target_assets": target_assets,
        "custom_devices": custom_devices,
        "include_virtualization": bool(task.include_virtualization),
        "run_commands": bool(getattr(task, "run_commands", False)),
        "schedule_type": task.schedule_type or "interval",
        "interval_hours": task.interval_hours or 24,
        "daily_time": task.daily_time or "02:00",
        "schedule_text": inspection_service.schedule_text(task),
        "next_run_at": task.next_run_at.isoformat() if task.next_run_at else None,
        "last_run_at": task.last_run_at.isoformat() if task.last_run_at else None,
        "last_status": task.last_status or "idle",
        "last_message": task.last_message or "",
        "last_report_id": task.last_report_id,
        "device_count": len(ids) + len(custom_devices),
        "asset_count": len(ids),
        "custom_count": len(custom_devices),
        "created_by": task.created_by or "",
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


def _report_dict(report: InspectionReport, include_payload: bool = False) -> Dict[str, Any]:
    data: Dict[str, Any] = {
        "id": report.id,
        "task_id": report.task_id,
        "task_name": report.task_name or "",
        "title": report.title,
        "source": report.source or "builtin",
        "trigger": report.trigger or "manual",
        "status": report.status or "success",
        "device_count": report.device_count or 0,
        "online_count": report.online_count or 0,
        "alert_count": report.alert_count or 0,
        "summary": report.summary or "",
        "conclusion": report.conclusion or "",
        "recommendations": report.recommendations or [],
        "original_filename": report.original_filename or "",
        "file_size": report.file_size or 0,
        "content_type": report.content_type or inspection_service.DOCX_MIME,
        "created_by": report.created_by or "",
        "created_at": report.created_at.isoformat() if report.created_at else None,
        "has_file": bool(report.filename),
        "download_url": f"/api/inspection/reports/{report.id}/download",
    }
    if include_payload:
        data["payload"] = report.payload or {}
    return data


@router.get("/vendor-commands")
def get_vendor_commands(
    request: Request,
    asset_ids: str = Query("", description="逗号分隔的资产 ID"),
    vendors: str = Query("", description="自定义设备厂商，逗号分隔"),
    db: Session = Depends(get_db),
):
    """预览所选资产按厂商自动匹配的配置备份与巡检命令。"""
    _require_user(request, db)
    ids = []
    for raw in str(asset_ids or "").split(","):
        raw = raw.strip()
        if not raw:
            continue
        try:
            value = int(raw)
        except ValueError:
            continue
        if value not in ids:
            ids.append(value)
    if not ids and not vendors:
        return {"groups": [], "devices": [], "unmatched_vendors": []}
    scoped = asset_scope.scope_device_query(db, request, db.query(Device).filter(Device.id.in_(ids)))
    devices = scoped.order_by(Device.id.asc()).all()
    groups = {}
    for device in devices:
        profile = vendor_commands.profile_summary(device)
        key = profile["profile"]
        group = groups.setdefault(key, {
            "profile": key,
            "vendor_label": profile["label"],
            "commands": profile["inspection_commands"],
            "backup_commands": profile["backup_commands"],
            "devices": [],
        })
        group["devices"].append({
            "id": device.id,
            "name": device.name,
            "ip_address": device.ip_address,
            "vendor": device.vendor or "",
            "model": device.model or "",
        })
    unmatched = []
    for raw in str(vendors or "").split(","):
        vendor = raw.strip()
        if not vendor:
            continue
        matched = vendor_commands.profile_for_vendor(vendor)
        if not matched:
            if vendor not in unmatched:
                unmatched.append(vendor)
            continue
        key = vendor_commands.match_vendor_text(vendor) or "custom"
        group = groups.setdefault(key, {
            "profile": key,
            "vendor_label": matched["label"],
            "commands": [
                {"key": item[0], "label": item[1], "command": item[2]}
                for item in matched["inspection"]
            ],
            "backup_commands": matched["backup_commands"],
            "devices": [],
        })
        group["devices"].append({"id": None, "name": f"自定义：{vendor}", "ip_address": "", "vendor": vendor, "model": ""})
    return {"groups": list(groups.values()), "devices": [
        {"id": device.id, "name": device.name, "vendor": device.vendor or "", "profile": vendor_commands.detect_vendor(device)}
        for device in devices
    ], "unmatched_vendors": unmatched}


# ==================== 巡检任务 ====================
@router.get("/overview")
def overview(request: Request, db: Session = Depends(get_db)):
    _require_user(request, db)
    tasks_total = db.query(InspectionTask).count()
    tasks_enabled = (
        db.query(InspectionTask).filter(InspectionTask.enabled.is_(True)).count()
    )
    reports_total = db.query(InspectionReport).count()
    builtin_total = (
        db.query(InspectionReport).filter(InspectionReport.source == "builtin").count()
    )
    upload_total = (
        db.query(InspectionReport).filter(InspectionReport.source == "upload").count()
    )
    latest = (
        db.query(InspectionReport)
        .order_by(InspectionReport.created_at.desc(), InspectionReport.id.desc())
        .first()
    )
    return {
        "docx_available": inspection_service.docx_available(),
        "reports_dir": str(inspection_service.ensure_reports_dir()),
        "max_upload_mb": inspection_service.MAX_UPLOAD_MB,
        "retention_days": inspection_service.report_retention_days(db),
        "office_ready": inspection_office.is_ready(settings_service.get_all(db)),
        "scheduler": inspection_service.scheduler_status(),
        "stats": {
            "tasks": tasks_total,
            "tasks_enabled": tasks_enabled,
            "reports": reports_total,
            "builtin_reports": builtin_total,
            "upload_reports": upload_total,
        },
        "latest_report": _report_dict(latest) if latest else None,
    }


@router.get("/settings")
def get_inspection_settings(request: Request, db: Session = Depends(get_db)):
    _require_user(request, db)
    values = settings_service.get_all(db)
    office = inspection_office.office_settings(values)
    return {
        "retention_days": inspection_service.report_retention_days(db),
        "default_retention_days": inspection_service.DEFAULT_REPORT_RETENTION_DAYS,
        "max_retention_days": inspection_service.MAX_REPORT_RETENTION_DAYS,
        "office_enabled": office["enabled"],
        "office_document_server_url": office["document_server_url"],
        "office_public_base_url": office["public_base_url"],
        "office_has_secret": bool(office["jwt_secret"]),
        "office_ready": inspection_office.is_ready(values),
    }


@router.put("/settings")
def update_inspection_settings(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    user = _require_user(request, db, write=True)
    try:
        days = inspection_service.normalize_retention_days(payload.get("retention_days"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    values = settings_service.get_all(db)
    changes: Dict[str, Any] = {"inspection_report_retention_days": days}
    if "office_enabled" in payload:
        changes["inspection_office_enabled"] = bool(payload.get("office_enabled"))
    if "office_document_server_url" in payload:
        url = str(payload.get("office_document_server_url") or "").strip().rstrip("/")
        if url and urlparse(url).scheme not in ("http", "https"):
            raise HTTPException(status_code=400, detail="Document Server 地址必须以 http:// 或 https:// 开头")
        changes["inspection_office_document_server_url"] = url
    if "office_public_base_url" in payload:
        url = str(payload.get("office_public_base_url") or "").strip().rstrip("/")
        if url and urlparse(url).scheme not in ("http", "https"):
            raise HTTPException(status_code=400, detail="产品对外地址必须以 http:// 或 https:// 开头")
        changes["inspection_office_public_base_url"] = url
    if "office_jwt_secret" in payload:
        secret = str(payload.get("office_jwt_secret") or "").strip()
        if secret:
            changes["inspection_office_jwt_secret"] = secret
    before = {
        "retention_days": inspection_service.report_retention_days(db),
        "office_enabled": bool(values.get("inspection_office_enabled")),
        "office_ready": inspection_office.is_ready(values),
    }
    settings_service.save(db, changes)
    updated = settings_service.get_all(db)
    audit.record(
        db, request, module="inspection", action="update",
        target_type="inspection_settings", target_name="巡检报告/在线Office设置",
        before=before,
        after={"retention_days": days, "office_enabled": bool(updated.get("inspection_office_enabled")), "office_ready": inspection_office.is_ready(updated)},
        message="更新巡检报告保留和在线 Office 设置",
    )
    db.commit()
    return {
        "message": f"巡检报告保留天数已设置为 {days} 天" + ("（永久保留）" if days == 0 else ""),
        "retention_days": days,
        "office_enabled": bool(updated.get("inspection_office_enabled")),
        "office_ready": inspection_office.is_ready(updated),
    }


@router.get("/tasks")
def list_tasks(
    request: Request,
    keyword: str = "",
    enabled: Optional[bool] = None,
    page: int = 1,
    page_size: int = 50,
    db: Session = Depends(get_db),
):
    _require_user(request, db)
    query = db.query(InspectionTask)
    if keyword.strip():
        like = f"%{keyword.strip()}%"
        query = query.filter(
            or_(InspectionTask.name.like(like), InspectionTask.created_by.like(like))
        )
    if enabled is not None:
        query = query.filter(InspectionTask.enabled.is_(bool(enabled)))
    total = query.count()
    page = max(1, int(page or 1))
    page_size = max(1, min(200, int(page_size or 50)))
    rows = (
        query.order_by(InspectionTask.updated_at.desc(), InspectionTask.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "items": [_task_dict(db, request, task) for task in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/tasks/{task_id}")
def get_task(task_id: int, request: Request, db: Session = Depends(get_db)):
    _require_user(request, db)
    task = _task_or_404(db, task_id)
    return _task_dict(db, request, task)


@router.post("/tasks")
def create_task(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    user = _require_user(request, db, write=True)
    data = _normalize_task_payload(db, request, payload)
    task = InspectionTask(created_by=user.username or "", created_at=datetime.utcnow())
    _apply_task_payload(task, data)
    task.next_run_at = (
        inspection_service.compute_next_run(db, task) if task.enabled else None
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    audit.record(
        db,
        request,
        module="inspection",
        action="create",
        target_type="inspection_task",
        target_id=task.id,
        target_name=task.name,
        after=_task_dict(db, request, task),
        message="创建设备巡检任务",
    )
    return {"message": "巡检任务已创建", "task": _task_dict(db, request, task)}


@router.post("/tasks/{task_id}/stop")
def stop_task(task_id: int, request: Request, db: Session = Depends(get_db)):
    """停止巡检任务：停用定时调度，保留历史报告。"""
    user = _require_user(request, db, write=True)
    task = _task_or_404(db, task_id)
    before = _task_dict(db, request, task)
    task.enabled = False
    task.next_run_at = None
    task.last_status = "idle"
    task.last_message = "已手动停止巡检调度"
    db.commit()
    audit.record(
        db, request, module="inspection", action="update",
        target_type="inspection_task", target_name=task.name,
        before=before, after={"enabled": False},
        message="停止巡检任务",
    )
    db.commit()
    return {"message": "巡检任务已停止", "task": _task_dict(db, request, task)}


@router.put("/tasks/{task_id}")
def update_task(
    task_id: int,
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    _require_user(request, db, write=True)
    task = _task_or_404(db, task_id)
    before = _task_dict(db, request, task)
    data = _normalize_task_payload(db, request, payload)
    _apply_task_payload(task, data)
    task.updated_at = datetime.utcnow()
    task.next_run_at = (
        inspection_service.compute_next_run(db, task) if task.enabled else None
    )
    db.commit()
    db.refresh(task)
    audit.record(
        db,
        request,
        module="inspection",
        action="update",
        target_type="inspection_task",
        target_id=task.id,
        target_name=task.name,
        before=before,
        after=_task_dict(db, request, task),
        message="修改设备巡检任务",
    )
    return {"message": "巡检任务已保存", "task": _task_dict(db, request, task)}


@router.delete("/tasks/{task_id}")
def delete_task(task_id: int, request: Request, db: Session = Depends(get_db)):
    _require_user(request, db, write=True)
    task = _task_or_404(db, task_id)
    name = task.name
    db.delete(task)
    db.commit()
    audit.record(
        db,
        request,
        module="inspection",
        action="delete",
        target_type="inspection_task",
        target_id=task_id,
        target_name=name,
        message="删除设备巡检任务（历史报告保留）",
    )
    return {"message": "巡检任务已删除，历史巡检报告已保留"}


@router.post("/tasks/{task_id}/run")
def run_task(task_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db, write=True)
    task = _task_or_404(db, task_id)
    _ensure_task_targets_visible(db, request, task)
    try:
        report = inspection_service.run_task_now(
            db, task, username=user.username or ""
        )
    except inspection_service.DocxUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"巡检执行失败：{exc}") from exc
    audit.record(
        db,
        request,
        module="inspection",
        action="run",
        target_type="inspection_task",
        target_id=task.id,
        target_name=task.name,
        after={"report_id": report.id},
        message=f"手动执行设备巡检并生成报告 #{report.id}",
    )
    return {
        "message": "巡检完成，已生成 Word 报告",
        "task": _task_dict(db, request, task),
        "report": _report_dict(report, include_payload=True),
    }


# ==================== 巡检报告 ====================
@router.get("/reports")
def list_reports(
    request: Request,
    task_id: Optional[int] = None,
    source: str = "",
    keyword: str = "",
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
):
    user = _require_user(request, db)
    query = db.query(InspectionReport)
    if task_id:
        query = query.filter(InspectionReport.task_id == task_id)
    if source:
        query = query.filter(InspectionReport.source == source)
    if keyword.strip():
        like = f"%{keyword.strip()}%"
        query = query.filter(
            or_(
                InspectionReport.title.like(like),
                InspectionReport.task_name.like(like),
                InspectionReport.summary.like(like),
            )
        )
    page = max(1, int(page or 1))
    page_size = max(1, min(200, int(page_size or 20)))
    visible_rows = [
        item for item in query.order_by(InspectionReport.created_at.desc(), InspectionReport.id.desc()).all()
        if _can_access_report(db, request, item, user)
    ]
    total = len(visible_rows)
    rows = visible_rows[(page - 1) * page_size:page * page_size]
    return {
        "items": [_report_dict(item) for item in rows],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/reports/{report_id}")
def get_report(report_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    report = _report_or_404(db, report_id)
    if not _can_access_report(db, request, report, user):
        raise HTTPException(status_code=404, detail="巡检报告不存在")
    return _report_dict(report, include_payload=True)


@router.get("/reports/{report_id}/preview")
def preview_report(report_id: int, request: Request, db: Session = Depends(get_db)):
    """在线预览报告；上传的 Word 将提取段落和表格为 HTML。"""
    user = _require_user(request, db)
    report = _report_or_404(db, report_id)
    if not _can_access_report(db, request, report, user):
        raise HTTPException(status_code=404, detail="巡检报告不存在")
    try:
        path = inspection_service.report_path(report.filename)
        if not path.is_file():
            raise FileNotFoundError("巡检报告文件不存在或已被删除")
        html = inspection_service.render_docx_preview(path)
    except inspection_service.DocxUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"报告预览失败：{exc}") from exc
    return {"report_id": report.id, "source": report.source, "html": html}


@router.get("/reports/{report_id}/office-config")
def get_office_config(report_id: int, request: Request, db: Session = Depends(get_db)):
    """返回 ONLYOFFICE 编辑器配置；未配置时前端回退到只读 HTML 预览。"""
    user = _require_user(request, db, write=True)
    report = _report_or_404(db, report_id)
    if not _can_access_report(db, request, report, user):
        raise HTTPException(status_code=404, detail="巡检报告不存在")
    values = settings_service.get_all(db)
    config = inspection_office.build_editor_config(values, report, user)
    if not config:
        raise HTTPException(status_code=400, detail="尚未配置在线 Office Document Server")
    return config


@router.get("/reports/{report_id}/office-file")
def get_office_file(report_id: int, token: str = Query(""), db: Session = Depends(get_db)):
    """供 Document Server 拉取 Word 文件；短时签名，不依赖登录令牌。"""
    if not inspection_office.verify_file_token(token, "file", report_id):
        raise HTTPException(status_code=403, detail="在线 Office 文件令牌无效或已过期")
    report = _report_or_404(db, report_id)
    try:
        path = inspection_service.report_path(report.filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="巡检报告文件不存在")
    return FileResponse(path, media_type=inspection_service.DOCX_MIME)


@router.post("/reports/{report_id}/office-callback")
async def office_callback(report_id: int, request: Request, token: str = Query(""), db: Session = Depends(get_db)):
    """ONLYOFFICE 保存回调；下载编辑器生成的新 docx 并原子替换原文件。"""
    if not inspection_office.verify_file_token(token, "callback", report_id):
        return {"error": 1}
    report = _report_or_404(db, report_id)
    values = settings_service.get_all(db)
    office = inspection_office.office_settings(values)
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        return {"error": 1}
    status = int(payload.get("status") or 0)
    if status not in (2, 6):
        return {"error": 0}
    url = str(payload.get("url") or "").strip()
    if not url or not inspection_office.allowed_callback_url(url, office["document_server_url"]):
        return {"error": 1}
    try:
        response = requests.get(url, timeout=30, verify=False)
        response.raise_for_status()
        content = response.content
        inspection_service.validate_docx_bytes(content)
        path = inspection_service.report_path(report.filename)
        directory = inspection_service.ensure_reports_dir()
        fd, temp_name = tempfile.mkstemp(prefix=".office-", suffix=".docx", dir=directory)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(content)
            os.replace(temp_name, path)
        finally:
            if os.path.exists(temp_name):
                os.unlink(temp_name)
        report.file_size = len(content)
        db.commit()
        audit.record(
            db, request, module="inspection", action="update",
            target_type="inspection_report", target_id=report.id,
            target_name=report.title, message="在线 Office 保存巡检报告",
        )
        return {"error": 0}
    except Exception:  # noqa: BLE001
        return {"error": 1}


@router.get("/reports/{report_id}/download")
def download_report(report_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db)
    report = _report_or_404(db, report_id)
    if not _can_access_report(db, request, report, user):
        raise HTTPException(status_code=404, detail="巡检报告不存在")
    try:
        path = inspection_service.report_path(report.filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if not path.is_file():
        raise HTTPException(status_code=404, detail="巡检报告文件不存在或已被删除")
    filename = inspection_service.safe_display_name(
        report.title or report.original_filename or f"inspection-report-{report.id}",
        f"inspection-report-{report.id}",
    )
    return FileResponse(
        path,
        media_type=inspection_service.DOCX_MIME,
        filename=filename,
    )


@router.post("/reports/upload")
async def upload_report(
    request: Request,
    file: UploadFile = File(..., description="Word 巡检报告（仅 .docx，最大 50MB）"),
    title: str = Form("", description="报告标题（可选，默认取文件名）"),
    note: str = Form("", description="备注（可选）"),
    task_id: Optional[int] = Form(None, description="关联巡检任务（可选）"),
    db: Session = Depends(get_db),
):
    user = _require_user(request, db, write=True)
    if len(title.strip()) > 300:
        raise HTTPException(status_code=400, detail="报告标题过长（最多 300 个字符）")
    if len(note.strip()) > 2000:
        raise HTTPException(status_code=400, detail="报告备注过长（最多 2000 个字符）")
    task: Optional[InspectionTask] = None
    if task_id:
        task = _task_or_404(db, task_id)
    original = file.filename or "upload.docx"
    try:
        content = await file.read(inspection_service.MAX_UPLOAD_BYTES + 1)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"读取上传文件失败：{exc}") from exc
    if len(content) > inspection_service.MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=413,
            detail=f"文件超过 {inspection_service.MAX_UPLOAD_MB}MB 限制",
        )
    try:
        report = inspection_service.save_uploaded_report(
            db,
            content=content,
            original_filename=original,
            title=title,
            note=note,
            task=task,
            username=user.username or "",
        )
    except inspection_service.DocxUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit.record(
        db,
        request,
        module="inspection",
        action="upload",
        target_type="inspection_report",
        target_id=report.id,
        target_name=report.title,
        after={"original_filename": report.original_filename, "size": report.file_size},
        message="上传自定义巡检报告",
    )
    return {"message": "巡检报告已上传", "report": _report_dict(report, include_payload=True)}


@router.delete("/reports/{report_id}")
def delete_report(report_id: int, request: Request, db: Session = Depends(get_db)):
    user = _require_user(request, db, write=True)
    report = _report_or_404(db, report_id)
    if not _can_access_report(db, request, report, user):
        raise HTTPException(status_code=404, detail="巡检报告不存在")
    title = report.title
    inspection_service.delete_report_file(report)
    db.delete(report)
    db.commit()
    audit.record(
        db,
        request,
        module="inspection",
        action="delete",
        target_type="inspection_report",
        target_id=report_id,
        target_name=title,
        message="删除巡检报告",
    )
    return {"message": "巡检报告已删除"}


# ==================== 参数校验 ====================
def _normalize_task_payload(
    db: Session, request: Request, payload: Dict[str, Any]
) -> Dict[str, Any]:
    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="请求参数格式不正确")
    name = str(payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="请填写巡检任务名称")
    if len(name) > 200:
        raise HTTPException(status_code=400, detail="任务名称过长（最多 200 个字符）")

    target_mode = str(payload.get("target_mode") or "assets").strip()
    if target_mode not in ("assets", "custom"):
        raise HTTPException(status_code=400, detail="巡检对象类型仅支持 assets 或 custom")

    raw_ids = payload.get("asset_ids") or []
    if not isinstance(raw_ids, list):
        raise HTTPException(status_code=400, detail="资产列表格式不正确")
    asset_ids: List[int] = []
    for raw in raw_ids:
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="资产 ID 不合法") from exc
        if value not in asset_ids:
            asset_ids.append(value)
    if len(asset_ids) > inspection_service.MAX_ASSETS_PER_TASK:
        raise HTTPException(
            status_code=400,
            detail=f"单个巡检任务最多选择 {inspection_service.MAX_ASSETS_PER_TASK} 台资产",
        )
    if asset_ids:
        scoped = asset_scope.scope_device_query(
            db, request, db.query(Device.id).filter(Device.id.in_(asset_ids))
        )
        found = {row[0] for row in scoped.all()}
        missing = [item for item in asset_ids if item not in found]
        if missing:
            preview = "、".join(str(item) for item in missing[:10])
            raise HTTPException(
                status_code=400,
                detail=f"以下资产不存在或无权访问：{preview}",
            )

    try:
        custom_devices = inspection_service.validate_custom_devices(
            payload.get("custom_devices") or []
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    include_virtualization = bool(payload.get("include_virtualization", False))
    run_commands = bool(payload.get("run_commands", True))
    if not asset_ids and not custom_devices:
        if not (include_virtualization and db.query(VirtualPlatform).count() > 0):
            raise HTTPException(
                status_code=400,
                detail="请至少选择一台资产或添加一个自定义设备；仅巡检虚拟化平台时需先配置平台",
            )

    schedule_type = str(payload.get("schedule_type") or "interval").strip()
    if schedule_type not in ("interval", "daily"):
        raise HTTPException(status_code=400, detail="调度方式仅支持 interval 或 daily")
    interval_hours = payload.get("interval_hours", 24)
    try:
        interval_hours = int(interval_hours)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="巡检间隔必须是整数小时") from exc
    if interval_hours < 1 or interval_hours > inspection_service.MAX_TASK_INTERVAL_HOURS:
        raise HTTPException(
            status_code=400,
            detail=f"巡检间隔应为 1~{inspection_service.MAX_TASK_INTERVAL_HOURS} 小时",
        )
    daily_time = str(payload.get("daily_time") or "02:00").strip()
    if schedule_type == "daily":
        try:
            daily_time = inspection_service.normalize_daily_time(daily_time)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return {
        "name": name,
        "enabled": bool(payload.get("enabled", True)),
        "target_mode": target_mode,
        "asset_ids": asset_ids,
        "custom_devices": custom_devices,
        "include_virtualization": include_virtualization,
        "run_commands": run_commands,
        "schedule_type": schedule_type,
        "interval_hours": interval_hours,
        "daily_time": daily_time,
    }


def _apply_task_payload(task: InspectionTask, data: Dict[str, Any]) -> None:
    task.name = data["name"]
    task.enabled = data["enabled"]
    task.target_mode = data["target_mode"]
    task.asset_ids = data["asset_ids"]
    task.custom_devices = data["custom_devices"]
    task.include_virtualization = data["include_virtualization"]
    task.run_commands = data.get("run_commands", True)
    task.schedule_type = data["schedule_type"]
    task.interval_hours = data["interval_hours"]
    task.daily_time = data["daily_time"]
    # 借用服务层校验，确保 daily/interval 取值合法且归一化
    try:
        inspection_service.validate_schedule(task)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


def _ensure_task_targets_visible(
    db: Session, request: Request, task: InspectionTask
) -> None:
    visible = asset_scope.visible_device_ids(db, request)
    if visible is None:
        return
    hidden = [item for item in _asset_ids(task) if item not in visible]
    if hidden:
        raise HTTPException(
            status_code=403,
            detail="巡检任务包含当前账号无权访问的资产，无法执行",
        )
