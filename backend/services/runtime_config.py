"""运行环境中的实际数据库与缓存配置快照。

系统配置页的“对接与缓存”需要同时展示：
- 页面里保存的外部数据库 / Redis 参数；
- 进程实际使用的 DATABASE_URL、REDIS_URL；
- 实际连通性（是否已连接、延迟、服务端版本、错误原因），便于确认在线/离线安装的
  PostgreSQL / Redis 是否真正对接成功。

本模块只做解析和只读探测，不修改连接，不返回数据库密码明文。
"""
from __future__ import annotations

import os
import time
from datetime import datetime
from typing import Any, Dict, Optional
from urllib.parse import quote, urlsplit, urlunsplit

from sqlalchemy.engine import make_url

from ..config import Config
from .cache import cache

# 只读探测连接的超时时间（秒），避免系统配置页因数据库/缓存异常被长时间阻塞
PROBE_TIMEOUT_SECONDS = 3


def _driver_ready(backend: str) -> Optional[bool]:
    """检查运行库所需的 Python 驱动是否可导入（psycopg2 / pymysql）。

    返回 None 表示该类型无需额外驱动或不适用。
    """
    module = {
        "postgresql": "psycopg2",
        "mysql": "pymysql",
        "mariadb": "pymysql",
    }.get((backend or "").lower())
    if not module:
        return None
    try:
        __import__(module)
        return True
    except Exception:  # noqa: BLE001
        return False


def _now_text() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _database_probe(db=None) -> Dict[str, Any]:
    """只读探测当前数据库连通性（复用请求会话，避免额外建连）。"""
    started = time.perf_counter()
    session = db
    own_session = False
    try:
        from sqlalchemy import text

        if session is None:
            from ..models.database import SessionLocal

            session = SessionLocal()
            own_session = True
        session.execute(text("SELECT 1"))
        version = None
        try:
            bind = session.get_bind()
            dialect = str(getattr(getattr(bind, "dialect", None), "name", "") or "")
            version_sql = "SELECT sqlite_version()" if dialect == "sqlite" else "SELECT version()"
            row = session.execute(text(version_sql)).first()
            if row and row[0]:
                version = str(row[0]).split(",")[0][:120]
        except Exception:  # noqa: BLE001 - 部分数据库/只读账号不允许查询 version()
            version = None
            try:
                session.rollback()
            except Exception:  # noqa: BLE001
                pass
        return {
            "connected": True,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "server_version": version,
            "error": "",
            "checked_at": _now_text(),
        }
    except Exception as exc:  # noqa: BLE001
        # 探测失败时清理会话事务状态，避免影响同一请求内后续查询
        try:
            if session is not None:
                session.rollback()
        except Exception:  # noqa: BLE001
            pass
        return {
            "connected": False,
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "server_version": None,
            "error": str(exc)[:240],
            "checked_at": _now_text(),
        }
    finally:
        if own_session and session is not None:
            try:
                session.close()
            except Exception:  # noqa: BLE001
                pass


def _cache_probe() -> Dict[str, Any]:
    """只读探测 Redis 连通性；未配置 Redis 时不发起网络连接。"""
    result: Dict[str, Any] = {
        "connected": False,
        "latency_ms": None,
        "redis_version": None,
        "clients": None,
        "error": "",
        "checked_at": _now_text(),
    }
    url = str(getattr(cache, "redis_url", "") or "").strip()
    if not url:
        result["error"] = "未配置 Redis，使用进程内缓存"
        return result

    started = time.perf_counter()
    try:
        probe = cache.test_connection()
    except Exception as exc:  # noqa: BLE001
        result["latency_ms"] = round((time.perf_counter() - started) * 1000, 1)
        result["error"] = str(exc)[:240]
        return result

    result["latency_ms"] = probe.get("latency_ms") or round(
        (time.perf_counter() - started) * 1000, 1
    )
    result["connected"] = bool(probe.get("ok"))
    result["redis_version"] = probe.get("version")
    result["clients"] = probe.get("clients")
    if not result["connected"]:
        result["error"] = str(probe.get("error") or "")[:240]
    return result


def _mask_secret_url(raw: str) -> str:
    """隐藏 URL 中的密码，保留协议、主机、端口、库名。"""
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
        host = parts.hostname or ""
        port = parts.port
        netloc = host
        if port:
            netloc += f":{port}"
        if parts.username:
            user = quote(parts.username, safe="")
            netloc = f"{user}@{netloc}"
        if parts.password:
            # 已经有用户名时替换密码；没有用户名时也明确标识已配置密码
            if "@" in netloc:
                user_part, host_part = netloc.split("@", 1)
                netloc = f"{user_part}:******@{host_part}"
            else:
                netloc = f"******@{netloc}"
        return urlunsplit((parts.scheme, netloc, parts.path, "", ""))
    except Exception:  # noqa: BLE001
        return "已配置"


