"""网站监控调度器 - 定时执行网站存活检查

特性:
- 按每个目标自己的 check_interval 调度
- 同类告警未确认时不重复产生（避免告警风暴）
- 历史记录按目标保留最近 N 条，防止数据库无限增长
"""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict

from sqlalchemy.orm import Session

from .monitor import WebsiteMonitor
from ..models.website import WebsiteTarget, WebsiteCheckHistory, WebsiteAlert
from ..notify import notify_alert
from ..services.alert_recovery import build_generic_recovery_payload
from ..services import alert_suppression

logger = logging.getLogger(__name__)

HISTORY_KEEP_PER_TARGET = 2000


class WebsiteScheduler:
    """网站监控定时调度器"""

    def __init__(self, db: Session):
        self.db = db
        self.monitor = WebsiteMonitor()
        self.running = False
        self.task: asyncio.Task | None = None
        self._next_check: Dict[int, datetime] = {}

    async def start(self):
        """启动调度（阻塞运行，直到 stop 或异常；由应用层守护任务负责重启）"""
        await self.monitor.start()
        self.running = True
        self.task = asyncio.current_task()
        logger.info("网站监控调度器已启动")
        try:
            await self._run_cycle()
        finally:
            self.running = False

    async def stop(self):
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
        await self.monitor.stop()
        logger.info("网站监控调度器已停止")

    async def _run_cycle(self):
        while self.running:
            try:
                await self._check_due_targets()
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error("网站监控调度异常: %s", exc)
                try:
                    self.db.rollback()
                except Exception:
                    pass
            await asyncio.sleep(5)

    async def _check_due_targets(self):
        targets = self.db.query(WebsiteTarget).filter(
            WebsiteTarget.is_enabled == True
        ).all()
        if not targets:
            return

        now = datetime.utcnow()
        for target in targets:
            interval = target.check_interval or 60
            due = self._next_check.get(target.id)
            if due is not None and now < due:
                continue
            self._next_check[target.id] = now + timedelta(seconds=interval)

            try:
                await self._check_target(target)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.error("检查网站 %s 失败: %s", target.name, exc)
                try:
                    self.db.rollback()
                except Exception:
                    pass

    async def _check_target(self, target: WebsiteTarget):
        result = await self.monitor.check_all(target)
        if not result:
            return

        http_result = result.get("http_result") or {}
        tcp_result = result.get("tcp_result") or {}
        ping_result = result.get("ping_result") or {}
        ip_result = result.get("ip_result") or {}

        is_alive = bool(
            http_result.get("is_alive")
            or tcp_result.get("is_alive")
            or ping_result.get("is_alive")
            or ip_result.get("is_reachable")
        )
        response_time = (
            http_result.get("response_time")
            or tcp_result.get("response_time")
            or ping_result.get("response_time")
            or 0
        )
        # 错误信息只在探测失败时记录，避免 HTTP 正常但 ping 被禁时误导
        error_message = "" if is_alive else (
            http_result.get("http_error")
            or tcp_result.get("error_message")
            or ping_result.get("error_message")
            or ip_result.get("error_message")
            or ""
        )

        record = WebsiteCheckHistory(
            target_id=target.id,
            status_code=http_result.get("status_code"),
            response_time=response_time,
            is_alive=is_alive,
            http_error=http_result.get("http_error"),
            dns_resolve_time=http_result.get("dns_resolve_time"),
            tcp_connect_time=http_result.get("tcp_connect_time"),
            ssl_time=http_result.get("ssl_time"),
            cert_info=http_result.get("cert_info"),
            final_ip=(http_result.get("final_ip")
                      or ping_result.get("final_ip")
                      or ip_result.get("final_ip")),
            content_length=http_result.get("content_length"),
            check_type=target.monitor_type,
            error_message=error_message,
            checked_at=datetime.utcnow(),
        )
        self.db.add(record)

        new_alerts: list = []
        if not is_alive:
            alert = self._raise_alert(
                target,
                alert_type="down",
                level=target.down_level or "critical",
                level_label=target.down_level_label,
                message=f"{target.name} 检测失败: {error_message or '不可达'}",
                details={"http": http_result, "ping": ping_result, "ip": ip_result},
            )
            if alert:
                new_alerts.append(alert)
        elif response_time and response_time > float(target.slow_threshold_ms or 5000):
            alert = self._raise_alert(
                target,
                alert_type="slow",
                level=target.slow_level or "warning",
                level_label=target.slow_level_label,
                message=f"{target.name} 响应缓慢: {response_time:.0f}ms（阈值 {float(target.slow_threshold_ms or 5000):.0f}ms）",
                details={"response_time": response_time, "threshold": target.slow_threshold_ms or 5000},
            )
            if alert:
                new_alerts.append(alert)

        cert_info = http_result.get("cert_info")
        cert_alert = self._raise_cert_alert(target, cert_info)
        if cert_alert:
            new_alerts.append(cert_alert)

        recovered = self._recover_alerts(target, is_alive, response_time, cert_info)
        self.db.commit()
        if recovered:
            logger.info("网站 %s 已恢复，自动关闭告警 %s 条", target.name, len(recovered))
            for recovered_alert in recovered:
                try:
                    notify_alert(build_generic_recovery_payload(
                        source="website",
                        alert_id=recovered_alert.id,
                        name=target.name,
                        ip_address=target.domain or target.ip_address or "",
                        alert_type=recovered_alert.alert_type,
                        message=recovered_alert.message,
                        level=recovered_alert.alert_level,
                        value=recovered_alert.value,
                        threshold=recovered_alert.threshold,
                        recovered_at=recovered_alert.resolved_at,
                        original_created_at=recovered_alert.created_at,
                    ))
                except Exception:  # noqa: BLE001
                    logger.exception("发送网站恢复通知失败: %s", recovered_alert.id)

        # 告警通知（异步，不阻塞探测）
        for alert in new_alerts:
            is_cert_alert = alert.alert_type == "ssl_expired"
            notify_alert({
                "source": "website",
                "source_id": alert.id,
                "level": alert.alert_level,
                "level_label": alert.level_label,
                "device_name": target.name,
                "ip_address": target.domain or target.ip_address or "",
                "alert_type": alert.alert_type,
                "message": alert.message,
                "value": (cert_info or {}).get("days_left") if is_cert_alert else (response_time or None),
                "threshold": (target.cert_expiry_days or 30) if is_cert_alert else (float(target.slow_threshold_ms or 5000) if alert.alert_type == "slow" else None),
                "certificate": cert_info if is_cert_alert else None,
                "created_at": datetime.utcnow().isoformat(timespec="seconds"),
            })

        self._trim_history(target.id)

    def _recover_alerts(self, target: WebsiteTarget, is_alive: bool,
                        response_time, cert_info) -> list:
        """网站恢复后自动关闭未恢复的 down/slow/ssl_expired 告警，并返回关闭的记录。"""
        now = datetime.utcnow()
        recovered_types: list[str] = []
        if is_alive:
            recovered_types.append("down")
        slow_threshold = float(target.slow_threshold_ms or 5000)
        if not is_alive or not response_time or float(response_time) <= slow_threshold:
            recovered_types.append("slow")
        if self._cert_is_healthy(target, cert_info):
            recovered_types.append("ssl_expired")
        if not recovered_types:
            return []
        alerts = self.db.query(WebsiteAlert).filter(
            WebsiteAlert.target_id == target.id,
            WebsiteAlert.alert_type.in_(recovered_types),
            WebsiteAlert.resolved_at.is_(None),
        ).all()
        for alert in alerts:
            alert.is_acknowledged = True
            alert.resolved_at = now
            alert.resolution = "auto_recovered"
        return alerts

    def _cert_is_healthy(self, target: WebsiteTarget, cert_info) -> bool:
        """证书告警可恢复：证书监控关闭，或当前所有证书都高于到期阈值。"""
        if target.cert_monitor_enabled is False:
            return True
        if not isinstance(cert_info, dict):
            return False
        candidates = [cert_info]
        for extra in cert_info.get("extra_certificates") or []:
            if isinstance(extra, dict):
                candidates.append(extra)
        if any(item.get("error") for item in candidates):
            return False
        valid = [item for item in candidates if item.get("days_left") is not None]
        if len(valid) != len(candidates) or not valid:
            return False
        try:
            threshold = int(target.cert_expiry_days if target.cert_expiry_days is not None else 30)
        except (TypeError, ValueError):
            threshold = 30
        try:
            return all(int(item.get("days_left")) > threshold for item in valid)
        except (TypeError, ValueError):
            return False

    def _raise_alert(self, target: WebsiteTarget, alert_type: str,
                     level: str, message: str, details: dict, level_label: str = None):
        """同类未确认告警只保留一条，返回新建的告警对象（已存在则返回 None）"""
        if alert_suppression.is_suppressed(
            self.db, "website", website_target_id=target.id,
            alert_type=alert_type, alert_level=level,
        ):
            return None
        exists = self.db.query(WebsiteAlert).filter(
            WebsiteAlert.target_id == target.id,
            WebsiteAlert.alert_type == alert_type,
            WebsiteAlert.resolved_at.is_(None),
        ).first()
        if exists:
            return None
        alert = WebsiteAlert(
            target_id=target.id,
            alert_type=alert_type,
            alert_level=level,
            level_label=level_label,
            message=message,
            details=details,
            created_at=datetime.utcnow(),
        )
        self.db.add(alert)
        return alert

    def _raise_cert_alert(self, target: WebsiteTarget, cert_info: dict):
        """证书即将到期或已过期时生成 ssl_expired 告警（含根域/子域证书）。"""
        if target.cert_monitor_enabled is False or not isinstance(cert_info, dict):
            return None
        candidates = [cert_info]
        for extra in cert_info.get("extra_certificates") or []:
            if isinstance(extra, dict):
                candidates.append(extra)
        valid = [
            item for item in candidates
            if not item.get("error") and item.get("days_left") is not None
        ]
        if not valid:
            return None
        try:
            threshold = int(target.cert_expiry_days if target.cert_expiry_days is not None else 30)
        except (TypeError, ValueError):
            threshold = 30
        if threshold < 0:
            threshold = 30
        expiring = []
        for item in valid:
            try:
                if int(item.get("days_left")) <= threshold:
                    expiring.append(item)
            except (TypeError, ValueError):
                continue
        if not expiring:
            return None

        primary = min(expiring, key=lambda item: int(item.get("days_left")))
        owner = (
            primary.get("owner")
            or primary.get("subject_organization")
            or primary.get("subject_common_name")
            or primary.get("host")
            or "未知单位"
        )
        valid_to = (primary.get("valid_to") or "")[:10] or "未知"
        days_left = int(primary.get("days_left"))
        expired = bool(primary.get("status") == "expired" or days_left < 0)
        extra_hosts = [
            str(item.get("host") or "").strip()
            for item in expiring
            if str(item.get("host") or "").strip() != str(primary.get("host") or "").strip()
        ]
        extra_text = f"，同时 {len(extra_hosts)} 个根域/子域证书临近到期：{', '.join(extra_hosts[:5])}" if extra_hosts else ""
        if expired:
            level = "critical"
            days_text = f"已过期 {abs(days_left)} 天" if days_left < 0 else "已过期"
            message = f"{target.name} HTTPS 证书{days_text}（所属单位：{owner}，到期时间：{valid_to}）{extra_text}"
        else:
            level = target.cert_alert_level or "warning"
            message = (
                f"{target.name} HTTPS 证书将在 {days_left} 天后到期"
                f"（所属单位：{owner}，到期时间：{valid_to}，告警阈值：{threshold} 天）{extra_text}"
            )
        return self._raise_alert(
            target,
            alert_type="ssl_expired",
            level=level,
            level_label=None,
            message=message,
            details=cert_info,
        )

    def _trim_history(self, target_id: int) -> None:
        """只保留最近 N 条历史"""
        try:
            total = self.db.query(WebsiteCheckHistory).filter(
                WebsiteCheckHistory.target_id == target_id
            ).count()
            if total <= HISTORY_KEEP_PER_TARGET:
                return
            cutoff_row = (
                self.db.query(WebsiteCheckHistory)
                .filter(WebsiteCheckHistory.target_id == target_id)
                .order_by(WebsiteCheckHistory.checked_at.desc())
                .offset(HISTORY_KEEP_PER_TARGET - 1)
                .first()
            )
            if cutoff_row and cutoff_row.checked_at:
                self.db.query(WebsiteCheckHistory).filter(
                    WebsiteCheckHistory.target_id == target_id,
                    WebsiteCheckHistory.checked_at < cutoff_row.checked_at,
                ).delete(synchronize_session=False)
                self.db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.debug("清理历史记录失败: %s", exc)
            self.db.rollback()


# 兼容旧引用
scheduler: WebsiteScheduler | None = None


def get_scheduler() -> WebsiteScheduler | None:
    return scheduler
