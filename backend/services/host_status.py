"""跨平台主机运行状态：CPU、内存、磁盘、网卡、服务与系统信息。

Windows / Linux 均通过 psutil 读取，不依赖系统命令。
"""
from __future__ import annotations

import os
import platform
import socket
import sys
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    import psutil
except Exception:  # pragma: no cover - 依赖缺失时给出可读错误
    psutil = None

_NET_LOCK = threading.Lock()
_LAST_NET: Dict[str, Any] = {"at": 0.0, "counters": {}}


def _collect_disks() -> List[Dict[str, Any]]:
    disks: List[Dict[str, Any]] = []
    seen = set()
    for part in psutil.disk_partitions(all=False):
        mountpoint = part.mountpoint
        if not mountpoint or mountpoint in seen:
            continue
        # Linux 的 squashfs/snap 等只读伪分区不纳入容量统计
        if part.fstype.lower() in {"squashfs", "iso9660", "udf", "devtmpfs", "tmpfs", "overlay"}:
            continue
        try:
            usage = psutil.disk_usage(mountpoint)
        except (PermissionError, OSError):
            continue
        if not usage.total:
            continue
        seen.add(mountpoint)
        disks.append({
            "mountpoint": mountpoint,
            "device": part.device,
            "fstype": part.fstype,
            "total": usage.total,
            "used": usage.used,
            "free": usage.free,
            "percent": usage.percent,
        })
    disks.sort(key=lambda item: (item["mountpoint"].lower() not in ("/", "c:\\"), item["mountpoint"].lower()))
    return disks[:20]


def _collect_network() -> List[Dict[str, Any]]:
    try:
        stats = psutil.net_if_stats()
        addresses = psutil.net_if_addrs()
        counters = psutil.net_io_counters(pernic=True)
    except Exception:
        return []
    now = time.monotonic()
    with _NET_LOCK:
        previous_at = float(_LAST_NET.get("at") or 0)
        previous = dict(_LAST_NET.get("counters") or {})
        _LAST_NET["at"] = now
        _LAST_NET["counters"] = {name: {"sent": item.bytes_sent, "recv": item.bytes_recv} for name, item in counters.items()}
    elapsed = max(0.001, now - previous_at) if previous_at else 0
    result: List[Dict[str, Any]] = []
    for name, stat in stats.items():
        io = counters.get(name)
        ips, macs = [], []
        for addr in addresses.get(name, []):
            family = getattr(addr, "family", None)
            if family == socket.AF_INET:
                ips.append(addr.address)
            elif family == socket.AF_INET6:
                ips.append(addr.address.split("%")[0])
            elif family == getattr(psutil, "AF_LINK", object()):
                macs.append((addr.address or "").lower())
        old = previous.get(name) or {}
        rx_rate = tx_rate = 0
        if elapsed and old and io:
            rx_rate = max(0, io.bytes_recv - old.get("recv", io.bytes_recv)) / elapsed
            tx_rate = max(0, io.bytes_sent - old.get("sent", io.bytes_sent)) / elapsed
        result.append({
            "name": name,
            "is_up": bool(stat.isup),
            "speed_mbps": stat.speed or 0,
            "mtu": stat.mtu,
            "mac": macs[0] if macs else "",
            "ips": ips,
            "bytes_sent": io.bytes_sent if io else 0,
            "bytes_recv": io.bytes_recv if io else 0,
            "packets_sent": io.packets_sent if io else 0,
            "packets_recv": io.packets_recv if io else 0,
            "errors_in": io.errin if io else 0,
            "errors_out": io.errout if io else 0,
            "drops_in": io.dropin if io else 0,
            "drops_out": io.dropout if io else 0,
            "rx_bytes_per_second": round(rx_rate, 1),
            "tx_bytes_per_second": round(tx_rate, 1),
        })
    result.sort(key=lambda item: (not item["is_up"], not item["ips"], item["name"].lower()))
    return result[:40]


def _check_port(port: int) -> bool:
    """本机连通性探测；用于 psutil 无权限读取连接表时的兜底。"""
    for host in ("127.0.0.1", "::1"):
        try:
            with socket.create_connection((host, int(port)), timeout=0.35):
                return True
        except OSError:
            continue
    return False


