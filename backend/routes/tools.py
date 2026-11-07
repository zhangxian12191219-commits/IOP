"""系统工具：SNMP Walk / Ping / Tracert / SSH 终端 / SFTP 文件传输"""
import asyncio
import io
import ipaddress
import json
import locale
import os
import posixpath
import re
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..models.database import SessionLocal, get_db
from ..models.models import Device
from ..models.user import User
from ..services import asset_scope
from ..services import auth as auth_service
from ..services import packet_capture
from ..services import traceroute_installer
from ..snmp.snmp_client import SNMPClient, SNMPError

router = APIRouter(prefix="/api/tools", tags=["系统工具"])
HOST_RE = re.compile(r"^[a-zA-Z0-9_.:\-\[\]]+$")

# 全量 Walk / MIB 调试结果的轻量分类（按 OID 前缀，不依赖设备加载 MIB 文件）
WALK_CATEGORIES = [
    ("system", "系统信息", ("1.3.6.1.2.1.1.",)),
    ("cpu", "CPU/处理器", ("1.3.6.1.2.1.25.3.3.",)),
    ("interface", "接口/端口", ("1.3.6.1.2.1.2.", "1.3.6.1.2.1.31.")),
    ("network", "IP/网络协议", ("1.3.6.1.2.1.4.", "1.3.6.1.2.1.5.", "1.3.6.1.2.1.6.", "1.3.6.1.2.1.7.")),
    ("storage", "存储/磁盘", ("1.3.6.1.2.1.25.2.",)),
    ("sensor", "温度/传感器", ("1.3.6.1.2.1.99.",)),
    ("host", "主机资源", ("1.3.6.1.2.1.25.",)),
    ("entity", "设备实体", ("1.3.6.1.2.1.47.",)),
    ("lldp", "LLDP 邻居", ("1.0.8802.",)),
    ("vendor", "厂商私有 OID", ("1.3.6.1.4.1.",)),
    ("other", "其他", ()),
]
WALK_NAMES = sorted([
    ("1.3.6.1.2.1.1.1", "系统描述"),
    ("1.3.6.1.2.1.1.3", "系统运行时间"),
    ("1.3.6.1.2.1.1.4", "系统联系人"),
    ("1.3.6.1.2.1.1.5", "设备名称"),
    ("1.3.6.1.2.1.1.6", "设备位置"),
    ("1.3.6.1.2.1.1.7", "系统服务"),
    ("1.3.6.1.2.1.2.2.1.2", "接口描述"),
    ("1.3.6.1.2.1.2.2.1.5", "接口速率"),
    ("1.3.6.1.2.1.2.2.1.8", "接口状态"),
    ("1.3.6.1.2.1.2.2.1.10", "接口入流量"),
    ("1.3.6.1.2.1.2.2.1.16", "接口出流量"),
    ("1.3.6.1.2.1.31.1.1.1.1", "接口名称"),
    ("1.3.6.1.2.1.31.1.1.1.15", "接口高速率"),
    ("1.3.6.1.2.1.25.3.3.1.2", "CPU 使用率"),
    ("1.3.6.1.2.1.25.2.3.1.2", "存储描述"),
    ("1.3.6.1.2.1.25.2.3.1.3", "存储总量"),
    ("1.3.6.1.2.1.25.2.3.1.5", "存储已用"),
    ("1.3.6.1.2.1.99.1.1.1.4", "传感器数值"),
], key=lambda item: len(item[0]), reverse=True)


def _walk_classify(oid: str) -> tuple[str, str, str]:
    """返回 (分类 key, 分类中文名, 人类可读名称)。"""
    normalized = str(oid or "").strip()
    category_key, category_label = "other", "其他"
    for key, label, prefixes in WALK_CATEGORIES:
        if not prefixes:
            continue
        if normalized.startswith(prefixes):
            category_key, category_label = key, label
            break
    name = ""
    for prefix, label in WALK_NAMES:
        if normalized.startswith(prefix):
            name = label
            break
    return category_key, category_label, name


class SnmpWalkRequest(BaseModel):
    host: str
    oid: str = ""
    version: str = "v2c"
    community: str = "public"
    port: int = Field(161, ge=1, le=65535)
    timeout: int = Field(3, ge=1, le=10)
    max_rows: int = Field(500, ge=1, le=5000)
    v3_username: Optional[str] = None
    v3_security_level: str = "authPriv"
    v3_auth_protocol: str = "SHA"
    v3_auth_password: Optional[str] = None
    v3_priv_protocol: str = "AES"
    v3_priv_password: Optional[str] = None
    v3_context_name: Optional[str] = None


