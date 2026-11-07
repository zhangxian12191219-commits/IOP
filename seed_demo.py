#!/usr/bin/env python3
"""演示数据初始化脚本（用于无真实 SNMP 设备时验证界面）

用法:
    python seed_demo.py

会生成:
- 8 台演示设备（路由器/交换机/防火墙/安全设备）
- 设备之间的拓扑连接
- 每台设备 24 小时的 CPU/内存/温度 历史指标
- 接口列表（含 up/down 状态）
- 若干告警
- 2 个网站监控目标

注意: 演示设备的 IP 为保留测试网段，SNMP 实际不可达，
      采集器会为它们产生“离线”告警，这是预期行为。
"""
import sys
import random
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
WORKSPACE = ROOT.parent
VENDOR = WORKSPACE / "vendor"
if VENDOR.exists():
    sys.path.insert(0, str(VENDOR))
sys.path.insert(0, str(ROOT))

from backend.models.database import SessionLocal, init_db  # noqa: E402
from backend.models.models import (  # noqa: E402
    Device, DeviceInterface, DeviceMetric, DeviceConnection, Alert,
)
from backend.models.room import (  # noqa: E402
    Cabinet, Room, RoomSensor, RoomSensorReading,
)
from backend.models.maintenance import DeviceMaintenance  # noqa: E402
from backend.models.website import WebsiteTarget  # noqa: E402

random.seed(20261027)

DEMO_DEVICES = [
    # name, ip, type, vendor, model, location
    ("核心路由器-01", "10.20.0.1", "router", "Huawei", "NE40E-X8A", "数据中心-A区"),
    ("核心交换机-01", "10.20.0.2", "switch", "Huawei", "S12700E-8", "数据中心-A区"),
    ("核心交换机-02", "10.20.0.3", "switch", "H3C", "S12508X-AF", "数据中心-A区"),
    ("汇聚交换机-01", "10.20.1.11", "switch", "Cisco", "C9300-48P", "办公楼-3F"),
    ("接入交换机-01", "10.20.2.21", "switch", "Ruijie", "S5720-28X", "办公楼-2F"),
    ("防火墙-01", "10.20.0.254", "firewall", "Fortinet", "FG-1800F", "数据中心-A区"),
    ("边界防火墙-02", "10.20.0.253", "firewall", "Sangfor", "AF-2000", "数据中心-A区"),
    ("行为安全网关-01", "10.20.0.250", "security", "TopSec", "NGFW-4000", "数据中心-A区"),
]

CONNECTIONS = [
    (0, 1, "GE0/0/1", "GE1/0/1"),
    (0, 2, "GE0/0/2", "GE1/0/1"),
    (0, 5, "GE0/0/3", "port1"),
    (1, 3, "GE1/0/10", "GigabitEthernet1/0/1"),
    (2, 3, "GE1/0/10", "GigabitEthernet1/0/2"),
    (3, 4, "GigabitEthernet1/0/24", "GE0/24"),
    (5, 6, "port2", "port1"),
    (5, 7, "port3", "GE0/1"),
]

IFACE_PREFIX = {
    "router": "GE0/0/",
    "switch": "GigabitEthernet1/0/",
    "firewall": "port",
    "security": "GE0/",
}

WEB_TARGETS = [
    ("公司官网", "https://www.example.com", "http"),
    ("搜索引擎", "https://www.baidu.com", "http"),
]

# 机房 / 机柜 / 上架（设备序号, 机柜序号, 起始U, 高度U, 功率W）
DEMO_ROOM = {
    "name": "数据中心A区",
    "building": "总部大楼",
    "floor": "B1",
    "location": "B1-东侧机房",
    "description": "演示机房（含 7 个机柜）",
    "length_m": 12.0,
    "width_m": 8.0,
    "height_m": 3.2,
    "floor_color": "#1f2937",
    "power_capacity_w": 60000,
}

DEMO_CABINETS = [
    # name, row, col, u_capacity, power_capacity_w
    ("A01-核心网络柜", 0, 0, 42, 6000),
    ("A02-核心网络柜", 0, 1, 42, 6000),
    ("A03-安全设备柜", 0, 2, 42, 6000),
    ("A04-安全设备柜", 0, 3, 42, 6000),
    ("B01-接入网络柜", 1, 0, 42, 6000),
    ("B02-接入网络柜", 1, 1, 42, 6000),
    ("B03-预留机柜", 1, 2, 42, 6000),
]

