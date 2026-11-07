"""用户、角色、群组模型（RBAC）

- User  用户（账号、密码哈希、是否启用、是否超级管理员）
- Role  角色（权限点列表）
- Group 用户群组（部门/团队）
- user_roles / user_groups 多对多关联
"""
from sqlalchemy import (
    Column, Integer, String, Boolean, DateTime, Text, JSON, Table, ForeignKey,
)
from sqlalchemy.orm import relationship
from datetime import datetime

from .database import Base

# 用户-角色 多对多
user_roles = Table(
    "user_roles",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("role_id", Integer, ForeignKey("roles.id", ondelete="CASCADE"), primary_key=True),
)

# 用户-群组 多对多
user_groups = Table(
    "user_groups",
    Base.metadata,
    Column("user_id", Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
    Column("group_id", Integer, ForeignKey("groups.id", ondelete="CASCADE"), primary_key=True),
)


class Role(Base):
    """角色"""

    __tablename__ = "roles"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, comment="角色名称")
    code = Column(String(50), unique=True, comment="角色标识")
    description = Column(Text, comment="描述")
    # 权限点列表，如 ["assets:view", "assets:edit"]，"*" 表示全部
    permissions = Column(JSON, default=list, comment="权限点列表")
    is_builtin = Column(Boolean, default=False, comment="是否内置角色")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    users = relationship("User", secondary=user_roles, back_populates="roles")


class Group(Base):
    """用户群组"""

    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, unique=True, comment="群组名称")
    code = Column(String(50), unique=True, comment="群组标识")
    description = Column(Text, comment="描述")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    users = relationship("User", secondary=user_groups, back_populates="groups")


class User(Base):
    """用户"""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(64), nullable=False, unique=True, index=True, comment="登录名")
    password_hash = Column(String(255), nullable=False, comment="密码哈希")
    real_name = Column(String(100), comment="姓名")
    email = Column(String(200), comment="邮箱")
    phone = Column(String(50), comment="手机号")
    is_active = Column(Boolean, default=True, comment="是否启用")
    is_superuser = Column(Boolean, default=False, comment="是否超级管理员")
    last_login = Column(DateTime, comment="最近登录时间")
    password_changed_at = Column(DateTime, default=datetime.utcnow, comment="最近修改密码时间")
    must_change_password = Column(Boolean, default=False, nullable=True, comment="是否必须先修改密码")
    # 二次身份验证（TOTP，兼容 Google Authenticator / 腾讯身份验证器）
    totp_secret = Column(String(64), nullable=True, comment="TOTP 密钥（Base32，启用后才有值）")
    totp_enabled = Column(Boolean, default=False, nullable=True, comment="是否启用二次身份验证")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    roles = relationship("Role", secondary=user_roles, back_populates="users")
    groups = relationship("Group", secondary=user_groups, back_populates="users")