class PingRequest(BaseModel):
    host: str
    count: int = Field(4, ge=1, le=20)
    timeout: int = Field(5, ge=1, le=10)


class TracertRequest(BaseModel):
    host: str
    max_hops: int = Field(30, ge=1, le=64)
    timeout: int = Field(5, ge=1, le=10)


class SftpConfig(BaseModel):
    host: str
    port: int = Field(22, ge=1, le=65535)
    username: str
    password: str = ""
    private_key: str = ""
    passphrase: str = ""
    accept_new_host_key: bool = True


class SftpListRequest(SftpConfig):
    path: str = "/"


class SftpDownloadRequest(SftpConfig):
    path: str


class CaptureStartRequest(BaseModel):
    interface: str
    interface_label: str = ""
    duration: int = Field(30, ge=1, le=packet_capture.MAX_CAPTURE_SECONDS)
    max_packets: int = Field(50000, ge=10, le=packet_capture.MAX_CAPTURE_PACKETS)
    bpf_filter: str = Field("", max_length=200)


class CaptureRecordBatchRequest(BaseModel):
    ids: List[int] = Field(default_factory=list)


def _validate_host(host: str) -> str:
    value = (host or "").strip()
    if not value or len(value) > 253 or not HOST_RE.match(value):
        raise HTTPException(status_code=400, detail="目标地址不合法")
    try:
        ipaddress.ip_address(value)
    except ValueError:
        # 域名：只允许字母数字点划线，避免被当作命令参数
        if not re.match(r"^[a-zA-Z0-9](?:[a-zA-Z0-9._-]*[a-zA-Z0-9])?$", value):
            raise HTTPException(status_code=400, detail="目标地址不合法")
    return value


def _require_managed_target(request: Request, db: Session, host: str) -> Device:
    """SSH/SFTP 只允许连接已纳管且当前用户有权限的设备，避免变成内网跳板。"""
    device = (
        db.query(Device)
        .filter((Device.ip_address == host) | (Device.name == host))
        .first()
    )
    if not device:
        raise HTTPException(status_code=403, detail="SSH/SFTP 仅允许连接已纳管设备")
    asset_scope.require_device_access(db, request, device)
    return device


def _decode_output(data: bytes) -> str:
    encodings = [locale.getpreferredencoding(False), "utf-8", "gbk"]
    for encoding in encodings:
        if not encoding:
            continue
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


@router.post("/snmpwalk")
async def snmpwalk(payload: SnmpWalkRequest):
    host = _validate_host(payload.host)
    requested_oid = (payload.oid or "").strip()
    if requested_oid and not re.match(r"^[0-9.]+$", requested_oid):
        raise HTTPException(status_code=400, detail="OID 必须是数字点分格式，例如 1.3.6.1.2.1.1；留空表示全量遍历")
    # 留空时从 1.3.6.1 开始，覆盖标准 MIB-2 与厂商 enterprises 子树
    start_oid = requested_oid or "1.3.6.1"
    client = SNMPClient(
        host=host,
        community=payload.community,
        version=payload.version,
        port=payload.port,
        timeout=payload.timeout,
        v3_username=payload.v3_username,
        v3_security_level=payload.v3_security_level,
        v3_auth_protocol=payload.v3_auth_protocol,
        v3_auth_password=payload.v3_auth_password,
        v3_priv_protocol=payload.v3_priv_protocol,
        v3_priv_password=payload.v3_priv_password,
        v3_context_name=payload.v3_context_name,
    )
    started = time.perf_counter()
    try:
        rows = await client.walk(start_oid, max_rows=payload.max_rows + 1)
    except SNMPError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"SNMP Walk 失败：{exc}") from None
    truncated = len(rows) > payload.max_rows
    visible_rows = rows[: payload.max_rows]
    items = []
    category_counts: Dict[str, int] = {}
    category_labels = {key: label for key, label, _ in WALK_CATEGORIES}
    for row_oid, value in visible_rows:
        category_key, category_label, name = _walk_classify(str(row_oid))
        category_counts[category_key] = category_counts.get(category_key, 0) + 1
        items.append({
            "oid": str(row_oid),
            "value": str(value),
            "category": category_key,
            "category_label": category_label,
            "name": name,
        })
    categories = [
        {"key": key, "label": category_labels.get(key, key), "count": count}
        for key, count in sorted(
            category_counts.items(),
            key=lambda item: (-item[1], next((i for i, rule in enumerate(WALK_CATEGORIES) if rule[0] == item[0]), 99)),
        )
    ]
    return {
        "host": host,
        "oid": start_oid,
        "requested_oid": requested_oid,
        "full_walk": not bool(requested_oid),
        "items": items,
        "categories": categories,
        "total": len(items),
        "truncated": truncated,
        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
    }


