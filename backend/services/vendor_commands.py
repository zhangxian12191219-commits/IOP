"""厂商适配的配置备份与巡检命令库。

配置备份和巡检共用一套厂商识别，避免两处命令不一致。
设备自身配置的 backup_command 优先于内置配置备份命令。
"""
from __future__ import annotations

import re
import time
from typing import Any, Dict, List

from .ssh_compat import open_shell, read_shell_until_idle

PROFILES: Dict[str, Dict[str, Any]] = {
    "huawei": {
        "label": "华为",
        "paging": ["screen-length 0 temporary"],
        "backup_commands": ["display current-configuration"],
        "inspection": [
            ("config", "系统配置", "display current-configuration"),
            ("status", "系统运行状态", "display version"),
            ("cpu", "CPU 使用率", "display cpu-usage"),
            ("memory", "内存使用率", "display memory-usage"),
            ("log", "日志异常", "display logbuffer"),
        ],
    },
    "h3c": {
        "label": "华三 H3C",
        "paging": ["screen-length 0 temporary"],
        "backup_commands": ["display current-configuration"],
        "inspection": [
            ("config", "系统配置", "display current-configuration"),
            ("status", "系统运行状态", "display version"),
            ("cpu", "CPU 使用率", "display cpu-usage"),
            ("memory", "内存使用率", "display memory"),
            ("log", "日志异常", "display logbuffer"),
        ],
    },
    "ruijie": {
        "label": "锐捷",
        "paging": ["terminal length 0"],
        "backup_commands": ["show running-config"],
        "inspection": [
            ("config", "系统配置", "show running-config"),
            ("status", "系统运行状态", "show version"),
            ("cpu", "CPU 使用率", "show cpu"),
            ("memory", "内存使用率", "show memory"),
            ("log", "日志异常", "show logging"),
        ],
    },
    "sangfor": {
        "label": "深信服",
        "paging": ["terminal length 0"],
        "backup_commands": ["show configuration"],
        "inspection": [
            ("config", "系统配置", "show configuration"),
            ("status", "系统运行状态", "show system"),
            ("cpu", "CPU 使用率", "show cpu"),
            ("memory", "内存使用率", "show memory"),
            ("log", "日志异常", "show log"),
        ],
    },
    "hillstone": {
        "label": "山石 Hillstone",
        "paging": ["terminal length 0"],
        "backup_commands": ["show configuration"],
        "inspection": [
            ("config", "系统配置", "show configuration"),
            ("status", "系统运行状态", "show system"),
            ("cpu", "CPU 使用率", "show cpu"),
            ("memory", "内存使用率", "show memory"),
            ("log", "日志异常", "show log"),
        ],
    },
    "fortinet": {
        "label": "飞塔 Fortinet",
        "paging": ["config system console", "set output standard", "end"],
        "backup_commands": ["show full-configuration"],
        "inspection": [
            ("config", "系统配置", "show full-configuration"),
            ("status", "系统运行状态", "get system status"),
            ("cpu", "CPU 使用率", "get system performance status"),
            ("memory", "内存使用率", "get system performance status"),
            ("log", "日志异常", "get log memory"),
        ],
    },
    "cisco": {
        "label": "Cisco",
        "paging": ["terminal length 0"],
        "backup_commands": ["show running-config"],
        "inspection": [
            ("config", "系统配置", "show running-config"),
            ("status", "系统运行状态", "show version"),
            ("cpu", "CPU 使用率", "show processes cpu"),
            ("memory", "内存使用率", "show processes memory"),
            ("log", "日志异常", "show logging"),
        ],
    },
    "juniper": {
        "label": "Juniper",
        "paging": ["set cli screen-length 0"],
        "backup_commands": ["show configuration | display set"],
        "inspection": [
            ("config", "系统配置", "show configuration | display set"),
            ("status", "系统运行状态", "show version"),
            ("cpu", "CPU 使用率", "show chassis routing-engine"),
            ("memory", "内存使用率", "show system processes extensive"),
            ("log", "日志异常", "show log messages"),
        ],
    },
    "arista": {
        "label": "Arista",
        "paging": ["terminal length 0"],
        "backup_commands": ["show running-config"],
        "inspection": [
            ("config", "系统配置", "show running-config"),
            ("status", "系统运行状态", "show version"),
            ("cpu", "CPU 使用率", "show processes top"),
            ("memory", "内存使用率", "show processes top"),
            ("log", "日志异常", "show logging"),
        ],
    },
    "f5": {
        "label": "F5 BIG-IP",
        "paging": [],
        "backup_commands": ["show running-config"],
        "inspection": [
            ("config", "系统配置", "show running-config"),
            ("status", "系统运行状态", "show sys version"),
            ("cpu", "CPU 使用率", "show sys performance"),
            ("memory", "内存使用率", "show sys performance"),
            ("log", "日志异常", "show sys log"),
        ],
    },
    "hpe": {
        "label": "HPE / Aruba",
        "paging": ["terminal length 0"],
        "backup_commands": ["show running-config"],
        "inspection": [
            ("config", "系统配置", "show running-config"),
            ("status", "系统运行状态", "show version"),
            ("cpu", "CPU 使用率", "show cpu"),
            ("memory", "内存使用率", "show memory"),
            ("log", "日志异常", "show logging"),
        ],
    },
    "mikrotik": {
        "label": "MikroTik",
        "paging": [],
        "backup_commands": ["/export"],
        "inspection": [
            ("config", "系统配置", "/export"),
            ("status", "系统运行状态", "/system resource print"),
            ("cpu", "CPU 使用率", "/system resource print"),
            ("memory", "内存使用率", "/system resource print"),
            ("log", "日志异常", "/log print"),
        ],
    },
    "zte": {
        "label": "中兴 ZTE",
        "paging": ["terminal length 0"],
        "backup_commands": ["show running-config"],
        "inspection": [
            ("config", "系统配置", "show running-config"),
            ("status", "系统运行状态", "show version"),
            ("cpu", "CPU 使用率", "show cpu"),
            ("memory", "内存使用率", "show memory"),
            ("log", "日志异常", "show logging"),
        ],
    },
    "maipu": {
        "label": "迈普 Maipu",
        "paging": ["terminal length 0"],
        "backup_commands": ["show running-config"],
        "inspection": [
            ("config", "系统配置", "show running-config"),
            ("status", "系统运行状态", "show version"),
            ("cpu", "CPU 使用率", "show cpu"),
            ("memory", "内存使用率", "show memory"),
            ("log", "日志异常", "show logging"),
        ],
    },
    "generic": {
        "label": "通用网络设备",
        "paging": ["terminal length 0"],
        "backup_commands": ["show running-config", "display current-configuration"],
        "inspection": [
            ("config", "系统配置", "show running-config"),
            ("status", "系统运行状态", "show version"),
            ("cpu", "CPU 使用率", "show cpu"),
            ("memory", "内存使用率", "show memory"),
            ("log", "日志异常", "show logging"),
        ],
    },
}

