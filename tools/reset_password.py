#!/usr/bin/env python3
"""服务器端密码恢复工具（仅限拥有服务器/数据库访问权限的运维人员）。

用途：
  - 普通用户忘记密码：由管理员在「用户权限」中重置；
  - 超级管理员忘记密码 / 所有管理员均无法登录：在项目目录运行本工具。

示例：
  python tools/reset_password.py --list-admins
  python tools/reset_password.py --username admin
  python tools/reset_password.py --username admin --enable --yes

安全说明：
  - 重置不需要旧密码，但必须能登录部署服务器；
  - 交互式输入新密码，不在命令行暴露密码；
  - 重置后旧密码立即失效，并清除登录失败锁定；
  - 操作写入审计日志。
"""
import argparse
import getpass
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKSPACE = ROOT.parent
VENDOR = WORKSPACE / "vendor"
# 保证 SQLite 相对数据库路径始终以项目根目录为基准
os.chdir(ROOT)
for extra in (ROOT, VENDOR):
    if extra.exists() and str(extra) not in sys.path:
        sys.path.insert(0, str(extra))

from fastapi import HTTPException  # noqa: E402

from backend.models.database import SessionLocal, init_db  # noqa: E402
from backend.models.user import User  # noqa: E402
from backend.services import audit, password_policy, security  # noqa: E402
from backend.services.auth import hash_password  # noqa: E402


def list_admins(db) -> int:
    admins = (
        db.query(User)
        .filter(User.is_superuser == True)  # noqa: E712
        .order_by(User.id)
        .all()
    )
    if not admins:
        print("[提示] 当前没有超级管理员账号。")
        return 0
    print("超级管理员账号：")
    for user in admins:
        state = "启用" if user.is_active else "已禁用"
        print(f"  - id={user.id}  用户名={user.username}  姓名={user.real_name or '-'}  状态={state}")
    return 0


def read_password(args) -> str:
    if args.password:
        return args.password
    while True:
        first = getpass.getpass("请输入新密码（输入时不显示）: ")
        if not first:
            print("[失败] 新密码不能为空。")
            continue
        second = getpass.getpass("请再次输入新密码: ")
        if first != second:
            print("[失败] 两次输入的密码不一致，请重试。")
            continue
        return first


def main() -> int:
    parser = argparse.ArgumentParser(
        description="智能运维服务平台服务器端密码恢复工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--username", help="需要重置密码的登录名（如 admin）")
    parser.add_argument("--password", help="直接指定新密码；交互执行时建议省略，避免留在 shell 历史中")
    parser.add_argument("--list-admins", action="store_true", help="列出全部超级管理员账号后退出")
    parser.add_argument("--enable", action="store_true", help="同时启用被禁用的账号")
    parser.add_argument("--yes", action="store_true", help="跳过交互确认（用于受控自动化）")
    args = parser.parse_args()

    init_db()
    db = SessionLocal()
    try:
        if args.list_admins:
            return list_admins(db)
        if not args.username:
            parser.print_help()
            print("\n[提示] 请使用 --username 指定要重置的账号，或使用 --list-admins 查看管理员。")
            return 2

        user = db.query(User).filter(User.username == args.username.strip()).first()
        if not user:
            print(f"[失败] 用户不存在: {args.username}")
            return 1

        if not args.yes:
            role = "超级管理员" if user.is_superuser else "普通用户"
            print(f"目标账号: {user.username}（{role}，{'启用' if user.is_active else '已禁用'}）")
            answer = input(f"确认重置该账号密码？输入用户名 {user.username} 继续: ").strip()
            if answer != user.username:
                print("[取消] 未重置任何密码。")
                return 1

        password = read_password(args)
        try:
            password_policy.validate_password(db, password)
        except HTTPException as exc:
            print(f"[失败] 新密码不符合策略: {exc.detail}")
            return 1

        user.password_hash = hash_password(password)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        user.password_changed_at = now
        user.updated_at = now
        if args.enable:
            user.is_active = True
        db.commit()

        # 清除登录失败锁定，避免重置后仍被临时锁定
        try:
            security.clear_failures(db, user.username)
        except Exception as exc:  # noqa: BLE001
            print(f"[提示] 清除登录锁定失败（可忽略）: {exc}")

        audit.record(
            db,
            None,
            module="users",
            action="update",
            target_type="user",
            target_id=user.id,
            target_name=user.username,
            after={"password": "******", "enabled": bool(user.is_active)},
            message="服务器命令行重置密码",
            operator="server-cli",
        )
        print(f"[成功] 已重置用户 {user.username} 的密码，旧密码立即失效。")
        if not user.is_active:
            print("[提示] 该账号仍处于禁用状态；如需启用请追加 --enable。")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
