"""即时通信接口：单聊 / 群聊消息、附件、群组、WebRTC 信令、群白板和悬浮球偏好。"""
import json
import logging
import mimetypes
import os
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from ..config import Config
from ..models.database import SessionLocal, get_db
from ..models.im import (
    GROUP_MAX_MEMBERS,
    GROUP_NAME_MAX_LENGTH,
    ChatAttachment,
    ChatGroup,
    ChatGroupMember,
    ChatMessage,
    ImPreference,
)
from ..models.user import User
from ..services import auth as auth_service
from ..services import im_groups as im_group_service
from ..services.im_schema import run_ensure_im_schema

logger = logging.getLogger(__name__)

# 历史库的 chat_messages.recipient_id 曾为 NOT NULL，导入路由时做一次幂等迁移
run_ensure_im_schema()

router = APIRouter(prefix="/api/im", tags=["即时通信"])

CHAT_RETENTION_DAYS = 15
MESSAGE_RECALL_SECONDS = 120
MAX_ATTACHMENT_BYTES = 500 * 1024 * 1024
MAX_MESSAGE_LENGTH = im_group_service.MAX_MESSAGE_LENGTH
ATTACHMENT_ROOT = Path(__file__).resolve().parents[2] / "data" / "chat_uploads"
ATTACHMENT_ROOT.mkdir(parents=True, exist_ok=True)

CALL_TYPES = {"call-offer", "call-answer", "call-ice", "call-hangup", "call-reject"}
GROUP_CALL_TYPES = {
    "group-call-start",
    "group-call-join",
    "group-call-leave",
    "group-call-end",
    "group-call-media",
    "group-call-reject",
}
WHITEBOARD_TYPES = {
    "whiteboard-draw",
    "whiteboard-clear",
    "whiteboard-undo",
    "whiteboard-pointer",
    "whiteboard-sync",
}
group_call_registry = im_group_service.registry
DEFAULT_SETTINGS = {
    "enabled": True,
    "shortcuts": ["im", "notes", "tools", "audio-call", "video-call", "alerts"],
    "custom_shortcuts": [],
    "recent": [],
    "position": None,
}


class ConnectionManager:
    def __init__(self):
        self.connections: Dict[int, set[WebSocket]] = {}

    async def connect(self, user_id: int, websocket: WebSocket):
        self.connections.setdefault(user_id, set()).add(websocket)

    def disconnect(self, user_id: int, websocket: WebSocket):
        rooms = self.connections.get(user_id)
        if not rooms:
            return
        rooms.discard(websocket)
        if not rooms:
            self.connections.pop(user_id, None)

    def online_ids(self) -> set[int]:
        return set(self.connections.keys())

    async def send_to(self, user_id: int, payload: dict) -> int:
        sent = 0
        for websocket in list(self.connections.get(user_id, set())):
            try:
                await websocket.send_json(payload)
                sent += 1
            except Exception:  # noqa: BLE001
                self.disconnect(user_id, websocket)
        return sent

    async def broadcast(self, payload: dict):
        for user_id in list(self.connections.keys()):
            await self.send_to(user_id, payload)


manager = ConnectionManager()


def _user_dict(user: User, online: Optional[bool] = None) -> dict:
    result = {
        "id": user.id,
        "username": user.username,
        "real_name": user.real_name or user.username,
        "is_superuser": bool(user.is_superuser),
        "email": user.email or "",
        "phone": user.phone or "",
    }
    if online is not None:
        result["online"] = bool(online)
    return result


def _attachment_dict(attachment: Optional[ChatAttachment]) -> Optional[dict]:
    if not attachment:
        return None
    mime = attachment.mime_type or mimetypes.guess_type(attachment.original_name)[0] or "application/octet-stream"
    return {
        "id": attachment.id,
        "name": attachment.original_name,
        "mime": mime,
        "size": int(attachment.size or 0),
        "kind": "image" if mime.startswith("image/") else "file",
        "url": f"/api/im/files/{attachment.id}",
        "created_at": attachment.created_at.isoformat() if attachment.created_at else None,
    }


def _message_dict(
    message: ChatMessage,
    attachment: Optional[ChatAttachment] = None,
    sender: Optional[User] = None,
) -> dict:
    recalled = bool(message.recalled_at)
    return {
        "id": message.id,
        "sender_id": message.sender_id,
        "recipient_id": message.recipient_id,
        "group_id": message.group_id,
        "sender": _user_dict(sender) if sender is not None else None,
        "content": "" if recalled else message.content,
        "message_type": "text" if recalled else (message.message_type or ("image" if attachment and (attachment.mime_type or "").startswith("image/") else ("file" if attachment else "text"))),
        "attachment": None if recalled else _attachment_dict(attachment),
        "created_at": message.created_at.isoformat() if message.created_at else None,
        "read_at": message.read_at.isoformat() if message.read_at else None,
        "recalled": recalled,
        "recalled_at": message.recalled_at.isoformat() if message.recalled_at else None,
        "can_recall": bool(
            not recalled
            and message.created_at
            and (datetime.utcnow() - message.created_at).total_seconds() <= MESSAGE_RECALL_SECONDS
        ),
        "recall_seconds": MESSAGE_RECALL_SECONDS,
    }


def _visible_message_filter(user_id: int):
    """只返回当前用户尚未删除的消息；删除是账号级隐藏，不影响对方。"""
    return or_(
        and_(
            ChatMessage.sender_id == user_id,
            or_(ChatMessage.sender_deleted.is_(False), ChatMessage.sender_deleted.is_(None)),
        ),
        and_(
            ChatMessage.recipient_id == user_id,
            or_(ChatMessage.recipient_deleted.is_(False), ChatMessage.recipient_deleted.is_(None)),
        ),
    )


def _group_visible_filter(user_id: int):
    """群聊消息只有发送方的“仅自己删除”标记，其他成员的消息始终可见。"""
    return or_(
        ChatMessage.sender_id != user_id,
        or_(ChatMessage.sender_deleted.is_(False), ChatMessage.sender_deleted.is_(None)),
    )


def _group_members(db: Session, group_id: int) -> List[tuple[ChatGroupMember, User]]:
    return (
        db.query(ChatGroupMember, User)
        .join(User, User.id == ChatGroupMember.user_id)
        .filter(ChatGroupMember.group_id == group_id)
        .order_by(ChatGroupMember.joined_at.asc(), ChatGroupMember.id.asc())
        .all()
    )


def _group_member_ids(db: Session, group_id: int) -> List[int]:
    rows = db.query(ChatGroupMember.user_id).filter(ChatGroupMember.group_id == group_id).all()
    return [int(row[0]) for row in rows]


def _find_group_member(db: Session, group_id: int, user_id: int) -> Optional[ChatGroupMember]:
    return (
        db.query(ChatGroupMember)
        .filter(ChatGroupMember.group_id == group_id, ChatGroupMember.user_id == user_id)
        .first()
    )


def _require_group_member(
    db: Session,
    group_id: int,
    user_id: int,
    require_owner: bool = False,
) -> tuple[ChatGroup, ChatGroupMember]:
    """校验群组成员身份（REST 抛 403/404，WebSocket 层捕获后回 error）。"""
    group = db.query(ChatGroup).filter(ChatGroup.id == int(group_id)).first()
    if not group:
        raise HTTPException(status_code=404, detail="群组不存在")
    membership = _find_group_member(db, group.id, user_id)
    if not membership:
        raise HTTPException(status_code=403, detail="你不是该群组成员，无权访问")
    if require_owner and int(group.owner_id) != int(user_id):
        raise HTTPException(status_code=403, detail="仅群主可执行该操作")
    return group, membership