_DETECT_RULES = [
    ("huawei", ("huawei", "华为", "vrp")),
    ("h3c", ("h3c", "华三", "新华三", "comware")),
    ("ruijie", ("ruijie", "锐捷", "rg-os")),
    ("sangfor", ("sangfor", "深信服")),
    ("hillstone", ("hillstone", "山石", "stoneos")),
    ("fortinet", ("fortinet", "fortigate", "飞塔")),
    ("cisco", ("cisco", "思科", "ios xe", "nx-os")),
    ("juniper", ("juniper", "瞻博", "junos")),
    ("arista", ("arista",)),
    ("f5", ("f5", "big-ip", "bigip")),
    ("hpe", ("hpe", "aruba", "hp ", "hewlett")),
    ("mikrotik", ("mikrotik", "routeros")),
    ("zte", ("zte", "中兴")),
    ("maipu", ("maipu", "迈普")),
]


def detect_vendor(device: Any) -> str:
    text = f"{getattr(device, 'vendor', '') or ''} {getattr(device, 'model', '') or ''} {getattr(device, 'name', '') or ''}".lower()
    for key, tokens in _DETECT_RULES:
        if any(token in text for token in tokens):
            return key
    return "generic"


def match_vendor_text(text: str) -> str | None:
    """按用户输入的厂商文本匹配；未识别返回 None（用于要求手工命令）。"""
    value = str(text or "").strip().lower()
    if not value:
        return None
    for key, tokens in _DETECT_RULES:
        if any(token in value for token in tokens):
            return key
    if value in ("generic", "通用", "其他"):
        return "generic"
    return None


def profile_for_vendor(vendor: str) -> Dict[str, Any] | None:
    key = match_vendor_text(vendor)
    return PROFILES.get(key) if key else None


