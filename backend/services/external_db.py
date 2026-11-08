"""外部数据库连接测试（与系统一致支持 SQLite / MySQL / PostgreSQL）"""
import time
from pathlib import Path
from typing import Any, Dict
from urllib.parse import quote, quote_plus

from sqlalchemy import create_engine, text


def _build_url(values: Dict[str, Any]) -> str:
    db_type = str(values.get("integration_db_type") or "mysql").lower()
    timeout = max(1, min(60, int(values.get("integration_timeout") or 10)))

    if db_type == "sqlite":
        raw = str(values.get("integration_sqlite_path") or "").strip()
        if not raw:
            raise ValueError("请填写 SQLite 数据库文件路径")
        if raw.startswith("sqlite://"):
            return raw
        if raw == ":memory:":
            return "sqlite:///:memory:"
        path = Path(raw).expanduser()
        if not path.exists():
            raise ValueError("SQLite 数据库文件不存在")
        if not path.is_file():
            raise ValueError("SQLite 路径不是文件")
        return "sqlite:///" + str(path.resolve()).replace("\\", "/")

    host = str(values.get("integration_host") or "").strip()
    database = str(values.get("integration_database") or "").strip()
    username = str(values.get("integration_username") or "").strip()
    password = str(values.get("integration_password") or "")
    if not host:
        raise ValueError("请填写数据库主机")
    if not database:
        raise ValueError("请填写数据库名称")
    port = int(values.get("integration_port") or (3306 if db_type == "mysql" else 5432))
    userinfo = quote_plus(username)
    if password:
        userinfo += ":" + quote_plus(password)
    db_name = quote(database, safe="")

    if db_type == "mysql":
        charset = str(values.get("integration_charset") or "utf8mb4").strip() or "utf8mb4"
        return (
            f"mysql+pymysql://{userinfo}@{host}:{port}/{db_name}"
            f"?charset={charset}&connect_timeout={timeout}"
        )
    if db_type == "postgresql":
        return (
            f"postgresql+psycopg2://{userinfo}@{host}:{port}/{db_name}"
            f"?connect_timeout={timeout}"
        )
    raise ValueError("数据库类型仅支持 SQLite / MySQL / PostgreSQL")


def test_connection(values: Dict[str, Any]) -> Dict[str, Any]:
    """建立真实连接并执行 SELECT 1，返回可展示的连接结果。"""
    started = time.perf_counter()
    password = str(values.get("integration_password") or "")
    engine = None
    try:
        url = _build_url(values)
        timeout = max(1, min(60, int(values.get("integration_timeout") or 10)))
        db_type = str(values.get("integration_db_type") or "mysql").lower()
        connect_args: Dict[str, Any] = {"timeout": timeout} if db_type == "sqlite" else {}
        engine = create_engine(
            url,
            pool_pre_ping=True,
            pool_timeout=timeout,
            connect_args=connect_args,
        )
        with engine.connect() as conn:
            if db_type == "sqlite":
                version = conn.execute(text("SELECT sqlite_version()")).scalar()
                table_count = conn.execute(
                    text("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
                ).scalar()
            elif db_type == "mysql":
                version = conn.execute(text("SELECT VERSION()")).scalar()
                table_count = None
            else:
                version = conn.execute(text("SELECT version()")).scalar()
                table_count = None
        elapsed = (time.perf_counter() - started) * 1000
        result: Dict[str, Any] = {
            "ok": True,
            "db_type": db_type,
            "latency_ms": round(elapsed, 1),
            "server_version": str(version or "")[:120],
        }
        if table_count is not None:
            result["table_count"] = int(table_count)
        return result
    except ValueError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    except Exception as exc:  # noqa: BLE001
        message = str(exc) or exc.__class__.__name__
        if password:
            message = message.replace(password, "******")
        return {
            "ok": False,
            "error": message[:500],
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
        }
    finally:
        if engine is not None:
            try:
                engine.dispose()
            except Exception:  # noqa: BLE001
                pass
