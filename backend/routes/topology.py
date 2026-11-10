"""拓扑路由 - 自动生成网络拓扑"""
import json
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import and_, func
from sqlalchemy.orm import Session
from typing import Dict, Any, List
from datetime import datetime, timedelta

from ..config import Config
from ..models.database import get_db
from ..models.models import Device, DeviceInterface, DeviceConnection, DeviceMetric, Alert
from ..models.settings import SystemSetting
from ..models.schemas import ConnectionCreate
from ..services.cache import (
    KEY_TOPOLOGY,
    cache,
    invalidate_dashboard,
    invalidate_topology,
)

router = APIRouter(prefix="/api/topology", tags=["拓扑管理"])

# 拓扑专用虚拟云节点：保存在 SystemSetting JSON 中，不写设备/资产表
CLOUD_LAYOUT_KEY = "topology_cloud_layout"
CLOUD_NODE_DEFAULT_LABEL = "互联网出口"

# 节点样式
DEVICE_TYPE_COLORS = {
    "router": "#3498db",
    "switch": "#2ecc71",
    "firewall": "#e74c3c",
    "security": "#9b59b6",
    "server": "#f39c12",
}
DEVICE_TYPE_SIZES = {
    "router": 40,
    "switch": 35,
    "firewall": 45,
    "security": 40,
    "server": 35,
}


@router.get("/")
def get_topology(request: Request, response: Response, db: Session = Depends(get_db)):
    """获取完整的网络拓扑（节点 + 连接 + 实时链路速率）

    结果带 TTL 缓存（默认 5 秒）；非超级管理员按资产群组过滤，且不使用全量缓存。
    """
    from ..services import asset_scope

    group_ids = asset_scope.allowed_group_ids(db, request)
    if group_ids is None:
        cached, hit = cache.get(KEY_TOPOLOGY)
        if hit and isinstance(cached, dict):
            response.headers["X-Cache"] = "HIT"
            return cached
        payload = _build_topology(db)
        cache.set(KEY_TOPOLOGY, payload, cache.ttl_topology)
        response.headers["X-Cache"] = "MISS"
        return payload

    payload = _build_topology(db, request=request)
    response.headers["X-Cache"] = "BYPASS"
    return payload


def _latest_metric_map(db: Session, device_ids) -> Dict[int, DeviceMetric]:
    """一次查询取回所有设备的最新指标（避免每台设备一次查询）"""
    if not device_ids:
        return {}
    latest = (
        db.query(
            DeviceMetric.device_id.label("device_id"),
            func.max(DeviceMetric.collected_at).label("max_at"),
        )
        .filter(DeviceMetric.device_id.in_(device_ids))
        .group_by(DeviceMetric.device_id)
        .subquery()
    )
    rows = (
        db.query(DeviceMetric)
        .join(
            latest,
            and_(
                DeviceMetric.device_id == latest.c.device_id,
                DeviceMetric.collected_at == latest.c.max_at,
            ),
        )
        .all()
    )
    return {row.device_id: row for row in rows}


def _status_map(db: Session, devices, metrics: Dict[int, DeviceMetric]) -> Dict[int, str]:
    """批量计算设备状态，避免逐台查询告警"""
    ids = [d.id for d in devices]
    offline_ids = set()
    critical_ids = set()
    if ids:
        alerts = (
            db.query(Alert.device_id, Alert.alert_type, Alert.alert_level)
            .filter(
                Alert.device_id.in_(ids),
                Alert.is_acknowledged == False,  # noqa: E712
            )
            .all()
        )
        for alert in alerts:
            if alert.alert_type == "offline":
                offline_ids.add(alert.device_id)
            elif alert.alert_level == "critical":
                critical_ids.add(alert.device_id)

    now = datetime.utcnow()
    status: Dict[int, str] = {}
    for device in devices:
        if not device.is_enabled:
            status[device.id] = "disabled"
            continue
        if device.id in offline_ids:
            status[device.id] = "offline"
            continue
        metric = metrics.get(device.id)
        if not metric or not metric.collected_at:
            status[device.id] = "unknown"
            continue
        if (now - metric.collected_at).total_seconds() > 300:
            status[device.id] = "offline"
        elif device.id in critical_ids:
            status[device.id] = "warning"
        else:
            status[device.id] = "online"
    return status