def get_profile(device: Any) -> Dict[str, Any]:
    return PROFILES[detect_vendor(device)]


def backup_commands(device: Any) -> List[str]:
    return list(get_profile(device)["backup_commands"])


def inspection_plan(device: Any) -> List[Dict[str, str]]:
    profile = get_profile(device)
    return [
        {"key": key, "label": label, "command": command}
        for key, label, command in profile["inspection"]
    ]


def profile_summary(device: Any) -> Dict[str, Any]:
    key = detect_vendor(device)
    profile = PROFILES[key]
    return {
        "profile": key,
        "label": profile["label"],
        "backup_commands": list(profile["backup_commands"]),
        "inspection_commands": inspection_plan(device),
    }


_ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
_PROMPT_RE = re.compile(r"(?m)^[^\r\n]{0,80}[>#\$]\s*$")
_LOG_ERROR_RE = re.compile(
    r"\b(error|failed|failure|critical|panic|exception|denied|unreachable|timeout|down|fault|corrupt)\b",
    re.IGNORECASE,
)


def _read_until_idle(channel, timeout: int, idle_seconds: float = 0.6) -> str:
    return read_shell_until_idle(channel, timeout, idle_seconds=idle_seconds)

def _clean_output(text: str, command: str) -> str:
    text = _ANSI_RE.sub("", text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"--+\s*More\s*--+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<---\s*More\s*--->", "", text, flags=re.IGNORECASE)
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped == command.strip() or _PROMPT_RE.match(stripped):
            continue
        if stripped.lower().startswith(("press any key", "---- more ----")):
            continue
        lines.append(stripped)
    return "\n".join(lines).strip()


def _log_findings(output: str) -> List[Dict[str, str]]:
    findings = []
    for line in (output or "").splitlines():
        if len(line) > 240:
            line = line[:240] + "…"
        if _LOG_ERROR_RE.search(line):
            findings.append({"line": line})
        if len(findings) >= 10:
            break
    return findings


def run_inspection_commands(device: Any, timeout: int = 8) -> Dict[str, Any]:
    """使用设备备份 SSH 凭据执行厂商巡检命令；未配置凭据时只返回计划。

    不修改设备，不执行配置命令；只读取配置/状态/CPU/内存/日志。
    """
    plan = inspection_plan(device)
    credential = getattr(device, "credential", None)
    username = str(getattr(device, "backup_username", "") or (credential.username if credential else "") or "").strip()
    password = getattr(device, "backup_password", "") or (credential.password if credential else "") or ""
    result: Dict[str, Any] = {
        "profile": detect_vendor(device),
        "profile_label": get_profile(device)["label"],
        "status": "skipped",
        "error": "",
        "commands": [
            {"key": item["key"], "label": item["label"], "command": item["command"],
             "ok": False, "summary": "", "output": ""}
            for item in plan
        ],
        "log_findings": [],
    }
    if not username or not password:
        result["error"] = "未配置设备备份 SSH 用户名或密码，已生成巡检命令计划但未执行"
        return result
    transport = None
    try:
        transport, channel = open_shell(
            str(getattr(device, "ip_address", "") or ""),
            int(getattr(device, "backup_port", None) or (credential.port if credential else 22) or 22),
            username,
            password,
            timeout=timeout,
        )
        _read_until_idle(channel, min(timeout, 8), idle_seconds=0.4)
        for item in get_profile(device)["paging"]:
            channel.send(item + "\n")
            _read_until_idle(channel, min(timeout, 8), idle_seconds=0.3)
        for command_result, item in zip(result["commands"], plan):
            channel.send(item["command"] + "\n")
            raw = _read_until_idle(channel, timeout)
            output = _clean_output(raw, item["command"])
            command_result["ok"] = bool(output)
            command_result["output"] = output[:6000]
            command_result["summary"] = (
                f"返回 {len(output.splitlines())} 行"
                if output else "无返回内容"
            )
            if item["key"] == "log":
                result["log_findings"] = _log_findings(output)
        result["status"] = "success"
    except Exception as exc:  # noqa: BLE001
        result["status"] = "failed"
        text = str(exc)
        if "Incompatible ssh peer" in text or "no acceptable host key" in text.lower():
            text += "（设备 SSH 算法过旧；已尝试兼容 ssh-rsa/group14-sha1）"
        result["error"] = text[:500]
    finally:
        try:
            if transport is not None:
                transport.close()
        except Exception:  # noqa: BLE001
            pass
    return result