def collect_port_status(expected: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    """监听端口与关键端口状态。

    expected: [{port, service, critical, protocol}]。先返回关键端口（即使未监听），
    再补充系统当前其他监听端口；无 psutil 权限时仍会对关键端口做本机 socket 探测。
    """
    expected_rows = []
    seen = set()
    for item in expected or []:
        try:
            port = int(item.get("port") or 0)
        except (TypeError, ValueError):
            continue
        if not 1 <= port <= 65535 or port in seen:
            continue
        seen.add(port)
        expected_rows.append({
            "port": port,
            "service": str(item.get("service") or "关键端口"),
            "protocol": str(item.get("protocol") or "TCP").upper(),
            "critical": bool(item.get("critical", False)),
            "scope": str(item.get("scope") or "external"),
        })

    listener_map: Dict[int, List[Dict[str, Any]]] = {}
    psutil_error = ""
    if psutil is not None:
        try:
            connections = psutil.net_connections(kind="inet")
        except (psutil.AccessDenied, PermissionError, OSError) as exc:  # type: ignore[attr-defined]
            connections = []
            psutil_error = f"无法读取系统连接表（{exc}），关键端口使用本机探测"
        process_cache: Dict[int, str] = {}
        for conn in connections:
            if getattr(conn, "status", None) != psutil.CONN_LISTEN:
                continue
            laddr = getattr(conn, "laddr", None)
            port = int(getattr(laddr, "port", 0) or 0)
            if not port:
                continue
            address = str(getattr(laddr, "ip", "") or "")
            pid = getattr(conn, "pid", None)
            process = ""
            if pid:
                if pid not in process_cache:
                    try:
                        process_cache[pid] = psutil.Process(pid).name()
                    except (psutil.Error, OSError):
                        process_cache[pid] = ""
                process = process_cache.get(pid, "")
            listener_map.setdefault(port, []).append({
                "address": address,
                "pid": pid,
                "process": process,
            })

    def make_row(port: int, service: str, protocol: str, expected_flag: bool, critical: bool = False, scope: str = "external") -> Dict[str, Any]:
        binds = listener_map.get(port, [])
        addresses = sorted({item["address"] for item in binds if item.get("address")})
        pids = sorted({item["pid"] for item in binds if item.get("pid")})
        processes = sorted({item["process"] for item in binds if item.get("process")})
        open_ok = bool(binds) or _check_port(port)
        bind_all = any(address in ("0.0.0.0", "::", "*") for address in addresses)
        return {
            "port": port,
            "service": service,
            "protocol": protocol,
            "expected": expected_flag,
            "critical": critical,
            "scope": scope,
            "listening": open_ok,
            "bind_all": bind_all,
            "addresses": addresses,
            "pid": pids[0] if pids else None,
            "pids": pids,
            "process": " / ".join(processes[:3]),
            "status": "running" if open_ok else "stopped",
        }

    rows = [
        make_row(item["port"], item["service"], item["protocol"], True, item["critical"], item.get("scope", "external"))
        for item in expected_rows
    ]
    for port in sorted(listener_map):
        if port in seen:
            continue
        binds = listener_map[port]
        rows.append({
            "port": port,
            "service": "其他监听端口",
            "protocol": "TCP",
            "expected": False,
            "critical": False,
            "scope": "system",
            "listening": True,
            "bind_all": any(item.get("address") in ("0.0.0.0", "::", "*") for item in binds),
            "addresses": sorted({item["address"] for item in binds if item.get("address")}),
            "pid": next((item["pid"] for item in binds if item.get("pid")), None),
            "pids": sorted({item["pid"] for item in binds if item.get("pid")}),
            "process": " / ".join(sorted({item["process"] for item in binds if item.get("process")})[:3]),
            "status": "running",
        })
    return {
        "available": psutil is not None or bool(expected_rows),
        "psutil_error": psutil_error,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "total": len(rows),
        "listening": sum(1 for row in rows if row["listening"]),
        "expected": sum(1 for row in rows if row["expected"]),
        "items": rows,
    }


def collect_host_status(
    db=None,
    *,
    collector_running: bool = False,
    scheduler_running: bool = False,
    background_tasks: bool = True,
    systemd_watchdog: bool = False,
    start_time: Optional[float] = None,
) -> Dict[str, Any]:
    if psutil is None:
        raise RuntimeError("psutil 未安装，无法读取主机状态")

    cpu_percent = psutil.cpu_percent(interval=0.15)
    cpu_count = psutil.cpu_count(logical=True) or 0
    cpu_physical = psutil.cpu_count(logical=False) or 0
    try:
        freq = psutil.cpu_freq()
        cpu_freq = round(freq.current, 1) if freq and freq.current else 0
    except Exception:
        cpu_freq = 0
    try:
        load_avg = [round(item, 2) for item in os.getloadavg()]
    except (AttributeError, OSError):
        load_avg = []

    memory = psutil.virtual_memory()
    swap = psutil.swap_memory()
    boot_time = psutil.boot_time()
    process = psutil.Process(os.getpid())
    process_memory = process.memory_info()

    db_status = {"status": "unknown", "type": "", "latency_ms": 0}
    if db is not None:
        started = time.perf_counter()
        try:
            from sqlalchemy import text
            db.execute(text("SELECT 1"))
            db_status = {
                "status": "connected",
                "type": db.get_bind().dialect.name if db.get_bind() is not None else "",
                "latency_ms": round((time.perf_counter() - started) * 1000, 2),
            }
        except Exception as exc:  # noqa: BLE001
            db_status = {"status": "error", "type": "", "latency_ms": 0, "error": str(exc)[:200]}
    uptime = max(0, int(time.time() - boot_time))
    app_uptime = max(0, int(time.time() - start_time)) if start_time else 0

    services = [
        {"key": "api", "name": "Web / API 服务", "status": "running", "detail": f"PID {os.getpid()} · 已运行 {app_uptime} 秒"},
        {
            "key": "database", "name": "数据库",
            "status": "running" if db_status["status"] == "connected" else "error",
            "detail": f"{db_status.get('type') or '未知'} · {db_status['latency_ms']}ms",
        },
        {
            "key": "collector", "name": "SNMP 采集器",
            "status": "running" if collector_running else "stopped",
            "detail": "后台采集任务" if background_tasks else "当前实例为无状态从节点",
        },
        {
            "key": "website_scheduler", "name": "网站监控调度器",
            "status": "running" if scheduler_running else "stopped",
            "detail": "周期探测网站/端口/ICMP",
        },
        {
            "key": "background", "name": "后台任务框架",
            "status": "running" if background_tasks else "disabled",
            "detail": "采集、调度、备份、清理" if background_tasks else "RUN_BACKGROUND_TASKS=0",
        },
        {
            "key": "watchdog", "name": "systemd Watchdog",
            "status": "running" if systemd_watchdog else "disabled",
            "detail": "systemd 看门狗已启用" if systemd_watchdog else "未启用或非 systemd 部署",
        },
    ]

    return {
        "host": {
            "hostname": socket.gethostname(),
            "platform": platform.system(),
            "platform_release": platform.release(),
            "platform_version": platform.version(),
            "architecture": platform.machine(),
            "python": sys.version.split()[0],
            "boot_time": datetime.fromtimestamp(boot_time).isoformat(timespec="seconds"),
            "uptime_seconds": uptime,
            "app_uptime_seconds": app_uptime,
        },
        "cpu": {
            "percent": round(cpu_percent, 1),
            "logical": cpu_count,
            "physical": cpu_physical,
            "frequency_mhz": cpu_freq,
            "load_average": load_avg,
            "process_percent": round(process.cpu_percent(interval=None), 1),
        },
        "memory": {
            "total": memory.total,
            "used": memory.used,
            "available": memory.available,
            "percent": memory.percent,
            "swap_total": swap.total,
            "swap_used": swap.used,
            "swap_percent": swap.percent,
        },
        "process": {
            "pid": os.getpid(),
            "rss": process_memory.rss,
            "vms": process_memory.vms,
        },
        "disks": _collect_disks(),
        "network": _collect_network(),
        "services": services,
        "database": db_status,
        "collected_at": datetime.now().isoformat(timespec="seconds"),
    }
