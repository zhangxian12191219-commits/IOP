"""告警通知分发器

将设备/网站告警按通道配置分发到邮件或 Webhook。
- 通道可设置最低级别（warning / critical）
- 同一告警在同一通道只成功通知一次（避免重复轰炸）
- 发送失败写入通知日志，不影响采集主流程
"""
import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from zoneinfo import ZoneInfo

from ..models.database import SessionLocal
from ..models.notifications import NotificationChannel, NotificationLog
from .channels import level_allows, send_via_channel

logger = logging.getLogger(__name__)

LEVEL_TEXT = {"critical": "严重", "warning": "告警", "info": "提示", "emergency": "紧急"}
ALERT_TYPE_TEXT = {
    "cpu": "CPU使用率",
    "memory": "内存使用率",
    "temperature": "温度",
    "power": "电源状态",
    "offline": "设备离线",
    "down": "探测失败",
    "slow": "响应缓慢",
    "ssl_expired": "证书过期",
    "storage_disk_fault": "存储磁盘故障",
}


def _fmt(value: Any) -> str:
    return "-" if value is None else str(value)


def _event_labels(payload: Dict[str, Any]) -> tuple[str, str, str]:
    """返回事件类型、级别显示文字和标题前缀。

    warning 的级别文字本身就是“告警”，标题里不能再拼一次 [告警]，
    否则会出现 [告警][告警]。
    """
    level = LEVEL_TEXT.get(payload.get("level", "warning"), "告警")
    if payload.get("recovery"):
        return "恢复", level, "[恢复]"
    level_tag = "" if level == "告警" else f"[{level}]"
    return "告警", level, f"[告警]{level_tag}"


def _clean_location(value: Any) -> str:
    """过滤 SNMP 设备位置常见的 unknown/未知 占位值。"""
    text = str(value or "").strip()
    if text.lower() in ("unknown", "none", "null", "-", "未知", "未填写"):
        return ""
    return text


def _location_lines(payload: Dict[str, Any]) -> list[str]:
    """告警正文中的位置信息。

    设备资产里的 location 常被 SNMP sysLocation 写成 "unknown"，外发正文不再
    展示该字段；如配置了机房/机柜或楼层/位置，仍会保留这些可读信息。
    """
    lines = []
    room = _clean_location(payload.get("room_name"))
    cabinet = _clean_location(payload.get("cabinet_name"))
    if room or cabinet:
        lines.append(f"机房 / 机柜：{room or '-'} / {cabinet or '-'}")
    floor = _clean_location(payload.get("room_floor"))
    location = _clean_location(payload.get("room_location"))
    if floor or location:
        lines.append(f"楼层 / 位置：{floor or '-'} / {location or '-'}")
    return lines


def _local_time_text(value: Any, with_seconds: bool = True) -> str:
    """把数据库中的 UTC 时间转换为外发通知使用的本地时间。"""
    if not value:
        dt = datetime.now(timezone.utc)
    else:
        try:
            if isinstance(value, datetime):
                dt = value
            else:
                text = str(value).strip()
                if text.endswith("Z"):
                    text = text[:-1] + "+00:00"
                dt = datetime.fromisoformat(text)
        except (TypeError, ValueError):
            text = str(value or "").strip()
            return text or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    zone_name = os.getenv("ALERT_TIMEZONE", "Asia/Shanghai").strip() or "Asia/Shanghai"
    try:
        local_dt = dt.astimezone(ZoneInfo(zone_name))
    except Exception:  # noqa: BLE001
        local_dt = dt.astimezone()
    return local_dt.strftime("%Y-%m-%d %H:%M:%S" if with_seconds else "%m-%d %H:%M")


