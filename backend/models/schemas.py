"""Pydantic 请求/响应模型"""
from typing import Optional, List, Any, Dict
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


# ==================== 设备 ====================

class DeviceBase(BaseModel):
    name: str = Field(..., description="设备名称")
    ip_address: str = Field(..., description="IP地址")
    device_type: str = Field(..., description="设备类型: router/switch/firewall/security")
    monitor_type: str = "snmp"
    tcp_port: Optional[int] = 80
    snmp_version: str = "v2c"
    community: str = "public"
    port: int = 161
    # SNMPv3
    v3_username: Optional[str] = None
    v3_security_level: Optional[str] = "authPriv"
    v3_auth_protocol: Optional[str] = "SHA"
    v3_auth_password: Optional[str] = None
    v3_priv_protocol: Optional[str] = "AES"
    v3_priv_password: Optional[str] = None
    v3_context_name: Optional[str] = None
    location: Optional[str] = None
    vendor: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    description: Optional[str] = None
    is_enabled: bool = True
    tags: Optional[List[str]] = None
    icon: Optional[str] = None
    # 维保 / 资产标签
    asset_no: Optional[str] = None
    purchase_date: Optional[str] = None
    warranty_start: Optional[str] = None
    warranty_until: Optional[str] = None
    maintenance_vendor: Optional[str] = None
    maintenance_contact: Optional[str] = None
    maintenance_phone: Optional[str] = None
    mib_id: Optional[int] = None
    custom_oids: Optional[Dict[str, str]] = None
    custom_metrics: Optional[List[Dict[str, Any]]] = None
    server_sensors: Optional[List[Dict[str, Any]]] = None
    # 机柜上架与功率
    cabinet_id: Optional[int] = None
    u_position: Optional[int] = None
    u_height: Optional[int] = 1
    power_watts: Optional[float] = 0
    group_id: Optional[int] = None
    storage_username: Optional[str] = None
    storage_password: Optional[str] = None
    storage_api_port: Optional[int] = None
    api_auth_type: Optional[str] = "auto"
    api_base_path: Optional[str] = None
    api_paths: Optional[Dict[str, Any]] = None
    ipmi_username: Optional[str] = None
    ipmi_password: Optional[str] = None
    ipmi_protocol: Optional[str] = "auto"
    ipmi_port: Optional[int] = 623


class DeviceCreate(DeviceBase):
    pass


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    ip_address: Optional[str] = None
    device_type: Optional[str] = None
    monitor_type: Optional[str] = None
    tcp_port: Optional[int] = None
    snmp_version: Optional[str] = None
    community: Optional[str] = None
    port: Optional[int] = None
    v3_username: Optional[str] = None
    v3_security_level: Optional[str] = None
    v3_auth_protocol: Optional[str] = None
    v3_auth_password: Optional[str] = None
    v3_priv_protocol: Optional[str] = None
    v3_priv_password: Optional[str] = None
    v3_context_name: Optional[str] = None
    location: Optional[str] = None
    vendor: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    description: Optional[str] = None
    is_enabled: Optional[bool] = None
    tags: Optional[List[str]] = None
    icon: Optional[str] = None
    # 维保 / 资产标签
    asset_no: Optional[str] = None
    purchase_date: Optional[str] = None
    warranty_start: Optional[str] = None
    warranty_until: Optional[str] = None
    maintenance_vendor: Optional[str] = None
    maintenance_contact: Optional[str] = None
    maintenance_phone: Optional[str] = None
    mib_id: Optional[int] = None
    custom_oids: Optional[Dict[str, str]] = None
    custom_metrics: Optional[List[Dict[str, Any]]] = None
    server_sensors: Optional[List[Dict[str, Any]]] = None
    cabinet_id: Optional[int] = None
    u_position: Optional[int] = None
    u_height: Optional[int] = None
    power_watts: Optional[float] = None
    group_id: Optional[int] = None
    storage_username: Optional[str] = None
    storage_password: Optional[str] = None
    storage_api_port: Optional[int] = None
    api_auth_type: Optional[str] = None
    api_base_path: Optional[str] = None
    api_paths: Optional[Dict[str, Any]] = None
    ipmi_username: Optional[str] = None
    ipmi_password: Optional[str] = None
    ipmi_protocol: Optional[str] = None
    ipmi_port: Optional[int] = None


class MetricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    cpu_usage: Optional[float] = None
    memory_usage: Optional[float] = None
    memory_total: Optional[float] = None
    memory_used: Optional[float] = None
    temperature: Optional[float] = None
    power_status: Optional[str] = None
    uptime: Optional[int] = None
    collected_at: Optional[datetime] = None


class DeviceOut(DeviceBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    metric: Optional[MetricOut] = None
    alert_count: int = 0


# ==================== 网站监控 ====================

class WebsiteTargetBase(BaseModel):
    name: str
    url: str
    domain: Optional[str] = None
    ip_address: Optional[str] = None
    monitor_type: str = "http"
    port: Optional[int] = None
    method: str = "GET"
    expected_status: int = 200
    expected_statuses: Optional[str] = None
    expected_keywords: Optional[str] = None
    timeout: int = 10
    check_interval: int = 60
    ignore_https_errors: bool = True
    cache_bust_seconds: int = 0
    category: Optional[str] = None
    category_mode: str = "auto"
    sort_order: int = 0
    cert_root_domain: Optional[str] = None
    cert_subdomains: Optional[str] = None
    slow_threshold_ms: float = 5000
    cert_monitor_enabled: bool = True
    cert_expiry_days: int = 30
    cert_alert_level: str = "warning"
    down_level: str = "critical"
    slow_level: str = "warning"
    down_level_label: Optional[str] = None
    slow_level_label: Optional[str] = None
    is_enabled: bool = True
    notify_email: Optional[str] = None
    notify_webhook: Optional[str] = None
    description: Optional[str] = None


class WebsiteTargetCreate(WebsiteTargetBase):
    pass


class WebsiteTargetUpdate(BaseModel):
    name: Optional[str] = None
    url: Optional[str] = None
    domain: Optional[str] = None
    ip_address: Optional[str] = None
    monitor_type: Optional[str] = None
    port: Optional[int] = None
    method: Optional[str] = None
    expected_status: Optional[int] = None
    expected_statuses: Optional[str] = None
    expected_keywords: Optional[str] = None
    timeout: Optional[int] = None
    check_interval: Optional[int] = None
    ignore_https_errors: Optional[bool] = None
    cache_bust_seconds: Optional[int] = None
    category: Optional[str] = None
    category_mode: Optional[str] = None
    sort_order: Optional[int] = None
    cert_root_domain: Optional[str] = None
    cert_subdomains: Optional[str] = None
    slow_threshold_ms: Optional[float] = None
    cert_monitor_enabled: Optional[bool] = None
    cert_expiry_days: Optional[int] = None
    cert_alert_level: Optional[str] = None
    down_level: Optional[str] = None
    slow_level: Optional[str] = None
    down_level_label: Optional[str] = None
    slow_level_label: Optional[str] = None
    is_enabled: Optional[bool] = None
    notify_email: Optional[str] = None
    notify_webhook: Optional[str] = None
    description: Optional[str] = None


# ==================== 拓扑 ====================

class ConnectionCreate(BaseModel):
    source_device_id: int
    source_interface: Optional[str] = ""
    dest_device_id: int
    dest_interface: Optional[str] = ""
    source_anchor: Optional[Dict[str, float]] = None
    dest_anchor: Optional[Dict[str, float]] = None


# ==================== 告警通知 ====================

class NotificationChannelBase(BaseModel):
    name: str = Field(..., description="通道名称")
    channel_type: str = Field(..., description="email / webhook / sms / upstream")
    enabled: bool = True
    min_level: str = Field("warning", description="warning 或 critical")
    config: Dict[str, Any] = Field(default_factory=dict, description="通道配置")


class NotificationChannelCreate(NotificationChannelBase):
    pass


class NotificationChannelUpdate(BaseModel):
    name: Optional[str] = None
    channel_type: Optional[str] = None
    enabled: Optional[bool] = None
    min_level: Optional[str] = None
    config: Optional[Dict[str, Any]] = None


# ==================== 机房 / 机柜 ====================

class RoomBase(BaseModel):
    name: str = Field(..., description="机房名称")
    building: Optional[str] = None
    floor: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    length_m: float = 12.0
    width_m: float = 8.0
    height_m: float = 3.2
    floor_color: Optional[str] = "#1f2937"
    power_capacity_w: Optional[float] = None


class RoomCreate(RoomBase):
    pass


class RoomUpdate(BaseModel):
    name: Optional[str] = None
    building: Optional[str] = None
    floor: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    length_m: Optional[float] = None
    width_m: Optional[float] = None
    height_m: Optional[float] = None
    floor_color: Optional[str] = None
    power_capacity_w: Optional[float] = None


class CabinetBase(BaseModel):
    name: str = Field(..., description="机柜名称/编号")
    room_id: int
    row_index: int = 0
    col_index: int = 0
    pos_x: Optional[float] = None
    pos_z: Optional[float] = None
    rotation: float = 0
    u_capacity: int = 42
    power_capacity_w: float = 6000
    width_m: float = 0.6
    depth_m: float = 1.2
    door_state: str = "closed"
    lock_type: str = "none"
    lock_config: Optional[Dict[str, Any]] = None
    is_locked: bool = True
    model: Optional[str] = None
    description: Optional[str] = None


class CabinetCreate(CabinetBase):
    pass


class CabinetUpdate(BaseModel):
    name: Optional[str] = None
    room_id: Optional[int] = None
    row_index: Optional[int] = None
    col_index: Optional[int] = None
    pos_x: Optional[float] = None
    pos_z: Optional[float] = None
    rotation: Optional[float] = None
    u_capacity: Optional[int] = None
    power_capacity_w: Optional[float] = None
    width_m: Optional[float] = None
    depth_m: Optional[float] = None
    door_state: Optional[str] = None
    lock_type: Optional[str] = None
    lock_config: Optional[Dict[str, Any]] = None
    is_locked: Optional[bool] = None
    model: Optional[str] = None
    description: Optional[str] = None


# ==================== 用户 / 角色 / 群组 ====================

class LoginRequest(BaseModel):
    username: str
    password: str
    captcha_id: Optional[str] = None
    captcha_code: Optional[str] = None
    # 已启用二次身份验证的账号，在第二次提交时携带 TOTP 动态验证码
    totp_code: Optional[str] = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=4, description="新密码（具体复杂度由系统密码策略校验）")


