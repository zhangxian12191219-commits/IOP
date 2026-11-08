"""安全策略：登录失败锁定、IP 白名单、来源 IP 解析"""
import ipaddress
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from ..models.audit import LoginAttempt
from . import settings as settings_service

logger = logging.getLogger(__name__)

# 安全相关配置项
SECURITY_KEYS = (
    "login_lock_enabled",
    "login_max_attempts",
    "login_lock_minutes",
    "ip_whitelist_enabled",
    "ip_whitelist",
    "trust_proxy",
)

# 安全配置短缓存，避免每个请求都查库（多进程下各自缓存 5 秒可接受）
_CACHE: Dict[str, Any] = {"ts": 0.0, "data": None}
_CACHE_SECONDS = 5.0


def get_security_config(db: Session) -> Dict[str, Any]:
    now = time.time()
    if _CACHE["data"] is not None and now - _CACHE["ts"] < _CACHE_SECONDS:
        return _CACHE["data"]
    all_settings = settings_service.get_all(db)
    data = {key: all_settings.get(key) for key in SECURITY_KEYS}
    _CACHE["data"] = data
    _CACHE["ts"] = now
    return data


def invalidate_security_cache() -> None:
    _CACHE["data"] = None
    _CACHE["ts"] = 0.0


def client_ip(request, trust_proxy: bool = False) -> str:
    """获取真实客户端 IP；trust_proxy 时取 X-Forwarded-For 第一个地址"""
    if request is None:
        return ""
    if trust_proxy:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            return forwarded.split(",")[0].strip()[:64]
        real_ip = request.headers.get("x-real-ip")
        if real_ip:
            return real_ip.strip()[:64]
    client = getattr(request, "client", None)
    return (getattr(client, "host", "") or "")[:64]


def parse_whitelist(text: str) -> List[ipaddress._BaseNetwork]:
    """解析白名单（逗号/换行/空格分隔，支持单 IP 与 CIDR、IPv4/IPv6）"""
    networks: List[ipaddress._BaseNetwork] = []
    for raw in (text or "").replace(",", "\n").replace(";", "\n").split():
        item = raw.strip()
        if not item:
            continue
        try:
            networks.append(ipaddress.ip_network(item, strict=False))
        except ValueError:
            continue
    return networks


def validate_whitelist(text: str) -> Tuple[bool, str]:
    """校验白名单格式，返回 (是否合法, 错误信息)"""
    entries = (text or "").replace(",", "\n").replace(";", "\n").split()
    for raw in entries:
        item = raw.strip()
        if not item:
            continue
        try:
            ipaddress.ip_network(item, strict=False)
        except ValueError:
            return False, f"IP 白名单格式不正确：{item}（支持 1.2.3.4、10.0.0.0/8、IPv6）"
    return True, ""


def ip_allowed(ip: str, text: str) -> bool:
    if not ip:
        return False
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for network in parse_whitelist(text):
        if addr in network:
            return True
    return False


def get_lock(db: Session, username: str) -> Optional[Dict[str, Any]]:
    """查询用户名是否处于锁定状态；未锁定返回 None"""
    row = (
        db.query(LoginAttempt)
        .filter(LoginAttempt.username == username)
        .first()
    )
    if not row or not row.locked_until:
        return None
    if row.locked_until <= datetime.utcnow():
        # 锁定已到期，清除锁定（保留计数由下次成功登录重置）
        row.locked_until = None
        row.fail_count = 0
        db.commit()
        return None
    seconds = int((row.locked_until - datetime.utcnow()).total_seconds())
    return {
        "locked_until": row.locked_until,
        "seconds_left": max(1, seconds),
        "fail_count": row.fail_count,
    }


def register_failure(
    db: Session, username: str, ip: str, max_attempts: int, lock_minutes: int
) -> Dict[str, Any]:
    """记录一次登录失败；达到阈值时锁定账号"""
    now = datetime.utcnow()
    row = db.query(LoginAttempt).filter(LoginAttempt.username == username).first()
    if not row:
        row = LoginAttempt(username=username, fail_count=0)
        db.add(row)
        db.flush()
    row.fail_count = (row.fail_count or 0) + 1
    row.ip = ip[:64]
    row.last_failed_at = now
    locked_until = None
    if max_attempts > 0 and row.fail_count >= max_attempts:
        locked_until = now + timedelta(minutes=max(1, lock_minutes))
        row.locked_until = locked_until
    row.updated_at = now
    db.commit()
    return {
        "fail_count": row.fail_count,
        "locked_until": locked_until,
        "remaining_attempts": max(0, max_attempts - row.fail_count),
    }


def clear_failures(db: Session, username: str) -> None:
    """登录成功后清除失败计数与锁定；SQLite 写锁短暂冲突时重试。"""
    for attempt in range(3):
        try:
            db.query(LoginAttempt).filter(LoginAttempt.username == username).delete(
                synchronize_session=False
            )
            db.commit()
            return
        except OperationalError as exc:
            db.rollback()
            if "locked" not in str(exc).lower() or attempt >= 2:
                raise
            time.sleep(0.3 * (attempt + 1))


def lock_message(seconds_left: int) -> str:
    minutes = max(1, (seconds_left + 59) // 60)
    return f"登录失败次数过多，账号已临时锁定，请约 {minutes} 分钟后重试"
