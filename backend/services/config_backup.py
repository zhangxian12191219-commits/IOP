"""网络设备配置备份：SSH 采集、定时调度、记录存储。"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..models.config_backup import ConfigBackup
from ..models.database import SessionLocal
from ..models.models import Device
from ..services import settings as settings_service
from . import config_backup_storage
from . import vendor_commands
from .ssh_compat import open_shell, read_shell_until_idle

logger = logging.getLogger("snmp-monitor.config-backup")

ANSI_RE = re.compile(r"\x1B\[[0-?]*[ -/]*[@-~]")
PROMPT_RE = re.compile(r"(?m)^[^\r\n]{0,80}[>#\$]\s*$")

class ConfigBackupError(RuntimeError):
    pass


# 同一设备不允许并发建 SSH 会话；交换机 VTY 数和分页输出都不适合并发备份。
_DEVICE_LOCKS: Dict[int, threading.Lock] = {}
_DEVICE_LOCKS_GUARD = threading.Lock()
# 全局限流，避免一次点击大量设备时同时占用过多交换机 VTY/CPU。
_MAX_CONCURRENT_BACKUPS = 3
_BACKUP_SLOTS = threading.BoundedSemaphore(_MAX_CONCURRENT_BACKUPS)


def _device_lock(device_id: int) -> threading.Lock:
    with _DEVICE_LOCKS_GUARD:
        return _DEVICE_LOCKS.setdefault(int(device_id), threading.Lock())


def _config_ends_complete(profile_key: str, text: str) -> bool:
    """已知配置类命令必须有完整结尾，防止分页/并发中断时保存半截配置。"""
    if profile_key not in {"huawei", "h3c", "cisco", "ruijie", "hpe", "arista", "zte", "maipu"}:
        return True
    lines = [line.strip().lower() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return False
    return lines[-1] in {"return", "end"} or any(
        line in {"return", "end"} for line in lines[-4:]
    )


def detect_vendor(device: Device) -> str:
    return vendor_commands.detect_vendor(device)


def _clean_config(text: str, command: str) -> str:
    text = ANSI_RE.sub("", text or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"--+\s*More\s*--+", "", text, flags=re.IGNORECASE)
    text = re.sub(r"<---\s*More\s*--->", "", text, flags=re.IGNORECASE)
    lines = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue
        if stripped == command.strip():
            continue
        if PROMPT_RE.match(stripped):
            continue
        if stripped.lower().startswith(("press any key", "---- more ----")):
            continue
        if any(ch in stripped for ch in ("\x07", "\x08")):
            stripped = stripped.replace("\x07", "").replace("\x08", "")
        lines.append(stripped.rstrip())
    cleaned = "\n".join(lines).strip()
    return cleaned + "\n" if cleaned else ""


def _read_until_idle(channel, timeout: int, idle_seconds: float = 0.8) -> str:
    # 交换机 More 分页会自动回车继续，不能只等第一次空闲。
    return read_shell_until_idle(channel, timeout, idle_seconds=idle_seconds)

def _ssh_collect(
    host: str, port: int, username: str, password: str,
    commands: List[str], paging: List[str], timeout: int,
) -> str:
    transport = None
    try:
        transport, channel = open_shell(host, port, username, password, timeout=timeout)
        _read_until_idle(channel, min(timeout, 15), idle_seconds=0.5)
        for item in paging:
            channel.send(item + "\n")
            _read_until_idle(channel, min(timeout, 10), idle_seconds=0.4)
        last_output = ""
        for command in commands:
            channel.send(command + "\n")
            last_output = _read_until_idle(channel, timeout, idle_seconds=1.5)
            cleaned = _clean_config(last_output, command)
            if cleaned and len(cleaned) >= 20:
                return cleaned
        raise ConfigBackupError("SSH 命令未返回有效配置：" + " / ".join(commands))
    except ConfigBackupError:
        raise
    except Exception as exc:  # noqa: BLE001
        text = str(exc)
        if "Incompatible ssh peer" in text or "no acceptable host key" in text.lower():
            text += "（设备 SSH 算法过旧；已尝试兼容 ssh-rsa/group14-sha1，请检查设备 SSH 版本或启用兼容算法）"
        raise ConfigBackupError(f"SSH 连接或读取失败：{text}") from exc
    finally:
        try:
            if transport is not None:
                transport.close()
        except Exception:  # noqa: BLE001
            pass


def collect_device_config(device: Device, timeout: int = 45) -> Dict[str, Any]:
    credential = getattr(device, "credential", None)
    username = (device.backup_username or (credential.username if credential else "") or "").strip()
    password = device.backup_password or (credential.password if credential else "") or ""
    if not username or not password:
        raise ConfigBackupError("未配置 SSH 用户名或密码，也未关联设备凭据")
    profile_key = vendor_commands.detect_vendor(device)
    profile = vendor_commands.PROFILES[profile_key]
    commands = [device.backup_command.strip()] if device.backup_command else list(profile["backup_commands"])
    port = int(device.backup_port or (credential.port if credential else 22) or 22)
    config_command = not device.backup_command or any(
        token in str(commands[0]).lower()
        for token in ("current-configuration", "running-config", "show configuration", "full-configuration")
    )
    text = ""
    for attempt in range(2):
        text = _ssh_collect(
            device.ip_address,
            port,
            username,
            password,
            commands,
            list(profile["paging"]),
            timeout,
        )
        if not config_command or _config_ends_complete(profile_key, text):
            break
        logger.warning("配置备份内容疑似不完整，重试 %s/%s：%s", attempt + 1, 2, device.name)
    if config_command and not _config_ends_complete(profile_key, text):
        raise ConfigBackupError(
            f"配置读取不完整，未检测到结尾 return/end（已重试）；请检查设备分页或并发会话：{device.name}"
        )
    return {
        "config_text": text,
        "command": commands[0],
        "vendor_profile": profile_key,
        "vendor_label": profile["label"],
    }


def _retention_cleanup(db: Session, device_id: int, retention: int, values: Optional[Dict[str, Any]] = None) -> None:
    if retention <= 0:
        return
    rows = (
        db.query(ConfigBackup)
        .filter(ConfigBackup.device_id == device_id)
        .order_by(ConfigBackup.created_at.desc())
        .offset(retention)
        .all()
    )
    for row in rows:
        if row.storage_key and values:
            config_backup_storage.delete(values, row.storage_key)
        db.delete(row)


def perform_backup(db: Session, device_id: int, method: str = "manual", triggered_by: str = "") -> Optional[ConfigBackup]:
    """执行一次配置备份并写入记录；同一设备串行、全局最多并发 3 个。"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        return None
    values = settings_service.get_all(db)
    timeout = max(10, min(180, int(values.get("config_backup_timeout") or 45)))
    retention = max(1, min(200, int(values.get("config_backup_retention_count") or 30)))
    device_lock = _device_lock(device_id)
    lock_timeout = max(15, timeout + 10)
    if not device_lock.acquire(timeout=lock_timeout):
        logger.warning("设备 %s 已有备份任务，本次等待超时", device.name)
        return None
    if not _BACKUP_SLOTS.acquire(timeout=lock_timeout):
        device_lock.release()
        logger.warning("配置备份并发队列已满，跳过设备 %s", device.name)
        return None
    try:
        record = ConfigBackup(
            device_id=device.id,
            status="running",
            method=method,
            triggered_by=str(triggered_by or "")[:100],
            started_at=datetime.utcnow(),
            created_at=datetime.utcnow(),
        )
        db.add(record)
        db.commit()
        db.refresh(record)
        started = time.monotonic()
        try:
            result = collect_device_config(device, timeout=timeout)
            text = result["config_text"]
            record.status = "success"
            record.config_text = text
            record.size_bytes = len(text.encode("utf-8"))
            record.sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
            record.command = result["command"][:200]
            record.vendor_profile = result["vendor_profile"][:50]
            record.error = ""
        except Exception as exc:  # noqa: BLE001
            record.status = "failed"
            record.error = str(exc)[:2000]
        record.finished_at = datetime.utcnow()
        record.duration_ms = int((time.monotonic() - started) * 1000)
        if record.status == "success":
            upload_result = config_backup_storage.upload(values, record, record.config_text or "")
            record.storage_type = str(upload_result.get("type") or "")[:20]
            record.storage_key = str(upload_result.get("key") or "")[:500]
            record.storage_status = str(upload_result.get("status") or "")[:20]
            record.storage_error = str(upload_result.get("error") or "")[:2000]
        db.commit()
        try:
            _retention_cleanup(db, device.id, retention, values)
            db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        db.refresh(record)
        return record
    finally:
        _BACKUP_SLOTS.release()
        device_lock.release()


