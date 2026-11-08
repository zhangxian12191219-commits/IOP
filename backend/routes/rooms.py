"""机房与机柜路由 - CRUD、开门、电子锁、温湿度传感器、3D 布局"""
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..models.models import Device, DeviceMetric, Alert
from ..models.room import (
    Cabinet, CabinetAccessLog, Room, RoomSensor, RoomSensorReading,
)
from ..models.schemas import (
    CabinetCreate, CabinetLockConfig, CabinetUpdate, RoomCreate, RoomUpdate,
    SensorCreate, SensorUpdate,
)
from ..services import cabinet_lock
from ..services.placement import cabinet_devices, cabinet_usage, u_range

router = APIRouter(prefix="/api/rooms", tags=["机房与机柜"])

# 3D 自动排布参数（米）
CABINET_GAP_X = 0.9      # 同排机柜之间间隙
ROW_GAP_Z = 2.2          # 排间距（冷热通道）
ROOM_MARGIN = 1.2        # 距墙距离


# ==================== 工具 ====================
def device_status(db: Session, device: Device) -> str:
    """设备状态：online / warning / offline / unknown"""
    offline = db.query(Alert).filter(
        Alert.device_id == device.id,
        Alert.alert_type == "offline",
        Alert.is_acknowledged == False,  # noqa: E712
    ).first()
    if offline:
        return "offline"

    metric = (
        db.query(DeviceMetric)
        .filter(DeviceMetric.device_id == device.id)
        .order_by(DeviceMetric.collected_at.desc())
        .first()
    )
    if not metric or not metric.collected_at:
        return "unknown"
    if (datetime.utcnow() - metric.collected_at).total_seconds() > 300:
        return "offline"

    critical = db.query(Alert).filter(
        Alert.device_id == device.id,
        Alert.is_acknowledged == False,  # noqa: E712
        Alert.alert_level == "critical",
        Alert.alert_type != "offline",
    ).count()
    return "warning" if critical else "online"


def latest_metric(db: Session, device_id: int) -> Optional[DeviceMetric]:
    return (
        db.query(DeviceMetric)
        .filter(DeviceMetric.device_id == device_id)
        .order_by(DeviceMetric.collected_at.desc())
        .first()
    )


def cabinet_to_dict(db: Session, cabinet: Cabinet, with_devices: bool = True) -> Dict[str, Any]:
    usage = cabinet_usage(db, cabinet)
    data: Dict[str, Any] = {
        "id": cabinet.id,
        "room_id": cabinet.room_id,
        "name": cabinet.name,
        "row_index": cabinet.row_index,
        "col_index": cabinet.col_index,
        "pos_x": cabinet.pos_x,
        "pos_z": cabinet.pos_z,
        "rotation": cabinet.rotation,
        "u_capacity": cabinet.u_capacity,
        "power_capacity_w": cabinet.power_capacity_w,
        "width_m": cabinet.width_m,
        "depth_m": cabinet.depth_m,
        "height_m": cabinet.height_m,
        "door_state": cabinet.door_state,
        "lock_type": cabinet.lock_type or "none",
        "is_locked": cabinet.is_locked if cabinet.is_locked is not None else True,
        "last_unlock_at": (
            cabinet.last_unlock_at.isoformat() if cabinet.last_unlock_at else None
        ),
        "last_unlock_by": cabinet.last_unlock_by,
        "model": cabinet.model,
        "description": cabinet.description,
        "usage": {
            "device_count": usage["device_count"],
            "used_power_w": usage["used_power_w"],
            "power_capacity_w": usage["power_capacity_w"],
            "power_percent": usage["power_percent"],
            "free_power_w": usage["free_power_w"],
            "used_u": usage["used_u"],
            "u_capacity": usage["u_capacity"],
            "u_percent": usage["u_percent"],
            "free_u": usage["free_u"],
        },
    }
    if with_devices:
        devices = []
        for device in cabinet_devices(db, cabinet.id):
            metric = latest_metric(db, device.id)
            devices.append({
                "id": device.id,
                "name": device.name,
                "ip_address": device.ip_address,
                "device_type": device.device_type,
                "u_position": device.u_position,
                "u_height": device.u_height or 1,
                "power_watts": device.power_watts or 0,
                "is_enabled": device.is_enabled,
                "status": device_status(db, device),
                "cpu_usage": metric.cpu_usage if metric else None,
                "memory_usage": metric.memory_usage if metric else None,
                "temperature": metric.temperature if metric else None,
                "power_status": metric.power_status if metric else None,
            })
        data["devices"] = devices
    return data