def build_message(payload: Dict[str, Any], compact: bool = False) -> tuple[str, str]:
    """生成通知标题与正文

    :param compact: True 时生成适合短信的精简文案（单条 70 字内优先）
    """
    level = LEVEL_TEXT.get(payload.get("level", "warning"), "告警")
    atype = ALERT_TYPE_TEXT.get(payload.get("alert_type") or "", payload.get("alert_type") or "告警")
    name = payload.get("device_name") or payload.get("ip_address") or "设备"
    is_recovery = bool(payload.get("recovery"))
    event_type, level_text, title_prefix = _event_labels(payload)

    source = payload.get("source") or "device"
    source_text = {
        "website": "网站监控",
        "virtualization": "虚拟化告警",
        "device": "设备告警",
    }.get(source, "告警")

    if is_recovery:
        recovered_at = _local_time_text(payload.get("recovered_at") or datetime.now(timezone.utc))
        if compact:
            text = f"事件类型：恢复；{name} {atype} 当前值 {_fmt(payload.get('value'))}，原阈值 {_fmt(payload.get('threshold'))}"
            if len(text) > 120:
                text = text[:118] + "…"
            return f"【恢复】{name}", text
        title = f"[恢复] {source_text}恢复 - {name}"
        lines = [
            f"事件类型：恢复",
            f"告警对象：{name}",
            f"对象地址：{_fmt(payload.get('ip_address'))}",
            *_location_lines(payload),
            f"告警类型：{atype}",
            f"当前值：{_fmt(payload.get('value'))}    原阈值：{_fmt(payload.get('threshold'))}",
            f"恢复时间：{recovered_at}",
            f"原告警：{payload.get('message') or '-'}",
        ]
        return title, "\n".join(lines)

    if compact:
        # 短信示例: 【告警】[北京节点] 核心交换机-01 CPU使用率 88% 超过阈值 80% (10:23)
        when = _local_time_text(payload.get("created_at") or datetime.now(timezone.utc), with_seconds=False)
        raw = payload.get("message") or atype
        node_prefix = ""
        if payload.get("source") == "upstream":
            node_prefix = f"[{payload.get('source_node_name') or payload.get('source_node_id') or '上级节点'}] "
        title = f"【告警】{name}"
        level_suffix = "" if level == "告警" else f"[{level}]"
        text = f"事件类型：告警；{level_suffix}{node_prefix}{name} {raw} ({when})"
        if len(text) > 120:
            text = text[:118] + "…"
        return title, text

    if payload.get("source") == "upstream":
        node_name = payload.get("source_node_name") or payload.get("source_node_id") or "未知节点"
        node_id = payload.get("source_node_id") or "-"
        origin = payload.get("origin_source") or "device"
        origin_text = "网站监控" if origin == "website" else "设备告警"
        title = f"{title_prefix} {node_name} · {atype}"
        lines = [
            f"事件类型：告警",
            f"告警级别：{level_text}",
            f"来源节点：{node_name}",
            f"节点标识：{node_id}",
            f"原始来源：{origin_text}",
            f"告警对象：{name}",
            f"对象地址：{_fmt(payload.get('ip_address'))}",
            *_location_lines(payload),
            f"告警类型：{atype}",
            f"当前值：{_fmt(payload.get('value'))}    阈值：{_fmt(payload.get('threshold'))}",
            f"告警原文：{payload.get('message') or '-'}",
            f"发生时间：{_local_time_text(payload.get('created_at') or datetime.now(timezone.utc))}",
            f"来源地址：{payload.get('source_url') or '-'}",
        ]
    elif payload.get("source") == "virtualization":
        title = f"{title_prefix} 虚拟化告警 - {name}"
        lines = [
            f"事件类型：告警",
            f"告警级别：{level_text}",
            f"告警对象：{name}",
            f"告警类型：{atype}",
            f"当前值：{_fmt(payload.get('value'))}    阈值：{_fmt(payload.get('threshold'))}",
            f"告警原文：{payload.get('message') or '-'}",
            f"发生时间：{_local_time_text(payload.get('created_at') or datetime.now(timezone.utc))}",
        ]
    elif payload.get("source") == "website":
        title = f"{title_prefix} 网站监控告警 - {name}"
        lines = [
            f"事件类型：告警",
            f"告警级别：{level_text}",
            f"监控对象：{name}",
            f"告警类型：{atype}",
            f"告警原文：{payload.get('message') or '-'}",
            f"发生时间：{_local_time_text(payload.get('created_at') or datetime.now(timezone.utc))}",
        ]
    else:
        title = f"{title_prefix} 设备告警 - {name}"
        lines = [
            f"事件类型：告警",
            f"告警级别：{level_text}",
            f"设备名称：{name}",
            f"设备地址：{_fmt(payload.get('ip_address'))}",
            *_location_lines(payload),
            f"告警类型：{atype}",
            f"当前值：{_fmt(payload.get('value'))}    阈值：{_fmt(payload.get('threshold'))}",
            f"告警原文：{payload.get('message') or '-'}",
            f"发生时间：{_local_time_text(payload.get('created_at') or datetime.now(timezone.utc))}",
        ]

    return title, "\n".join(lines)