def _group_dict(
    db: Session,
    group: ChatGroup,
    current_user_id: int,
    online_ids: Optional[set[int]] = None,
    member_rows: Optional[List[tuple[ChatGroupMember, User]]] = None,
) -> dict:
    online = manager.online_ids() if online_ids is None else online_ids
    rows = member_rows if member_rows is not None else _group_members(db, group.id)
    current_row = next((row for row, _user in rows if int(row.user_id) == int(current_user_id)), None)
    retention_cutoff = datetime.utcnow() - timedelta(days=CHAT_RETENTION_DAYS)
    unread_query = db.query(func.count(ChatMessage.id)).filter(
        ChatMessage.group_id == group.id,
        ChatMessage.sender_id != current_user_id,
        ChatMessage.message_type != "whiteboard",
        ChatMessage.recalled_at.is_(None),
        ChatMessage.created_at >= retention_cutoff,
    )
    if current_row and current_row.last_read_at:
        unread_query = unread_query.filter(ChatMessage.created_at > current_row.last_read_at)
    unread = int(unread_query.scalar() or 0)

    last_message = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.group_id == group.id,
            ChatMessage.message_type != "whiteboard",
            ChatMessage.created_at >= retention_cutoff,
        )
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .first()
    )
    last_payload = None
    if last_message:
        sender_name = next(
            (
                (user.real_name or user.username)
                for _member, user in rows
                if int(user.id) == int(last_message.sender_id)
            ),
            "",
        )
        last_payload = {
            "content": "[消息已撤回]" if last_message.recalled_at else (last_message.content or "")[:80],
            "created_at": last_message.created_at.isoformat() if last_message.created_at else None,
            "sender_id": last_message.sender_id,
            "sender_name": sender_name,
            "message_type": last_message.message_type,
        }

    members = [
        {
            **_user_dict(user, user.id in online),
            "role": member.role or "member",
            "joined_at": member.joined_at.isoformat() if member.joined_at else None,
            "last_read_at": member.last_read_at.isoformat() if member.last_read_at else None,
        }
        for member, user in rows
    ]
    return {
        "id": group.id,
        "name": group.name,
        "owner_id": group.owner_id,
        "created_at": group.created_at.isoformat() if group.created_at else None,
        "member_count": len(members),
        "online_count": sum(1 for _member, user in rows if user.id in online),
        "members": members,
        "unread": unread,
        "last_message": last_payload,
        "is_owner": int(group.owner_id) == int(current_user_id),
    }


def _attachment_map(db: Session, rows: List[ChatMessage]) -> Dict[int, ChatAttachment]:
    attachment_ids = [row.attachment_id for row in rows if row.attachment_id]
    if not attachment_ids:
        return {}
    return {
        item.id: item
        for item in db.query(ChatAttachment).filter(ChatAttachment.id.in_(attachment_ids)).all()
    }


def _users_map(db: Session, user_ids: List[int]) -> Dict[int, User]:
    unique_ids = {int(user_id) for user_id in user_ids if user_id}
    if not unique_ids:
        return {}
    return {
        user.id: user
        for user in db.query(User).filter(User.id.in_(unique_ids)).all()
    }


def _presence_payload(db: Session) -> dict:
    online = manager.online_ids()
    users = (
        db.query(User)
        .filter(User.is_active.is_(True))
        .order_by(User.real_name.asc(), User.username.asc())
        .all()
    )
    return {
        "type": "presence",
        "users": [_user_dict(user, user.id in online) for user in users],
        "online_ids": sorted(online),
    }


def _preference_defaults() -> dict:
    return {
        "enabled": True,
        "shortcuts": list(DEFAULT_SETTINGS["shortcuts"]),
        "custom_shortcuts": [],
        "recent": [],
        "position": None,
    }


def _normalize_preferences(raw: Optional[dict]) -> dict:
    base = _preference_defaults()
    if not isinstance(raw, dict):
        return base
    if "enabled" in raw:
        base["enabled"] = bool(raw.get("enabled"))
    shortcuts = raw.get("shortcuts")
    if isinstance(shortcuts, list):
        base["shortcuts"] = [
            str(item)[:64] for item in shortcuts
            if isinstance(item, (str, int)) and str(item).strip()
        ][:10]
    custom_shortcuts = raw.get("custom_shortcuts")
    if isinstance(custom_shortcuts, list):
        clean_custom = []
        seen_paths = set()
        for item in custom_shortcuts[:20]:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip()[:300]
            if not path or not (path.startswith("/") or path.startswith(("http://", "https://"))):
                continue
            if path in seen_paths:
                continue
            seen_paths.add(path)
            shortcut_id = str(item.get("id") or "").strip()[:64]
            if not shortcut_id.startswith("custom_"):
                shortcut_id = f"custom_{len(clean_custom) + 1}"
            clean_custom.append({
                "id": shortcut_id,
                "label": str(item.get("label") or path)[:24],
                "path": path,
                "icon": str(item.get("icon") or "Link")[:32],
            })
        base["custom_shortcuts"] = clean_custom

    recent = raw.get("recent")
    if isinstance(recent, list):
        clean = []
        seen = set()
        for item in recent:
            if not isinstance(item, dict):
                continue
            path = str(item.get("path") or "").strip()[:300]
            if not path or path in seen:
                continue
            seen.add(path)
            clean.append({
                "path": path,
                "title": str(item.get("title") or "").strip()[:80],
                "visited_at": str(item.get("visited_at") or "")[:40],
            })
        base["recent"] = clean[:3]
    position = raw.get("position")
    if isinstance(position, dict):
        try:
            base["position"] = {
                "x": max(0.0, min(20000.0, float(position.get("x")))),
                "y": max(0.0, min(20000.0, float(position.get("y")))),
            }
        except (TypeError, ValueError):
            base["position"] = None
    else:
        base["position"] = None
    return base


def _get_preference(db: Session, user_id: int) -> ImPreference:
    row = db.query(ImPreference).filter(ImPreference.user_id == user_id).first()
    if not row:
        row = ImPreference(user_id=user_id, settings=_preference_defaults())
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


@router.get("/users")
def list_users(db: Session = Depends(get_db), current: User = Depends(auth_service.get_current_user)):
    online = manager.online_ids()
    users = (
        db.query(User)
        .filter(User.is_active.is_(True), User.id != current.id)
        .order_by(User.real_name.asc(), User.username.asc())
        .all()
    )
    unread_rows = (
        db.query(ChatMessage.sender_id, func.count(ChatMessage.id))
        .filter(
            ChatMessage.recipient_id == current.id,
            ChatMessage.read_at.is_(None),
            ChatMessage.recalled_at.is_(None),
            ChatMessage.created_at >= datetime.utcnow() - timedelta(days=CHAT_RETENTION_DAYS),
            or_(ChatMessage.recipient_deleted.is_(False), ChatMessage.recipient_deleted.is_(None)),
        )
        .group_by(ChatMessage.sender_id)
        .all()
    )
    unread = {int(sender_id): int(count) for sender_id, count in unread_rows}
    return {
        "items": [
            {**_user_dict(user, user.id in online), "unread": unread.get(user.id, 0)}
            for user in users
        ],
        "me": _user_dict(current),
        "online_ids": sorted(online),
        "unread": unread,
        "retention_days": CHAT_RETENTION_DAYS,
    }


@router.get("/messages/{peer_id}")
def list_messages(
    peer_id: int,
    limit: int = Query(100, ge=1, le=300),
    db: Session = Depends(get_db),
    current: User = Depends(auth_service.get_current_user),
):
    peer = db.query(User).filter(User.id == peer_id, User.is_active.is_(True)).first()
    if not peer:
        raise HTTPException(status_code=404, detail="用户不存在")
    retention_cutoff = datetime.utcnow() - timedelta(days=CHAT_RETENTION_DAYS)
    rows = (
        db.query(ChatMessage)
        .filter(or_(
            and_(ChatMessage.sender_id == current.id, ChatMessage.recipient_id == peer_id),
            and_(ChatMessage.sender_id == peer_id, ChatMessage.recipient_id == current.id),
        ), ChatMessage.group_id.is_(None),
            ChatMessage.created_at >= retention_cutoff, _visible_message_filter(current.id))
        .order_by(ChatMessage.created_at.asc())
        .limit(limit)
        .all()
    )
    now = datetime.utcnow()
    changed = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.sender_id == peer_id,
            ChatMessage.recipient_id == current.id,
            ChatMessage.read_at.is_(None),
        )
        .update({ChatMessage.read_at: now}, synchronize_session=False)
    )
    if changed:
        db.commit()
    attachments = {
        item.id: item for item in db.query(ChatAttachment).filter(
            ChatAttachment.id.in_([row.attachment_id for row in rows if row.attachment_id])
        ).all()
    } if rows else {}
    return {
        "items": [_message_dict(item, attachments.get(item.attachment_id)) for item in rows],
        "peer": _user_dict(peer, peer.id in manager.online_ids()),
        "retention_days": CHAT_RETENTION_DAYS,
    }


