"""自定义告警规则。

每条规则绑定一个设备、一个指标条件、一个严重级别和一组通知通道。
"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, JSON, String
from sqlalchemy.orm import relationship

from .database import Base


class DeviceAlertRule(Base):
    __tablename__ = "device_alert_rules"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(100), nullable=False)
    metric = Column(String(50), nullable=False, comment="cpu_usage/memory_usage/temperature/disk_usage/power/offline/custom")
    custom_key = Column(String(100), comment="metric=custom 时的自定义指标 key")
    operator = Column(String(10), default="gt", comment="gt/gte/lt/lte/eq/ne")
    threshold = Column(Float, nullable=False, comment="触发阈值")
    level = Column(String(20), default="warning", comment="info/warning/critical/emergency")
    level_label = Column(String(50), comment="自定义级别显示名称")
    notify_channel_ids = Column(JSON, default=list, comment="选中的通知通道 ID")
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    device = relationship("Device")