async def _run_command(cmd: List[str], timeout: float) -> tuple[int, bytes]:
    proc = await asyncio.create_subprocess_exec(
        *cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        output, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout)
        return proc.returncode or 0, output
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise HTTPException(status_code=504, detail="目标响应超时") from None


@router.post("/ping")
async def ping(payload: PingRequest):
    host = _validate_host(payload.host)
    if os.name == "nt":
        cmd = ["ping", "-n", str(payload.count), "-w", str(payload.timeout * 1000), host]
    else:
        cmd = ["ping", "-c", str(payload.count), "-W", str(payload.timeout), host]
    started = time.perf_counter()
    try:
        code, raw = await _run_command(cmd, payload.timeout * payload.count + 5)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="服务器未安装 ping 命令") from None
    output = _decode_output(raw)
    loss_match = re.search(r"(\d+)%\s*(?:packet\s*loss|丢失|loss)", output, re.I)
    if not loss_match:
        loss_match = re.search(r"(?:丢失|loss)\s*[=:]\s*\d+\s*\((\d+)%", output, re.I)
    loss = int(loss_match.group(1)) if loss_match else (100 if code != 0 else 0)
    latency = {
        "min": None, "avg": None, "max": None,
    }
    rtt_match = re.search(r"(?:min/avg/max(?:/mdev)?|最短|minimum)\s*[=:]\s*([\d.]+)\s*ms.*?([\d.]+)\s*ms", output, re.I)
    if rtt_match:
        latency["min"] = float(rtt_match.group(1))
    avg_match = re.search(r"(?:平均|average|avg)\s*[=:]\s*([\d.]+)\s*ms", output, re.I)
    if avg_match:
        latency["avg"] = float(avg_match.group(1))
    max_match = re.search(r"(?:最长|maximum|max)\s*[=:]\s*([\d.]+)\s*ms", output, re.I)
    if max_match:
        latency["max"] = float(max_match.group(1))
    unix_rtt = re.search(r"=\s*([\d.]+)/([\d.]+)/([\d.]+)", output)
    if unix_rtt:
        latency = {"min": float(unix_rtt.group(1)), "avg": float(unix_rtt.group(2)), "max": float(unix_rtt.group(3))}
    return {
        "host": host,
        "alive": code == 0 and loss < 100,
        "loss_percent": loss,
        "latency": latency,
        "output": output,
        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
    }


_PUBLIC_IP_CACHE: Dict[str, Any] = {"value": None, "ts": 0.0}


def _fetch_public_ip() -> Dict[str, Any]:
    providers = (
        ("https://ipinfo.io/json", "ipinfo.io"),
        ("https://api.ipify.org?format=json", "ipify.org"),
        ("https://ifconfig.me/all.json", "ifconfig.me"),
    )
    errors = []
    for url, source in providers:
        started = time.perf_counter()
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "SNMP-NMS-PublicIP/1.0"})
            with urllib.request.urlopen(request, timeout=6) as response:
                data = json.loads(response.read(256 * 1024).decode("utf-8"))
            ip = str(data.get("ip") or data.get("ip_addr") or "").strip()
            ipaddress.ip_address(ip)
            result = {
                "ip": ip,
                "version": "IPv6" if ":" in ip else "IPv4",
                "country": str(data.get("country") or ""),
                "region": str(data.get("region") or data.get("region_name") or ""),
                "city": str(data.get("city") or ""),
                "isp": str(data.get("org") or data.get("isp") or ""),
                "source": source,
                "duration_ms": round((time.perf_counter() - started) * 1000, 1),
                "queried_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
            }
            return result
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{source}: {exc}")
    raise HTTPException(status_code=502, detail="公网 IP 查询失败：" + "；".join(errors[-2:]))


