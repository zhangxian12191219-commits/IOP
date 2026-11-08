"""AI 智能运维路由：只读对话、分析、报告和模型配置。"""
from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..models.user import User
from ..services import ai_ops
from ..services import ai_agent
from ..services import audit
from ..services import asset_scope
from ..services.auth import get_current_user, has_permission

router = APIRouter(prefix="/api/ai", tags=["AI智能运维"])

# 轻量进程内限流，防止单个账号刷外部模型或生成报告造成费用/资源耗尽。
_rate_lock = threading.Lock()
_rate_events: dict[str, deque] = defaultdict(deque)


def _rate_limit(user: User, action: str, limit: int, window: int = 60) -> None:
    key = f"{user.username}:{action}"
    now = time.monotonic()
    with _rate_lock:
        events = _rate_events[key]
        while events and now - events[0] > window:
            events.popleft()
        if len(events) >= limit:
            raise HTTPException(
                status_code=429,
                detail="AI 请求过于频繁，请稍后再试",
                headers={"Retry-After": str(window)},
            )
        events.append(now)



def _viewer(current: User = Depends(get_current_user)) -> User:
    if not current.is_superuser and not (
        has_permission(current, "ai:view") or has_permission(current, "monitor:view")
    ):
        raise HTTPException(status_code=403, detail="需要 AI 查看权限")
    return current


def _ai_scope(db: Session, request: Request, user: User):
    """AI 统计必须遵守资产群组范围，避免通过对话/大屏越权读取其他群组设备。"""
    device_ids = asset_scope.visible_device_ids(db, request)
    include_virtualization = bool(
        user.is_superuser or has_permission(user, "virtualization:view")
    )
    return device_ids, include_virtualization


def _admin(current: User = Depends(get_current_user)) -> User:
    if not current.is_superuser and not has_permission(current, "ai:config"):
        raise HTTPException(status_code=403, detail="需要 AI 模型配置权限")
    return current


@router.get("/status")
def status(db: Session = Depends(get_db), current: User = Depends(_viewer)):
    config = ai_ops.get_config(db)
    return ai_ops.public_config(config)


@router.get("/overview")
def overview(request: Request, db: Session = Depends(get_db), current: User = Depends(_viewer)):
    device_ids, include_virtualization = _ai_scope(db, request, current)
    return ai_ops.overview(db, device_ids=device_ids, include_virtualization=include_virtualization)


@router.get("/alerts/analysis")
def alerts_analysis(request: Request, db: Session = Depends(get_db), current: User = Depends(_viewer)):
    device_ids, include_virtualization = _ai_scope(db, request, current)
    data = ai_ops.overview(db, device_ids=device_ids, include_virtualization=include_virtualization)
    return {"overview": data, "analysis": ai_ops._alert_analysis(data)}


@router.post("/chat")
def chat(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current: User = Depends(_viewer),
):
    _rate_limit(current, "chat", 30)
    device_ids, include_virtualization = _ai_scope(db, request, current)
    session_id = str(payload.get("session_id") or "").strip()[:80]
    channel = "voice" if str(payload.get("channel") or "").strip().lower() in (
        "voice", "speech", "audio",
    ) else "text"
    try:
        return ai_ops.chat(
            db,
            str(payload.get("message") or ""),
            payload.get("history") if isinstance(payload.get("history"), list) else [],
            device_ids=device_ids,
            include_virtualization=include_virtualization,
            session_id=session_id,
            username=current.username or "",
            channel=channel,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/tts")
def tts(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current: User = Depends(_viewer),
):
    """OpenAI 兼容 TTS 代理，前端优先播放模型音频，失败时回退浏览器语音。"""
    _rate_limit(current, "tts", 60)
    text = str(payload.get("text") or "").strip()
    if not text:
        raise HTTPException(status_code=400, detail="TTS 文本不能为空")
    config = ai_ops.get_config(db)
    try:
        audio, media_type, _ = ai_ops.synthesize_speech(config, text)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"TTS 调用失败：{str(exc)[:300]}") from exc
    return Response(content=audio, media_type=media_type, headers={"Cache-Control": "no-store"})


