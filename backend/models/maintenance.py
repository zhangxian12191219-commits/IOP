"""设备维保记录模型"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, Text, DateTime, ForeignKey
from sqlalchemy.orm import relationship

from .database import Base


class DeviceMaintenance(Base):
    """设备维保/巡检/维修记录"""

    __tablename__ = "device_maintenance"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), index=True, nullable=False
    )
    maint_type = Column(String(20), default="inspection", comment="repair/inspection/parts/other")
    title = Column(String(200), nullable=False, comment="事项标题")
    description = Column(Text, comment="详细说明")
    engineer = Column(String(100), comment="处理人/工程师")
    cost = Column(Float, comment="费用(元)")
    maintained_at = Column(DateTime, default=datetime.utcnow, comment="维保时间")
    created_by = Column(String(100), comment="登记人")
    created_at = Column(DateTime, default=datetime.utcnow)

    device = relationship("Device")
