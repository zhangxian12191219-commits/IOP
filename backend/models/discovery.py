"""定时自动发现调度配置"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Text

from .database import Base


class DiscoverySchedule(Base):
    """SNMP 网段定时扫描配置（单行配置）"""

    __tablename__ = "discovery_schedules"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), default="定时扫描", comment="定时任务名称")
    enabled = Column(Boolean, default=False, index=True)
    target = Column(String(500), default="", comment="CIDR / IP 范围 / 逗号分隔地址")

    version = Column(String(10), default="v2c")
    community = Column(String(255), default="public")
    communities = Column(JSON, default=list, comment="定时扫描使用的多个 v1/v2c 团体名")
    port = Column(Integer, default=161)
    timeout = Column(Integer, default=2)
    concurrency = Column(Integer, default=32)
    v3_username = Column(String(100), default="")
    v3_security_level = Column(String(30), default="authPriv")
    v3_auth_protocol = Column(String(20), default="SHA")
    v3_auth_password = Column(String(255))
    v3_priv_protocol = Column(String(20), default="AES")
    v3_priv_password = Column(String(255))
    v3_context_name = Column(String(100))

    interval_minutes = Column(Integer, default=60, comment="扫描间隔（分钟）")
    auto_add = Column(Boolean, default=True, comment="发现后自动入库")

    last_run_at = Column(DateTime)
    last_status = Column(String(20), default="idle", comment="idle/running/success/failed")
    last_found = Column(Integer, default=0)
    last_added = Column(Integer, default=0)
    last_duration_ms = Column(Integer, default=0)
    last_message = Column(Text, default="")

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