@router.post("/messages/{message_id}/recall")
async def recall_message(
    message_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(auth_service.get_current_user),
):
    """发送方在 2 分钟内撤回消息，双方（群聊为全体在线成员）实时替换为撤回提示。"""
    message = db.query(ChatMessage).filter(
        ChatMessage.id == message_id,
        or_(ChatMessage.sender_id == current.id, ChatMessage.recipient_id == current.id),
    ).first()
    if message and message.group_id:
        # 群聊消息：只有发送者本人可撤回，且发送者仍是群成员
        _require_group_member(db, message.group_id, current.id)
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")
    if message.sender_id != current.id:
        raise HTTPException(status_code=403, detail="只能撤回自己发送的消息")
    if message.recalled_at:
        raise HTTPException(status_code=400, detail="消息已撤回")
    if not message.created_at or (datetime.utcnow() - message.created_at).total_seconds() > MESSAGE_RECALL_SECONDS:
        raise HTTPException(status_code=400, detail="超过 2 分钟，无法撤回")

    attachment = db.query(ChatAttachment).filter(ChatAttachment.message_id == message.id).first()
    if attachment:
        try:
            _attachment_path(attachment).unlink(missing_ok=True)
        except OSError:
            pass
        db.delete(attachment)
    message.content = ""
    message.attachment_id = None
    message.message_type = "text"
    message.recalled_at = datetime.utcnow()
    message.recalled_by = current.id
    db.commit()
    db.refresh(message)
    outgoing = _message_dict(message)
    event = {"type": "message-recall", "by": current.id, "message": outgoing}
    if message.group_id:
        for member_id in _group_member_ids(db, message.group_id):
            await manager.send_to(member_id, event)
    else:
        await manager.send_to(message.recipient_id, event)
        await manager.send_to(message.sender_id, event)
    return {"message": outgoing, "recall_seconds": MESSAGE_RECALL_SECONDS}


@router.delete("/messages/{message_id}")
def delete_message(
    message_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(auth_service.get_current_user),
):
    """单聊：删除当前账号会话中的消息（对方仍保留）；群聊：仅发送者本人可隐藏。"""
    message = db.query(ChatMessage).filter(
        ChatMessage.id == message_id,
        or_(ChatMessage.sender_id == current.id, ChatMessage.recipient_id == current.id),
    ).first()
    if not message:
        raise HTTPException(status_code=404, detail="消息不存在")
    if message.group_id:
        _require_group_member(db, message.group_id, current.id)
        if message.sender_id != current.id:
            raise HTTPException(status_code=403, detail="群聊消息仅发送者本人可删除")
        message.sender_deleted = True
    elif message.sender_id == current.id:
        message.sender_deleted = True
    else:
        message.recipient_deleted = True
    db.commit()
    return {"message_id": message.id, "deleted": True}


@router.get("/unread")
def unread_counts(db: Session = Depends(get_db), current: User = Depends(auth_service.get_current_user)):
    rows = (
        db.query(ChatMessage.sender_id, func.count(ChatMessage.id))
        .filter(
            ChatMessage.recipient_id == current.id,
            ChatMessage.read_at.is_(None),
            ChatMessage.recalled_at.is_(None),
            ChatMessage.created_at >= datetime.utcnow() - timedelta(days=CHAT_RETENTION_DAYS),
            or_(ChatMessage.recipient_deleted.is_(False), ChatMessage.recipient_deleted.is_(None)),
        )
        .group_by(ChatMessage.sender_id)
        .all()
    )
    counts = {str(sender_id): int(count) for sender_id, count in rows}

    # 群聊未读：按成员的 last_read_at 游标统计（白板笔画不计入未读）
    group_counts: Dict[str, int] = {}
    memberships = (
        db.query(ChatGroupMember, ChatGroup)
        .join(ChatGroup, ChatGroup.id == ChatGroupMember.group_id)
        .filter(ChatGroupMember.user_id == current.id)
        .all()
    )
    retention_cutoff = datetime.utcnow() - timedelta(days=CHAT_RETENTION_DAYS)
    for membership, group in memberships:
        query = db.query(func.count(ChatMessage.id)).filter(
            ChatMessage.group_id == group.id,
            ChatMessage.sender_id != current.id,
            ChatMessage.message_type != "whiteboard",
            ChatMessage.recalled_at.is_(None),
            ChatMessage.created_at >= retention_cutoff,
        )
        if membership.last_read_at:
            query = query.filter(ChatMessage.created_at > membership.last_read_at)
        count = int(query.scalar() or 0)
        if count:
            group_counts[str(group.id)] = count
    return {
        "counts": counts,
        "total": sum(counts.values()),
        "group_counts": group_counts,
        "group_total": sum(group_counts.values()),
        "retention_days": CHAT_RETENTION_DAYS,
    }


# ==================== 群组 REST 接口 ====================

def _purge_group_data(db: Session, group_id: int) -> int:
    """删除群组全部消息、附件及其物理文件（群组解散时提前清理）。"""
    message_ids = [
        int(row[0])
        for row in db.query(ChatMessage.id).filter(ChatMessage.group_id == group_id).all()
    ]
    if not message_ids:
        return 0
    attachments = (
        db.query(ChatAttachment)
        .filter(ChatAttachment.message_id.in_(message_ids))
        .all()
    )
    for attachment in attachments:
        try:
            _attachment_path(attachment).unlink(missing_ok=True)
        except OSError:
            pass
    if attachments:
        db.query(ChatAttachment).filter(
            ChatAttachment.id.in_([item.id for item in attachments])
        ).delete(synchronize_session=False)
    db.query(ChatMessage).filter(ChatMessage.id.in_(message_ids)).delete(synchronize_session=False)
    return len(message_ids)


async def _broadcast_group_update(
    db: Session, group_id: int, action: str, extra_user_ids: Optional[List[int]] = None
) -> None:
    """群组结构变化后通知在线成员刷新群列表（不带敏感数据）。"""
    recipients = set(_group_member_ids(db, group_id))
    recipients.update(int(uid) for uid in (extra_user_ids or []))
    online = manager.online_ids()
    payload = {"type": "group-updated", "group_id": int(group_id), "action": action}
    for user_id in recipients:
        if user_id in online:
            await manager.send_to(user_id, payload)


@router.get("/groups")
def list_groups(db: Session = Depends(get_db), current: User = Depends(auth_service.get_current_user)):
    """当前用户加入的群组列表（含成员、在线人数、未读数与最近消息摘要）。"""
    groups = (
        db.query(ChatGroup)
        .join(ChatGroupMember, ChatGroupMember.group_id == ChatGroup.id)
        .filter(ChatGroupMember.user_id == current.id)
        .order_by(ChatGroup.created_at.desc(), ChatGroup.id.desc())
        .all()
    )
    online = manager.online_ids()
    items = [
        _group_dict(db, group, current.id, online_ids=online, member_rows=_group_members(db, group.id))
        for group in groups
    ]
    group_unread = {str(item["id"]): int(item["unread"]) for item in items}
    return {
        "items": items,
        "group_unread": group_unread,
        "group_total": sum(group_unread.values()),
        "limits": {
            "name_max_length": GROUP_NAME_MAX_LENGTH,
            "max_members": GROUP_MAX_MEMBERS,
            "max_message_length": MAX_MESSAGE_LENGTH,
        },
        "retention_days": CHAT_RETENTION_DAYS,
    }