def _alert_stats_map(db: Session, ids: List[int]) -> Dict[int, Dict[str, Any]]:
    """活动告警数量与最高级别，用于拓扑节点角标/闪烁。"""
    stats: Dict[int, Dict[str, Any]] = {}
    if not ids:
        return stats
    rows = (
        db.query(Alert.device_id, Alert.alert_level)
        .filter(
            Alert.device_id.in_(ids),
            Alert.resolved_at.is_(None),
            Alert.is_hidden.isnot(True),
        )
        .all()
    )
    rank = {"info": 1, "warning": 2, "critical": 3, "emergency": 4}
    for device_id, level in rows:
        item = stats.setdefault(device_id, {"count": 0, "level": ""})
        item["count"] += 1
        if rank.get(level or "", 0) >= rank.get(item["level"] or "", 0):
            item["level"] = level or ""
    return stats


def _normalize_anchor(value: Any) -> Any:
    """校验并归一化拖拽锚点，坐标是设备框内的相对位置 0~1。"""
    if not isinstance(value, dict):
        return None
    try:
        x = float(value.get("x"))
        y = float(value.get("y"))
    except (TypeError, ValueError):
        return None
    if not (0 <= x <= 1 and 0 <= y <= 1):
        return None
    return {"x": round(x, 4), "y": round(y, 4)}


def _normalize_color(value: Any) -> str:
    text = str(value or "").strip()
    if text and len(text) == 7 and text.startswith("#"):
        try:
            int(text[1:], 16)
            return text.lower()
        except ValueError:
            return ""
    return ""


def _normalize_edge_offset(value: Any) -> Any:
    """校验连线手动偏移量。"""
    if not isinstance(value, dict):
        return None
    try:
        x = float(value.get("x", 0))
        y = float(value.get("y", 0))
    except (TypeError, ValueError):
        return None
    if not (-20000 <= x <= 20000 and -20000 <= y <= 20000):
        return None
    result = {"x": round(x, 2), "y": round(y, 2)}
    color = _normalize_color(value.get("color"))
    if color:
        result["color"] = color
    raw_points = value.get("points")
    if isinstance(raw_points, list):
        points = []
        for item in raw_points[:4]:
            if not isinstance(item, dict):
                continue
            try:
                px = float(item.get("x", 0))
                py = float(item.get("y", 0))
            except (TypeError, ValueError):
                continue
            if -20000 <= px <= 20000 and -20000 <= py <= 20000:
                points.append({"x": round(px, 2), "y": round(py, 2)})
        if points:
            result["points"] = points
    return result


def _positive_int(value: Any) -> Any:
    if isinstance(value, bool):
        return None
    try:
        number = int(value)
    except (TypeError, ValueError):
        return None
    return number if number > 0 else None


def _cloud_node_id(value: Any) -> Any:
    if isinstance(value, str):
        value = value.strip()
        if value.startswith("cloud_"):
            value = value[6:]
    return _positive_int(value)


def _cloud_endpoint_id(value: str) -> Any:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text.startswith("cloud_"):
        return None
    return _positive_int(text[6:])


def _device_endpoint_id(value: str) -> Any:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text.startswith("device_"):
        return None
    return _positive_int(text[7:])


