"""系统开机自启状态与开关。

Linux 使用 systemd 服务名（默认 snmp-nms），Windows 使用当前用户的
HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Run 启动项。
只负责“是否随系统启动”，不会启动/停止正在运行的服务。
"""
from __future__ import annotations

import os
import platform
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict

SERVICE_NAME = os.getenv("SNMP_SERVICE_NAME", "snmp-nms").strip() or "snmp-nms"
APP_ROOT = Path(__file__).resolve().parents[2]
RUN_SCRIPT = APP_ROOT / "run_backend.py"
WINDOWS_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
WINDOWS_VALUE_NAME = "SNMPMonitor"


def _run(command: list[str], timeout: int = 20) -> subprocess.CompletedProcess:
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _linux_status() -> Dict[str, Any]:
    unit = SERVICE_NAME if SERVICE_NAME.endswith(".service") else f"{SERVICE_NAME}.service"
    result: Dict[str, Any] = {
        "platform": "linux",
        "mode": "systemd",
        "service": unit,
        "supported": False,
        "enabled": False,
        "active": False,
        "message": "",
    }
    try:
        enabled = _run(["systemctl", "is-enabled", unit], timeout=10)
        active = _run(["systemctl", "is-active", unit], timeout=10)
        state = (enabled.stdout or "").strip().splitlines()
        enabled_state = state[0] if state else (enabled.stderr or "").strip()
        active_state = (active.stdout or "").strip() or (active.stderr or "").strip()
        # unit 不存在时 systemctl 的 stderr 通常包含 not-found
        unit_missing = "not-found" in (enabled.stderr or "").lower()
        result.update({
            "supported": not unit_missing,
            "enabled": enabled_state in ("enabled", "enabled-runtime"),
            "enabled_state": enabled_state or "unknown",
            "active": active_state == "active",
            "active_state": active_state or "unknown",
            "message": (
                f"systemd 服务 {unit} 已随系统启动"
                if enabled_state in ("enabled", "enabled-runtime")
                else f"systemd 服务 {unit} 未设置开机自启"
            ) if not unit_missing else (
                f"未检测到 systemd 服务 {unit}，请使用部署脚本安装服务"
            ),
        })
    except FileNotFoundError:
        result["message"] = "当前系统没有 systemctl，无法通过 systemd 管理开机自启"
    except subprocess.TimeoutExpired:
        result["message"] = "查询 systemd 服务状态超时"
    except Exception as exc:  # noqa: BLE001
        result["message"] = f"查询 systemd 服务状态失败: {exc}"
    return result


def _windows_command() -> str:
    executable = Path(sys.executable)
    return f'"{executable}" "{RUN_SCRIPT}" 8000'


def _windows_status() -> Dict[str, Any]:
    result: Dict[str, Any] = {
        "platform": "windows",
        "mode": "startup-registry",
        "service": "SNMPMonitor",
        "supported": True,
        "enabled": False,
        # 当前请求由正在运行的本系统进程处理，因此 Windows 下服务一定是运行中
        "active": True,
        "active_state": "running",
        "command": _windows_command(),
        "message": "",
    }
    try:
        import winreg  # type: ignore
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_READ) as key:
            value, _ = winreg.QueryValueEx(key, WINDOWS_VALUE_NAME)
        result["enabled"] = bool(value)
        result["message"] = "已设置为当前用户登录时启动" if value else "未设置开机自启"
    except FileNotFoundError:
        result["message"] = "未设置开机自启"
    except Exception as exc:  # noqa: BLE001
        result["supported"] = False
        result["message"] = f"读取 Windows 启动项失败: {exc}"
    return result


def get_status() -> Dict[str, Any]:
    system = platform.system().lower()
    if system == "linux":
        return _linux_status()
    if system == "windows":
        return _windows_status()
    return {
        "platform": system or "unknown",
        "mode": "unsupported",
        "service": SERVICE_NAME,
        "supported": False,
        "enabled": False,
        "active": False,
        "message": "当前操作系统不支持一键设置开机自启，请使用系统服务管理器配置",
    }


def set_enabled(enabled: bool) -> Dict[str, Any]:
    status = get_status()
    if not status.get("supported"):
        raise ValueError(status.get("message") or "当前环境不支持设置开机自启")
    if status.get("platform") == "linux":
        unit = status["service"]
        action = "enable" if enabled else "disable"
        try:
            proc = _run(["systemctl", action, unit], timeout=20)
        except FileNotFoundError as exc:
            raise ValueError("当前系统没有 systemctl") from exc
        except subprocess.TimeoutExpired as exc:
            raise ValueError("设置 systemd 开机自启超时") from exc
        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            if "Interactive authentication required" in detail or "Access denied" in detail:
                detail = "权限不足：请以 root 或具有 sudo 权限的服务账号运行"
            raise ValueError(detail or f"systemctl {action} 执行失败")
        return get_status()
    if status.get("platform") == "windows":
        try:
            import winreg  # type: ignore
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, WINDOWS_RUN_KEY, 0, winreg.KEY_SET_VALUE
            ) as key:
                if enabled:
                    winreg.SetValueEx(key, WINDOWS_VALUE_NAME, 0, winreg.REG_SZ, _windows_command())
                else:
                    try:
                        winreg.DeleteValue(key, WINDOWS_VALUE_NAME)
                    except FileNotFoundError:
                        pass
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"写入 Windows 启动项失败: {exc}") from exc
        return get_status()
    raise ValueError("当前操作系统不支持设置开机自启")