@router.post("/agent/chat")
async def agent_chat(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current: User = Depends(_viewer),
):
    """AI 运维智能体：工具调用、全模块检索、MIB 配置建议。"""
    _rate_limit(current, "agent_chat", 30)
    device_ids, include_virtualization = _ai_scope(db, request, current)
    channel = "voice" if str(payload.get("channel") or "").strip().lower() in (
        "voice", "speech", "audio",
    ) else "text"
    try:
        return await ai_agent.chat(
            db,
            str(payload.get("message") or ""),
            payload.get("history") if isinstance(payload.get("history"), list) else [],
            device_ids=device_ids,
            include_virtualization=include_virtualization,
            session_id=str(payload.get("session_id") or "")[:80],
            username=current.username or "",
            channel=channel,
            user=current,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/agent/capabilities")
def agent_capabilities(current: User = Depends(_viewer)):
    return {
        "tools": [
            {"key": key, "name": label}
            for key, label in ai_agent.TOOL_LABELS.items()
        ],
        "modules": [
            "资产管理", "告警中心", "MIB 管理", "配置备份", "网络拓扑", "机房与机柜",
            "虚拟化", "网站与证书", "设备巡检", "用户与审计", "授权信息", "系统运行",
        ],
        "safe_actions": True,
    }


@router.post("/chat/reset")
def chat_reset(
    payload: Optional[Dict[str, Any]] = Body(None),
    current: User = Depends(_viewer),
):
    """清空当前用户的指定会话上下文，用于开启新对话。"""
    ai_ops.reset_session(
        current.username or "",
        str((payload or {}).get("session_id") or "").strip()[:80],
    )
    return {"message": "会话已重置", "session_id": ""}


@router.get("/config")
def get_config(db: Session = Depends(get_db), current: User = Depends(_admin)):
    return ai_ops.public_config(ai_ops.get_config(db))


@router.put("/config")
def save_config(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current: User = Depends(_admin),
):
    base_url = str(payload.get("base_url") or "").strip()
    if base_url and not base_url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="模型地址必须以 http:// 或 https:// 开头")
    wake_word = str(payload.get("wake_word") or "").strip()
    if len(wake_word) > 40:
        raise HTTPException(status_code=400, detail="唤醒词最多 40 个字符")
    try:
        result = ai_ops.save_config(db, payload)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit.record(
        db, request, module="ai", action="update",
        target_type="ai_config", target_name="AI智能运维配置",
        after={**result, "api_key": "******" if result.get("has_key") else ""},
        message="更新 AI 智能运维模型配置",
    )
    return {"message": "AI 配置已保存", **result}


@router.post("/config/test")
def test_config(
    payload: Optional[Dict[str, Any]] = Body(None),
    db: Session = Depends(get_db),
    current: User = Depends(_admin),
):
    """使用表单当前填写的连接信息测试，不保存配置。"""
    _rate_limit(current, "config_test", 10)
    saved = ai_ops.get_config(db)
    config = dict(saved)
    data = payload if isinstance(payload, dict) else {}
    base_url = str(data.get("base_url") or "").strip()
    model = str(data.get("model") or "").strip()
    api_key = str(data.get("api_key") or "").strip()
    if base_url:
        if not base_url.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail="模型地址必须以 http:// 或 https:// 开头")
        config["base_url"] = base_url
    if model:
        config["model"] = model
    # API Key 留空时沿用已保存的 Key，填写新 Key 时使用新 Key 测试。
    config["api_key"] = api_key or saved.get("api_key") or ""
    config["has_key"] = bool(config["api_key"])
    if data.get("temperature") not in (None, ""):
        try:
            config["temperature"] = str(float(data.get("temperature")))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="温度必须是数字") from None
    if data.get("max_tokens") not in (None, ""):
        try:
            config["max_tokens"] = max(100, min(8000, int(data.get("max_tokens"))))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="最大 Token 必须是整数") from None
    if not config.get("base_url") or not config.get("model"):
        raise HTTPException(status_code=400, detail="请填写模型地址和模型名称")
    if not config.get("api_key"):
        raise HTTPException(status_code=400, detail="请填写 API Key")
    try:
        reply = ai_ops._call_model(config, [
            {"role": "system", "content": "只回复：连接成功"},
            {"role": "user", "content": "ping"},
        ])
        return {
            "ok": True,
            "message": reply[:300],
            "model": config["model"],
            "base_url": config["base_url"],
            "using_saved_key": not bool(api_key),
        }
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"模型连接失败：{str(exc)[:500]}") from exc


@router.post("/reports")
def generate_report(
    request: Request,
    payload: Optional[Dict[str, Any]] = Body(None),
    db: Session = Depends(get_db),
    current: User = Depends(_viewer),
):
    _rate_limit(current, "report", 5)
    topic = str((payload or {}).get("topic") or "").strip()
    device_ids, include_virtualization = _ai_scope(db, request, current)
    try:
        result = ai_ops.generate_report(
            db, topic=topic, username=current.username or "",
            device_ids=device_ids, include_virtualization=include_virtualization,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"报告生成失败：{str(exc)[:500]}") from exc
    audit.record(
        db, request, module="ai", action="create",
        target_type="ai_report", target_id=result["id"], target_name=result["title"],
        message=f"生成 AI 运维报告（{result['mode']}）",
    )
    return result


@router.get("/reports")
def reports(
    limit: int = Query(20, ge=1, le=100),
    db: Session = Depends(get_db),
    current: User = Depends(_viewer),
):
    return {"items": ai_ops.list_reports(db, limit, None if current.is_superuser else current.username)}


@router.get("/reports/{report_id}/download")
def download_report(
    report_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(_viewer),
):
    from ..models.ai_report import AiOpsReport

    report = db.query(AiOpsReport).filter(AiOpsReport.id == report_id).first()
    if not report:
        raise HTTPException(status_code=404, detail="AI 报告不存在")
    if not current.is_superuser and report.created_by != current.username:
        raise HTTPException(status_code=404, detail="AI 报告不存在")
    try:
        path = ai_ops.report_path(report.filename)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    media = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if path.suffix.lower() != ".docx":
        media = "text/markdown; charset=utf-8"
    return FileResponse(path, media_type=media, filename=report.filename or path.name)
