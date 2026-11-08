"""系统更新接口：上传更新包、在线更新、任务状态。"""
from __future__ import annotations

import shutil
from pathlib import Path
import hmac
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy.orm import Session

from ..config import PROJECT_ROOT
from ..models.database import get_db
from ..services import audit as audit_service
from ..services import settings as settings_service
from ..services import update_manager

router = APIRouter(prefix="/api/system/update", tags=["系统更新"])


def _version_payload() -> Dict[str, Any]:
    return update_manager.read_version()


def _job_payload(job: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not job:
        return None
    safe = dict(job)
    # 不向前端暴露内部绝对路径
    for key in ("zip_path", "stage_dir", "backup_dir", "status_path", "log_path", "app_dir"):
        safe.pop(key, None)
    return safe


def _public_job_payload(job: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    safe = _job_payload(job)
    if safe:
        safe.pop("status_token", None)
        safe.pop("username", None)
    return safe


def _ensure_newer(package: Dict[str, Any], force: bool) -> None:
    current = update_manager.read_version()
    if not force and package.get("version") == current.get("version"):
        raise HTTPException(
            status_code=400,
            detail=f"更新包版本 {package.get('version')} 与当前版本相同；如需强制重装请勾选强制更新",
        )


@router.get("")
def get_update_info(db: Session = Depends(get_db)):
    values = settings_service.get_all(db)
    job = update_manager.load_job()
    return {
        "current": _version_payload(),
        "online_url": values.get("update_online_url") or "",
        "restart_mode": update_manager.restart_mode(),
        "job": _job_payload(job),
        "active": update_manager.active_job() is not None,
        "backups": update_manager.list_backups(),
        "limits": {
            "max_zip_mb": 512,
            "backup_retention": update_manager.DEFAULT_BACKUP_RETENTION,
        },
    }


@router.put("/config")
def save_update_config(
    request: Request,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
):
    url = str(payload.get("online_url") or "").strip()
    if url and not (url.startswith("http://") or url.startswith("https://")):
        raise HTTPException(status_code=400, detail="在线更新地址必须以 http:// 或 https:// 开头")
    if len(url) > 1000:
        raise HTTPException(status_code=400, detail="在线更新地址过长")
    settings_service.save(db, {"update_online_url": url})
    audit_service.record(
        db, request, module="system", action="update",
        target_type="update_config", target_name="系统更新配置",
        after={"update_online_url": url}, message="修改在线更新服务地址",
    )
    return {"message": "在线更新地址已保存", "online_url": url}


def _start_job(package: Dict[str, Any], source: str, request: Request, db: Session):
    if update_manager.active_job():
        raise HTTPException(status_code=409, detail="已有更新任务正在执行，请等待完成")
    try:
        job = update_manager.start_update(
            package,
            source=source,
            username=getattr(request.state, "username", "") or "",
            install_dependencies=True,
        )
    except update_manager.UpdateError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    audit_service.record(
        db, request, module="system", action="update",
        target_type="system_update", target_name=f"v{job['new_version']}",
        after={
            "job_id": job["job_id"], "source": source,
            "current_version": job["current_version"],
            "new_version": job["new_version"],
            "sha256": job.get("sha256", ""),
        },
        message=f"启动系统更新 v{job['current_version']} → v{job['new_version']}",
    )
    return job


@router.post("/upload")
async def upload_update(
    request: Request,
    file: UploadFile = File(...),
    dry_run: bool = Query(False),
    force: bool = Query(False),
    db: Session = Depends(get_db),
):
    if not file.filename or not file.filename.lower().endswith(".zip"):
        raise HTTPException(status_code=400, detail="请上传 .zip 更新包")
    try:
        saved = update_manager.save_upload(file, file.filename)
    except update_manager.UpdateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"保存更新包失败: {exc}") from exc

    package = None
    try:
        package = update_manager.prepare_package(saved, source="upload")
        _ensure_newer(package, force)
        if dry_run:
            result = {
                "valid": True,
                "current": _version_payload(),
                "package": {
                    "version": package.get("version"),
                    "display_version": package.get("display_version"),
                    "build": package.get("build"),
                    "sha256": package.get("sha256"),
                    "filename": file.filename,
                },
            }
            shutil.rmtree(package["stage"], ignore_errors=True)
            saved.unlink(missing_ok=True)
            return result
        job = _start_job(package, "upload", request, db)
        return {"message": "更新包校验通过，正在自动更新并重启服务", "job": _job_payload(job)}
    except HTTPException:
        if package:
            shutil.rmtree(package.get("stage", ""), ignore_errors=True)
        saved.unlink(missing_ok=True)
        raise
    except update_manager.UpdateError as exc:
        if package:
            shutil.rmtree(package.get("stage", ""), ignore_errors=True)
        saved.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        if package:
            shutil.rmtree(package.get("stage", ""), ignore_errors=True)
        saved.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"更新包处理失败: {exc}") from exc


