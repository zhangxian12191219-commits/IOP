"""运维笔记接口：个人隔离、分享、批量操作与复制"""
from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..models.tool_note import ToolNote, ToolNoteShare
from ..models.user import User
from ..services.auth import get_current_user

router = APIRouter(prefix="/api/notes", tags=["运维笔记"])
NOTE_FORMATS = {"markdown", "plain"}


class NotePayload(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    content: str = Field("", max_length=200000)
    note_format: str = "markdown"


class NoteUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=200)
    content: Optional[str] = Field(None, max_length=200000)
    note_format: Optional[str] = None


class SharePayload(BaseModel):
    user_ids: List[int] = Field(default_factory=list, max_length=100)


class BatchIdsPayload(BaseModel):
    ids: List[int] = Field(..., min_length=1, max_length=200)


class BatchSharePayload(BaseModel):
    ids: List[int] = Field(..., min_length=1, max_length=200)
    user_ids: List[int] = Field(default_factory=list, max_length=100)


def _validate_format(value: str) -> str:
    value = (value or "markdown").strip().lower()
    if value not in NOTE_FORMATS:
        raise HTTPException(status_code=400, detail="笔记格式仅支持 markdown 或 plain")
    return value


def _note_dict(note: ToolNote, current_id: int, owner_name: str = "", shared_to: Optional[list] = None) -> dict:
    return {
        "id": note.id,
        "title": note.title,
        "content": note.content or "",
        "note_format": note.note_format or "markdown",
        "owner_id": note.owner_id,
        "owner_name": owner_name,
        "is_owner": note.owner_id == current_id,
        "created_at": note.created_at.isoformat() if note.created_at else None,
        "updated_at": note.updated_at.isoformat() if note.updated_at else None,
        "shared_to": shared_to or [],
    }


def _share_users(db: Session, note_ids: List[int]) -> dict:
    if not note_ids:
        return {}
    rows = (
        db.query(ToolNoteShare, User)
        .join(User, User.id == ToolNoteShare.user_id)
        .filter(ToolNoteShare.note_id.in_(note_ids))
        .all()
    )
    result = {}
    for share, user in rows:
        result.setdefault(share.note_id, []).append({
            "id": user.id,
            "username": user.username,
            "real_name": user.real_name or "",
        })
    return result


def _own_note(db: Session, note_id: int, current: User) -> ToolNote:
    note = db.query(ToolNote).filter(ToolNote.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="笔记不存在")
    if note.owner_id != current.id:
        raise HTTPException(status_code=403, detail="无权修改或删除他人的笔记")
    return note


def _replace_shares(db: Session, note: ToolNote, user_ids: List[int], owner_id: int) -> int:
    valid_users = []
    if user_ids:
        valid_users = db.query(User).filter(User.id.in_(user_ids), User.is_active.is_(True)).all()
    valid_ids = {user.id for user in valid_users if user.id != owner_id}
    db.query(ToolNoteShare).filter(ToolNoteShare.note_id == note.id).delete(synchronize_session=False)
    for user_id in valid_ids:
        db.add(ToolNoteShare(note_id=note.id, user_id=user_id))
    return len(valid_ids)


@router.get("")
def list_notes(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    own = db.query(ToolNote).filter(ToolNote.owner_id == current.id).order_by(ToolNote.updated_at.desc()).all()
    own_ids = [note.id for note in own]
    own_shares = _share_users(db, own_ids)

    shared_rows = (
        db.query(ToolNote, User)
        .join(ToolNoteShare, ToolNoteShare.note_id == ToolNote.id)
        .join(User, User.id == ToolNote.owner_id)
        .filter(ToolNoteShare.user_id == current.id)
        .order_by(ToolNote.updated_at.desc())
        .all()
    )
    shared = [
        _note_dict(note, current.id, owner_name=owner.username, shared_to=[])
        for note, owner in shared_rows
    ]
    return {
        "items": [
            _note_dict(note, current.id, owner_name=current.username, shared_to=own_shares.get(note.id, []))
            for note in own
        ],
        "shared": shared,
    }


@router.get("/users")
def note_share_users(db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    users = (
        db.query(User)
        .filter(User.is_active.is_(True), User.id != current.id)
        .order_by(User.username.asc())
        .all()
    )
    return [{"id": user.id, "username": user.username, "real_name": user.real_name or ""} for user in users]


@router.post("")
def create_note(payload: NotePayload, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    note = ToolNote(
        owner_id=current.id,
        title=payload.title.strip(),
        content=payload.content or "",
        note_format=_validate_format(payload.note_format),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(note)
    db.commit()
    db.refresh(note)
    return _note_dict(note, current.id, owner_name=current.username)


@router.put("/{note_id}")
def update_note(note_id: int, payload: NoteUpdate, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    note = _own_note(db, note_id, current)
    if payload.title is not None:
        title = payload.title.strip()
        if not title:
            raise HTTPException(status_code=400, detail="笔记标题不能为空")
        note.title = title
    if payload.content is not None:
        note.content = payload.content
    if payload.note_format is not None:
        note.note_format = _validate_format(payload.note_format)
    note.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(note)
    return _note_dict(note, current.id, owner_name=current.username, shared_to=_share_users(db, [note.id]).get(note.id, []))


@router.delete("/{note_id}")
def delete_note(note_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    note = _own_note(db, note_id, current)
    db.delete(note)
    db.commit()
    return {"deleted": 1}


@router.post("/batch-delete")
def batch_delete(payload: BatchIdsPayload, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    notes = db.query(ToolNote).filter(ToolNote.id.in_(payload.ids), ToolNote.owner_id == current.id).all()
    count = len(notes)
    for note in notes:
        db.delete(note)
    db.commit()
    return {"deleted": count, "requested": len(payload.ids)}


@router.post("/batch-share")
def batch_share(payload: BatchSharePayload, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    notes = db.query(ToolNote).filter(ToolNote.id.in_(payload.ids), ToolNote.owner_id == current.id).all()
    total = 0
    for note in notes:
        total += _replace_shares(db, note, payload.user_ids, current.id)
    db.commit()
    return {"notes": len(notes), "shared_users": len(set(payload.user_ids)), "links": total}


@router.post("/{note_id}/share")
def share_note(note_id: int, payload: SharePayload, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    note = _own_note(db, note_id, current)
    count = _replace_shares(db, note, payload.user_ids, current.id)
    db.commit()
    return {"note_id": note.id, "shared_users": count, "shared_to": _share_users(db, [note.id]).get(note.id, [])}


@router.post("/{note_id}/copy")
def copy_note(note_id: int, db: Session = Depends(get_db), current: User = Depends(get_current_user)):
    note = db.query(ToolNote).filter(ToolNote.id == note_id).first()
    if not note:
        raise HTTPException(status_code=404, detail="笔记不存在")
    if note.owner_id != current.id:
        shared = db.query(ToolNoteShare).filter(
            ToolNoteShare.note_id == note_id,
            ToolNoteShare.user_id == current.id,
        ).first()
        if not shared:
            raise HTTPException(status_code=403, detail="无权访问该笔记")
    copy = ToolNote(
        owner_id=current.id,
        title=f"{note.title}（副本）"[:200],
        content=note.content or "",
        note_format=note.note_format or "markdown",
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(copy)
    db.commit()
    db.refresh(copy)
    return _note_dict(copy, current.id, owner_name=current.username)