def room_to_dict(db: Session, room: Room, with_cabinets: bool = False) -> Dict[str, Any]:
    cabinets = db.query(Cabinet).filter(Cabinet.room_id == room.id).all()
    usage = []
    for cab in cabinets:
        usage.append(cabinet_usage(db, cab))

    total_power = round(sum(u["used_power_w"] for u in usage), 2)
    total_capacity = round(sum(float(c.power_capacity_w or 0) for c in cabinets), 2)
    total_devices = sum(u["device_count"] for u in usage)
    total_u_used = sum(u["used_u"] for u in usage)
    total_u_capacity = sum(int(c.u_capacity or 0) for c in cabinets)

    data: Dict[str, Any] = {
        "id": room.id,
        "name": room.name,
        "building": room.building,
        "floor": room.floor,
        "location": room.location,
        "description": room.description,
        "length_m": room.length_m,
        "width_m": room.width_m,
        "height_m": room.height_m,
        "floor_color": room.floor_color,
        "power_capacity_w": room.power_capacity_w,
        "created_at": room.created_at.isoformat() if room.created_at else None,
        "updated_at": room.updated_at.isoformat() if room.updated_at else None,
        "summary": {
            "cabinet_count": len(cabinets),
            "device_count": total_devices,
            "used_power_w": total_power,
            "cabinet_power_capacity_w": total_capacity,
            "power_percent": round(total_power / room.power_capacity_w * 100, 2)
                             if room.power_capacity_w else None,
            "used_u": total_u_used,
            "u_capacity": total_u_capacity,
            "u_percent": round(total_u_used / total_u_capacity * 100, 2)
                         if total_u_capacity else 0,
        },
    }
    if with_cabinets:
        data["cabinets"] = [cabinet_to_dict(db, c) for c in cabinets]
    return data


def _auto_position(cabinet: Cabinet) -> tuple:
    """未指定坐标时按行列自动排布"""
    col = int(cabinet.col_index or 0)
    row = int(cabinet.row_index or 0)
    x = ROOM_MARGIN + col * (float(cabinet.width_m or 0.6) + CABINET_GAP_X)
    z = ROOM_MARGIN + row * (float(cabinet.depth_m or 1.2) + ROW_GAP_Z)
    return round(x, 2), round(z, 2)


def _validate_cabinet_update(db: Session, cabinet: Cabinet, data: Dict[str, Any]) -> None:
    """调整机柜容量时，确保已上架设备仍然合法"""
    new_u = int(data.get("u_capacity", cabinet.u_capacity) or 42)
    new_power = float(data.get("power_capacity_w", cabinet.power_capacity_w) or 0)
    devices = cabinet_devices(db, cabinet.id)

    for device in devices:
        _, end = u_range(device)
        if end > new_u:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"机柜「{cabinet.name}」中有设备「{device.name}」占用到 U{end}，"
                    f"不能把 U 容量调整为 {new_u}U"
                ),
            )

    used = sum(float(d.power_watts or 0) for d in devices)
    if new_power and used > new_power + 1e-6:
        raise HTTPException(
            status_code=400,
            detail=(
                f"机柜「{cabinet.name}」已上架设备合计 {used:.0f}W，"
                f"不能把额定功率调整为 {new_power:.0f}W"
            ),
        )


# ==================== 机房 ====================
@router.get("/")
def list_rooms(db: Session = Depends(get_db)):
    """机房列表（含汇总）"""
    rooms = db.query(Room).order_by(Room.id).all()
    return [room_to_dict(db, r) for r in rooms]


@router.post("/")
def create_room(payload: RoomCreate, db: Session = Depends(get_db)):
    room = Room(**payload.model_dump())
    room.created_at = datetime.utcnow()
    room.updated_at = datetime.utcnow()
    db.add(room)
    db.commit()
    db.refresh(room)
    return room_to_dict(db, room)


@router.get("/{room_id}")
def get_room(room_id: int, db: Session = Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="机房不存在")
    return room_to_dict(db, room, with_cabinets=True)


@router.put("/{room_id}")
def update_room(room_id: int, payload: RoomUpdate, db: Session = Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="机房不存在")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(room, key, value)
    room.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(room)
    return room_to_dict(db, room, with_cabinets=True)