@router.get("/public-ip")
def public_ip(force: bool = False):
    """查询平台访问互联网的出口公网 IP。"""
    now = time.time()
    cached = _PUBLIC_IP_CACHE.get("value")
    if not force and cached and now - float(_PUBLIC_IP_CACHE.get("ts") or 0) < 60:
        return {**cached, "cached": True}
    result = _fetch_public_ip()
    _PUBLIC_IP_CACHE.update({"value": result, "ts": now})
    return {**result, "cached": False}


@router.post("/tracert")
async def tracert(payload: TracertRequest):
    host = _validate_host(payload.host)
    if os.name != "nt" and not traceroute_installer.traceroute_installed():
        installed = await traceroute_installer.ensure_traceroute()
        if installed.get("status") != "success":
            raise HTTPException(status_code=500, detail=installed.get("message") or "自动安装 traceroute 失败")
    if os.name == "nt":
        cmd = ["tracert", "-d", "-h", str(payload.max_hops), "-w", str(payload.timeout * 1000), host]
    else:
        cmd = ["traceroute", "-n", "-m", str(payload.max_hops), "-w", str(payload.timeout), host]
    started = time.perf_counter()
    try:
        code, raw = await _run_command(cmd, payload.max_hops * (payload.timeout + 1) + 8)
    except FileNotFoundError:
        raise HTTPException(status_code=500, detail="服务器未安装 tracert / traceroute 命令，自动安装失败") from None
    output = _decode_output(raw)
    hops = []
    for line in output.splitlines():
        nums = re.findall(r"\b(\d{1,3})\b", line)
        if nums and int(nums[0]) <= payload.max_hops:
            ips = re.findall(r"(?:\d{1,3}\.){3}\d{1,3}", line)
            if ips:
                hops.append({"hop": int(nums[0]), "ip": ips[0], "raw": line.strip()})
    return {
        "host": host,
        "success": code == 0,
        "hops": hops,
        "output": output,
        "duration_ms": round((time.perf_counter() - started) * 1000, 1),
    }


@router.get("/traceroute/status")
def traceroute_install_status():
    """当前 traceroute 自动安装任务状态。"""
    return {
        "installed": traceroute_installer.traceroute_installed(),
        "job": traceroute_installer.current_job(),
    }


@router.post("/traceroute/install")
async def install_traceroute():
    """手动触发/重试 traceroute 安装，返回最终安装结果。"""
    return await traceroute_installer.ensure_traceroute()


def _parse_tracert_line(line: str, max_hops: int) -> Optional[Dict[str, Any]]:
    match = re.match(r"^\s*(\d{1,3})\s+", line or "")
    if not match:
        return None
    hop = int(match.group(1))
    if hop < 1 or hop > max_hops:
        return None
    ips = re.findall(r"(?:\d{1,3}\.){3}\d{1,3}", line)
    return {"hop": hop, "ip": ips[0] if ips else "", "raw": line.strip()}


