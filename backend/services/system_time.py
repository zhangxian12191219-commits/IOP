"""系统时间 / NTP 设置服务（Windows / Linux 通用）

设计要点：
- 只通过 subprocess 参数列表调用系统命令（不使用 shell，无字符串拼接注入风险）
- 所有外部命令统一 10 秒超时，失败/权限不足/命令不存在都转换为结构化 JSON，绝不抛出 500
- 手工设置时间只在用户明确操作时执行（Windows: PowerShell Set-Date；Linux: timedatectl set-time / date -s）
- NTP 开关与服务器列表持久化在 system_settings（ntp_enabled / ntp_servers），
  并在系统命令执行失败时如实返回 ok=False，不伪造成功
"""
import ipaddress
import logging
import os
import platform
import re
import shutil
import socket
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..models.settings import SystemSetting

logger = logging.getLogger(__name__)

COMMAND_TIMEOUT = 10            # 单条系统命令最长 10 秒，避免阻塞请求
MAX_SERVERS = 8
DEFAULT_SERVERS = ("ntp.aliyun.com", "ntp1.aliyun.com")
NTP_ENABLED_KEY = "ntp_enabled"
NTP_SERVERS_KEY = "ntp_servers"
TIMESYNCD_DROPIN = Path("/etc/systemd/timesyncd.conf.d/snmp-nms.conf")

IS_WINDOWS = os.name == "nt"

_HOSTNAME_RE = re.compile(
    r"^(?=.{1,253}$)(?!-)[A-Za-z0-9-]{1,63}(?<!-)(\.(?!-)[A-Za-z0-9-]{1,63}(?<!-))*$"
)
_TIMEZONE_RE = re.compile(r"^[A-Za-z0-9_+\-/]{1,64}$")


# ==================== 校验 ====================

def validate_ntp_server(value: Any) -> str:
    """校验单个 NTP 服务器（IP 或主机名），非法时抛 ValueError"""
    text = str(value or "").strip()
    if not text:
        raise ValueError("NTP 服务器地址不能为空")
    if len(text) > 253:
        raise ValueError(f"NTP 服务器地址过长：{text[:40]}…")
    try:
        ipaddress.ip_address(text)
        return text
    except ValueError:
        pass
    if _HOSTNAME_RE.match(text):
        return text
    raise ValueError(f"NTP 服务器地址不合法：{text}")


def parse_server_list(raw: Any) -> List[str]:
    """把列表 / 逗号 / 换行 / 分号分隔的服务器配置解析为去重列表"""
    if raw is None:
        return []
    if isinstance(raw, (list, tuple, set)):
        items = [str(item) for item in raw]
    else:
        items = re.split(r"[,;\r\n]+", str(raw))
    servers: List[str] = []
    for item in items:
        text = item.strip()
        if not text:
            continue
        server = validate_ntp_server(text)
        if server not in servers:
            servers.append(server)
    if len(servers) > MAX_SERVERS:
        raise ValueError(f"NTP 服务器最多 {MAX_SERVERS} 个")
    return servers


def validate_timezone(value: Any) -> str:
    """校验时区名（IANA），支持 UTC"""
    text = str(value or "").strip()
    if not text:
        raise ValueError("时区不能为空")
    if not _TIMEZONE_RE.match(text):
        raise ValueError("时区格式不合法")
    if text.upper() == "UTC":
        return "UTC"
    try:
        from zoneinfo import ZoneInfo

        ZoneInfo(text)
        return text
    except Exception:  # noqa: BLE001 - 缺少 tzdata 时回退到白名单
        pass
    try:
        from .settings import TIMEZONES

        if text in TIMEZONES:
            return text
    except Exception:  # noqa: BLE001
        pass
    raise ValueError(f"不支持的时区：{text}")


def parse_local_datetime(value: Any) -> datetime:
    """解析前端 datetime-local 提交的本地时间字符串"""
    text = str(value or "").strip()
    if not text:
        raise ValueError("请选择要设置的系统时间")
    normalized = text.replace(" ", "T", 1)
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("时间格式不合法，应为 YYYY-MM-DD HH:MM[:SS]") from exc
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone().replace(tzinfo=None)
    if not 2000 <= parsed.year <= 2100:
        raise ValueError("系统时间超出允许范围（2000 ~ 2100 年）")
    return parsed.replace(microsecond=0)


# ==================== 配置持久化 ====================