@router.post("/groups")
async def create_group(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current: User = Depends(auth_service.get_current_user),
):
    """创建群组：创建者自动成为群主和成员，其余成员 ID 需为有效账号。"""
    name = im_group_service.normalize_group_name(payload.get("name"))
    if not name:
        raise HTTPException(status_code=400, detail="群名称不能为空")
    raw_member_ids = payload.get("member_ids")
    if raw_member_ids is None:
        raw_member_ids = payload.get("memberIds")
    member_ids = [
        user_id
        for user_id in im_group_service.normalize_user_ids(raw_member_ids)
        if user_id != current.id
    ]
    if len(member_ids) + 1 > GROUP_MAX_MEMBERS:
        raise HTTPException(status_code=400, detail=f"群成员不能超过 {GROUP_MAX_MEMBERS} 人")
    members: List[User] = []
    if member_ids:
        members = (
            db.query(User)
            .filter(User.id.in_(member_ids), User.is_active.is_(True))
            .all()
        )
        if len(members) != len(member_ids):
            raise HTTPException(status_code=400, detail="部分成员不存在或已被停用")

    group = ChatGroup(name=name, owner_id=current.id, created_at=datetime.utcnow())
    db.add(group)
    db.flush()
    db.add(ChatGroupMember(
        group_id=group.id, user_id=current.id, role="owner", joined_at=datetime.utcnow(),
    ))
    for member in members:
        db.add(ChatGroupMember(
            group_id=group.id, user_id=member.id, role="member", joined_at=datetime.utcnow(),
        ))
    db.commit()
    db.refresh(group)
    await _broadcast_group_update(db, group.id, "created")
    return {
        "group": _group_dict(db, group, current.id),
        "retention_days": CHAT_RETENTION_DAYS,
    }


@router.get("/groups/{group_id}")
def get_group(
    group_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(auth_service.get_current_user),
):
    group, _membership = _require_group_member(db, group_id, current.id)
    return {
        "group": _group_dict(db, group, current.id),
        "retention_days": CHAT_RETENTION_DAYS,
    }


@router.get("/groups/{group_id}/members")
def list_group_members(
    group_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(auth_service.get_current_user),
):
    group, _membership = _require_group_member(db, group_id, current.id)
    rows = _group_members(db, group.id)
    online = manager.online_ids()
    return {
        "group_id": group.id,
        "items": [
            {
                **_user_dict(user, user.id in online),
                "role": member.role or "member",
                "joined_at": member.joined_at.isoformat() if member.joined_at else None,
            }
            for member, user in rows
        ],
        "max_members": GROUP_MAX_MEMBERS,
    }


@router.post("/groups/{group_id}/members")
async def add_group_members(
    group_id: int,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current: User = Depends(auth_service.get_current_user),
):
    """群主添加成员；重复成员自动忽略。"""
    group, _membership = _require_group_member(db, group_id, current.id, require_owner=True)
    raw_ids = payload.get("user_ids")
    if raw_ids is None:
        raw_ids = payload.get("userIds")
    user_ids = [
        user_id
        for user_id in im_group_service.normalize_user_ids(raw_ids)
        if user_id != group.owner_id
    ]
    existing_ids = set(_group_member_ids(db, group.id))
    new_ids = [user_id for user_id in user_ids if user_id not in existing_ids]
    if not new_ids:
        return {"group": _group_dict(db, group, current.id), "added": []}
    users = db.query(User).filter(User.id.in_(new_ids), User.is_active.is_(True)).all()
    if len(users) != len(new_ids):
        raise HTTPException(status_code=400, detail="部分用户不存在或已被停用")
    if len(existing_ids) + len(new_ids) > GROUP_MAX_MEMBERS:
        raise HTTPException(status_code=400, detail=f"群成员不能超过 {GROUP_MAX_MEMBERS} 人")
    for user in users:
        db.add(ChatGroupMember(
            group_id=group.id, user_id=user.id, role="member", joined_at=datetime.utcnow(),
        ))
    db.commit()
    await _broadcast_group_update(db, group.id, "member-added", extra_user_ids=new_ids)
    return {
        "group": _group_dict(db, group, current.id),
        "added": [_user_dict(user, user.id in manager.online_ids()) for user in users],
    }


@router.delete("/groups/{group_id}/members/{user_id}")
async def remove_group_member(
    group_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(auth_service.get_current_user),
):
    """群主移除成员（不能移除群主本人）。"""
    group, _membership = _require_group_member(db, group_id, current.id, require_owner=True)
    if int(user_id) == int(group.owner_id):
        raise HTTPException(status_code=400, detail="不能移除群主")
    target = _find_group_member(db, group.id, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="该用户不在群组中")
    db.delete(target)
    db.commit()
    await _broadcast_group_update(db, group.id, "member-removed", extra_user_ids=[int(user_id)])
    return {"removed": int(user_id), "group": _group_dict(db, group, current.id)}


@router.post("/groups/{group_id}/leave")
async def leave_group(
    group_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(auth_service.get_current_user),
):
    """退出群组：群主退出时自动移交给最早加入的成员；最后一人退出则解散群聊。"""
    group, membership = _require_group_member(db, group_id, current.id)
    remaining = (
        db.query(ChatGroupMember)
        .filter(ChatGroupMember.group_id == group.id, ChatGroupMember.user_id != current.id)
        .order_by(ChatGroupMember.joined_at.asc(), ChatGroupMember.id.asc())
        .all()
    )
    db.delete(membership)
    dissolved = False
    owner_changed_to = None
    if int(group.owner_id) == int(current.id):
        if remaining:
            new_owner = remaining[0]
            group.owner_id = int(new_owner.user_id)
            new_owner.role = "owner"
            owner_changed_to = int(new_owner.user_id)
        else:
            dissolved = True
            _purge_group_data(db, group.id)
            db.delete(group)
    db.commit()
    if not dissolved:
        await _broadcast_group_update(db, group.id, "left", extra_user_ids=[int(current.id)])
        if owner_changed_to:
            await _broadcast_group_update(db, group.id, "owner-changed")
    return {"left": True, "dissolved": dissolved, "owner_id": owner_changed_to}


@router.get("/groups/{group_id}/messages")
def list_group_messages(
    group_id: int,
    limit: int = Query(100, ge=1, le=300),
    db: Session = Depends(get_db),
    current: User = Depends(auth_service.get_current_user),
):
    """群聊历史（15 天内，白板笔画不进入聊天记录），并把已读游标推进到当前时间。"""
    group, membership = _require_group_member(db, group_id, current.id)
    retention_cutoff = datetime.utcnow() - timedelta(days=CHAT_RETENTION_DAYS)
    rows = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.group_id == group.id,
            ChatMessage.message_type != "whiteboard",
            ChatMessage.created_at >= retention_cutoff,
            _group_visible_filter(current.id),
        )
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    attachments = _attachment_map(db, rows)
    senders = _users_map(db, [row.sender_id for row in rows])
    membership.last_read_at = datetime.utcnow()
    db.commit()
    return {
        "items": [
            _message_dict(row, attachments.get(row.attachment_id), senders.get(row.sender_id))
            for row in rows
        ],
        "group": _group_dict(db, group, current.id),
        "retention_days": CHAT_RETENTION_DAYS,
    }


@router.get("/groups/{group_id}/whiteboard")
def list_group_whiteboard(
    group_id: int,
    limit: int = Query(500, ge=1, le=1000),
    db: Session = Depends(get_db),
    current: User = Depends(auth_service.get_current_user),
):
    """群白板笔画（15 天保留期，按时间升序返回，供重新进入白板时回放）。"""
    group, _membership = _require_group_member(db, group_id, current.id)
    retention_cutoff = datetime.utcnow() - timedelta(days=CHAT_RETENTION_DAYS)
    rows = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.group_id == group.id,
            ChatMessage.message_type == "whiteboard",
            ChatMessage.created_at >= retention_cutoff,
            _group_visible_filter(current.id),
        )
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    strokes = []
    for row in rows:
        try:
            payload = json.loads(row.content or "{}")
        except (TypeError, ValueError):
            continue
        stroke = payload.get("stroke") if isinstance(payload, dict) else None
        if not isinstance(stroke, dict):
            continue
        strokes.append({
            **stroke,
            "id": f"wb-{row.id}",
            "sender_id": row.sender_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })
    return {
        "strokes": strokes,
        "board_id": "main",
        "retention_days": CHAT_RETENTION_DAYS,
    }





