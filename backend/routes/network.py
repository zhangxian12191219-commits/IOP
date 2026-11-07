"""主机网络配置、服务、计划任务与防火墙（仅超级管理员）"""
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..services import audit
from ..services import host_network

router = APIRouter(prefix="/api/network", tags=["主机网络"])


def _fail(request: Request, db: Session, module: str, action: str, target: str, exc: Exception):
    audit.record(
        db, request, module="network", action=action,
        target_type=module, target_name=target,
        status="failed", message=str(exc)[:800],
    )
    raise HTTPException(status_code=400, detail=str(exc)) from exc


def _confirm(payload: Dict[str, Any], label: str) -> None:
    if not payload.get("confirm"):
        raise HTTPException(status_code=400, detail=f"请确认{label}")


@router.get("/overview")
def overview():
    try:
        return host_network.get_overview()
    except host_network.HostCommandError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.put("/adapter")
def configure_adapter(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    _confirm(payload, "网络变更可能中断当前连接")
    name = str(payload.get("name") or "")
    try:
        result = host_network.configure_adapter(
            name=name,
            mode=str(payload.get("mode") or ""),
            ip=str(payload.get("ip") or ""),
            prefix=payload.get("prefix") or 24,
            gateway=str(payload.get("gateway") or ""),
            dns=payload.get("dns") or [],
        )
    except host_network.HostCommandError as exc:
        _fail(request, db, "adapter", "update", name, exc)
    audit.record(
        db, request, module="network", action="update",
        target_type="adapter", target_name=name,
        after={"mode": payload.get("mode"), "ip": payload.get("ip"),
               "prefix": payload.get("prefix"), "gateway": payload.get("gateway")},
        message="修改主机网卡配置",
    )
    return result


@router.post("/routes")
def add_route(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    _confirm(payload, "添加路由")
    destination = str(payload.get("destination") or "")
    try:
        result = host_network.add_route(
            destination=destination,
            gateway=str(payload.get("gateway") or ""),
            interface=str(payload.get("interface") or ""),
            metric=payload.get("metric") or 10,
        )
    except host_network.HostCommandError as exc:
        _fail(request, db, "route", "create", destination, exc)
    audit.record(
        db, request, module="network", action="create",
        target_type="route", target_name=destination,
        after={"gateway": payload.get("gateway"), "interface": payload.get("interface")},
        message="新增主机明细路由",
    )
    return result


@router.post("/routes/delete")
def delete_route(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    _confirm(payload, "删除路由")
    destination = str(payload.get("destination") or "")
    try:
        result = host_network.delete_route(
            destination=destination,
            gateway=str(payload.get("gateway") or ""),
            interface=str(payload.get("interface") or ""),
        )
    except host_network.HostCommandError as exc:
        _fail(request, db, "route", "delete", destination, exc)
    audit.record(
        db, request, module="network", action="delete",
        target_type="route", target_name=destination,
        message="删除主机明细路由",
    )
    return result


@router.post("/firewall")
def set_firewall(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    action = str(payload.get("action") or "").lower()
    if action not in ("enable", "disable"):
        raise HTTPException(status_code=400, detail="防火墙操作只支持 enable / disable")
    _confirm(payload, "切换防火墙可能改变主机暴露面")
    try:
        result = host_network.set_firewall(action == "enable")
    except host_network.HostCommandError as exc:
        _fail(request, db, "firewall", "update", action, exc)
    audit.record(
        db, request, module="network", action="update",
        target_type="firewall", target_name=action,
        message=f"{'启用' if action == 'enable' else '关闭'}主机防火墙",
    )
    return result


@router.post("/restart")
def restart_network(
    request: Request,
    payload: Optional[Dict[str, Any]] = Body(default=None),
    db: Session = Depends(get_db),
):
    """重启 Linux 网络服务，使修改后的 IP/DNS/路由立即重新加载。"""
    payload = payload or {}
    _confirm(payload, "重启网络服务可能短暂中断当前连接")
    try:
        result = host_network.restart_network_service()
    except host_network.HostCommandError as exc:
        _fail(request, db, "network_service", "restart", "network", exc)
    audit.record(
        db, request, module="network", action="restart",
        target_type="network_service", target_name=result.get("service") or "network",
        message=result.get("message") or "重启主机网络服务",
    )
    return result


@router.get("/services")
def services(query: str = "", limit: int = 300):
    try:
        return {"items": host_network.list_services(query=query, limit=limit)}
    except host_network.HostCommandError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/services/action")
def service_action(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    name = str(payload.get("name") or "")
    action = str(payload.get("action") or "")
    _confirm(payload, f"对服务 {name} 执行 {action}")
    try:
        result = host_network.service_action(name, action)
    except host_network.HostCommandError as exc:
        _fail(request, db, "service", action, name, exc)
    audit.record(
        db, request, module="network", action=action,
        target_type="service", target_name=name,
        message=f"服务操作：{action} {name}",
    )
    return result


@router.get("/scheduled-tasks")
def scheduled_tasks():
    try:
        return {"items": host_network.list_scheduled_tasks()}
    except host_network.HostCommandError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/scheduled-tasks/action")
def scheduled_task_action(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    name = str(payload.get("name") or "")
    action = str(payload.get("action") or "")
    _confirm(payload, f"对计划任务 {name} 执行 {action}")
    try:
        result = host_network.scheduled_task_action(name, action)
    except host_network.HostCommandError as exc:
        _fail(request, db, "scheduled_task", action, name, exc)
    audit.record(
        db, request, module="network", action=action,
        target_type="scheduled_task", target_name=name,
        message=f"计划任务操作：{action} {name}",
    )
    return result