def _read_settings(db: Session) -> Dict[str, str]:
    rows = (
        db.query(SystemSetting)
        .filter(SystemSetting.key.in_((NTP_ENABLED_KEY, NTP_SERVERS_KEY)))
        .all()
    )
    return {row.key: row.value for row in rows}


def get_ntp_config(db: Session) -> Dict[str, Any]:
    """读取 NTP 配置（未配置时给出默认服务器，但默认不启用）"""
    rows = _read_settings(db)
    enabled = str(rows.get(NTP_ENABLED_KEY) or "").strip().lower() in ("1", "true", "yes", "on")
    raw_servers = rows.get(NTP_SERVERS_KEY)
    try:
        servers = parse_server_list(raw_servers) if str(raw_servers or "").strip() else list(DEFAULT_SERVERS)
    except ValueError:
        servers = list(DEFAULT_SERVERS)
    return {
        "enabled": enabled,
        "servers": servers,
        "stored": bool(rows),
    }


def save_ntp_config(db: Session, *, enabled: Optional[bool] = None, servers: Optional[List[str]] = None) -> Dict[str, Any]:
    """写入 NTP 配置（只写传入的字段）"""
    values: Dict[str, str] = {}
    if enabled is not None:
        values[NTP_ENABLED_KEY] = "True" if enabled else "False"
    if servers is not None:
        values[NTP_SERVERS_KEY] = ",".join(servers)
    if not values:
        return get_ntp_config(db)
    for key, value in values.items():
        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        if row:
            row.value = value
        else:
            db.add(SystemSetting(key=key, value=value))
    db.commit()
    return get_ntp_config(db)


# ==================== 命令执行 ====================

def _command_path(name: str) -> Optional[str]:
    """返回命令绝对路径；不存在时返回 None"""
    return shutil.which(name)


def _run(args: List[str], timeout: int = COMMAND_TIMEOUT) -> Dict[str, Any]:
    """安全执行系统命令：参数列表、无 shell、超时保护、异常结构化"""
    if not args:
        return {
            "ok": False, "code": "invalid", "command": "",
            "error": "命令参数为空", "stdout": "", "stderr": "",
        }
    binary = str(args[0])
    resolved = _command_path(binary)
    display = " ".join(str(item) for item in args)
    if not resolved:
        return {
            "ok": False, "code": "not_found", "command": display,
            "error": f"系统未安装命令 {binary}",
            "stdout": "", "stderr": "",
        }
    try:
        completed = subprocess.run(  # noqa: S603 - 参数列表，无 shell
            [resolved, *[str(item) for item in args[1:]]],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=max(1, int(timeout)),
            check=False,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False, "code": "timeout", "command": display,
            "error": f"命令执行超时（超过 {timeout} 秒）", "stdout": "", "stderr": "",
        }
    except PermissionError:
        return {
            "ok": False, "code": "permission", "command": display,
            "error": "权限不足，请使用管理员/root 权限运行服务",
            "stdout": "", "stderr": "",
        }
    except OSError as exc:
        return {
            "ok": False, "code": "os_error", "command": display,
            "error": f"命令执行失败：{exc}", "stdout": "", "stderr": "",
        }

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    ok = completed.returncode == 0
    result: Dict[str, Any] = {
        "ok": ok,
        "code": "ok" if ok else "failed",
        "command": display,
        "returncode": int(completed.returncode),
        "stdout": stdout[:4000],
        "stderr": stderr[:4000],
    }
    if not ok:
        lowered = (stderr or stdout).lower()
        if "permission denied" in lowered or "access is denied" in lowered or "拒绝访问" in lowered:
            result["code"] = "permission"
        elif "not permitted" in lowered or "must be root" in lowered:
            result["code"] = "permission"
        result["error"] = (stderr or stdout or "命令执行失败")[:1000]
    return result


def _format_offset(delta: timedelta) -> str:
    total = int(delta.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    if seconds:
        return f"{sign}{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{sign}{hours:02d}:{minutes:02d}"


def _parse_key_values(text: str) -> Dict[str, str]:
    data: Dict[str, str] = {}
    for line in str(text or "").splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key.strip()] = value.strip()
    return data


# ==================== 平台状态探测 ====================

