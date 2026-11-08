"""集群节点身份、心跳与负载均衡配置生成

集群依赖共享数据库：每个实例把本机心跳写入 cluster_nodes，
所有节点从同一张表读取集群状态。节点本地身份保存在
data/cluster_node.json，不使用共享配置，避免所有节点同名。
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import socket
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..config import Config
from ..models.cluster import ClusterNode
from ..models.database import SessionLocal
from ..services import license_manager, settings as settings_service
from ..services import version_info

logger = logging.getLogger("snmp-monitor.cluster")

IDENTITY_FILE = Path(Config.LICENSE_FILE).parent / "cluster_node.json"
_loop_task: Optional[asyncio.Task] = None
_stopping = False


def _now() -> datetime:
    return datetime.utcnow()


def _write_identity(data: Dict[str, Any]) -> None:
    IDENTITY_FILE.parent.mkdir(parents=True, exist_ok=True)
    temp = IDENTITY_FILE.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(temp, 0o600)
    except OSError:
        pass
    temp.replace(IDENTITY_FILE)


def load_identity() -> Dict[str, Any]:
    """读取本机节点身份；第一次启动时自动生成。"""
    try:
        data = json.loads(IDENTITY_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict) and data.get("node_id"):
            return data
    except (OSError, ValueError):
        pass
    host = platform.node() or socket.gethostname() or "node"
    data = {
        "node_id": uuid.uuid4().hex,
        "name": host[:120],
        "address": f"{socket.gethostname()}:8000",
        "created_at": _now().isoformat(),
    }
    _write_identity(data)
    return data


def update_identity(name: str, address: str) -> Dict[str, Any]:
    identity = load_identity()
    identity["name"] = str(name or identity.get("name") or "node").strip()[:120]
    identity["address"] = str(address or "").strip()[:255]
    _write_identity(identity)
    return identity


def _settings(db: Session) -> Dict[str, Any]:
    return settings_service.get_all(db)


def _heartbeat_interval(values: Dict[str, Any]) -> int:
    try:
        return max(10, min(300, int(values.get("cluster_heartbeat_interval") or 30)))
    except (TypeError, ValueError):
        return 30


def _license_snapshot() -> Dict[str, Any]:
    try:
        return license_manager.get_license_status()
    except Exception as exc:  # noqa: BLE001
        logger.warning("读取授权状态失败: %s", exc)
        return {"status": "invalid", "max_nodes": 0, "message": str(exc)}


def _serialize_node(node: ClusterNode, interval: int, local_id: str) -> Dict[str, Any]:
    last = node.last_heartbeat
    stale_after = max(interval * 3, 90)
    status = node.status or "offline"
    online = bool(last and (_now() - last).total_seconds() <= stale_after) and status not in (
        "offline", "license_invalid", "license_limit",
    )
    if not online and status not in ("license_invalid", "license_limit"):
        status = "offline"
    return {
        "id": node.id,
        "node_id": node.node_id,
        "name": node.name,
        "address": node.address or "",
        "version": node.version or "",
        "status": status,
        "online": online,
        "local": node.node_id == local_id,
        "weight": node.weight or 1,
        "license_status": node.license_status or "",
        "license_max_nodes": node.license_max_nodes or 0,
        "license_expires_at": node.license_expires_at,
        "started_at": node.started_at.isoformat() if node.started_at else None,
        "last_heartbeat": last.isoformat() if last else None,
    }


def cluster_status(db: Session) -> Dict[str, Any]:
    values = _settings(db)
    interval = _heartbeat_interval(values)
    identity = load_identity()
    license_status = _license_snapshot()
    try:
        version = version_info.get_version_info(db).get("effective", {}).get("display_version", "")
    except Exception:  # noqa: BLE001
        version = ""
    nodes = db.query(ClusterNode).order_by(ClusterNode.last_heartbeat.desc(), ClusterNode.id.asc()).all()
    serialized = [_serialize_node(node, interval, identity["node_id"]) for node in nodes]
    online_nodes = [node for node in serialized if node["online"]]
    max_nodes = int(license_status.get("max_nodes") or 0)
    return {
        "settings": {
            "cluster_enabled": bool(values.get("cluster_enabled")),
            "cluster_name": values.get("cluster_name") or "",
            "cluster_heartbeat_interval": interval,
            "lb_enabled": bool(values.get("lb_enabled")),
            "lb_strategy": values.get("lb_strategy") or "round_robin",
            "lb_public_url": values.get("lb_public_url") or "",
            "lb_sticky": bool(values.get("lb_sticky")),
        },
        "identity": identity,
        "nodes": serialized,
        "summary": {
            "total": len(serialized),
            "online": len(online_nodes),
            "max_nodes": max_nodes,
            "license_status": license_status.get("status"),
            "license_licensed": license_status.get("licensed", False),
            "license_message": license_status.get("message", ""),
        },
        "server_version": version,
    }


def _is_license_clusterable(status: Dict[str, Any]) -> bool:
    return status.get("status") == "licensed" and status.get("licensed", False)


def heartbeat(db: Session) -> Dict[str, Any]:
    """本机写入共享数据库心跳。失败不抛出，返回状态供日志使用。"""
    values = _settings(db)
    interval = _heartbeat_interval(values)
    identity = load_identity()
    license_status = _license_snapshot()
    configured_enabled = bool(values.get("cluster_enabled"))
    if not configured_enabled:
        return {"ok": False, "reason": "disabled"}
    if not _is_license_clusterable(license_status):
        _mark_local(db, identity, interval, license_status, status="license_invalid")
        return {"ok": False, "reason": "license", "message": license_status.get("message")}
    max_nodes = int(license_status.get("max_nodes") or 0)
    if max_nodes < 1:
        _mark_local(db, identity, interval, license_status, status="license_invalid")
        return {"ok": False, "reason": "license", "message": "授权未包含集群节点"}
    cutoff = _now() - timedelta(seconds=max(interval * 3, 90))
    active_nodes = (
        db.query(ClusterNode)
        .filter(ClusterNode.last_heartbeat >= cutoff, ClusterNode.node_id != identity["node_id"])
        .all()
    )
    active_limits = [int(node.license_max_nodes or 0) for node in active_nodes if int(node.license_max_nodes or 0) > 0]
    effective_limit = min([max_nodes] + active_limits) if active_limits else max_nodes
    local = db.query(ClusterNode).filter(ClusterNode.node_id == identity["node_id"]).first()
    if not local and len(active_nodes) >= effective_limit:
        return {
            "ok": False,
            "reason": "limit",
            "message": f"集群节点数已达到有效授权上限 {effective_limit} 个",
        }
    if not local:
        local = ClusterNode(
            node_id=identity["node_id"],
            name=identity.get("name") or "node",
            address=identity.get("address") or "",
            weight=1,
            started_at=_now(),
        )
        db.add(local)
        db.flush()
    local.name = str(identity.get("name") or local.name or "node")[:120]
    local.address = str(identity.get("address") or "")[:255]
    try:
        local.version = version_info.get_version_info(db).get("effective", {}).get("display_version", "")[:80]
    except Exception:  # noqa: BLE001
        local.version = local.version or ""
    local.status = "online"
    local.license_status = str(license_status.get("status") or "")
    local.license_max_nodes = max_nodes
    local.license_expires_at = str(license_status.get("expires_at") or "")
    local.last_heartbeat = _now()
    db.commit()
    return {"ok": True, "max_nodes": effective_limit, "active_nodes": len(active_nodes) + 1}


def _mark_local(db: Session, identity: Dict[str, Any], interval: int, license_status: Dict[str, Any], status: str) -> None:
    local = db.query(ClusterNode).filter(ClusterNode.node_id == identity["node_id"]).first()
    if not local:
        return
    local.status = status
    local.license_status = str(license_status.get("status") or "")
    local.license_max_nodes = int(license_status.get("max_nodes") or 0)
    local.last_heartbeat = _now()
    db.commit()


def mark_offline(db: Session) -> None:
    try:
        identity = load_identity()
        local = db.query(ClusterNode).filter(ClusterNode.node_id == identity["node_id"]).first()
        if local:
            local.status = "offline"
            local.last_heartbeat = _now()
            db.commit()
    except Exception as exc:  # noqa: BLE001
        logger.debug("标记节点离线失败: %s", exc)


def remove_node(db: Session, node_id: str) -> bool:
    node = db.query(ClusterNode).filter(ClusterNode.node_id == node_id).first()
    if not node:
        return False
    db.delete(node)
    db.commit()
    return True


def update_weight(db: Session, node_id: str, weight: int) -> bool:
    node = db.query(ClusterNode).filter(ClusterNode.node_id == node_id).first()
    if not node:
        return False
    node.weight = max(1, min(100, int(weight)))
    db.commit()
    return True


def lb_config(db: Session) -> Dict[str, Any]:
    values = _settings(db)
    identity = load_identity()
    interval = _heartbeat_interval(values)
    cutoff = _now() - timedelta(seconds=max(interval * 3, 90))
    nodes = (
        db.query(ClusterNode)
        .filter(ClusterNode.last_heartbeat >= cutoff, ClusterNode.status == "online")
        .order_by(ClusterNode.id.asc())
        .all()
    )
    strategy = values.get("lb_strategy") or "round_robin"
    sticky = bool(values.get("lb_sticky"))
    lines = ["upstream snmp_nms_cluster {"]
    if sticky or strategy == "ip_hash":
        lines.append("    ip_hash;")
    elif strategy == "least_conn":
        lines.append("    least_conn;")
    used = []
    for node in nodes:
        address = (node.address or "").strip()
        if not address or ":" not in address:
            continue
        used.append({"name": node.name, "address": address, "weight": node.weight or 1})
        lines.append(f"    server {address} weight={node.weight or 1} max_fails=3 fail_timeout=10s;")
    lines.append("}")
    lines.extend([
        "",
        "server {",
        "    listen 80;",
        "    server_name _;",
        "    location / {",
        "        proxy_pass http://snmp_nms_cluster;",
        "        proxy_set_header Host $host;",
        "        proxy_set_header X-Real-IP $remote_addr;",
        "        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;",
        "        proxy_read_timeout 300s;",
        "    }",
        "}",
    ])
    return {
        "enabled": bool(values.get("lb_enabled")),
        "strategy": strategy,
        "sticky": sticky,
        "public_url": values.get("lb_public_url") or "",
        "nodes": used,
        "config": "\n".join(lines),
        "warning": "节点地址必须填写为 host:port，且所有节点连接同一个外部数据库和 Redis。",
    }


async def heartbeat_loop() -> None:
    global _stopping
    _stopping = False
    await asyncio.sleep(8)
    while not _stopping:
        db = SessionLocal()
        sleep_seconds = 30
        try:
            sleep_seconds = _heartbeat_interval(_settings(db))
            result = heartbeat(db)
            if not result.get("ok") and result.get("reason") not in ("disabled",):
                logger.debug("集群心跳未注册: %s", result)
        except Exception as exc:  # noqa: BLE001
            logger.debug("集群心跳异常: %s", exc)
        finally:
            db.close()
        try:
            await asyncio.sleep(max(10, sleep_seconds))
        except asyncio.CancelledError:
            break


def start_loop() -> None:
    global _loop_task
    if _loop_task and not _loop_task.done():
        return
    try:
        loop = asyncio.get_running_loop()
        _loop_task = loop.create_task(heartbeat_loop())
    except RuntimeError:
        _loop_task = None


async def stop_loop() -> None:
    global _stopping
    _stopping = True
    if _loop_task and not _loop_task.done():
        _loop_task.cancel()
        try:
            await _loop_task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001
            pass