@router.websocket("/tracert/ws")
async def tracert_stream(websocket: WebSocket):
    """WebSocket 实时路由追踪：逐行推送 tracert/traceroute 输出。"""
    await websocket.accept()
    db = SessionLocal()
    process = None
    try:
        try:
            config = await asyncio.wait_for(websocket.receive_json(), timeout=20)
        except Exception:
            await websocket.send_json({"type": "error", "message": "连接参数无效"})
            await websocket.close(code=4400)
            return
        user = _ws_user(str(config.get("token") or ""), db)
        db.close()
        db = None
        if not user:
            await websocket.send_json({"type": "error", "message": "登录状态无效或无权使用路由追踪"})
            await websocket.close(code=4401)
            return
        try:
            host = _validate_host(str(config.get("host") or ""))
        except HTTPException as exc:
            await websocket.send_json({"type": "error", "message": str(exc.detail)})
            await websocket.close(code=4400)
            return
        max_hops = max(1, min(64, int(config.get("max_hops") or 30)))
        timeout = max(1, min(10, int(config.get("timeout") or 5)))
        if os.name == "nt":
            cmd = ["tracert", "-d", "-h", str(max_hops), "-w", str(timeout * 1000), host]
        else:
            cmd = ["traceroute", "-n", "-m", str(max_hops), "-w", str(timeout), host]
        started = time.perf_counter()
        await websocket.send_json({
            "type": "start",
            "host": host,
            "max_hops": max_hops,
            "message": f"开始追踪 {host}",
        })
        if os.name != "nt" and not traceroute_installer.traceroute_installed():
            async def _install_progress(job: Dict[str, Any]) -> None:
                await websocket.send_json({
                    "type": "install",
                    "status": job.get("status"),
                    "progress": job.get("progress", 0),
                    "stage": job.get("stage", ""),
                    "message": job.get("message", ""),
                    "log": job.get("log", ""),
                })

            install_result = await traceroute_installer.ensure_traceroute(_install_progress)
            if install_result.get("status") != "success":
                await websocket.send_json({
                    "type": "error",
                    "message": install_result.get("message") or "自动安装 traceroute 失败",
                })
                await websocket.close(code=4500)
                return
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
        except FileNotFoundError:
            await websocket.send_json({"type": "error", "message": "服务器未安装 tracert / traceroute 命令，自动安装失败"})
            await websocket.close(code=4500)
            return
        deadline = time.monotonic() + max(30, max_hops * (timeout + 1) + 10)
        output_lines: List[str] = []
        hops: List[Dict[str, Any]] = []
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                process.kill()
                await process.wait()
                await websocket.send_json({"type": "error", "message": "路由追踪超时，已终止"})
                await websocket.close(code=4504)
                return
            raw = await asyncio.wait_for(process.stdout.readline(), timeout=remaining)
            if not raw:
                break
            line = _decode_output(raw).rstrip("\r\n")
            if not line:
                continue
            output_lines.append(line)
            hop = _parse_tracert_line(line, max_hops)
            if hop:
                hops.append(hop)
            await websocket.send_json({
                "type": "line",
                "line": line,
                "hop": hop,
                "hops_found": len(hops),
                "elapsed_ms": round((time.perf_counter() - started) * 1000, 1),
            })
        code = await asyncio.wait_for(process.wait(), timeout=10)
        output = "\n".join(output_lines)
        await websocket.send_json({
            "type": "done",
            "host": host,
            "success": code == 0,
            "hops": hops,
            "output": output,
            "duration_ms": round((time.perf_counter() - started) * 1000, 1),
        })
    except WebSocketDisconnect:
        if process and process.returncode is None:
            process.kill()
            await process.wait()
    except asyncio.TimeoutError:
        if process and process.returncode is None:
            process.kill()
            await process.wait()
        try:
            await websocket.send_json({"type": "error", "message": "路由追踪超时，已终止"})
        except Exception:
            pass
    except Exception as exc:  # noqa: BLE001
        if process and process.returncode is None:
            process.kill()
            await process.wait()
        try:
            await websocket.send_json({"type": "error", "message": f"路由追踪失败：{exc}"})
        except Exception:
            pass
    finally:
        if db is not None:
            db.close()
        try:
            await websocket.close()
        except Exception:
            pass


def _ws_user(token: str, db: Session) -> Optional[User]:
    try:
        payload = auth_service.decode_token(token)
        user = db.query(User).filter(User.id == int(payload.get("sub"))).first()
    except (ValueError, TypeError):
        return None
    if not user or not user.is_active:
        return None
    if not auth_service.has_permission(user, "tools:edit"):
        return None
    return user


def _sftp_connect(config: SftpConfig):
    """建立 SFTP 会话，返回 ssh / sftp / 临时私钥路径。"""
    try:
        import paramiko
    except ImportError:
        raise HTTPException(status_code=500, detail="服务器未安装 paramiko，请执行 pip install -r requirements.txt") from None
    host = _validate_host(config.host)
    username = (config.username or "").strip()
    if not username:
        raise HTTPException(status_code=400, detail="请输入 SSH 用户名")
    key_path = ""
    if (config.private_key or "").strip():
        handle = tempfile.NamedTemporaryFile("w", suffix=".key", delete=False, encoding="utf-8")
        handle.write(config.private_key)
        handle.close()
        key_path = handle.name
        try:
            os.chmod(key_path, 0o600)
        except OSError:
            pass
    ssh = paramiko.SSHClient()
    ssh.load_system_host_keys()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy() if config.accept_new_host_key else paramiko.RejectPolicy())
    kwargs: Dict[str, Any] = {
        "hostname": host,
        "port": int(config.port),
        "username": username,
        "timeout": 12,
        "banner_timeout": 12,
        "auth_timeout": 12,
        # 禁止使用服务器自身的 ssh-agent / ~/.ssh 私钥，避免复用系统凭据
        "allow_agent": False,
        "look_for_keys": False,
    }
    if config.password:
        kwargs["password"] = config.password
    if key_path:
        kwargs["pkey"] = paramiko.PKey.from_path(key_path, config.passphrase or None)
    try:
        ssh.connect(**kwargs)
        sftp = ssh.open_sftp()
    except Exception:
        ssh.close()
        if key_path:
            Path(key_path).unlink(missing_ok=True)
        raise
    return ssh, sftp, key_path


