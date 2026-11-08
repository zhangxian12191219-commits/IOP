"""证书监控调度器：定期刷新托管证书状态，并尝试续期临近到期的 ACME 证书。"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict

from sqlalchemy.orm import Session

from ..models.certificate import ManagedCertificate
from . import manager

logger = logging.getLogger(__name__)

REFRESH_INTERVAL_SECONDS = 1800
AUTO_RENEW_DAYS = 15
RENEW_RETRY_SECONDS = 6 * 3600


class CertificateScheduler:
    def __init__(self, db: Session):
        self.db = db
        self.running = False
        self._last_renew: Dict[int, datetime] = {}

    async def start(self):
        self.running = True
        logger.info("证书监控调度器已启动")
        try:
            while self.running:
                try:
                    await self._tick()
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    logger.error("证书监控调度异常: %s", exc)
                    try:
                        self.db.rollback()
                    except Exception:
                        pass
                await asyncio.sleep(REFRESH_INTERVAL_SECONDS)
        finally:
            self.running = False

    async def stop(self):
        self.running = False

    async def _tick(self):
        result = await manager.refresh_all(self.db)
        logger.info("证书监控刷新完成: %s", result)
        records = self.db.query(ManagedCertificate).filter(
            ManagedCertificate.source == "acme",
            ManagedCertificate.auto_renew.is_(True),
        ).all()
        now = datetime.utcnow()
        for record in records:
            if not record.valid_to:
                continue
            days = (record.valid_to - now).days
            if days > AUTO_RENEW_DAYS:
                continue
            last = self._last_renew.get(record.id)
            if last and (now - last).total_seconds() < RENEW_RETRY_SECONDS:
                continue
            self._last_renew[record.id] = now
            try:
                await asyncio.to_thread(manager.renew_acme_certificate, self.db, record)
                logger.info("证书自动续期成功: %s", record.name)
            except Exception as exc:  # noqa: BLE001
                try:
                    record.last_renew_error = str(exc)[:2000]
                    self.db.commit()
                except Exception:
                    self.db.rollback()
                logger.warning("证书自动续期失败 %s: %s", record.name, exc)
