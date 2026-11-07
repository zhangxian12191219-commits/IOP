"""集群节点与负载均衡配置 API（仅超级管理员）"""
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..services import audit
from ..services import cluster_manager
from ..services import license_manager
from ..services import settings as settings_service

router = APIRouter(prefix="/api/cluster", tags=["集群"])

CONFIG_KEYS = {
    "cluster_enabled", "cluster_name", "cluster_heartbeat_interval",
    "lb_enabled", "lb_strategy", "lb_public_url", "lb_sticky",
}


def _license() -> Dict[str, Any]:
    return license_manager.get_license_status()


@router.get("/status")
def get_status(db: Session = Depends(get_db)):
    return cluster_manager.cluster_status(db)


@router.put("/config")
def update_config(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    data = payload.get("settings") if isinstance(payload, dict) and "settings" in payload else payload
    if not isinstance(data, dict) or not data:
        raise HTTPException(status_code=400, detail="没有需要保存的集群配置")
    data = {key: value for key, value in data.items() if key in CONFIG_KEYS}
    if not data:
        raise HTTPException(status_code=400, detail="没有可用的集群配置项")
    if data.get("cluster_enabled"):
        status = _license()
        if status.get("status") not in ("licensed", "opensource") or not status.get("valid", True):
            raise HTTPException(status_code=400, detail="启用集群需要有效授权")
        if int(status.get("max_nodes") or 0) < 1:
            raise HTTPException(status_code=400, detail="当前授权未包含集群节点额度")
    normalized, errors = settings_service.validate(data)
    if errors:
        raise HTTPException(status_code=400, detail="；".join(errors))
    before = settings_service.get_all(db)
    updated = settings_service.save(db, normalized)
    audit.record(
        db, request, module="cluster", action="update",
        target_type="cluster_config", target_name="集群配置",
        before={key: before.get(key) for key in normalized},
        after=normalized,
        message=f"更新集群配置 {len(normalized)} 项",
    )
    return {
        "message": "集群配置已保存",
        "settings": {key: updated.get(key) for key in CONFIG_KEYS},
        "status": cluster_manager.cluster_status(db),
    }


@router.get("/identity")
def get_identity():
    return cluster_manager.load_identity()


@router.put("/identity")
def update_identity(request: Request, payload: Dict[str, Any] = Body(...)):
    name = str(payload.get("name") or "").strip()
    address = str(payload.get("address") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="节点名称不能为空")
    if len(name) > 120 or len(address) > 255:
        raise HTTPException(status_code=400, detail="节点名称或地址过长")
    if address and ":" not in address:
        raise HTTPException(status_code=400, detail="节点地址格式应为 host:port")
    identity = cluster_manager.update_identity(name, address)
    return {"message": "本节点身份已保存", "identity": identity}


@router.get("/nodes")
def list_nodes(db: Session = Depends(get_db)):
    status = cluster_manager.cluster_status(db)
    return {
        "items": status["nodes"],
        "summary": status["summary"],
        "next_heartbeat_seconds": 30,
    }


@router.put("/nodes/{node_id}")
def update_node_weight(
    node_id: str,
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    try:
        weight = int(payload.get("weight") or 1)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="节点权重必须是整数") from exc
    if not cluster_manager.update_weight(db, node_id, weight):
        raise HTTPException(status_code=404, detail="节点不存在")
    audit.record(
        db, request, module="cluster", action="update",
        target_type="cluster_node", target_name=node_id,
        after={"weight": max(1, min(100, weight))},
        message="调整集群节点权重",
    )
    return {"message": "节点权重已更新"}


@router.delete("/nodes/{node_id}")
def remove_node(node_id: str, request: Request, db: Session = Depends(get_db)):
    identity = cluster_manager.load_identity()
    if node_id == identity.get("node_id"):
        raise HTTPException(status_code=400, detail="不能删除当前节点，停止服务后节点会自动离线")
    if not cluster_manager.remove_node(db, node_id):
        raise HTTPException(status_code=404, detail="节点不存在")
    audit.record(
        db, request, module="cluster", action="delete",
        target_type="cluster_node", target_name=node_id,
        message="移除集群节点",
    )
    return {"message": "节点已移除"}


@router.get("/lb-config")
def get_lb_config(db: Session = Depends(get_db)):
    status = _license()
    if status.get("status") not in ("licensed", "opensource"):
        raise HTTPException(status_code=403, detail="生成负载均衡配置需要有效授权")
    return cluster_manager.lb_config(db)