# ==================== 二次身份验证（TOTP） ====================

class TotpCodeRequest(BaseModel):
    code: str = Field(..., max_length=16, description="身份验证器中的 6 位动态验证码")


class TotpDisableRequest(BaseModel):
    code: str = Field(..., max_length=16, description="身份验证器中的 6 位动态验证码")
    password: str = Field(..., min_length=1, description="当前登录密码")


class RoleCreate(BaseModel):
    name: str = Field(..., max_length=100)
    code: Optional[str] = None
    description: Optional[str] = None
    permissions: List[str] = Field(default_factory=list)


class RoleUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None
    permissions: Optional[List[str]] = None


class GroupCreate(BaseModel):
    name: str = Field(..., max_length=100)
    code: Optional[str] = None
    description: Optional[str] = None


class GroupUpdate(BaseModel):
    name: Optional[str] = None
    code: Optional[str] = None
    description: Optional[str] = None


class UserCreate(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=4)
    real_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    is_active: bool = True
    is_superuser: bool = False
    role_ids: List[int] = Field(default_factory=list)
    group_ids: List[int] = Field(default_factory=list)


class UserUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=2, max_length=64)
    password: Optional[str] = Field(None, min_length=4)
    old_password: Optional[str] = None
    real_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    is_active: Optional[bool] = None
    is_superuser: Optional[bool] = None
    role_ids: Optional[List[int]] = None
    group_ids: Optional[List[int]] = None


# ==================== 维保记录 ====================

class MaintenanceCreate(BaseModel):
    maint_type: str = Field("inspection", description="repair/inspection/parts/other")
    title: str = Field(..., max_length=200)
    description: Optional[str] = None
    engineer: Optional[str] = None
    cost: Optional[float] = None
    maintained_at: Optional[datetime] = None


# ==================== 机房温湿度传感器 ====================

