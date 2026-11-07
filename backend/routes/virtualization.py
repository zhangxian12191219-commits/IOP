"""虚拟化管理 API（只读纳管 VMware / H3C CAS / KVM）。"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..models.virtualization import VirtualHost, VirtualMachine, VirtualPlatform, VirtualizationAlert
from ..services import audit
from ..services import virtualization as virtualization_service
from ..services import virtualization_alerts as virtualization_alert_service
from ..services.virtualization_crypto import encrypt_password

router = APIRouter(prefix="/api/virtualization", tags=["虚拟化管理"])

PLATFORM_TYPES = {"vmware", "kvm", "cas", "proxmox", "docker", "kubernetes"}
POWER_STATES = {"running", "stopped", "paused", "unknown"}
TOP_METRICS = {"cpu_usage", "memory_usage", "disk_usage"}

VM_SORT_FIELDS = {
    "name": VirtualMachine.name,
    "power_state": VirtualMachine.power_state,
    "vcpu": VirtualMachine.vcpu,
    "memory_mb": VirtualMachine.memory_mb,
    "disk_total_gb": VirtualMachine.disk_total_gb,
    "disk_used_gb": VirtualMachine.disk_used_gb,
    "disk_usage": VirtualMachine.disk_usage,
    "cpu_usage": VirtualMachine.cpu_usage,
    "memory_usage": VirtualMachine.memory_usage,
    "ip_address": VirtualMachine.ip_sort_key,
    "last_seen": VirtualMachine.last_seen,
}
HOST_SORT_FIELDS = {
    "name": VirtualHost.name,
    "ip_address": VirtualHost.ip_address,
    "cluster_name": VirtualHost.cluster_name,
    "status": VirtualHost.status,
    "cpu_cores": VirtualHost.cpu_cores,
    "cpu_usage": VirtualHost.cpu_usage,
    "memory_total_mb": VirtualHost.memory_total_mb,
    "memory_usage": VirtualHost.memory_usage,
    "storage_total_gb": VirtualHost.storage_total_gb,
    "storage_usage": VirtualHost.storage_usage,
    "net_rx_bps": VirtualHost.net_rx_bps,
    "net_tx_bps": VirtualHost.net_tx_bps,
    "vm_count": VirtualHost.vm_count,
    "last_seen": VirtualHost.last_seen,
}


def _order_by(query, sort_fields, sort_by: str, sort_order: str, id_column):
    if sort_by not in sort_fields:
        raise HTTPException(status_code=400, detail="不支持的排序字段")
    if sort_order not in ("asc", "desc"):
        raise HTTPException(status_code=400, detail="排序方向只支持 asc 或 desc")
    column = sort_fields[sort_by]
    primary = column.desc() if sort_order == "desc" else column.asc()
    return query.order_by(primary, id_column.asc())


class PlatformPayload(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    platform_type: str = Field(..., min_length=1, max_length=20)
    address: str = Field(..., min_length=1, max_length=255)
    port: Optional[int] = Field(None, ge=1, le=65535)
    username: str = Field(..., min_length=1, max_length=120)
    password: Optional[str] = Field(None, max_length=500)
    verify_tls: bool = True
    enabled: bool = True
    sync_interval_minutes: int = Field(5, ge=1, le=1440)


class TestPayload(BaseModel):
    password: Optional[str] = Field(None, max_length=500)


class VmAlertSettingsPayload(BaseModel):
    cpu_enabled: bool = True
    cpu_threshold: int = Field(80, ge=1, le=100)
    memory_enabled: bool = True
    memory_threshold: int = Field(85, ge=1, le=100)
    disk_enabled: bool = True
    disk_threshold: int = Field(85, ge=1, le=100)
    shutdown_enabled: bool = True
    platform_enabled: bool = True
    storage_enabled: bool = True
    storage_threshold: int = Field(85, ge=1, le=100)


ALERT_LEVEL_PATTERN = "^(info|warning|critical|emergency)$"


class VmAlertAckPayload(BaseModel):
    """单条告警确认时可选调整级别与是否发送到告警渠道。"""
    alert_level: Optional[str] = Field(None, pattern=ALERT_LEVEL_PATTERN)
    send_notification: Optional[bool] = None


class VmAlertUpdatePayload(BaseModel):
    """更新告警级别/通知开关（不改变确认状态）。"""
    alert_level: Optional[str] = Field(None, pattern=ALERT_LEVEL_PATTERN)
    send_notification: Optional[bool] = None


class VmAlertBulkDeletePayload(BaseModel):
    ids: List[int] = Field(..., min_length=1, max_length=500)


class VmAlertBulkAckPayload(BaseModel):
    ids: List[int] = Field(..., min_length=1, max_length=500)
    alert_level: Optional[str] = Field(None, pattern=ALERT_LEVEL_PATTERN)
    send_notification: Optional[bool] = None


def _platform_dict(platform: VirtualPlatform, host_count: int = 0, vm_count: int = 0) -> Dict[str, Any]:
    return {
        "id": platform.id,
        "name": platform.name,
        "platform_type": platform.platform_type,
        "address": platform.address,
        "port": platform.port,
        "username": platform.username,
        "password_set": bool(platform.password_enc),
        "verify_tls": bool(platform.verify_tls),
        "enabled": bool(platform.enabled),
        "sync_interval_minutes": platform.sync_interval_minutes or 5,
        "last_sync_at": platform.last_sync_at.isoformat() if platform.last_sync_at else None,
        "last_sync_status": platform.last_sync_status or "never",
        "last_error": platform.last_error or "",
        "health": platform.last_health or {},
        "host_count": host_count,
        "vm_count": vm_count,
        "created_at": platform.created_at.isoformat() if platform.created_at else None,
    }


def _vm_dict(vm: VirtualMachine, platform: Optional[VirtualPlatform] = None) -> Dict[str, Any]:
    host = vm.host
    return {
        "id": vm.id,
        "platform_id": vm.platform_id,
        "platform_name": (platform or vm.platform).name if (platform or vm.platform) else "",
        "platform_type": (platform or vm.platform).platform_type if (platform or vm.platform) else "",
        "host_id": vm.host_id,
        "host_name": host.name if host else "",
        "cluster_name": host.cluster_name if host else "",
        "external_id": vm.external_id,
        "name": vm.name,
        "power_state": vm.power_state,
        "vcpu": vm.vcpu or 0,
        "memory_mb": vm.memory_mb or 0,
        "disk_total_gb": vm.disk_total_gb or 0,
        "disk_used_gb": vm.disk_used_gb or 0,
        "disk_usage": vm.disk_usage,
        "nic_count": vm.nic_count or 0,
        "ip_addresses": vm.ip_addresses or [],
        "primary_ip": vm.primary_ip or "",
        "guest_os": vm.guest_os or "",
        "tools_status": vm.tools_status or "",
        "cpu_usage": vm.cpu_usage,
        "memory_usage": vm.memory_usage,
        "net_rx_bps": vm.net_rx_bps or 0,
        "net_tx_bps": vm.net_tx_bps or 0,
        "last_seen": vm.last_seen.isoformat() if vm.last_seen else None,
    }


def _host_dict(host: VirtualHost, platform: Optional[VirtualPlatform] = None) -> Dict[str, Any]:
    return {
        "id": host.id,
        "platform_id": host.platform_id,
        "platform_name": (platform or host.platform).name if (platform or host.platform) else "",
        "platform_type": (platform or host.platform).platform_type if (platform or host.platform) else "",
        "external_id": host.external_id,
        "name": host.name,
        "ip_address": host.ip_address or host.name or "",
        "cluster_name": host.cluster_name or "",
        "status": host.status or "unknown",
        "cpu_model": host.cpu_model or "",
        "cpu_cores": host.cpu_cores or 0,
        "cpu_mhz": host.cpu_mhz or 0,
        "cpu_usage": host.cpu_usage,
        "memory_total_mb": host.memory_total_mb or 0,
        "memory_used_mb": host.memory_used_mb or 0,
        "memory_usage": host.memory_usage,
        "storage_total_gb": host.storage_total_gb or 0,
        "storage_used_gb": host.storage_used_gb or 0,
        "storage_usage": host.storage_usage,
        "net_rx_bps": host.net_rx_bps or 0,
        "net_tx_bps": host.net_tx_bps or 0,
        "vm_count": host.vm_count or 0,
        "uptime_seconds": host.uptime_seconds or 0,
        "last_seen": host.last_seen.isoformat() if host.last_seen else None,
    }


def _validate_payload(payload: PlatformPayload) -> str:
    platform_type = (payload.platform_type or "").strip().lower()
    if platform_type not in PLATFORM_TYPES:
        raise HTTPException(status_code=400, detail="平台类型只支持 vmware、cas、proxmox、kvm、docker 或 kubernetes")
    if not payload.address.strip():
        raise HTTPException(status_code=400, detail="平台地址不能为空")
    return platform_type


def _default_port(platform_type: str) -> int:
    return (
        443 if platform_type == "vmware"
        else 8006 if platform_type == "proxmox"
        else 8080 if platform_type == "cas"
        else 2375 if platform_type == "docker"
        else 6443 if platform_type == "kubernetes"
        else 22
    )


def _apply_payload(platform: VirtualPlatform, payload: PlatformPayload, platform_type: str) -> None:
    platform.name = payload.name.strip()
    platform.platform_type = platform_type
    platform.address = payload.address.strip()
    platform.port = payload.port or _default_port(platform_type)
    username = payload.username.strip()
    if platform_type == "vmware":
        username = virtualization_service.normalize_vmware_username(username)
    elif platform_type == "proxmox":
        username = virtualization_service.normalize_proxmox_username(username)
    platform.username = username
    platform.verify_tls = bool(payload.verify_tls)
    platform.enabled = bool(payload.enabled)
    platform.sync_interval_minutes = payload.sync_interval_minutes
    if payload.password is not None and payload.password != "":
        platform.password_enc = encrypt_password(payload.password)


@router.get("/platforms")
def list_platforms(db: Session = Depends(get_db)):
    platforms = db.query(VirtualPlatform).order_by(VirtualPlatform.created_at.asc()).all()
    rows = []
    for platform in platforms:
        rows.append(_platform_dict(
            platform,
            host_count=db.query(VirtualHost).filter(VirtualHost.platform_id == platform.id).count(),
            vm_count=db.query(VirtualMachine).filter(VirtualMachine.platform_id == platform.id).count(),
        ))
    return {"items": rows}


@router.post("/platforms", status_code=201)
def create_platform(payload: PlatformPayload, db: Session = Depends(get_db)):
    platform_type = _validate_payload(payload)
    if not payload.password:
        raise HTTPException(status_code=400, detail="新增平台必须填写密码")
    platform = VirtualPlatform(
        name=payload.name.strip(),
        platform_type=platform_type,
        address=payload.address.strip(),
        port=payload.port or _default_port(platform_type),
        username=(
            virtualization_service.normalize_vmware_username(payload.username)
            if platform_type == "vmware"
            else virtualization_service.normalize_proxmox_username(payload.username)
            if platform_type == "proxmox"
            else payload.username.strip()
        ),
        password_enc=encrypt_password(payload.password),
        verify_tls=payload.verify_tls,
        enabled=payload.enabled,
        sync_interval_minutes=payload.sync_interval_minutes,
    )
    db.add(platform)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="平台名称已存在")
    db.refresh(platform)
    return _platform_dict(platform)


@router.put("/platforms/{platform_id}")
def update_platform(platform_id: int, payload: PlatformPayload, db: Session = Depends(get_db)):
    platform = db.query(VirtualPlatform).filter(VirtualPlatform.id == platform_id).first()
    if not platform:
        raise HTTPException(status_code=404, detail="平台不存在")
    platform_type = _validate_payload(payload)
    _apply_payload(platform, payload, platform_type)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=400, detail="平台名称已存在")
    db.refresh(platform)
    return _platform_dict(platform)


@router.delete("/platforms/{platform_id}")
def delete_platform(platform_id: int, db: Session = Depends(get_db)):
    platform = db.query(VirtualPlatform).filter(VirtualPlatform.id == platform_id).first()
    if not platform:
        raise HTTPException(status_code=404, detail="平台不存在")
    db.delete(platform)
    db.commit()
    return {"ok": True}


@router.post("/platforms/{platform_id}/test")
def test_platform(platform_id: int, payload: Optional[TestPayload] = None, db: Session = Depends(get_db)):
    platform = db.query(VirtualPlatform).filter(VirtualPlatform.id == platform_id).first()
    if not platform:
        raise HTTPException(status_code=404, detail="平台不存在")
    try:
        result = virtualization_service.test_platform(platform, payload.password if payload else None)
        return {"ok": True, "detail": result}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/platforms/{platform_id}/sync")
def sync_platform(platform_id: int, db: Session = Depends(get_db)):
    platform = db.query(VirtualPlatform).filter(VirtualPlatform.id == platform_id).first()
    if not platform:
        raise HTTPException(status_code=404, detail="平台不存在")
    try:
        result = virtualization_service.sync_platform(db, platform)
        return {"ok": True, **result}
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/sync")
def sync_all(db: Session = Depends(get_db)):
    platforms = db.query(VirtualPlatform).filter(VirtualPlatform.enabled.is_(True)).all()
    results = []
    for platform in platforms:
        try:
            results.append({"platform": platform.name, "ok": True, **virtualization_service.sync_platform(db, platform)})
        except Exception as exc:  # noqa: BLE001
            results.append({"platform": platform.name, "ok": False, "error": str(exc)[:500]})
    return {"items": results}


@router.get("/alert-settings")
def get_vm_alert_settings(db: Session = Depends(get_db)):
    return virtualization_alert_service.get_rules(db)


@router.put("/alert-settings")
def save_vm_alert_settings(payload: VmAlertSettingsPayload, db: Session = Depends(get_db)):
    rules = virtualization_alert_service.save_rules(db, payload.model_dump())
    evaluation = virtualization_alert_service.evaluate_all(db)
    return {"settings": rules, "evaluation": evaluation}


@router.get("/vm-alerts")
def list_vm_alerts(
    status: str = Query("active", pattern="^(active|history|resolved|all)$"),
    target_type: str = Query("all", pattern="^(all|vm|platform)$"),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(VirtualizationAlert).filter(
        VirtualizationAlert.is_hidden.isnot(True),
    )
    if target_type == "platform":
        query = query.filter(VirtualizationAlert.vm_id.is_(None))
    elif target_type == "vm":
        query = query.filter(VirtualizationAlert.vm_id.is_not(None))
    if status == "active":
        # 活动告警只看是否恢复；确认只是处理状态，不能隐藏仍然存在的告警。
        query = query.filter(VirtualizationAlert.resolved_at.is_(None))
    elif status == "history":
        # 只有自动恢复/已解决的告警进入历史；已确认但仍存在的告警继续留在活动列表。
        query = query.filter(VirtualizationAlert.resolved_at.is_not(None))
    elif status == "resolved":
        query = query.filter(VirtualizationAlert.resolved_at.is_not(None))
    total = query.count()
    alerts = (
        query.order_by(
            VirtualizationAlert.resolved_at.is_not(None).asc(),
            VirtualizationAlert.created_at.desc(),
            VirtualizationAlert.id.desc(),
        )
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [virtualization_alert_service.alert_to_dict(alert) for alert in alerts],
        "counts": virtualization_alert_service.counts(db, target_type),
    }


@router.put("/vm-alerts/{alert_id}")
def update_vm_alert(
    alert_id: int,
    payload: VmAlertUpdatePayload,
    db: Session = Depends(get_db),
):
    """更新告警级别/是否发送到告警渠道，不改变确认状态。"""
    alert = db.query(VirtualizationAlert).filter(VirtualizationAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="虚拟机告警不存在")
    try:
        changed = virtualization_alert_service.update_alert(
            db, alert, payload.alert_level, payload.send_notification
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "message": "虚拟机告警设置已更新" if changed else "虚拟机告警设置无变化",
        "updated": bool(changed),
        "alert": virtualization_alert_service.alert_to_dict(alert),
    }


def _is_history_alert(alert: VirtualizationAlert) -> bool:
    return bool(alert.resolved_at is not None)


@router.delete("/vm-alerts/{alert_id}")
def delete_vm_alert(
    alert_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """删除一条已进入历史的虚拟化告警。"""
    alert = db.query(VirtualizationAlert).filter(VirtualizationAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="虚拟化告警不存在")
    if not _is_history_alert(alert):
        raise HTTPException(status_code=400, detail="只能删除已恢复的告警历史")
    target = alert.vm_name or alert.platform_name or "虚拟化告警"
    db.delete(alert)
    audit.record(
        db, request, module="virtualization", action="delete",
        target_type="virtualization_alert", target_id=alert_id, target_name=target,
        message="删除虚拟化告警历史",
    )
    db.commit()
    return {"message": "告警历史已删除", "deleted": 1}


@router.post("/vm-alerts/bulk-delete")
def bulk_delete_vm_alerts(
    payload: VmAlertBulkDeletePayload,
    request: Request,
    db: Session = Depends(get_db),
):
    """批量删除已恢复的虚拟化告警历史。"""
    alerts = (
        db.query(VirtualizationAlert)
        .filter(VirtualizationAlert.id.in_(payload.ids))
        .all()
    )
    if not alerts:
        raise HTTPException(status_code=404, detail="未找到可删除的告警历史")
    deletable = [alert for alert in alerts if _is_history_alert(alert)]
    skipped = len(alerts) - len(deletable)
    for alert in deletable:
        db.delete(alert)
    audit.record(
        db, request, module="virtualization", action="delete",
        target_type="virtualization_alert_batch", target_name="批量删除虚拟化告警历史",
        after={"ids": [alert.id for alert in deletable], "skipped": skipped},
        message=f"批量删除 {len(deletable)} 条虚拟化告警历史",
    )
    db.commit()
    return {
        "message": f"已删除 {len(deletable)} 条告警历史" + (f"，跳过 {skipped} 条当前告警" if skipped else ""),
        "deleted": len(deletable),
        "skipped": skipped,
    }


@router.post("/vm-alerts/bulk-ack")
def bulk_acknowledge_vm_alerts(
    payload: VmAlertBulkAckPayload,
    db: Session = Depends(get_db),
):
    """批量确认虚拟机告警，可同时统一设置级别与通知开关。"""
    alerts = (
        db.query(VirtualizationAlert)
        .filter(VirtualizationAlert.id.in_(payload.ids))
        .order_by(VirtualizationAlert.id.asc())
        .all()
    )
    if not alerts:
        raise HTTPException(status_code=404, detail="未找到可操作的虚拟机告警")
    try:
        result = virtualization_alert_service.bulk_acknowledge(
            db, alerts, payload.alert_level, payload.send_notification
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result["updated"]:
        message = f"已处理 {result['updated']} 条虚拟机告警（新确认 {result['acknowledged']} 条）"
    else:
        message = "所选虚拟机告警无需更新"
    return {
        "message": message,
        **result,
        "items": [virtualization_alert_service.alert_to_dict(alert) for alert in alerts],
    }


@router.post("/vm-alerts/{alert_id}/ack")
def acknowledge_vm_alert(
    alert_id: int,
    payload: Optional[VmAlertAckPayload] = None,
    db: Session = Depends(get_db),
):
    alert = db.query(VirtualizationAlert).filter(VirtualizationAlert.id == alert_id).first()
    if not alert:
        raise HTTPException(status_code=404, detail="虚拟机告警不存在")
    try:
        virtualization_alert_service.acknowledge_alert(
            db,
            alert,
            payload.alert_level if payload else None,
            payload.send_notification if payload else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.refresh(alert)
    return {"message": "虚拟机告警已确认", "alert": virtualization_alert_service.alert_to_dict(alert)}


@router.get("/overview")
def overview(db: Session = Depends(get_db)):
    counts = dict(
        db.query(VirtualMachine.power_state, func.count(VirtualMachine.id))
        .group_by(VirtualMachine.power_state)
        .all()
    )
    total = db.query(VirtualMachine).count()
    host_count = db.query(VirtualHost).count()
    platform_count = db.query(VirtualPlatform).count()
    last_sync = db.query(func.max(VirtualPlatform.last_sync_at)).scalar()
    alert_counts = virtualization_alert_service.counts(db)
    return {
        "total": total,
        "running": int(counts.get("running", 0)),
        "stopped": int(counts.get("stopped", 0)),
        "paused": int(counts.get("paused", 0)),
        "unknown": int(counts.get("unknown", 0)),
        "hosts": host_count,
        "platforms": platform_count,
        "vm_alerts_active": alert_counts["active"],
        "vm_alerts_unack": alert_counts["unacknowledged"],
        "last_sync_at": last_sync.isoformat() if last_sync else None,
    }


@router.get("/filters")
def filter_options(db: Session = Depends(get_db)):
    platforms = db.query(VirtualPlatform).order_by(VirtualPlatform.name.asc()).all()
    hosts = db.query(VirtualHost).order_by(VirtualHost.name.asc()).all()
    clusters = sorted({
        row.cluster_name.strip()
        for row in hosts
        if row.cluster_name and row.cluster_name.strip()
    }, key=str.casefold)
    guest_os = sorted({
        row.guest_os.strip()
        for row in db.query(VirtualMachine.guest_os).all()
        if row.guest_os and row.guest_os.strip()
    }, key=str.casefold)
    return {
        "platforms": [
            {"id": row.id, "name": row.name, "platform_type": row.platform_type}
            for row in platforms
        ],
        "hosts": [
            {
                "id": row.id,
                "name": row.name,
                "platform_id": row.platform_id,
                "cluster_name": row.cluster_name or "",
            }
            for row in hosts
        ],
        "clusters": clusters,
        "guest_os": guest_os,
    }


@router.get("/vms")
def list_vms(
    platform_id: Optional[int] = None,
    status: Optional[str] = None,
    host_id: Optional[int] = None,
    cluster: str = "",
    guest_os: str = "",
    min_cpu: Optional[float] = Query(None, ge=0, le=100),
    min_memory: Optional[float] = Query(None, ge=0, le=100),
    min_disk: Optional[float] = Query(None, ge=0, le=100),
    min_vcpu: Optional[int] = Query(None, ge=1),
    min_memory_mb: Optional[float] = Query(None, ge=0),
    min_disk_gb: Optional[float] = Query(None, ge=0),
    keyword: str = "",
    sort_by: str = "name",
    sort_order: str = "asc",
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=200),
    db: Session = Depends(get_db),
):
    if sort_by == "ip_address":
        virtualization_service.backfill_primary_ips(db)
    query = db.query(VirtualMachine)
    if platform_id:
        query = query.filter(VirtualMachine.platform_id == platform_id)
    if status and status in POWER_STATES:
        query = query.filter(VirtualMachine.power_state == status)
    if host_id:
        query = query.filter(VirtualMachine.host_id == host_id)
    if cluster.strip():
        query = query.join(VirtualHost, VirtualMachine.host_id == VirtualHost.id).filter(
            VirtualHost.cluster_name == cluster.strip()
        )
    if guest_os.strip():
        query = query.filter(VirtualMachine.guest_os == guest_os.strip())
    if min_cpu is not None:
        query = query.filter(VirtualMachine.cpu_usage >= min_cpu)
    if min_memory is not None:
        query = query.filter(VirtualMachine.memory_usage >= min_memory)
    if min_disk is not None:
        query = query.filter(VirtualMachine.disk_usage >= min_disk)
    if min_vcpu is not None:
        query = query.filter(VirtualMachine.vcpu >= min_vcpu)
    if min_memory_mb is not None:
        query = query.filter(VirtualMachine.memory_mb >= min_memory_mb)
    if min_disk_gb is not None:
        query = query.filter(VirtualMachine.disk_total_gb >= min_disk_gb)
    if keyword.strip():
        like = f"%{keyword.strip()}%"
        query = query.filter(or_(
            VirtualMachine.name.ilike(like),
            VirtualMachine.guest_os.ilike(like),
        ))
    total = query.count()
    query = _order_by(query, VM_SORT_FIELDS, sort_by, sort_order, VirtualMachine.id)
    rows = (
        query.offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_vm_dict(row) for row in rows],
    }


@router.get("/vms/{vm_id}")
def get_vm(vm_id: int, db: Session = Depends(get_db)):
    vm = db.query(VirtualMachine).filter(VirtualMachine.id == vm_id).first()
    if not vm:
        raise HTTPException(status_code=404, detail="虚拟机不存在")
    return _vm_dict(vm)


@router.get("/hosts")
def list_hosts(
    platform_id: Optional[int] = None,
    status: Optional[str] = None,
    cluster: str = "",
    min_cpu: Optional[float] = Query(None, ge=0, le=100),
    min_memory: Optional[float] = Query(None, ge=0, le=100),
    min_storage: Optional[float] = Query(None, ge=0, le=100),
    min_vm_count: Optional[int] = Query(None, ge=0),
    keyword: str = "",
    sort_by: str = "name",
    sort_order: str = "asc",
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(VirtualHost)
    if platform_id:
        query = query.filter(VirtualHost.platform_id == platform_id)
    if status and status in {"online", "offline", "unknown"}:
        query = query.filter(VirtualHost.status == status)
    if cluster.strip():
        query = query.filter(VirtualHost.cluster_name == cluster.strip())
    if min_cpu is not None:
        query = query.filter(VirtualHost.cpu_usage >= min_cpu)
    if min_memory is not None:
        query = query.filter(VirtualHost.memory_usage >= min_memory)
    if min_storage is not None:
        query = query.filter(VirtualHost.storage_usage >= min_storage)
    if min_vm_count is not None:
        query = query.filter(VirtualHost.vm_count >= min_vm_count)
    if keyword.strip():
        like = f"%{keyword.strip()}%"
        query = query.filter(or_(
            VirtualHost.name.ilike(like),
            VirtualHost.ip_address.ilike(like),
            VirtualHost.cluster_name.ilike(like),
        ))
    total = query.count()
    query = _order_by(query, HOST_SORT_FIELDS, sort_by, sort_order, VirtualHost.id)
    rows = (
        query.offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "items": [_host_dict(row) for row in rows],
    }


@router.get("/hosts/{host_id}")
def get_host(host_id: int, db: Session = Depends(get_db)):
    host = db.query(VirtualHost).filter(VirtualHost.id == host_id).first()
    if not host:
        raise HTTPException(status_code=404, detail="宿主机不存在")
    vms = db.query(VirtualMachine).filter(VirtualMachine.host_id == host.id).all()
    data = _host_dict(host)
    data["vms"] = [_vm_dict(vm) for vm in vms]
    return data


@router.get("/top")
def top_vms(
    metric: str = "cpu_usage",
    limit: int = Query(10, ge=1, le=50),
    platform_id: Optional[int] = None,
    target: str = Query("vm", pattern="^(vm|host)$"),
    db: Session = Depends(get_db),
):
    if metric not in TOP_METRICS:
        raise HTTPException(status_code=400, detail="不支持的排行指标")
    if target == "host":
        # 宿主机使用 storage_usage 表示“硬盘/存储使用率”
        host_metric = "storage_usage" if metric == "disk_usage" else metric
        column = getattr(VirtualHost, host_metric)
        query = db.query(VirtualHost).filter(
            VirtualHost.status == "online",
            column.isnot(None),
        )
        if platform_id:
            query = query.filter(VirtualHost.platform_id == platform_id)
        rows = query.order_by(column.desc()).limit(limit).all()
        return {
            "metric": metric,
            "target": "host",
            "items": [
                {
                    "id": row.id,
                    "name": row.name,
                    "value": getattr(row, host_metric),
                    "platform_name": row.platform.name if row.platform else "",
                    "host_name": row.cluster_name or row.ip_address or "",
                    "power_state": row.status,
                }
                for row in rows
            ],
        }
    column = getattr(VirtualMachine, metric)
    query = db.query(VirtualMachine).filter(
        VirtualMachine.power_state == "running",
        column.isnot(None),
    )
    if platform_id:
        query = query.filter(VirtualMachine.platform_id == platform_id)
    rows = query.order_by(column.desc()).limit(limit).all()
    return {
        "metric": metric,
        "target": "vm",
        "items": [
            {
                "id": row.id,
                "name": row.name,
                "value": getattr(row, metric),
                "platform_name": row.platform.name if row.platform else "",
                "host_name": row.host.name if row.host else "",
                "power_state": row.power_state,
            }
            for row in rows
        ],
    }
