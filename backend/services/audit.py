"""配置变更审计服务：写入、脱敏、查询、清理"""
import json
import logging
import re
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models.audit import AuditLog

logger = logging.getLogger(__name__)

# 需要脱敏的字段名（包含匹配，不区分大小写）
_SENSITIVE_KEY = re.compile(
    r"(password|passwd|pwd|token|secret|private|community|auth|api[_-]?key|access[_-]?key|redis[_-]?url)",
    re.IGNORECASE,
)
_MASK = "******"


def mask_sensitive(value: Any) -> Any:
    """递归脱敏字典/列表中的密码、Token、密钥等"""
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if _SENSITIVE_KEY.search(str(key)):
                result[key] = _MASK if item not in (None, "") else item
            else:
                result[key] = mask_sensitive(item)
        return result
    if isinstance(value, list):
        return [mask_sensitive(item) for item in value]
    return value


def jsonable(value: Any) -> Any:
    """转换为可写入 JSON 列的值"""
    try:
        json.dumps(value, ensure_ascii=False)
        return value
    except (TypeError, ValueError):
        return json.loads(json.dumps(value, ensure_ascii=False, default=str))


def diff_keys(before: Optional[dict], after: Optional[dict]) -> List[str]:
    """计算发生变化的字段"""
    before = before or {}
    after = after or {}
    keys = set(before) | set(after)
    return sorted(k for k in keys if before.get(k) != after.get(k))


def client_ip(request) -> str:
    """取请求来源 IP（优先 X-Forwarded-For 由 security.client_ip 处理代理场景）"""
    if request is None:
        return ""
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()[:64]
    client = getattr(request, "client", None)
    return (getattr(client, "host", "") or "")[:64]


def record(
    db: Session,
    request,
    module: str,
    action: str,
    target_type: str = "",
    target_id: Any = "",
    target_name: str = "",
    before: Optional[dict] = None,
    after: Optional[dict] = None,
    status: str = "success",
    message: str = "",
    operator: Optional[str] = None,
    operator_id: Optional[int] = None,
    commit: bool = True,
) -> Optional[AuditLog]:
    """写入审计日志；失败不影响业务主流程"""
    try:
        before_masked = mask_sensitive(before or {})
        after_masked = mask_sensitive(after or {})
        if operator is None:
            operator = getattr(getattr(request, "state", None), "username", None) or "system"
        if operator_id is None:
            operator_id = getattr(getattr(request, "state", None), "user_id", None)
        item = AuditLog(
            module=module,
            action=action,
            target_type=target_type,
            target_id=str(target_id or "")[:100],
            target_name=(target_name or "")[:200],
            operator=(operator or "system")[:100],
            operator_id=operator_id,
            ip=client_ip(request),
            before=jsonable(before_masked),
            after=jsonable(after_masked),
            changed=diff_keys(before_masked, after_masked),
            status=status,
            message=(message or "")[:2000],
            created_at=datetime.utcnow(),
        )
        db.add(item)
        if commit:
            db.commit()
        return item
    except Exception as exc:  # noqa: BLE001
        logger.warning("写入审计日志失败: %s", exc)
        try:
            db.rollback()
        except Exception:  # noqa: BLE001
            pass
        return None


def query_logs(
    db: Session,
    module: Optional[str] = None,
    action: Optional[str] = None,
    operator: Optional[str] = None,
    keyword: Optional[str] = None,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
    page: int = 1,
    size: int = 20,
    scope_operator: Optional[str] = None,
    status: Optional[str] = None,
):
    query = db.query(AuditLog)
    if scope_operator:
        # 非超级管理员只能查询自己的审计记录，忽略前端传入的其他操作人筛选
        query = query.filter(AuditLog.operator == scope_operator)
    if module:
        query = query.filter(AuditLog.module == module)
    if action:
        query = query.filter(AuditLog.action == action)
    if status:
        query = query.filter(AuditLog.status == status)
    if operator and not scope_operator:
        query = query.filter(AuditLog.operator.ilike(f"%{operator}%"))
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(
            or_(
                AuditLog.target_name.ilike(like),
                AuditLog.message.ilike(like),
                AuditLog.target_id.ilike(like),
            )
        )
    if start:
        query = query.filter(AuditLog.created_at >= start)
    if end:
        query = query.filter(AuditLog.created_at <= end)
    total = query.count()
    items = (
        query.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
        .offset(max(0, (page - 1) * size))
        .limit(min(size, 200))
        .all()
    )
    return total, items


def cleanup(db: Session, retention_days: int) -> int:
    """清理超过保留天数的审计日志（0 表示永久保留）"""
    if not retention_days or retention_days <= 0:
        return 0
    cutoff = datetime.utcnow() - timedelta(days=retention_days)
    deleted = db.query(AuditLog).filter(AuditLog.created_at < cutoff).delete(
        synchronize_session=False
    )
    db.commit()
    if deleted:
        logger.info("已清理 %d 条过期审计日志（保留 %d 天）", deleted, retention_days)
    return deleted
