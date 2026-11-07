"""网站监控路由 - CRUD + 检查记录 + 批量导入导出"""
import csv
import io
import ipaddress
from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, Form, Body
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_
from typing import List, Optional
from datetime import datetime, timedelta
from urllib.parse import urlparse, urlsplit, urlunsplit, parse_qsl, urlencode

from ..models.database import get_db
from ..models.website import WebsiteTarget, WebsiteCheckHistory, WebsiteAlert
from ..models.schemas import WebsiteTargetCreate, WebsiteTargetUpdate

router = APIRouter(prefix="/api/website", tags=["网站监控"])

EXPORT_COLUMNS = [
    "name", "url", "monitor_type", "domain", "ip_address", "port", "method",
    "expected_status", "expected_statuses", "expected_keywords", "timeout",
    "check_interval", "slow_threshold_ms", "ignore_https_errors",
    "cache_bust_seconds", "expected_statuses", "cert_monitor_enabled",
    "cert_expiry_days", "cert_alert_level", "cert_root_domain",
    "cert_subdomains", "category", "category_mode", "sort_order",
    "is_enabled", "description",
]


def _parse_time(value: Optional[str], end: bool = False) -> Optional[datetime]:
    if not value:
        return None
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text[:10], "%Y-%m-%d")
        except ValueError:
            return None
    if end and len(str(value).strip()) <= 10:
        parsed = parsed + timedelta(days=1)
    return parsed


def _is_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(str(value).strip().strip("[]"))
        return True
    except ValueError:
        return False


def _normalize_target_data(data: dict) -> dict:
    """统一 URL、域名/IP，并对 HTTP 地址补齐协议。"""
    mtype = str(data.get("monitor_type") or "http").lower()
    data["monitor_type"] = mtype
    url = str(data.get("url") or "").strip()
    if mtype in ("http", "https"):
        if url and "://" not in url:
            url = "http://" + url
        data["url"] = url
        if url:
            parsed = urlsplit(url)
            host = parsed.hostname or ""
            if parsed.scheme == "https":
                data["monitor_type"] = "https"
            else:
                data["monitor_type"] = data["monitor_type"] or "http"
            data["domain"] = "" if _is_ip(host) else host
            data["ip_address"] = host if _is_ip(host) else None
    else:
        host = str(data.get("domain") or data.get("ip_address") or "").strip()
        data["domain"] = "" if _is_ip(host) else host
        data["ip_address"] = host if _is_ip(host) else None
        if not data.get("url") and host:
            data["url"] = f"{mtype}://{host}" + (f":{data.get('port')}" if mtype == "tcp" and data.get("port") else "")
    mode = str(data.get("category_mode") or "auto").lower()
    data["category_mode"] = "manual" if mode == "manual" else "auto"
    if data["category_mode"] == "auto" or not str(data.get("category") or "").strip():
        data["category"] = _auto_category(data)
    else:
        data["category"] = str(data.get("category")).strip()[:100]
    try:
        data["sort_order"] = int(data.get("sort_order") or 0)
    except (TypeError, ValueError):
        data["sort_order"] = 0
    try:
        data["cache_bust_seconds"] = max(0, min(86400, int(data.get("cache_bust_seconds") or 0)))
    except (TypeError, ValueError):
        data["cache_bust_seconds"] = 0
    data["expected_statuses"] = str(data.get("expected_statuses") or "").strip()[:200]
    return data


def _auto_category(data: dict) -> str:
    host = str(data.get("domain") or data.get("ip_address") or "").strip().lower()
    if not host and data.get("url"):
        try:
            parsed = urlsplit(str(data.get("url")) if "://" in str(data.get("url")) else f"http://{data.get('url')}")
            host = (parsed.hostname or "").strip().lower()
        except Exception:  # noqa: BLE001
            host = ""
    if _is_ip(host):
        return "IP 地址"
    if not host:
        return "未分类"
    if host.startswith("www."):
        return "主站"
    first = host.split(".")[0]
    if first in ("api", "openapi"):
        return "API 服务"
    if first in ("mail", "smtp", "imap", "pop"):
        return "邮件服务"
    if first in ("admin", "manage", "portal", "oa"):
        return "管理平台"
    if first in ("cdn", "static", "img"):
        return "静态资源"
    if host.count(".") <= 1:
        return "根域名"
    return "子域名"


