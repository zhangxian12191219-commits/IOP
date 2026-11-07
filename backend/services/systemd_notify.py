"""systemd sd_notify / Watchdog 心跳（无需第三方依赖）

- 启动完成发送 READY=1（systemd 单元 Type=notify 需要）
- 周期性发送 WATCHDOG=1（配合 WatchdogSec=），超时未收到则 systemd 自动重启
- 停止前发送 STOPPING=1
未在 systemd 下运行（无 NOTIFY_SOCKET）时全部为无操作。
"""
import logging
import os
import socket

logger = logging.getLogger(__name__)

_READY = False


def _send(message: str) -> bool:
    address = os.getenv("NOTIFY_SOCKET", "").strip()
    if not address:
        return False
    # abstract namespace socket 以 @ 开头，发送时用 \0 替换
    target = "\0" + address[1:] if address.startswith("@") else address
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        try:
            sock.connect(target)
            sock.sendall(message.encode("utf-8"))
        finally:
            sock.close()
        return True
    except Exception as exc:  # noqa: BLE001
        logger.debug("sd_notify 发送失败: %s", exc)
        return False


def ready(status: str = "") -> bool:
    global _READY
    _READY = True
    message = "READY=1"
    if status:
        message += f"\nSTATUS={status}"
    return _send(message)


def watchdog() -> bool:
    return _send("WATCHDOG=1")


def stopping(status: str = "Stopping") -> bool:
    return _send(f"STOPPING=1\nSTATUS={status}")


def status(text: str) -> bool:
    return _send(f"STATUS={text}")


def enabled() -> bool:
    return bool(os.getenv("NOTIFY_SOCKET", "").strip())


def watchdog_interval() -> float:
    """WatchdogSec 的一半；systemd 通过 WATCHDOG_USEC 传入微秒"""
    raw = os.getenv("WATCHDOG_USEC", "").strip()
    try:
        usec = int(raw)
    except (TypeError, ValueError):
        return 0.0
    if usec <= 0:
        return 0.0
    return max(1.0, usec / 1_000_000 / 2)