def _split_webrtc_urls(raw: str) -> List[str]:
    return [item.strip() for item in str(raw or "").replace(";", ",").replace("\n", ",").split(",") if item.strip()]


@router.get("/webrtc-config")
def get_webrtc_config(current: User = Depends(auth_service.get_current_user)):
    """局域网优先的 ICE 配置；TURN 可通过环境变量按现场网络启用。"""
    ice_servers = []
    stun_urls = _split_webrtc_urls(getattr(Config, "WEBRTC_STUN_URLS", ""))
    if stun_urls:
        ice_servers.append({"urls": stun_urls})
    turn_urls = _split_webrtc_urls(getattr(Config, "WEBRTC_TURN_URLS", ""))
    if turn_urls:
        turn_urls = [url if ":" in url.split("?")[0] else f"turn:{url}" for url in turn_urls]
        turn = {"urls": turn_urls}
        username = str(getattr(Config, "WEBRTC_TURN_USERNAME", "") or "").strip()
        credential = str(getattr(Config, "WEBRTC_TURN_CREDENTIAL", "") or "").strip()
        if username:
            turn["username"] = username
            turn["credential"] = credential
        ice_servers.append(turn)
    force_relay = bool(getattr(Config, "WEBRTC_FORCE_RELAY", False)) and bool(turn_urls)
    return {
        "iceServers": ice_servers,
        "iceTransportPolicy": "relay" if force_relay else "all",
        "iceCandidatePoolSize": 2,
        "mode": "lan-turn" if turn_urls else "lan-direct",
        "turn_configured": bool(turn_urls),
    }


@router.get("/preferences")
def get_preferences(db: Session = Depends(get_db), current: User = Depends(auth_service.get_current_user)):
    row = _get_preference(db, current.id)
    return {"settings": _normalize_preferences(row.settings)}


@router.put("/preferences")
def update_preferences(
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current: User = Depends(auth_service.get_current_user),
):
    row = _get_preference(db, current.id)
    incoming = payload.get("settings") if isinstance(payload.get("settings"), dict) else payload
    merged = _normalize_preferences({**(row.settings or {}), **(incoming or {})})
    row.settings = merged
    row.updated_at = datetime.utcnow()
    db.commit()
    return {"settings": row.settings}


def _ws_user(token: str, db: Session) -> Optional[User]:
    try:
        payload = auth_service.decode_token(token)
        user = db.query(User).filter(User.id == int(payload.get("sub"))).first()
    except Exception:  # noqa: BLE001 - 过期/非法 token 统一按未登录处理
        return None
    if not user or not user.is_active:
        return None
    return user


def _attachment_path(attachment: ChatAttachment) -> Path:
    return ATTACHMENT_ROOT / str(attachment.stored_name).replace("\\", "/")


def _safe_attachment_name(filename: str) -> str:
    name = os.path.basename(str(filename or "file")).replace("\x00", "").strip()
    return (name or "file")[:255]


@router.post("/upload")
async def upload_attachment(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current: User = Depends(auth_service.get_current_user),
):
    """上传图片或文件，单文件最大 500MB；保存 15 天后随消息清理。"""
    original_name = _safe_attachment_name(file.filename or "file")
    mime = file.content_type or mimetypes.guess_type(original_name)[0] or "application/octet-stream"
    suffix = Path(original_name).suffix.lower()[:20]
    stored_name = f"{datetime.utcnow().strftime('%Y%m')}/{uuid.uuid4().hex}{suffix}"
    target = ATTACHMENT_ROOT / stored_name
    target.parent.mkdir(parents=True, exist_ok=True)
    size = 0
    try:
        with target.open("wb") as output:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_ATTACHMENT_BYTES:
                    raise HTTPException(status_code=413, detail="单个文件不能超过 500MB")
                output.write(chunk)
    except HTTPException:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    except Exception as exc:  # noqa: BLE001
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(status_code=500, detail=f"文件保存失败: {exc}") from exc
    finally:
        await file.close()

    if size <= 0:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise HTTPException(status_code=400, detail="不能上传空文件")

    attachment = ChatAttachment(
        uploader_id=current.id,
        original_name=original_name,
        stored_name=stored_name,
        mime_type=mime[:200],
        size=size,
        created_at=datetime.utcnow(),
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return {
        "attachment": _attachment_dict(attachment),
        "retention_days": CHAT_RETENTION_DAYS,
        "max_size": MAX_ATTACHMENT_BYTES,
    }


@router.get("/files/{attachment_id}")
def get_attachment(
    attachment_id: int,
    db: Session = Depends(get_db),
    current: User = Depends(auth_service.get_current_user),
):
    """附件下载/图片预览；支持 ?token= 供 img/video 标签直接访问。"""
    attachment = db.query(ChatAttachment).filter(ChatAttachment.id == attachment_id).first()
    if not attachment:
        raise HTTPException(status_code=404, detail="附件不存在")
    allowed = attachment.uploader_id == current.id
    if not allowed and attachment.message_id:
        message = db.query(ChatMessage).filter(ChatMessage.id == attachment.message_id).first()
        if message and message.group_id:
            # 群聊附件：群成员均可访问
            allowed = _find_group_member(db, message.group_id, current.id) is not None
        elif message:
            allowed = current.id in (message.sender_id, message.recipient_id)
    if not allowed:
        raise HTTPException(status_code=403, detail="无权访问该附件")
    path = _attachment_path(attachment)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="附件文件已被清理")
    mime = attachment.mime_type or mimetypes.guess_type(attachment.original_name)[0] or "application/octet-stream"
    disposition = "inline" if mime.startswith("image/") else "attachment"
    from urllib.parse import quote
    headers = {
        "Content-Disposition": f"{disposition}; filename*=UTF-8''{quote(attachment.original_name)}",
        "Cache-Control": "private, max-age=3600",
    }
    return FileResponse(path, media_type=mime, headers=headers)


def cleanup_expired_messages(db: Session) -> dict:
    """删除超过 15 天的全部聊天记录及其附件文件。

    群聊消息、群聊附件和持久化的白板笔画都落在 chat_messages / chat_attachments
    两张表中，因此这里按统一的 15 天截止时间一并清理。
    """
    cutoff = datetime.utcnow() - timedelta(days=CHAT_RETENTION_DAYS)
    expired_messages = db.query(ChatMessage).filter(ChatMessage.created_at < cutoff).all()
    message_ids = [item.id for item in expired_messages]
    whiteboard_count = sum(1 for item in expired_messages if item.message_type == "whiteboard")
    group_count = sum(1 for item in expired_messages if item.group_id is not None)
    expired_attachments = db.query(ChatAttachment).filter(
        or_(
            ChatAttachment.created_at < cutoff,
            ChatAttachment.message_id.in_(message_ids) if message_ids else False,
        )
    ).all()
    removed_files = 0
    for attachment in expired_attachments:
        try:
            _attachment_path(attachment).unlink(missing_ok=True)
            removed_files += 1
        except OSError:
            pass
    if expired_attachments:
        db.query(ChatAttachment).filter(
            ChatAttachment.id.in_([item.id for item in expired_attachments])
        ).delete(synchronize_session=False)
    if message_ids:
        db.query(ChatMessage).filter(ChatMessage.id.in_(message_ids)).delete(synchronize_session=False)
    db.commit()
    return {
        "messages": len(message_ids),
        "files": removed_files,
        "group_messages": group_count,
        "whiteboard": whiteboard_count,
    }


# ==================== WebSocket 群组 / 群通话 / 白板处理 ====================

async def _ws_error(websocket: WebSocket, message: str, **extra) -> None:
    try:
        await websocket.send_json({"type": "error", "message": message, **extra})
    except Exception:  # noqa: BLE001
        pass


def _resolve_group(db: Session, raw_group_id: Any, user_id: int) -> Optional[ChatGroup]:
    """WebSocket 侧群组访问控制：群存在且当前用户是成员。"""
    try:
        group_id = int(raw_group_id)
    except (TypeError, ValueError):
        return None
    if group_id <= 0:
        return None
    group = db.query(ChatGroup).filter(ChatGroup.id == group_id).first()
    if not group or not _find_group_member(db, group.id, user_id):
        return None
    return group


