"""审计日志路由：查询、导出、清理"""
import csv
import io
import json
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.audit import AuditLog
from ..models.database import get_db
from ..services import audit as audit_service
from ..services import settings as settings_service

router = APIRouter(prefix="/api/audit", tags=["审计日志"])

MODULE_LABELS = {
    "settings": "系统配置",
    "users": "用户",
    "roles": "角色",
    "groups": "群组",
    "notifications": "通知通道",
    "config": "配置导入导出",
    "security": "登录安全",
}

ACTION_LABELS = {
    "create": "新增",
    "update": "修改",
    "delete": "删除",
    "import": "导入",
    "export": "导出",
    "login": "登录",
    "cleanup": "清理",
}


def _to_dict(item: AuditLog) -> dict:
    return {
        "id": item.id,
        "module": item.module,
        "module_label": MODULE_LABELS.get(item.module, item.module),
        "action": item.action,
        "action_label": ACTION_LABELS.get(item.action, item.action),
        "target_type": item.target_type,
        "target_id": item.target_id,
        "target_name": item.target_name,
        "operator": item.operator,
        "operator_id": item.operator_id,
        "ip": item.ip,
        "before": item.before or {},
        "after": item.after or {},
        "changed": item.changed or [],
        "status": item.status,
        "message": item.message,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


@router.get("/meta")
def get_meta(request: Request, db: Session = Depends(get_db)):
    """审计模块与动作选项（普通用户只返回自己的记录范围）"""
    is_superuser = bool(getattr(request.state, "is_superuser", False))
    username = str(getattr(request.state, "username", "") or "")
    module_query = db.query(AuditLog.module)
    action_query = db.query(AuditLog.action)
    if not is_superuser:
        if not username:
            raise HTTPException(status_code=401, detail="未登录，请先登录")
        module_query = module_query.filter(AuditLog.operator == username)
        action_query = action_query.filter(AuditLog.operator == username)
    modules = [
        row[0]
        for row in module_query.distinct().order_by(AuditLog.module).all()
        if row[0]
    ]
    actions = [
        row[0]
        for row in action_query.distinct().order_by(AuditLog.action).all()
        if row[0]
    ]
    return {
        "modules": [{"value": m, "label": MODULE_LABELS.get(m, m)} for m in modules],
        "actions": [{"value": a, "label": ACTION_LABELS.get(a, a)} for a in actions],
        "retention_days": int(settings_service.get_value(db, "audit_retention_days") or 0),
        "scope": "all" if is_superuser else "self",
    }


@router.get("/logs")
def list_logs(
    request: Request,
    module: Optional[str] = None,
    action: Optional[str] = None,
    operator: Optional[str] = None,
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """分页查询审计日志：超管全量，其他用户仅本人记录"""
    is_superuser = bool(getattr(request.state, "is_superuser", False))
    username = str(getattr(request.state, "username", "") or "")
    if not is_superuser and not username:
        raise HTTPException(status_code=401, detail="未登录，请先登录")
    if status not in (None, "", "success", "failed"):
        raise HTTPException(status_code=400, detail="状态筛选只支持 success 或 failed")
    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)
    total, items = audit_service.query_logs(
        db, module=module, action=action, operator=operator,
        keyword=keyword, start=start_dt, end=end_dt, page=page, size=size,
        scope_operator=None if is_superuser else username,
        status=status or None,
    )
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [_to_dict(item) for item in items],
        "scope": "all" if is_superuser else "self",
    }


@router.get("/export")
def export_logs(
    request: Request,
    module: Optional[str] = None,
    action: Optional[str] = None,
    operator: Optional[str] = None,
    keyword: Optional[str] = None,
    status: Optional[str] = None,
    start: Optional[str] = None,
    end: Optional[str] = None,
    fmt: str = Query("csv", alias="format"),
    db: Session = Depends(get_db),
):
    """导出审计日志（CSV / JSON）：超管全量，其他用户仅本人记录"""
    is_superuser = bool(getattr(request.state, "is_superuser", False))
    username = str(getattr(request.state, "username", "") or "")
    if not is_superuser and not username:
        raise HTTPException(status_code=401, detail="未登录，请先登录")
    if status not in (None, "", "success", "failed"):
        raise HTTPException(status_code=400, detail="状态筛选只支持 success 或 failed")
    scope_operator = None if is_superuser else username
    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)
    # 导出不分页：按 200 条一批取完（最多 10000 条，避免误导出过大）
    items = []
    page_no = 1
    while len(items) < 10000:
        _, batch = audit_service.query_logs(
            db, module=module, action=action, operator=operator,
            keyword=keyword, start=start_dt, end=end_dt, page=page_no, size=200,
            scope_operator=scope_operator, status=status or None,
        )
        if not batch:
            break
        items.extend(batch)
        if len(batch) < 200:
            break
        page_no += 1
    if fmt == "json":
        payload = json.dumps(
            [_to_dict(item) for item in items], ensure_ascii=False, indent=2
        )
        filename = f"audit-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
        content = payload.encode("utf-8")
        media = "application/json"
    else:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow([
            "时间", "模块", "动作", "对象类型", "对象", "操作人", "IP",
            "状态", "变更字段", "备注",
        ])
        for item in items:
            writer.writerow([
                item.created_at.strftime("%Y-%m-%d %H:%M:%S") if item.created_at else "",
                MODULE_LABELS.get(item.module, item.module),
                ACTION_LABELS.get(item.action, item.action),
                item.target_type or "",
                item.target_name or item.target_id or "",
                item.operator or "",
                item.ip or "",
                "成功" if item.status == "success" else "失败",
                ", ".join(item.changed or []),
                item.message or "",
            ])
        filename = f"audit-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
        content = ("\ufeff" + buffer.getvalue()).encode("utf-8")
        media = "text/csv; charset=utf-8"

    audit_service.record(
        db, request, module="audit", action="export",
        target_type="audit", target_name=f"审计日志导出（{len(items)} 条）",
        message=f"导出格式: {fmt}",
    )
    return Response(
        content=content,
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.delete("/cleanup")
def cleanup_logs(request: Request, days: int = Query(..., ge=1, le=3650), db: Session = Depends(get_db)):
    """手动清理指定天数之前的审计日志（仅超级管理员）"""
    if not bool(getattr(request.state, "is_superuser", False)):
        raise HTTPException(status_code=403, detail="仅超级管理员可以清理审计日志")
    deleted = audit_service.cleanup(db, days)
    audit_service.record(
        db, request, module="audit", action="cleanup",
        target_type="audit", message=f"清理 {days} 天前的审计日志，共 {deleted} 条",
    )
    return {"deleted": deleted, "days": days}


def _parse_dt(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = value.strip().replace("Z", "")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None