def _linux_probe() -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "timezone": None,
        "synchronized": None,
        "ntp_enabled": None,
        "service": None,
        "source": "",
        "detail": "",
        "commands": [],
    }

    if _command_path("timedatectl"):
        result = _run([
            "timedatectl", "show",
            "-p", "Timezone", "-p", "NTP", "-p", "NTPSynchronized",
        ])
        info["commands"].append(result)
        values = _parse_key_values(result.get("stdout", ""))
        if values.get("Timezone"):
            info["timezone"] = values["Timezone"]
        if values.get("NTP") in ("yes", "no"):
            info["ntp_enabled"] = values["NTP"] == "yes"
        if values.get("NTPSynchronized") in ("yes", "no"):
            info["synchronized"] = values["NTPSynchronized"] == "yes"
        if not info["detail"] and not result.get("ok"):
            info["detail"] = result.get("error", "")

    # chrony 系统的 timedatectl 同样报告 NTP=yes，进一步识别真正使用的时间服务
    if info["ntp_enabled"] is not False and _command_path("chronyc"):
        result = _run(["chronyc", "tracking"])
        info["commands"].append(result)
        if result.get("ok"):
            info["service"] = "chronyd"
            values = {}
            for line in str(result.get("stdout") or "").splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    values[key.strip().lower()] = value.strip()
            leap = str(values.get("leap status", "")).lower()
            reference = values.get("reference id", "")
            if reference:
                info["source"] = reference
            if leap:
                info["synchronized"] = leap.startswith("normal")
        elif not info["detail"]:
            info["detail"] = result.get("error", "")

    if info["service"] is None and info["ntp_enabled"]:
        info["service"] = "systemd-timesyncd"

    if info["ntp_enabled"] and info["service"] == "systemd-timesyncd" and _command_path("timedatectl"):
        sync_result = _run([
            "timedatectl", "show-timesync",
            "-p", "ServerName", "-p", "ServerAddress",
        ])
        info["commands"].append(sync_result)
        sync_values = _parse_key_values(sync_result.get("stdout", ""))
        info["source"] = sync_values.get("ServerName") or sync_values.get("ServerAddress") or info["source"]

    # timedatectl 不存在或无法判断时，回退 ntpq
    if info["synchronized"] is None and _command_path("ntpq"):
        result = _run(["ntpq", "-p"])
        info["commands"].append(result)
        if result.get("ok"):
            info["service"] = info["service"] or "ntpd"
            lines = [
                line for line in str(result.get("stdout") or "").splitlines()
                if line.startswith(("*", "+", "-"))
            ]
            info["synchronized"] = any(line.startswith("*") for line in lines)
            if lines:
                info["source"] = lines[0].split()[0].lstrip("*+-") if lines[0].split() else ""
        elif not info["detail"]:
            info["detail"] = result.get("error", "")

    return info


def _windows_probe(servers: List[str]) -> Dict[str, Any]:
    info: Dict[str, Any] = {
        "timezone": None,
        "synchronized": None,
        "ntp_enabled": None,
        "service": "w32time",
        "source": "",
        "detail": "",
        "commands": [],
    }

    if _command_path("tzutil"):
        result = _run(["tzutil", "/g"])
        info["commands"].append(result)
        if result.get("ok") and result.get("stdout"):
            info["timezone"] = result["stdout"].splitlines()[0].strip()

    if not _command_path("w32tm"):
        info["detail"] = "未找到 w32tm 命令，无法查询系统时间同步状态"
        return info

    result = _run(["w32tm", "/query", "/status"])
    info["commands"].append(result)
    if not result.get("ok"):
        info["detail"] = result.get("error", "")
        info["synchronized"] = False
        return info

    output = str(result.get("stdout") or "")
    lowered = output.lower()
    matched = [server for server in servers if server and server.lower() in lowered]
    if matched:
        info["synchronized"] = True
        info["source"] = matched[0]
        info["ntp_enabled"] = True
    elif "cmos" in lowered or "local clock" in lowered or "本地" in output:
        info["synchronized"] = False
        info["ntp_enabled"] = False
        info["source"] = "Local CMOS Clock"
    else:
        info["synchronized"] = None
        info["ntp_enabled"] = None
        info["source"] = (output.splitlines()[-1][:200] if output else "")
    info["detail"] = output[:2000]
    return info


# ==================== 状态 ====================

