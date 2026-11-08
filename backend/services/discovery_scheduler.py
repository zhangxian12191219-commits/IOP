"""定时循环自动发现调度器。

复用自动发现路由的 SNMP 扫描逻辑；按 IP 去重由扫描入库逻辑保证，
自动入库的设备会标记 source=auto。
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..models.database import SessionLocal
from ..models.discovery import DiscoverySchedule
from ..models.models import Device

logger = logging.getLogger(__name__)
_RUN_LOCK = asyncio.Lock()


def get_or_create_schedule(db: Session) -> DiscoverySchedule:
    """兼容旧版单任务接口：返回第一条任务，没有则创建默认任务。"""
    schedule = db.query(DiscoverySchedule).order_by(DiscoverySchedule.id.asc()).first()
    if schedule:
        if not schedule.name:
            schedule.name = "定时扫描"
            db.commit()
        return schedule
    schedule = DiscoverySchedule(name="默认定时扫描")
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    return schedule


def list_schedules(db: Session) -> list[DiscoverySchedule]:
    schedules = db.query(DiscoverySchedule).order_by(DiscoverySchedule.id.asc()).all()
    changed = False
    used = {item.name for item in schedules if item.name}
    for item in schedules:
        if item.name:
            continue
        base = "定时扫描"
        name = base
        suffix = 2
        while name in used:
            name = f"{base} {suffix}"
            suffix += 1
        item.name = name
        used.add(name)
        changed = True
    if changed:
        db.commit()
    return schedules


def get_schedule(db: Session, schedule_id: int) -> Optional[DiscoverySchedule]:
    return db.query(DiscoverySchedule).filter(DiscoverySchedule.id == schedule_id).first()


def schedule_to_dict(schedule: DiscoverySchedule) -> Dict[str, Any]:
    next_run = None
    if schedule.enabled:
        base = schedule.last_run_at or datetime.utcnow()
        next_run = (base + timedelta(minutes=max(1, schedule.interval_minutes or 60))).isoformat()
    return {
        "id": schedule.id,
        "name": schedule.name or "定时扫描",
        "enabled": bool(schedule.enabled),
        "target": schedule.target or "",
        "version": schedule.version or "v2c",
        "community": schedule.community or "",
        "communities": list(schedule.communities or ([schedule.community] if schedule.community else [])),
        "port": schedule.port or 161,
        "timeout": schedule.timeout or 2,
        "concurrency": schedule.concurrency or 32,
        "v3_username": schedule.v3_username or "",
        "v3_security_level": schedule.v3_security_level or "authPriv",
        "v3_auth_protocol": schedule.v3_auth_protocol or "SHA",
        "v3_auth_password": schedule.v3_auth_password or "",
        "v3_priv_protocol": schedule.v3_priv_protocol or "AES",
        "v3_priv_password": schedule.v3_priv_password or "",
        "v3_context_name": schedule.v3_context_name or "",
        "interval_minutes": schedule.interval_minutes or 60,
        "auto_add": bool(schedule.auto_add),
        "last_run_at": schedule.last_run_at.isoformat() if schedule.last_run_at else None,
        "last_status": schedule.last_status or "idle",
        "last_found": schedule.last_found or 0,
        "last_added": schedule.last_added or 0,
        "last_duration_ms": schedule.last_duration_ms or 0,
        "last_message": schedule.last_message or "",
        "next_run_at": next_run,
    }


def backfill_device_sources(db: Session) -> int:
    """旧数据回填：带“自动发现”标签的旧设备标记为自动发现，其余为手动。"""
    updated = 0
    for device in db.query(Device).filter(Device.source.is_(None)).all():
        tags = device.tags or []
        is_auto = any("自动发现" in str(tag) for tag in tags)
        device.source = "auto" if is_auto else "manual"
        if is_auto and not device.discovered_at:
            device.discovered_at = device.created_at
        updated += 1
    if updated:
        db.commit()
    return updated


async def run_schedule_now(db: Session, schedule: Optional[DiscoverySchedule] = None,
                           force: bool = False) -> Dict[str, Any]:
    """执行一次定时扫描。force=True 时忽略 enabled（供“立即执行”使用）。"""
    schedule = schedule or get_or_create_schedule(db)
    if not schedule.enabled and not force:
        return {"ok": False, "message": "定时自动发现未启用"}
    if not (schedule.target or "").strip():
        return {"ok": False, "message": "定时自动发现未配置扫描范围"}

    async with _RUN_LOCK:
        schedule.last_status = "running"
        schedule.last_run_at = datetime.utcnow()
        schedule.last_message = "正在扫描..."
        db.commit()
        started = time.monotonic()
        try:
            # 延迟导入，避免 app/routes 初始化阶段的循环依赖
            from ..routes.discovery import SnmpScanRequest, scan_snmp_communities

            payload = SnmpScanRequest(
                target=schedule.target,
                version=schedule.version or "v2c",
                community=schedule.community or "public",
                port=schedule.port or 161,
                timeout=schedule.timeout or 2,
                concurrency=schedule.concurrency or 32,
                v3_username=schedule.v3_username or None,
                v3_security_level=schedule.v3_security_level or "authPriv",
                v3_auth_protocol=schedule.v3_auth_protocol or "SHA",
                v3_auth_password=schedule.v3_auth_password or None,
                v3_priv_protocol=schedule.v3_priv_protocol or "AES",
                v3_priv_password=schedule.v3_priv_password or None,
                v3_context_name=schedule.v3_context_name or None,
                auto_add=bool(schedule.auto_add),
            )
            communities = list(schedule.communities or [])
            if not communities:
                communities = [schedule.community or "public"]
            result = await scan_snmp_communities(payload, communities, db)
            elapsed = int((time.monotonic() - started) * 1000)
            schedule = get_schedule(db, schedule.id) or get_or_create_schedule(db)
            schedule.last_status = "success"
            schedule.last_found = int(result.get("discovered") or 0)
            schedule.last_added = int(result.get("added") or 0)
            schedule.last_duration_ms = elapsed
            schedule.last_message = (
                f"扫描完成：发现 {schedule.last_found} 台，新增 {schedule.last_added} 台"
            )
            db.commit()
            logger.info("定时自动发现完成[%s]: %s", schedule.name, schedule.last_message)
            return {"ok": True, **schedule_to_dict(schedule)}
        except Exception as exc:  # noqa: BLE001
            elapsed = int((time.monotonic() - started) * 1000)
            try:
                db.rollback()
                schedule = get_schedule(db, schedule.id) or get_or_create_schedule(db)
                schedule.last_status = "failed"
                schedule.last_duration_ms = elapsed
                schedule.last_message = str(exc)[:1000]
                db.commit()
            except Exception:  # noqa: BLE001
                logger.exception("保存定时自动发现失败状态出错")
            logger.exception("定时自动发现失败")
            return {"ok": False, "message": str(exc), "status": "failed"}


class DiscoveryScheduler:
    """后台循环：每 15 秒检查一次是否到期。"""

    def __init__(self, shutdown_event: Optional[asyncio.Event] = None):
        self.shutdown_event = shutdown_event or asyncio.Event()
        self.running = False
        self.task: Optional[asyncio.Task] = None

    async def start(self) -> None:
        self.running = True
        self.task = asyncio.current_task()
        logger.info("定时自动发现调度器已启动")
        try:
            while not self.shutdown_event.is_set():
                try:
                    await self._tick()
                except asyncio.CancelledError:
                    raise
                except Exception:  # noqa: BLE001
                    logger.exception("定时自动发现调度异常")
                try:
                    await asyncio.wait_for(self.shutdown_event.wait(), timeout=15)
                except asyncio.TimeoutError:
                    pass
        finally:
            self.running = False
            logger.info("定时自动发现调度器已停止")

    async def stop(self) -> None:
        self.running = False
        task = self.task
        current = asyncio.current_task()
        if task and task is not current and not task.done():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        self.task = None

    async def _tick(self) -> None:
        db = SessionLocal()
        try:
            schedules = list_schedules(db)
            for schedule in schedules:
                if not schedule.enabled or not (schedule.target or "").strip():
                    continue
                interval = max(1, int(schedule.interval_minutes or 60))
                due = (
                    schedule.last_run_at is None
                    or datetime.utcnow() >= schedule.last_run_at + timedelta(minutes=interval)
                )
                if due:
                    await run_schedule_now(db, schedule)
        finally:
            db.close()