@router.delete("/{room_id}")
def delete_room(room_id: int, db: Session = Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="机房不存在")

    # 解除设备与机柜的绑定，再删除机柜/机房
    cabinet_ids = [c.id for c in db.query(Cabinet).filter(Cabinet.room_id == room_id).all()]
    if cabinet_ids:
        db.query(Device).filter(Device.cabinet_id.in_(cabinet_ids)).update(
            {"cabinet_id": None, "u_position": None}, synchronize_session=False
        )
        # 机柜对机房有外键，需先删除机柜（设备已解除绑定）
        db.query(Cabinet).filter(Cabinet.room_id == room_id).delete(
            synchronize_session=False
        )
    db.delete(room)
    db.commit()
    return {"message": "机房已删除（设备已解除机柜绑定）"}


@router.get("/{room_id}/layout")
def get_room_layout(room_id: int, db: Session = Depends(get_db)):
    """机房 3D 布局数据：房间尺寸 + 机柜位置/尺寸/门状态 + 设备状态与功率"""
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="机房不存在")

    cabinets = (
        db.query(Cabinet)
        .filter(Cabinet.room_id == room_id)
        .order_by(Cabinet.row_index, Cabinet.col_index, Cabinet.id)
        .all()
    )

    payload = []
    for cab in cabinets:
        x, z = (
            (float(cab.pos_x), float(cab.pos_z))
            if cab.pos_x is not None and cab.pos_z is not None
            else _auto_position(cab)
        )
        item = cabinet_to_dict(db, cab)
        item.update({
            "x": x,
            "z": z,
            "height": cab.height_m,
            "rotation": float(cab.rotation or 0),
        })
        payload.append(item)

    return {
        "room": {
            "id": room.id,
            "name": room.name,
            "building": room.building,
            "floor": room.floor,
            "length_m": room.length_m,
            "width_m": room.width_m,
            "height_m": room.height_m,
            "floor_color": room.floor_color,
            "power_capacity_w": room.power_capacity_w,
            "summary": room_to_dict(db, room)["summary"],
        },
        "cabinets": payload,
        "timestamp": datetime.utcnow().isoformat(),
    }


# ==================== 机柜 ====================
@router.get("/{room_id}/cabinets")
def list_cabinets(room_id: int, db: Session = Depends(get_db)):
    room = db.query(Room).filter(Room.id == room_id).first()
    if not room:
        raise HTTPException(status_code=404, detail="机房不存在")
    cabinets = (
        db.query(Cabinet)
        .filter(Cabinet.room_id == room_id)
        .order_by(Cabinet.row_index, Cabinet.col_index, Cabinet.id)
        .all()
    )
    return [cabinet_to_dict(db, c) for c in cabinets]


@router.post("/cabinets")
def create_cabinet(payload: CabinetCreate, db: Session = Depends(get_db)):
    room = db.query(Room).filter(Room.id == payload.room_id).first()
    if not room:
        raise HTTPException(status_code=400, detail="机房不存在")

    data = payload.model_dump()
    if data.get("door_state") not in ("open", "closed"):
        data["door_state"] = "closed"
    if not data.get("lock_config"):
        data["lock_config"] = {}
    if data.get("lock_type") not in ("none", "demo", "http", "relay_tcp"):
        data["lock_type"] = "none"
    cabinet = Cabinet(**data)
    cabinet.created_at = datetime.utcnow()
    cabinet.updated_at = datetime.utcnow()
    db.add(cabinet)
    db.commit()
    db.refresh(cabinet)
    return cabinet_to_dict(db, cabinet)


@router.put("/cabinets/{cabinet_id}")
def update_cabinet(cabinet_id: int, payload: CabinetUpdate, db: Session = Depends(get_db)):
    cabinet = db.query(Cabinet).filter(Cabinet.id == cabinet_id).first()
    if not cabinet:
        raise HTTPException(status_code=404, detail="机柜不存在")

    data = payload.model_dump(exclude_unset=True)
    if "room_id" in data:
        room = db.query(Room).filter(Room.id == data["room_id"]).first()
        if not room:
            raise HTTPException(status_code=400, detail="目标机房不存在")
        if int(data["room_id"]) != cabinet.room_id:
            raise HTTPException(
                status_code=400,
                detail="暂不支持跨机房迁移机柜，请先移除机柜内设备",
            )
    if "door_state" in data and data["door_state"] not in ("open", "closed"):
        raise HTTPException(status_code=400, detail="door_state 仅支持 open / closed")

    _validate_cabinet_update(db, cabinet, data)

    for key, value in data.items():
        setattr(cabinet, key, value)
    cabinet.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(cabinet)
    return cabinet_to_dict(db, cabinet)


