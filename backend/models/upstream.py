"""告警渠道 - 上级平台接收模型"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text, JSON

from .database import Base


class UpstreamReceivedAlert(Base):
    """上级平台收到的下级节点告警，用于审计、去重和状态查看。"""

    __tablename__ = "upstream_received_alerts"

    id = Column(Integer, primary_key=True, index=True)
    event_id = Column(String(120), unique=True, index=True, nullable=False)
    source_node_id = Column(String(120), index=True)
    source_node_name = Column(String(200))
    source_instance = Column(String(120))
    source_ip = Column(String(64))
    origin_source = Column(String(20))
    level = Column(String(20), index=True)
    alert_type = Column(String(50))
    title = Column(String(300))
    message = Column(Text)
    payload = Column(JSON, default=dict)
    forwarded_count = Column(Integer, default=0)
    status = Column(String(30), default="received")
    error = Column(Text)
    received_at = Column(DateTime, default=datetime.utcnow, index=True)
