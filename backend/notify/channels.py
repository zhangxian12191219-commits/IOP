"""通知发送器 - 邮件(SMTP) / Webhook / 短信"""
import asyncio
import hashlib
import json
import logging
import smtplib
import ssl
from datetime import datetime
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr, formatdate
from typing import Any, Dict, List

import aiohttp

from ..config import Config
from ..models.user import User
from .sms import SmsError, send_sms

logger = logging.getLogger(__name__)

LEVEL_RANK = {"info": 0, "warning": 1, "critical": 2, "emergency": 3}


def resolve_sms_contacts(config: Dict[str, Any], db=None) -> Dict[str, Any]:
    """解析短信联系人；关联用户优先使用用户表中的最新姓名/手机号。"""
    cfg = dict(config or {})
    contacts = cfg.get("contacts")
    if not isinstance(contacts, list):
        return cfg
    resolved = []
    for raw in contacts:
        if not isinstance(raw, dict):
            continue
        contact = dict(raw)
        user_id = contact.get("user_id")
        if user_id and db is not None:
            try:
                user = db.query(User).filter(User.id == int(user_id)).first()
                if user and user.is_active and (user.phone or "").strip():
                    contact["name"] = (user.real_name or user.username or contact.get("name") or "").strip()
                    contact["phone"] = str(user.phone).strip()
                    contact["user_name"] = user.username
            except (TypeError, ValueError):
                pass
        phone = str(contact.get("phone") or "").strip()
        name = str(contact.get("name") or contact.get("user_name") or "").strip()
        if not phone:
            continue
        contact["name"] = name
        contact["phone"] = phone
        resolved.append(contact)
    if resolved:
        cfg["contacts"] = resolved
        cfg["phones"] = [item["phone"] for item in resolved]
    return cfg


def level_allows(alert_level: str, min_level: str) -> bool:
    """判断告警级别是否达到通道最低要求"""
    return LEVEL_RANK.get((alert_level or "warning").lower(), 1) >= LEVEL_RANK.get(
        (min_level or "warning").lower(), 1
    )


# ==================== 邮件 ====================
def _send_email_sync(cfg: Dict[str, Any], subject: str, body: str) -> None:
    host = cfg.get("smtp_host")
    port = int(cfg.get("smtp_port") or 25)
    user = cfg.get("smtp_user")
    password = cfg.get("smtp_password")
    use_ssl = bool(cfg.get("use_ssl", port == 465))
    use_tls = bool(cfg.get("use_tls", port == 587))
    mail_from = cfg.get("mail_from") or user
    mail_to = cfg.get("mail_to") or []
    if isinstance(mail_to, str):
        mail_to = [x.strip() for x in mail_to.replace(";", ",").split(",") if x.strip()]
    if not host or not mail_from or not mail_to:
        raise ValueError("邮件通道配置不完整：需要 smtp_host / mail_from / mail_to")

    msg = MIMEText(body, "plain", "utf-8")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = formataddr((str(Header(cfg.get("from_name") or "SNMP监控", "utf-8")), mail_from))
    msg["To"] = ", ".join(mail_to)
    msg["Date"] = formatdate(localtime=True)

    if use_ssl:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(host, port, timeout=15, context=ctx) as server:
            if user and password:
                server.login(user, password)
            server.sendmail(mail_from, mail_to, msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=15) as server:
            server.ehlo()
            if use_tls:
                server.starttls(context=ssl.create_default_context())
                server.ehlo()
            if user and password:
                server.login(user, password)
            server.sendmail(mail_from, mail_to, msg.as_string())


async def send_email(cfg: Dict[str, Any], subject: str, body: str) -> None:
    """异步发送邮件（smtplib 为阻塞调用，放入线程池）"""
    loop = asyncio.get_running_loop()
    await loop.run_in_executor(None, _send_email_sync, cfg, subject, body)