def _cert_extra_hosts(target: WebsiteTarget) -> List[str]:
    hosts = []
    root = str(getattr(target, "cert_root_domain", "") or "").strip()
    if root:
        hosts.append(root)
    for item in str(getattr(target, "cert_subdomains", "") or "").replace(";", ",").split(","):
        host = item.strip()
        if host and host not in hosts:
            hosts.append(host)
    return hosts[:20]


def _statuses_for_export(item: WebsiteTarget) -> str:
    return str(getattr(item, "expected_statuses", "") or "")


@router.get("/targets")
def list_targets(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    monitor_type: Optional[str] = None,
    is_enabled: Optional[bool] = None,
    category: Optional[str] = None,
    search: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    sort_by: str = "sort_order",
    sort_order: str = "asc",
):
    """获取网站监控目标列表，支持分类、时间段、排序和分页。"""
    query = db.query(WebsiteTarget)

    if monitor_type:
        query = query.filter(WebsiteTarget.monitor_type == monitor_type)
    if is_enabled is not None:
        query = query.filter(WebsiteTarget.is_enabled == is_enabled)
    if search:
        query = query.filter(
            or_(
                WebsiteTarget.name.contains(search),
                WebsiteTarget.url.contains(search),
                WebsiteTarget.domain.contains(search),
                WebsiteTarget.ip_address.contains(search),
            )
        )
    start = _parse_time(start_time)
    end = _parse_time(end_time, end=True)
    if start:
        query = query.filter(WebsiteTarget.created_at >= start)
    if end:
        query = query.filter(WebsiteTarget.created_at < end)

    allowed_sort = {
        "name": WebsiteTarget.name,
        "url": WebsiteTarget.url,
        "category": WebsiteTarget.category,
        "monitor_type": WebsiteTarget.monitor_type,
        "expected_status": WebsiteTarget.expected_status,
        "created_at": WebsiteTarget.created_at,
        "updated_at": WebsiteTarget.updated_at,
        "sort_order": WebsiteTarget.sort_order,
    }
    sort_column = allowed_sort.get(sort_by, WebsiteTarget.sort_order)
    order = sort_column.desc() if str(sort_order).lower() == "desc" else sort_column.asc()
    if category:
        # 兼容升级前 category 为空的历史目标：按自动归类结果过滤
        rows = query.order_by(order, WebsiteTarget.id.asc()).all()
        rows = [item for item in rows if (item.category or _auto_category({
            "domain": item.domain,
            "ip_address": item.ip_address,
            "url": item.url,
        })) == category]
        total = len(rows)
        targets = rows[(page - 1) * size: page * size]
    else:
        total = query.count()
        targets = query.order_by(order, WebsiteTarget.id.asc()).offset((page - 1) * size).limit(size).all()

    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [target_to_dict(t, db) for t in targets],
    }


@router.get("/targets/categories")
def list_categories(db: Session = Depends(get_db)):
    rows = db.query(WebsiteTarget).all()
    values = sorted({
        (item.category or _auto_category({
            "domain": item.domain,
            "ip_address": item.ip_address,
            "url": item.url,
        }))
        for item in rows
    })
    return {"items": [value for value in values if value]}


@router.get("/targets/export")
def export_targets(db: Session = Depends(get_db)):
    rows = db.query(WebsiteTarget).order_by(WebsiteTarget.sort_order.asc(), WebsiteTarget.id.asc()).all()
    output = io.StringIO()
    output.write("\ufeff")
    writer = csv.writer(output)
    writer.writerow(EXPORT_COLUMNS)
    for item in rows:
        writer.writerow([
            item.name, item.url, item.monitor_type, item.domain, item.ip_address,
            item.port, item.method, item.expected_status, _statuses_for_export(item),
            item.expected_keywords, item.timeout, item.check_interval,
            item.slow_threshold_ms, item.ignore_https_errors is not False, item.cache_bust_seconds,
            item.expected_statuses, item.cert_monitor_enabled, item.cert_expiry_days,
            item.cert_alert_level, item.cert_root_domain, item.cert_subdomains,
            item.category or _auto_category({"domain": item.domain, "ip_address": item.ip_address, "url": item.url}),
            item.category_mode, item.sort_order, item.is_enabled,
            item.description,
        ])
    filename = f"website-targets-{datetime.now().strftime('%Y%m%d-%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue().encode("utf-8")]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/targets/import")
