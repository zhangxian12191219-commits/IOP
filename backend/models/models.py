"""数据库模型定义"""
from sqlalchemy import Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from .database import Base


class AlertSuppression(Base):
    """告警抑制规则：在时间窗口内阻止同类告警重复生成和通知"""
    __tablename__ = "alert_suppressions"

    id = Column(Integer, primary_key=True, index=True)
    source = Column(String(20), default="device", comment="device / website / all")
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=True)
    website_target_id = Column(Integer, ForeignKey("website_targets.id"), nullable=True)
    alert_type = Column(String(100), nullable=True, comment="为空表示该对象全部告警类型")
    alert_level = Column(String(20), nullable=True, comment="为空表示全部级别")
    reason = Column(Text, comment="抑制原因")
    starts_at = Column(DateTime, default=datetime.utcnow, comment="生效时间")
    ends_at = Column(DateTime, nullable=True, comment="结束时间，为空表示长期")
    is_enabled = Column(Boolean, default=True, comment="是否启用")
    created_at = Column(DateTime, default=datetime.utcnow)


class Device(Base):
    """设备资产表"""
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False, comment="设备名称")
    ip_address = Column(String(45), unique=True, nullable=False, index=True, comment="IP地址")
    device_type = Column(String(50), nullable=False, comment="设备类型: router/switch/firewall/switch/security")
    monitor_type = Column(String(20), default="snmp", comment="接入方式: snmp/ping/tcp/api/ipmi")
    tcp_port = Column(Integer, default=80, comment="TCP端口探测端口")
    snmp_version = Column(String(10), default="v2c", comment="SNMP版本: v1/v2c/v3")
    community = Column(String(100), default="public", comment="SNMP Community (v1/v2c)")
    port = Column(Integer, default=161, comment="SNMP端口")
    # ---- SNMPv3 (USM) ----
    v3_username = Column(String(100), comment="v3 安全名/用户名")
    v3_security_level = Column(String(30), default="authPriv",
                               comment="v3 安全级别: noAuthNoPriv/authNoPriv/authPriv")
    v3_auth_protocol = Column(String(20), default="SHA",
                              comment="v3 认证协议: MD5/SHA/SHA224/SHA256/SHA384/SHA512")
    v3_auth_password = Column(String(255), comment="v3 认证密码")
    v3_priv_protocol = Column(String(20), default="AES",
                              comment="v3 加密协议: DES/AES/AES192/AES256")
    v3_priv_password = Column(String(255), comment="v3 加密密码")
    v3_context_name = Column(String(100), comment="v3 上下文名（可空）")
    location = Column(String(500), comment="设备位置")
    vendor = Column(String(100), comment="厂商")
    model = Column(String(200), comment="型号")
    serial_number = Column(String(200), comment="序列号")
    description = Column(Text, comment="描述")
    is_enabled = Column(Boolean, default=True, comment="是否启用监控")
    tags = Column(JSON, default=list, comment="标签")
    icon = Column(String(500), comment="自定义图标 URL（为空则使用类型默认图标）")
    # 维保 / 资产标签
    asset_no = Column(String(100), comment="资产编号")
    purchase_date = Column(String(20), comment="采购日期 YYYY-MM-DD")
    warranty_start = Column(String(20), comment="维保开始日期 YYYY-MM-DD")
    warranty_until = Column(String(20), comment="维保到期日期 YYYY-MM-DD")
    maintenance_vendor = Column(String(100), comment="维保厂商")
    maintenance_contact = Column(String(100), comment="维保联系人")
    maintenance_phone = Column(String(50), comment="维保联系电话")
    # 采集优化：引用的 MIB 文件与自定义指标 OID
    mib_id = Column(Integer, comment="引用的 MIB 文件 ID")
    # 统一设备凭据（SSH/巡检/备份共用）
    credential_id = Column(Integer, ForeignKey("device_credentials.id"), nullable=True, index=True,
                           comment="关联设备凭据")
    # 配置备份（SSH）
    backup_enabled = Column(Boolean, default=False, comment="是否加入配置备份")
    backup_username = Column(String(100), comment="配置备份 SSH 用户名")
    backup_password = Column(String(255), comment="配置备份 SSH 密码")
    backup_port = Column(Integer, default=22, comment="配置备份 SSH 端口")
    backup_command = Column(String(200), comment="自定义配置查看命令（空则按厂商）")
    # 戴尔存储只读 API（SNMP 不能提供硬件状态时使用）
    storage_username = Column(String(100), comment="存储只读 API 用户名")
    storage_password_enc = Column(String(500), comment="存储只读 API 密码密文")
    storage_api_port = Column(Integer, default=443, comment="API HTTPS 端口")
    api_auth_type = Column(String(20), default="auto", comment="API 认证方式: auto/basic/bearer/session")
    api_base_path = Column(String(300), comment="API 基础路径，如 /api/v1")
    api_paths = Column(JSON, default=dict, comment="API 自定义路径: {login, metrics}")
    ipmi_username = Column(String(100), comment="IPMI 用户名")
    ipmi_password_enc = Column(String(500), comment="IPMI 密码密文")
    ipmi_protocol = Column(String(20), default="auto", comment="IPMI 协议: auto/lanplus/lan")
    ipmi_port = Column(Integer, default=623, comment="IPMI UDP 端口")
    backup_interval_hours = Column(Integer, default=0, comment="设备独立备份间隔小时，0 使用全局")
    custom_oids = Column(JSON, default=dict, comment="自定义采集 OID: {cpu/memory/temperature/power: oid}")
    custom_metrics = Column(JSON, default=list, comment="自定义指标: [{key,name,oid,unit,scale}]")
    # 服务器硬件监控：CPU温度/内存故障/电源电压电流/硬盘故障/进排风温度等
    server_sensors = Column(JSON, default=list, comment="服务器硬件传感器: [{key,name,oid,unit,scale,kind}]")
    # 拓扑图中手动拖动后的节点坐标（为空则使用自动分层布局）
    topo_x = Column(Float, comment="拓扑节点 X 坐标")
    topo_y = Column(Float, comment="拓扑节点 Y 坐标")
    topo_width = Column(Float, comment="拓扑节点宽度")
    topo_height = Column(Float, comment="拓扑节点高度")
    # ---- 机柜上架与功率 ----
    cabinet_id = Column(Integer, ForeignKey("cabinets.id"), nullable=True, index=True,
                        comment="所在机柜")
    u_position = Column(Integer, comment="起始 U 位（从机柜底部起算，1 开始）")
    u_height = Column(Integer, default=1, comment="占用 U 数")
    power_watts = Column(Float, default=0, comment="额定功率(W)")
    # ---- 资产归属群组（按群组控制可见范围）----
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=True, index=True,
                      comment="所属资产群组")
    # ---- 资产来源 ----
    source = Column(String(20), default="manual", index=True,
                    comment="资产来源: manual 手动添加 / auto 自动发现")
    discovered_at = Column(DateTime, comment="自动发现入库时间")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关联关系
    cabinet = relationship("Cabinet", back_populates="devices")
    credential = relationship("DeviceCredential", back_populates="devices")
    config_backups = relationship("ConfigBackup", back_populates="device", cascade="all, delete-orphan")
    interfaces = relationship("DeviceInterface", back_populates="device", cascade="all, delete-orphan")
    metrics = relationship("DeviceMetric", back_populates="device", cascade="all, delete-orphan")
    connections = relationship("DeviceConnection", back_populates="source_device", foreign_keys="DeviceConnection.source_device_id", cascade="all, delete-orphan")
    connections_dest = relationship("DeviceConnection", back_populates="dest_device", foreign_keys="DeviceConnection.dest_device_id", cascade="all, delete-orphan")


