"""MIB 自动匹配学习档案：记录设备指纹与成功验证的指标映射。"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, JSON, String, Text

from .database import Base


class MibMatchProfile(Base):
    __tablename__ = "mib_match_profiles"

    id = Column(Integer, primary_key=True, index=True)
    fingerprint = Column(String(160), unique=True, nullable=False, index=True)
    vendor = Column(String(100), default="")
    model = Column(String(200), default="")
    sys_object_id = Column(String(200), default="")
    sys_descr = Column(Text, default="")
    mib_id = Column(Integer, nullable=True, index=True)
    metric_map = Column(JSON, default=dict)
    success_count = Column(Integer, default=0)
    last_used_at = Column(DateTime, default=datetime.utcnow)
    created_at = Column(DateTime, default=datetime.utcnow)
