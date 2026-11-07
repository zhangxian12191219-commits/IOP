"""机柜上架与功率校验

规则:
1. 设备的 U 位必须落在机柜 U 容量范围内
2. 同机柜内不同设备的 U 区间不能重叠
3. 同机柜内所有设备额定功率之和不得超过机柜额定功率
"""
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException
from sqlalchemy.orm import Session

from ..models.models import Device
from ..models.room import Cabinet


def cabinet_devices(
    db: Session, cabinet_id: int, exclude_device_id: Optional[int] = None
) -> List[Device]:
    query = db.query(Device).filter(Device.cabinet_id == cabinet_id)
    if exclude_device_id is not None:
        query = query.filter(Device.id != exclude_device_id)
    return query.order_by(Device.u_position.asc().nulls_first()).all()


def u_range(device: Device) -> Tuple[int, int]:
    """设备占用的 U 区间（闭区间，1 为机柜最底部）"""
    start = int(device.u_position or 1)
    height = max(1, int(device.u_height or 1))
    return start, start + height - 1


def cabinet_usage(
    db: Session, cabinet: Cabinet, exclude_device_id: Optional[int] = None
) -> Dict[str, Any]:
    """机柜使用情况汇总"""
    devices = cabinet_devices(db, cabinet.id, exclude_device_id)

    used_power = round(sum(float(d.power_watts or 0) for d in devices), 2)
    used_u = sum(max(1, int(d.u_height or 1)) for d in devices)
    capacity = float(cabinet.power_capacity_w or 0)
    u_capacity = int(cabinet.u_capacity or 42)

    # 已占用 U 位分布
    occupied = set()
    for d in devices:
        start, end = u_range(d)
        occupied.update(range(start, end + 1))

    free_slots = [u for u in range(1, u_capacity + 1) if u not in occupied]

    return {
        "cabinet_id": cabinet.id,
        "device_count": len(devices),
        "used_power_w": used_power,
        "power_capacity_w": capacity,
        "power_percent": round(used_power / capacity * 100, 2) if capacity else 0,
        "free_power_w": round(max(0.0, capacity - used_power), 2),
        "used_u": used_u,
        "u_capacity": u_capacity,
        "u_percent": round(used_u / u_capacity * 100, 2) if u_capacity else 0,
        "free_u": max(0, u_capacity - used_u),
        "free_slots": free_slots,
        "devices": [
            {
                "id": d.id,
                "name": d.name,
                "device_type": d.device_type,
                "u_position": d.u_position,
                "u_height": d.u_height or 1,
                "power_watts": d.power_watts or 0,
            }
            for d in devices
        ],
    }


def find_free_u(cabinet: Cabinet, devices: List[Device], u_height: int) -> Optional[int]:
    """在机柜中寻找一段连续空闲 U 位（从低到高）"""
    u_capacity = int(cabinet.u_capacity or 42)
    height = max(1, int(u_height or 1))
    occupied = set()
    for d in devices:
        start, end = u_range(d)
        occupied.update(range(start, end + 1))

    for start in range(1, u_capacity - height + 2):
        if all((start + offset) not in occupied for offset in range(height)):
            return start
    return None


def validate_placement(
    db: Session,
    cabinet: Cabinet,
    u_position: Optional[int],
    u_height: Optional[int],
    power_watts: Optional[float],
    exclude_device_id: Optional[int] = None,
) -> int:
    """校验设备能否放入机柜，返回最终采用的 U 起始位置

    - 未指定 u_position 时自动寻找最低空闲 U 位
    - 校验失败抛出 HTTPException(400)，消息可直接展示给用户
    """
    height = max(1, int(u_height or 1))
    u_capacity = int(cabinet.u_capacity or 42)
    others = cabinet_devices(db, cabinet.id, exclude_device_id)

    if height > u_capacity:
        raise HTTPException(
            status_code=400,
            detail=f"设备高度 {height}U 超过机柜「{cabinet.name}」总容量 {u_capacity}U",
        )

    # 位置
    if u_position in (None, 0):
        start = find_free_u(cabinet, others, height)
        if start is None:
            raise HTTPException(
                status_code=400,
                detail=f"机柜「{cabinet.name}」没有连续 {height}U 的空闲位置",
            )
    else:
        start = int(u_position)

    end = start + height - 1
    if start < 1 or end > u_capacity:
        raise HTTPException(
            status_code=400,
            detail=(
                f"U 位超出范围：机柜「{cabinet.name}」容量 {u_capacity}U，"
                f"当前为 U{start}-U{end}"
            ),
        )

    # U 位冲突
    for other in others:
        o_start, o_end = u_range(other)
        if not (end < o_start or start > o_end):
            raise HTTPException(
                status_code=400,
                detail=(
                    f"U 位冲突：机柜「{cabinet.name}」中 U{o_start}-U{o_end} 已被"
                    f"「{other.name}」占用，本次需要 U{start}-U{end}"
                ),
            )

    # 功率
    capacity = float(cabinet.power_capacity_w or 0)
    used = sum(float(d.power_watts or 0) for d in others)
    new_total = used + float(power_watts or 0)
    if capacity and new_total > capacity + 1e-6:
        raise HTTPException(
            status_code=400,
            detail=(
                f"机柜「{cabinet.name}」功率超限：已用 {used:.0f}W + 本设备 "
                f"{float(power_watts or 0):.0f}W = {new_total:.0f}W，"
                f"超过额定 {capacity:.0f}W（可用 {max(0.0, capacity - used):.0f}W）"
            ),
        )

    return start