class DeviceCredential(Base):
    """设备凭据：巡检、配置备份共用，一次录入可分配多台资产。"""
    __tablename__ = "device_credentials"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(120), nullable=False, comment="凭据名称")
    username = Column(String(120), nullable=False, comment="用户名")
    password = Column(String(500), comment="密码")
    port = Column(Integer, default=22, comment="SSH 端口")
    description = Column(String(500), comment="说明")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    devices = relationship("Device", back_populates="credential")


class DeviceInterface(Base):
    """设备接口表"""
    __tablename__ = "device_interfaces"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    if_index = Column(String(100), comment="接口索引")
    if_name = Column(String(100), comment="接口名称")
    if_type = Column(String(100), comment="接口类型")
    if_mac = Column(String(32), comment="接口物理地址 MAC")
    if_mtu = Column(Integer, comment="MTU")
    if_speed = Column(Float, comment="接口速率(bps)")
    if_oper_status = Column(String(20), comment="操作状态: up/down/notpresent")
    if_admin_status = Column(String(20), comment="管理状态")
    if_description = Column(String(500), comment="接口描述")
    # 流量计数（SNMP 64 位计数器，用 Float 兼容大数值）
    in_octets = Column(Float, comment="入方向字节数")
    out_octets = Column(Float, comment="出方向字节数")
    in_errors = Column(Integer, comment="入方向错误包")
    out_errors = Column(Integer, comment="出方向错误包")
    # 根据相邻两次采样差值计算的实时速率（bps）
    in_bps = Column(Float, comment="入方向速率(bps)")
    out_bps = Column(Float, comment="出方向速率(bps)")
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    device = relationship("Device", back_populates="interfaces")


