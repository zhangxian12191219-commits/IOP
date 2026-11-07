"""虚拟化只读纳管：VMware vCenter、H3C CAS 与 KVM/libvirt(SSH+virsh)。

设计原则：
- 只做只读采集，不执行开关机、删除、快照等写操作。
- VMware 使用 pyVmomi（延迟导入），H3C CAS 使用 REST API + HTTP Digest，
  KVM 使用 SSH + virsh，避免额外依赖 libvirt 客户端。
- 所有异常转换为 VirtualizationError，由路由层返回可读错误。
"""
from __future__ import annotations

import asyncio
import http.cookiejar
import ipaddress
import json
import logging
import re
import shlex
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models.database import SessionLocal
from ..models.virtualization import VirtualHost, VirtualMachine, VirtualPlatform
from . import virtualization_alerts
from .virtualization_crypto import decrypt_password

logger = logging.getLogger("snmp-monitor.virtualization")
VMWARE_DEFAULT_SSO_DOMAIN = "vsphere.local"
PROXMOX_DEFAULT_REALM = "pam"
_KVM_NET_CACHE: Dict[int, Tuple[float, float, float]] = {}


def normalize_vmware_username(username: Any) -> str:
    """VMware SSO 账号必须带域；只填用户名时补默认 vsphere.local。"""
    raw = str(username or "").strip()
    if not raw:
        return ""
    if "@" in raw or "\\" in raw:
        return raw
    return f"{raw}@{VMWARE_DEFAULT_SSO_DOMAIN}"


def normalize_proxmox_username(username: Any) -> str:
    """Proxmox 账号必须带 realm；只填用户名时按 PAM 域处理。"""
    raw = str(username or "").strip()
    if not raw:
        return ""
    if "@" in raw:
        return raw
    return f"{raw}@{PROXMOX_DEFAULT_REALM}"


class VirtualizationError(RuntimeError):
    """平台连接或采集错误。"""


