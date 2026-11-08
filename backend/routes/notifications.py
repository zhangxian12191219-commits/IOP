"""告警渠道路由 - 通道管理与测试"""
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..models.notifications import NotificationChannel, NotificationLog
from ..models.user import User
from ..models.schemas import NotificationChannelCreate, NotificationChannelUpdate
from ..notify import dispatch, send_via_channel
from ..services import audit
from ..services import upstream as upstream_service

router = APIRouter(prefix="/api/notifications", tags=["告警渠道"])

MASK = "******"
SECRET_KEYS = ("smtp_password", "token", "secret", "password", "api_key", "access_token")

# 支持的通道类型
CHANNEL_TYPES = ("email", "webhook", "sms", "upstream")
# 短信网关实现方式
SMS_PROVIDERS = {
    "mfm920e": {
        "name": "MFM-920E 智能告警模块",
        "desc": "融智云 MFM-920E 原生 HTTP 接口：POST /cgi-bin/NoticePush，JSON 中的 To 为手机号数组，成功响应 Reply=OK。",
        "required": ["url", "phones"],
    },
    "http": {
        "name": "HTTP 短信网关",
        "desc": "多数硬件短信猫/短信网关、企业短信平台提供 HTTP 接口，"
                "可自定义 URL、参数模板与成功判定方式。",
        "required": ["url", "phones"],
    },
    "smpp": {
        "name": "SMPP 3.4 网关",
        "desc": "运营商级短信网关常用 TCP 协议，需 host/port/system_id/password。",
        "required": ["host", "system_id", "password", "phones"],
    },
    "serial": {
        "name": "串口 GSM 模块",
        "desc": "短信猫通过串口 AT 指令发送，需 port（如 /dev/ttyUSB0）且安装 pyserial。",
        "required": ["port", "phones"],
    },
}


def _mask_config(cfg: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not cfg:
        return {}
    out = dict(cfg)
    for key in SECRET_KEYS:
        if out.get(key):
            out[key] = MASK
    return out


def _merge_secrets(new_cfg: Dict[str, Any], old_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """前端回传掩码/空值时保留原密码"""
    merged = dict(new_cfg or {})
    for key in SECRET_KEYS:
        if key in merged and merged[key] in (MASK, "", None):
            if old_cfg and old_cfg.get(key):
                merged[key] = old_cfg[key]
    return merged


def _channel_to_dict(ch: NotificationChannel) -> dict:
    return {
        "id": ch.id,
        "name": ch.name,
        "channel_type": ch.channel_type,
        "enabled": ch.enabled,
        "min_level": ch.min_level,
        "config": _mask_config(ch.config),
        "created_at": ch.created_at.isoformat() if ch.created_at else None,
        "updated_at": ch.updated_at.isoformat() if ch.updated_at else None,
    }


def _normalize_sms_config(db: Session, channel_type: str, config: Dict[str, Any]) -> Dict[str, Any]:
    """规范化短信联系人，兼容旧版 phones，并填充关联用户的最新信息。"""
    cfg = dict(config or {})
    if channel_type != "sms":
        return cfg
    contacts = cfg.get("contacts")
    if isinstance(contacts, list):
        cleaned = []
        seen = set()
        for raw in contacts:
            if not isinstance(raw, dict):
                continue
            item = dict(raw)
            user_id = item.get("user_id")
            if user_id:
                try:
                    user = db.query(User).filter(User.id == int(user_id)).first()
                except (TypeError, ValueError):
                    user = None
                if user:
                    item["user_id"] = user.id
                    item["user_name"] = user.username
                    item["name"] = (user.real_name or user.username or item.get("name") or "").strip()
                    if (user.phone or "").strip():
                        item["phone"] = str(user.phone).strip()
                else:
                    item.pop("user_id", None)
            phone = str(item.get("phone") or "").strip()
            if not phone or phone in seen:
                continue
            seen.add(phone)
            item["phone"] = phone
            item["name"] = str(item.get("name") or item.get("user_name") or "").strip()
            cleaned.append(item)
        if cleaned:
            cfg["contacts"] = cleaned
            cfg["phones"] = [item["phone"] for item in cleaned]
        elif cfg.get("phones"):
            cfg["contacts"] = []
        else:
            cfg["contacts"] = []
            cfg["phones"] = []
    # 旧版 phones 兼容：统一去重为数组
    phones = cfg.get("phones")
    if phones:
        if isinstance(phones, str):
            phones = [p.strip() for p in phones.replace(";", ",").split(",") if p.strip()]
        elif isinstance(phones, (list, tuple)):
            phones = [str(p).strip() for p in phones if str(p).strip()]
        else:
            phones = []
        cfg["phones"] = list(dict.fromkeys(phones))
    return cfg


def _validate_config(channel_type: str, config: Dict[str, Any]) -> None:
    """保存前做必要字段校验，避免配错了到告警时才失败"""
    cfg = config or {}
    if channel_type == "email":
        missing = [k for k in ("smtp_host", "mail_from", "mail_to") if not cfg.get(k)]
        if missing:
            raise HTTPException(status_code=400, detail=f"邮件通道缺少字段: {', '.join(missing)}")
    elif channel_type == "webhook":
        if not cfg.get("url"):
            raise HTTPException(status_code=400, detail="Webhook 通道缺少 url")
    elif channel_type == "upstream":
        missing = [k for k in ("url", "token", "source_node_name") if not cfg.get(k)]
        if missing:
            raise HTTPException(status_code=400, detail=f"上级平台通道缺少字段: {', '.join(missing)}")
        if not str(cfg.get("url") or "").startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="上级平台地址必须以 http:// 或 https:// 开头")
    elif channel_type == "sms":
        provider = (cfg.get("provider") or "http").lower()
        if provider not in SMS_PROVIDERS:
            raise HTTPException(
                status_code=400, detail=f"短信 provider 仅支持: {', '.join(SMS_PROVIDERS)}"
            )
        missing = [k for k in SMS_PROVIDERS[provider]["required"] if not cfg.get(k)]
        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"短信({provider})缺少字段: {', '.join(missing)}",
            )