async def import_targets(
    file: UploadFile = File(...),
    mode: str = Form("skip"),
    db: Session = Depends(get_db),
):
    raw = await file.read()
    if len(raw) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="CSV 文件不能超过 5MB")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("gbk", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise HTTPException(status_code=400, detail="CSV 缺少表头")
    created = updated = skipped = 0
    errors = []
    for index, row in enumerate(reader, start=2):
        try:
            name = str(row.get("name") or "").strip()
            url = str(row.get("url") or "").strip()
            if not name or not url:
                raise ValueError("name 和 url 不能为空")
            data = {
                "name": name,
                "url": url,
                "monitor_type": str(row.get("monitor_type") or "http").strip() or "http",
                "port": int(row["port"]) if str(row.get("port") or "").strip() else None,
                "method": str(row.get("method") or "GET").upper(),
                "expected_status": int(row.get("expected_status") or 200),
                "expected_statuses": str(row.get("expected_statuses") or ""),
                "expected_keywords": str(row.get("expected_keywords") or "") or None,
                "timeout": int(row.get("timeout") or 10),
                "check_interval": int(row.get("check_interval") or 60),
                "slow_threshold_ms": float(row.get("slow_threshold_ms") or 5000),
                "ignore_https_errors": str(row.get("ignore_https_errors") or "true").lower() in ("1", "true", "yes", "on"),
                "cache_bust_seconds": int(row.get("cache_bust_seconds") or 0),
                "cert_monitor_enabled": str(row.get("cert_monitor_enabled") or "true").lower() in ("1", "true", "yes", "on"),
                "cert_expiry_days": int(row.get("cert_expiry_days") or 30),
                "cert_alert_level": str(row.get("cert_alert_level") or "warning"),
                "cert_root_domain": str(row.get("cert_root_domain") or "") or None,
                "cert_subdomains": str(row.get("cert_subdomains") or "") or None,
                "category": str(row.get("category") or ""),
                "category_mode": str(row.get("category_mode") or "auto"),
                "sort_order": int(row.get("sort_order") or 0),
                "is_enabled": str(row.get("is_enabled") or "true").lower() in ("1", "true", "yes", "on"),
                "description": str(row.get("description") or "") or None,
            }
            _validate_target_values(data)
            data = _normalize_target_data(data)
            existing = db.query(WebsiteTarget).filter(WebsiteTarget.url == data["url"]).first()
            if existing:
                if mode != "update":
                    skipped += 1
                    continue
                for key, value in data.items():
                    setattr(existing, key, value)
                existing.updated_at = datetime.utcnow()
                updated += 1
            else:
                item = WebsiteTarget(**data)
                item.created_at = datetime.utcnow()
                item.updated_at = datetime.utcnow()
                db.add(item)
                created += 1
        except Exception as exc:  # noqa: BLE001
            errors.append({"row": index, "message": str(exc)})
    db.commit()
    return {"created": created, "updated": updated, "skipped": skipped, "errors": errors[:50]}


@router.put("/targets/reorder")
def reorder_targets(payload: dict = Body(...), db: Session = Depends(get_db)):
    ids = payload.get("ids") if isinstance(payload, dict) else None
    if not isinstance(ids, list):
        raise HTTPException(status_code=400, detail="ids 必须是数组")
    order_map = {}
    for index, raw_id in enumerate(ids):
        try:
            order_map[int(raw_id)] = index
        except (TypeError, ValueError):
            continue
    if not order_map:
        raise HTTPException(status_code=400, detail="没有有效的目标 ID")
    updated = 0
    for target in db.query(WebsiteTarget).filter(WebsiteTarget.id.in_(order_map.keys())).all():
        target.sort_order = order_map[target.id]
        target.updated_at = datetime.utcnow()
        updated += 1
    db.commit()
    return {"updated": updated}


@router.get("/targets/{target_id}")
def get_target(target_id: int, db: Session = Depends(get_db)):
    """获取网站监控目标详情"""
    target = db.query(WebsiteTarget).filter(WebsiteTarget.id == target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="目标不存在")
    return target_to_dict(target, db)


@router.post("/targets")
def create_target(payload: WebsiteTargetCreate, db: Session = Depends(get_db)):
    """创建网站监控目标"""
    data = payload.model_dump()
    _validate_target_values(data)
    data = _normalize_target_data(data)
    existing = db.query(WebsiteTarget).filter(WebsiteTarget.url == data["url"]).first()
    if existing:
        raise HTTPException(status_code=400, detail="该URL已存在")

    target = WebsiteTarget(**data)
    target.created_at = datetime.utcnow()
    target.updated_at = datetime.utcnow()
    db.add(target)
    db.commit()
    db.refresh(target)
    return target_to_dict(target, db)


@router.put("/targets/{target_id}")
def update_target(target_id: int, payload: WebsiteTargetUpdate, db: Session = Depends(get_db)):
    """更新网站监控目标"""
    target = db.query(WebsiteTarget).filter(WebsiteTarget.id == target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="目标不存在")

    data = payload.model_dump(exclude_unset=True)
    _validate_target_values(data)
    base = {
        "name": target.name,
        "url": target.url,
        "monitor_type": target.monitor_type,
        "domain": target.domain,
        "ip_address": target.ip_address,
        "port": target.port,
        "expected_statuses": target.expected_statuses,
        "cache_bust_seconds": target.cache_bust_seconds,
        "category": target.category,
        "category_mode": target.category_mode,
        "sort_order": target.sort_order,
    }
    base.update(data)
    normalized = _normalize_target_data(base)
    if data.get("category_mode") == "auto" or (target.category_mode or "auto") == "auto":
        data["category"] = normalized.get("category")
    for key in list(data.keys()):
        if key in normalized and key != "category":
            data[key] = normalized[key]
    for key, value in data.items():
        setattr(target, key, value)

    target.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(target)
    return target_to_dict(target, db)


@router.delete("/targets/{target_id}")
def delete_target(target_id: int, db: Session = Depends(get_db)):
    """删除网站监控目标（同时清理历史记录与告警）"""
    target = db.query(WebsiteTarget).filter(WebsiteTarget.id == target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="目标不存在")

    db.query(WebsiteCheckHistory).filter(
        WebsiteCheckHistory.target_id == target_id
    ).delete(synchronize_session=False)
    db.query(WebsiteAlert).filter(
        WebsiteAlert.target_id == target_id
    ).delete(synchronize_session=False)

    db.delete(target)
    db.commit()
    return {"message": "目标已删除"}


@router.put("/targets/{target_id}/toggle")
def toggle_target(target_id: int, db: Session = Depends(get_db)):
    """启用/禁用目标"""
    target = db.query(WebsiteTarget).filter(WebsiteTarget.id == target_id).first()
    if not target:
        raise HTTPException(status_code=404, detail="目标不存在")
    
    target.is_enabled = not target.is_enabled
    target.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(target)
    return target_to_dict(target, db)


# ==================== 检查历史 ====================

@router.get("/targets/{target_id}/history")
def get_check_history(
    target_id: int,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
):
    """获取检查历史（支持时间段查询）"""
    query = db.query(WebsiteCheckHistory).filter(
        WebsiteCheckHistory.target_id == target_id
    )
    start = _parse_time(start_time)
    end = _parse_time(end_time, end=True)
    if start:
        query = query.filter(WebsiteCheckHistory.checked_at >= start)
    if end:
        query = query.filter(WebsiteCheckHistory.checked_at < end)
    query = query.order_by(WebsiteCheckHistory.checked_at.desc())
    
    total = query.count()
    records = query.offset((page - 1) * size).limit(size).all()
    
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [record_to_dict(r) for r in records]
    }


