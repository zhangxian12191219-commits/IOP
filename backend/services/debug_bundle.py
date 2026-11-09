"""Debug 诊断包：收集脱敏后的运行信息，供用户反馈问题。"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import socket
import subprocess
import sys
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List

from sqlalchemy.orm import Session

from ..config import Config, PROJECT_ROOT

DEBUG_DIR = Path(Config.LOG_DIR).parent / "debug"
RETENTION = 20
_LOG_LIMIT_BYTES = 512 * 1024
_LOG_LIMIT_LINES = 4000
_PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----[\s\S]{40,}?-----END [A-Z0-9 ]*PRIVATE KEY-----"
)
_JWT_RE = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
_SECRET_VALUE_RE = re.compile(
    r"(?i)\b(password|passwd|pwd|secret|token|api[_-]?key|apikey|"
    r"community|license[_-]?key|private[_-]?key|access[_-]?key|authorization)\b"
    r"(\s*[:=]\s*)([\"']?)([^\"'\s,;}]+)"
)
_URL_AUTH_RE = re.compile(r"([a-z][a-z0-9+.-]*://[^/\s:@]+:)([^@\s/]+)(@)", re.IGNORECASE)
_SECRET_KEYS = (
    "password", "passwd", "pwd", "secret", "token", "api_key", "apikey",
    "community", "license_key", "private_key", "credential", "authorization",
    "cookie", "access_key", "integration_password", "redis_url",
)


def redact_text(value: str) -> str:
    """对日志和诊断文本做通用脱敏。"""
    text = str(value or "")
    text = _PRIVATE_KEY_RE.sub("<redacted-private-key>", text)
    text = _JWT_RE.sub("<redacted-jwt>", text)
    text = _SECRET_VALUE_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}<redacted>", text)
    text = _URL_AUTH_RE.sub(r"\1<redacted>\3", text)
    return text


def _redact_value(value: Any, key: str = "") -> Any:
    lower = str(key).lower()
    if any(part in lower for part in _SECRET_KEYS):
        return "<redacted>"
    if isinstance(value, dict):
        return {str(k): _redact_value(v, str(k)) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, str):
        return redact_text(value)
    return value


def _version() -> str:
    try:
        data = json.loads((PROJECT_ROOT / "backend" / "version.json").read_text(encoding="utf-8"))
        return str(data.get("version") or "")
    except (OSError, ValueError):
        return ""


def _run_fixed(command: List[str], timeout: int = 8) -> str:
    """只执行固定诊断命令，不接收用户参数。"""
    try:
        proc = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        output = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        return redact_text(output.strip())[:256 * 1024]
    except (OSError, subprocess.SubprocessError) as exc:
        return f"[命令不可用] {' '.join(command)}: {exc}"


def _system_info() -> str:
    lines = [
        f"generated_at: {datetime.now(timezone.utc).isoformat()}",
        f"app_version: {_version()}",
        f"platform: {platform.platform()}",
        f"system: {platform.system()} {platform.release()}",
        f"machine: {platform.machine()}",
        f"processor: {platform.processor()}",
        f"python: {sys.version}",
        f"hostname: {socket.gethostname()}",
        f"app_root: {PROJECT_ROOT}",
        f"log_dir: {Config.LOG_DIR}",
        f"pid: {os.getpid()}",
    ]
    try:
        usage = shutil.disk_usage(PROJECT_ROOT)
        lines.append(f"disk_root: total={usage.total} used={usage.used} free={usage.free}")
    except OSError:
        pass
    try:
        load = os.getloadavg()
        lines.append(f"loadavg: {load}")
    except (AttributeError, OSError):
        pass
    return "\n".join(lines)


def _network_info() -> str:
    system = platform.system().lower()
    commands: List[tuple[str, List[str]]] = []
    if system == "windows":
        commands = [
            ("ipconfig", ["ipconfig", "/all"]),
            ("route", ["route", "print"]),
            ("netstat", ["netstat", "-ano"]),
        ]
    else:
        commands = [
            ("ip-address", ["ip", "-brief", "addr"]),
            ("ip-route", ["ip", "route"]),
            ("listeners", ["ss", "-lnt"]),
        ]
    blocks = []
    for title, command in commands:
        blocks.append(f"===== {title} =====\n{_run_fixed(command)}")
    return "\n\n".join(blocks)


def _tail_log(path: Path) -> str:
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - _LOG_LIMIT_BYTES))
            data = handle.read()
    except OSError:
        return ""
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()[-_LOG_LIMIT_LINES:]
    return redact_text("\n".join(lines))


def _log_files() -> List[Path]:
    log_dir = Path(Config.LOG_DIR)
    if not log_dir.is_dir():
        return []
    result = []
    for path in sorted(log_dir.glob("*.log*"), key=lambda p: p.stat().st_mtime, reverse=True):
        if path.is_file():
            result.append(path)
        if len(result) >= 8:
            break
    return result


def _journal_text() -> str:
    if platform.system().lower() != "linux" or not shutil.which("journalctl"):
        return "[当前平台不使用 journalctl]"
    return _run_fixed(["journalctl", "-u", "snmp-nms", "-n", "1500", "--no-pager", "-o", "short-iso"], timeout=10)


def _database_counts(db: Session) -> Dict[str, Any]:
    from ..models.models import Alert, Device, DeviceMetric
    from ..models.user import Role, User
    from ..models.website import WebsiteTarget

    result: Dict[str, Any] = {}
    for name, model in (
        ("devices", Device), ("alerts", Alert), ("metrics", DeviceMetric),
        ("users", User), ("roles", Role), ("websites", WebsiteTarget),
    ):
        try:
            result[name] = int(db.query(model).count())
        except Exception as exc:  # noqa: BLE001
            result[name] = f"error: {exc}"
    return result


def _settings_snapshot(db: Session) -> Dict[str, Any]:
    from . import settings as settings_service

    try:
        return _redact_value(settings_service.get_all(db))
    except Exception as exc:  # noqa: BLE001
        return {"error": str(exc)}


def _write_manifest(zf: zipfile.ZipFile, entries: Dict[str, bytes]) -> None:
    manifest = {}
    for name, data in entries.items():
        manifest[name] = {
            "size": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }
    raw = json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8")
    zf.writestr("manifest.json", raw)


def create_bundle(db: Session, note: str = "") -> Dict[str, Any]:
    """生成脱敏 Debug 诊断 ZIP，返回下载信息。"""
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"debug-{stamp}-{uuid.uuid4().hex[:6]}.zip"
    path = DEBUG_DIR / name
    note = redact_text((note or "").strip()[:1000])

    entries: Dict[str, bytes] = {}
    entries["README.txt"] = (
        "IOP Debug 诊断包\n"
        "================\n\n"
        "本文件由系统配置 → 网络配置 → Debug 日志收集生成。\n"
        "已对密码、Token、API Key、私钥、授权文件和数据库内容做脱敏/排除。\n"
        "请把本 ZIP 发给技术支持，并附上问题发生时间和现象描述。\n"
    ).encode("utf-8")
    entries["summary.txt"] = (
        f"版本: {_version()}\n"
        f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        f"问题描述: {note or '未填写'}\n"
    ).encode("utf-8")
    entries["system-info.txt"] = _system_info().encode("utf-8")
    entries["network.txt"] = _network_info().encode("utf-8")
    entries["journal.txt"] = _journal_text().encode("utf-8")
    entries["config.json"] = json.dumps(
        _settings_snapshot(db), ensure_ascii=False, indent=2
    ).encode("utf-8")
    entries["database.json"] = json.dumps(
        _database_counts(db), ensure_ascii=False, indent=2
    ).encode("utf-8")
    entries["metadata.json"] = json.dumps({
        "version": _version(),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "note": note,
        "platform": platform.platform(),
        "python": sys.version,
        "log_files": [p.name for p in _log_files()],
    }, ensure_ascii=False, indent=2).encode("utf-8")

    for log_path in _log_files():
        content = _tail_log(log_path)
        if content:
            entries[f"logs/{log_path.name}"] = content.encode("utf-8")

    errors = []
    for key, data in entries.items():
        if key.startswith("logs/"):
            for line in data.decode("utf-8", errors="replace").splitlines():
                if re.search(r"\b(ERROR|CRITICAL|Traceback|Exception)\b", line):
                    errors.append(f"[{key}] {line}")
    entries["recent-errors.txt"] = ("\n".join(errors[-1000:]) or "未发现明显的 ERROR/Traceback").encode("utf-8")

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for entry_name, data in sorted(entries.items()):
            zf.writestr(entry_name, data)
        _write_manifest(zf, entries)

    for old in sorted(DEBUG_DIR.glob("debug-*.zip"), key=lambda p: p.stat().st_mtime, reverse=True)[RETENTION:]:
        try:
            old.unlink()
        except OSError:
            pass

    return {
        "name": name,
        "size": path.stat().st_size,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "download_url": f"/api/system/debug/{name}/download",
    }
