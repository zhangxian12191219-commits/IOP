"""即时通信表结构轻量迁移。

历史版本的 ``chat_messages.recipient_id`` 为 NOT NULL，群聊消息没有单一接收人，
需要把该列放宽为可空并补充 ``group_id``。项目没有引入 Alembic，这里做一次
幂等的启动期迁移：

- SQLite：重建表（SQLite 不支持 ALTER COLUMN），保留全部历史数据并重建索引；
- MySQL / PostgreSQL：直接修改列可空性并补列、补索引。

迁移失败只记录日志，不阻断应用启动；接口层会再次校验，最坏情况下群聊写入
会失败并返回明确错误。
"""
from __future__ import annotations

import logging
from typing import Dict

from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateIndex, CreateTable

from ..models.database import engine
from ..models.im import ChatGroup, ChatGroupMember, ChatMessage

logger = logging.getLogger(__name__)

_TABLE = "chat_messages"
_TMP_TABLE = "chat_messages__im_rebuild"
_IS_SQLITE = engine.dialect.name == "sqlite"
_QUOTE = "`" if engine.dialect.name in ("mysql", "mariadb") else '"'


def _column_info() -> Dict[str, dict]:
    """返回列名 -> PRAGMA / inspector 信息（含 notnull / nullable 标记）。"""
    if _IS_SQLITE:
        with engine.connect() as conn:
            rows = conn.execute(text(f"PRAGMA table_info({_QUOTE}{_TABLE}{_QUOTE})")).fetchall()
        return {
            str(row[1]): {
                "name": str(row[1]),
                "nullable": not bool(row[3]),
                "type": row[2],
            }
            for row in rows
        }
    inspector = inspect(engine)
    return {
        column["name"]: {
            "name": column["name"],
            "nullable": bool(column.get("nullable", True)),
            "type": str(column.get("type")),
        }
        for column in inspector.get_columns(_TABLE)
    }


def _table_exists(name: str) -> bool:
    try:
        return name in inspect(engine).get_table_names()
    except Exception:  # noqa: BLE001
        return False


def _ensure_group_tables() -> None:
    """先建好群组父表，保证外键可解析；已存在则跳过。"""
    ChatGroup.__table__.create(bind=engine, checkfirst=True)
    ChatGroupMember.__table__.create(bind=engine, checkfirst=True)


def _rebuild_sqlite_table() -> None:
    """SQLite 重建 chat_messages：recipient_id 可空 + group_id 列，保留数据与索引。"""
    ddl = str(CreateTable(ChatMessage.__table__).compile(engine))
    if "CREATE TABLE" not in ddl:
        raise RuntimeError("无法生成 chat_messages 的建表语句")
    ddl = ddl.replace("CREATE TABLE chat_messages", f"CREATE TABLE {_TMP_TABLE}", 1)

    target_columns = [column.name for column in ChatMessage.__table__.columns]
    old_columns = _column_info()
    common_columns = [name for name in target_columns if name in old_columns]

    def quote(name: str) -> str:
        return f'{_QUOTE}{name}{_QUOTE}'

    columns_sql = ", ".join(quote(name) for name in common_columns)
    with engine.begin() as conn:
        conn.execute(text(f"DROP TABLE IF EXISTS {_QUOTE}{_TMP_TABLE}{_QUOTE}"))
        conn.execute(text(ddl))
        conn.execute(
            text(
                f"INSERT INTO {_QUOTE}{_TMP_TABLE}{_QUOTE} ({columns_sql}) "
                f"SELECT {columns_sql} FROM {_QUOTE}{_TABLE}{_QUOTE}"
            )
        )
        conn.execute(text(f"DROP TABLE {_QUOTE}{_TABLE}{_QUOTE}"))
        conn.execute(
            text(
                f"ALTER TABLE {_QUOTE}{_TMP_TABLE}{_QUOTE} "
                f"RENAME TO {_QUOTE}{_TABLE}{_QUOTE}"
            )
        )
        for index in ChatMessage.__table__.indexes:
            try:
                conn.execute(text(str(CreateIndex(index).compile(engine))))
            except Exception as exc:  # noqa: BLE001 - 索引已存在时忽略
                logger.debug("重建 chat_messages 索引 %s 失败: %s", index.name, exc)


def _widen_other_dialect() -> None:
    """MySQL / PostgreSQL：修改可空性并补充 group_id 列与索引。"""
    with engine.begin() as conn:
        if engine.dialect.name in ("mysql", "mariadb"):
            conn.execute(text(f"ALTER TABLE {_TABLE} MODIFY COLUMN recipient_id INTEGER NULL"))
        else:
            conn.execute(
                text(f"ALTER TABLE {_TABLE} ALTER COLUMN recipient_id DROP NOT NULL")
            )
        conn.execute(text(f"ALTER TABLE {_TABLE} ADD COLUMN group_id INTEGER NULL"))
        try:
            conn.execute(
                text(f"CREATE INDEX ix_chat_messages_group_id ON {_TABLE} (group_id)")
            )
        except Exception as exc:  # noqa: BLE001 - 索引已存在时忽略
            logger.debug("创建 chat_messages.group_id 索引失败: %s", exc)


def ensure_im_schema() -> bool:
    """幂等迁移；返回是否执行了变更。异常由调用方决定如何处理。"""
    if not _table_exists(_TABLE):
        # 全新数据库：init_db() 会按模型建表，无需迁移
        return False
    _ensure_group_tables()
    columns = _column_info()
    recipient = columns.get("recipient_id")
    needs_widen = bool(recipient) and not recipient.get("nullable", True)
    needs_group_column = "group_id" not in columns
    if not needs_widen and not needs_group_column:
        return False
    if _IS_SQLITE:
        _rebuild_sqlite_table()
    else:
        _widen_other_dialect()
    logger.warning(
        "即时通信表结构迁移完成: chat_messages.recipient_id 可空=%s, group_id 新增=%s",
        needs_widen,
        needs_group_column,
    )
    return True


def run_ensure_im_schema() -> None:
    """启动期调用入口：吞掉异常并记录，避免影响应用可用性。"""
    try:
        ensure_im_schema()
    except Exception as exc:  # noqa: BLE001
        logger.warning("即时通信表结构迁移失败（群聊写入可能不可用）: %s", exc)


__all__ = ["ensure_im_schema", "run_ensure_im_schema"]