@router.delete("/cabinets/{cabinet_id}")
def delete_cabinet(cabinet_id: int, db: Session = Depends(get_db)):
    cabinet = db.query(Cabinet).filter(Cabinet.id == cabinet_id).first()
    if not cabinet:
        raise HTTPException(status_code=404, detail="机柜不存在")
    devices = cabinet_devices(db, cabinet.id)
    if devices:
        raise HTTPException(
            status_code=400,
            detail=f"机柜内还有 {len(devices)} 台设备，请先移除后再删除机柜",
        )
    db.delete(cabinet)
    db.commit()
    return {"message": "机柜已删除"}


def _operator(request: Optional[Request]) -> str:
    username = getattr(getattr(request, "state", None), "username", None)
    return username or "system"


def _log_access(
    db: Session, cabinet: Cabinet, action: str, operator: str,
    success: bool, message: str = "",
) -> CabinetAccessLog:
    item = CabinetAccessLog(
        cabinet_id=cabinet.id,
        action=action,
        operator=operator,
        success=success,
        message=(message or "")[:1000],
        created_at=datetime.utcnow(),
    )
    db.add(item)
    return item


@router.put("/cabinets/{cabinet_id}/door")
def set_door_state(
    cabinet_id: int,
    request: Request,
    state: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """设置机柜门状态：state=open / closed；不传则切换

    开门前若电子锁处于锁定状态，会先调用锁控驱动开锁；失败则拒绝开门。
    关门后默认自动上锁（可用 lock_config.auto_lock=false 关闭）。
    """
    cabinet = db.query(Cabinet).filter(Cabinet.id == cabinet_id).first()
    if not cabinet:
        raise HTTPException(status_code=404, detail="机柜不存在")

    if state is None:
        new_state = "open" if (cabinet.door_state or "closed") == "closed" else "closed"
    else:
        new_state = state.lower()
        if new_state not in ("open", "closed"):
            raise HTTPException(status_code=400, detail="state 仅支持 open / closed")

    operator = _operator(request)
    lock_type = (cabinet.lock_type or "none").lower()
    is_locked = cabinet.is_locked if cabinet.is_locked is not None else True
    config = cabinet.lock_config if isinstance(cabinet.lock_config, dict) else {}

    if new_state == "open":
        if is_locked and lock_type != "none":
            try:
                _ok, msg = cabinet_lock.operate(cabinet, "unlock")
            except cabinet_lock.LockError as exc:
                _log_access(db, cabinet, "open_door", operator, False, f"开锁失败: {exc}")
                db.commit()
                raise HTTPException(
                    status_code=400, detail=f"电子锁开启失败，无法开门：{exc}"
                ) from exc
            cabinet.is_locked = False
            cabinet.last_unlock_at = datetime.utcnow()
            cabinet.last_unlock_by = operator
            _log_access(db, cabinet, "unlock", operator, True, f"开门前自动开锁：{msg}")
        _log_access(db, cabinet, "open_door", operator, True, "机柜门已打开")
    else:
        _log_access(db, cabinet, "close_door", operator, True, "机柜门已关闭")
        if lock_type != "none" and config.get("auto_lock", True):
            try:
                _ok, msg = cabinet_lock.operate(cabinet, "lock")
                cabinet.is_locked = True
                _log_access(db, cabinet, "lock", operator, True, f"关门自动上锁：{msg}")
            except cabinet_lock.LockError as exc:
                _log_access(db, cabinet, "lock", operator, False, f"自动上锁失败: {exc}")

    cabinet.door_state = new_state
    cabinet.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(cabinet)
    return {
        "id": cabinet.id,
        "name": cabinet.name,
        "door_state": cabinet.door_state,
        "is_locked": cabinet.is_locked,
        "devices": cabinet_to_dict(db, cabinet).get("devices", []),
    }


# ==================== 机柜电子锁 ====================
@router.put("/cabinets/{cabinet_id}/lock")
def operate_cabinet_lock(
    cabinet_id: int,
    request: Request,
    action: str = Query(..., pattern="^(unlock|lock)$"),
    db: Session = Depends(get_db),
):
    """远程开锁 / 上锁（记录审计日志）"""
    cabinet = db.query(Cabinet).filter(Cabinet.id == cabinet_id).first()
    if not cabinet:
        raise HTTPException(status_code=404, detail="机柜不存在")

    operator = _operator(request)
    try:
        _ok, message = cabinet_lock.operate(cabinet, action)
    except cabinet_lock.LockError as exc:
        _log_access(db, cabinet, action, operator, False, str(exc))
        db.commit()
        raise HTTPException(status_code=400, detail=f"电子锁操作失败：{exc}") from exc

    cabinet.is_locked = action == "lock"
    if action == "unlock":
        cabinet.last_unlock_at = datetime.utcnow()
        cabinet.last_unlock_by = operator
    cabinet.updated_at = datetime.utcnow()
    _log_access(db, cabinet, action, operator, True, message)
    db.commit()
    db.refresh(cabinet)
    return {
        "id": cabinet.id,
        "name": cabinet.name,
        "is_locked": cabinet.is_locked,
        "message": message,
        **_cabinet_lock_status(cabinet),
    }


def _cabinet_lock_status(cabinet: Cabinet) -> dict:
    return {
        "lock_type": cabinet.lock_type or "none",
        "is_locked": cabinet.is_locked if cabinet.is_locked is not None else True,
        "door_state": cabinet.door_state,
        "last_unlock_at": (
            cabinet.last_unlock_at.isoformat() if cabinet.last_unlock_at else None
        ),
        "last_unlock_by": cabinet.last_unlock_by,
        "config": cabinet_lock.lock_config_summary(cabinet)["config"],
    }


@router.get("/cabinets/{cabinet_id}/lock-status")
def get_cabinet_lock_status(cabinet_id: int, db: Session = Depends(get_db)):
    """机柜电子锁状态（配置中的 token 等敏感字段已脱敏）"""
    cabinet = db.query(Cabinet).filter(Cabinet.id == cabinet_id).first()
    if not cabinet:
        raise HTTPException(status_code=404, detail="机柜不存在")
    return {"id": cabinet.id, "name": cabinet.name, **_cabinet_lock_status(cabinet)}


@router.put("/cabinets/{cabinet_id}/lock-config")
def update_cabinet_lock_config(
    cabinet_id: int,
    payload: CabinetLockConfig,
    db: Session = Depends(get_db),
):
    """配置机柜电子锁类型与参数（lock_config 例：http: {url,token}；relay_tcp: {host,port,channel}）"""
    cabinet = db.query(Cabinet).filter(Cabinet.id == cabinet_id).first()
    if not cabinet:
        raise HTTPException(status_code=404, detail="机柜不存在")

    data = payload.model_dump(exclude_unset=True)
    if "lock_type" in data and data["lock_type"]:
        lock_type = data["lock_type"].lower()
        if lock_type not in ("none", "demo", "http", "relay_tcp"):
            raise HTTPException(
                status_code=400, detail="lock_type 仅支持 none / demo / http / relay_tcp"
            )
        cabinet.lock_type = lock_type
    if "lock_config" in data and data["lock_config"] is not None:
        cabinet.lock_config = data["lock_config"]
    if "is_locked" in data and data["is_locked"] is not None:
        cabinet.is_locked = bool(data["is_locked"])

    cabinet.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(cabinet)
    return {"message": "电子锁配置已保存", **_cabinet_lock_status(cabinet)}


@router.get("/cabinets/{cabinet_id}/access-logs")
def get_cabinet_access_logs(
    cabinet_id: int,
    limit: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    """机柜开锁/开关门审计日志"""
    if not db.query(Cabinet).filter(Cabinet.id == cabinet_id).first():
        raise HTTPException(status_code=404, detail="机柜不存在")
    items = (
        db.query(CabinetAccessLog)
        .filter(CabinetAccessLog.cabinet_id == cabinet_id)
        .order_by(CabinetAccessLog.created_at.desc(), CabinetAccessLog.id.desc())
        .limit(limit)
        .all()
    )
    return {
        "total": len(items),
        "items": [
            {
                "id": item.id,
                "action": item.action,
                "operator": item.operator,
                "success": item.success,
                "message": item.message,
                "created_at": item.created_at.isoformat() if item.created_at else None,
            }
            for item in items
        ],
    }


# ==================== 机房温湿度传感器 ====================
SENSOR_SOURCES = ("demo", "snmp", "xiaomi", "rs485", "modbus_tcp", "mqtt")


def _validate_sensor_source(data: dict) -> None:
    source = str(data.get("source") or "demo")
    if source not in SENSOR_SOURCES:
        raise HTTPException(status_code=400, detail="source 仅支持 demo / snmp / xiaomi / rs485 / modbus_tcp / mqtt")
    if source == "snmp" and not str(data.get("ip") or "").strip():
        raise HTTPException(status_code=400, detail="SNMP 传感器必须填写 IP 地址")
    if source == "xiaomi" and not str(data.get("xiaomi_url") or "").strip():
        raise HTTPException(status_code=400, detail="小米传感器必须填写网关 HTTP JSON 地址")
    if source == "rs485":
        if not str(data.get("serial_port") or "").strip():
            raise HTTPException(status_code=400, detail="RS485 传感器必须填写串口")
        if int(data.get("function_code") or 3) not in (3, 4):
            raise HTTPException(status_code=400, detail="RS485 功能码仅支持 03 / 04")
        if str(data.get("parity") or "N").upper() not in ("N", "E", "O"):
            raise HTTPException(status_code=400, detail="RS485 校验位仅支持 N / E / O")
        if str(data.get("word_order") or "big") not in ("big", "little"):
            raise HTTPException(status_code=400, detail="RS485 字序仅支持 big / little")
        if int(data.get("register_count") or 1) not in (1, 2):
            raise HTTPException(status_code=400, detail="RS485 寄存器数量仅支持 1 / 2")
    if source == "modbus_tcp":
        if not str(data.get("modbus_host") or "").strip():
            raise HTTPException(status_code=400, detail="Modbus TCP 传感器必须填写主机地址")
        if int(data.get("function_code") or 3) not in (3, 4):
            raise HTTPException(status_code=400, detail="Modbus TCP 功能码仅支持 03 / 04")
        if int(data.get("register_count") or 1) not in (1, 2):
            raise HTTPException(status_code=400, detail="Modbus TCP 寄存器数量仅支持 1 / 2")
    if source == "mqtt":
        if not str(data.get("mqtt_host") or "").strip():
            raise HTTPException(status_code=400, detail="MQTT 传感器必须填写 Broker 主机")
        if not str(data.get("mqtt_topic") or "").strip():
            raise HTTPException(status_code=400, detail="MQTT 传感器必须填写订阅主题")


def _sensor_status(sensor: RoomSensor) -> dict:
    temp = sensor.last_temperature
    hum = sensor.last_humidity
    temp_status = "unknown"
    if temp is not None:
        if temp > (sensor.temp_high or 30):
            temp_status = "high"
        elif temp < (sensor.temp_low or 15):
            temp_status = "low"
        else:
            temp_status = "normal"
    humidity_status = "unknown"
    if hum is not None:
        if hum > (sensor.humidity_high or 70):
            humidity_status = "high"
        elif hum < (sensor.humidity_low or 30):
            humidity_status = "low"
        else:
            humidity_status = "normal"
    overall = "normal"
    if "high" in (temp_status, humidity_status) or "low" in (temp_status, humidity_status):
        overall = "alarm"
    elif temp_status == "unknown" and humidity_status == "unknown":
        overall = "unknown"
    return {
        "temperature_status": temp_status,
        "humidity_status": humidity_status,
        "status": overall,
    }


def _sensor_to_dict(sensor: RoomSensor) -> dict:
    return {
        "id": sensor.id,
        "room_id": sensor.room_id,
        "name": sensor.name,
        "sensor_type": sensor.sensor_type,
        "source": sensor.source,
        "ip": sensor.ip,
        "snmp_version": sensor.snmp_version,
        "community": sensor.community,
        "port": sensor.port,
        "oid_temperature": sensor.oid_temperature,
        "oid_humidity": sensor.oid_humidity,
        "xiaomi_url": sensor.xiaomi_url,
        "xiaomi_token": sensor.xiaomi_token,
        "xiaomi_device_id": sensor.xiaomi_device_id,
        "xiaomi_temperature_path": sensor.xiaomi_temperature_path,
        "xiaomi_humidity_path": sensor.xiaomi_humidity_path,
        "serial_port": sensor.serial_port,
        "baudrate": sensor.baudrate,
        "bytesize": sensor.bytesize,
        "parity": sensor.parity,
        "stopbits": sensor.stopbits,
        "slave_id": sensor.slave_id,
        "function_code": sensor.function_code,
        "register_temperature": sensor.register_temperature,
        "register_humidity": sensor.register_humidity,
        "register_count": sensor.register_count,
        "temperature_scale": sensor.temperature_scale,
        "humidity_scale": sensor.humidity_scale,
        "signed_temperature": sensor.signed_temperature,
        "word_order": sensor.word_order,
        "serial_timeout": sensor.serial_timeout,
        "modbus_host": sensor.modbus_host,
        "modbus_port": sensor.modbus_port,
        "modbus_unit_id": sensor.modbus_unit_id,
        "modbus_timeout": sensor.modbus_timeout,
        "mqtt_host": sensor.mqtt_host,
        "mqtt_port": sensor.mqtt_port,
        "mqtt_username": sensor.mqtt_username,
        "mqtt_password": sensor.mqtt_password,
        "mqtt_topic": sensor.mqtt_topic,
        "mqtt_tls": sensor.mqtt_tls,
        "mqtt_client_id": sensor.mqtt_client_id,
        "mqtt_timeout": sensor.mqtt_timeout,
        "mqtt_temperature_path": sensor.mqtt_temperature_path,
        "mqtt_humidity_path": sensor.mqtt_humidity_path,
        "temp_high": sensor.temp_high,
        "temp_low": sensor.temp_low,
        "humidity_high": sensor.humidity_high,
        "humidity_low": sensor.humidity_low,
        "is_enabled": sensor.is_enabled,
        "last_temperature": sensor.last_temperature,
        "last_humidity": sensor.last_humidity,
        "last_updated": sensor.last_updated.isoformat() if sensor.last_updated else None,
        **_sensor_status(sensor),
    }


@router.get("/{room_id}/sensors")
def list_room_sensors(room_id: int, db: Session = Depends(get_db)):
    """机房温湿度传感器列表（含最新读数与阈值状态）"""
    if not db.query(Room).filter(Room.id == room_id).first():
        raise HTTPException(status_code=404, detail="机房不存在")
    sensors = (
        db.query(RoomSensor)
        .filter(RoomSensor.room_id == room_id)
        .order_by(RoomSensor.id)
        .all()
    )
    return {"total": len(sensors), "items": [_sensor_to_dict(s) for s in sensors]}


@router.post("/{room_id}/sensors")
def create_room_sensor(room_id: int, payload: SensorCreate, db: Session = Depends(get_db)):
    """新增温湿度传感器（演示 / SNMP / 小米网关 / RS485）"""
    if not db.query(Room).filter(Room.id == room_id).first():
        raise HTTPException(status_code=404, detail="机房不存在")
    _validate_sensor_source(payload.model_dump())
    if payload.sensor_type not in ("temperature", "humidity", "combined"):
        raise HTTPException(
            status_code=400, detail="sensor_type 仅支持 temperature / humidity / combined"
        )

    sensor = RoomSensor(
        room_id=room_id,
        name=payload.name.strip()[:100],
        sensor_type=payload.sensor_type,
        source=payload.source,
        ip=payload.ip,
        snmp_version=payload.snmp_version,
        community=payload.community,
        port=payload.port,
        oid_temperature=payload.oid_temperature,
        oid_humidity=payload.oid_humidity,
        xiaomi_url=payload.xiaomi_url,
        xiaomi_token=payload.xiaomi_token,
        xiaomi_device_id=payload.xiaomi_device_id,
        xiaomi_temperature_path=payload.xiaomi_temperature_path,
        xiaomi_humidity_path=payload.xiaomi_humidity_path,
        serial_port=payload.serial_port,
        baudrate=payload.baudrate,
        bytesize=payload.bytesize,
        parity=payload.parity,
        stopbits=payload.stopbits,
        slave_id=payload.slave_id,
        function_code=payload.function_code,
        register_temperature=payload.register_temperature,
        register_humidity=payload.register_humidity,
        register_count=payload.register_count,
        temperature_scale=payload.temperature_scale,
        humidity_scale=payload.humidity_scale,
        signed_temperature=payload.signed_temperature,
        word_order=payload.word_order,
        serial_timeout=payload.serial_timeout,
        modbus_host=payload.modbus_host,
        modbus_port=payload.modbus_port,
        modbus_unit_id=payload.modbus_unit_id,
        modbus_timeout=payload.modbus_timeout,
        mqtt_host=payload.mqtt_host,
        mqtt_port=payload.mqtt_port,
        mqtt_username=payload.mqtt_username,
        mqtt_password=payload.mqtt_password,
        mqtt_topic=payload.mqtt_topic,
        mqtt_tls=payload.mqtt_tls,
        mqtt_client_id=payload.mqtt_client_id,
        mqtt_timeout=payload.mqtt_timeout,
        mqtt_temperature_path=payload.mqtt_temperature_path,
        mqtt_humidity_path=payload.mqtt_humidity_path,
        temp_high=payload.temp_high,
        temp_low=payload.temp_low,
        humidity_high=payload.humidity_high,
        humidity_low=payload.humidity_low,
        is_enabled=payload.is_enabled,
        created_at=datetime.utcnow(),
    )
    db.add(sensor)
    db.commit()
    db.refresh(sensor)
    return _sensor_to_dict(sensor)


@router.put("/sensors/{sensor_id}")
def update_room_sensor(
    sensor_id: int, payload: SensorUpdate, db: Session = Depends(get_db)
):
    sensor = db.query(RoomSensor).filter(RoomSensor.id == sensor_id).first()
    if not sensor:
        raise HTTPException(status_code=404, detail="传感器不存在")

    data = payload.model_dump(exclude_unset=True)
    validation_data = {
        "source": sensor.source,
        "ip": sensor.ip,
        "xiaomi_url": sensor.xiaomi_url,
        "serial_port": sensor.serial_port,
        "function_code": sensor.function_code,
        "parity": sensor.parity,
        "word_order": sensor.word_order,
        "register_count": sensor.register_count,
        "modbus_host": sensor.modbus_host,
        "mqtt_host": sensor.mqtt_host,
        "mqtt_topic": sensor.mqtt_topic,
    }
    validation_data.update(data)
    _validate_sensor_source(validation_data)
    if "sensor_type" in data and data["sensor_type"] not in (
        "temperature", "humidity", "combined",
    ):
        raise HTTPException(
            status_code=400, detail="sensor_type 仅支持 temperature / humidity / combined"
        )
    for key, value in data.items():
        setattr(sensor, key, value)
    db.commit()
    db.refresh(sensor)
    return _sensor_to_dict(sensor)


@router.delete("/sensors/{sensor_id}")
def delete_room_sensor(sensor_id: int, db: Session = Depends(get_db)):
    sensor = db.query(RoomSensor).filter(RoomSensor.id == sensor_id).first()
    if not sensor:
        raise HTTPException(status_code=404, detail="传感器不存在")
    db.delete(sensor)
    db.commit()
    return {"message": "传感器已删除"}


@router.get("/sensors/{sensor_id}/readings")
def get_sensor_readings(
    sensor_id: int,
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
):
    """传感器历史读数（默认最近 24 小时）"""
    sensor = db.query(RoomSensor).filter(RoomSensor.id == sensor_id).first()
    if not sensor:
        raise HTTPException(status_code=404, detail="传感器不存在")
    since = datetime.utcnow() - timedelta(hours=hours)
    rows = (
        db.query(RoomSensorReading)
        .filter(
            RoomSensorReading.sensor_id == sensor_id,
            RoomSensorReading.recorded_at >= since,
        )
        .order_by(RoomSensorReading.recorded_at)
        .all()
    )
    temps = [r.temperature for r in rows if r.temperature is not None]
    hums = [r.humidity for r in rows if r.humidity is not None]
    return {
        "sensor_id": sensor_id,
        "hours": hours,
        "items": [
            {
                "temperature": r.temperature,
                "humidity": r.humidity,
                "recorded_at": r.recorded_at.isoformat() if r.recorded_at else None,
            }
            for r in rows
        ],
        "stats": {
            "temperature_avg": round(sum(temps) / len(temps), 1) if temps else None,
            "temperature_max": round(max(temps), 1) if temps else None,
            "temperature_min": round(min(temps), 1) if temps else None,
            "humidity_avg": round(sum(hums) / len(hums), 1) if hums else None,
            "humidity_max": round(max(hums), 1) if hums else None,
            "humidity_min": round(min(hums), 1) if hums else None,
            "count": len(rows),
        },
    }


@router.get("/{room_id}/sensor-summary")
def get_room_sensor_summary(room_id: int, db: Session = Depends(get_db)):
    """机房温湿度概览（3D 视图侧栏使用）"""
    if not db.query(Room).filter(Room.id == room_id).first():
        raise HTTPException(status_code=404, detail="机房不存在")
    sensors = (
        db.query(RoomSensor)
        .filter(RoomSensor.room_id == room_id, RoomSensor.is_enabled == True)  # noqa: E712
        .all()
    )
    temps = [s.last_temperature for s in sensors if s.last_temperature is not None]
    hums = [s.last_humidity for s in sensors if s.last_humidity is not None]
    alarms = sum(1 for s in sensors if _sensor_status(s)["status"] == "alarm")
    return {
        "room_id": room_id,
        "sensor_count": len(sensors),
        "alarm_count": alarms,
        "temperature_avg": round(sum(temps) / len(temps), 1) if temps else None,
        "humidity_avg": round(sum(hums) / len(hums), 1) if hums else None,
        "sensors": [_sensor_to_dict(s) for s in sensors],
    }


@router.get("/cabinets/{cabinet_id}/usage")
def get_cabinet_usage(cabinet_id: int, db: Session = Depends(get_db)):
    """机柜 U 位与功率使用情况"""
    cabinet = db.query(Cabinet).filter(Cabinet.id == cabinet_id).first()
    if not cabinet:
        raise HTTPException(status_code=404, detail="机柜不存在")
    return cabinet_usage(db, cabinet)