class InterfaceMetric(Base):
    """接口流量历史（按采样间隔保存，用于详情时间范围查询）"""
    __tablename__ = "interface_metrics"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    interface_id = Column(Integer, ForeignKey("device_interfaces.id", ondelete="CASCADE"), nullable=False, index=True)
    if_name = Column(String(100), comment="接口名称快照")
    in_bps = Column(Float, comment="入方向速率(bps)")
    out_bps = Column(Float, comment="出方向速率(bps)")
    in_octets = Column(Float, comment="入方向累计字节")
    out_octets = Column(Float, comment="出方向累计字节")
    in_errors = Column(Integer, comment="入方向累计错误包")
    out_errors = Column(Integer, comment="出方向累计错误包")
    oper_status = Column(String(20), comment="up/down/notpresent")
    collected_at = Column(DateTime, default=datetime.utcnow, index=True)


class DeviceMetric(Base):
    """设备监控指标表"""
    __tablename__ = "device_metrics"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    cpu_usage = Column(Float, comment="CPU使用率(%)")
    memory_usage = Column(Float, comment="内存使用率(%)")
    memory_total = Column(Float, comment="总内存(MB)")
    memory_used = Column(Float, comment="已用内存(MB)")
    disk_usage = Column(Float, comment="磁盘使用率(%)")
    disk_total = Column(Float, comment="磁盘总容量(MB)")
    disk_used = Column(Float, comment="磁盘已用容量(MB)")
    temperature = Column(Float, comment="温度(℃)")
    power_status = Column(String(20), comment="电源状态: normal/failure")
    uptime = Column(Integer, comment="运行时间(秒)")
    custom = Column(JSON, default=dict, comment="自定义指标采集值: {metric_key: value}")
    collected_at = Column(DateTime, default=datetime.utcnow)

    device = relationship("Device", back_populates="metrics")


class DeviceConnection(Base):
    """设备连接关系表（用于拓扑生成）"""
    __tablename__ = "device_connections"

    id = Column(Integer, primary_key=True, index=True)
    source_device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    source_interface = Column(String(100), comment="源接口")
    dest_device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    dest_interface = Column(String(100), comment="目的接口")
    # 拖拽连线时记录鼠标在设备框内的相对位置（0~1），用于保持精确起点/终点
    source_anchor = Column(JSON, comment="源端锚点 {x,y}")
    dest_anchor = Column(JSON, comment="目的端锚点 {x,y}")
    edge_offset = Column(JSON, comment="连线路径手动偏移 {x,y}")
    edge_label_offset = Column(JSON, comment="流量标签组手动偏移 {x,y}")
    discovered_at = Column(DateTime, default=datetime.utcnow)

    source_device = relationship("Device", foreign_keys=[source_device_id], back_populates="connections")
    dest_device = relationship("Device", foreign_keys=[dest_device_id], back_populates="connections_dest")


class Alert(Base):
    """告警记录表"""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, ForeignKey("devices.id"), nullable=False)
    alert_type = Column(String(50), nullable=False, comment="告警类型: cpu/memory/temperature/offline/rule_ID")
    alert_level = Column(String(20), nullable=False, comment="告警级别: info/warning/critical/emergency")
    level_label = Column(String(50), comment="自定义级别显示名称")
    rule_id = Column(Integer, nullable=True, comment="资产告警规则 ID")
    message = Column(Text, comment="告警信息")
    value = Column(Float, comment="触发值")
    threshold = Column(Float, comment="阈值")
    is_acknowledged = Column(Boolean, default=False, comment="是否已确认")
    acknowledged_at = Column(DateTime, comment="最近一次人工确认时间")
    resolved_at = Column(DateTime, comment="自动恢复时间")
    resolution = Column(String(50), comment="恢复方式: device_recovered 等")
    is_hidden = Column(Boolean, default=False, index=True, comment="人工抑制后从活动列表隐藏")
    created_at = Column(DateTime, default=datetime.utcnow)

    device = relationship("Device")