def _safe_float(value: Any, default: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    if not (-20000 <= number <= 20000):
        return default
    return round(number, 2)


def _safe_size(value: Any, default: float, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return round(max(low, min(high, number)), 2)


def _load_cloud_layout(db: Session) -> Dict[str, Any]:
    """读取拓扑云节点/云链路（SystemSetting JSON，失败时返回空结构）。"""
    empty = {"cloud_nodes": [], "cloud_links": []}
    row = db.query(SystemSetting).filter(SystemSetting.key == CLOUD_LAYOUT_KEY).first()
    if not row or not row.value:
        return empty
    try:
        data = json.loads(row.value)
    except (TypeError, ValueError):
        return empty
    if not isinstance(data, dict):
        return empty
    cloud_nodes = data.get("cloud_nodes")
    cloud_links = data.get("cloud_links")
    return {
        "cloud_nodes": cloud_nodes if isinstance(cloud_nodes, list) else [],
        "cloud_links": cloud_links if isinstance(cloud_links, list) else [],
    }


def _save_cloud_layout(db: Session, cloud_nodes: list, cloud_links: list) -> None:
    """把云节点/云链路写入 SystemSetting；调用方负责 commit。"""
    serialized = json.dumps(
        {"cloud_nodes": cloud_nodes, "cloud_links": cloud_links},
        ensure_ascii=False,
    )
    row = db.query(SystemSetting).filter(SystemSetting.key == CLOUD_LAYOUT_KEY).first()
    if row:
        row.value = serialized
    else:
        db.add(SystemSetting(key=CLOUD_LAYOUT_KEY, value=serialized))


def _clear_cloud_layout(db: Session) -> None:
    db.query(SystemSetting).filter(SystemSetting.key == CLOUD_LAYOUT_KEY).delete(
        synchronize_session=False,
    )


def _normalize_cloud_nodes(items: Any) -> list:
    """校验并规范化云节点；id 缺失/重复时自动分配，保证唯一。"""
    if not isinstance(items, list):
        return []
    parsed_ids = []
    for item in items:
        if not isinstance(item, dict):
            continue
        node_id = _cloud_node_id(item.get("id") or item.get("cloud_id") or item.get("cloud_node_id"))
        if node_id and node_id not in parsed_ids:
            parsed_ids.append(node_id)
    next_id = max(parsed_ids, default=0) + 1
    seen = set()
    result = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        node_id = _cloud_node_id(item.get("id") or item.get("cloud_id") or item.get("cloud_node_id"))
        if node_id and node_id in seen:
            node_id = None
        if not node_id:
            while next_id in seen:
                next_id += 1
            node_id = next_id
            next_id += 1
        seen.add(node_id)
        label = str(item.get("label") or CLOUD_NODE_DEFAULT_LABEL).strip()[:100]
        label = label or CLOUD_NODE_DEFAULT_LABEL
        result.append({
            "id": node_id,
            "label": label,
            "x": _safe_float(item.get("x"), 120 + index * 160),
            "y": _safe_float(item.get("y"), 120),
            "width": _safe_size(item.get("width"), 140, 70, 320),
            "height": _safe_size(item.get("height"), 84, 50, 240),
        })
    result.sort(key=lambda node: node["id"])
    return result


def _normalize_cloud_links(
    items: Any,
    cloud_node_ids: set,
    device_ids: set,
) -> list:
    """校验云链路：一条边必须是一端云节点、一端真实设备。

    云端不写入 DeviceConnection，仅保存在拓扑布局 JSON 中。
    """
    if not isinstance(items, list):
        return []
    parsed_ids = []
    for item in items:
        if not isinstance(item, dict):
            continue
        link_id = _positive_int(item.get("id") or item.get("cloud_link_id"))
        if link_id and link_id not in parsed_ids:
            parsed_ids.append(link_id)
    next_id = max(parsed_ids, default=0) + 1
    seen = set()
    result = []
    for item in items:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "").strip()
        target = str(item.get("target") or "").strip()
        if not source or not target or source == target:
            continue
        source_cloud = _cloud_endpoint_id(source)
        target_cloud = _cloud_endpoint_id(target)
        # 必须恰好一端是 cloud_*，另一端是 device_*
        if (source_cloud is not None) == (target_cloud is not None):
            continue
        if source_cloud is not None:
            if source_cloud not in cloud_node_ids:
                continue
            device_id = _device_endpoint_id(target)
            if device_id is None or device_id not in device_ids:
                continue
        else:
            if target_cloud not in cloud_node_ids:
                continue
            device_id = _device_endpoint_id(source)
            if device_id is None or device_id not in device_ids:
                continue
        link_id = _positive_int(item.get("id") or item.get("cloud_link_id"))
        if link_id and link_id in seen:
            link_id = None
        if not link_id:
            while next_id in seen:
                next_id += 1
            link_id = next_id
            next_id += 1
        seen.add(link_id)
        result.append({
            "id": link_id,
            "source": source,
            "target": target,
            "source_interface": str(item.get("source_interface") or "").strip()[:200],
            "target_interface": str(item.get("target_interface") or "").strip()[:200],
            "color": _normalize_color(item.get("color")),
            "edge_offset": _normalize_edge_offset({
                "x": item.get("offset_x", 0), "y": item.get("offset_y", 0),
                "points": item.get("offset_points") or [],
            }),
            "edge_label_offset": _normalize_edge_offset({
                "x": item.get("label_offset_x", 0), "y": item.get("label_offset_y", 0)
            }),
            "source_anchor": _normalize_anchor(item.get("source_anchor")),
            "dest_anchor": _normalize_anchor(item.get("dest_anchor")),
        })
    result.sort(key=lambda link: link["id"])
    return result


def _build_topology(db: Session, request: Request = None) -> Dict[str, Any]:
    """真正计算拓扑（未命中缓存时执行；可按用户群组过滤）"""
    # 拓扑与资产管理保持一致：包含启用和未启用资产，未启用节点灰显。
    device_query = db.query(Device)
    if request is not None:
        from ..services import asset_scope

        device_query = asset_scope.scope_device_query(db, request, device_query)
    devices = device_query.all()
    connections = db.query(DeviceConnection).all()

    # 批量取最新指标与状态
    device_ids = [d.id for d in devices]
    metrics = _latest_metric_map(db, device_ids)
    statuses = _status_map(db, devices, metrics)
    alert_stats = _alert_stats_map(db, device_ids)

    # 接口缓存：{device_id: {if_name: iface}}，用于把连线映射到实际接口速率
    iface_cache: Dict[int, Dict[str, DeviceInterface]] = {}
    for iface in db.query(DeviceInterface).all():
        iface_cache.setdefault(iface.device_id, {})[(iface.if_name or "")] = iface

    nodes = []
    for device in devices:
        metric = metrics.get(device.id)
        nodes.append({
            "id": f"device_{device.id}",
            "device_id": device.id,
            "label": device.name or device.ip_address,
            "ip_address": device.ip_address,
            "device_type": device.device_type,
            "location": device.location or "",
            "vendor": device.vendor or "",
            "model": device.model or "",
            "icon": device.icon,
            "status": statuses.get(device.id, "unknown"),
            "alert_count": int(alert_stats.get(device.id, {}).get("count", 0)),
            "alert_level": alert_stats.get(device.id, {}).get("level", ""),
            "is_enabled": bool(device.is_enabled),
            "cpu_usage": metric.cpu_usage if metric else None,
            "memory_usage": metric.memory_usage if metric else None,
            "size": DEVICE_TYPE_SIZES.get(device.device_type, 30),
            "color": DEVICE_TYPE_COLORS.get(device.device_type, "#95a5a6"),
            # 手动布局坐标（为空则前端按层级自动布局）
            "x": device.topo_x,
            "y": device.topo_y,
            "width": device.topo_width,
            "height": device.topo_height,
        })

    valid_ids = {d.id for d in devices}
    edges = []
    for conn in connections:
        # 跳过指向已删除/禁用设备的连接
        if conn.source_device_id not in valid_ids or conn.dest_device_id not in valid_ids:
            continue

        src_if = iface_cache.get(conn.source_device_id, {}).get(conn.source_interface or "")
        dst_if = iface_cache.get(conn.dest_device_id, {}).get(conn.dest_interface or "")

        # 源设备出方向流量 = 通往目标设备的速率；入方向为其反向流量
        src_out = float(src_if.out_bps) if src_if and src_if.out_bps is not None else None
        src_in = float(src_if.in_bps) if src_if and src_if.in_bps is not None else None
        dst_out = float(dst_if.out_bps) if dst_if and dst_if.out_bps is not None else None
        dst_in = float(dst_if.in_bps) if dst_if and dst_if.in_bps is not None else None

        capacities = [
            float(i.if_speed) for i in (src_if, dst_if)
            if i is not None and i.if_speed
        ]
        capacity = min(capacities) if capacities else None

        flows = [v for v in (src_out, src_in, dst_out, dst_in) if v is not None]
        max_flow = max(flows) if flows else None
        utilization = round(max_flow / capacity * 100, 1) if max_flow and capacity else None

        source_status = (src_if.if_oper_status or "up") if src_if else "unknown"
        dest_status = (dst_if.if_oper_status or "up") if dst_if else "unknown"
        oper_up = bool(
            (src_if is None or source_status == "up")
            and (dst_if is None or dest_status == "up")
        )
        source_errors = int((src_if.in_errors or 0) + (src_if.out_errors or 0)) if src_if else 0
        dest_errors = int((dst_if.in_errors or 0) + (dst_if.out_errors or 0)) if dst_if else 0
        has_errors = (source_errors + dest_errors) > 0
        interface_status = "down" if not oper_up else ("error" if has_errors else "up")

        edges.append({
            "id": f"conn_{conn.id}",
            "connection_id": conn.id,
            "source": f"device_{conn.source_device_id}",
            "target": f"device_{conn.dest_device_id}",
            "source_interface": conn.source_interface or "",
            "target_interface": conn.dest_interface or "",
            "source_anchor": _normalize_anchor(conn.source_anchor),
            "dest_anchor": _normalize_anchor(conn.dest_anchor),
            "edge_offset": _normalize_edge_offset(conn.edge_offset),
            "edge_label_offset": _normalize_edge_offset(conn.edge_label_offset),
            "edge_color": (
                _normalize_edge_offset(conn.edge_offset) or {}
            ).get("color", ""),
            # 实时速率（bps）
            "src_out_bps": src_out,
            "src_in_bps": src_in,
            "dst_out_bps": dst_out,
            "dst_in_bps": dst_in,
            "capacity_bps": capacity,
            "utilization": utilization,
            "max_bps": max_flow,
            "oper_up": oper_up,
            "interface_status": interface_status,
            "source_oper_status": source_status,
            "dest_oper_status": dest_status,
            "source_errors": source_errors,
            "dest_errors": dest_errors,
            "has_errors": has_errors,
            "updated_at": (
                max(
                    [i.updated_at for i in (src_if, dst_if) if i is not None and i.updated_at],
                    default=None,
                ).isoformat()
                if (src_if or dst_if)
                else None
            ),
        })

    total_bps = sum(e["max_bps"] or 0 for e in edges)

    # 拓扑专用虚拟云节点/云链路：不参与资产、采集和 DeviceConnection
    cloud_layout = _load_cloud_layout(db)
    cloud_nodes_raw = _normalize_cloud_nodes(cloud_layout.get("cloud_nodes"))
    cloud_node_ids = {node["id"] for node in cloud_nodes_raw}
    cloud_links_raw = _normalize_cloud_links(
        cloud_layout.get("cloud_links"),
        cloud_node_ids,
        valid_ids,
    )
    cloud_nodes = [
        {
            "id": f"cloud_{node['id']}",
            "cloud_id": node["id"],
            "cloud_node_id": node["id"],
            "device_id": None,
            "label": node["label"],
            "ip_address": "",
            "device_type": "cloud",
            "location": "",
            "vendor": "",
            "model": "",
            "icon": "",
            "status": "unknown",
            "x": node["x"],
            "y": node["y"],
            "width": node["width"],
            "height": node["height"],
            "is_cloud": True,
            "cloud": True,
        }
        for node in cloud_nodes_raw
    ]
    cloud_links = []
    for link in cloud_links_raw:
        source_is_cloud = str(link["source"]).startswith("cloud_")
        device_endpoint = link["target"] if source_is_cloud else link["source"]
        interface_name = link["target_interface"] if source_is_cloud else link["source_interface"]
        try:
            device_id = int(str(device_endpoint).replace("device_", ""))
        except (TypeError, ValueError):
            device_id = None
        iface = iface_cache.get(device_id, {}).get(interface_name or "") if device_id else None
        capacity = float(iface.if_speed) if iface and iface.if_speed else None
        in_bps = float(iface.in_bps) if iface and iface.in_bps is not None else None
        out_bps = float(iface.out_bps) if iface and iface.out_bps is not None else None
        max_flow = max([v for v in (in_bps, out_bps) if v is not None], default=None)
        utilization = round(max_flow / capacity * 100, 1) if max_flow and capacity else None
        cloud_links.append({
            "id": f"cloudlink_{link['id']}",
            "cloud_link_id": link["id"],
            "connection_id": None,
            "source": link["source"],
            "target": link["target"],
            "source_interface": link["source_interface"],
            "target_interface": link["target_interface"],
            "is_cloud_link": True,
            "cloud_link": True,
            "edge_offset": link.get("edge_offset"),
            "edge_label_offset": link.get("edge_label_offset"),
            "source_anchor": link.get("source_anchor"),
            "dest_anchor": link.get("dest_anchor"),
            "color": link.get("color", ""),
            # 云出口用设备侧接口流量代表该出口的上下行
            "oper_up": (iface.if_oper_status or "up") == "up" if iface else None,
            "interface_status": (
                "unknown" if not iface
                else ("down" if (iface.if_oper_status or "up") != "up"
                      else ("error" if (int(iface.in_errors or 0) + int(iface.out_errors or 0)) > 0 else "up"))
            ),
            "source_errors": int(iface.in_errors or 0) if iface else 0,
            "dest_errors": int(iface.out_errors or 0) if iface else 0,
            "has_errors": bool(iface and (int(iface.in_errors or 0) + int(iface.out_errors or 0)) > 0),
            "capacity_bps": capacity,
            "utilization": utilization,
            "max_bps": max_flow,
            "src_out_bps": out_bps if not source_is_cloud else None,
            "src_in_bps": in_bps if not source_is_cloud else None,
            "dst_out_bps": out_bps if source_is_cloud else None,
            "dst_in_bps": in_bps if source_is_cloud else None,
            "updated_at": iface.updated_at.isoformat() if iface and iface.updated_at else None,
        })

    return {
        "nodes": nodes,
        "edges": edges,
        "cloud_nodes": cloud_nodes,
        "cloud_links": cloud_links,
        "total_devices": len(nodes),
        "total_connections": len(edges),
        "total_cloud_nodes": len(cloud_nodes),
        "total_cloud_links": len(cloud_links),
        "total_bps": round(total_bps, 2),
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.put("/layout")
def save_topology_layout(payload: dict, db: Session = Depends(get_db)):
    """保存手动拓扑布局（编辑模式下拖动节点后保存）

    请求体：
      {"nodes": [{"device_id": 1, "x": 120.5, "y": 80.0, "width": 116, "height": 82}, ...],
       "edges": [{"connection_id": 8, "offset_x": 20, "offset_y": -12}, ...],
       "cloud_nodes": [{"id": 1, "label": "互联网出口", "x": 120, "y": 80}],
       "cloud_links": [{"id": 1, "source": "cloud_1", "target": "device_5",
                        "source_interface": "", "target_interface": "GE0/1"}]}
      {"reset": true}   # 恢复自动布局（清空设备坐标、连线偏移、云节点和云链路）
    """
    if payload.get("reset"):
        db.query(Device).filter(
            (Device.topo_x.isnot(None)) | (Device.topo_y.isnot(None))
            | (Device.topo_width.isnot(None)) | (Device.topo_height.isnot(None))
        ).update(
            {"topo_x": None, "topo_y": None, "topo_width": None, "topo_height": None},
            synchronize_session=False,
        )
        db.query(DeviceConnection).filter(
            (DeviceConnection.edge_offset.isnot(None))
            | (DeviceConnection.edge_label_offset.isnot(None))
            | (DeviceConnection.source_anchor.isnot(None))
            | (DeviceConnection.dest_anchor.isnot(None))
        ).update(
            {
                "edge_offset": None,
                "edge_label_offset": None,
                "source_anchor": None,
                "dest_anchor": None,
            },
            synchronize_session=False,
        )
        _clear_cloud_layout(db)
        db.commit()
        invalidate_topology()
        return {"message": "已恢复自动布局", "saved": 0, "cloud_nodes": 0, "cloud_links": 0}

    nodes = payload.get("nodes")
    cloud_nodes_present = "cloud_nodes" in payload
    cloud_links_present = "cloud_links" in payload
    if nodes is None:
        nodes = []
    if not isinstance(nodes, list):
        raise HTTPException(status_code=400, detail="nodes 必须是数组")
    if not nodes and not (cloud_nodes_present or cloud_links_present):
        raise HTTPException(status_code=400, detail="nodes 不能为空")

    devices = {d.id: d for d in db.query(Device).all()}
    saved = 0
    for item in nodes:
        if not isinstance(item, dict):
            continue
        device_id = item.get("device_id")
        device = devices.get(int(device_id)) if device_id is not None else None
        if not device:
            continue
        try:
            x = float(item.get("x"))
            y = float(item.get("y"))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="坐标必须是数字") from None
        # 合理范围保护，避免异常值导致画布无限大
        if not (-20000 <= x <= 20000 and -20000 <= y <= 20000):
            raise HTTPException(status_code=400, detail="坐标超出允许范围")
        device.topo_x = round(x, 2)
        device.topo_y = round(y, 2)
        width = item.get("width")
        height = item.get("height")
        if width is not None or height is not None:
            try:
                node_width = float(width)
                node_height = float(height)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail="设备尺寸必须是数字") from None
            if not (70 <= node_width <= 320 and 50 <= node_height <= 240):
                raise HTTPException(status_code=400, detail="设备尺寸超出允许范围（宽 70~320，高 50~240）")
            device.topo_width = round(node_width, 2)
            device.topo_height = round(node_height, 2)
        saved += 1

    saved_edges = 0
    edge_items = payload.get("edges") or []
    if not isinstance(edge_items, list):
        raise HTTPException(status_code=400, detail="edges 必须是数组")
    connections = {c.id: c for c in db.query(DeviceConnection).all()}
    for item in edge_items:
        if not isinstance(item, dict):
            continue
        connection_id = item.get("connection_id")
        conn = connections.get(int(connection_id)) if connection_id is not None else None
        if not conn:
            continue
        if "source_device_id" in item and item.get("source_device_id") is not None:
            new_source_id = int(item.get("source_device_id"))
            if new_source_id not in devices:
                raise HTTPException(status_code=400, detail="源设备不存在")
            if new_source_id != conn.source_device_id:
                conn.source_device_id = new_source_id
                conn.source_interface = ""
        if "dest_device_id" in item and item.get("dest_device_id") is not None:
            new_dest_id = int(item.get("dest_device_id"))
            if new_dest_id not in devices:
                raise HTTPException(status_code=400, detail="目的设备不存在")
            if new_dest_id != conn.dest_device_id:
                conn.dest_device_id = new_dest_id
                conn.dest_interface = ""
        if conn.source_device_id == conn.dest_device_id:
            raise HTTPException(status_code=400, detail="不能连接设备自身")
        offset = _normalize_edge_offset({
            "x": item.get("offset_x", 0),
            "y": item.get("offset_y", 0),
            "points": item.get("offset_points") or [],
        })
        edge_color = _normalize_color(item.get("edge_color"))
        if edge_color:
            offset = offset or {"x": 0, "y": 0}
            offset["color"] = edge_color
        has_control_points = bool(offset and isinstance(offset.get("points"), list) and offset.get("points"))
        conn.edge_offset = None if not offset or (
            abs(offset.get("x", 0)) < 0.01
            and abs(offset.get("y", 0)) < 0.01
            and not offset.get("color")
            and not has_control_points
        ) else offset
        label_offset = _normalize_edge_offset({
            "x": item.get("label_offset_x", 0),
            "y": item.get("label_offset_y", 0),
        })
        conn.edge_label_offset = (
            None if not label_offset or (abs(label_offset["x"]) < 0.01 and abs(label_offset["y"]) < 0.01)
            else label_offset
        )
        if "source_anchor" in item:
            conn.source_anchor = _normalize_anchor(item.get("source_anchor"))
        if "dest_anchor" in item:
            conn.dest_anchor = _normalize_anchor(item.get("dest_anchor"))
        saved_edges += 1

    # 云节点/云链路独立维护，不写入 DeviceConnection
    saved_cloud_nodes = 0
    saved_cloud_links = 0
    if cloud_nodes_present or cloud_links_present:
        existing_cloud = _load_cloud_layout(db)
        if cloud_nodes_present:
            raw_cloud_nodes = payload.get("cloud_nodes")
            if not isinstance(raw_cloud_nodes, list):
                raise HTTPException(status_code=400, detail="cloud_nodes 必须是数组")
            cloud_nodes = _normalize_cloud_nodes(raw_cloud_nodes)
        else:
            cloud_nodes = _normalize_cloud_nodes(existing_cloud.get("cloud_nodes"))
        cloud_node_ids = {node["id"] for node in cloud_nodes}

        if cloud_links_present:
            raw_cloud_links = payload.get("cloud_links")
            if not isinstance(raw_cloud_links, list):
                raise HTTPException(status_code=400, detail="cloud_links 必须是数组")
        else:
            # 仅更新云节点时保留已有链路，但过滤掉已删除云节点/设备对应的链路
            raw_cloud_links = existing_cloud.get("cloud_links")
        cloud_links = _normalize_cloud_links(raw_cloud_links, cloud_node_ids, set(devices))
        _save_cloud_layout(db, cloud_nodes, cloud_links)
        saved_cloud_nodes = len(cloud_nodes)
        saved_cloud_links = len(cloud_links)

    db.commit()
    invalidate_topology()
    message = f"布局已保存（{saved} 个节点，{saved_edges} 条连线）"
    if saved_cloud_nodes or saved_cloud_links:
        message += f"，云节点 {saved_cloud_nodes} 个，云出口链路 {saved_cloud_links} 条"
    return {
        "message": message,
        "saved": saved,
        "saved_edges": saved_edges,
        "saved_cloud_nodes": saved_cloud_nodes,
        "saved_cloud_links": saved_cloud_links,
    }