async def _broadcast_group(db: Session, group_id: int, payload: dict, exclude_user_id: Optional[int] = None) -> None:
    """只向在线的群成员广播，避免越权下发。"""
    member_ids = _group_member_ids(db, group_id)
    online = manager.online_ids()
    for user_id in member_ids:
        if exclude_user_id is not None and int(user_id) == int(exclude_user_id):
            continue
        if user_id in online:
            await manager.send_to(user_id, payload)


def _call_participants_payload(db: Session, call: dict) -> List[dict]:
    participant_ids = sorted(call["participants"].keys())
    users = _users_map(db, participant_ids)
    online = manager.online_ids()
    result = []
    for user_id in participant_ids:
        state = call["participants"].get(user_id) or {}
        user = users.get(user_id)
        base = _user_dict(user, user_id in online) if user else {
            "id": user_id,
            "username": f"user-{user_id}",
            "real_name": f"用户 {user_id}",
            "is_superuser": False,
            "email": "",
            "phone": "",
            "online": user_id in online,
        }
        result.append({
            **base,
            "muted": bool(state.get("muted")),
            "camera": bool(state.get("camera")),
            "joined": bool(state.get("joined", True)),
            "joined_at": state["joined_at"].isoformat() if state.get("joined_at") else None,
        })
    return result


async def _handle_group_message(websocket: WebSocket, db: Session, user: User, payload: dict) -> None:
    group = _resolve_group(db, payload.get("group_id"), user.id)
    if not group:
        await _ws_error(websocket, "群组不存在或你不是群成员")
        return
    content = str(payload.get("content") or "").strip()
    attachment = None
    attachment_raw = payload.get("attachment_id")
    if attachment_raw not in (None, "", 0, "0"):
        try:
            attachment_id = int(attachment_raw)
        except (TypeError, ValueError):
            await _ws_error(websocket, "附件参数不合法")
            return
        attachment = db.query(ChatAttachment).filter(
            ChatAttachment.id == attachment_id,
            ChatAttachment.uploader_id == user.id,
            ChatAttachment.message_id.is_(None),
        ).first()
        if not attachment:
            await _ws_error(websocket, "附件不存在、已使用或无权发送")
            return
    if (not content and not attachment) or len(content) > MAX_MESSAGE_LENGTH:
        await _ws_error(websocket, f"消息内容不能为空或超过 {MAX_MESSAGE_LENGTH} 字")
        return
    message_type = "text"
    if attachment:
        message_type = "image" if (attachment.mime_type or "").startswith("image/") else "file"
    message = ChatMessage(
        sender_id=user.id,
        recipient_id=None,
        group_id=group.id,
        content=content or attachment.original_name,
        message_type=message_type,
        attachment_id=attachment.id if attachment else None,
    )
    try:
        db.add(message)
        db.flush()
        if attachment:
            attachment.message_id = message.id
        db.commit()
        db.refresh(message)
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        logger.warning("群消息写入失败（群 %s）: %s", group.id, exc)
        await _ws_error(websocket, "群消息发送失败，请稍后重试")
        return
    outgoing = _message_dict(message, attachment, sender=user)
    event = {
        "type": "message",
        "group_id": group.id,
        "from": _user_dict(user, True),
        "message": outgoing,
    }
    member_ids = _group_member_ids(db, group.id)
    online = manager.online_ids()
    for member_id in member_ids:
        if int(member_id) == int(user.id):
            continue
        if member_id in online:
            await manager.send_to(member_id, event)
    await websocket.send_json({
        "type": "message-ack",
        "temp_id": payload.get("temp_id"),
        "message": outgoing,
    })


async def _handle_group_typing(websocket: WebSocket, db: Session, user: User, payload: dict) -> None:
    group = _resolve_group(db, payload.get("group_id"), user.id)
    if not group:
        return
    event = {
        "type": "group-typing",
        "group_id": group.id,
        "from": _user_dict(user, True),
        "typing": bool(payload.get("typing")),
    }
    await _broadcast_group(db, group.id, event, exclude_user_id=user.id)


async def _handle_group_read(websocket: WebSocket, db: Session, user: User, payload: dict) -> None:
    group = _resolve_group(db, payload.get("group_id"), user.id)
    if not group:
        return
    membership = _find_group_member(db, group.id, user.id)
    if not membership:
        return
    membership.last_read_at = datetime.utcnow()
    db.commit()
    event = {
        "type": "group-read",
        "group_id": group.id,
        "user_id": user.id,
        "last_read_at": membership.last_read_at.isoformat() if membership.last_read_at else None,
    }
    await _broadcast_group(db, group.id, event)


async def _handle_group_call_event(
    websocket: WebSocket, db: Session, user: User, payload: dict, msg_type: str
) -> None:
    group = _resolve_group(db, payload.get("group_id"), user.id)
    if not group:
        await _ws_error(websocket, "群组不存在或你不是群成员", group_id=payload.get("group_id"))
        return
    call_id = im_group_service.normalize_call_id(payload.get("call_id"))
    if not call_id:
        await _ws_error(websocket, "通话标识不合法", group_id=group.id)
        return

    if msg_type == "group-call-start":
        call_type = "video" if payload.get("call_type") == "video" else "audio"
        if group_call_registry.get(call_id):
            await _ws_error(websocket, "该群通话已存在", group_id=group.id)
            return
        member_ids = _group_member_ids(db, group.id)
        online = manager.online_ids()
        online_others = [uid for uid in member_ids if uid != user.id and uid in online]
        offline_ids = [uid for uid in member_ids if uid != user.id and uid not in online]
        if not online_others:
            await websocket.send_json({
                "type": "call-error",
                "group_id": group.id,
                "message": "当前没有其他在线成员，无法发起群通话",
            })
            return
        call = group_call_registry.start(
            call_id, group.id, call_type, user.id, [user.id, *online_others],
        )
        if not call:
            await _ws_error(websocket, "群通话创建失败", group_id=group.id)
            return
        participants = _call_participants_payload(db, call)
        offline_members = [
            _user_dict(item) for item in _users_map(db, offline_ids).values()
        ]
        await websocket.send_json({
            "type": "group-call-started",
            "group_id": group.id,
            "group_name": group.name,
            "call_id": call_id,
            "call_type": call_type,
            "from": _user_dict(user, True),
            "participants": participants,
            "offline_members": offline_members,
        })
        invite = {
            "type": "group-call-invite",
            "group_id": group.id,
            "group_name": group.name,
            "call_id": call_id,
            "call_type": call_type,
            "from": _user_dict(user, True),
            "participants": participants,
            "offline_members": offline_members,
        }
        for member_id in online_others:
            await manager.send_to(member_id, invite)
        return

    if msg_type == "group-call-join":
        call = group_call_registry.get(call_id)
        if not call or int(call["group_id"]) != int(group.id):
            await websocket.send_json({
                "type": "call-error", "group_id": group.id,
                "message": "群通话已结束", "call_id": call_id,
            })
            return
        group_call_registry.join(call_id, user.id)
        participants = _call_participants_payload(db, call)
        await websocket.send_json({
            "type": "group-call-roster",
            "group_id": group.id,
            "call_id": call_id,
            "call_type": call["call_type"],
            "participants": participants,
        })
        joined_event = {
            "type": "group-call-participant-joined",
            "group_id": group.id,
            "call_id": call_id,
            "user": _user_dict(user, True),
            "participants": participants,
        }
        for member_id in group_call_registry.participant_ids(call_id):
            if int(member_id) == int(user.id):
                continue
            await manager.send_to(member_id, joined_event)
        return

    if msg_type == "group-call-leave":
        existing_call = group_call_registry.get(call_id)
        if not existing_call or int(existing_call["group_id"]) != int(group.id):
            await websocket.send_json({
                "type": "group-call-ended", "group_id": group.id,
                "call_id": call_id, "by": user.id, "reason": "not-found",
            })
            return
        call, remaining = group_call_registry.leave(call_id, user.id)
        if not call or int(call["group_id"]) != int(group.id):
            await websocket.send_json({
                "type": "group-call-ended", "group_id": group.id,
                "call_id": call_id, "by": user.id, "reason": "not-found",
            })
            return
        left_event = {
            "type": "group-call-participant-left",
            "group_id": group.id,
            "call_id": call_id,
            "user_id": user.id,
        }
        for member_id in group_call_registry.participant_ids(call_id):
            await manager.send_to(member_id, left_event)
        if remaining <= 0:
            await _broadcast_group(db, group.id, {
                "type": "group-call-ended", "group_id": group.id,
                "call_id": call_id, "by": user.id, "reason": "empty",
            })
        return

    if msg_type == "group-call-end":
        call = group_call_registry.get(call_id)
        if not call or int(call["group_id"]) != int(group.id):
            await websocket.send_json({
                "type": "group-call-ended", "group_id": group.id,
                "call_id": call_id, "by": user.id, "reason": "not-found",
            })
            return
        if not group_call_registry.is_participant(call_id, user.id):
            await _ws_error(websocket, "你不在该群通话中", group_id=group.id)
            return
        group_call_registry.end(call_id)
        await _broadcast_group(db, group.id, {
            "type": "group-call-ended", "group_id": group.id,
            "call_id": call_id, "by": user.id, "reason": "ended",
        })
        return

    if msg_type == "group-call-media":
        call = group_call_registry.get(call_id)
        if not call or int(call["group_id"]) != int(group.id):
            return
        if not group_call_registry.is_participant(call_id, user.id):
            return
        group_call_registry.set_media(
            call_id, user.id, bool(payload.get("muted")), bool(payload.get("camera")),
        )
        event = {
            "type": "group-call-media",
            "group_id": group.id,
            "call_id": call_id,
            "user_id": user.id,
            "muted": bool(payload.get("muted")),
            "camera": bool(payload.get("camera")),
        }
        for member_id in group_call_registry.participant_ids(call_id):
            if int(member_id) == int(user.id):
                continue
            await manager.send_to(member_id, event)
        return

    if msg_type == "group-call-reject":
        call = group_call_registry.get(call_id)
        if not call or int(call["group_id"]) != int(group.id):
            return
        await manager.send_to(call["owner_id"], {
            "type": "group-call-rejected",
            "group_id": group.id,
            "call_id": call_id,
            "user": _user_dict(user, True),
            "reason": str(payload.get("reason") or "rejected")[:200],
        })
        # 被邀请人拒绝后从登记表移除，其他成员同步移除其画面占位
        group_call_registry.leave(call_id, user.id)
        left_event = {
            "type": "group-call-participant-left",
            "group_id": group.id,
            "call_id": call_id,
            "user_id": user.id,
        }
        remaining = group_call_registry.participant_ids(call_id)
        for member_id in remaining:
            await manager.send_to(member_id, left_event)
        if not remaining:
            await _broadcast_group(db, group.id, {
                "type": "group-call-ended", "group_id": group.id,
                "call_id": call_id, "by": user.id, "reason": "empty",
            })
        return