def get_status(db: Session) -> Dict[str, Any]:
    """完整状态：系统时间、时区/UTC 偏移、NTP 状态与服务器、平台能力"""
    config = get_ntp_config(db)
    now = datetime.now()
    local = now.astimezone()
    offset = local.utcoffset() or timedelta(0)

    if IS_WINDOWS:
        probe = _windows_probe(config["servers"])
        platform_label = "Windows"
    else:
        probe = _linux_probe()
        platform_label = "Linux" if platform.system().lower() == "linux" else platform.system()

    timezone_name = probe.get("timezone") or local.tzname() or "UTC"
    # Windows 的 tzutil 返回 Windows 时区 ID（如 China Standard Time），仅作展示
    timezone_display = timezone_name

    warnings: List[str] = []
    if IS_WINDOWS:
        if not _command_path("w32tm"):
            warnings.append("未检测到 w32tm，无法查询或配置 Windows 时间同步。")
        if not _command_path("powershell"):
            warnings.append("未检测到 PowerShell，无法通过网页手动设置系统时间。")
    else:
        if not _command_path("timedatectl") and not _command_path("chronyc") and not _command_path("ntpq"):
            warnings.append("未检测到 timedatectl / chronyc / ntpq，NTP 状态可能无法准确获取。")
        if not (_command_path("timedatectl") or _command_path("date")):
            warnings.append("未检测到可用时间命令，无法通过网页手动设置系统时间。")
    if config["enabled"] and probe.get("synchronized") is False:
        warnings.append("已启用 NTP，但系统尚未与时间源完成同步；请检查服务器连通性或配置权限。")
    if probe.get("detail") and probe.get("synchronized") is None:
        warnings.append(f"系统时间同步状态未知：{probe['detail'][:200]}")

    capabilities = {
        "manual_set_time": bool(
            (_command_path("powershell") if IS_WINDOWS else (_command_path("timedatectl") or _command_path("date")))
        ),
        "set_timezone": bool(not IS_WINDOWS and _command_path("timedatectl")),
        "enable_ntp": bool(_command_path("w32tm") if IS_WINDOWS else _command_path("timedatectl")),
        "disable_ntp": bool(not IS_WINDOWS and _command_path("timedatectl")),
        "configure_servers": bool(
            _command_path("w32tm") if IS_WINDOWS else (
                _command_path("timedatectl") or _command_path("chronyc")
            )
        ),
        "sync_now": bool(
            _command_path("w32tm") if IS_WINDOWS else (
                _command_path("chronyc") or _command_path("ntpdate") or _command_path("timedatectl")
            )
        ),
    }

    return {
        "platform": platform.system(),
        "platform_label": platform_label,
        "platform_release": platform.release(),
        "hostname": socket.gethostname(),
        "now": local.replace(tzinfo=None).isoformat(timespec="seconds"),
        "now_local": local.isoformat(timespec="seconds"),
        "utc_now": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "timestamp": int(now.timestamp()),
        "timezone": timezone_display,
        "timezone_iana": None if IS_WINDOWS else probe.get("timezone"),
        "utc_offset": _format_offset(offset),
        "utc_offset_seconds": int(offset.total_seconds()),
        "ntp_enabled": bool(config["enabled"]),
        "ntp_servers": config["servers"],
        "ntp_synchronized": probe.get("synchronized"),
        "ntp_service": probe.get("service"),
        "ntp_source": probe.get("source") or "",
        "ntp_detail": (probe.get("detail") or "")[:2000],
        "capabilities": capabilities,
        "warnings": warnings,
        "commands": probe.get("commands") or [],
        "checked_at": local.isoformat(timespec="seconds"),
    }


# ==================== 应用设置 ====================

def _apply_timezone_linux(timezone_name: str) -> List[Dict[str, Any]]:
    return [_run(["timedatectl", "set-timezone", timezone_name])]


def _apply_servers_linux(servers: List[str]) -> List[Dict[str, Any]]:
    """应用 NTP 服务器列表：优先 systemd-timesyncd drop-in，其次 chrony 运行时源"""
    results: List[Dict[str, Any]] = []
    timesyncd_available = _command_path("timedatectl") and (
        Path("/lib/systemd/system/systemd-timesyncd.service").exists()
        or Path("/etc/systemd/timesyncd.conf").exists()
    )
    if timesyncd_available:
        content = "[Time]\nNTP={}\n".format(" ".join(servers)) if servers else ""
        try:
            if content:
                TIMESYNCD_DROPIN.parent.mkdir(parents=True, exist_ok=True)
                TIMESYNCD_DROPIN.write_text(content, encoding="utf-8")
            elif TIMESYNCD_DROPIN.exists():
                TIMESYNCD_DROPIN.unlink()
            results.append({
                "ok": True,
                "code": "ok",
                "command": f"write {TIMESYNCD_DROPIN}",
                "stdout": content.strip(),
                "stderr": "",
            })
        except PermissionError:
            results.append({
                "ok": False,
                "code": "permission",
                "command": f"write {TIMESYNCD_DROPIN}",
                "error": "写入 systemd-timesyncd 配置需要 root 权限",
                "stdout": "",
                "stderr": "",
            })
            return results
        except OSError as exc:
            results.append({
                "ok": False,
                "code": "os_error",
                "command": f"write {TIMESYNCD_DROPIN}",
                "error": f"写入 systemd-timesyncd 配置失败：{exc}",
                "stdout": "",
                "stderr": "",
            })
            return results
        results.append(_run(["systemctl", "restart", "systemd-timesyncd"]))
        return results

    if _command_path("chronyc"):
        for server in servers:
            results.append(_run(["chronyc", "add", "server", server, "iburst"]))
        if results and all(item.get("ok") for item in results):
            results.append(_run(["chronyc", "reload", "sources"]))
        return results

    results.append({
        "ok": False,
        "code": "unsupported",
        "command": "",
        "error": (
            "当前 Linux 系统未检测到 systemd-timesyncd 或 chrony，"
            "NTP 服务器列表已保存但无法通过网页下发；请手工维护 /etc/ntp.conf 或 chrony 配置。"
        ),
        "stdout": "",
        "stderr": "",
    })
    return results