@router.get("/targets/{target_id}/stats")
def get_target_stats(target_id: int, hours: int = Query(24, ge=1), db: Session = Depends(get_db)):
    """获取目标统计"""
    cutoff = datetime.utcnow() - timedelta(hours=hours)
    
    records = db.query(WebsiteCheckHistory).filter(
        and_(
            WebsiteCheckHistory.target_id == target_id,
            WebsiteCheckHistory.checked_at >= cutoff
        )
    ).all()
    
    if not records:
        return {
            "total_checks": 0,
            "alive_count": 0,
            "down_count": 0,
            "uptime_percent": 0,
            "avg_response_time": 0,
            "min_response_time": 0,
            "max_response_time": 0,
            "target": target_id,
            "hours": hours,
        }
    
    alive_count = sum(1 for r in records if r.is_alive)
    down_count = len(records) - alive_count
    uptimes = [r.response_time for r in records if r.response_time > 0]
    
    return {
        "total_checks": len(records),
        "alive_count": alive_count,
        "down_count": down_count,
        "uptime_percent": round(alive_count / len(records) * 100, 2),
        "avg_response_time": round(sum(uptimes) / len(uptimes), 2) if uptimes else 0,
        "min_response_time": round(min(uptimes), 2) if uptimes else 0,
        "max_response_time": round(max(uptimes), 2) if uptimes else 0,
        "target": target_id,
        "hours": hours,
    }


