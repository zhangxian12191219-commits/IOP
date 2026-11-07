"""总部/分支级联 API 与出站隧道端点。"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from ..models.cascade import CascadeMessage, CascadeNode
from ..models.database import SessionLocal, get_db
from ..models.user import User
from ..services import audit
from ..services import cascade as cascade_service
from ..services import cascade_tunnel, web_gateway
from ..services.auth import get_current_user

logger = logging.getLogger("snmp-monitor.cascade")
router = APIRouter(prefix="/api/cascade", tags=["总部分支级联"])


def _admin(current: User = Depends(get_current_user)) -> User:
    if not current.is_superuser:
        raise HTTPException(status_code=403, detail="级联配置仅超级管理员可操作")
    return current


def _node_or_404(db: Session, node_id: int) -> CascadeNode:
    node = db.query(CascadeNode).filter(CascadeNode.id == node_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="分支节点不存在")
    return node


@router.get("/status")
def status(db: Session = Depends(get_db), current: User = Depends(_admin)):
    data = cascade_service.status(db)
    data["tunnel"] = cascade_tunnel.manager.branch_state()
    return data


@router.get("/config")
def get_config(db: Session = Depends(get_db), current: User = Depends(_admin)):
    return {"config": cascade_service.public_config(cascade_service.get_config(db))}


@router.put("/config")
async def save_config(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current: User = Depends(_admin),
):
    try:
        result = cascade_service.save_config(db, payload)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await cascade_tunnel.manager.reload()
    try:
        await web_gateway.gateway.apply_cascade_tunnel(db)
    except Exception as exc:  # noqa: BLE001
        logger.warning("级联专用端口应用失败: %s", exc)
    audit.record(
        db, request, module="cascade", action="update",
        target_type="cascade_config", target_name="级联连接配置",
        after=result, message="更新总部/分支级联配置",
    )
    return {"message": "级联配置已保存", "config": result}


@router.get("/nodes")
def list_nodes(db: Session = Depends(get_db), current: User = Depends(_admin)):
    return cascade_service.status(db)


@router.post("/nodes")
def create_node(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current: User = Depends(_admin),
):
    try:
        result = cascade_service.create_node(db, str(payload.get("name") or ""))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    audit.record(
        db, request, module="cascade", action="create",
        target_type="cascade_node", target_id=result["id"], target_name=result["name"],
        after={"node_key": result["node_key"]}, message="登记级联分支节点并生成接入令牌",
    )
    return {"message": "分支节点已登记，请立即保存一次性接入令牌", **result}


@router.get("/nodes/{node_id}")
def get_node(node_id: int, db: Session = Depends(get_db), current: User = Depends(_admin)):
    node = _node_or_404(db, node_id)
    data = cascade_service.node_dict(node)
    data["snapshot"] = node.snapshot or {}
    data["connected"] = cascade_tunnel.manager.hq_connected(node.node_key)
    return data


@router.delete("/nodes/{node_id}")
def delete_node(
    node_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(_admin),
):
    node = _node_or_404(db, node_id)
    name = node.name
    db.query(CascadeMessage).filter(CascadeMessage.node_key == node.node_key).delete(synchronize_session=False)
    db.delete(node)
    db.commit()
    audit.record(
        db, request, module="cascade", action="delete",
        target_type="cascade_node", target_id=node_id, target_name=name,
        message="删除级联分支节点",
    )
    return {"message": "分支节点已删除"}


@router.get("/messages")
def messages(
    node_id: Optional[int] = None,
    limit: int = Query(100, ge=1, le=200),
    db: Session = Depends(get_db),
    current: User = Depends(_admin),
):
    config = cascade_service.get_config(db)
    if config["role"] == "branch":
        rows = cascade_service.list_messages(db, "hq", limit)
    else:
        node_key = ""
        if node_id:
            node_key = _node_or_404(db, node_id).node_key
        rows = cascade_service.list_messages(db, node_key, limit)
    return {"items": rows}


@router.post("/messages")
async def send_message(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current: User = Depends(_admin),
):
    content = str(payload.get("content") or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="消息内容不能为空")
    config = cascade_service.get_config(db)
    if config["role"] == "branch":
        row = cascade_service.add_message(
            db, "hq", config["node_name"] or "分支节点", content,
            "branch_to_hq", delivered=True,
        )
        sent = await cascade_tunnel.manager.send_branch_chat(content)
        if not sent:
            # 消息保留在分支本地，隧道恢复后仍可查看历史；总部需在线才能实时收到
            raise HTTPException(status_code=409, detail="总部隧道当前未连接，消息未发送")
        return {"message": "消息已发送", "item": {
            "id": row.id, "sender": row.sender, "content": row.content,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        }}
    try:
        node_id = int(payload.get("node_id") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="请选择分支节点") from None
    node = _node_or_404(db, node_id)
    row = cascade_service.add_message(
        db, node.node_key, current.username or "总部", content,
        "hq_to_branch", delivered=False,
    )
    sent = await cascade_tunnel.manager.send_to_branch(node, {
        "type": "chat", "sender": current.username or "总部", "content": content,
        "message_id": row.id,
    })
    if sent:
        row.delivered = True
        db.commit()
    audit.record(
        db, request, module="cascade", action="create",
        target_type="cascade_message", target_id=row.id, target_name=node.name,
        message=f"向分支 {node.name} 发送级联消息（{'已投递' if sent else '待投递'}）",
    )
    return {
        "message": "消息已发送" if sent else "分支离线，消息已保存并等待投递",
        "item": {
            "id": row.id, "sender": row.sender, "content": row.content,
            "delivered": bool(row.delivered),
            "created_at": row.created_at.isoformat() if row.created_at else None,
        },
    }


@router.websocket("/tunnel")
async def tunnel(websocket: WebSocket, token: str = Query("", max_length=200)):
    """分支主动连接总部的加密隧道入口。"""
    db = SessionLocal()
    try:
        header = websocket.headers.get("authorization", "")
        token = token or (header[7:].strip() if header.lower().startswith("bearer ") else "")
        node = cascade_service.authenticate_node(db, token)
        if not node:
            await websocket.close(code=4401, reason="接入令牌无效")
            return
        await websocket.accept()
        cascade_tunnel.manager.register_hq(node.node_key, websocket)
        await cascade_tunnel.manager.deliver_pending(node)
        while True:
            frame = await websocket.receive_text()
            try:
                payload = cascade_service.decrypt_frame(token, frame)
            except ValueError as exc:
                await websocket.send_json({"type": "error", "message": str(exc)[:200]})
                continue
            kind = str(payload.get("type") or "")
            if kind == "hello":
                cascade_service.touch_node(
                    db, node,
                    name=str(payload.get("node_name") or node.name),
                    version=str(payload.get("version") or ""),
                    address=str(payload.get("address") or ""),
                )
                if isinstance(payload.get("snapshot"), dict):
                    cascade_service.record_snapshot(db, node, payload["snapshot"])
                await websocket.send_text(cascade_service.encrypt_frame(token, {"type": "ack", "at": node.last_seen.isoformat() if node.last_seen else None}))
                await cascade_tunnel.manager.deliver_pending(node)
            elif kind == "heartbeat":
                cascade_service.touch_node(db, node)
            elif kind == "snapshot":
                if isinstance(payload.get("snapshot"), dict):
                    cascade_service.record_snapshot(db, node, payload["snapshot"])
                await websocket.send_text(cascade_service.encrypt_frame(token, {"type": "ack", "at": node.last_sync.isoformat() if node.last_sync else None}))
            elif kind == "chat":
                content = str(payload.get("content") or "").strip()
                if content:
                    cascade_service.add_message(
                        db, node.node_key, str(payload.get("sender") or node.name),
                        content, "branch_to_hq", delivered=True,
                    )
                    await websocket.send_text(cascade_service.encrypt_frame(token, {"type": "ack", "message_id": payload.get("message_id")}))
            else:
                await websocket.send_text(cascade_service.encrypt_frame(token, {"type": "error", "message": "不支持的隧道消息类型"}))
    except WebSocketDisconnect:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("级联隧道异常: %s", exc)
    finally:
        try:
            node_key = node.node_key if "node" in locals() and node else ""
            if node_key:
                cascade_tunnel.manager.unregister_hq(node_key, websocket)
                node = db.query(CascadeNode).filter(CascadeNode.node_key == node_key).first()
                if node:
                    node.status = "offline"
                    db.commit()
        except Exception:  # noqa: BLE001
            db.rollback()
        db.close()