def _float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _int(value: Any, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _gb(value: Any) -> float:
    return round(_float(value) / (1024 ** 3), 2)


def _mb_from_kb(value: Any) -> float:
    return round(_float(value) / 1024, 2)


def _percent(used: float, total: float) -> float:
    if total <= 0:
        return 0.0
    return round(max(0.0, min(100.0, used / total * 100)), 2)


def _ip_sort_key(value: Any) -> str:
    """IPv4/IPv6 自然排序键，保证 10.0.0.2 排在 10.0.0.10 前面。"""
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        ip = ipaddress.ip_address(text)
    except ValueError:
        return f"9{text}"
    if ip.version == 4:
        return "4" + ".".join(f"{int(part):03d}" for part in text.split("."))
    return "6" + ip.exploded


def _clean_address(address: str) -> str:
    value = (address or "").strip()
    if not value:
        raise VirtualizationError("平台地址不能为空")
    if "://" in value:
        parsed = urlparse(value)
        value = parsed.hostname or ""
    else:
        value = value.split("/", 1)[0]
    value = value.strip().strip("[]")
    if not value:
        raise VirtualizationError("平台地址不合法")
    if not re.match(r"^[A-Za-z0-9._:-]+$", value):
        raise VirtualizationError("平台地址包含非法字符")
    return value


def _port(platform: VirtualPlatform) -> int:
    if platform.platform_type == "vmware":
        return _int(platform.port, 443)
    if platform.platform_type == "cas":
        return _int(platform.port, 8080)
    if platform.platform_type == "proxmox":
        return _int(platform.port, 8006)
    if platform.platform_type == "docker":
        return _int(platform.port, 2375)
    if platform.platform_type == "kubernetes":
        return _int(platform.port, 6443)
    return _int(platform.port, 22)


def _power_state(value: str) -> str:
    raw = str(value or "").strip().lower()
    if raw in ("poweredon", "running", "on"):
        return "running"
    if raw in ("poweredoff", "shutoff", "off", "stopped"):
        return "stopped"
    if raw in ("suspended", "paused", "pmsuspended"):
        return "paused"
    return "unknown"


# ============================================================================
# KVM / libvirt over SSH
# ============================================================================
class KvmSshAdapter:
    """通过 SSH 执行 virsh / proc 命令读取 KVM 状态。"""

    def __init__(self, platform: VirtualPlatform, password: str):
        self.platform = platform
        self.password = password
        self.host = _clean_address(platform.address)
        self.port = _port(platform)
        self.username = platform.username
        self.client = None
        self.host_external_id = self.host

    def connect(self):
        try:
            import paramiko
        except ImportError as exc:  # pragma: no cover
            raise VirtualizationError("缺少 paramiko，无法连接 KVM") from exc
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            client.connect(
                self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                timeout=10,
                banner_timeout=10,
                auth_timeout=10,
                look_for_keys=False,
                allow_agent=False,
            )
        except Exception as exc:  # noqa: BLE001
            raise VirtualizationError(f"KVM SSH 连接失败：{exc}") from exc
        self.client = client
        return client

    def close(self) -> None:
        if self.client:
            try:
                self.client.close()
            except Exception:  # noqa: BLE001
                pass
            self.client = None

    def run(self, command: str, timeout: int = 20, allow_fail: bool = False) -> str:
        if not self.client:
            self.connect()
        try:
            _stdin, stdout, stderr = self.client.exec_command(
                f"LC_ALL=C {command}", timeout=timeout
            )
            out = stdout.read().decode("utf-8", errors="replace")
            err = stderr.read().decode("utf-8", errors="replace")
            code = stdout.channel.recv_exit_status()
        except Exception as exc:  # noqa: BLE001
            if allow_fail:
                return ""
            raise VirtualizationError(f"KVM 命令执行失败：{exc}") from exc
        if code != 0 and not allow_fail:
            raise VirtualizationError((err or out or f"命令退出码 {code}").strip()[:400])
        return out

    def test(self) -> Dict[str, Any]:
        try:
            self.connect()
            hostname = self.run("hostname").strip()
            version = self.run("virsh --version", timeout=10).strip()
            domains = self.run("virsh list --all --name", timeout=15).splitlines()
            return {
                "address": self.host,
                "port": self.port,
                "hostname": hostname,
                "version": version,
                "platform": "kvm",
                "vm_count": len([x for x in domains if x.strip()]),
            }
        finally:
            self.close()

    def _parse_key_values(self, text: str) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for line in text.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                result[key.strip()] = value.strip()
        return result

    def _parse_dominfo(self, text: str) -> Dict[str, str]:
        result: Dict[str, str] = {}
        for line in text.splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                result[key.strip()] = value.strip()
        return result

    def _vm_detail(self, name: str) -> Dict[str, Any]:
        info = self._parse_dominfo(self.run(f"virsh dominfo {shlex.quote(name)}"))
        state_text = info.get("State", "")
        state = _power_state(state_text)
        if state == "unknown" and "paused" in state_text.lower():
            state = "paused"
        vcpu = _int(info.get("CPU(s)"), 0)
        max_mem_kb = _float(str(info.get("Max memory") or "").split()[0]) if info.get("Max memory") else 0.0
        memory_mb = _mb_from_kb(max_mem_kb)
        stat = self._parse_key_values(
            self.run(f"virsh domstats {shlex.quote(name)}", allow_fail=True)
        )
        cpu_time_ns = _int(stat.get("cpu.time"), 0)
        balloon_current = _float(stat.get("balloon.current"))
        balloon_max = _float(stat.get("balloon.maximum"))
        memory_used_mb = _mb_from_kb(balloon_current) if balloon_current else 0
        memory_usage = _percent(memory_used_mb, memory_mb)
        if not memory_usage and balloon_max:
            memory_usage = _percent(balloon_current, balloon_max)

        # block.N.capacity/allocation 单位为 bytes
        block_capacity = 0.0
        block_allocation = 0.0
        block_keys = set()
        for key in stat:
            match = re.match(r"block\.(\d+)\.(capacity|allocation)$", key)
            if match:
                block_keys.add(match.group(1))
        for idx in block_keys:
            block_capacity += _float(stat.get(f"block.{idx}.capacity"))
            block_allocation += _float(stat.get(f"block.{idx}.allocation"))

        nic_names = {
            stat.get(k) for k in stat
            if re.match(r"net\.\d+\.name$", k) and stat.get(k)
        }
        ips = self._vm_ips(name)
        guest_os = ""
        try:
            guest = self._parse_key_values(
                self.run(f"virsh guestinfo {shlex.quote(name)}", timeout=8, allow_fail=True)
            )
            guest_os = guest.get("os.name") or guest.get("os.id") or ""
        except Exception:  # noqa: BLE001
            guest_os = ""
        if not guest_os:
            xml = self.run(f"virsh dumpxml {shlex.quote(name)}", allow_fail=True)
            match = re.search(r"<description>(.*?)</description>", xml, re.S)
            if match:
                guest_os = match.group(1).strip()

        return {
            "external_id": info.get("UUID") or name,
            "name": name,
            "power_state": state,
            "vcpu": vcpu,
            "memory_mb": memory_mb,
            "memory_used_mb": memory_used_mb,
            "memory_usage": memory_usage,
            "disk_total_gb": _gb(block_capacity),
            "disk_used_gb": _gb(block_allocation),
            "disk_usage": _percent(block_allocation, block_capacity),
            "nic_count": len(nic_names),
            "ip_addresses": ips,
            "guest_os": guest_os,
            "tools_status": "guest-agent" if ips else "not-detected",
            "cpu_time_ns": cpu_time_ns,
            "host_name": self.host_external_id,
            "extra": {"state_text": state_text},
        }

    def _vm_ips(self, name: str) -> List[str]:
        text = self.run(
            f"virsh domifaddr {shlex.quote(name)} --source agent",
            timeout=8,
            allow_fail=True,
        )
        if not text:
            text = self.run(
                f"virsh domifaddr {shlex.quote(name)}", timeout=8, allow_fail=True
            )
        ips: List[str] = []
        for line in text.splitlines():
            match = re.search(r"\b((?:\d{1,3}\.){3}\d{1,3})\b", line)
            if match and match.group(1) not in ips:
                ips.append(match.group(1))
        return ips

    def collect(self) -> Dict[str, Any]:
        try:
            self.connect()
            hostname = self.run("hostname").strip() or self.host
            self.host_external_id = hostname
            host_ip = self.host
            ip_text = self.run("hostname -I", timeout=8, allow_fail=True).strip()
            if ip_text:
                host_ip = ip_text.split()[0]
            node = self._parse_dominfo(self.run("virsh nodeinfo"))
            cores = _int(node.get("CPU(s)"), 1) or 1
            cpu_mhz = _float((node.get("CPU frequency") or "").replace("MHz", "").strip())
            mem_total_kb = _float(str(node.get("Memory size") or "").split()[0]) if node.get("Memory size") else 0.0
            mem_total_mb = _mb_from_kb(mem_total_kb)
            cpu_usage = self._host_cpu_usage()
            mem_usage, mem_used_mb = self._host_memory()
            storage_total, storage_used = self._host_storage()
            net_rx, net_tx = self._host_network()
            vm_names = [
                line.strip()
                for line in self.run("virsh list --all --name", timeout=15).splitlines()
                if line.strip()
            ]
            vms = []
            for name in vm_names:
                try:
                    vms.append(self._vm_detail(name))
                except VirtualizationError as exc:
                    logger.warning("KVM VM 采集失败 %s/%s: %s", self.host, name, exc)
            host = {
                "external_id": hostname,
                "name": hostname,
                "ip_address": host_ip,
                "cluster_name": "KVM",
                "status": "online",
                "cpu_cores": cores,
                "cpu_mhz": cpu_mhz,
                "cpu_usage": cpu_usage,
                "memory_total_mb": mem_total_mb,
                "memory_used_mb": mem_used_mb,
                "memory_usage": mem_usage,
                "storage_total_gb": storage_total,
                "storage_used_gb": storage_used,
                "storage_usage": _percent(storage_used, storage_total),
                "net_rx_bps": net_rx,
                "net_tx_bps": net_tx,
                "vm_count": len(vms),
                "uptime_seconds": self._host_uptime(),
                "extra": {"address": self.host, "port": self.port},
            }
            return {"hosts": [host], "vms": vms, "version": self.run("virsh --version", timeout=10).strip()}
        finally:
            self.close()

    def _host_cpu_usage(self) -> float:
        text = self.run("vmstat 1 2 | tail -1", timeout=8, allow_fail=True)
        parts = text.split()
        if len(parts) >= 15:
            try:
                idle = float(parts[14])
                return round(max(0.0, min(100.0, 100.0 - idle)), 2)
            except (TypeError, ValueError):
                pass
        return 0.0

    def _host_memory(self) -> Tuple[float, float]:
        text = self.run("free -m", allow_fail=True)
        for line in text.splitlines():
            if line.lower().startswith("mem:"):
                parts = line.split()
                if len(parts) >= 3:
                    total = _float(parts[1])
                    used = _float(parts[2])
                    return _percent(used, total), used
        return 0.0, 0.0

    def _host_storage(self) -> Tuple[float, float]:
        text = self.run("df -Pk / | tail -1", allow_fail=True)
        parts = text.split()
        if len(parts) >= 3:
            return _gb(_float(parts[1]) * 1024), _gb(_float(parts[2]) * 1024)
        return 0.0, 0.0

    def _host_network(self) -> Tuple[float, float]:
        """通过 /proc/net/dev 的累计字节计算两次同步之间的速率。"""
        text = self.run("cat /proc/net/dev", allow_fail=True)
        rx = tx = 0.0
        for line in text.splitlines():
            if ":" not in line:
                continue
            name, values = line.split(":", 1)
            if name.strip() == "lo":
                continue
            parts = values.split()
            if len(parts) < 9:
                continue
            try:
                rx += float(parts[0])
                tx += float(parts[8])
            except (TypeError, ValueError):
                continue
        now = time.monotonic()
        previous = _KVM_NET_CACHE.get(self.platform.id)
        _KVM_NET_CACHE[self.platform.id] = (rx, tx, now)
        if not previous:
            return 0.0, 0.0
        elapsed = max(0.001, now - previous[2])
        return (
            round(max(0.0, (rx - previous[0]) / elapsed), 2),
            round(max(0.0, (tx - previous[1]) / elapsed), 2),
        )

    def _host_uptime(self) -> int:
        text = self.run("cat /proc/uptime", allow_fail=True).split()
        return _int(text[0]) if text else 0


# ============================================================================
# H3C CAS REST API（HTTP Digest）
# ============================================================================
class CasAdapter:
    """H3C CAS REST API 只读采集。

    CAS 使用标准 HTTP Digest 认证；接口默认位于 /cas/casrs。
    适配器只调用 hostpool / cluster / host / vm 查询接口，不执行任何写操作。
    """

    API_PREFIX = "/cas/casrs"

    def __init__(self, platform: VirtualPlatform, password: str):
        self.platform = platform
        self.password = password
        raw = (platform.address or "").strip()
        parsed = urlparse(raw if "://" in raw else f"//{raw}")
        self.host = _clean_address(raw)
        self.port = _int(platform.port, 8080)
        if raw.lower().startswith("https://"):
            self.scheme = "https"
        elif raw.lower().startswith("http://"):
            self.scheme = "http"
        else:
            self.scheme = "https" if self.port in (443, 8443) else "http"
        if parsed.port:
            self.port = parsed.port
        self.username = platform.username
        self.base_url = f"{self.scheme}://{self.host}:{self.port}{self.API_PREFIX}"
        self.opener = self._build_opener()

    def _build_opener(self):
        password_mgr = urllib.request.HTTPPasswordMgrWithDefaultRealm()
        password_mgr.add_password(None, self.base_url, self.username, self.password)
        cookie_jar = http.cookiejar.CookieJar()
        handlers = [
            urllib.request.HTTPCookieProcessor(cookie_jar),
            urllib.request.HTTPDigestAuthHandler(password_mgr),
        ]
        if self.scheme == "https" and not self.platform.verify_tls:
            context = ssl._create_unverified_context()
            handlers.append(urllib.request.HTTPSHandler(context=context))
        return urllib.request.build_opener(*handlers)

    def _request(self, path: str, params: Optional[Dict[str, Any]] = None) -> Tuple[Any, Any]:
        query = f"?{urllib.parse.urlencode(params)}" if params else ""
        url = f"{self.base_url}{path}{query}"
        request = urllib.request.Request(url, headers={
            "Accept": "application/json",
            "User-Agent": "SNMP-NMS-CAS-Adapter/1.0",
        })
        try:
            with self.opener.open(request, timeout=30) as response:
                raw = response.read()
                headers = dict(response.headers)
                status = response.status
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:  # noqa: BLE001
                pass
            if exc.code == 401:
                raise VirtualizationError("H3C CAS 认证失败，请检查用户名、密码和 Digest 认证配置") from exc
            message = exc.headers.get("Error-Message") or detail or str(exc)
            raise VirtualizationError(f"H3C CAS 接口错误 HTTP {exc.code}: {message}") from exc
        except urllib.error.URLError as exc:
            raise VirtualizationError(f"H3C CAS 连接失败: {exc.reason}") from exc
        if status >= 400:
            raise VirtualizationError(f"H3C CAS 接口返回 HTTP {status}")
        text = raw.decode("utf-8", errors="replace")
        try:
            data: Any = json.loads(text) if text.strip() else {}
        except ValueError:
            try:
                data = self._xml_to_obj(ET.fromstring(raw))
            except Exception as exc:  # noqa: BLE001
                raise VirtualizationError(f"H3C CAS 返回内容无法解析: {exc}") from exc
        if isinstance(data, dict) and data.get("code") not in (None, 0, "0"):
            raise VirtualizationError(
                f"H3C CAS 接口错误 {data.get('code')}: "
                f"{data.get('msg') or data.get('errorMsg') or ''}"
            )
        return data, headers

    @classmethod
    def _xml_to_obj(cls, element) -> Any:
        children = list(element)
        if not children:
            return (element.text or "").strip()
        result: Dict[str, Any] = {}
        for child in children:
            key = child.tag.split("}", 1)[-1]
            value = cls._xml_to_obj(child)
            if key in result:
                if not isinstance(result[key], list):
                    result[key] = [result[key]]
                result[key].append(value)
            else:
                result[key] = value
        return result

    @staticmethod
    def _items(data: Any, keys: Tuple[str, ...]) -> List[Dict[str, Any]]:
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            for key in keys:
                value = data.get(key)
                if isinstance(value, list):
                    return [item for item in value if isinstance(item, dict)]
                if isinstance(value, dict):
                    return [value]
        return []

    def _host_pools(self) -> Dict[int, str]:
        data, _ = self._request("/hostpool/all")
        return {
            _int(item.get("id")): str(item.get("name") or "")
            for item in self._items(data, ("hostPool", "hostpool", "hostPools"))
            if _int(item.get("id"))
        }

    def _clusters(self) -> Dict[int, str]:
        data, _ = self._request("/cluster/clusterInfo/all")
        return {
            _int(item.get("id")): str(item.get("name") or "")
            for item in self._items(data, ("clusterDetailInfo", "cluster"))
            if _int(item.get("id"))
        }

    def _hosts(self) -> List[Dict[str, Any]]:
        data, _ = self._request("/host/list", {"offset": 0, "limit": 5000})
        return self._items(data, ("host", "hosts"))

    def _vms(self) -> List[Dict[str, Any]]:
        data, _ = self._request("/vm/vmList", {"offset": 0, "limit": 5000})
        return self._items(data, ("domain", "domains", "vm"))

    @staticmethod
    def _extract_ips(vm: Dict[str, Any]) -> List[str]:
        values: List[str] = []
        candidates = [vm.get("ipAddress"), vm.get("ip"), vm.get("ipv4Attribute")]
        for candidate in candidates:
            if isinstance(candidate, str) and candidate.strip():
                values.append(candidate.strip())
            elif isinstance(candidate, dict):
                ipv4 = candidate.get("ipv4")
                if isinstance(ipv4, dict) and ipv4.get("ipAddress"):
                    values.append(str(ipv4["ipAddress"]).strip())
                elif isinstance(ipv4, list):
                    for item in ipv4:
                        if isinstance(item, dict) and item.get("ipAddress"):
                            values.append(str(item["ipAddress"]).strip())
            elif isinstance(candidate, list):
                for item in candidate:
                    if isinstance(item, dict):
                        ipv4 = item.get("ipv4")
                        if isinstance(ipv4, dict) and ipv4.get("ipAddress"):
                            values.append(str(ipv4["ipAddress"]).strip())
        result = []
        for value in values:
            if value and value not in result:
                result.append(value)
        return result

    @staticmethod
    def _nic_count(vm: Dict[str, Any]) -> int:
        attr = vm.get("ipv4Attribute")
        if isinstance(attr, list):
            return len(attr)
        if isinstance(attr, dict):
            return 1
        return 1 if vm.get("ipAddress") else 0

    @staticmethod
    def _disk_total_gb(vm: Dict[str, Any]) -> float:
        text = " ".join(str(vm.get(key) or "") for key in ("diskInfo", "diskDetail"))
        matches = re.findall(r"([\d.]+)\s*(TB|GB|G|MB|M)\b", text, re.I)
        total = 0.0
        for number, unit in matches:
            value = _float(number)
            if unit.upper() == "TB":
                total += value * 1024
            elif unit.upper() in ("GB", "G"):
                total += value
            elif unit.upper() in ("MB", "M"):
                total += value / 1024
        return round(total, 2)

    @staticmethod
    def _status(value: Any) -> str:
        if isinstance(value, (int, float)):
            return {1: "unknown", 2: "running", 3: "stopped", 4: "paused"}.get(int(value), "unknown")
        return _power_state(str(value or ""))

    def test(self) -> Dict[str, Any]:
        pools = self._host_pools()
        hosts = self._hosts()
        vms = self._vms()
        try:
            version_data, _ = self._request("/host/version")
            version = (
                str(version_data.get("version") or version_data)
                if isinstance(version_data, dict) else str(version_data)
            )
        except Exception:  # noqa: BLE001
            version = "H3C CAS"
        return {
            "address": self.host,
            "port": self.port,
            "hostname": self.host,
            "version": version,
            "platform": "cas",
            "api_type": "H3C CAS REST (Digest)",
            "host_count": len(hosts),
            "vm_count": len(vms),
            "hostpool_count": len(pools),
        }

    def collect(self) -> Dict[str, Any]:
        pools = self._host_pools()
        clusters = self._clusters()
        raw_hosts = self._hosts()
        raw_vms = self._vms()
        host_id_map = {_int(item.get("id")): str(item.get("name") or "") for item in raw_hosts}
        host_name_map = {str(item.get("name") or ""): item for item in raw_hosts}
        vm_count_by_host: Dict[str, int] = {}
        for vm in raw_vms:
            name = str(vm.get("hostName") or host_id_map.get(_int(vm.get("hostId")), ""))
            if name:
                vm_count_by_host[name] = vm_count_by_host.get(name, 0) + 1

        hosts = []
        for item in raw_hosts:
            host_id = _int(item.get("id"))
            name = str(item.get("name") or item.get("ip") or host_id)
            cluster_id = _int(item.get("clusterId"))
            pool_id = _int(item.get("hostPoolId"))
            storage_capacity_mb = _float(item.get("storageCapacity"))
            storage_used_mb = _float(item.get("allocation"))
            if not storage_used_mb and item.get("avilable") is not None:
                storage_used_mb = max(0.0, storage_capacity_mb - _float(item.get("avilable")))
            memory_mb = _float(item.get("memorySize"))
            cores = _int(item.get("cpuCount")) or (
                _int(item.get("cpuCores")) * max(1, _int(item.get("cpuSockets"), 1))
            )
            hosts.append({
                "external_id": str(host_id or name),
                "name": name,
                "ip_address": str(
                    item.get("ip") or item.get("ipAddress") or item.get("manageIp")
                    or item.get("hostIp") or name
                ).strip()[:45],
                "cluster_name": clusters.get(cluster_id) or pools.get(pool_id) or "",
                "status": "online" if _int(item.get("status"), 1) == 1 else "offline",
                "cpu_model": f"{item.get('cpuProvider') or ''} {item.get('provider') or ''}".strip(),
                "cpu_cores": cores,
                "cpu_mhz": _float(item.get("frequency")),
                "cpu_usage": None,
                "memory_total_mb": round(memory_mb, 2),
                "memory_used_mb": 0.0,
                "memory_usage": None,
                "storage_total_gb": round(storage_capacity_mb / 1024, 2),
                "storage_used_gb": round(storage_used_mb / 1024, 2),
                "storage_usage": _percent(storage_used_mb, storage_capacity_mb),
                "vm_count": vm_count_by_host.get(name, 0),
                "uptime_seconds": 0,
                "extra": {
                    "cas_host_id": host_id,
                    "cas_cluster_id": cluster_id,
                    "cas_hostpool_id": pool_id,
                    "ha": _int(item.get("enableHA") or item.get("haEnable")),
                    "maintain": _int(item.get("cvkMaintain")),
                },
            })

        vms = []
        for item in raw_vms:
            host_id = _int(item.get("hostId"))
            host_name = str(item.get("hostName") or host_id_map.get(host_id, ""))
            vms.append({
                "external_id": str(item.get("uuid") or item.get("id") or item.get("name") or ""),
                "name": str(item.get("title") or item.get("name") or item.get("uuid") or ""),
                "power_state": self._status(item.get("vmStatus")),
                "vcpu": _int(item.get("cpu")),
                "memory_mb": _float(item.get("memory")),
                "disk_total_gb": self._disk_total_gb(item),
                "disk_used_gb": 0.0,
                "disk_usage": None,
                "nic_count": self._nic_count(item),
                "ip_addresses": self._extract_ips(item),
                "guest_os": str(item.get("osDesc") or item.get("osVersion") or ""),
                "tools_status": "running" if _int(item.get("castoolsStatus")) else "not_running",
                "cpu_usage": max(0.0, min(100.0, _float(item.get("cpuRate")))),
                "memory_usage": max(0.0, min(100.0, _float(item.get("memRate")))),
                "host_name": host_name if host_name in host_name_map else "",
                "extra": {
                    "cas_id": _int(item.get("id")),
                    "uuid": item.get("uuid") or "",
                    "cluster_id": _int(item.get("clusterId")),
                    "hostpool_id": _int(item.get("hostPoolId")),
                    "uptime_minutes": _int(item.get("uptime")),
                },
            })
        return {
            "hosts": hosts,
            "vms": vms,
            "version": "H3C CAS",
            "hostpools": len(pools),
            "clusters": len(clusters),
        }


# ============================================================================
# VMware vCenter
# ============================================================================
class ProxmoxAdapter:
    """Proxmox VE API2 只读采集（支持账号密码和 API Token）。"""

    API_PREFIX = "/api2/json"

    def __init__(self, platform: VirtualPlatform, password: str):
        self.platform = platform
        self.password = password
        raw = (platform.address or "").strip()
        parsed = urlparse(raw if "://" in raw else f"//{raw}")
        self.host = _clean_address(raw)
        self.port = _int(platform.port, 8006)
        if raw.lower().startswith("http://"):
            self.scheme = "http"
        else:
            self.scheme = "https"
        if parsed.port:
            self.port = parsed.port
        self.username = normalize_proxmox_username(platform.username)
        self.base_url = f"{self.scheme}://{self.host}:{self.port}{self.API_PREFIX}"
        self.ticket = ""
        self.csrf_token = ""
        self.token_auth = "!" in self.username and bool(password)
        context = None
        if self.scheme == "https" and not platform.verify_tls:
            context = ssl._create_unverified_context()
        handlers = []
        if context is not None:
            handlers.append(urllib.request.HTTPSHandler(context=context))
        self.opener = urllib.request.build_opener(*handlers)

    def _http_error(self, exc: urllib.error.HTTPError) -> VirtualizationError:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", errors="replace")[:500]
        except Exception:  # noqa: BLE001
            pass
        if exc.code == 401:
            return VirtualizationError(
                "Proxmox 认证失败：请检查账号 realm（如 root@pam）、密码或 API Token；"
                "使用 API Token 时用户名格式为 user@realm!tokenid，密码填 Token Secret"
            )
        if exc.code == 403:
            return VirtualizationError(
                "Proxmox 权限不足：只读账号建议分配 PVEAuditor 角色（至少需要 VM.Audit、Sys.Audit 权限）"
            )
        return VirtualizationError(f"Proxmox 接口错误 HTTP {exc.code}: {detail or exc.reason}")

    def _login(self) -> None:
        if self.ticket or self.token_auth:
            return
        body = urllib.parse.urlencode({
            "username": self.username,
            "password": self.password,
        }).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}/access/ticket",
            data=body,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
                "User-Agent": "SNMP-NMS-Proxmox-Adapter/1.0",
            },
            method="POST",
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace") or "{}")
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from exc
        except urllib.error.URLError as exc:
            raise VirtualizationError(f"Proxmox 连接失败: {exc.reason}") from exc
        data = payload.get("data") or payload
        self.ticket = str(data.get("ticket") or "")
        self.csrf_token = str(data.get("CSRFPreventionToken") or "")
        if not self.ticket:
            raise VirtualizationError("Proxmox 登录失败：接口没有返回认证票据")

    def _request(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        self._login()
        query = f"?{urllib.parse.urlencode(params, doseq=True)}" if params else ""
        headers = {
            "Accept": "application/json",
            "User-Agent": "SNMP-NMS-Proxmox-Adapter/1.0",
        }
        if self.token_auth:
            headers["Authorization"] = f"PVEAPIToken={self.username}={self.password}"
        elif self.ticket:
            headers["Cookie"] = f"PVEAuthCookie={self.ticket}"
        if self.csrf_token:
            headers["CSRFPreventionToken"] = self.csrf_token
        request = urllib.request.Request(
            f"{self.base_url}{path}{query}", headers=headers, method="GET"
        )
        try:
            with self.opener.open(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8", errors="replace") or "{}")
        except urllib.error.HTTPError as exc:
            raise self._http_error(exc) from exc
        except urllib.error.URLError as exc:
            raise VirtualizationError(f"Proxmox 连接失败: {exc.reason}") from exc
        except ValueError as exc:
            raise VirtualizationError(f"Proxmox 返回内容无法解析: {exc}") from exc
        return payload.get("data") if isinstance(payload, dict) else payload

    @staticmethod
    def _node_status(item: Dict[str, Any]) -> str:
        return "online" if str(item.get("status") or "").lower() == "online" else "offline"

    @staticmethod
    def _bytes_gb(value: Any) -> float:
        return round(_float(value) / (1024 ** 3), 2)

    @staticmethod
    def _bytes_mb(value: Any) -> float:
        return round(_float(value) / (1024 ** 2), 2)

    def _cluster_meta(self) -> Tuple[str, Dict[str, str]]:
        """读取集群名称和节点 IP；权限不足时静默回退。"""
        name = "Proxmox VE"
        ip_map: Dict[str, str] = {}
        try:
            rows = self._request("/cluster/status") or []
        except VirtualizationError:
            return name, ip_map
        for item in rows if isinstance(rows, list) else []:
            if not isinstance(item, dict):
                continue
            if item.get("type") == "cluster" and item.get("name"):
                name = str(item["name"])
            if item.get("type") == "node":
                node_name = str(item.get("name") or item.get("node") or "").strip()
                ip = str(item.get("ip") or "").strip()
                if node_name and ip:
                    ip_map[node_name] = ip
        return name, ip_map

    def test(self) -> Dict[str, Any]:
        version = self._request("/version") or {}
        nodes = self._request("/nodes") or []
        version_text = str(version.get("version") or "")
        release = str(version.get("release") or "")
        if release and release not in version_text:
            version_text = f"{version_text} ({release})".strip()
        node_name = ""
        if isinstance(nodes, list) and nodes:
            node_name = str(nodes[0].get("node") or "") if isinstance(nodes[0], dict) else ""
        return {
            "address": self.host,
            "port": self.port,
            "hostname": node_name or self.host,
            "version": version_text or "Proxmox VE",
            "platform": "proxmox",
            "api_type": "PVE API2",
            "node_count": len(nodes) if isinstance(nodes, list) else 0,
        }

    def _flatten_osd_tree(self, node: Any) -> List[Dict[str, Any]]:
        result: List[Dict[str, Any]] = []
        if not isinstance(node, dict):
            return result
        if str(node.get("type") or "") == "osd":
            result.append(node)
        for child in node.get("children") or []:
            result.extend(self._flatten_osd_tree(child))
        return result

    def _storage_health(self) -> Dict[str, Any]:
        """采集 PVE 已接入的存储（dir/LVM/iSCSI/NFS/RBD/CephFS 等）。"""
        try:
            rows = self._request("/cluster/resources", {"type": "storage"}) or []
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "items": [], "error": str(exc)[:300]}
        if not isinstance(rows, list):
            rows = []
        try:
            configs = self._request("/storage") or []
        except Exception:  # noqa: BLE001
            configs = []
        config_map = {
            str(item.get("storage") or ""): item
            for item in configs if isinstance(item, dict) and item.get("storage")
        }
        grouped: Dict[str, Dict[str, Any]] = {}
        for item in rows:
            if not isinstance(item, dict):
                continue
            name = str(item.get("storage") or "")
            if not name:
                continue
            status = str(item.get("status") or "unknown").lower()
            current = grouped.setdefault(name, {
                "name": name,
                "type": str(item.get("plugintype") or (config_map.get(name) or {}).get("type") or item.get("type") or "unknown"),
                "content": str(item.get("content") or (config_map.get(name) or {}).get("content") or ""),
                "shared": bool(item.get("shared") or (config_map.get(name) or {}).get("shared")),
                "statuses": [],
                "nodes": [],
                "total_gb": 0.0,
                "used_gb": 0.0,
            })
            if status not in current["statuses"]:
                current["statuses"].append(status)
            node = str(item.get("node") or "")
            if node and node not in current["nodes"]:
                current["nodes"].append(node)
            try:
                total = _float(item.get("maxdisk"))
                used = _float(item.get("disk"))
            except (TypeError, ValueError):
                total = used = 0.0
            if total > current["total_gb"] * (1024 ** 3):
                # 同一共享存储会在多个节点重复出现，取最大容量一次
                current["total_gb"] = total / (1024 ** 3)
                current["used_gb"] = used / (1024 ** 3)
        items = []
        for item in grouped.values():
            statuses = item.pop("statuses", [])
            # 任一节点不可用即标记异常；共享存储以最差状态为准
            if any(status not in ("available", "active", "ok") for status in statuses):
                status = next((value for value in statuses if value not in ("available", "active", "ok")), "unknown")
            else:
                status = "available"
            total = round(float(item.get("total_gb") or 0), 2)
            used = round(float(item.get("used_gb") or 0), 2)
            usage = round(used / total * 100, 2) if total > 0 else None
            items.append({
                **item,
                "status": status,
                "total_gb": total,
                "used_gb": used,
                "usage": usage,
            })
        return {"available": True, "items": items}

    def _ceph_health(self, node_rows: List[Any]) -> Dict[str, Any]:
        """采集 Proxmox 集群 Ceph 健康；未启用 Ceph 时返回不可用，不影响平台同步。"""
        try:
            raw = self._request("/cluster/ceph/status") or {}
        except Exception as exc:  # noqa: BLE001
            return {"available": False, "error": str(exc)[:300]}
        if not isinstance(raw, dict):
            return {"available": False, "error": "Ceph status 返回格式异常"}
        health = raw.get("health") if isinstance(raw.get("health"), dict) else {}
        osdmap = raw.get("osdmap") if isinstance(raw.get("osdmap"), dict) else {}
        pgmap = raw.get("pgmap") if isinstance(raw.get("pgmap"), dict) else {}
        monmap = raw.get("monmap") if isinstance(raw.get("monmap"), dict) else {}
        checks = health.get("checks") if isinstance(health.get("checks"), dict) else {}
        check_items = []
        for name, item in checks.items():
            if not isinstance(item, dict):
                continue
            detail = item.get("detail") if isinstance(item.get("detail"), list) else []
            messages = [str(value.get("message") or "") for value in detail if isinstance(value, dict)]
            check_items.append({
                "name": name,
                "severity": str(item.get("severity") or ""),
                "muted": bool(item.get("muted")),
                "summary": str((item.get("summary") or {}).get("message") or ""),
                "detail": [message for message in messages if message][:5],
            })
        osds: List[Dict[str, Any]] = []
        nodes = [str(item.get("node") or "") for item in node_rows if isinstance(item, dict) and item.get("node")]
        if nodes:
            try:
                tree = self._request(f"/nodes/{nodes[0]}/ceph/osd") or {}
                if isinstance(tree, dict) and isinstance(tree.get("root"), dict):
                    tree = tree["root"]
                osds = self._flatten_osd_tree(tree)
            except Exception:  # noqa: BLE001
                osds = []
        osd_items = []
        for item in osds:
            try:
                osd_id = int(item.get("id"))
            except (TypeError, ValueError):
                osd_id = item.get("id")
            osd_items.append({
                "id": osd_id,
                "name": str(item.get("name") or f"osd.{osd_id}"),
                "host": str(item.get("host") or ""),
                "status": str(item.get("status") or "unknown"),
                "in": _int(item.get("in"), 1),
                "device_class": str(item.get("device_class") or ""),
                "blfsdev": str(item.get("blfsdev") or ""),
                "percent_used": round(_float(item.get("percent_used")), 2),
            })
        down_osds = [item for item in osd_items if item["status"] != "up" or item["in"] == 0]
        pgs_by_state: Dict[str, int] = {}
        for item in pgmap.get("pgs_by_state") or []:
            if isinstance(item, dict):
                pgs_by_state[str(item.get("state_name") or "")] = _int(item.get("count"), 0)
        pg_total = _int(pgmap.get("num_pgs"), 0) or sum(pgs_by_state.values())
        pg_degraded = sum(count for state, count in pgs_by_state.items() if state != "active+clean")
        mon_total = len(monmap.get("mons") or [])
        quorum_names = raw.get("quorum_names") if isinstance(raw.get("quorum_names"), list) else []
        spurious = next((item for item in check_items if item["name"] in ("BLUESTORE_SPURIOUS_READ_ERRORS", "DEVICE_HEALTH")), None)
        recent_crash = next((item for item in check_items if item["name"] == "RECENT_CRASH"), None)
        return {
            "available": True,
            "status": str(health.get("status") or "UNKNOWN"),
            "checks": check_items,
            "osd_total": _int(osdmap.get("num_osds"), len(osd_items)),
            "osd_up": _int(osdmap.get("num_up_osds"), sum(1 for item in osd_items if item["status"] == "up")),
            "osd_in": _int(osdmap.get("num_in_osds"), sum(1 for item in osd_items if item["in"] != 0)),
            "osd_down": _int(osdmap.get("num_down_osds"), sum(1 for item in osd_items if item["status"] != "up")),
            "osd_out": _int(osdmap.get("num_out_osds"), sum(1 for item in osd_items if item["in"] == 0)),
            "down_osds": down_osds[:50],
            "pg_total": pg_total,
            "pg_degraded": pg_degraded,
            "pgs_by_state": pgs_by_state,
            "mon_total": mon_total,
            "quorum_count": len(quorum_names),
            "quorum_names": quorum_names[:20],
            "spurious_read_errors": spurious.get("detail") if spurious else [],
            "recent_crash": recent_crash.get("detail") if recent_crash else [],
        }

    def collect(self) -> Dict[str, Any]:
        version = self._request("/version") or {}
        node_rows = self._request("/nodes") or []
        cluster_name, node_ip_map = self._cluster_meta()
        resource_rows = self._request("/cluster/resources", {"type": "vm"}) or []
        if not isinstance(node_rows, list):
            node_rows = []
        if not isinstance(resource_rows, list):
            resource_rows = []
        resources = [item for item in resource_rows if isinstance(item, dict) and not item.get("template")]

        vm_count_by_node: Dict[str, int] = {}
        for item in resources:
            node = str(item.get("node") or "")
            if node:
                vm_count_by_node[node] = vm_count_by_node.get(node, 0) + 1

        hosts = []
        for item in node_rows:
            if not isinstance(item, dict):
                continue
            node_name = str(item.get("node") or item.get("name") or self.host)
            max_cpu = _int(item.get("maxcpu"), 0)
            cpu_fraction = _float(item.get("cpu"))
            cpu_usage = round(cpu_fraction * 100, 2) if cpu_fraction <= 1 else round(cpu_fraction, 2)
            mem_total = self._bytes_mb(item.get("maxmem"))
            mem_used = self._bytes_mb(item.get("mem"))
            storage_total = self._bytes_gb(item.get("maxdisk"))
            storage_used = self._bytes_gb(item.get("disk"))
            node_ip = node_ip_map.get(node_name) or (node_name if re.match(r"^\d{1,3}(?:\.\d{1,3}){3}$", node_name) else self.host)
            hosts.append({
                "external_id": node_name,
                "name": node_name,
                "ip_address": node_ip[:45],
                "cluster_name": cluster_name,
                "status": self._node_status(item),
                "cpu_model": "Proxmox VE Node",
                "cpu_cores": max_cpu,
                "cpu_mhz": 0.0,
                "cpu_usage": max(0.0, min(100.0, cpu_usage)),
                "memory_total_mb": mem_total,
                "memory_used_mb": mem_used,
                "memory_usage": _percent(mem_used, mem_total),
                "storage_total_gb": storage_total,
                "storage_used_gb": storage_used,
                "storage_usage": _percent(storage_used, storage_total),
                "vm_count": vm_count_by_node.get(node_name, 0),
                "uptime_seconds": _int(item.get("uptime"), 0),
                "extra": {"pve_node": node_name, "level": item.get("level") or ""},
            })

        vms = []
        for item in resources:
            vm_type = str(item.get("type") or "qemu").lower()
            if vm_type not in ("qemu", "lxc"):
                continue
            vmid = _int(item.get("vmid"), 0)
            if not vmid:
                continue
            max_mem = self._bytes_mb(item.get("maxmem"))
            mem = self._bytes_mb(item.get("mem"))
            disk_total = self._bytes_gb(item.get("maxdisk"))
            disk_used = self._bytes_gb(item.get("disk"))
            cpu_fraction = _float(item.get("cpu"))
            cpu_usage = round(cpu_fraction * 100, 2) if cpu_fraction <= 1 else round(cpu_fraction, 2)
            status = _power_state(str(item.get("status") or ""))
            name = str(item.get("name") or f"{vm_type}-{vmid}")
            vms.append({
                "external_id": f"{vm_type}-{vmid}",
                "name": name,
                "power_state": status,
                "vcpu": _int(item.get("maxcpu"), 0),
                "memory_mb": max_mem,
                "disk_total_gb": disk_total,
                "disk_used_gb": disk_used,
                "disk_usage": _percent(disk_used, disk_total),
                "nic_count": 0,
                "ip_addresses": [],
                "guest_os": "LXC 容器" if vm_type == "lxc" else "QEMU 虚拟机",
                "tools_status": "guestAgentRunning" if vm_type == "qemu" and status == "running" else "unknown",
                "cpu_usage": max(0.0, min(100.0, cpu_usage)),
                "memory_usage": _percent(mem, max_mem),
                "host_name": str(item.get("node") or ""),
                "uptime_seconds": _int(item.get("uptime"), 0),
                "extra": {
                    "pve_type": vm_type,
                    "vmid": vmid,
                    "node": item.get("node") or "",
                    "template": bool(item.get("template")),
                },
            })

        version_text = str(version.get("version") or "Proxmox VE")
        release = str(version.get("release") or "")
        if release and release not in version_text:
            version_text = f"{version_text} ({release})".strip()
        ceph = self._ceph_health(node_rows)
        storage = self._storage_health()
        return {"hosts": hosts, "vms": vms, "version": version_text, "health": {"ceph": ceph, "storage": storage}}


class VMwareAdapter:
    """vCenter 8.0+ 只读采集，pyVmomi 延迟导入。"""

    def __init__(self, platform: VirtualPlatform, password: str):
        self.platform = platform
        self.password = password
        self.host = _clean_address(platform.address)
        self.port = _port(platform)
        self.username = normalize_vmware_username(platform.username)
        self.si = None
        self.vim = None

    def _connect(self):
        try:
            from pyVim.connect import SmartConnect
            from pyVmomi import vim
        except ImportError as exc:  # pragma: no cover
            raise VirtualizationError(
                "缺少 pyVmomi，无法连接 VMware。请在后端环境安装 pyvmomi"
            ) from exc
        context = None
        if not self.platform.verify_tls:
            context = ssl._create_unverified_context()
        try:
            self.si = SmartConnect(
                host=self.host,
                user=self.username,
                pwd=self.password,
                port=self.port,
                sslContext=context,
            )
        except Exception as exc:  # noqa: BLE001
            error_text = str(exc)
            if "InvalidLogin" in type(exc).__name__ or "incorrect user name or password" in error_text:
                raise VirtualizationError(
                    "vCenter 登录失败：账号或密码错误。"
                    f"VMware 账号必须填写 SSO 域（当前使用 {self.username}），"
                    "例如 snmp-nms@vsphere.local；请确认该账号可在 vSphere Client 正常登录且未被锁定。"
                ) from exc
            raise VirtualizationError(f"vCenter 连接失败：{exc}") from exc
        self.vim = vim
        return self.si

    def close(self) -> None:
        if self.si:
            try:
                from pyVim.connect import Disconnect
                Disconnect(self.si)
            except Exception:  # noqa: BLE001
                pass
            self.si = None

    def test(self) -> Dict[str, Any]:
        try:
            si = self._connect()
            about = si.content.about
            return {
                "address": self.host,
                "port": self.port,
                "username": self.username,
                "hostname": about.name,
                "version": about.version,
                "platform": "vmware",
                "api_type": about.apiType,
            }
        finally:
            self.close()

    def _cluster_name(self, obj) -> str:
        parent = getattr(obj, "parent", None)
        while parent:
            if isinstance(parent, self.vim.ClusterComputeResource):
                return parent.name
            parent = getattr(parent, "parent", None)
        return ""

    def _host_ip(self, host) -> str:
        """优先取宿主机管理 vNIC 的 IP，缺失时回退主机名（通常是 IP）。"""
        try:
            vnics = getattr(getattr(host, "config", None), "network", None)
            for vnic in getattr(vnics, "vnic", None) or []:
                ip = str(getattr(getattr(vnic, "spec", None), "ipAddress", "") or "").strip()
                if ip:
                    return ip[:45]
        except Exception:  # noqa: BLE001
            pass
        try:
            ip = str(getattr(getattr(host, "summary", None), "managementServerIp", "") or "").strip()
            if ip:
                return ip[:45]
        except Exception:  # noqa: BLE001
            pass
        return str(getattr(host, "name", "") or "").strip()[:45]

    def _hosts(self) -> List[Dict[str, Any]]:
        content = self.si.content
        view = content.viewManager.CreateContainerView(
            content.rootFolder, [self.vim.HostSystem], True
        )
        result = []
        try:
            for host in view.view:
                summary = host.summary
                hw = summary.hardware
                cores = _int(getattr(hw, "numCpuCores", 0), 0)
                mhz = _float(getattr(hw, "cpuMhz", 0))
                total_mb = _float(getattr(hw, "memorySize", 0)) / (1024 ** 2)
                used_mb = _float(summary.quickStats.overallMemoryUsage)
                cpu_mhz = _float(summary.quickStats.overallCpuUsage)
                cap_bytes = free_bytes = 0.0
                for store in getattr(host, "datastore", None) or []:
                    try:
                        cap_bytes += _float(store.summary.capacity)
                        free_bytes += _float(store.summary.freeSpace)
                    except Exception:  # noqa: BLE001
                        continue
                result.append({
                    "external_id": host.name,
                    "name": host.name,
                    "ip_address": self._host_ip(host),
                    "cluster_name": self._cluster_name(host),
                    "status": "online" if str(summary.runtime.connectionState) == "connected" else "offline",
                    "cpu_model": str(getattr(hw, "cpuModel", "") or ""),
                    "cpu_cores": cores,
                    "cpu_mhz": mhz,
                    "cpu_usage": _percent(cpu_mhz, cores * mhz),
                    "memory_total_mb": round(total_mb, 2),
                    "memory_used_mb": round(used_mb, 2),
                    "memory_usage": _percent(used_mb, total_mb),
                    "storage_total_gb": _gb(cap_bytes),
                    "storage_used_gb": _gb(max(0.0, cap_bytes - free_bytes)),
                    "storage_usage": _percent(max(0.0, cap_bytes - free_bytes), cap_bytes),
                    "vm_count": len(getattr(host, "vm", None) or []),
                    "uptime_seconds": _int(getattr(summary.quickStats, "uptime", 0)),
                    "extra": {"connection_state": str(summary.runtime.connectionState)},
                })
        finally:
            view.Destroy()
        return result

    def _vms(self, hosts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        content = self.si.content
        view = content.viewManager.CreateContainerView(
            content.rootFolder, [self.vim.VirtualMachine], True
        )
        host_names = {item["name"] for item in hosts}
        result = []
        try:
            for vm in view.view:
                config = getattr(vm, "config", None)
                if not config or getattr(config, "template", False):
                    continue
                summary = vm.summary
                guest = summary.guest
                hw = config.hardware
                vcpu = _int(getattr(hw, "numCPU", 0))
                memory_mb = _float(getattr(hw, "memoryMB", 0))
                disk_total = 0.0
                nic_count = 0
                for dev in getattr(hw, "device", None) or []:
                    if isinstance(dev, self.vim.vm.device.VirtualDisk):
                        disk_total += _float(getattr(dev, "capacityInBytes", 0))
                    elif isinstance(dev, self.vim.vm.device.VirtualEthernetCard):
                        nic_count += 1
                guest_disks = getattr(guest, "disk", None) or []
                disk_used = sum(
                    max(0.0, _float(getattr(d, "capacity", 0)) - _float(getattr(d, "freeSpace", 0)))
                    for d in guest_disks
                )
                if not disk_used:
                    disk_used = _float(getattr(summary.storage, "committed", 0))
                qs = summary.quickStats
                cpu_usage = 0.0
                max_cpu = _float(getattr(summary.runtime, "maxCpuUsage", 0))
                if max_cpu > 0:
                    cpu_usage = _percent(_float(qs.overallCpuUsage), max_cpu)
                mem_usage = _percent(_float(qs.guestMemoryUsage), memory_mb)
                ips = []
                ip = getattr(guest, "ipAddress", None)
                if ip:
                    ips.append(ip)
                host_name = getattr(summary.runtime.host, "name", "") if summary.runtime.host else ""
                tools = str(getattr(guest, "toolsRunningStatus", "") or "")
                result.append({
                    "external_id": getattr(config, "instanceUuid", None) or vm._moId,
                    "name": config.name,
                    "power_state": _power_state(summary.runtime.powerState),
                    "vcpu": vcpu,
                    "memory_mb": memory_mb,
                    "disk_total_gb": _gb(disk_total),
                    "disk_used_gb": _gb(disk_used),
                    "disk_usage": _percent(disk_used, disk_total),
                    "nic_count": nic_count,
                    "ip_addresses": ips,
                    "guest_os": getattr(config, "guestFullName", "") or "",
                    "tools_status": tools,
                    "cpu_usage": round(cpu_usage, 2),
                    "memory_usage": mem_usage,
                    "host_name": host_name if host_name in host_names else "",
                    "extra": {"mo_id": vm._moId, "cluster": self._cluster_name(vm)},
                })
        finally:
            view.Destroy()
        return result

    def collect(self) -> Dict[str, Any]:
        try:
            self._connect()
            hosts = self._hosts()
            vms = self._vms(hosts)
            return {"hosts": hosts, "vms": vms, "version": self.si.content.about.version}
        finally:
            self.close()


# ============================================================================
# 同步到数据库
# ============================================================================
# ============================================================================
# Docker Engine API
# ============================================================================
def _http_base(platform: VirtualPlatform, default_port: int, default_scheme: str = "https"):
    raw = (platform.address or "").strip()
    parsed = urlparse(raw if "://" in raw else f"//{raw}")
    host = _clean_address(raw)
    port = _int(platform.port, 0) or parsed.port or default_port
    scheme = (parsed.scheme or "").lower()
    if scheme not in ("http", "https"):
        scheme = default_scheme
    if port == 2376:
        scheme = "https"
    return scheme, host, port


def _quantity_number(value: Any, divisor: float = 1.0) -> float:
    """解析 Kubernetes 数量（如 8、500m、16Gi、1048576Ki）。"""
    text = str(value or "").strip()
    if not text:
        return 0.0
    multipliers = {"Ki": 1024, "Mi": 1024 ** 2, "Gi": 1024 ** 3, "Ti": 1024 ** 4}
    for suffix, factor in multipliers.items():
        if text.endswith(suffix):
            return _float(text[:-len(suffix)]) * factor / divisor
    if text.endswith("m"):
        return _float(text[:-1]) / 1000 / divisor
    return _float(text) / divisor


class DockerEngineAdapter:
    """Docker Engine API 只读采集（TCP/HTTPS，不使用本机 docker CLI）。"""

    def __init__(self, platform: VirtualPlatform, password: str):
        self.platform = platform
        self.password = password or ""
        self.username = (platform.username or "").strip()
        self.scheme, self.host, self.port = _http_base(platform, 2375, "http")
        self.base_url = f"{self.scheme}://{self.host}:{self.port}"
        self.opener = urllib.request.build_opener()
        if self.scheme == "https" and not platform.verify_tls:
            context = ssl._create_unverified_context()
            self.opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context))

    def _headers(self) -> Dict[str, str]:
        headers = {"Accept": "application/json", "User-Agent": "SNMP-NMS-Docker-Adapter/1.0"}
        if self.username and self.password:
            import base64
            raw = f"{self.username}:{self.password}".encode("utf-8")
            headers["Authorization"] = "Basic " + base64.b64encode(raw).decode("ascii")
        return headers

    def _request(self, path: str) -> Any:
        request = urllib.request.Request(f"{self.base_url}{path}", headers=self._headers())
        try:
            with self.opener.open(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8", errors="replace") or "{}")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:  # noqa: BLE001
                pass
            if exc.code in (401, 403):
                raise VirtualizationError("Docker API 认证失败：请检查账号密码，或确认 Docker 允许远程只读访问") from exc
            raise VirtualizationError(f"Docker API 错误 HTTP {exc.code}: {detail or exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise VirtualizationError(f"Docker 连接失败: {exc.reason}") from exc

    def test(self) -> Dict[str, Any]:
        version = self._request("/version")
        return {
            "ok": True,
            "platform": "docker",
            "version": version.get("Version") or version.get("ApiVersion") or "",
            "api_version": version.get("ApiVersion") or "",
        }

    def collect(self) -> Dict[str, Any]:
        version = self._request("/version")
        info = self._request("/info")
        containers = self._request("/containers/json?all=1")
        host_id = f"docker-{_clean_address(self.platform.address)}"
        host_name = str(info.get("Name") or _clean_address(self.platform.address)).lstrip("/")
        memory_total_mb = round(_float(info.get("MemTotal")) / 1024 / 1024, 2)
        host = {
            "external_id": host_id,
            "name": host_name,
            "ip_address": _clean_address(self.platform.address),
            "cluster_name": "Docker Engine",
            "status": "online",
            "cpu_model": str(info.get("Architecture") or ""),
            "cpu_cores": _int(info.get("NCPU"), 0),
            "cpu_mhz": 0,
            "cpu_usage": None,
            "memory_total_mb": memory_total_mb,
            "memory_used_mb": 0,
            "memory_usage": None,
            "storage_total_gb": 0,
            "storage_used_gb": 0,
            "storage_usage": None,
            "vm_count": len(containers),
            "uptime_seconds": 0,
            "extra": {"docker_version": version.get("Version") or "", "containers": info.get("Containers")},
        }
        vms: List[Dict[str, Any]] = []
        for item in containers:
            if not isinstance(item, dict) or not item.get("Id"):
                continue
            state = str(item.get("State") or "").lower()
            power = "running" if state == "running" else ("paused" if state == "paused" else "stopped")
            ips = []
            networks = (item.get("NetworkSettings") or {}).get("Networks") or {}
            for net in networks.values():
                ip = str((net or {}).get("IPAddress") or "").strip()
                if ip and ip not in ips:
                    ips.append(ip)
            names = item.get("Names") or []
            display = str(names[0] if names else item.get("Id", ""))[:255].lstrip("/")
            vms.append({
                "external_id": str(item.get("Id"))[:255],
                "name": display,
                "host_name": host_id,
                "power_state": power,
                "vcpu": 0,
                "memory_mb": 0,
                "disk_total_gb": 0,
                "disk_used_gb": 0,
                "disk_usage": None,
                "nic_count": len(ips),
                "ip_addresses": ips,
                "guest_os": str(item.get("Image") or ""),
                "tools_status": str(item.get("Status") or ""),
                "cpu_usage": None,
                "memory_usage": None,
                "net_rx_bps": 0,
                "net_tx_bps": 0,
                "extra": {"docker_state": state, "image": item.get("Image") or ""},
            })
        return {"hosts": [host], "vms": vms, "version": version.get("Version") or ""}


# ============================================================================
# Kubernetes API
# ============================================================================
class KubernetesAdapter:
    """Kubernetes API Server 只读采集（ServiceAccount Bearer Token）。"""

    def __init__(self, platform: VirtualPlatform, password: str):
        self.platform = platform
        self.token = (password or "").strip()
        if self.token.lower().startswith("bearer "):
            self.token = self.token[7:].strip()
        self.scheme, self.host, self.port = _http_base(platform, 6443, "https")
        self.base_url = f"{self.scheme}://{self.host}:{self.port}"
        self.opener = urllib.request.build_opener()
        if self.scheme == "https" and not platform.verify_tls:
            context = ssl._create_unverified_context()
            self.opener = urllib.request.build_opener(urllib.request.HTTPSHandler(context=context))

    def _request(self, path: str) -> Any:
        headers = {"Accept": "application/json", "User-Agent": "SNMP-NMS-Kubernetes-Adapter/1.0"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(f"{self.base_url}{path}", headers=headers)
        try:
            with self.opener.open(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8", errors="replace") or "{}")
        except urllib.error.HTTPError as exc:
            detail = ""
            try:
                detail = exc.read().decode("utf-8", errors="replace")[:500]
            except Exception:  # noqa: BLE001
                pass
            if exc.code in (401, 403):
                raise VirtualizationError(
                    "Kubernetes API 认证或权限不足：请检查 Bearer Token，并确认 ServiceAccount 具备 nodes/pods 只读权限"
                ) from exc
            raise VirtualizationError(f"Kubernetes API 错误 HTTP {exc.code}: {detail or exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise VirtualizationError(f"Kubernetes 连接失败: {exc.reason}") from exc

    def test(self) -> Dict[str, Any]:
        version = self._request("/version")
        return {
            "ok": True,
            "platform": "kubernetes",
            "version": version.get("gitVersion") or version.get("major") or "",
            "api_version": version.get("major", "") + "." + version.get("minor", ""),
        }

    def _nodes(self) -> List[Dict[str, Any]]:
        data = self._request("/api/v1/nodes")
        return data.get("items") or []

    def _pods(self) -> List[Dict[str, Any]]:
        data = self._request("/api/v1/pods")
        return data.get("items") or []

    def _node(self, item: Dict[str, Any]) -> Dict[str, Any]:
        meta = item.get("metadata") or {}
        status = item.get("status") or {}
        addresses = status.get("addresses") or []
        ip = next((str(a.get("address")) for a in addresses if a.get("type") == "InternalIP"), "")
        ready = False
        for condition in status.get("conditions") or []:
            if condition.get("type") == "Ready":
                ready = str(condition.get("status") or "").lower() == "true"
                break
        capacity = status.get("capacity") or {}
        allocatable = status.get("allocatable") or {}
        cpu = _quantity_number(allocatable.get("cpu") or capacity.get("cpu"), 1)
        mem_bytes = _quantity_number(allocatable.get("memory") or capacity.get("memory"), 1)
        name = str(meta.get("name") or "node")
        return {
            "external_id": f"node/{name}"[:255],
            "name": name,
            "ip_address": ip or name,
            "cluster_name": "Kubernetes",
            "status": "online" if ready else "offline",
            "cpu_model": str((status.get("nodeInfo") or {}).get("architecture") or ""),
            "cpu_cores": int(cpu),
            "cpu_mhz": 0,
            "cpu_usage": None,
            "memory_total_mb": round(mem_bytes / 1024 / 1024, 2),
            "memory_used_mb": 0,
            "memory_usage": None,
            "storage_total_gb": 0,
            "storage_used_gb": 0,
            "storage_usage": None,
            "vm_count": 0,
            "uptime_seconds": 0,
            "extra": {"kubelet_version": (status.get("nodeInfo") or {}).get("kubeletVersion") or ""},
        }

    def _pod(self, item: Dict[str, Any]) -> Dict[str, Any]:
        meta = item.get("metadata") or {}
        spec = item.get("spec") or {}
        status = item.get("status") or {}
        name = str(meta.get("name") or "pod")
        namespace = str(meta.get("namespace") or "default")
        phase = str(status.get("phase") or "Unknown")
        node = str(spec.get("nodeName") or "")
        pod_ip = str(status.get("podIP") or "")
        vcpu = 0.0
        memory_mb = 0.0
        images = []
        for container in (spec.get("containers") or []):
            resources = container.get("resources") or {}
            requests = resources.get("requests") or {}
            limits = resources.get("limits") or {}
            vcpu += max(_quantity_number(requests.get("cpu"), 1), _quantity_number(limits.get("cpu"), 1))
            memory_mb += max(
                _quantity_number(requests.get("memory"), 1024 ** 2),
                _quantity_number(limits.get("memory"), 1024 ** 2),
            )
            if container.get("image"):
                images.append(str(container.get("image")))
        return {
            "external_id": f"pod/{namespace}/{name}"[:255],
            "name": f"{namespace}/{name}"[:255],
            "host_name": f"node/{node}" if node else "",
            "power_state": "running" if phase == "Running" else "stopped",
            "vcpu": max(1, int(vcpu + 0.9999)) if vcpu > 0 else 0,
            "memory_mb": round(memory_mb, 2),
            "disk_total_gb": 0,
            "disk_used_gb": 0,
            "disk_usage": None,
            "nic_count": 1 if pod_ip else 0,
            "ip_addresses": [pod_ip] if pod_ip else [],
            "guest_os": images[0] if images else "",
            "tools_status": phase,
            "cpu_usage": None,
            "memory_usage": None,
            "net_rx_bps": 0,
            "net_tx_bps": 0,
            "extra": {"namespace": namespace, "phase": phase},
        }

    def collect(self) -> Dict[str, Any]:
        version = self._request("/version")
        nodes = self._nodes()
        pods = self._pods()
        hosts = [self._node(item) for item in nodes if isinstance(item, dict)]
        host_by_name = {host["external_id"]: host for host in hosts}
        vms = []
        for item in pods:
            if not isinstance(item, dict):
                continue
            vm = self._pod(item)
            if vm.get("host_name") in host_by_name:
                host_by_name[vm["host_name"]]["vm_count"] += 1
            vms.append(vm)
        return {
            "hosts": hosts,
            "vms": vms,
            "version": version.get("gitVersion") or "",
        }


def _adapter_for(platform: VirtualPlatform, password: str):
    if platform.platform_type == "vmware":
        return VMwareAdapter(platform, password)
    if platform.platform_type == "kvm":
        return KvmSshAdapter(platform, password)
    if platform.platform_type == "cas":
        return CasAdapter(platform, password)
    if platform.platform_type == "proxmox":
        return ProxmoxAdapter(platform, password)
    if platform.platform_type == "docker":
        return DockerEngineAdapter(platform, password)
    if platform.platform_type == "kubernetes":
        return KubernetesAdapter(platform, password)
    raise VirtualizationError(f"暂不支持的平台类型：{platform.platform_type}")


def _platform_password(platform: VirtualPlatform, password: Optional[str] = None) -> str:
    if password is not None and password != "":
        return password
    if platform.platform_type == "docker":
        # Docker Engine 可以关闭认证；此时允许空密码
        return decrypt_password(platform.password_enc) if platform.password_enc else ""
    if not platform.password_enc:
        if platform.platform_type == "kubernetes":
            raise VirtualizationError("Kubernetes 未配置 Bearer Token")
        raise VirtualizationError("平台密码未配置")
    return decrypt_password(platform.password_enc)


def backfill_primary_ips(db: Session) -> None:
    """为旧虚拟机快照补齐主 IP 和自然排序键，确保 IP 排序对历史数据也生效。"""
    rows = (
        db.query(VirtualMachine)
        .filter(or_(
            VirtualMachine.primary_ip.is_(None),
            VirtualMachine.primary_ip == "",
            VirtualMachine.ip_sort_key.is_(None),
            VirtualMachine.ip_sort_key == "",
        ))
        .all()
    )
    changed = False
    for row in rows:
        ips = row.ip_addresses if isinstance(row.ip_addresses, list) else []
        first = str(row.primary_ip or "").strip() or next(
            (str(ip).strip() for ip in ips if str(ip).strip()), ""
        )
        if first:
            row.primary_ip = first[:45]
            row.ip_sort_key = _ip_sort_key(first)
            changed = True
    if changed:
        db.commit()


def test_platform(platform: VirtualPlatform, password: Optional[str] = None) -> Dict[str, Any]:
    secret = _platform_password(platform, password)
    adapter = _adapter_for(platform, secret)
    return adapter.test()


def _kvm_cpu_usage(
    previous: Optional[VirtualMachine], data: Dict[str, Any]
) -> Optional[float]:
    cpu_time = data.get("cpu_time_ns")
    if cpu_time is None:
        return data.get("cpu_usage")
    if not previous or not previous.cpu_time_ns or not previous.sample_at:
        return None
    now = datetime.utcnow()
    elapsed = (now - previous.sample_at).total_seconds()
    if elapsed <= 0:
        return previous.cpu_usage
    delta = _int(cpu_time) - _int(previous.cpu_time_ns)
    if delta <= 0:
        return 0.0
    vcpu = max(1, _int(data.get("vcpu"), 1))
    return round(max(0.0, min(100.0, delta / (elapsed * 1_000_000_000 * vcpu) * 100)), 2)


def sync_platform(db: Session, platform: VirtualPlatform, password: Optional[str] = None) -> Dict[str, Any]:
    """全量同步一个平台；异常时记录错误并抛出。"""
    try:
        secret = _platform_password(platform, password)
        adapter = _adapter_for(platform, secret)
        payload = adapter.collect()
        hosts_data = payload.get("hosts") or []
        vms_data = payload.get("vms") or []
        now = datetime.utcnow()

        existing_hosts = {
            row.external_id: row
            for row in db.query(VirtualHost).filter(VirtualHost.platform_id == platform.id).all()
        }
        host_map: Dict[str, VirtualHost] = {}
        for data in hosts_data:
            ext = str(data.get("external_id") or "")
            if not ext:
                continue
            row = existing_hosts.get(ext)
            if not row:
                row = VirtualHost(platform_id=platform.id, external_id=ext, name=data.get("name") or ext)
                db.add(row)
                db.flush()
            row.name = data.get("name") or ext
            row.ip_address = str(data.get("ip_address") or "").strip()[:45] or row.name[:45]
            row.cluster_name = data.get("cluster_name") or ""
            row.status = data.get("status") or "unknown"
            row.cpu_model = data.get("cpu_model") or ""
            row.cpu_cores = _int(data.get("cpu_cores"), 0)
            row.cpu_mhz = _float(data.get("cpu_mhz"))
            row.cpu_usage = data.get("cpu_usage")
            row.memory_total_mb = _float(data.get("memory_total_mb"))
            row.memory_used_mb = _float(data.get("memory_used_mb"))
            row.memory_usage = data.get("memory_usage")
            row.storage_total_gb = _float(data.get("storage_total_gb"))
            row.storage_used_gb = _float(data.get("storage_used_gb"))
            row.storage_usage = data.get("storage_usage")
            row.net_rx_bps = _float(data.get("net_rx_bps"))
            row.net_tx_bps = _float(data.get("net_tx_bps"))
            row.vm_count = _int(data.get("vm_count"), 0)
            row.uptime_seconds = _int(data.get("uptime_seconds"), 0)
            row.last_seen = now
            row.extra = data.get("extra") or {}
            host_map[ext] = row
        db.flush()
        host_map_by_name = {row.name: row for row in host_map.values()}

        existing_vms = {
            row.external_id: row
            for row in db.query(VirtualMachine).filter(VirtualMachine.platform_id == platform.id).all()
        }
        seen_vms = set()
        for data in vms_data:
            ext = str(data.get("external_id") or "")
            if not ext:
                continue
            seen_vms.add(ext)
            row = existing_vms.get(ext)
            if not row:
                row = VirtualMachine(platform_id=platform.id, external_id=ext, name=data.get("name") or ext)
                db.add(row)
                db.flush()
            host_name = data.get("host_name") or ""
            host_row = host_map.get(host_name) or host_map_by_name.get(host_name)
            row.host_id = host_row.id if host_row else None
            row.name = data.get("name") or ext
            row.power_state = data.get("power_state") or "unknown"
            row.vcpu = _int(data.get("vcpu"), 0)
            row.memory_mb = _float(data.get("memory_mb"))
            row.disk_total_gb = _float(data.get("disk_total_gb"))
            row.disk_used_gb = _float(data.get("disk_used_gb"))
            row.disk_usage = data.get("disk_usage")
            row.nic_count = _int(data.get("nic_count"), 0)
            row.ip_addresses = data.get("ip_addresses") or []
            row.primary_ip = next(
                (str(ip).strip()[:45] for ip in row.ip_addresses if str(ip).strip()), ""
            )
            row.ip_sort_key = _ip_sort_key(row.primary_ip)
            row.guest_os = data.get("guest_os") or ""
            row.tools_status = data.get("tools_status") or ""
            row.cpu_usage = _kvm_cpu_usage(row, data) if platform.platform_type == "kvm" else data.get("cpu_usage")
            row.memory_usage = data.get("memory_usage")
            row.net_rx_bps = _float(data.get("net_rx_bps"))
            row.net_tx_bps = _float(data.get("net_tx_bps"))
            if data.get("cpu_time_ns") is not None:
                row.cpu_time_ns = _int(data.get("cpu_time_ns"))
                row.sample_at = now
            row.last_seen = now
            row.extra = data.get("extra") or {}

        if seen_vms:
            db.query(VirtualMachine).filter(
                VirtualMachine.platform_id == platform.id,
                ~VirtualMachine.external_id.in_(seen_vms),
            ).delete(synchronize_session=False)
        else:
            db.query(VirtualMachine).filter(VirtualMachine.platform_id == platform.id).delete(
                synchronize_session=False
            )

        seen_hosts = {str(item.get("external_id")) for item in hosts_data if item.get("external_id")}
        if seen_hosts:
            db.query(VirtualHost).filter(
                VirtualHost.platform_id == platform.id,
                ~VirtualHost.external_id.in_(seen_hosts),
            ).delete(synchronize_session=False)
        else:
            db.query(VirtualHost).filter(VirtualHost.platform_id == platform.id).delete(
                synchronize_session=False
            )

        platform.last_sync_at = now
        platform.last_sync_status = "success"
        platform.last_error = ""
        platform.last_health = payload.get("health") or {}
        db.commit()
        alert_result = {"created": 0, "resolved": 0, "active": 0}
        try:
            alert_result = virtualization_alerts.evaluate_platform(db, platform.id, now)
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.warning("虚拟机告警评估失败 %s: %s", platform.name, exc)
        return {
            "platform": platform.name,
            "hosts": len(hosts_data),
            "vms": len(vms_data),
            "version": payload.get("version") or "",
            "synced_at": now.isoformat(),
            "alerts": alert_result,
        }
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        try:
            platform.last_sync_status = "failed"
            platform.last_error = str(exc)[:500]
            db.commit()
            try:
                virtualization_alerts.evaluate_platform(db, platform.id)
            except Exception as alert_exc:  # noqa: BLE001
                db.rollback()
                logger.warning("平台告警评估失败 %s: %s", platform.name, alert_exc)
        except Exception:  # noqa: BLE001
            db.rollback()
        if isinstance(exc, VirtualizationError):
            raise
        raise VirtualizationError(str(exc)) from exc


def sync_due_platforms() -> None:
    """调度器线程入口：创建独立 Session，顺序同步到期平台。"""
    db = SessionLocal()
    try:
        now = datetime.utcnow()
        platforms = db.query(VirtualPlatform).filter(VirtualPlatform.enabled.is_(True)).all()
        for platform in platforms:
            interval = max(1, _int(platform.sync_interval_minutes, 5))
            due = not platform.last_sync_at or now - platform.last_sync_at >= timedelta(minutes=interval)
            if not due:
                continue
            try:
                sync_platform(db, platform)
            except Exception as exc:  # noqa: BLE001
                logger.warning("虚拟化平台同步失败 %s: %s", platform.name, exc)
    finally:
        db.close()


class VirtualizationScheduler:
    def __init__(self):
        self._task: Optional[asyncio.Task] = None
        self._stopping = False

    async def start(self, _shutdown_event=None) -> None:
        if self._task and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._stopping = True
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
            self._task = None

    async def _loop(self) -> None:
        await asyncio.sleep(20)
        while not self._stopping:
            try:
                await asyncio.to_thread(sync_due_platforms)
            except Exception as exc:  # noqa: BLE001
                logger.debug("虚拟化调度异常: %s", exc)
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break


scheduler = VirtualizationScheduler()
