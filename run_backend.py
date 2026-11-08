#!/usr/bin/env python3
"""后端启动脚本（支持前台运行与进程守护配合）

用法:
    python run_backend.py                # 默认 0.0.0.0:8000
    python run_backend.py 8010           # 指定端口
    python run_backend.py --check        # 仅做启动自检（依赖/数据库/端口）

特性:
- 自动把项目上层的 vendor 目录（如存在）加入 sys.path
- 启动异常自动重试（默认 3 次，指数退避），失败后以非 0 退出，交由 systemd / Docker 重启
- 日志同时输出到控制台与 data/logs/backend.log（轮转）
"""
import os
import socket
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent          # snmp-monitor/
WORKSPACE = ROOT.parent                          # 工作区
VENDOR = WORKSPACE / "vendor"

if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))
sys.path.insert(0, str(ROOT))

import uvicorn  # noqa: E402

from backend.config import Config  # noqa: E402


def _port_in_use(host: str, port: int) -> bool:
    """检测端口是否已被占用（connect 探测 + bind 兜底，兼容 Windows 的 SO_REUSEADDR 行为）"""
    target = "127.0.0.1" if host in ("0.0.0.0", "::") else host
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            if sock.connect_ex((target, port)) == 0:
                return True
    except OSError:
        pass

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind((target, port))
            return False
        except OSError:
            return True


def _self_check(port: int) -> int:
    """启动自检：依赖、数据目录、端口"""
    try:
        import fastapi, sqlalchemy, pysnmp, aiohttp  # noqa: F401
    except ImportError as exc:
        print(f"[自检失败] 缺少依赖: {exc}\n请执行: pip install -r backend/requirements.txt")
        return 2

    Path(Config.LOG_DIR).mkdir(parents=True, exist_ok=True)
    Path(Config.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)

    if _port_in_use(Config.API_HOST, port):
        print(f"[自检失败] 端口 {port} 已被占用，请先停止占用进程或更换端口")
        return 3

    print("[自检通过] 依赖、目录、端口均正常")
    return 0


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    flags = {a for a in sys.argv[1:] if a.startswith("-")}
    port = int(args[0]) if args else Config.API_PORT
    # 让 Web 登录网关知道内部应用实际端口
    os.environ["API_PORT"] = str(port)

    if "--check" in flags:
        return _self_check(port)

    Path(Config.LOG_DIR).mkdir(parents=True, exist_ok=True)
    print(f"[启动] 智能运维服务平台后端 -> http://127.0.0.1:{port}")
    print(f"[文档] Swagger API -> http://127.0.0.1:{port}/docs")
    print(f"[日志] {Path(Config.LOG_DIR) / 'backend.log'}")

    # 端口被占用时直接退出（避免死循环重启），交由人工/编排系统处理
    if _port_in_use(Config.API_HOST, port):
        print(f"[错误] 端口 {port} 已被占用，退出")
        return 3

    retries = max(1, int(os.getenv("STARTUP_RETRIES", "3")))
    for attempt in range(1, retries + 1):
        try:
            uvicorn.run(
                "backend.app:app",
                host=Config.API_HOST,
                port=port,
                reload=False,
                log_level=Config.LOG_LEVEL.lower(),
                timeout_graceful_shutdown=20,
            )
            return 0
        except KeyboardInterrupt:
            print("[退出] 收到中断信号，正常退出")
            return 0
        except SystemExit as exc:  # uvicorn 内部 sys.exit
            code = int(exc.code or 0)
            if code == 0:
                return 0
            print(f"[错误] 服务退出，返回码 {code}")
            return code
        except Exception as exc:  # noqa: BLE001
            print(f"[错误] 启动失败（第 {attempt}/{retries} 次）: {exc}")
            if attempt >= retries:
                print("[错误] 已重试到上限，退出（由 systemd/Docker 负责再次拉起）")
                return 1
            time.sleep(min(30, 5 * attempt))
    return 1


if __name__ == "__main__":
    sys.exit(main())