DEMO_PLACEMENT = {
    0: (0, 30, 8, 1200),   # 核心路由器-01
    1: (0, 20, 2, 800),    # 核心交换机-01
    2: (1, 20, 2, 800),    # 核心交换机-02
    3: (4, 40, 1, 350),    # 汇聚交换机-01
    4: (5, 40, 1, 150),    # 接入交换机-01
    5: (2, 30, 1, 450),    # 防火墙-01
    6: (3, 30, 1, 450),    # 边界防火墙-02
    7: (2, 20, 2, 600),    # 行为安全网关-01
}

# 机房温湿度传感器（演示数据）
DEMO_SENSORS = [
    ("冷通道-温湿度", "combined", "demo", 21.5, 45.0, 30.0, 16.0, 70.0, 30.0),
    ("热通道-温湿度", "combined", "demo", 26.5, 42.0, 32.0, 18.0, 70.0, 30.0),
    ("B排-湿度", "humidity", "demo", None, 52.0, 30.0, 16.0, 70.0, 30.0),
]

# 维保记录（设备序号, 类型, 标题, 说明, 工程师, 费用）
DEMO_MAINTENANCE = [
    (0, "inspection", "季度巡检", "检查电源、风扇与接口状态，清理灰尘。", "张工", 0),
    (0, "parts", "更换风扇模块", "更换 3 号风扇模块，运行正常。", "李工", 680),
    (5, "repair", "电源模块维修", "更换冗余电源模块，双电源恢复正常。", "王工", 1250),
    (1, "inspection", "年度巡检", "配置备份与固件版本检查。", "张工", 0),
]


