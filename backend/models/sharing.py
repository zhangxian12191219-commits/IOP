"""仪表盘 / 拓扑图 / 大屏共享模型。

共享默认只读；成员可以提交编辑申请，资源所有者审批后 can_edit 才为 True。
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import relationship

from .database import Base


class SharedResource(Base):
    __tablename__ = "shared_resources"
    __table_args__ = (
        UniqueConstraint("resource_type", "resource_key", "owner_id", name="uq_shared_resource_owner"),
    )

    id = Column(Integer, primary_key=True, index=True)
    resource_type = Column(String(20), nullable=False, index=True)
    resource_key = Column(String(100), nullable=False, index=True)
    owner_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(200), default="")
    config_json = Column(Text, default="{}")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    members = relationship("SharedResourceMember", back_populates="resource", cascade="all, delete-orphan")
    requests = relationship("SharedEditRequest", back_populates="resource", cascade="all, delete-orphan")


class SharedResourceMember(Base):
    __tablename__ = "shared_resource_members"
    __table_args__ = (UniqueConstraint("resource_id", "user_id", name="uq_shared_resource_member"),)

    id = Column(Integer, primary_key=True, index=True)
    resource_id = Column(Integer, ForeignKey("shared_resources.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    can_edit = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    resource = relationship("SharedResource", back_populates="members")


class SharedEditRequest(Base):
    __tablename__ = "shared_edit_requests"

    id = Column(Integer, primary_key=True, index=True)
    resource_id = Column(Integer, ForeignKey("shared_resources.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status = Column(String(20), default="pending", nullable=False, index=True)
    message = Column(String(500), default="")
    created_at = Column(DateTime, default=datetime.utcnow)
    decided_at = Column(DateTime, nullable=True)
    reviewer_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    resource = relationship("SharedResource", back_populates="requests")
