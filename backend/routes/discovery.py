"""设备自动发现：SNMP 网段扫描 + IP 存活探测"""
import asyncio
import ipaddress
import locale
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..models.discovery import DiscoverySchedule
from ..models.models import Device
from ..services import audit, license_manager
from ..services.cache import invalidate_all
from ..services.discovery_scheduler import (
    get_or_create_schedule,
    get_schedule,
    list_schedules,
    run_schedule_now,
    schedule_to_dict,
)
from ..snmp.snmp_client import SNMPClient, SNMPError

router = APIRouter(prefix="/api/discovery", tags=["设备自动发现"])
MAX_SNMP_HOSTS = 512
MAX_PING_HOSTS = 1024
MAX_CONCURRENCY = 128

VENDOR_HINTS = [
    ("cisco", "Cisco"), ("huawei", "Huawei"), ("h3c", "H3C"),
    ("fortinet", "Fortinet"), ("fortigate", "Fortinet"), ("ruijie", "Ruijie"),
    ("juniper", "Juniper"), ("hpe", "HPE"), ("aruba", "Aruba"),
    ("tp-link", "TP-Link"), ("sangfor", "Sangfor"), ("topsec", "Topsec"),
    ("hillstone", "Hillstone"), ("palo alto", "Palo Alto"),
    ("dell", "Dell"), ("lenovo", "Lenovo"), ("inspur", "Inspur"),
    ("microsoft", "Microsoft"), ("linux", "Linux"),
]


class SnmpCredentials(BaseModel):
    version: str = "v2c"
    community: str = "public"
    port: int = Field(161, ge=1, le=65535)
    timeout: int = Field(2, ge=1, le=10)
    concurrency: int = Field(32, ge=1, le=MAX_CONCURRENCY)
    v3_username: Optional[str] = None
    v3_security_level: str = "authPriv"
    v3_auth_protocol: str = "SHA"
    v3_auth_password: Optional[str] = None
    v3_priv_protocol: str = "AES"
    v3_priv_password: Optional[str] = None
    v3_context_name: Optional[str] = None


class SnmpScanRequest(SnmpCredentials):
    target: str
    name: str = ""
    auto_add: bool = True


class SnmpAddRequest(SnmpCredentials):
    ips: List[str]


class PingScanRequest(BaseModel):
    target: str
    timeout: int = Field(1, ge=1, le=5)
    concurrency: int = Field(64, ge=1, le=MAX_CONCURRENCY)


class DiscoverySchedulePayload(SnmpCredentials):
    name: str = "定时扫描"
    enabled: bool = False
    target: str = ""
    interval_minutes: int = Field(60, ge=5, le=1440)
    auto_add: bool = True
    communities: List[str] = Field(default_factory=list)


def _require_superuser(request: Request) -> None:
    if not getattr(request.state, "is_superuser", False):
        raise HTTPException(status_code=403, detail="只有超级管理员可以配置定时自动发现")


def _expand_targets(target: str, max_hosts: int) -> List[str]:
    """展开 CIDR、起止 IP、简写末段和逗号分隔的 IP 列表。"""
    raw = (target or "").strip()
    if not raw:
        raise HTTPException(status_code=400, detail="请输入扫描范围")
    hosts: List[str] = []
    seen = set()

    def add(ip: str):
        if ip not in seen:
            seen.add(ip)
            hosts.append(ip)

    for token in re.split(r"[\s,;]+", raw):
        if not token:
            continue
        try:
            if "/" in token:
                network = ipaddress.ip_network(token, strict=False)
                for ip in network.hosts():
                    add(str(ip))
                    if len(hosts) > max_hosts:
                        raise HTTPException(status_code=400, detail=f"扫描范围过大，单次最多 {max_hosts} 个地址")
                continue
            if "-" in token:
                left, right = token.split("-", 1)
                start = ipaddress.ip_address(left)
                if "." not in right:
                    right = f"{left.rsplit('.', 1)[0]}.{right}"
                end = ipaddress.ip_address(right)
                if start.version != end.version or int(end) < int(start):
                    raise ValueError("IP 范围不合法")
                current = start
                while int(current) <= int(end):
                    add(str(current))
                    if len(hosts) > max_hosts:
                        raise HTTPException(status_code=400, detail=f"扫描范围过大，单次最多 {max_hosts} 个地址")
                    current = ipaddress.ip_address(int(current) + 1)
                continue
            add(str(ipaddress.ip_address(token)))
        except HTTPException:
            raise
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无法识别地址：{token}") from None
    if not hosts:
        raise HTTPException(status_code=400, detail="扫描范围为空")
    return hosts


