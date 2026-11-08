"""即时通信：单聊 / 群聊消息、群组成员、附件与用户个性化偏好。"""
from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)

from .database import Base

# 群组限制：名称长度与成员上限（接口与 WebSocket 共用）
GROUP_NAME_MAX_LENGTH = 60
GROUP_MAX_MEMBERS = 30
GROUP_MEMBER_ROLES = ("owner", "member")


class ChatGroup(Base):
    """群聊会话：由群主创建，成员关系保存在 ChatGroupMember。"""

    __tablename__ = "chat_groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(GROUP_NAME_MAX_LENGTH), nullable=False)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ChatGroupMember(Base):
    """群成员关系：承担群组访问控制、未读游标（last_read_at）和角色。"""

    __tablename__ = "chat_group_members"
    __table_args__ = (
        UniqueConstraint("group_id", "user_id", name="uq_chat_group_member"),
    )

    id = Column(Integer, primary_key=True, index=True)
    group_id = Column(
        Integer, ForeignKey("chat_groups.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    user_id = Column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    role = Column(String(20), default="member", comment="owner/member")
    joined_at = Column(DateTime, default=datetime.utcnow)
    last_read_at = Column(DateTime, nullable=True, comment="群聊已读游标")


class ChatMessage(Base):
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    sender_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    # 单聊消息的接收人；群聊消息为 NULL（见 group_id）
    recipient_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    # 群聊消息所属群组；单聊消息为 NULL
    group_id = Column(
        Integer, ForeignKey("chat_groups.id", ondelete="CASCADE"), nullable=True, index=True,
    )
    content = Column(Text, nullable=False)
    message_type = Column(String(20), default="text", comment="text/image/file/whiteboard")
    attachment_id = Column(Integer, nullable=True, index=True, comment="关联聊天附件ID")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    read_at = Column(DateTime, nullable=True, comment="单聊已读时间；群聊使用成员表游标")
    recalled_at = Column(DateTime, nullable=True, comment="撤回时间")
    recalled_by = Column(Integer, nullable=True, comment="撤回操作人")
    sender_deleted = Column(Boolean, default=False, nullable=True, comment="发送方已删除（仅自己不可见）")
    recipient_deleted = Column(Boolean, default=False, nullable=True, comment="接收方已删除（仅自己不可见）")


class ChatAttachment(Base):
    """即时通信附件：图片/文件，保存 15 天后随消息一起清理。"""

    __tablename__ = "chat_attachments"

    id = Column(Integer, primary_key=True, index=True)
    uploader_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    original_name = Column(String(255), nullable=False)
    stored_name = Column(String(500), nullable=False)
    mime_type = Column(String(200), comment="MIME 类型")
    size = Column(Integer, default=0, comment="文件大小(字节)")
    message_id = Column(Integer, nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class ImPreference(Base):
    """每个用户独立的悬浮球 / 快捷入口配置。"""

    __tablename__ = "im_preferences"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    settings = Column(JSON, default=dict)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
