"""告警通知模型 - 通知通道与发送日志"""
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Text, JSON, ForeignKey
from datetime import datetime
from .database import Base


class NotificationChannel(Base):
    """通知通道（邮件 / Webhook）"""

    __tablename__ = "notification_channels"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, comment="通道名称")
    channel_type = Column(String(20), nullable=False, comment="类型: email / webhook / sms / upstream")
    enabled = Column(Boolean, default=True, comment="是否启用")
    min_level = Column(String(20), default="warning", comment="最低触发级别: warning/critical")
    config = Column(JSON, default=dict, comment="通道配置(JSON)")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class NotificationLog(Base):
    """通知发送日志"""

    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(Integer, ForeignKey("notification_channels.id"), nullable=True)
    channel_name = Column(String(100), comment="通道名称快照")
    channel_type = Column(String(20), comment="通道类型快照")
    source = Column(String(20), comment="告警来源: device / website")
    source_id = Column(Integer, comment="告警ID")
    title = Column(String(300), comment="标题")
    message = Column(Text, comment="内容")
    status = Column(String(20), comment="success / failed")
    error = Column(Text, comment="失败原因")
    created_at = Column(DateTime, default=datetime.utcnow)