@router.get("/sms/providers")
def list_sms_providers():
    """短信网关实现方式说明（供前端表单展示）"""
    return [{"provider": key, **value} for key, value in SMS_PROVIDERS.items()]


def _channel_snapshot(ch: NotificationChannel) -> dict:
    return {
        "name": ch.name,
        "channel_type": ch.channel_type,
        "enabled": bool(ch.enabled),
        "min_level": ch.min_level,
        "config": _mask_config(ch.config),
    }


@router.get("/channels")
def list_channels(db: Session = Depends(get_db)):
    """获取通知通道列表"""
    channels = db.query(NotificationChannel).order_by(NotificationChannel.id).all()
    return [_channel_to_dict(c) for c in channels]


@router.post("/channels")
def create_channel(
    payload: NotificationChannelCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    """新增通知通道（email / webhook / sms）"""
    if payload.channel_type not in CHANNEL_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"channel_type 仅支持: {', '.join(CHANNEL_TYPES)}",
        )
    config = _normalize_sms_config(db, payload.channel_type, payload.config or {})
    _validate_config(payload.channel_type, config)

    ch = NotificationChannel(
        name=payload.name,
        channel_type=payload.channel_type,
        enabled=payload.enabled,
        min_level=payload.min_level or "warning",
        config=config,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(ch)
    db.commit()
    db.refresh(ch)
    audit.record(
        db, request, module="notifications", action="create",
        target_type="channel", target_id=ch.id, target_name=ch.name,
        after=_channel_snapshot(ch),
        message=f"新增通知通道 {ch.name}（{ch.channel_type}）",
    )
    return _channel_to_dict(ch)


@router.put("/channels/{channel_id}")
def update_channel(
    channel_id: int,
    payload: NotificationChannelUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    """更新通知通道"""
    ch = db.query(NotificationChannel).filter(NotificationChannel.id == channel_id).first()
    if not ch:
        raise HTTPException(status_code=404, detail="通道不存在")

    before = _channel_snapshot(ch)
    data = payload.model_dump(exclude_unset=True)
    if "config" in data:
        data["config"] = _merge_secrets(data["config"] or {}, ch.config or {})

    channel_type = data.get("channel_type") or ch.channel_type
    if channel_type not in CHANNEL_TYPES:
        raise HTTPException(status_code=400, detail=f"channel_type 仅支持: {', '.join(CHANNEL_TYPES)}")
    if "config" in data or "channel_type" in data:
        data["config"] = _normalize_sms_config(db, channel_type, data.get("config") or ch.config or {})
        _validate_config(channel_type, data["config"])

    for key, value in data.items():
        setattr(ch, key, value)

    ch.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(ch)
    audit.record(
        db, request, module="notifications", action="update",
        target_type="channel", target_id=ch.id, target_name=ch.name,
        before=before, after=_channel_snapshot(ch),
        message=f"更新通知通道 {ch.name}",
    )
    return _channel_to_dict(ch)


@router.delete("/channels/{channel_id}")
def delete_channel(channel_id: int, request: Request, db: Session = Depends(get_db)):
    """删除通知通道"""
    ch = db.query(NotificationChannel).filter(NotificationChannel.id == channel_id).first()
    if not ch:
        raise HTTPException(status_code=404, detail="通道不存在")
    before = _channel_snapshot(ch)
    ch_name = ch.name
    db.query(NotificationLog).filter(NotificationLog.channel_id == channel_id).delete(
        synchronize_session=False
    )
    db.delete(ch)
    db.commit()
    audit.record(
        db, request, module="notifications", action="delete",
        target_type="channel", target_id=channel_id, target_name=ch_name,
        before=before, message=f"删除通知通道 {ch_name}",
    )
    return {"message": "通道已删除"}


@router.post("/channels/{channel_id}/test")
async def test_channel(channel_id: int, db: Session = Depends(get_db)):
    """向指定通道发送测试通知"""
    ch = db.query(NotificationChannel).filter(NotificationChannel.id == channel_id).first()
    if not ch:
        raise HTTPException(status_code=404, detail="通道不存在")

    title = "[测试] 智能运维服务平台通知测试"
    if ch.channel_type == "sms":
        title = "【测试】智能运维服务平台"
        text = f"【测试】智能运维服务平台短信通道测试，{datetime.now().strftime('%m-%d %H:%M')}"
    else:
        text = (
            "这是一条测试消息。\n"
            f"通道：{ch.name}（{ch.channel_type}）\n"
            f"时间：{datetime.now().isoformat(timespec='seconds')}\n"
            "收到此消息说明通知配置正确。"
        )
    payload = {"level": "warning", "source": "test", "message": title, "test": True}

    try:
        await send_via_channel(ch, title, text, payload, db=db)
    except Exception as exc:  # noqa: BLE001
        db.add(NotificationLog(
            channel_id=ch.id,
            channel_name=ch.name,
            channel_type=ch.channel_type,
            source="test",
            source_id=None,
            title=title,
            message=text,
            status="failed",
            error=str(exc)[:1000],
            created_at=datetime.utcnow(),
        ))
        db.commit()
        raise HTTPException(status_code=400, detail=f"发送失败: {exc}") from exc

    db.add(NotificationLog(
        channel_id=ch.id,
        channel_name=ch.name,
        channel_type=ch.channel_type,
        source="test",
        source_id=None,
        title=title,
        message=text,
        status="success",
        error=None,
        created_at=datetime.utcnow(),
    ))
    db.commit()
    return {"message": "测试消息已发送"}


@router.post("/test")
async def test_inline_config(payload: Dict[str, Any], db: Session = Depends(get_db)):
    """不保存通道，直接用给定配置测试（便于表单调试）"""
    channel_type = (payload or {}).get("channel_type")
    config = _normalize_sms_config(db, channel_type, (payload or {}).get("config") or {})
    if channel_type not in CHANNEL_TYPES:
        raise HTTPException(
            status_code=400, detail=f"channel_type 仅支持: {', '.join(CHANNEL_TYPES)}"
        )
    _validate_config(channel_type, config)

    class _Tmp:
        name = "临时通道"
        id = None
        min_level = "warning"

    tmp = _Tmp()
    tmp.channel_type = channel_type
    tmp.config = config

    title = "[测试] 智能运维服务平台通知测试"
    text = f"这是一条测试消息，时间：{datetime.now().isoformat(timespec='seconds')}"
    try:
        await send_via_channel(tmp, title, text, {"level": "warning", "source": "test", "test": True}, db=db)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"发送失败: {exc}") from exc
    return {"message": "测试消息已发送"}


@router.get("/upstream/settings")
def upstream_settings(db: Session = Depends(get_db)):
    """上级平台接收配置与最近接收统计（仅超级管理员）。"""
    return upstream_service.settings_info(db)


@router.post("/upstream/token")
def create_upstream_token(request: Request, db: Session = Depends(get_db)):
    """生成或重置上级平台接收入口令牌。"""
    token = upstream_service.generate_token(db)
    audit.record(
        db, request, module="notifications", action="update",
        target_type="upstream_token", target_name="上级平台接入令牌",
        message="生成上级平台接收入口令牌",
    )
    return {
        "message": "上级平台接入令牌已生成，请复制到下级节点的上级平台渠道",
        **upstream_service.settings_info(db), "token": token,
    }


@router.get("/upstream/received")
def upstream_received(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """上级平台最近收到的下级告警。"""
    return {"items": upstream_service.recent_received(db, limit)}


@router.post("/upstream/ingest")
async def upstream_ingest(
    payload: Dict[str, Any],
    request: Request,
    db: Session = Depends(get_db),
    x_upstream_token: Optional[str] = Header(None, alias="X-Upstream-Token"),
):
    """供本系统下级节点上报告警的公开接收入口（令牌鉴权）。"""
    if not upstream_service.token_matches(db, x_upstream_token or ""):
        raise HTTPException(status_code=401, detail="上级平台接收令牌无效")
    try:
        remote_ip = request.client.host if request.client else ""
        result = await upstream_service.ingest(db, payload, remote_ip)
        if result.get("status") == "failed":
            raise HTTPException(status_code=502, detail=result.get("detail") or "上级平台本地外发通道全部失败")
        return result
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/logs")
def list_logs(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    status: Optional[str] = None,
    source: Optional[str] = None,
):
    """通知发送日志"""
    query = db.query(NotificationLog).order_by(NotificationLog.created_at.desc())
    if status:
        query = query.filter(NotificationLog.status == status)
    if source:
        query = query.filter(NotificationLog.source == source)

    total = query.count()
    rows = query.offset((page - 1) * size).limit(size).all()
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [
            {
                "id": r.id,
                "channel_id": r.channel_id,
                "channel_name": r.channel_name,
                "channel_type": r.channel_type,
                "source": r.source,
                "source_id": r.source_id,
                "title": r.title,
                "message": r.message,
                "status": r.status,
                "error": r.error,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }


@router.post("/dispatch-test")
async def dispatch_test(payload: Optional[Dict[str, Any]] = None):
    """向所有已启用通道分发一条模拟告警，验证端到端链路"""
    info = payload or {}
    result = await dispatch({
        "source": "device",
        "source_id": None,
        "level": info.get("level", "warning"),
        "device_name": info.get("device_name", "测试设备-Core-SW-01"),
        "ip_address": info.get("ip_address", "10.0.0.1"),
        "alert_type": info.get("alert_type", "cpu"),
        "message": info.get("message", "CPU使用率 88% 超过阈值 80%（模拟告警）"),
        "value": info.get("value", 88),
        "threshold": info.get("threshold", 80),
        "created_at": datetime.utcnow().isoformat(timespec="seconds"),
    })
    return {"results": result, "count": len(result)}