# ==================== Webhook ====================
def _webhook_body(template: str, title: str, text: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    tpl = (template or "generic").lower()
    recovery = bool(payload.get("recovery"))
    event_label = "恢复" if recovery else "告警"
    event_color = "#22c55e" if recovery else "#ef4444"
    event_marker = "🟢" if recovery else "🔴"
    marked_title = f"{event_marker} {title}"
    if tpl == "dingtalk":
        return {
            "msgtype": "markdown",
            "markdown": {"title": marked_title, "text": f"### {marked_title}\n\n{text}"},
        }
    if tpl == "wecom":
        return {
            "msgtype": "markdown",
            "markdown": {"content": f"### {marked_title}\n\n{text}"},
        }
    if tpl == "feishu":
        return {"msg_type": "text", "content": {"text": f"{marked_title}\n{text}"}}
    if tpl == "slack":
        return {"text": f"{event_marker} *{title}*\n{text}"}
    # generic：结构化数据，便于对接自建系统；颜色字段供支持富文本的接收端使用
    return {
        "title": marked_title,
        "text": text,
        "level": payload.get("level"),
        "source": payload.get("source"),
        "device_name": payload.get("device_name"),
        "ip_address": payload.get("ip_address"),
        "room_name": payload.get("room_name"),
        "cabinet_name": payload.get("cabinet_name"),
        "room_floor": payload.get("room_floor"),
        "room_location": payload.get("room_location"),
        "alert_type": payload.get("alert_type"),
        "value": payload.get("value"),
        "threshold": payload.get("threshold"),
        "created_at": payload.get("created_at"),
        "message_type": "recovery" if recovery else "alert",
        "event_type": "recovery" if recovery else "alert",
        "event_label": event_label,
        "event_color": event_color,
        "color": event_color,
        "recovery": recovery,
        "recovered_at": payload.get("recovered_at"),
        "original_created_at": payload.get("original_created_at"),
    }


async def send_webhook(
    cfg: Dict[str, Any], title: str, text: str, payload: Dict[str, Any]
) -> None:
    url = cfg.get("url")
    if not url:
        raise ValueError("Webhook 通道缺少 url")

    headers = {"Content-Type": "application/json"}
    headers.update(cfg.get("headers") or {})
    timeout = int(cfg.get("timeout") or 10)
    body = _webhook_body(cfg.get("template") or "generic", title, text, payload)

    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            json=body,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            resp_text = (await resp.text())[:500]
            if resp.status >= 400:
                raise RuntimeError(f"HTTP {resp.status}: {resp_text}")


# ==================== 上级平台（仅本系统） ====================
def _upstream_event_id(payload: Dict[str, Any]) -> str:
    """为同一条原始告警生成稳定事件 ID，供上级去重。"""
    explicit = str(payload.get("event_id") or "").strip()
    if explicit:
        return explicit[:120]
    source = str(payload.get("source") or "device")
    source_id = payload.get("source_id")
    stamp = payload.get("created_at") or payload.get("recovered_at") or ""
    message = payload.get("message") or payload.get("title") or ""
    raw = json.dumps(
        {"source": source, "source_id": source_id, "stamp": stamp, "message": message,
         "level": payload.get("level"), "recovery": bool(payload.get("recovery"))},
        ensure_ascii=False, sort_keys=True,
    )
    return "evt-" + hashlib.sha1(raw.encode("utf-8")).hexdigest()


async def send_upstream(
    cfg: Dict[str, Any], title: str, text: str, payload: Dict[str, Any]
) -> None:
    """把告警发送到上级本系统实例。"""
    url = str(cfg.get("url") or "").strip()
    token = str(cfg.get("token") or "").strip()
    if not url:
        raise ValueError("上级平台通道缺少 url")
    if not token:
        raise ValueError("上级平台通道缺少接收令牌")
    node_name = str(cfg.get("source_node_name") or "").strip() or Config.INSTANCE_ID
    node_id = str(cfg.get("source_node_id") or "").strip() or Config.INSTANCE_ID
    timeout = int(cfg.get("timeout") or 10)
    body = {
        "protocol": "snmp-monitor-alert-v1",
        "event_id": _upstream_event_id(payload),
        "source_node_id": node_id,
        "source_node_name": node_name,
        "source_instance": Config.INSTANCE_ID,
        "source_url": str(cfg.get("source_url") or "").strip(),
        "source": payload.get("source") or "device",
        "origin_source": payload.get("source") or "device",
        "level": payload.get("level") or "warning",
        "alert_type": payload.get("alert_type") or "alert",
        "device_name": payload.get("device_name") or "",
        "ip_address": payload.get("ip_address") or "",
        "room_name": payload.get("room_name") or "",
        "cabinet_name": payload.get("cabinet_name") or "",
        "room_floor": payload.get("room_floor") or "",
        "room_location": payload.get("room_location") or "",
        "value": payload.get("value"),
        "threshold": payload.get("threshold"),
        "title": title,
        "text": text,
        "message": payload.get("message") or text,
        "created_at": payload.get("created_at"),
        "recovered_at": payload.get("recovered_at"),
        "original_created_at": payload.get("original_created_at"),
        "message_type": "recovery" if payload.get("recovery") else "alert",
        "event_type": "recovery" if payload.get("recovery") else "alert",
        "recovery": bool(payload.get("recovery")),
        "test": bool(payload.get("test")),
    }
    headers = {
        "Content-Type": "application/json",
        "X-Upstream-Token": token,
        "X-Upstream-Protocol": "snmp-monitor-alert-v1",
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            json=body,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            resp_text = (await resp.text())[:1000]
            if resp.status >= 400:
                raise RuntimeError(f"上级平台返回 HTTP {resp.status}: {resp_text}")
            try:
                data = json.loads(resp_text)
                if data.get("ok") is False:
                    raise RuntimeError(f"上级平台拒绝告警: {data.get('detail') or resp_text}")
            except json.JSONDecodeError:
                pass


# ==================== 短信正文模板 ====================
def render_sms_template(template: Any, payload: Dict[str, Any], title: str, text: str) -> str:
    """渲染短信模板；未知占位符保持原样，模板为空时使用调度器精简正文。"""
    raw = str(template or "").strip()
    if not raw:
        return text or title
    values = {
        "level": payload.get("level") or "warning",
        "level_label": payload.get("level_label") or payload.get("level") or "warning",
        "device_name": payload.get("device_name") or payload.get("ip_address") or "设备",
        "ip_address": payload.get("ip_address") or "",
        "alert_type": payload.get("alert_type") or "告警",
        "message": payload.get("message") or text or title,
        "value": payload.get("value") if payload.get("value") is not None else "-",
        "threshold": payload.get("threshold") if payload.get("threshold") is not None else "-",
        "source": payload.get("source") or "device",
        "time": datetime.now().strftime("%m-%d %H:%M"),
    }

    class SafeValues(dict):
        def __missing__(self, key):
            return "{" + key + "}"

    try:
        rendered = raw.format_map(SafeValues(values))
    except (ValueError, IndexError):
        rendered = text or title
    rendered = " ".join(rendered.split())
    return rendered[:500]


# ==================== 统一入口 ====================
async def send_via_channel(channel: Any, title: str, text: str, payload: Dict[str, Any], db=None) -> None:
    cfg = channel.config or {}
    if channel.channel_type == "email":
        await send_email(cfg, title, text)
    elif channel.channel_type == "webhook":
        await send_webhook(cfg, title, text, payload)
    elif channel.channel_type == "sms":
        # 短信正文支持通道模板；未配置模板时使用 dispatcher 的精简正文。
        body = render_sms_template(cfg.get("message_template"), payload, title, text)
        cfg = resolve_sms_contacts(cfg, db)
        await send_sms(cfg, cfg.get("phones"), body)
    elif channel.channel_type == "upstream":
        await send_upstream(cfg, title, text, payload)
    else:
        raise ValueError(f"不支持的通知类型: {channel.channel_type}")
