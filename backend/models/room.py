"""机房与机柜模型

- Room        机房（含尺寸、总功率）
- Cabinet     机柜（含所在机房、3D 位置、U 容量、功率上限、门状态、电子锁）
- CabinetAccessLog  机柜电子锁操作审计
- RoomSensor  机房温湿度传感器（SNMP / 演示）
- RoomSensorReading 传感器历史读数
- Device      设备的 cabinet_id / u_position / u_height / power_watts 字段在 models.py 中
"""
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, DateTime, Text, ForeignKey, JSON,
)
from sqlalchemy.orm import relationship
from datetime import datetime

from .database import Base


class Room(Base):
    """机房"""

    __tablename__ = "rooms"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False, comment="机房名称")
    building = Column(String(100), comment="楼宇")
    floor = Column(String(50), comment="楼层")
    location = Column(String(300), comment="详细位置")
    description = Column(Text, comment="描述")
    # 3D 房间尺寸（米）
    length_m = Column(Float, default=12.0, comment="长度(米)")
    width_m = Column(Float, default=8.0, comment="宽度(米)")
    height_m = Column(Float, default=3.2, comment="层高(米)")
    floor_color = Column(String(20), default="#1f2937", comment="地面颜色")
    # 机房总供电能力（瓦），仅用于展示与汇总
    power_capacity_w = Column(Float, comment="机房总功率(W)")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    cabinets = relationship(
        "Cabinet", back_populates="room", cascade="all, delete-orphan"
    )
    sensors = relationship(
        "RoomSensor", back_populates="room", cascade="all, delete-orphan"
    )


class Cabinet(Base):
    """机柜"""

    __tablename__ = "cabinets"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id"), nullable=False, index=True)
    name = Column(String(100), nullable=False, comment="机柜名称/编号")
    row_index = Column(Integer, default=0, comment="行")
    col_index = Column(Integer, default=0, comment="列")
    # 3D 位置与朝向
    pos_x = Column(Float, comment="X 坐标(米)，为空则按行列自动排布")
    pos_z = Column(Float, comment="Z 坐标(米)")
    rotation = Column(Float, default=0, comment="朝向角度(0/90/180/270)")
    # 规格
    u_capacity = Column(Integer, default=42, comment="U 容量")
    power_capacity_w = Column(Float, default=6000, comment="机柜额定功率(W)")
    width_m = Column(Float, default=0.6, comment="宽(米)")
    depth_m = Column(Float, default=1.2, comment="深(米)")
    door_state = Column(String(10), default="closed", comment="门状态: closed/open")
    # 电子锁：lock_type: none/http/relay_tcp/demo；lock_config 存地址/通道/密钥等
    lock_type = Column(String(20), default="none", comment="电子锁类型: none/http/relay_tcp/demo")
    lock_config = Column(JSON, default=dict, comment="电子锁配置")
    is_locked = Column(Boolean, default=True, comment="是否已上锁")
    last_unlock_at = Column(DateTime, comment="最近一次开锁时间")
    last_unlock_by = Column(String(100), comment="最近一次开锁人")
    model = Column(String(100), comment="机柜型号")
    description = Column(Text, comment="描述")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    room = relationship("Room", back_populates="cabinets")
    devices = relationship("Device", back_populates="cabinet")
    access_logs = relationship(
        "CabinetAccessLog", back_populates="cabinet", cascade="all, delete-orphan"
    )

    @property
    def height_m(self) -> float:
        """按 U 数换算高度（1U = 44.45mm）"""
        return round((self.u_capacity or 42) * 0.04445, 3)


class CabinetAccessLog(Base):
    """机柜电子锁操作审计日志"""

    __tablename__ = "cabinet_access_logs"

    id = Column(Integer, primary_key=True, index=True)
    cabinet_id = Column(
        Integer, ForeignKey("cabinets.id", ondelete="CASCADE"), index=True
    )
    action = Column(String(20), comment="unlock / lock / open_door / close_door")
    operator = Column(String(100), comment="操作人")
    success = Column(Boolean, default=True)
    message = Column(Text, comment="结果说明")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    cabinet = relationship("Cabinet", back_populates="access_logs")