# ==================== 告警 ====================

@router.get("/targets/{target_id}/alerts")
def get_target_alerts(
    target_id: int,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
):
    """获取目标告警"""
    query = db.query(WebsiteAlert).filter(
        WebsiteAlert.target_id == target_id
    ).order_by(WebsiteAlert.created_at.desc())
    
    total = query.count()
    alerts = query.offset((page - 1) * size).limit(size).all()
    
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [alert_to_dict(a) for a in alerts]
    }


@router.post("/alerts/{alert_id}/ack")
def acknowledge_website_alert(alert_id: int, db: Session = Depends(get_db)):
    """确认告警"""
    alert = db.query(WebsiteAlert).filter(WebsiteAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="告警不存在")
    
    alert.is_acknowledged = True
    db.commit()
    return {"message": "告警已确认"}


# ==================== 工具函数 ====================

def _validate_target_values(data: dict) -> None:
    allowed_levels = {"info", "warning", "critical", "emergency"}
    if "down_level" in data and data.get("down_level") not in allowed_levels:
        raise HTTPException(status_code=400, detail="检测失败告警级别不合法")
    if "slow_level" in data and data.get("slow_level") not in allowed_levels:
        raise HTTPException(status_code=400, detail="响应缓慢告警级别不合法")
    if "slow_threshold_ms" in data:
        try:
            threshold = float(data["slow_threshold_ms"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="慢响应阈值必须是数字") from None
        if not 100 <= threshold <= 600000:
            raise HTTPException(status_code=400, detail="慢响应阈值必须在 100~600000 毫秒之间")
        data["slow_threshold_ms"] = threshold
    if "cert_expiry_days" in data and data.get("cert_expiry_days") is not None:
        try:
            cert_days = int(data["cert_expiry_days"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="证书到期告警天数必须是整数") from None
        if not 1 <= cert_days <= 3650:
            raise HTTPException(status_code=400, detail="证书到期告警天数必须在 1~3650 天之间")
        data["cert_expiry_days"] = cert_days
    if "cert_alert_level" in data and data.get("cert_alert_level") not in allowed_levels:
        raise HTTPException(status_code=400, detail="证书到期告警级别不合法")
    if "monitor_type" in data and str(data.get("monitor_type") or "").lower() not in ("http", "https", "tcp", "ping"):
        raise HTTPException(status_code=400, detail="监控类型不合法")
    if "category_mode" in data and data.get("category_mode") not in ("auto", "manual"):
        raise HTTPException(status_code=400, detail="归类方式只支持 auto 或 manual")
    if "cache_bust_seconds" in data and data.get("cache_bust_seconds") is not None:
        try:
            cache_seconds = int(data["cache_bust_seconds"])
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="缓存更换间隔必须是整数") from None
        if not 0 <= cache_seconds <= 86400:
            raise HTTPException(status_code=400, detail="缓存更换间隔必须在 0~86400 秒之间")
        data["cache_bust_seconds"] = cache_seconds
    if "expected_statuses" in data and data.get("expected_statuses"):
        spec = str(data["expected_statuses"]).replace("，", ",")
        for token in spec.split(","):
            token = token.strip()
            if not token:
                continue
            parts = token.split("-", 1)
            try:
                values = [int(part.strip()) for part in parts if part.strip()]
            except ValueError:
                raise HTTPException(status_code=400, detail="允许状态码格式不合法，例如 200,301-399") from None
            if not values or not all(100 <= value <= 599 for value in values):
                raise HTTPException(status_code=400, detail="允许状态码格式不合法，例如 200,301-399")


def target_to_dict(target: WebsiteTarget, db: Session = None) -> dict:
    """目标转字典"""
    latest_record = None
    recent_checks = []
    if db:
        latest_record = db.query(WebsiteCheckHistory).filter(
            WebsiteCheckHistory.target_id == target.id
        ).order_by(WebsiteCheckHistory.checked_at.desc()).first()
        recent = db.query(WebsiteCheckHistory).filter(
            WebsiteCheckHistory.target_id == target.id
        ).order_by(WebsiteCheckHistory.checked_at.desc()).limit(24).all()
        recent_checks = [
            {
                "is_alive": bool(record.is_alive),
                "response_time": round(float(record.response_time or 0), 2),
                "checked_at": record.checked_at.isoformat() if record.checked_at else None,
            }
            for record in reversed(recent)
        ]
    
    unack_alerts = 0
    if db:
        unack_alerts = db.query(WebsiteAlert).filter(
            WebsiteAlert.target_id == target.id,
            WebsiteAlert.is_acknowledged == False
        ).count()
    
    return {
        "id": target.id,
        "name": target.name,
        "url": target.url,
        "domain": target.domain,
        "ip_address": target.ip_address,
        "monitor_type": target.monitor_type,
        "port": target.port,
        "method": target.method,
        "expected_status": target.expected_status,
        "expected_statuses": target.expected_statuses or "",
        "expected_keywords": target.expected_keywords,
        "timeout": target.timeout,
        "check_interval": target.check_interval,
        "ignore_https_errors": target.ignore_https_errors is not False,
        "cache_bust_seconds": target.cache_bust_seconds or 0,
        "category": target.category or _auto_category({
            "domain": target.domain,
            "ip_address": target.ip_address,
            "url": target.url,
        }),
        "category_mode": target.category_mode or "auto",
        "sort_order": target.sort_order or 0,
        "cert_root_domain": target.cert_root_domain or "",
        "cert_subdomains": target.cert_subdomains or "",
        "slow_threshold_ms": target.slow_threshold_ms or 5000,
        "cert_monitor_enabled": target.cert_monitor_enabled if target.cert_monitor_enabled is not None else True,
        "cert_expiry_days": target.cert_expiry_days if target.cert_expiry_days is not None else 30,
        "cert_alert_level": target.cert_alert_level or "warning",
        "down_level": target.down_level or "critical",
        "slow_level": target.slow_level or "warning",
        "down_level_label": target.down_level_label or "",
        "slow_level_label": target.slow_level_label or "",
        "is_enabled": target.is_enabled,
        "notify_email": target.notify_email,
        "notify_webhook": target.notify_webhook,
        "description": target.description,
        "created_at": target.created_at.isoformat() if target.created_at else None,
        "updated_at": target.updated_at.isoformat() if target.updated_at else None,
        "latest_status": {
            "is_alive": latest_record.is_alive if latest_record else None,
            "status_code": latest_record.status_code if latest_record else None,
            "response_time": latest_record.response_time if latest_record else None,
            "checked_at": latest_record.checked_at.isoformat() if latest_record and latest_record.checked_at else None,
            "cert_info": latest_record.cert_info if latest_record else None,
        } if latest_record else None,
        "recent_checks": recent_checks,
        "unack_alerts": unack_alerts,
    }


def record_to_dict(record: WebsiteCheckHistory) -> dict:
    """检查记录转字典"""
    return {
        "id": record.id,
        "target_id": record.target_id,
        "status_code": record.status_code,
        "response_time": record.response_time,
        "is_alive": record.is_alive,
        "http_error": record.http_error,
        "dns_resolve_time": record.dns_resolve_time,
        "tcp_connect_time": record.tcp_connect_time,
        "ssl_time": record.ssl_time,
        "cert_info": record.cert_info,
        "final_ip": record.final_ip,
        "content_length": record.content_length,
        "check_type": record.check_type,
        "error_message": record.error_message,
        "checked_at": record.checked_at.isoformat() if record.checked_at else None,
    }


def alert_to_dict(alert: WebsiteAlert) -> dict:
    """告警转字典"""
    return {
        "id": alert.id,
        "target_id": alert.target_id,
        "alert_type": alert.alert_type,
        "alert_level": alert.alert_level,
        "level_label": alert.level_label or "",
        "message": alert.message,
        "details": alert.details,
        "is_acknowledged": alert.is_acknowledged,
        "resolved_at": alert.resolved_at.isoformat() if alert.resolved_at else None,
        "resolution": alert.resolution,
        "is_resolved": bool(alert.resolved_at),
        "created_at": alert.created_at.isoformat() if alert.created_at else None,
    }
