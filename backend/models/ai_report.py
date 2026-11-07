"""AI 运维报告记录。"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Integer, String, Text

from .database import Base


class AiOpsReport(Base):
    __tablename__ = "ai_ops_reports"

    id = Column(Integer, primary_key=True, index=True)
    title = Column(String(300), nullable=False)
    filename = Column(String(255))
    content = Column(Text, default="")
    model = Column(String(200), default="")
    mode = Column(String(20), default="local")
    created_by = Column(String(100), default="")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