def _database_snapshot() -> Dict[str, Any]:
    raw = str(Config.DATABASE_URL or "").strip()
    source = "environment" if os.getenv("DATABASE_URL") else "default"
    result: Dict[str, Any] = {
        "source": source,
        "url_masked": "",
        "type": "sqlite",
        "type_label": "SQLite",
        "driver": "",
        "host": "",
        "port": None,
        "database": "",
        "sqlite_path": "",
        "username": "",
        "password_set": False,
        "display": "SQLite",
        "auto_fill": False,
        "auto_filled": False,
        "driver_ready": None,
    }
    if not raw:
        return result

    try:
        url = make_url(raw)
    except Exception:  # noqa: BLE001
        result["display"] = "已配置（无法解析 URL）"
        result["url_masked"] = "已配置"
        return result

    backend = (url.get_backend_name() or "").lower()
    result["type"] = backend or "unknown"
    result["driver"] = url.get_driver_name() or ""
    if backend == "sqlite":
        path = str(url.database or "")
        result["sqlite_path"] = path
        result["database"] = path
        result["display"] = f"SQLite · {path or '默认数据库'}"
        result["url_masked"] = _mask_secret_url(raw)
        return result

    port = url.port or {"mysql": 3306, "mariadb": 3306, "postgresql": 5432}.get(backend)
    database = str(url.database or "")
    host = str(url.host or "")
    username = str(url.username or "")
    type_label = {
        "postgresql": "PostgreSQL",
        "mysql": "MySQL",
        "mariadb": "MariaDB",
    }.get(backend, backend or "数据库")
    result.update({
        "type": backend or "unknown",
        "type_label": type_label,
        "host": host,
        "port": port,
        "database": database,
        "username": username,
        "password_set": bool(url.password),
        "display": f"{type_label} · {host}:{port}/{database}".rstrip("/"),
        "url_masked": _mask_secret_url(raw),
        "driver_ready": _driver_ready(backend),
    })
    return result


def _cache_snapshot(settings: Dict[str, Any]) -> Dict[str, Any]:
    raw = str(getattr(cache, "redis_url", "") or "").strip()
    settings_url = str(settings.get("redis_url") or "").strip()
    env_url = str(Config.REDIS_URL or "").strip()
    if env_url and (not settings_url or settings_url == env_url):
        source = "environment"
    elif settings_url:
        source = "settings"
    elif env_url:
        source = "environment"
    else:
        source = "memory"

    backend = "memory"
    try:
        backend = str(cache.info().get("backend") or "memory")
    except Exception:  # noqa: BLE001
        pass

    result: Dict[str, Any] = {
        "source": source,
        "backend": backend,
        "enabled": bool(getattr(cache, "enabled", False)),
        "url_masked": "",
        "host": "",
        "port": None,
        "database": "",
        "password_set": False,
        "display": "进程内缓存（未配置 Redis）",
    }
    if not raw:
        return result

    try:
        parts = urlsplit(raw)
        host = parts.hostname or ""
        port = parts.port or 6379
        db = (parts.path or "/0").lstrip("/") or "0"
        result.update({
            "host": host,
            "port": port,
            "database": db,
            "password_set": bool(parts.password),
            "url_masked": _mask_secret_url(raw),
            "display": f"Redis · {host}:{port}/{db}",
        })
    except Exception:  # noqa: BLE001
        result["display"] = "Redis（地址已配置）"
        result["url_masked"] = "已配置"
    return result


def snapshot(settings: Dict[str, Any], db=None) -> Dict[str, Any]:
    """返回系统配置页展示用的运行时配置快照（含实际连通性）。

    db 为当前请求的数据库会话时复用连接探测；为空时仅探测缓存。
    """
    database = _database_snapshot()
    if db is not None:
        database.update(_database_probe(db))
    cache_info = _cache_snapshot(settings)
    cache_info.update(_cache_probe())
    return {
        "database": database,
        "cache": cache_info,
    }


def integration_defaults(database: Dict[str, Any]) -> Dict[str, Any]:
    """把实际运行数据库转换为“外部数据库对接”表单可用的初始值。

    不包含密码：密码仍在环境变量中，页面只提示已配置，避免把运行库密码
    回显到浏览器。
    """
    db_type = str(database.get("type") or "")
    if db_type not in ("mysql", "mariadb", "postgresql", "sqlite"):
        return {}
    if db_type == "mariadb":
        db_type = "mysql"
    defaults: Dict[str, Any] = {
        "integration_db_type": db_type,
        "integration_timeout": 10,
    }
    if db_type == "sqlite":
        defaults["integration_sqlite_path"] = database.get("sqlite_path") or ""
        return defaults
    defaults.update({
        "integration_host": database.get("host") or "",
        "integration_port": database.get("port") or (5432 if db_type == "postgresql" else 3306),
        "integration_database": database.get("database") or "",
        "integration_username": database.get("username") or "",
        "integration_charset": "utf8mb4",
    })
    return defaults
