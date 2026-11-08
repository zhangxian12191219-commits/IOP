"""系统设置模型（键值对）"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime

from .database import Base


class SystemSetting(Base):
    """系统配置：key - value 形式存储（value 为字符串）"""

    __tablename__ = "system_settings"

    id = Column(Integer, primary_key=True, index=True)
    key = Column(String(100), nullable=False, unique=True, index=True, comment="配置项")
    value = Column(Text, comment="配置值（字符串）")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
