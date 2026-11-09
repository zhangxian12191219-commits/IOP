"""系统运维接口：数据库备份列表/立即备份/下载/删除"""
import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..models.user import User
from ..services.auth import get_current_user, has_permission
from ..services import audit as audit_service
from ..services import backup as backup_service
from ..services import debug_bundle
from ..services import settings as settings_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/system", tags=["系统维护"])

BACKUP_SETTING_KEYS = ("backup_enabled", "backup_interval_hours", "backup_retention_count")


class DebugCollectRequest(BaseModel):
    note: str = ""


def _require_debug(current: User = Depends(get_current_user)) -> User:
    if not current.is_superuser and not has_permission(current, "settings:view"):
        raise HTTPException(status_code=403, detail="Debug 日志收集仅系统配置查看权限可操作")
    return current


def _require_superuser(current: User = Depends(get_current_user)) -> User:
    if not current.is_superuser:
        raise HTTPException(status_code=403, detail="数据库备份仅超级管理员可操作")
    return current


def _backup_config(db: Session) -> Dict[str, Any]:
    values = settings_service.get_all(db)
    return {
        "backup_enabled": bool(values.get("backup_enabled")),
        "backup_interval_hours": int(values.get("backup_interval_hours") or 24),
        "backup_retention_count": int(values.get("backup_retention_count") or 7),
        "backup_dir": str(backup_service.backup_dir()),
        "latest": backup_service.latest_backup(),
    }


@router.get("/backups")
def list_backups(db: Session = Depends(get_db), current: User = Depends(_require_superuser)):
    """备份列表与自动备份配置"""
    return {
        "config": _backup_config(db),
        "items": backup_service.list_backups(),
    }


@router.post("/backups")
def create_backup(request: Request, db: Session = Depends(get_db), current: User = Depends(_require_superuser)):
    """立即创建一次数据库备份"""
    config = _backup_config(db)
    try:
        result = backup_service.create_backup(
            reason="manual",
            retention=config["backup_retention_count"],
        )
    except Exception as exc:  # noqa: BLE001
        audit_service.record(
            db, request, module="system", action="create",
            target_type="backup", target_name="数据库备份",
            status="failed", message=str(exc)[:800],
        )
        raise HTTPException(status_code=500, detail=f"备份失败: {exc}") from exc
    audit_service.record(
        db, request, module="system", action="create",
        target_type="backup", target_name=result["name"],
        after={"file": result["name"], "size": result["size"],
               "method": result.get("method")},
        message=f"手动创建数据库备份（{result.get('method')}，{result['size']} 字节）",
    )
    return result


@router.delete("/backups/{name}")
def delete_backup(name: str, request: Request, db: Session = Depends(get_db), current: User = Depends(_require_superuser)):
    """删除指定备份文件"""
    try:
        deleted = backup_service.delete_backup(name)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="备份文件不存在")
    audit_service.record(
        db, request, module="system", action="delete",
        target_type="backup", target_name=name,
        message=f"删除数据库备份 {name}",
    )
    return {"message": "备份已删除", "name": name}


@router.get("/backups/{name}/download")
def download_backup(name: str, current: User = Depends(_require_superuser)):
    """下载备份文件（需 settings:edit 权限）"""
    safe = Path(name).name
    if not safe.startswith(backup_service.BACKUP_PREFIX):
        raise HTTPException(status_code=400, detail="非法的备份文件名")
    path = backup_service.backup_dir() / safe
    if not path.exists():
        raise HTTPException(status_code=404, detail="备份文件不存在")
    return FileResponse(
        path=str(path),
        filename=safe,
        media_type="application/octet-stream",
    )

@router.post("/debug/collect")
def collect_debug_bundle(
    payload: DebugCollectRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(_require_debug),
):
    """生成脱敏 Debug 诊断包，供用户下载后反馈问题。"""
    try:
        result = debug_bundle.create_bundle(db, payload.note)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Debug 诊断包生成失败")
        raise HTTPException(status_code=500, detail=f"Debug 日志收集失败：{exc}") from exc
    audit_service.record(
        db, request, module="system", action="create",
        target_type="debug_bundle", target_name=result["name"],
        message=f"生成 Debug 诊断包 {result['name']}",
        operator=current.username,
    )
    return result


@router.get("/debug/{name}/download")
def download_debug_bundle(
    name: str,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(_require_debug),
):
    """下载已生成的 Debug 诊断包。"""
    safe = Path(name).name
    if not safe.startswith("debug-") or not safe.endswith(".zip"):
        raise HTTPException(status_code=400, detail="非法的诊断包文件名")
    path = debug_bundle.DEBUG_DIR / safe
    if not path.is_file():
        raise HTTPException(status_code=404, detail="诊断包不存在或已过期")
    audit_service.record(
        db, request, module="system", action="download",
        target_type="debug_bundle", target_name=safe,
        message=f"下载 Debug 诊断包 {safe}",
        operator=current.username,
    )
    return FileResponse(
        path=str(path),
        filename=safe,
        media_type="application/zip",
    )