def _windows_config_peers(servers: List[str]) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    if not _command_path("w32tm"):
        results.append({
            "ok": False, "code": "not_found", "command": "w32tm",
            "error": "系统未安装 w32tm，无法配置 Windows 时间同步",
            "stdout": "", "stderr": "",
        })
        return results
    config_args = [
        "w32tm", "/config",
        f"/manualpeerlist:{' '.join(servers)}",
        "/syncfromflags:manual",
        "/update",
    ]
    result = _run(config_args)
    results.append(result)
    if not result.get("ok"):
        # w32time 服务未运行时先尝试启动再配置一次
        if _command_path("net"):
            results.append(_run(["net", "start", "w32time"]))
            results.append(_run(config_args))
    return results


def configure(
    db: Session,
    *,
    ntp_enabled: Optional[bool] = None,
    ntp_servers: Any = None,
    timezone_name: Optional[str] = None,
) -> Dict[str, Any]:
    """保存并应用 NTP / 时区配置

    返回 ok 表示系统命令是否全部成功；配置本身始终先落库，
    失败时通过 results / message 如实告知，绝不伪造成功。
    """
    current = get_ntp_config(db)
    enabled = current["enabled"] if ntp_enabled is None else bool(ntp_enabled)
    servers = current["servers"] if ntp_servers is None else parse_server_list(ntp_servers)
    if enabled and not servers:
        raise ValueError("启用 NTP 自动同步时，至少需要配置一个 NTP 服务器")

    tz = validate_timezone(timezone_name) if str(timezone_name or "").strip() else None

    saved = save_ntp_config(db, enabled=enabled, servers=servers)
    results: List[Dict[str, Any]] = []

    if tz:
        if IS_WINDOWS:
            results.append({
                "ok": False, "code": "unsupported", "command": "tzutil /s",
                "error": (
                    "Windows 下时区请在「设置 → 时间和语言 → 日期和时间」中修改；"
                    "也可通过 tzutil 指定 Windows 时区名称。"
                ),
                "stdout": "", "stderr": "",
            })
        else:
            results.extend(_apply_timezone_linux(tz))

    if IS_WINDOWS:
        if enabled:
            results.extend(_windows_config_peers(servers))
        else:
            results.append({
                "ok": False, "code": "unsupported", "command": "",
                "error": (
                    "Windows 下暂不支持通过网页关闭系统时间同步服务（w32time 由系统策略管理）；"
                    "NTP 服务器配置已保存，可在系统「日期和时间」中关闭自动同步。"
                ),
                "stdout": "", "stderr": "",
            })
    else:
        if _command_path("timedatectl"):
            results.append(_run(["timedatectl", "set-ntp", "true" if enabled else "false"]))
        elif enabled:
            results.append({
                "ok": False, "code": "unsupported", "command": "",
                "error": "未检测到 timedatectl，无法通过网页开启 NTP 自动同步（Chrony/NTPd 请用系统服务管理）",
                "stdout": "", "stderr": "",
            })
        else:
            results.append({
                "ok": False, "code": "unsupported", "command": "",
                "error": "未检测到 timedatectl，无法开关 NTP 同步",
                "stdout": "", "stderr": "",
            })
        if enabled:
            results.extend(_apply_servers_linux(servers))

    failures = [item for item in results if not item.get("ok")]
    ok = not failures
    message = "NTP 设置已保存"
    if ok and tz:
        message = "时区与 NTP 设置已应用"
    elif ok:
        message = "NTP 设置已保存并应用"
    else:
        message = "NTP 设置已保存，但系统命令执行未全部成功：" + "；".join(
            str(item.get("error") or item.get("command") or "未知错误") for item in failures[:3]
        )

    return {
        "ok": ok,
        "saved": saved,
        "applied": ok,
        "message": message,
        "results": results,
        "status": get_status(db),
    }