def _sftp_close(ssh, sftp, key_path):
    try:
        sftp.close()
    except Exception:  # noqa: BLE001
        pass
    try:
        ssh.close()
    except Exception:  # noqa: BLE001
        pass
    if key_path:
        Path(key_path).unlink(missing_ok=True)


def _remote_path(value: str, fallback: str = "/") -> str:
    path = (value or fallback).strip() or fallback
    if "\x00" in path:
        raise HTTPException(status_code=400, detail="远端路径不合法")
    return posixpath.normpath(path)


def _sftp_list(config: SftpConfig, path: str) -> List[Dict[str, Any]]:
    ssh, sftp, key_path = _sftp_connect(config)
    try:
        target = _remote_path(path)
        rows = []
        for item in sftp.listdir_attr(target):
            is_dir = (item.st_mode or 0) & 0o170000 == 0o040000
            rows.append({
                "name": item.filename,
                "is_dir": is_dir,
                "size": 0 if is_dir else int(item.st_size or 0),
                "modified": int(item.st_mtime or 0),
            })
        rows.sort(key=lambda row: (not row["is_dir"], row["name"].lower()))
        return rows
    finally:
        _sftp_close(ssh, sftp, key_path)


def _sftp_upload(config: SftpConfig, remote_dir: str, filename: str, source) -> Dict[str, Any]:
    ssh, sftp, key_path = _sftp_connect(config)
    try:
        directory = _remote_path(remote_dir, "/tmp")
        name = Path(filename or "upload.bin").name
        if not name or name in (".", ".."):
            raise HTTPException(status_code=400, detail="文件名不合法")
        remote_path = posixpath.join(directory, name)
        try:
            sftp.stat(directory)
        except Exception:
            raise HTTPException(status_code=400, detail=f"远端目录不存在：{directory}") from None
        source.seek(0)
        sftp.putfo(source, remote_path, confirm=True)
        stat = sftp.stat(remote_path)
        return {"remote_path": remote_path, "name": name, "size": int(stat.st_size or 0)}
    finally:
        _sftp_close(ssh, sftp, key_path)


def _sftp_download(config: SftpConfig, path: str) -> tuple[bytes, str]:
    ssh, sftp, key_path = _sftp_connect(config)
    try:
        target = _remote_path(path)
        buffer = io.BytesIO()
        sftp.getfo(target, buffer)
        return buffer.getvalue(), posixpath.basename(target) or "download.bin"
    finally:
        _sftp_close(ssh, sftp, key_path)


@router.post("/sftp/list")
async def sftp_list(payload: SftpListRequest, request: Request, db: Session = Depends(get_db)):
    _require_managed_target(request, db, _validate_host(payload.host))
    try:
        items = await asyncio.to_thread(_sftp_list, payload, payload.path)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"SFTP 目录读取失败：{exc}") from None
    return {"path": _remote_path(payload.path), "items": items}


@router.post("/sftp/upload")
async def sftp_upload(
    file: UploadFile = File(...),
    host: str = Form(...),
    port: int = Form(22),
    username: str = Form(...),
    password: str = Form(""),
    private_key: str = Form(""),
    passphrase: str = Form(""),
    accept_new_host_key: bool = Form(True),
    remote_dir: str = Form("/tmp"),
    request: Request = None,
    db: Session = Depends(get_db),
):
    _require_managed_target(request, db, _validate_host(host))
    if file.size and file.size > 200 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="单个文件不能超过 200MB")
    config = SftpConfig(
        host=host,
        port=port,
        username=username,
        password=password,
        private_key=private_key,
        passphrase=passphrase,
        accept_new_host_key=accept_new_host_key,
    )
    try:
        result = await asyncio.to_thread(_sftp_upload, config, remote_dir, file.filename, file.file)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"文件上传失败：{exc}") from None
    finally:
        await file.close()
    return {"message": "文件上传成功", **result}


