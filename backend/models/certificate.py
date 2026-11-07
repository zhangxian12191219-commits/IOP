"""证书管理模型：托管、监控和 ACME 申请记录。"""
from datetime import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, Text

from .database import Base


class ManagedCertificate(Base):
    """集中管理的证书。

    证书和私钥不直接写入数据库：cert_path/key_path 指向 data/certificates
    目录，目录权限 700、文件权限 600。
    """

    __tablename__ = "managed_certificates"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, comment="证书名称")
    cert_type = Column(String(20), default="domain", comment="domain/ip")
    source = Column(String(20), default="import", comment="import/acme")
    primary_host = Column(String(255), nullable=False, index=True, comment="主域名或 IP")
    san_json = Column(JSON, default=list, comment="SAN 列表")
    subject = Column(String(500), comment="证书主题")
    issuer = Column(String(500), comment="颁发者")
    serial_number = Column(String(200), comment="序列号")
    fingerprint = Column(String(200), comment="SHA256 指纹")
    key_type = Column(String(50), comment="密钥类型")
    signature_algorithm = Column(String(100), comment="签名算法")
    valid_from = Column(DateTime, nullable=True)
    valid_to = Column(DateTime, nullable=True)
    status = Column(String(20), default="unknown", comment="valid/expiring/expired/error")
    last_error = Column(Text, comment="最近一次校验错误")
    last_checked_at = Column(DateTime, nullable=True)
    monitor_enabled = Column(Boolean, default=True, comment="是否监控")
    monitor_host = Column(String(255), comment="监控主机，默认主域名/IP")
    monitor_port = Column(Integer, default=443, comment="监控端口")
    warning_days = Column(Integer, default=30, comment="提前告警天数")
    auto_renew = Column(Boolean, default=False, comment="是否自动续期（ACME）")
    renew_config = Column(JSON, default=dict, comment="ACME 申请/续期参数")
    last_renew_error = Column(Text, comment="最近一次续期错误")
    cert_path = Column(String(500), comment="证书 PEM 相对路径")
    key_path = Column(String(500), comment="私钥 PEM 相对路径")
    chain_path = Column(String(500), comment="证书链 PEM 相对路径")
    notes = Column(Text, comment="备注")
    created_by = Column(String(100), comment="创建人")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
