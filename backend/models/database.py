"""数据库配置与初始化

支持 SQLite（默认，零依赖）、MySQL、PostgreSQL，通过 DATABASE_URL 切换：
  sqlite:///snmp_monitor.db
  mysql+pymysql://user:pass@host:3306/snmp_nms?charset=utf8mb4
  postgresql+psycopg2://user:pass@host:5432/snmp_nms
"""
import logging
import os

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import sessionmaker, declarative_base

from ..config import Config

logger = logging.getLogger(__name__)

_URL = Config.DATABASE_URL
_IS_SQLITE = _URL.startswith("sqlite")
_IS_MYSQL = _URL.startswith("mysql")
_IS_POSTGRES = _URL.startswith(("postgresql", "postgres"))

_engine_kwargs = {"pool_pre_ping": True}
_SQLITE_BUSY_TIMEOUT_MS = max(1000, int(os.getenv("SQLITE_BUSY_TIMEOUT_MS", "30000")))
if _IS_SQLITE:
    # Python sqlite3 默认 5 秒；采集写入较多时登录/审计容易报 database is locked
    _engine_kwargs["connect_args"] = {
        "check_same_thread": False,
        "timeout": _SQLITE_BUSY_TIMEOUT_MS / 1000,
    }
else:
    # MySQL / PostgreSQL 连接池：设备量大时可调大 DB_POOL_SIZE / DB_MAX_OVERFLOW
    _engine_kwargs.update(
        pool_size=Config.DB_POOL_SIZE,
        max_overflow=Config.DB_MAX_OVERFLOW,
        pool_recycle=Config.DB_POOL_RECYCLE,
        pool_timeout=30,
    )
    if _IS_MYSQL:
        _engine_kwargs["connect_args"] = {"charset": "utf8mb4"}

engine = create_engine(_URL, **_engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


if _IS_SQLITE:
    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _connection_record):
        """SQLite 稳定性设置：WAL 提升并发、busy_timeout 避免锁冲突直接报错"""
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute(f"PRAGMA busy_timeout={_SQLITE_BUSY_TIMEOUT_MS}")
            cursor.execute("PRAGMA wal_autocheckpoint=1000")
            cursor.execute("PRAGMA foreign_keys=ON")
        except Exception as exc:  # noqa: BLE001
            logger.debug("设置 SQLite PRAGMA 失败: %s", exc)
        finally:
            cursor.close()

# 导入所有模型确保它们被注册到 Base
# 注：若某个模型模块先于本模块被导入（如直接 import backend.models.models），
# 这里可能遇到「部分初始化」的循环导入，忽略即可（应用入口始终先导入本模块）。
try:  # noqa: SIM105
    from .models import Device, DeviceInterface, DeviceMetric, DeviceConnection, Alert  # noqa: E402,F401
    from .room import Room, Cabinet, CabinetAccessLog, RoomSensor, RoomSensorReading  # noqa: E402,F401
    from .maintenance import DeviceMaintenance  # noqa: E402,F401
    from .user import User, Role, Group, user_roles, user_groups  # noqa: E402,F401
    from .website import WebsiteTarget, WebsiteCheckHistory, WebsiteAlert  # noqa: E402,F401
    from .discovery import DiscoverySchedule  # noqa: E402,F401
    from .notifications import NotificationChannel, NotificationLog  # noqa: E402,F401
    from .upstream import UpstreamReceivedAlert  # noqa: E402,F401
    from .ai_report import AiOpsReport  # noqa: E402,F401
    from .mib_auto import MibMatchProfile  # noqa: E402,F401
    from .cascade import CascadeNode, CascadeMessage  # noqa: E402,F401
    from .mib import MibFile, MibObject  # noqa: E402,F401
    from .settings import SystemSetting  # noqa: E402,F401
    from .audit import AuditLog, LoginAttempt  # noqa: E402,F401
    from .capture import CaptureRecord  # noqa: E402,F401
    from .cluster import ClusterNode  # noqa: E402,F401
    from .config_backup import ConfigBackup  # noqa: E402,F401
    from .im import ChatMessage, ChatAttachment, ImPreference  # noqa: E402,F401
    from .certificate import ManagedCertificate  # noqa: E402,F401
    from .sharing import SharedResource, SharedResourceMember, SharedEditRequest  # noqa: E402,F401
    from .inspection import InspectionTask, InspectionReport  # noqa: E402,F401
    from .virtualization import (  # noqa: E402,F401
        VirtualPlatform, VirtualHost, VirtualMachine, VirtualizationAlert,
    )
except ImportError:  # pragma: no cover
    pass


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _add_missing_columns() -> None:
    """轻量迁移：为已存在的表补齐新增列（ADD COLUMN）

    兼容 SQLite / MySQL / PostgreSQL：只做「加列」，不做改类型/删列；
    复杂结构变更建议使用数据库迁移工具（Alembic）或新建库后迁移数据。
    """
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    quote = "`" if _IS_MYSQL else '"'

    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if table.name not in existing_tables:
                continue
            db_cols = {c["name"] for c in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in db_cols:
                    continue
                col_type = column.type.compile(engine.dialect)
                sql = (
                    f"ALTER TABLE {quote}{table.name}{quote} "
                    f"ADD COLUMN {quote}{column.name}{quote} {col_type}"
                )
                try:
                    conn.execute(text(sql))
                    logger.info("数据库迁移: %s 新增列 %s", table.name, column.name)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("迁移列失败 %s.%s: %s", table.name, column.name, exc)


def init_db():
    """初始化数据库表（并补齐新增列）"""
    Base.metadata.create_all(bind=engine)
    try:
        _add_missing_columns()
    except Exception as exc:  # noqa: BLE001
        logger.warning("数据库列检查失败（可忽略）: %s", exc)