@router.post("/sftp/download")
async def sftp_download(payload: SftpDownloadRequest, request: Request, db: Session = Depends(get_db)):
    _require_managed_target(request, db, _validate_host(payload.host))
    try:
        content, name = await asyncio.to_thread(_sftp_download, payload, payload.path)
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"文件下载失败：{exc}") from None
    if len(content) > 200 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="单个文件不能超过 200MB")
    from urllib.parse import quote
    headers = {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(name)}"}
    return Response(content=content, media_type="application/octet-stream", headers=headers)


@router.get("/capture/interfaces")
def capture_interfaces():
    capability = packet_capture.capture_capability()
    try:
        interfaces = packet_capture.list_capture_interfaces()
    except packet_capture.CaptureError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return {
        **capability,
        "interfaces": interfaces,
    }


@router.post("/capture/start")
def capture_start(payload: CaptureStartRequest, db: Session = Depends(get_db)):
    try:
        interfaces = packet_capture.list_capture_interfaces()
    except packet_capture.CaptureError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    found = next((item for item in interfaces if item["id"] == payload.interface), None)
    if not found:
        raise HTTPException(status_code=400, detail="抓包网卡不存在，请刷新网卡列表")
    try:
        job = packet_capture.start_capture(
            payload.interface,
            payload.interface_label or found.get("label") or payload.interface,
            payload.duration,
            payload.max_packets,
            payload.bpf_filter or "",
        )
    except packet_capture.CaptureError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    time.sleep(0.25)
    return job.snapshot(db)


@router.get("/capture/status/{job_id}")
def capture_status(job_id: str, db: Session = Depends(get_db)):
    job = packet_capture.get_capture_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="抓包任务不存在或已过期")
    return job.snapshot(db)


@router.post("/capture/stop/{job_id}")
def capture_stop(job_id: str, db: Session = Depends(get_db)):
    job = packet_capture.stop_capture_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="抓包任务不存在或已过期")
    # 停止接口会等待抓包线程写完 .cap 并写入文件记录，前端停止后即可直接展示
    job.wait_finished(5.0)
    return job.snapshot(db)


@router.get("/capture/jobs")
def capture_jobs():
    return packet_capture.list_capture_jobs()


@router.get("/capture/records")
def capture_records(limit: int = 200, db: Session = Depends(get_db)):
    return {"items": packet_capture.list_capture_records(db, max(1, min(500, limit)))}


@router.get("/capture/records/{record_id}/download")
def capture_record_download(record_id: int, db: Session = Depends(get_db)):
    record = packet_capture.get_capture_record(db, record_id)
    if not record:
        raise HTTPException(status_code=404, detail="抓包记录不存在")
    path = packet_capture.capture_record_path(record.filename)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="抓包文件不存在")
    media_type = "application/vnd.tcpdump.pcap" if path.suffix.lower() == ".cap" else "application/json"
    return Response(
        content=path.read_bytes(),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{record.filename}"'},
    )


