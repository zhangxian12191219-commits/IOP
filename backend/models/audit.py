"""审计日志与登录失败记录模型"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, Text

from .database import Base


class AuditLog(Base):
    """配置变更审计日志（设置、用户/角色/群组、通知通道、配置导入导出等）"""

    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    module = Column(String(50), nullable=False, index=True, comment="模块: settings/users/roles/groups/notifications/config/security")
    action = Column(String(50), nullable=False, index=True, comment="动作: create/update/delete/import/export/login 等")
    target_type = Column(String(50), comment="对象类型")
    target_id = Column(String(100), comment="对象 ID")
    target_name = Column(String(200), comment="对象名称")
    operator = Column(String(100), index=True, comment="操作人用户名")
    operator_id = Column(Integer, comment="操作人用户 ID")
    ip = Column(String(64), comment="操作来源 IP")
    before = Column(JSON, default=dict, comment="变更前（脱敏）")
    after = Column(JSON, default=dict, comment="变更后（脱敏）")
    changed = Column(JSON, default=list, comment="变更字段列表")
    status = Column(String(20), default="success", comment="success / failed")
    message = Column(Text, comment="备注")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)


class LoginAttempt(Base):
    """登录失败计数与锁定状态（按用户名）"""

    __tablename__ = "login_attempts"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(100), nullable=False, unique=True, index=True)
    ip = Column(String(64), comment="最近一次失败来源 IP")
    fail_count = Column(Integer, default=0, comment="连续失败次数")
    locked_until = Column(DateTime, comment="锁定到期时间（为空表示未锁定）")
    last_failed_at = Column(DateTime, comment="最近失败时间")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