@router.post("/discover")
async def discover_topology(db: Session = Depends(get_db)):
    """通过 SNMP LLDP/CDP 自动发现设备连接关系并写入数据库"""
    from ..snmp.discovery import TopologyDiscovery

    discovery = TopologyDiscovery(db)
    added = await discovery.discover()
    invalidate_topology()
    invalidate_dashboard()

    total = db.query(DeviceConnection).count()
    return {
        "message": f"自动发现完成，新增 {added} 条连接",
        "added": added,
        "total_connections": total,
    }


@router.post("/add-connection")
def add_connection(payload: ConnectionCreate, db: Session = Depends(get_db)):
    """手动添加设备连接关系"""
    src = db.query(Device).filter(Device.id == payload.source_device_id).first()
    dst = db.query(Device).filter(Device.id == payload.dest_device_id).first()
    if not src or not dst:
        raise HTTPException(status_code=404, detail="源设备或目的设备不存在")
    if src.id == dst.id:
        raise HTTPException(status_code=400, detail="不能连接设备自身")

    exists = db.query(DeviceConnection).filter(
        DeviceConnection.source_device_id == payload.source_device_id,
        DeviceConnection.dest_device_id == payload.dest_device_id,
        DeviceConnection.source_interface == (payload.source_interface or ""),
        DeviceConnection.dest_interface == (payload.dest_interface or ""),
    ).first()
    if exists:
        raise HTTPException(status_code=400, detail="该连接已存在")

    conn = DeviceConnection(
        source_device_id=payload.source_device_id,
        source_interface=payload.source_interface or "",
        dest_device_id=payload.dest_device_id,
        dest_interface=payload.dest_interface or "",
        source_anchor=_normalize_anchor(payload.source_anchor),
        dest_anchor=_normalize_anchor(payload.dest_anchor),
        discovered_at=datetime.utcnow(),
    )
    db.add(conn)
    db.commit()
    db.refresh(conn)
    invalidate_topology()
    return {"id": conn.id, "message": "连接已添加"}


