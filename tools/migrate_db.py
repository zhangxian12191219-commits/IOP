#!/usr/bin/env python3
"""数据库迁移工具：SQLite ↔ MySQL ↔ PostgreSQL

用法示例：
  # SQLite（当前 data/snmp_monitor.db）→ MySQL（先建好空库 snmp_nms）
  python tools/migrate_db.py \
      --to "mysql+pymysql://nms:密码@127.0.0.1:3306/snmp_nms?charset=utf8mb4"

  # SQLite → PostgreSQL
  python tools/migrate_db.py \
      --to "postgresql+psycopg2://nms:密码@127.0.0.1:5432/snmp_nms"

  # 指定源库（默认读取环境变量 DATABASE_URL / sqlite:///snmp_monitor.db）
  python tools/migrate_db.py --from "sqlite:///snmp_monitor.db" --to "mysql+pymysql://..."

  # 目标库已有数据时先清空再导入
  python tools/migrate_db.py --to "..." --truncate
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import Boolean, create_engine, inspect, text  # noqa: E402

# 先导入模型，确保 Base.metadata 包含所有表
from backend.models.database import Base  # noqa: E402
import backend.models  # noqa: F401,E402
import backend.models.database as database_module  # noqa: F401,E402


def _row_to_dict(table, row):
    """把源库一行转换为可插入目标库的 dict（处理布尔值差异）"""
    data = dict(row)
    for column in table.columns:
        value = data.get(column.name)
        if value is None:
            continue
        if isinstance(column.type, Boolean):
            data[column.name] = bool(value)
    return data


def _clear_target(conn, dialect: str, table_names) -> None:
    if dialect == "sqlite":
        conn.execute(text("PRAGMA foreign_keys=OFF"))
        for name in reversed(list(table_names)):
            conn.execute(text(f'DELETE FROM "{name}"'))
        conn.execute(text("PRAGMA foreign_keys=ON"))
    elif dialect == "mysql":
        conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
        for name in reversed(list(table_names)):
            conn.execute(text(f"DELETE FROM `{name}`"))
        conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
    elif dialect == "postgresql":
        quoted = ", ".join(f'"{name}"' for name in table_names)
        conn.execute(text(f"TRUNCATE {quoted} RESTART IDENTITY CASCADE"))
    else:
        for name in reversed(list(table_names)):
            conn.execute(text(f'DELETE FROM "{name}"'))


def _reset_postgres_sequences(conn, table_names) -> None:
    """PostgreSQL：迁移显式 id 后重置自增序列，避免后续插入主键冲突"""
    for name in table_names:
        try:
            conn.execute(text(
                f"SELECT setval(pg_get_serial_sequence('{name}', 'id'), "
                f"COALESCE((SELECT MAX(id) FROM \"{name}\"), 1))"
            ))
        except Exception:  # noqa: BLE001
            pass


def migrate(from_url: str, to_url: str, truncate: bool = False, batch_size: int = 500) -> int:
    source = create_engine(from_url)
    target = create_engine(to_url)

    source_inspector = inspect(source)
    source_tables = set(source_inspector.get_table_names())
    tables = [t for t in Base.metadata.sorted_tables if t.name in source_tables]

    if not tables:
        print("源库中没有可迁移的表（请确认 --from 是否正确）")
        return 1

    print(f"源库: {from_url}")
    print(f"目标库: {to_url}")
    print(f"表数量: {len(tables)}")

    Base.metadata.create_all(bind=target)

    target_dialect = target.dialect.name
    with target.begin() as conn:
        if truncate:
            print("清空目标库已有数据 ...")
            _clear_target(conn, target_dialect, [t.name for t in tables])

    total_rows = 0
    target_tables = set(inspect(target).get_table_names())
    with source.connect() as src_conn:
        for table in tables:
            if table.name not in target_tables:
                print(f"  [跳过] {table.name}（目标库不存在该表）")
                continue
            rows = [_row_to_dict(table, row) for row in src_conn.execute(table.select()).mappings()]
            if not rows:
                print(f"  {table.name}: 0 行")
                continue
            with target.begin() as dst_conn:
                for start in range(0, len(rows), batch_size):
                    dst_conn.execute(table.insert(), rows[start:start + batch_size])
            total_rows += len(rows)
            print(f"  {table.name}: {len(rows)} 行")

    if target_dialect == "postgresql":
        with target.begin() as conn:
            _reset_postgres_sequences(conn, [t.name for t in tables])

    print(f"迁移完成，共 {total_rows} 行。")

    # 校验行数
    print("行数校验：")
    with source.connect() as src_conn, target.connect() as dst_conn:
        for table in tables:
            src_count = src_conn.execute(text(f'SELECT COUNT(*) FROM "{table.name}"')).scalar()
            dst_count = dst_conn.execute(text(f'SELECT COUNT(*) FROM "{table.name}"')).scalar()
            flag = "OK" if src_count == dst_count else "不一致!"
            print(f"  {table.name}: {src_count} -> {dst_count} [{flag}]")

    print("\n提示：迁移完成后把应用的 DATABASE_URL 指向目标库并重启服务即可。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="智能运维服务平台数据库迁移工具")
    parser.add_argument(
        "--from", dest="from_url",
        default=os.getenv("DATABASE_URL", "sqlite:///snmp_monitor.db"),
        help="源数据库 URL（默认取 DATABASE_URL 或 sqlite:///snmp_monitor.db）",
    )
    parser.add_argument("--to", dest="to_url", required=True, help="目标数据库 URL")
    parser.add_argument("--truncate", action="store_true", help="导入前清空目标库数据")
    parser.add_argument("--batch", type=int, default=500, help="批量插入行数（默认 500）")
    args = parser.parse_args()

    if args.from_url == args.to_url:
        print("源库与目标库相同，无需迁移")
        return 1
    return migrate(args.from_url, args.to_url, args.truncate, args.batch)


if __name__ == "__main__":
    raise SystemExit(main())
