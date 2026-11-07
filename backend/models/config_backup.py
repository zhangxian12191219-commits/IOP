"""设备配置备份记录"""
from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from .database import Base


class ConfigBackup(Base):
    __tablename__ = "config_backups"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(
        Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status = Column(String(20), default="running", index=True, comment="running/success/failed")
    method = Column(String(20), default="manual", comment="manual/scheduled")
    config_text = Column(Text, comment="设备配置原文")
    error = Column(Text, comment="失败原因")
    size_bytes = Column(Integer, default=0)
    sha256 = Column(String(64), index=True)
    command = Column(String(200), comment="实际执行命令")
    vendor_profile = Column(String(50), comment="厂商适配器")
    triggered_by = Column(String(100), comment="触发人")
    started_at = Column(DateTime, default=datetime.utcnow)
    finished_at = Column(DateTime)
    duration_ms = Column(Integer, default=0)
    storage_type = Column(String(20), default="", comment="外部存储类型: webdav/sftp")
    storage_key = Column(String(500), default="", comment="外部存储对象路径")
    storage_status = Column(String(20), default="", comment="disabled/success/failed")
    storage_error = Column(Text, comment="外部存储同步错误")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    device = relationship("Device", back_populates="config_backups")