@router.put("/connection/{conn_id}")
def update_connection(conn_id: int, payload: ConnectionCreate, db: Session = Depends(get_db)):
    """修改已有设备连接的源/目的设备、接口和锚点。"""
    conn = db.query(DeviceConnection).filter(DeviceConnection.id == conn_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="连接不存在")
    src = db.query(Device).filter(Device.id == payload.source_device_id).first()
    dst = db.query(Device).filter(Device.id == payload.dest_device_id).first()
    if not src or not dst:
        raise HTTPException(status_code=404, detail="源设备或目的设备不存在")
    if src.id == dst.id:
        raise HTTPException(status_code=400, detail="不能连接设备自身")
    exists = db.query(DeviceConnection).filter(
        DeviceConnection.id != conn_id,
        DeviceConnection.source_device_id == payload.source_device_id,
        DeviceConnection.dest_device_id == payload.dest_device_id,
        DeviceConnection.source_interface == (payload.source_interface or ""),
        DeviceConnection.dest_interface == (payload.dest_interface or ""),
    ).first()
    if exists:
        raise HTTPException(status_code=400, detail="该连接已存在")
    conn.source_device_id = payload.source_device_id
    conn.source_interface = payload.source_interface or ""
    conn.dest_device_id = payload.dest_device_id
    conn.dest_interface = payload.dest_interface or ""
    if payload.source_anchor is not None:
        conn.source_anchor = _normalize_anchor(payload.source_anchor)
    if payload.dest_anchor is not None:
        conn.dest_anchor = _normalize_anchor(payload.dest_anchor)
    db.commit()
    invalidate_topology()
    return {"id": conn.id, "message": "连接参数已更新"}


