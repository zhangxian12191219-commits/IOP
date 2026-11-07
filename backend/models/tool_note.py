"""运维笔记：个人笔记与分享关系"""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from .database import Base


class ToolNote(Base):
    __tablename__ = "tool_notes"

    id = Column(Integer, primary_key=True, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(200), nullable=False)
    content = Column(Text, default="")
    note_format = Column(String(20), default="markdown", comment="markdown/plain")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    shares = relationship("ToolNoteShare", back_populates="note", cascade="all, delete-orphan")


class ToolNoteShare(Base):
    __tablename__ = "tool_note_shares"
    __table_args__ = (UniqueConstraint("note_id", "user_id", name="uq_tool_note_share"),)

    id = Column(Integer, primary_key=True, index=True)
    note_id = Column(Integer, ForeignKey("tool_notes.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    note = relationship("ToolNote", back_populates="shares")
