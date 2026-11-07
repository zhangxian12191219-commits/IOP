"""网站监控模型 - 监控目标配置及监控结果"""
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, JSON, ForeignKey
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base


class WebsiteTarget(Base):
    """网站监控目标表"""
    __tablename__ = "website_targets"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, comment="监控名称")
    url = Column(String(500), nullable=False, comment="监控URL")
    domain = Column(String(255), comment="域名")
    ip_address = Column(String(45), comment="IP地址")
    monitor_type = Column(String(20), nullable=False, default="http", comment="监控类型: http/https/tcp/ping")
    port = Column(Integer, comment="TCP端口")
    method = Column(String(10), default="GET", comment="HTTP方法")
    expected_status = Column(Integer, default=200, comment="期望HTTP状态码")
    expected_statuses = Column(String(200), comment="允许状态码，支持逗号/范围，如 200,301-399")
    expected_keywords = Column(Text, comment="期望响应关键字，多个用逗号分隔")
    timeout = Column(Integer, default=10, comment="请求超时秒数")
    check_interval = Column(Integer, default=60, comment="检查间隔秒数")
    ignore_https_errors = Column(Boolean, default=True, comment="忽略HTTPS证书安全提示")
    cache_bust_seconds = Column(Integer, default=0, comment="缓存更换间隔秒数，0为关闭")
    category = Column(String(100), comment="分类")
    category_mode = Column(String(20), default="auto", comment="分类方式: auto/manual")
    sort_order = Column(Integer, default=0, index=True, comment="自定义排序")
    cert_root_domain = Column(String(255), comment="根域名证书监控")
    cert_subdomains = Column(Text, comment="额外证书子域名，逗号分隔")
    slow_threshold_ms = Column(Float, default=5000, comment="响应缓慢阈值(毫秒)")
    cert_monitor_enabled = Column(Boolean, default=True, comment="是否监控HTTPS证书到期")
    cert_expiry_days = Column(Integer, default=30, comment="证书剩余天数告警阈值")
    cert_alert_level = Column(String(20), default="warning", comment="证书到期告警级别")
    down_level = Column(String(20), default="critical", comment="检测失败告警级别")
    slow_level = Column(String(20), default="warning", comment="响应缓慢告警级别")
    down_level_label = Column(String(50), comment="检测失败自定义级别名")
    slow_level_label = Column(String(50), comment="响应缓慢自定义级别名")
    is_enabled = Column(Boolean, default=True, comment="是否启用")
    notify_email = Column(String(100), comment="通知邮箱")
    notify_webhook = Column(String(500), comment="Webhook地址")
    description = Column(Text, comment="描述")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联
    check_history = relationship("WebsiteCheckHistory", back_populates="target", cascade="all, delete-orphan")
    alerts = relationship("WebsiteAlert", back_populates="target", cascade="all, delete-orphan")


class WebsiteCheckHistory(Base):
    """网站监控历史结果"""
    __tablename__ = "website_check_history"

    id = Column(Integer, primary_key=True, index=True)
    target_id = Column(Integer, ForeignKey("website_targets.id"), nullable=False, index=True)
    status_code = Column(Integer, comment="HTTP状态码")
    response_time = Column(Float, comment="响应时间(ms)")
    is_alive = Column(Boolean, comment="是否存活")
    http_error = Column(Text, comment="HTTP错误信息")
    dns_resolve_time = Column(Float, comment="DNS解析时间(ms)")
    tcp_connect_time = Column(Float, comment="TCP连接时间(ms)")
    ssl_time = Column(Float, comment="SSL握手时间(ms)")
    cert_info = Column(JSON, comment="HTTPS证书信息（所属单位/颁发机构/有效期等）")
    final_ip = Column(String(45), comment="最终解析IP")
    content_length = Column(Integer, comment="响应内容长度")
    check_type = Column(String(20), comment="检查类型")  # http/https/tcp/ping
    error_message = Column(Text, comment="错误信息")
    checked_at = Column(DateTime, default=datetime.utcnow)

    target = relationship("WebsiteTarget", back_populates="check_history")


class WebsiteAlert(Base):
    """网站监控告警"""
    __tablename__ = "website_alerts"

    id = Column(Integer, primary_key=True, index=True)
    target_id = Column(Integer, ForeignKey("website_targets.id"), nullable=False, index=True)
    alert_type = Column(String(20), nullable=False, comment="类型: down/slow/ssl_expired")
    alert_level = Column(String(20), nullable=False, default="warning")
    level_label = Column(String(50), comment="自定义级别显示名称")
    message = Column(Text, nullable=False)
    details = Column(JSON, comment="详细信息")
    is_acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime, comment="最近一次人工确认时间")
    resolved_at = Column(DateTime, comment="自动恢复时间")
    resolution = Column(String(50), comment="恢复方式")
    is_hidden = Column(Boolean, default=False, index=True, comment="人工抑制后从活动列表隐藏")
    created_at = Column(DateTime, default=datetime.utcnow)

    target = relationship("WebsiteTarget", back_populates="alerts")
