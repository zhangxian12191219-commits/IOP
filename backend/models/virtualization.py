"""虚拟化管理模型：只读纳管 VMware / KVM 平台。"""
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from .database import Base


class VirtualPlatform(Base):
    """虚拟化平台连接。密码只保存 Fernet 密文。"""
    __tablename__ = "virtual_platforms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, unique=True, comment="平台名称")
    platform_type = Column(String(20), nullable=False, index=True, comment="vmware/cas/kvm/proxmox/docker/kubernetes")
    address = Column(String(255), nullable=False, comment="管理地址/IP/域名")
    port = Column(Integer, default=443, nullable=False, comment="连接端口")
    username = Column(String(120), nullable=False, comment="只读账号")
    password_enc = Column(Text, comment="加密后的密码")
    verify_tls = Column(Boolean, default=True, comment="是否校验 TLS 证书")
    enabled = Column(Boolean, default=True, comment="是否参与定时同步")
    sync_interval_minutes = Column(Integer, default=5, comment="同步间隔（分钟）")
    last_sync_at = Column(DateTime, comment="最后同步时间")
    last_sync_status = Column(String(20), default="never", comment="never/success/failed")
    last_error = Column(Text, comment="最后一次错误")
    last_health = Column(JSON, default=dict, comment="平台健康快照（PVE Ceph 等）")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    hosts = relationship(
        "VirtualHost", back_populates="platform", cascade="all, delete-orphan"
    )
    vms = relationship(
        "VirtualMachine", back_populates="platform", cascade="all, delete-orphan"
    )


class VirtualHost(Base):
    """虚拟化宿主机。"""
    __tablename__ = "virtual_hosts"
    __table_args__ = (
        UniqueConstraint("platform_id", "external_id", name="uq_virtual_host"),
    )

    id = Column(Integer, primary_key=True, index=True)
    platform_id = Column(
        Integer, ForeignKey("virtual_platforms.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    external_id = Column(String(255), nullable=False, comment="平台内唯一标识")
    name = Column(String(255), nullable=False)
    ip_address = Column(String(45), comment="宿主机管理 IP")
    cluster_name = Column(String(255), comment="集群/数据中心")
    status = Column(String(30), default="unknown", comment="online/offline/unknown")
    cpu_model = Column(String(255), comment="CPU 型号")
    cpu_cores = Column(Integer, default=0, comment="逻辑 CPU 核数")
    cpu_mhz = Column(Float, default=0, comment="单核主频 MHz")
    cpu_usage = Column(Float, comment="CPU 使用率 %")
    memory_total_mb = Column(Float, default=0)
    memory_used_mb = Column(Float, default=0)
    memory_usage = Column(Float, comment="内存使用率 %")
    storage_total_gb = Column(Float, default=0)
    storage_used_gb = Column(Float, default=0)
    storage_usage = Column(Float, comment="存储使用率 %")
    net_rx_bps = Column(Float, default=0)
    net_tx_bps = Column(Float, default=0)
    vm_count = Column(Integer, default=0)
    uptime_seconds = Column(BigInteger, comment="运行时长（秒）")
    last_seen = Column(DateTime, default=datetime.utcnow)
    extra = Column(JSON, default=dict)

    platform = relationship("VirtualPlatform", back_populates="hosts")
    vms = relationship("VirtualMachine", back_populates="host")


class VirtualMachine(Base):
    """虚拟机只读快照。"""
    __tablename__ = "virtual_machines"
    __table_args__ = (
        UniqueConstraint("platform_id", "external_id", name="uq_virtual_machine"),
    )

    id = Column(Integer, primary_key=True, index=True)
    platform_id = Column(
        Integer, ForeignKey("virtual_platforms.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    host_id = Column(
        Integer, ForeignKey("virtual_hosts.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    external_id = Column(String(255), nullable=False, comment="平台内唯一标识")
    name = Column(String(255), nullable=False, index=True)
    power_state = Column(String(20), default="unknown", index=True,
                         comment="running/stopped/paused/unknown")
    vcpu = Column(Integer, default=0)
    memory_mb = Column(Float, default=0, comment="分配内存 MB")
    disk_total_gb = Column(Float, default=0, comment="磁盘配置容量 GB")
    disk_used_gb = Column(Float, default=0, comment="磁盘已用容量 GB")
    disk_usage = Column(Float, comment="磁盘使用率 %")
    nic_count = Column(Integer, default=0)
    ip_addresses = Column(JSON, default=list)
    primary_ip = Column(String(45), comment="主 IP，用于列表展示和排序")
    ip_sort_key = Column(String(80), index=True, comment="IP 自然排序键")
    guest_os = Column(String(255), comment="Guest OS")
    tools_status = Column(String(50), comment="VMware Tools / Guest Agent 状态")
    cpu_usage = Column(Float, comment="CPU 使用率 %")
    memory_usage = Column(Float, comment="内存使用率 %")
    net_rx_bps = Column(Float, default=0)
    net_tx_bps = Column(Float, default=0)
    # KVM 的 CPU 时间是累计值，保留下来用于计算两次同步之间的使用率
    cpu_time_ns = Column(BigInteger, comment="KVM 累计 CPU 时间（ns）")
    sample_at = Column(DateTime, comment="CPU 采样时间")
    last_seen = Column(DateTime, default=datetime.utcnow)
    extra = Column(JSON, default=dict)

    platform = relationship("VirtualPlatform", back_populates="vms")
    host = relationship("VirtualHost", back_populates="vms")


class VirtualizationAlert(Base):
    """虚拟机告警：CPU、内存、磁盘使用率超过阈值或关机。"""
    __tablename__ = "virtualization_alerts"

    id = Column(Integer, primary_key=True, index=True)
    platform_id = Column(
        Integer, ForeignKey("virtual_platforms.id", ondelete="CASCADE"),
        nullable=True, index=True,
    )
    vm_id = Column(
        Integer, ForeignKey("virtual_machines.id", ondelete="SET NULL"),
        nullable=True, index=True,
    )
    platform_name = Column(String(120), comment="平台名称快照")
    vm_name = Column(String(255), comment="虚拟机名称快照")
    alert_type = Column(String(30), nullable=False, index=True,
                        comment="vm_cpu/vm_memory/vm_disk/vm_shutdown")
    alert_level = Column(String(20), default="warning", comment="info/warning/critical/emergency")
    # 是否允许该条告警发送到已配置的告警渠道（邮件/Webhook）；历史数据为 NULL 时按“发送”处理
    send_notification = Column(Boolean, default=True, comment="是否发送到告警渠道")
    message = Column(Text, nullable=False)
    value = Column(Float, comment="触发值")
    threshold = Column(Float, comment="阈值")
    is_acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime, comment="最近一次人工确认时间")
    is_hidden = Column(Boolean, default=False, index=True, comment="批量确认后从活动列表隐藏")
    resolved_at = Column(DateTime, comment="自动恢复时间")
    resolution = Column(String(50), comment="恢复方式")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