class RoomSensor(Base):
    """机房温湿度传感器（SNMP 采集或演示数据）"""

    __tablename__ = "room_sensors"

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(Integer, ForeignKey("rooms.id", ondelete="CASCADE"), index=True)
    name = Column(String(100), nullable=False, comment="传感器名称")
    sensor_type = Column(String(20), default="combined", comment="temperature/humidity/combined")
    source = Column(String(20), default="demo", comment="demo / snmp / xiaomi / rs485 / modbus_tcp / mqtt")
    # SNMP 配置
    ip = Column(String(64), comment="传感器 IP")
    snmp_version = Column(String(10), default="v2c")
    community = Column(String(100), default="public")
    port = Column(Integer, default=161)
    oid_temperature = Column(String(200), comment="温度 OID")
    oid_humidity = Column(String(200), comment="湿度 OID")
    # 小米/米家网关 HTTP JSON 配置
    xiaomi_url = Column(String(500), comment="小米网关/桥接 HTTP JSON 地址")
    xiaomi_token = Column(String(300), comment="小米网关 Bearer Token（可选）")
    xiaomi_device_id = Column(String(120), comment="小米设备 ID（可选 query 参数）")
    xiaomi_temperature_path = Column(String(120), default="temperature", comment="温度 JSON 路径")
    xiaomi_humidity_path = Column(String(120), default="humidity", comment="湿度 JSON 路径")
    # RS485 / Modbus RTU 配置
    serial_port = Column(String(100), comment="串口，如 COM3 或 /dev/ttyUSB0")
    baudrate = Column(Integer, default=9600)
    bytesize = Column(Integer, default=8)
    parity = Column(String(2), default="N", comment="N/E/O")
    stopbits = Column(Integer, default=1)
    slave_id = Column(Integer, default=1, comment="Modbus 从站地址")
    function_code = Column(Integer, default=3, comment="03 保持寄存器 / 04 输入寄存器")
    register_temperature = Column(Integer, default=0, comment="温度寄存器起始地址")
    register_humidity = Column(Integer, comment="湿度寄存器起始地址，温度-only 可空")
    register_count = Column(Integer, default=1, comment="每个数值占用寄存器数（1/2）")
    temperature_scale = Column(Float, default=0.1, comment="温度缩放系数")
    humidity_scale = Column(Float, default=0.1, comment="湿度缩放系数")
    signed_temperature = Column(Boolean, default=True, comment="温度寄存器是否有符号")
    word_order = Column(String(10), default="big", comment="32 位寄存器字序 big/little")
    serial_timeout = Column(Float, default=1.0, comment="RS485 读取超时秒")
    # Modbus TCP 配置
    modbus_host = Column(String(120), comment="Modbus TCP 主机")
    modbus_port = Column(Integer, default=502)
    modbus_unit_id = Column(Integer, default=1, comment="Modbus TCP 单元 ID")
    modbus_timeout = Column(Float, default=3.0, comment="Modbus TCP 超时秒")
    # MQTT 配置
    mqtt_host = Column(String(120), comment="MQTT Broker 主机")
    mqtt_port = Column(Integer, default=1883)
    mqtt_username = Column(String(120))
    mqtt_password = Column(String(300))
    mqtt_topic = Column(String(300), comment="订阅主题")
    mqtt_tls = Column(Boolean, default=False)
    mqtt_client_id = Column(String(120), comment="客户端 ID（可选）")
    mqtt_timeout = Column(Float, default=5.0, comment="等待消息超时秒")
    mqtt_temperature_path = Column(String(120), default="temperature")
    mqtt_humidity_path = Column(String(120), default="humidity")
    # 阈值
    temp_high = Column(Float, default=30.0, comment="温度上限(℃)")
    temp_low = Column(Float, default=15.0, comment="温度下限(℃)")
    humidity_high = Column(Float, default=70.0, comment="湿度上限(%)")
    humidity_low = Column(Float, default=30.0, comment="湿度下限(%)")
    is_enabled = Column(Boolean, default=True)
    # 最新读数
    last_temperature = Column(Float)
    last_humidity = Column(Float)
    last_updated = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    room = relationship("Room", back_populates="sensors")
    readings = relationship(
        "RoomSensorReading", back_populates="sensor", cascade="all, delete-orphan"
    )


class RoomSensorReading(Base):
    """温湿度历史读数"""

    __tablename__ = "room_sensor_readings"

    id = Column(Integer, primary_key=True, index=True)
    sensor_id = Column(
        Integer, ForeignKey("room_sensors.id", ondelete="CASCADE"), index=True
    )
    temperature = Column(Float)
    humidity = Column(Float)
    recorded_at = Column(DateTime, default=datetime.utcnow, index=True)

    sensor = relationship("RoomSensor", back_populates="readings")