def backup_due(device: Device, interval_hours: int, db: Session) -> bool:
    last = (
        db.query(ConfigBackup)
        .filter(ConfigBackup.device_id == device.id)
        .order_by(ConfigBackup.created_at.desc())
        .first()
    )
    if not last:
        return True
    interval = int(device.backup_interval_hours or interval_hours or 24)
    return datetime.utcnow() - last.created_at >= timedelta(hours=max(1, interval))


class ConfigBackupScheduler:
    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._stopping = False
        self._running = False
        self.last_run: Optional[str] = None
        self.last_error: str = ""

    async def start(self, shutdown_event=None) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop(shutdown_event))

    async def stop(self) -> None:
        self._stopping = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        self._task = None

    async def _loop(self, shutdown_event=None) -> None:
        await asyncio.sleep(20)
        while not self._stopping:
            try:
                await self._tick()
            except Exception as exc:  # noqa: BLE001
                self.last_error = str(exc)[:300]
                logger.debug("配置备份调度异常: %s", exc)
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break

    async def _tick(self) -> None:
        if self._running:
            return
        self._running = True
        db = SessionLocal()
        try:
            values = settings_service.get_all(db)
            if not values.get("config_backup_enabled"):
                return
            interval = max(1, min(168, int(values.get("config_backup_interval_hours") or 24)))
            concurrency = max(1, min(10, int(values.get("config_backup_concurrency") or 3)))
            devices = (
                db.query(Device)
                .filter(Device.backup_enabled == True)  # noqa: E712
                .filter(
                    Device.is_enabled.is_(True),
                    (Device.credential_id.isnot(None))
                    | (Device.backup_username.isnot(None) & Device.backup_password.isnot(None)),
                )
                .all()
            )
            due = [device for device in devices if backup_due(device, interval, db)]
            if not due:
                return
            semaphore = asyncio.Semaphore(concurrency)

            async def one(device_id: int):
                async with semaphore:
                    session = SessionLocal()
                    try:
                        await asyncio.to_thread(perform_backup, session, device_id, "scheduled", "scheduler")
                    finally:
                        session.close()

            await asyncio.gather(*(one(device.id) for device in due))
            self.last_run = datetime.utcnow().isoformat()
            self.last_error = ""
        finally:
            db.close()
            self._running = False

    def status(self) -> Dict[str, Any]:
        return {
            "running": bool(self._task and not self._task.done()),
            "busy": self._running,
            "last_run": self.last_run,
            "last_error": self.last_error,
        }


scheduler = ConfigBackupScheduler()