def seed() -> None:
    init_db()
    db = SessionLocal()
    try:
        # ---------- 设备 ----------
        devices = []
        for index, (name, ip, dtype, vendor, model, loc) in enumerate(DEMO_DEVICES):
            dev = db.query(Device).filter(Device.ip_address == ip).first()
            if not dev:
                dev = Device(
                    name=name, ip_address=ip, device_type=dtype,
                    snmp_version="v2c", community="public", port=161,
                    location=loc, vendor=vendor, model=model,
                    description="演示数据", is_enabled=True, tags=["demo"],
                    created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
                )
                db.add(dev)
                db.flush()
            # 维保 / 资产标签信息（已有数据时也补齐）
            if not dev.asset_no:
                dev.asset_no = f"IT-{1001 + index}"
            if not dev.purchase_date:
                dev.purchase_date = f"2023-{(index % 12) + 1:02d}-15"
            if not dev.warranty_until:
                # 最后两台故意临近/超过维保期，便于界面展示提醒
                if index == 6:
                    dev.warranty_until = (datetime.utcnow() - timedelta(days=12)).strftime("%Y-%m-%d")
                elif index == 4:
                    dev.warranty_until = (datetime.utcnow() + timedelta(days=21)).strftime("%Y-%m-%d")
                else:
                    dev.warranty_until = (datetime.utcnow() + timedelta(days=240 + index * 30)).strftime("%Y-%m-%d")
            if not dev.maintenance_vendor:
                dev.maintenance_vendor = f"{vendor} 授权服务商"
            if not dev.maintenance_contact:
                dev.maintenance_contact = "售后工程师"
            if not dev.maintenance_phone:
                dev.maintenance_phone = "400-800-1234"
            devices.append(dev)
        db.commit()
        print(f"[OK] 设备: {len(devices)} 台（含资产编号/维保信息）")

        # ---------- 机房与机柜 ----------
        room = db.query(Room).filter(Room.name == DEMO_ROOM["name"]).first()
        if not room:
            room = Room(
                **DEMO_ROOM,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(room)
            db.flush()
            print(f"[OK] 机房: {room.name}（{room.length_m}x{room.width_m}m）")
        else:
            print(f"[OK] 机房已存在: {room.name}")

        cabinets = []
        for index, (name, row, col, u_cap, power_cap) in enumerate(DEMO_CABINETS):
            cab = db.query(Cabinet).filter(
                Cabinet.room_id == room.id, Cabinet.name == name
            ).first()
            if not cab:
                cab = Cabinet(
                    room_id=room.id,
                    name=name,
                    row_index=row,
                    col_index=col,
                    u_capacity=u_cap,
                    power_capacity_w=power_cap,
                    width_m=0.6,
                    depth_m=1.2,
                    rotation=0,
                    door_state="closed",
                    model="标准42U机柜",
                    lock_type="demo",
                    lock_config={"auto_lock": True},
                    is_locked=True,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                db.add(cab)
                db.flush()
            elif not cab.lock_type or cab.lock_type == "none":
                # 已有数据补齐演示电子锁配置
                cab.lock_type = "demo"
                cab.lock_config = {"auto_lock": True}
                cab.is_locked = True
            cabinets.append(cab)
        db.commit()
        print(f"[OK] 机柜: {len(cabinets)} 个（演示电子锁）")

        # ---------- 设备上架（U 位 + 功率） ----------
        placed = 0
        for idx, (cab_idx, u_pos, u_height, power_w) in DEMO_PLACEMENT.items():
            if idx >= len(devices):
                continue
            device = devices[idx]
            cabinet = cabinets[cab_idx]
            device.cabinet_id = cabinet.id
            device.u_position = u_pos
            device.u_height = u_height
            device.power_watts = power_w
            placed += 1
        db.commit()
        print(f"[OK] 上架设备: {placed} 台（已按机柜功率校验范围配置）")

        # ---------- 接口 ----------
        iface_count = 0
        for dev in devices:
            existing = db.query(DeviceInterface).filter_by(device_id=dev.id).count()
            if existing:
                continue
            prefix = IFACE_PREFIX.get(dev.device_type, "GE0/")
            total = 24 if dev.device_type == "switch" else 8
            for i in range(1, total + 1):
                up = random.random() > 0.18
                db.add(DeviceInterface(
                    device_id=dev.id,
                    if_index=str(i),
                    if_name=f"{prefix}{i}",
                    if_type="6" if dev.device_type == "switch" else "24",
                    if_mtu=1500,
                    if_speed=1_000_000_000 if i <= 4 else 100_000_000,
                    if_oper_status="up" if up else "down",
                    if_admin_status="up",
                    if_description=f"上联/下联端口 {i}",
                    updated_at=datetime.utcnow(),
                ))
                iface_count += 1
        db.commit()
        print(f"[OK] 接口: {iface_count} 个")

        # ---------- 拓扑连接 ----------
        conn_added = 0
        for si, di, sif, dif in CONNECTIONS:
            src, dst = devices[si], devices[di]
            exists = db.query(DeviceConnection).filter_by(
                source_device_id=src.id, dest_device_id=dst.id
            ).first()
            if exists:
                continue
            db.add(DeviceConnection(
                source_device_id=src.id, source_interface=sif,
                dest_device_id=dst.id, dest_interface=dif,
                discovered_at=datetime.utcnow(),
            ))
            conn_added += 1
        db.commit()
        print(f"[OK] 拓扑连接: {conn_added} 条")

        # ---------- 24 小时指标 ----------
        now = datetime.utcnow()
        points = 0
        # 演示自定义指标（光功率 / 风扇转速）
        custom_defs = [
            {"key": "optical_rx", "name": "光模块收光功率", "oid": "1.3.6.1.4.1.2011.99.4.1",
             "unit": "dBm", "scale": 1},
            {"key": "fan_speed", "name": "风扇转速", "oid": "1.3.6.1.4.1.2011.99.5.1",
             "unit": "RPM", "scale": 1},
        ]
        if devices and not devices[0].custom_metrics:
            devices[0].custom_metrics = custom_defs
            db.commit()
        for dev in devices:
            has = db.query(DeviceMetric).filter_by(device_id=dev.id).count()
            if has:
                continue
            base_cpu = random.uniform(18, 42)
            base_mem = random.uniform(35, 62)
            base_temp = random.uniform(34, 44)
            base_optical = random.uniform(-8.5, -2.0)
            base_fan = random.uniform(3200, 5200)
            for i in range(288):  # 每 5 分钟一个点，24 小时
                ts = now - timedelta(minutes=5 * (287 - i))
                hour = ts.hour
                # 工作时间负载略高
                busy = 1.18 if 9 <= hour <= 18 else 0.92
                noise = random.uniform(-4, 4)
                cpu = max(1.0, min(98.0, base_cpu * busy + noise))
                mem = max(5.0, min(96.0, base_mem + random.uniform(-4, 4)))
                temp = max(20.0, min(95.0, base_temp + cpu * 0.12 + random.uniform(-1, 1)))
                custom = {}
                if devices and dev.id == devices[0].id:
                    custom = {
                        "optical_rx": round(base_optical + random.uniform(-0.6, 0.6), 2),
                        "fan_speed": round(base_fan + random.uniform(-250, 250)),
                    }
                db.add(DeviceMetric(
                    device_id=dev.id,
                    cpu_usage=round(cpu, 2),
                    memory_usage=round(mem, 2),
                    memory_total=round(random.uniform(2048, 8192), 0),
                    memory_used=round(mem * 40, 2),
                    temperature=round(temp, 1),
                    power_status="normal",
                    uptime=3_600_000 + i * 300,
                    custom=custom,
                    collected_at=ts,
                ))
                points += 1
        db.commit()
        print(f"[OK] 指标记录: {points} 条")

        # ---------- 告警 ----------
        db.query(Alert).filter(Alert.device_id.in_([d.id for d in devices])).delete(
            synchronize_session=False
        )
        db.commit()
        alert_defs = [
            (devices[3], "cpu", "warning", "CPU使用率 84.5% 超过阈值 80%", 84.5, 80.0),
            (devices[4], "memory", "critical", "内存使用率 93.1% 超过阈值 85%", 93.1, 85.0),
            (devices[6], "temperature", "warning", "温度 72.4°C 超过阈值 70°C", 72.4, 70.0),
            (devices[5], "power", "critical", "电源状态异常", None, None),
        ]
        for dev, atype, level, msg, val, th in alert_defs:
            db.add(Alert(
                device_id=dev.id, alert_type=atype, alert_level=level,
                message=f"{dev.name}: {msg}", value=val, threshold=th,
                is_acknowledged=False,
                created_at=now - timedelta(minutes=random.randint(3, 90)),
            ))
        db.commit()
        print(f"[OK] 告警: {len(alert_defs)} 条")

        # ---------- 机房温湿度传感器 ----------
        sensor_added = 0
        now = datetime.utcnow()
        for name, stype, source, temp, hum, t_high, t_low, h_high, h_low in DEMO_SENSORS:
            sensor = db.query(RoomSensor).filter_by(room_id=room.id, name=name).first()
            if sensor:
                continue
            sensor = RoomSensor(
                room_id=room.id,
                name=name,
                sensor_type=stype,
                source=source,
                temp_high=t_high,
                temp_low=t_low,
                humidity_high=h_high,
                humidity_low=h_low,
                is_enabled=True,
                created_at=now,
            )
            db.add(sensor)
            db.flush()
            sensor_added += 1

            # 24 小时历史（每 10 分钟一个点）
            last_t = temp if temp is not None else 24.0
            last_h = hum if hum is not None else 45.0
            for i in range(144):
                last_t = max(16.0, min(33.0, last_t + random.uniform(-0.5, 0.5)))
                last_h = max(25.0, min(75.0, last_h + random.uniform(-1.5, 1.5)))
                db.add(RoomSensorReading(
                    sensor_id=sensor.id,
                    temperature=round(last_t, 1) if stype in ("temperature", "combined") else None,
                    humidity=round(last_h, 1) if stype in ("humidity", "combined") else None,
                    recorded_at=now - timedelta(minutes=10 * i),
                ))
            sensor.last_temperature = round(last_t, 1) if stype in ("temperature", "combined") else None
            sensor.last_humidity = round(last_h, 1) if stype in ("humidity", "combined") else None
            sensor.last_updated = now
        db.commit()
        print(f"[OK] 温湿度传感器: 新增 {sensor_added} 个（含 24 小时历史）")

        # ---------- 维保记录 ----------
        maint_added = 0
        for dev_index, mtype, title, desc, engineer, cost in DEMO_MAINTENANCE:
            if dev_index >= len(devices):
                continue
            dev = devices[dev_index]
            exists = db.query(DeviceMaintenance).filter_by(
                device_id=dev.id, title=title
            ).first()
            if exists:
                continue
            db.add(DeviceMaintenance(
                device_id=dev.id,
                maint_type=mtype,
                title=title,
                description=desc,
                engineer=engineer,
                cost=cost,
                maintained_at=datetime.utcnow() - timedelta(days=random.randint(5, 180)),
                created_by="system",
                created_at=datetime.utcnow(),
            ))
            maint_added += 1
        db.commit()
        print(f"[OK] 维保记录: 新增 {maint_added} 条")

        # ---------- 网站监控目标 ----------
        target_added = 0
        for name, url, mtype in WEB_TARGETS:
            if db.query(WebsiteTarget).filter_by(url=url).first():
                continue
            db.add(WebsiteTarget(
                name=name, url=url, monitor_type=mtype,
                method="GET", expected_status=200, timeout=10,
                check_interval=60, is_enabled=True,
                description="演示数据",
                created_at=datetime.utcnow(), updated_at=datetime.utcnow(),
            ))
            target_added += 1
        db.commit()
        print(f"[OK] 网站监控目标: {target_added} 个")

        print("\n演示数据初始化完成。启动前后端后访问 http://localhost:5173")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