def _snmp_client(ip: str, payload: SnmpCredentials) -> SNMPClient:
    return SNMPClient(
        host=ip,
        community=payload.community,
        version=payload.version,
        port=payload.port,
        timeout=payload.timeout,
        retries=1,
        v3_username=payload.v3_username,
        v3_security_level=payload.v3_security_level,
        v3_auth_protocol=payload.v3_auth_protocol,
        v3_auth_password=payload.v3_auth_password,
        v3_priv_protocol=payload.v3_priv_protocol,
        v3_priv_password=payload.v3_priv_password,
        v3_context_name=payload.v3_context_name,
    )


def _guess_vendor(text: str) -> str:
    lower = (text or "").lower()
    for hint, name in VENDOR_HINTS:
        if hint in lower:
            return name
    return ""


def _guess_type(text: str) -> str:
    lower = (text or "").lower()
    if any(word in lower for word in ("firewall", "fortigate", "fortinet", "palo alto", "sangfor", "topsec", "hillstone")):
        return "firewall"
    if any(word in lower for word in ("router", "routeros", "juniper", "mx", "router")):
        return "router"
    if any(word in lower for word in ("switch", "catalyst", "nexus", "switch")):
        return "switch"
    if any(word in lower for word in ("server", "linux", "windows", "vmware", "esxi")):
        return "server"
    if any(word in lower for word in ("security", "ids", "ips")):
        return "security"
    return "other"


async def _probe_snmp(ip: str, payload: SnmpCredentials, sem: asyncio.Semaphore) -> Optional[Dict[str, Any]]:
    async with sem:
        started = time.perf_counter()
        try:
            info = await _snmp_client(ip, payload).get_system_info()
        except (SNMPError, asyncio.TimeoutError, OSError):
            return None
        except Exception:  # noqa: BLE001 - 单点失败不影响整体扫描
            return None
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        sysdescr = str(info.get("sysdescr") or "").strip()
        sysname = str(info.get("sysname") or "").strip()
        if not sysdescr and not sysname:
            return None
        vendor = _guess_vendor(f"{sysdescr} {sysname}")
        return {
            "ip_address": ip,
            "name": sysname or ip,
            "sys_name": sysname,
            "sys_descr": sysdescr,
            "location": str(info.get("syslocation") or "").strip(),
            "vendor": vendor,
            "model": "",
            "device_type": _guess_type(sysdescr),
            "latency_ms": elapsed,
        }


