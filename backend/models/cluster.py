"""集群节点注册与心跳"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String

from .database import Base


class ClusterNode(Base):
    __tablename__ = "cluster_nodes"

    id = Column(Integer, primary_key=True, index=True)
    node_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(120), nullable=False)
    address = Column(String(255), default="")
    version = Column(String(80), default="")
    status = Column(String(30), default="online", comment="online/offline/license_limit/license_invalid")
    weight = Column(Integer, default=1)
    license_status = Column(String(30), default="")
    license_max_nodes = Column(Integer, default=0)
    license_expires_at = Column(String(40))
    started_at = Column(DateTime, default=datetime.utcnow)
    last_heartbeat = Column(DateTime, default=datetime.utcnow, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
