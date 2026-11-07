#!/usr/bin/env python3
"""Web 登录网关应急恢复工具。

用途：HTTPS/登录网关配置错误导致无法打开 Web 页面时，在服务器本地关闭
登录网关，恢复内部 8000 端口访问。执行后需要重启应用进程。

用法：
    python tools/recover_web_gateway.py
    python tools/recover_web_gateway.py --http80

默认关闭 HTTP/HTTPS 登录网关；--http80 会启用 HTTP 80 作为恢复地址。
"""
from __future__ import annotations

import argparse
import os
import sqlite3
from pathlib import Path
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parent.parent
os.environ.setdefault("PYTHONPATH", str(ROOT))


def _sqlite_path() -> Path | None:
    url = os.getenv("DATABASE_URL", "sqlite:///snmp_monitor.db")
    if not url.startswith("sqlite"):
        return None
    raw = url.split("sqlite:///", 1)[-1].split("?", 1)[0]
    path = Path(unquote(raw))
    if not path.is_absolute():
        path = ROOT / path
    return path


def _print_restart_help() -> None:
    print("\n请重启应用使配置生效，任选一种：")
    print("  sudo systemctl restart snmp-nms")
    print("  ./start.sh restart")
    print("  docker compose restart snmp-nms")
    print("\n重启后访问：http://<服务器IP>:8000")
    print("确认能打开后，再到「系统配置 → 登录与安全」重新配置 HTTP/HTTPS。")


def main() -> int:
    parser = argparse.ArgumentParser(description="关闭/重置 Web 登录网关，恢复 8000 访问")
    parser.add_argument(
        "--http80",
        action="store_true",
        help="关闭 HTTPS，同时启用 HTTP 80（80 被占用或无权限时不要使用）",
    )
    args = parser.parse_args()
    db_path = _sqlite_path()
    if db_path is None:
        print("当前 DATABASE_URL 不是 SQLite，无法自动修改。请执行以下 SQL 后重启：")
        print(
            "UPDATE system_settings SET value='False' "
            "WHERE key IN ('web_http_enabled','web_https_enabled');"
        )
        _print_restart_help()
        return 1
    if not db_path.is_file():
        print(f"数据库不存在: {db_path}")
        return 1
    values = {
        "web_https_enabled": "False",
        "web_ssl_certificate_id": "0",
        "web_http_enabled": "True" if args.http80 else "False",
        "web_http_port": "80",
        "web_https_port": "443",
    }
    conn = sqlite3.connect(str(db_path))
    try:
        for key, value in values.items():
            conn.execute(
                "UPDATE system_settings SET value=? WHERE key=?",
                (value, key),
            )
        conn.commit()
        rows = conn.execute(
            "SELECT key,value FROM system_settings WHERE key LIKE 'web_%' ORDER BY key"
        ).fetchall()
    finally:
        conn.close()
    print(f"已更新数据库: {db_path}")
    for key, value in rows:
        print(f"  {key} = {value}")
    _print_restart_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