def _create_device(db: Session, item: Dict[str, Any], payload: SnmpCredentials, added_by: str = "") -> Optional[int]:
    existing = db.query(Device).filter(Device.ip_address == item["ip_address"]).first()
    if existing:
        return existing.id
    license_manager.check_asset_capacity(db)
    device = Device(
        name=(item.get("name") or item["ip_address"])[:255],
        ip_address=item["ip_address"],
        device_type=item.get("device_type") or "other",
        snmp_version=payload.version,
        community=payload.community,
        port=payload.port,
        v3_username=payload.v3_username,
        v3_security_level=payload.v3_security_level,
        v3_auth_protocol=payload.v3_auth_protocol,
        v3_auth_password=payload.v3_auth_password,
        v3_priv_protocol=payload.v3_priv_protocol,
        v3_priv_password=payload.v3_priv_password,
        v3_context_name=payload.v3_context_name,
        location=item.get("location") or "",
        vendor=item.get("vendor") or "",
        model=item.get("model") or "",
        description=(item.get("sys_descr") or "")[:2000],
        is_enabled=True,
        tags=["自动发现"],
        custom_oids={},
        custom_metrics=[],
        server_sensors=[],
        source="auto",
        discovered_at=datetime.utcnow(),
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(device)
    db.flush()
    return device.id


def _normalize_communities(values: Any, fallback: str = "") -> List[str]:
    """去空、去重并限制单次最多 10 个团体名。"""
    result: List[str] = []
    raw = values if isinstance(values, list) else []
    if not raw and fallback:
        raw = [fallback]
    for value in raw:
        text = str(value or "").strip()
        if text and text not in result:
            result.append(text)
    return result[:10]


async def scan_snmp_communities(
    payload: SnmpCredentials,
    communities: List[str],
    db: Session,
) -> Dict[str, Any]:
    """多团体名 SNMP 扫描：同一轮内按团体名依次尝试，每个 IP 只入库一次。

    探测成功的设备使用实际可用的团体名保存；已存在 IP 直接跳过。
    """
    targets = _expand_targets(getattr(payload, "target", ""), MAX_SNMP_HOSTS)
    community_list = _normalize_communities(communities, payload.community)
    sem = asyncio.Semaphore(min(payload.concurrency, MAX_CONCURRENCY))
    started = time.perf_counter()

    hits: Dict[str, Dict[str, Any]] = {}
    remaining = list(targets)
    for community in community_list:
        if not remaining:
            break
        credential = payload.model_copy(update={"community": community})
        probed = await asyncio.gather(*[_probe_snmp(ip, credential, sem) for ip in remaining])
        next_remaining = []
        for ip, item in zip(remaining, probed):
            if item:
                hits[ip] = {"item": item, "community": community}
            else:
                next_remaining.append(ip)
        remaining = next_remaining

    items = [hits[ip]["item"] for ip in targets if ip in hits]
    existing_ips = (
        {row[0] for row in db.query(Device.ip_address).filter(Device.ip_address.in_(list(hits))).all()}
        if hits else set()
    )
    for item in items:
        item["exists"] = item["ip_address"] in existing_ips
        item["added"] = False

    added = 0
    for item in items:
        if item["exists"]:
            continue
        try:
            hit = hits[item["ip_address"]]
            credential = payload.model_copy(update={"community": hit["community"]})
            device_id = _create_device(db, item, credential)
            db.commit()
            item["added"] = device_id is not None
            item["device_id"] = device_id
            item["exists"] = item["added"]
            if item["added"]:
                added += 1
        except Exception:  # noqa: BLE001
            db.rollback()
    if added:
        invalidate_all()

    return {
        "items": items,
        "total": len(targets),
        "discovered": len(items),
        "added": added,
        "duration_seconds": round(time.perf_counter() - started, 2),
        "target": getattr(payload, "target", ""),
        "name": getattr(payload, "name", ""),
        "communities_tried": len(community_list),
    }


def _validate_schedule_payload(
    db: Session,
    payload: DiscoverySchedulePayload,
    exclude_id: Optional[int] = None,
):
    name = str(payload.name or "").strip() or "定时扫描"
    if len(name) > 100:
        raise HTTPException(status_code=400, detail="任务名称不能超过 100 个字符")
    duplicate = db.query(DiscoverySchedule).filter(
        func.lower(DiscoverySchedule.name) == name.lower()
    )
    if exclude_id:
        duplicate = duplicate.filter(DiscoverySchedule.id != exclude_id)
    if duplicate.first():
        raise HTTPException(status_code=400, detail="定时任务名称已存在")
    target = str(payload.target or "").strip()
    if payload.enabled and not target:
        raise HTTPException(status_code=400, detail="启用定时扫描前请填写扫描范围")
    if target:
        _expand_targets(target, MAX_SNMP_HOSTS)
    communities = _normalize_communities(payload.communities, payload.community)
    if len([str(item).strip() for item in (payload.communities or []) if str(item).strip()]) > 10:
        raise HTTPException(status_code=400, detail="每个定时任务最多配置 10 个团体名")
    if payload.version != "v3" and not communities:
        raise HTTPException(status_code=400, detail="请至少填写一个 SNMP 团体名")
    return name, target, communities


def _apply_schedule_payload(
    schedule: DiscoverySchedule,
    payload: DiscoverySchedulePayload,
    name: str,
    target: str,
    communities: List[str],
) -> None:
    schedule.name = name
    schedule.enabled = bool(payload.enabled)
    schedule.target = target
    schedule.version = payload.version
    schedule.community = communities[0] if communities else payload.community
    schedule.communities = communities if payload.version != "v3" else []
    schedule.port = payload.port
    schedule.timeout = payload.timeout
    schedule.concurrency = payload.concurrency
    schedule.v3_username = payload.v3_username or None
    schedule.v3_security_level = payload.v3_security_level
    schedule.v3_auth_protocol = payload.v3_auth_protocol
    schedule.v3_auth_password = payload.v3_auth_password or None
    schedule.v3_priv_protocol = payload.v3_priv_protocol
    schedule.v3_priv_password = payload.v3_priv_password or None
    schedule.v3_context_name = payload.v3_context_name or None
    schedule.interval_minutes = payload.interval_minutes
    schedule.auto_add = bool(payload.auto_add)
    schedule.updated_at = datetime.utcnow()


@router.get("/schedules")
def list_discovery_schedules(request: Request, db: Session = Depends(get_db)):
    """定时扫描任务列表。仅超级管理员可访问。"""
    _require_superuser(request)
    schedules = list_schedules(db)
    return {
        "total": len(schedules),
        "items": [schedule_to_dict(item) for item in schedules],
    }


@router.post("/schedules")
def create_discovery_schedule(
    payload: DiscoverySchedulePayload,
    request: Request,
    db: Session = Depends(get_db),
):
    """新建定时扫描任务。"""
    _require_superuser(request)
    if db.query(DiscoverySchedule).count() >= 50:
        raise HTTPException(status_code=400, detail="定时扫描任务最多 50 个")
    name, target, communities = _validate_schedule_payload(db, payload)
    schedule = DiscoverySchedule(name=name)
    _apply_schedule_payload(schedule, payload, name, target, communities)
    db.add(schedule)
    audit.record(
        db, request, module="assets", action="create",
        target_type="discovery_schedule", target_name=name,
        after={
            "name": name, "enabled": schedule.enabled, "target": target,
            "interval_minutes": schedule.interval_minutes,
            "version": schedule.version, "community_count": len(communities),
            "auto_add": schedule.auto_add,
        },
        message=f"新建定时扫描任务 {name}",
    )
    db.commit()
    db.refresh(schedule)
    return schedule_to_dict(schedule)


@router.put("/schedules/{schedule_id}")
def update_discovery_schedule(
    schedule_id: int,
    payload: DiscoverySchedulePayload,
    request: Request,
    db: Session = Depends(get_db),
):
    """修改指定定时扫描任务。"""
    _require_superuser(request)
    schedule = get_schedule(db, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="定时扫描任务不存在")
    name, target, communities = _validate_schedule_payload(db, payload, exclude_id=schedule.id)
    _apply_schedule_payload(schedule, payload, name, target, communities)
    audit.record(
        db, request, module="assets", action="update",
        target_type="discovery_schedule", target_id=schedule.id, target_name=name,
        after={
            "name": name, "enabled": schedule.enabled, "target": target,
            "interval_minutes": schedule.interval_minutes,
            "version": schedule.version, "community_count": len(communities),
            "auto_add": schedule.auto_add,
        },
        message=f"修改定时扫描任务 {name}",
    )
    db.commit()
    db.refresh(schedule)
    return schedule_to_dict(schedule)


@router.delete("/schedules/{schedule_id}")
def delete_discovery_schedule(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """删除指定定时扫描任务。"""
    _require_superuser(request)
    schedule = get_schedule(db, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="定时扫描任务不存在")
    name = schedule.name or f"#{schedule.id}"
    audit.record(
        db, request, module="assets", action="delete",
        target_type="discovery_schedule", target_id=schedule.id, target_name=name,
        message=f"删除定时扫描任务 {name}",
    )
    db.delete(schedule)
    db.commit()
    return {"message": f"定时扫描任务「{name}」已删除"}


@router.post("/schedules/{schedule_id}/run")
async def run_discovery_schedule(
    schedule_id: int,
    request: Request,
    db: Session = Depends(get_db),
):
    """立即执行指定定时扫描任务。"""
    _require_superuser(request)
    schedule = get_schedule(db, schedule_id)
    if not schedule:
        raise HTTPException(status_code=404, detail="定时扫描任务不存在")
    result = await run_schedule_now(db, schedule, force=True)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message") or "执行自动发现失败")
    return result


# ---- 兼容旧版单任务接口 ----
@router.get("/schedule")
def get_discovery_schedule(request: Request, db: Session = Depends(get_db)):
    _require_superuser(request)
    return schedule_to_dict(get_or_create_schedule(db))


@router.put("/schedule")
def update_legacy_discovery_schedule(
    payload: DiscoverySchedulePayload,
    request: Request,
    db: Session = Depends(get_db),
):
    _require_superuser(request)
    schedule = get_or_create_schedule(db)
    name, target, communities = _validate_schedule_payload(db, payload, exclude_id=schedule.id)
    _apply_schedule_payload(schedule, payload, name, target, communities)
    audit.record(
        db, request, module="assets", action="update",
        target_type="discovery_schedule", target_id=schedule.id, target_name=name,
        message=f"修改定时扫描任务 {name}（兼容接口）",
    )
    db.commit()
    db.refresh(schedule)
    return schedule_to_dict(schedule)


@router.post("/schedule/run")
async def run_legacy_discovery_schedule(request: Request, db: Session = Depends(get_db)):
    _require_superuser(request)
    schedule = get_or_create_schedule(db)
    result = await run_schedule_now(db, schedule, force=True)
    if not result.get("ok"):
        raise HTTPException(status_code=400, detail=result.get("message") or "执行自动发现失败")
    return result


@router.post("/snmp/scan")
async def snmp_scan(payload: SnmpScanRequest, request: Request, db: Session = Depends(get_db)):
    targets = _expand_targets(payload.target, MAX_SNMP_HOSTS)
    sem = asyncio.Semaphore(min(payload.concurrency, MAX_CONCURRENCY))
    started = time.perf_counter()
    probed = await asyncio.gather(*[_probe_snmp(ip, payload, sem) for ip in targets])
    items = [item for item in probed if item]
    existing_ips = {row[0] for row in db.query(Device.ip_address).filter(Device.ip_address.in_([i["ip_address"] for i in items])).all()} if items else set()

    added = 0
    for item in items:
        item["exists"] = item["ip_address"] in existing_ips
        item["added"] = False
    if payload.auto_add:
        for item in items:
            if item["exists"]:
                continue
            try:
                device_id = _create_device(db, item, payload)
                db.commit()
                item["added"] = device_id is not None
                item["device_id"] = device_id
                item["exists"] = item["added"]
                added += 1
            except Exception:  # noqa: BLE001
                db.rollback()
        invalidate_all()

    duration = round(time.perf_counter() - started, 2)
    return {
        "items": items,
        "total": len(targets),
        "discovered": len(items),
        "added": added,
        "duration_seconds": duration,
        "target": payload.target,
        "name": payload.name,
    }


@router.post("/snmp/add")
async def snmp_add(payload: SnmpAddRequest, request: Request, db: Session = Depends(get_db)):
    ips: List[str] = []
    for value in payload.ips:
        try:
            ips.append(str(ipaddress.ip_address(value)))
        except ValueError:
            continue
    if not ips:
        raise HTTPException(status_code=400, detail="没有可添加的设备")
    sem = asyncio.Semaphore(min(payload.concurrency, MAX_CONCURRENCY))
    probed = await asyncio.gather(*[_probe_snmp(ip, payload, sem) for ip in ips])
    added: List[Dict[str, Any]] = []
    exists: List[str] = []
    failed: List[str] = []
    for ip, item in zip(ips, probed):
        if not item:
            failed.append(ip)
            continue
        existing = db.query(Device).filter(Device.ip_address == ip).first()
        if existing:
            exists.append(ip)
            continue
        try:
            device_id = _create_device(db, item, payload)
            db.commit()
            added.append({"ip_address": ip, "device_id": device_id, "name": item["name"]})
        except Exception:  # noqa: BLE001
            db.rollback()
            failed.append(ip)
    invalidate_all()
    return {"added": added, "exists": exists, "failed": failed}


async def _ping_once(ip: str, timeout: int) -> Dict[str, Any]:
    started = time.perf_counter()
    if os.name == "nt":
        cmd = ["ping", "-n", "1", "-w", str(timeout * 1000), ip]
    else:
        cmd = ["ping", "-c", "1", "-W", str(timeout), ip]
    method = "icmp"
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout + 1.5)
        elapsed = round((time.perf_counter() - started) * 1000, 1)
        if proc.returncode == 0:
            text = stdout.decode(locale.getpreferredencoding(False) or "utf-8", errors="ignore")
            match = re.search(r"(?:time|时间|tiempo|temps)\s*[=<]\s*([\d.]+)\s*ms", text, re.I)
            latency = round(float(match.group(1)), 1) if match else elapsed
            return {"alive": True, "latency_ms": latency, "method": method}
        return {"alive": False, "latency_ms": None, "method": method}
    except FileNotFoundError:
        method = "tcp"
    except Exception:  # noqa: BLE001
        return {"alive": False, "latency_ms": None, "method": method}
    # 没有 ping 命令时回退到常见 TCP 端口探测
    for port in (22, 80, 443, 161):
        try:
            _, writer = await asyncio.wait_for(asyncio.open_connection(ip, port), timeout=timeout)
            writer.close()
            await writer.wait_closed()
            return {"alive": True, "latency_ms": round((time.perf_counter() - started) * 1000, 1), "method": method}
        except Exception:  # noqa: BLE001
            continue
    return {"alive": False, "latency_ms": None, "method": method}


@router.post("/ping/scan")
async def ping_scan(payload: PingScanRequest):
    targets = _expand_targets(payload.target, MAX_PING_HOSTS)
    sem = asyncio.Semaphore(min(payload.concurrency, MAX_CONCURRENCY))
    started = time.perf_counter()

    async def probe(ip: str):
        async with sem:
            result = await _ping_once(ip, payload.timeout)
            return {"ip_address": ip, **result}

    items = await asyncio.gather(*[probe(ip) for ip in targets])
    alive = sum(1 for item in items if item["alive"])
    return {
        "items": items,
        "total": len(targets),
        "alive": alive,
        "offline": len(targets) - alive,
        "duration_seconds": round(time.perf_counter() - started, 2),
        "target": payload.target,
    }
