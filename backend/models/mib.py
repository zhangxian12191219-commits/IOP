"""MIB 文件与 MIB 对象模型"""
from datetime import datetime

from sqlalchemy import (
    Column, Integer, String, Text, DateTime, JSON, ForeignKey, Index, Boolean,
)
from sqlalchemy.orm import relationship

from .database import Base


class MibFile(Base):
    """导入的 MIB 文件"""

    __tablename__ = "mib_files"

    id = Column(Integer, primary_key=True, index=True)
    filename = Column(String(255), nullable=False, comment="原始文件名")
    module_name = Column(String(120), index=True, comment="MIB 模块名")
    size = Column(Integer, default=0, comment="文件大小（字节）")
    object_count = Column(Integer, default=0, comment="解析出的对象数")
    readable_count = Column(Integer, default=0, comment="可读取对象数")
    unresolved_count = Column(Integer, default=0, comment="未能解析的引用数")
    categories = Column(JSON, default=list, comment="识别到的指标类别")
    imports = Column(JSON, default=list, comment="IMPORTS 的模块列表")
    note = Column(Text, comment="备注/解析提示")
    is_builtin = Column(Boolean, default=False, index=True, comment="是否内置厂商常用库")
    builtin_key = Column(String(80), index=True, comment="内置库唯一标识")
    device_category = Column(String(30), index=True, comment="设备类型: switch/server/storage")
    vendor = Column(String(60), index=True, comment="厂商")
    device_model = Column(String(120), index=True, comment="设备型号")
    created_at = Column(DateTime, default=datetime.utcnow)

    objects = relationship(
        "MibObject", back_populates="mib", cascade="all, delete-orphan"
    )


class MibObject(Base):
    """MIB 对象（OID 节点）"""

    __tablename__ = "mib_objects"

    id = Column(Integer, primary_key=True, index=True)
    mib_id = Column(
        Integer, ForeignKey("mib_files.id", ondelete="CASCADE"), index=True
    )
    name = Column(String(160), nullable=False, index=True, comment="对象名")
    oid = Column(String(200), nullable=False, index=True, comment="数字 OID")
    syntax = Column(String(160), comment="SYNTAX")
    access = Column(String(40), comment="MAX-ACCESS")
    status = Column(String(40), comment="STATUS")
    description = Column(Text, comment="DESCRIPTION")
    category = Column(String(30), index=True, comment="推荐类别: cpu/memory/...")
    score = Column(Integer, default=0, comment="类别置信度")

    mib = relationship("MibFile", back_populates="objects")


Index("ix_mib_objects_mib_category", MibObject.mib_id, MibObject.category)