@router.delete("/connection/{conn_id}")
def delete_connection(conn_id: int, db: Session = Depends(get_db)):
    """删除设备连接关系"""
    conn = db.query(DeviceConnection).filter(DeviceConnection.id == conn_id).first()
    if not conn:
        raise HTTPException(status_code=404, detail="连接不存在")

    db.delete(conn)
    db.commit()
    invalidate_topology()
    return {"message": "连接已删除"}


def get_device_status(db: Session, device_id: int) -> str:
    """获取设备状态: online / warning / offline / unknown"""
    # 未确认离线告警优先
    offline_alert = db.query(Alert).filter(
        Alert.device_id == device_id,
        Alert.alert_type == "offline",
        Alert.is_acknowledged == False,
    ).first()
    if offline_alert:
        return "offline"

    metric = (
        db.query(DeviceMetric)
        .filter(DeviceMetric.device_id == device_id)
        .order_by(DeviceMetric.collected_at.desc())
        .first()
    )

    if not metric or not metric.collected_at:
        return "unknown"

    if (datetime.utcnow() - metric.collected_at).total_seconds() > 300:
        return "offline"

    critical_alerts = db.query(Alert).filter(
        Alert.device_id == device_id,
        Alert.is_acknowledged == False,
        Alert.alert_level == "critical",
        Alert.alert_type != "offline",
    ).count()

    return "warning" if critical_alerts > 0 else "online"
