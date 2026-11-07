"""机柜电子锁对接服务

支持多种驱动（通过机柜 lock_config 配置）：
- none      未接硬件，仅维护软件状态（默认）
- demo      演示模式，模拟开/关锁成功，可选 fail=true 模拟失败
- http      通过 HTTP 接口控制（网络锁控板 / 智能锁网关）
- relay_tcp 通过 TCP 继电器板发送指令（如 AT+RELAY=...）

约定：驱动失败抛出 LockError，由路由记录审计日志并返回 400/502。
"""
import ipaddress
import json
import logging
import socket
from urllib.parse import urlparse
import urllib.error
import urllib.request
from typing import Any, Dict, Tuple

logger = logging.getLogger("snmp-monitor.cabinet-lock")

TIMEOUT = 5


class LockError(Exception):
    """电子锁操作失败"""


def _check_remote_host(host: str, label: str) -> str:
    value = str(host or "").strip()
    if not value:
        raise LockError(f"{label}未配置")
    try:
        ip = ipaddress.ip_address(value)
        if ip.is_loopback or ip.is_link_local or ip.is_unspecified:
            raise LockError(f"{label}不允许使用回环、链路本地或未指定地址")
    except ValueError:
        if value.lower() in {"localhost", "metadata.google.internal", "metadata"}:
            raise LockError(f"{label}不允许使用本机或云元数据地址")
    return value


def _cfg(cabinet) -> Dict[str, Any]:
    config = getattr(cabinet, "lock_config", None) or {}
    return config if isinstance(config, dict) else {}


def _driver_demo(cabinet, action: str) -> str:
    config = _cfg(cabinet)
    if config.get("fail"):
        raise LockError("演示模式配置为失败（lock_config.fail=true）")
    return f"演示模式：{action} 成功"


def _driver_http(cabinet, action: str) -> str:
    config = _cfg(cabinet)
    url = (config.get("url") or "").strip()
    if not url:
        raise LockError("HTTP 电子锁未配置 url")
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise LockError("锁控 url 必须是 http:// 或 https:// 地址")
    _check_remote_host(parsed.hostname, "锁控地址")
    method = str(config.get("method") or "POST").upper()
    if method not in ("POST", "PUT"):
        raise LockError("锁控 HTTP 方法只支持 POST 或 PUT")
    payload = {
        "action": action,
        "cabinet_id": cabinet.id,
        "cabinet_name": cabinet.name,
        "channel": config.get("channel"),
    }
    headers = {"Content-Type": "application/json"}
    token = config.get("token")
    if token:
        headers["Authorization"] = str(token)

    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=float(config.get("timeout") or TIMEOUT)) as resp:
            body = resp.read(512).decode("utf-8", errors="replace")
            if resp.status >= 400:
                raise LockError(f"锁控接口返回 HTTP {resp.status}: {body[:120]}")
    except urllib.error.URLError as exc:
        raise LockError(f"锁控接口连接失败: {exc}") from exc
    return f"HTTP 锁控 {action} 成功"


def _driver_relay_tcp(cabinet, action: str) -> str:
    config = _cfg(cabinet)
    host = _check_remote_host(config.get("host"), "TCP 继电器")
    port = int(config.get("port") or 8080)

    channel = config.get("channel", 1)
    default_cmd = "AT+RELAY={ch},{val}\r\n"
    template = config.get("unlock_cmd") if action == "unlock" else config.get("lock_cmd")
    command = template or default_cmd
    command = str(command).format(ch=channel, val=1 if action == "unlock" else 0)

    try:
        with socket.create_connection((host, port), timeout=float(config.get("timeout") or TIMEOUT)) as sock:
            sock.settimeout(float(config.get("timeout") or TIMEOUT))
            sock.sendall(command.encode("utf-8"))
            try:
                sock.recv(256)
            except socket.timeout:
                pass
    except OSError as exc:
        raise LockError(f"继电器连接失败: {exc}") from exc
    return f"TCP 继电器 {action} 指令已发送"


DRIVERS = {
    "none": lambda cabinet, action: "未配置电子锁硬件，仅更新软件状态",
    "demo": _driver_demo,
    "http": _driver_http,
    "relay_tcp": _driver_relay_tcp,
}


def operate(cabinet, action: str) -> Tuple[bool, str]:
    """执行开锁/上锁；返回 (成功, 说明)"""
    if action not in ("unlock", "lock"):
        raise LockError(f"不支持的操作: {action}")

    lock_type = (getattr(cabinet, "lock_type", None) or "none").lower()
    driver = DRIVERS.get(lock_type)
    if driver is None:
        raise LockError(f"不支持的电子锁类型: {lock_type}")

    try:
        message = driver(cabinet, action)
    except LockError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("电子锁操作异常")
        raise LockError(f"电子锁操作异常: {exc}") from exc

    logger.info("机柜电子锁 %s %s: %s", cabinet.name, action, message)
    return True, message


def lock_config_summary(cabinet) -> Dict[str, Any]:
    """返回脱敏后的锁配置（不暴露 token/密码）"""
    config = _cfg(cabinet)
    safe = {}
    for key, value in config.items():
        if key in ("token", "password", "secret"):
            safe[key] = "******" if value else ""
        else:
            safe[key] = value
    return {
        "lock_type": getattr(cabinet, "lock_type", "none") or "none",
        "is_locked": bool(getattr(cabinet, "is_locked", True)),
        "last_unlock_at": (
            cabinet.last_unlock_at.isoformat() if cabinet.last_unlock_at else None
        ),
        "last_unlock_by": cabinet.last_unlock_by,
        "config": safe,
    }
