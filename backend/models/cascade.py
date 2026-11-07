"""总部/分支级联模型。"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, Text

from .database import Base


class CascadeNode(Base):
    """总部登记的分支节点。只保存接入令牌哈希，不保存明文令牌。"""

    __tablename__ = "cascade_nodes"

    id = Column(Integer, primary_key=True, index=True)
    node_key = Column(String(80), unique=True, index=True, nullable=False)
    name = Column(String(160), nullable=False)
    token_hash = Column(String(64), unique=True, index=True, nullable=False)
    token_enc = Column(Text, default="", comment="接入令牌密文，仅供总部向分支加密下发")
    address = Column(String(255), default="")
    version = Column(String(80), default="")
    status = Column(String(20), default="offline", index=True)
    last_seen = Column(DateTime, index=True)
    last_sync = Column(DateTime)
    snapshot = Column(JSON, default=dict)
    snapshot_updated_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class CascadeMessage(Base):
    """级联即时通信消息；总部和分支使用同一模型。"""

    __tablename__ = "cascade_messages"

    id = Column(Integer, primary_key=True, index=True)
    node_key = Column(String(80), default="", index=True, comment="总部侧分支标识")
    sender = Column(String(160), default="")
    direction = Column(String(20), default="hq_to_branch", comment="hq_to_branch / branch_to_hq")
    content = Column(Text, default="")
    delivered = Column(Boolean, default=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