async def _relay_group_signal(
    websocket: WebSocket, db: Session, user: User, payload: dict, msg_type: str
) -> None:
    """群通话 mesh 信令：call_id + from + to + group_id，逐对转发 SDP/ICE。"""
    group = _resolve_group(db, payload.get("group_id"), user.id)
    if not group:
        await _ws_error(websocket, "群组不存在或你不是群成员")
        return
    call_id = im_group_service.normalize_call_id(payload.get("call_id"))
    call = group_call_registry.get(call_id)
    if not call or int(call["group_id"]) != int(group.id):
        await websocket.send_json({
            "type": "call-error", "group_id": group.id,
            "message": "群通话已结束", "call_id": call_id,
        })
        return
    try:
        target_id = int(payload.get("to"))
    except (TypeError, ValueError):
        await _ws_error(websocket, "通话目标不合法", group_id=group.id)
        return
    if not group_call_registry.is_participant(call_id, user.id) or not group_call_registry.is_participant(call_id, target_id):
        await websocket.send_json({
            "type": "call-error", "group_id": group.id,
            "message": "通话成员不存在或已离开", "call_id": call_id,
        })
        return
    relay = {
        "type": msg_type,
        "from": _user_dict(user, True),
        "to": target_id,
        "call_id": call_id,
        "call_type": call["call_type"],
        "group_id": group.id,
        "sdp": payload.get("sdp"),
        "candidate": payload.get("candidate"),
        "reason": str(payload.get("reason") or "")[:200],
    }
    await manager.send_to(target_id, relay)


def _whiteboard_strokes(db: Session, group_id: int, user_id: int, limit: int = 500) -> List[dict]:
    retention_cutoff = datetime.utcnow() - timedelta(days=CHAT_RETENTION_DAYS)
    rows = (
        db.query(ChatMessage)
        .filter(
            ChatMessage.group_id == group_id,
            ChatMessage.message_type == "whiteboard",
            ChatMessage.created_at >= retention_cutoff,
            _group_visible_filter(user_id),
        )
        .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
        .limit(limit)
        .all()
    )
    rows.reverse()
    strokes = []
    for row in rows:
        try:
            payload = json.loads(row.content or "{}")
        except (TypeError, ValueError):
            continue
        stroke = payload.get("stroke") if isinstance(payload, dict) else None
        if not isinstance(stroke, dict):
            continue
        strokes.append({
            **stroke,
            "id": f"wb-{row.id}",
            "sender_id": row.sender_id,
            "created_at": row.created_at.isoformat() if row.created_at else None,
        })
    return strokes