@router.post("/capture/records/batch-download")
def capture_records_batch_download(payload: CaptureRecordBatchRequest, db: Session = Depends(get_db)):
    try:
        content, filename = packet_capture.build_capture_records_zip(db, payload.ids)
    except packet_capture.CaptureError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return Response(
        content=content,
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/capture/records/batch-delete")
def capture_records_batch_delete(payload: CaptureRecordBatchRequest, db: Session = Depends(get_db)):
    result = packet_capture.delete_capture_records(db, payload.ids)
    return {"message": "抓包记录已删除", **result}


@router.websocket("/ssh")
async def ssh_terminal(websocket: WebSocket):
    await websocket.accept()
    try:
        config = await asyncio.wait_for(websocket.receive_json(), timeout=20)
    except Exception:  # noqa: BLE001
        await websocket.close(code=4400, reason="连接参数无效")
        return

    db = SessionLocal()
    try:
        user = _ws_user(str(config.get("token") or ""), db)
    finally:
        db.close()
    if not user:
        await websocket.send_json({"type": "error", "message": "登录状态无效或无权使用 SSH 终端"})
        await websocket.close(code=4401, reason="未登录或无权限")
        return

    try:
        import paramiko
    except ImportError:
        await websocket.send_json({"type": "error", "message": "服务器未安装 paramiko，请执行 pip install -r requirements.txt"})
        await websocket.close(code=4500)
        return

    host = _validate_host(str(config.get("host") or ""))
    scope_db = SessionLocal()
    try:
        target_device = scope_db.query(Device).filter((Device.ip_address == host) | (Device.name == host)).first()
        if not target_device or not asset_scope.can_access_device_for_user(scope_db, user, target_device):
            await websocket.send_json({"type": "error", "message": "SSH 仅允许连接已纳管且有权限的设备"})
            await websocket.close(code=4403, reason="无权访问目标设备")
            return
    finally:
        scope_db.close()
    port = int(config.get("port") or 22)
    username = str(config.get("username") or "").strip()
    password = str(config.get("password") or "")
    private_key = str(config.get("private_key") or "")
    passphrase = str(config.get("passphrase") or "")
    accept_new = bool(config.get("accept_new_host_key"))
    cols = max(20, min(300, int(config.get("cols") or 100)))
    rows = max(5, min(100, int(config.get("rows") or 30)))
    if not username:
        await websocket.send_json({"type": "error", "message": "请输入 SSH 用户名"})
        await websocket.close(code=4400)
        return

    key_path = ""
    client = None
    channel = None
    try:
        if private_key.strip():
            handle = tempfile.NamedTemporaryFile("w", suffix=".key", delete=False, encoding="utf-8")
            handle.write(private_key)
            handle.close()
            key_path = handle.name
            try:
                os.chmod(key_path, 0o600)
            except OSError:
                pass

        def connect():
            ssh = paramiko.SSHClient()
            ssh.load_system_host_keys()
            ssh.set_missing_host_key_policy(
                paramiko.AutoAddPolicy() if accept_new else paramiko.RejectPolicy()
            )
            kwargs: Dict[str, Any] = {
                "hostname": host,
                "port": port,
                "username": username,
                "timeout": 10,
                "banner_timeout": 10,
                "auth_timeout": 10,
                # 不复用服务器自身的 SSH agent / 私钥
                "allow_agent": False,
                "look_for_keys": False,
            }
            if password:
                kwargs["password"] = password
            if key_path:
                kwargs["pkey"] = paramiko.PKey.from_path(key_path, passphrase or None)
            ssh.connect(**kwargs)
            shell = ssh.invoke_shell(term="xterm-256color", width=cols, height=rows)
            return ssh, shell

        client, channel = await asyncio.to_thread(connect)
        await websocket.send_json({"type": "ready", "message": "SSH 已连接"})

        async def reader():
            while True:
                try:
                    data = await asyncio.to_thread(channel.recv, 4096)
                except Exception:  # noqa: BLE001
                    break
                if not data:
                    break
                await websocket.send_json({"type": "data", "data": data.decode("utf-8", errors="replace")})

        reader_task = asyncio.create_task(reader())
        try:
            while True:
                message = await websocket.receive()
                if message.get("type") == "websocket.disconnect":
                    break
                text = message.get("text")
                if text:
                    try:
                        payload = json.loads(text)
                    except Exception:  # noqa: BLE001
                        payload = None
                    if isinstance(payload, dict) and payload.get("type") == "resize":
                        channel.resize_pty(
                            width=max(20, min(300, int(payload.get("cols") or cols))),
                            height=max(5, min(100, int(payload.get("rows") or rows))),
                        )
                    elif isinstance(payload, dict) and payload.get("type") == "input":
                        channel.send(str(payload.get("data") or ""))
                    elif isinstance(payload, dict) and payload.get("type") == "disconnect":
                        break
                    else:
                        channel.send(text)
                elif message.get("bytes"):
                    channel.send(message["bytes"])
        finally:
            reader_task.cancel()
    except HTTPException as exc:
        await websocket.send_json({"type": "error", "message": str(exc.detail)})
    except Exception as exc:  # noqa: BLE001
        await websocket.send_json({"type": "error", "message": f"SSH 连接失败：{exc}"})
    finally:
        try:
            if channel:
                channel.close()
            if client:
                client.close()
        except Exception:  # noqa: BLE001
            pass
        if key_path:
            Path(key_path).unlink(missing_ok=True)
        try:
            await websocket.close()
        except Exception:  # noqa: BLE001
            pass
