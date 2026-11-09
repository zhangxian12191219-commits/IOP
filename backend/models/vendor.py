"""厂商库模型：资产与 MIB 共用的厂商主数据。"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, Text

from .database import Base


class Vendor(Base):
    __tablename__ = "vendors"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(80), unique=True, nullable=False, index=True, comment="厂商标准名称")
    aliases = Column(JSON, default=list, comment="中英文别名/简称")
    category = Column(String(30), default="other", comment="network/server/storage/backup/security/virtualization/other")
    note = Column(Text, comment="备注")
    is_builtin = Column(Boolean, default=False, comment="系统内置厂商")
    is_enabled = Column(Boolean, default=True, comment="资产表单是否可选")
    sort_order = Column(Integer, default=100, comment="排序，越小越靠前")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