async def _handle_whiteboard_event(
    websocket: WebSocket, db: Session, user: User, payload: dict, msg_type: str
) -> None:
    group = _resolve_group(db, payload.get("group_id"), user.id)
    if not group:
        await _ws_error(websocket, "群组不存在或你不是群成员")
        return
    board_id = im_group_service.normalize_board_id(payload.get("board_id"))

    if msg_type == "whiteboard-sync":
        await websocket.send_json({
            "type": "whiteboard-state",
            "group_id": group.id,
            "board_id": board_id,
            "strokes": _whiteboard_strokes(db, group.id, user.id),
        })
        return

    if msg_type == "whiteboard-draw":
        stroke = im_group_service.sanitize_stroke(payload.get("stroke"))
        if not stroke:
            await _ws_error(websocket, "白板笔画数据不合法", group_id=group.id)
            return
        temp_id = str((payload.get("stroke") or {}).get("temp_id") or "")[:80]
        content = json.dumps(
            {"board_id": board_id, "stroke": stroke},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        if len(content) > im_group_service.MAX_STROKE_CONTENT_CHARS:
            await _ws_error(websocket, "白板笔画数据过大", group_id=group.id)
            return
        message = ChatMessage(
            sender_id=user.id,
            recipient_id=None,
            group_id=group.id,
            content=content,
            message_type="whiteboard",
        )
        try:
            db.add(message)
            db.commit()
            db.refresh(message)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.warning("白板笔画写入失败（群 %s）: %s", group.id, exc)
            await _ws_error(websocket, "白板笔画保存失败", group_id=group.id)
            return
        outgoing_stroke = {
            **stroke,
            "id": f"wb-{message.id}",
            "temp_id": temp_id or None,
            "sender_id": user.id,
            "created_at": message.created_at.isoformat() if message.created_at else None,
        }
        await _broadcast_group(db, group.id, {
            "type": "whiteboard-stroke",
            "group_id": group.id,
            "board_id": board_id,
            "from": _user_dict(user, True),
            "stroke": outgoing_stroke,
        })
        return

    if msg_type == "whiteboard-clear":
        db.query(ChatMessage).filter(
            ChatMessage.group_id == group.id,
            ChatMessage.message_type == "whiteboard",
        ).delete(synchronize_session=False)
        db.commit()
        await _broadcast_group(db, group.id, {
            "type": "whiteboard-clear",
            "group_id": group.id,
            "board_id": board_id,
            "from": _user_dict(user, True),
        })
        return

    if msg_type == "whiteboard-undo":
        target = (
            db.query(ChatMessage)
            .filter(
                ChatMessage.group_id == group.id,
                ChatMessage.message_type == "whiteboard",
                ChatMessage.sender_id == user.id,
            )
            .order_by(ChatMessage.created_at.desc(), ChatMessage.id.desc())
            .first()
        )
        stroke_id = None
        if target:
            stroke_id = f"wb-{target.id}"
            db.delete(target)
            db.commit()
        await _broadcast_group(db, group.id, {
            "type": "whiteboard-undo",
            "group_id": group.id,
            "board_id": board_id,
            "from": _user_dict(user, True),
            "stroke_id": stroke_id,
        })
        return

    if msg_type == "whiteboard-pointer":
        pointer = im_group_service.sanitize_pointer({
            "x": payload.get("x"),
            "y": payload.get("y"),
            "visible": payload.get("visible", True),
        })
        if not pointer:
            return
        await _broadcast_group(db, group.id, {
            "type": "whiteboard-pointer",
            "group_id": group.id,
            "board_id": board_id,
            "from": _user_dict(user, True),
            **pointer,
        }, exclude_user_id=user.id)
        return


@router.websocket("/ws")
async def chat_websocket(websocket: WebSocket, token: str = Query("")):
    await websocket.accept()
    db = SessionLocal()
    current = _ws_user(token, db)
    if not current:
        await websocket.send_json({"type": "error", "message": "登录状态无效"})
        await websocket.close(code=4401)
        db.close()
        return
    user = current
    await manager.connect(user.id, websocket)
    try:
        await websocket.send_json({"type": "ready", "user": _user_dict(user, True)})
        await manager.broadcast(_presence_payload(db))
        while True:
            try:
                payload = await websocket.receive_json()
            except WebSocketDisconnect:
                break
            if not isinstance(payload, dict):
                continue
            msg_type = str(payload.get("type") or "")
            # ---- 群组 / 群通话 / 白板事件 ----
            if msg_type in GROUP_CALL_TYPES:
                await _handle_group_call_event(websocket, db, user, payload, msg_type)
                continue
            if msg_type in WHITEBOARD_TYPES:
                await _handle_whiteboard_event(websocket, db, user, payload, msg_type)
                continue
            if msg_type == "group-typing" or (msg_type == "typing" and payload.get("group_id")):
                await _handle_group_typing(websocket, db, user, payload)
                continue
            if msg_type == "group-read":
                await _handle_group_read(websocket, db, user, payload)
                continue
            # ---- 消息（单聊 / 群聊） ----
            if msg_type == "message":
                if payload.get("group_id") not in (None, "", 0, "0"):
                    await _handle_group_message(websocket, db, user, payload)
                    continue
                try:
                    recipient_id = int(payload.get("to"))
                except (TypeError, ValueError):
                    await websocket.send_json({"type": "error", "message": "接收人不合法"})
                    continue
                content = str(payload.get("content") or "").strip()
                attachment = None
                attachment_raw = payload.get("attachment_id")
                if attachment_raw not in (None, "", 0, "0"):
                    try:
                        attachment_id = int(attachment_raw)
                    except (TypeError, ValueError):
                        await websocket.send_json({"type": "error", "message": "附件参数不合法"})
                        continue
                    attachment = db.query(ChatAttachment).filter(
                        ChatAttachment.id == attachment_id,
                        ChatAttachment.uploader_id == user.id,
                        ChatAttachment.message_id.is_(None),
                    ).first()
                    if not attachment:
                        await websocket.send_json({"type": "error", "message": "附件不存在、已使用或无权发送"})
                        continue
                if (not content and not attachment) or len(content) > MAX_MESSAGE_LENGTH:
                    await websocket.send_json({"type": "error", "message": f"消息内容不能为空或超过 {MAX_MESSAGE_LENGTH} 字"})
                    continue
                recipient = db.query(User).filter(User.id == recipient_id, User.is_active.is_(True)).first()
                if not recipient or recipient.id == user.id:
                    await websocket.send_json({"type": "error", "message": "接收人不存在"})
                    continue
                message_type = "text"
                if attachment:
                    message_type = "image" if (attachment.mime_type or "").startswith("image/") else "file"
                message = ChatMessage(
                    sender_id=user.id,
                    recipient_id=recipient.id,
                    content=content or attachment.original_name,
                    message_type=message_type,
                    attachment_id=attachment.id if attachment else None,
                )
                db.add(message)
                db.flush()
                if attachment:
                    attachment.message_id = message.id
                db.commit()
                db.refresh(message)
                outgoing = _message_dict(message, attachment)
                await manager.send_to(recipient.id, {
                    "type": "message",
                    "from": _user_dict(user, True),
                    "message": outgoing,
                })
                await websocket.send_json({
                    "type": "message-ack",
                    "temp_id": payload.get("temp_id"),
                    "message": outgoing,
                })
                continue
            if msg_type == "read":
                try:
                    peer_id = int(payload.get("peer_id"))
                except (TypeError, ValueError):
                    continue
                db.query(ChatMessage).filter(
                    ChatMessage.sender_id == peer_id,
                    ChatMessage.recipient_id == user.id,
                    ChatMessage.read_at.is_(None),
                ).update({ChatMessage.read_at: datetime.utcnow()}, synchronize_session=False)
                db.commit()
                await manager.send_to(peer_id, {"type": "read", "by": user.id, "peer_id": user.id})
                # 通知同一账号的其他标签页同步清除该会话未读
                await manager.send_to(user.id, {
                    "type": "read",
                    "by": user.id,
                    "peer_id": peer_id,
                    "self": True,
                })
                continue
            if msg_type in CALL_TYPES:
                if payload.get("group_id") not in (None, "", 0, "0"):
                    await _relay_group_signal(websocket, db, user, payload, msg_type)
                    continue
                try:
                    recipient_id = int(payload.get("to"))
                except (TypeError, ValueError):
                    continue
                recipient = db.query(User).filter(User.id == recipient_id, User.is_active.is_(True)).first()
                if not recipient:
                    await websocket.send_json({"type": "call-error", "message": "对方用户不存在"})
                    continue
                if recipient.id not in manager.online_ids():
                    await websocket.send_json({"type": "call-error", "message": "对方当前不在线"})
                    continue
                relay = {
                    "type": msg_type,
                    "from": _user_dict(user, True),
                    "call_id": str(payload.get("call_id") or "")[:100],
                    "call_type": str(payload.get("call_type") or "audio"),
                    "sdp": payload.get("sdp"),
                    "candidate": payload.get("candidate"),
                    "reason": str(payload.get("reason") or "")[:200],
                }
                await manager.send_to(recipient.id, relay)
                continue
            if msg_type == "typing":
                try:
                    recipient_id = int(payload.get("to"))
                except (TypeError, ValueError):
                    continue
                await manager.send_to(recipient_id, {
                    "type": "typing",
                    "from": _user_dict(user, True),
                    "typing": bool(payload.get("typing")),
                })
                continue
            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})
    except WebSocketDisconnect:
        pass
    except Exception:  # noqa: BLE001
        pass
    finally:
        manager.disconnect(user.id, websocket)
        # 断线即退出所有群通话，通知仍在通话中的成员
        try:
            touched_calls = group_call_registry.remove_user(user.id)
            for call in touched_calls:
                group_id = int(call.get("group_id") or 0)
                call_id = call.get("call_id")
                if not group_id or not call_id:
                    continue
                for member_id in group_call_registry.participant_ids(call_id):
                    await manager.send_to(member_id, {
                        "type": "group-call-participant-left",
                        "group_id": group_id,
                        "call_id": call_id,
                        "user_id": user.id,
                    })
                if not group_call_registry.get(call_id):
                    await _broadcast_group(db, group_id, {
                        "type": "group-call-ended",
                        "group_id": group_id,
                        "call_id": call_id,
                        "by": user.id,
                        "reason": "disconnected",
                    })
        except Exception:  # noqa: BLE001
            pass
        try:
            await manager.broadcast(_presence_payload(db))
        except Exception:  # noqa: BLE001
            pass
        db.close()