def sync_now(db: Session) -> Dict[str, Any]:
    """立即同步系统时间（Windows: w32tm /resync；Linux: chronyc makestep / ntpdate / 重启 timesyncd）"""
    config = get_ntp_config(db)
    if not config["enabled"]:
        raise ValueError("请先启用 NTP 自动同步，再执行立即同步")
    servers = config["servers"]
    results: List[Dict[str, Any]] = []

    if IS_WINDOWS:
        if not _command_path("w32tm"):
            results.append({
                "ok": False, "code": "not_found", "command": "w32tm",
                "error": "系统未安装 w32tm，无法立即同步时间",
                "stdout": "", "stderr": "",
            })
        else:
            first = _run(["w32tm", "/resync", "/force"])
            results.append(first)
            if not first.get("ok"):
                if _command_path("net"):
                    results.append(_run(["net", "start", "w32time"]))
                results.append(_run(["w32tm", "/resync", "/force"]))
    else:
        attempted = False
        if _command_path("chronyc"):
            attempted = True
            results.append(_run(["chronyc", "makestep"]))
        if _command_path("ntpdate") and servers:
            attempted = True
            results.append(_run(["ntpdate", "-u", *servers]))
        if not attempted and _command_path("timedatectl"):
            attempted = True
            results.append(_run(["systemctl", "restart", "systemd-timesyncd"]))
        if not attempted:
            results.append({
                "ok": False, "code": "unsupported", "command": "",
                "error": "未检测到 chronyc / ntpdate / timedatectl，无法立即同步时间",
                "stdout": "", "stderr": "",
            })

    ok = any(bool(item.get("ok")) for item in results)
    failures = [item for item in results if not item.get("ok")]
    message = "时间同步已触发，请稍后刷新查看同步状态" if ok else (
        "时间同步失败：" + "；".join(
            str(item.get("error") or item.get("command") or "未知错误") for item in failures[:3]
        )
    )
    return {
        "ok": ok,
        "message": message,
        "results": results,
        "status": get_status(db),
    }


def set_system_time(db: Session, value: Any, timezone_name: Optional[str] = None) -> Dict[str, Any]:
    """手工设置系统时间（仅在用户明确操作时执行）"""
    config = get_ntp_config(db)
    if config["enabled"]:
        raise ValueError("已启用 NTP 自动同步，请先关闭 NTP 再手动设置时间")
    target = parse_local_datetime(value)
    tz = validate_timezone(timezone_name) if str(timezone_name or "").strip() else None
    results: List[Dict[str, Any]] = []

    if tz and not IS_WINDOWS:
        results.extend(_apply_timezone_linux(tz))

    stamp = target.strftime("%Y-%m-%d %H:%M:%S")
    if IS_WINDOWS:
        # 仅在手动设置时间时使用 PowerShell Set-Date
        script = (
            "$ErrorActionPreference='Stop'; "
            f"$d=[datetime]::ParseExact('{target.strftime('%Y-%m-%dT%H:%M:%S')}',"
            "'yyyy-MM-ddTHH:mm:ss',[System.Globalization.CultureInfo]::InvariantCulture); "
            "Set-Date -Date $d; Get-Date -Format 'yyyy-MM-ddTHH:mm:ss'"
        )
        results.append(_run(["powershell", "-NoProfile", "-NonInteractive", "-Command", script]))
    else:
        if _command_path("timedatectl"):
            results.append(_run(["timedatectl", "set-time", stamp]))
            if not results[-1].get("ok"):
                results.append(_run(["date", "-s", stamp]))
        else:
            results.append(_run(["date", "-s", stamp]))

    ok = bool(results) and all(bool(item.get("ok")) for item in results)
    failures = [item for item in results if not item.get("ok")]
    message = f"系统时间已设置为 {stamp}" if ok else (
        "设置系统时间失败：" + "；".join(
            str(item.get("error") or item.get("command") or "未知错误") for item in failures[:3]
        )
    )
    return {
        "ok": ok,
        "requested": stamp,
        "message": message,
        "results": results,
        "status": get_status(db),
    }