@router.post("/check")
def check_online_update(request: Request, db: Session = Depends(get_db)):
    values = settings_service.get_all(db)
    url = str(values.get("update_online_url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="请先保存在线更新服务地址")
    try:
        meta = update_manager.fetch_online_metadata(url)
        version = meta.get("version") or ""
        package_info = None
        if not version:
            # ZIP 直链：下载后读取包内版本，校验完成后立即清理
            saved = update_manager.download_url(meta["download_url"], meta.get("sha256") or "")
            try:
                package = update_manager.prepare_package(saved, source="online-check")
                version = package["version"]
                package_info = {
                    "version": package["version"],
                    "display_version": package["display_version"],
                    "build": package["build"],
                }
            finally:
                shutil.rmtree(update_manager.STAGING_DIR / package["job_id"], ignore_errors=True) if package_info else None
                saved.unlink(missing_ok=True)
        current = _version_payload()
        return {
            "current": current,
            "version": version,
            "display_version": meta.get("display_version") or version,
            "notes": meta.get("notes") or "",
            "download_url": meta.get("download_url"),
            "update_available": bool(version and version != current.get("version")),
            "package": package_info,
        }
    except update_manager.UpdateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"检查在线更新失败: {exc}") from exc


@router.post("/online")
def start_online_update(request: Request, db: Session = Depends(get_db)):
    values = settings_service.get_all(db)
    url = str(values.get("update_online_url") or "").strip()
    if not url:
        raise HTTPException(status_code=400, detail="请先保存在线更新服务地址")
    if update_manager.active_job():
        raise HTTPException(status_code=409, detail="已有更新任务正在执行，请等待完成")
    saved = None
    package = None
    try:
        meta = update_manager.fetch_online_metadata(url)
        saved = update_manager.download_url(meta["download_url"], meta.get("sha256") or "")
        package = update_manager.prepare_package(saved, source="online")
        _ensure_newer(package, False)
        job = _start_job(package, "online", request, db)
        return {"message": "在线更新包校验通过，正在自动更新并重启服务", "job": _job_payload(job)}
    except HTTPException:
        if package:
            shutil.rmtree(package.get("stage", ""), ignore_errors=True)
        if saved:
            saved.unlink(missing_ok=True)
        raise
    except update_manager.UpdateError as exc:
        if package:
            shutil.rmtree(package.get("stage", ""), ignore_errors=True)
        if saved:
            saved.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        if package:
            shutil.rmtree(package.get("stage", ""), ignore_errors=True)
        if saved:
            saved.unlink(missing_ok=True)
        raise HTTPException(status_code=500, detail=f"在线更新失败: {exc}") from exc


@router.get("/backups/{backup_id}/files")
def get_backup_files(backup_id: str):
    """查看历史版本备份文件清单（不暴露绝对路径）。"""
    try:
        return update_manager.backup_files(backup_id)
    except update_manager.UpdateError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/backups/{backup_id}")
def delete_backup_version(
    backup_id: str,
    request: Request,
    db: Session = Depends(get_db),
):
    """删除一个历史版本备份。"""
    try:
        removed = update_manager.delete_backup(backup_id)
    except update_manager.UpdateError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    audit_service.record(
        db, request, module="system", action="update",
        target_type="version_backup", target_name=f"v{removed.get('display_version')}",
        after=removed, message=f"删除历史版本备份 v{removed.get('display_version')}",
    )
    return {"message": f"历史版本 v{removed.get('display_version')} 已删除", **removed}


@router.post("/rollback")
def rollback_version(
    request: Request,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
):
    """从最近保留的版本备份回退。"""
    backup_id = str(payload.get("backup_id") or payload.get("job_id") or "").strip()
    if not backup_id:
        raise HTTPException(status_code=400, detail="请选择要回退的版本")
    force = bool(payload.get("force"))
    try:
        job = update_manager.start_rollback(
            backup_id,
            username=getattr(request.state, "username", "") or "",
            force=force,
        )
    except update_manager.UpdateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db, request, module="system", action="update",
        target_type="system_rollback", target_name=f"v{job['new_version']}",
        after={
            "job_id": job["job_id"],
            "backup_id": backup_id,
            "current_version": job["current_version"],
            "target_version": job["new_version"],
        },
        message=f"启动系统版本回退 {job['current_version']} → {job['new_version']}",
    )
    return {"message": "版本回退任务已启动，正在备份当前程序并重启服务", "job": _job_payload(job)}


@router.get("/public-status/{job_id}")
def public_update_status(job_id: str, token: str = Query("", max_length=128)):
    """仅凭随机状态令牌读取更新进度。

    更新重启会轮换登录令牌或短暂中断 API；该接口只返回脱敏进度，
    使用 job 的独立随机令牌，不暴露版本包路径、用户或任何管理数据。
    """
    job = update_manager.load_job(job_id)
    expected = str((job or {}).get("status_token") or "")
    if not job or not expected or not hmac.compare_digest(expected, str(token or "")):
        raise HTTPException(status_code=404, detail="更新任务不存在")
    return {
        "job": _public_job_payload(job),
        "current": _version_payload(),
    }


@router.get("/status")
def get_update_status(job_id: Optional[str] = Query(None, max_length=100)):
    job = update_manager.load_job(job_id)
    return {
        "job": _job_payload(job),
        "active": update_manager.active_job() is not None,
        "current": _version_payload(),
    }