async def dispatch(payload: Dict[str, Any], exclude_channel_types: Optional[set] = None) -> List[Dict[str, Any]]:
    """执行一次分发，返回每个通道的结果"""
    results: List[Dict[str, Any]] = []
    db = SessionLocal()
    try:
        channels = (
            db.query(NotificationChannel)
            .filter(NotificationChannel.enabled == True)  # noqa: E712
            .all()
        )
        if not channels:
            return results

        source = payload.get("source") or "device"
        source_id = payload.get("source_id")
        selected_channel_ids = payload.get("channel_ids")
        if selected_channel_ids is not None:
            selected = {int(item) for item in selected_channel_ids if str(item).lstrip("-").isdigit()}
            channels = [channel for channel in channels if channel.id in selected]

        for channel in channels:
            if exclude_channel_types and channel.channel_type in exclude_channel_types:
                continue
            if not level_allows(payload.get("level", "warning"), channel.min_level):
                continue

            # 短信使用精简文案，邮件/Webhook 使用完整文案
            if channel.channel_type == "sms":
                title, text = build_message(payload, compact=True)
            else:
                title, text = build_message(payload)

            # 去重：同告警同通道已成功发送则跳过
            if source_id is not None:
                dup = (
                    db.query(NotificationLog)
                    .filter(
                        NotificationLog.channel_id == channel.id,
                        NotificationLog.source == source,
                        NotificationLog.source_id == source_id,
                        NotificationLog.status == "success",
                    )
                    .first()
                )
                if dup:
                    continue

            status, error = "success", None
            try:
                await send_via_channel(channel, title, text, payload, db=db)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                status, error = "failed", str(exc)[:1000]
                logger.warning("通知通道 %s 发送失败: %s", channel.name, exc)

            db.add(NotificationLog(
                channel_id=channel.id,
                channel_name=channel.name,
                channel_type=channel.channel_type,
                source=source,
                source_id=source_id,
                title=title,
                message=text,
                status=status,
                error=error,
                created_at=datetime.utcnow(),
            ))
            try:
                db.commit()
            except Exception as exc:  # noqa: BLE001
                logger.error("写入通知日志失败: %s", exc)
                db.rollback()

            results.append({"channel": channel.name, "status": status, "error": error})
        return results
    finally:
        db.close()


def notify_alert(payload: Dict[str, Any]) -> Optional[asyncio.Task]:
    """在事件循环中异步分发（不阻塞采集流程）"""
    if not payload:
        return None
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.debug("无运行中的事件循环，跳过通知")
        return None

    async def _run():
        try:
            await dispatch(payload)
        except Exception as exc:  # noqa: BLE001
            logger.error("告警通知分发异常: %s", exc)

    return loop.create_task(_run())


def notify_alert_sync(payload: Dict[str, Any]) -> None:
    """同步场景（如告警列表对账）发送恢复通知；有事件循环时仍异步执行。"""
    if not payload:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and loop.is_running():
        notify_alert(payload)
        return
    try:
        asyncio.run(dispatch(payload))
    except Exception as exc:  # noqa: BLE001
        logger.error("同步告警通知分发异常: %s", exc)