class SensorCreate(BaseModel):
    name: str = Field(..., max_length=100)
    sensor_type: str = "combined"          # temperature / humidity / combined
    source: str = "demo"                   # demo / snmp / xiaomi / rs485
    ip: Optional[str] = None
    snmp_version: str = "v2c"
    community: str = "public"
    port: int = 161
    oid_temperature: Optional[str] = None
    oid_humidity: Optional[str] = None
    xiaomi_url: Optional[str] = None
    xiaomi_token: Optional[str] = None
    xiaomi_device_id: Optional[str] = None
    xiaomi_temperature_path: str = "temperature"
    xiaomi_humidity_path: str = "humidity"
    serial_port: Optional[str] = None
    baudrate: int = 9600
    bytesize: int = 8
    parity: str = "N"
    stopbits: int = 1
    slave_id: int = 1
    function_code: int = 3
    register_temperature: int = 0
    register_humidity: Optional[int] = None
    register_count: int = 1
    temperature_scale: float = 0.1
    humidity_scale: float = 0.1
    signed_temperature: bool = True
    word_order: str = "big"
    serial_timeout: float = 1.0
    modbus_host: Optional[str] = None
    modbus_port: int = 502
    modbus_unit_id: int = 1
    modbus_timeout: float = 3.0
    mqtt_host: Optional[str] = None
    mqtt_port: int = 1883
    mqtt_username: Optional[str] = None
    mqtt_password: Optional[str] = None
    mqtt_topic: Optional[str] = None
    mqtt_tls: bool = False
    mqtt_client_id: Optional[str] = None
    mqtt_timeout: float = 5.0
    mqtt_temperature_path: str = "temperature"
    mqtt_humidity_path: str = "humidity"
    temp_high: float = 30.0
    temp_low: float = 15.0
    humidity_high: float = 70.0
    humidity_low: float = 30.0
    is_enabled: bool = True


class SensorUpdate(BaseModel):
    name: Optional[str] = None
    sensor_type: Optional[str] = None
    source: Optional[str] = None
    ip: Optional[str] = None
    snmp_version: Optional[str] = None
    community: Optional[str] = None
    port: Optional[int] = None
    oid_temperature: Optional[str] = None
    oid_humidity: Optional[str] = None
    xiaomi_url: Optional[str] = None
    xiaomi_token: Optional[str] = None
    xiaomi_device_id: Optional[str] = None
    xiaomi_temperature_path: Optional[str] = None
    xiaomi_humidity_path: Optional[str] = None
    serial_port: Optional[str] = None
    baudrate: Optional[int] = None
    bytesize: Optional[int] = None
    parity: Optional[str] = None
    stopbits: Optional[int] = None
    slave_id: Optional[int] = None
    function_code: Optional[int] = None
    register_temperature: Optional[int] = None
    register_humidity: Optional[int] = None
    register_count: Optional[int] = None
    temperature_scale: Optional[float] = None
    humidity_scale: Optional[float] = None
    signed_temperature: Optional[bool] = None
    word_order: Optional[str] = None
    serial_timeout: Optional[float] = None
    modbus_host: Optional[str] = None
    modbus_port: Optional[int] = None
    modbus_unit_id: Optional[int] = None
    modbus_timeout: Optional[float] = None
    mqtt_host: Optional[str] = None
    mqtt_port: Optional[int] = None
    mqtt_username: Optional[str] = None
    mqtt_password: Optional[str] = None
    mqtt_topic: Optional[str] = None
    mqtt_tls: Optional[bool] = None
    mqtt_client_id: Optional[str] = None
    mqtt_timeout: Optional[float] = None
    mqtt_temperature_path: Optional[str] = None
    mqtt_humidity_path: Optional[str] = None
    temp_high: Optional[float] = None
    temp_low: Optional[float] = None
    humidity_high: Optional[float] = None
    humidity_low: Optional[float] = None
    is_enabled: Optional[bool] = None


# ==================== 机柜电子锁 ====================

class CabinetLockConfig(BaseModel):
    lock_type: Optional[str] = None       # none / demo / http / relay_tcp
    lock_config: Optional[Dict[str, Any]] = None
    is_locked: Optional[bool] = None
