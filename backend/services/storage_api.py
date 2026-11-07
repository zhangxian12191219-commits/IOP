"""戴尔 PowerVault ME5 只读 REST/XML API 采集。

ME5 的 SNMP 代理通常只暴露 MIB-II，无法读取控制器、传感器和磁盘健康。
本模块使用存储管理只读账号通过 HTTPS XML API 读取硬件状态，仅执行 GET。
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

import requests
import urllib3

from ..models.models import Device
from .virtualization_crypto import decrypt_password

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


class StorageApiError(RuntimeError):
    pass


def is_dell_storage(device: Device) -> bool:
    vendor = str(getattr(device, "vendor", "") or "").lower()
    model = str(getattr(device, "model", "") or "").upper()
    return (
        str(getattr(device, "device_type", "") or "").lower() == "storage"
        and ("dell" in vendor or "戴尔" in vendor)
        and ("ME" in model or "POWERVAULT" in model)
    )


def _props(obj: ET.Element) -> Dict[str, str]:
    return {
        str(item.attrib.get("name") or ""): (item.text or "").strip()
        for item in obj.findall("PROPERTY")
        if item.attrib.get("name")
    }


def _objects(root: ET.Element, basetype: str) -> List[Dict[str, str]]:
    return [
        _props(obj)
        for obj in root.findall(".//OBJECT")
        if str(obj.attrib.get("basetype") or "") == basetype
    ]


def _number(value: Any) -> Optional[float]:
    match = re.search(r"-?\d+(?:\.\d+)?", str(value or ""))
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _size_gb(value: Any) -> Optional[float]:
    text = str(value or "").strip()
    number = _number(text)
    if number is None:
        return None
    upper = text.upper()
    if "TB" in upper:
        return round(number * 1024, 2)
    if "MB" in upper:
        return round(number / 1024, 2)
    return round(number, 2)


def _speed_bps(value: Any) -> Optional[float]:
    text = str(value or "").strip().upper()
    number = _number(text)
    if number is None:
        return None
    if "GB" in text or "GBPS" in text:
        return number * 1_000_000_000
    if "MB" in text or "MBPS" in text:
        return number * 1_000_000
    if "KB" in text:
        return number * 1_000
    return number


def _status_ok(value: str) -> bool:
    text = str(value or "").strip().lower()
    return text in ("", "ok", "up", "operational", "healthy", "normal", "redundant")


def _port_objects(root: ET.Element) -> List[Dict[str, str]]:
    """端口主记录和下一条 iscsi-port/fc-port 详情按顺序配对。"""
    result: List[Dict[str, str]] = []
    pending: Optional[Dict[str, str]] = None
    for obj in root.findall(".//OBJECT"):
        basetype = str(obj.attrib.get("basetype") or "")
        props = _props(obj)
        if basetype == "port":
            if pending:
                result.append(pending)
            pending = dict(props)
        elif basetype in ("iscsi-port", "fc-port", "sas-port") and pending is not None:
            pending.update(props)
        elif pending:
            result.append(pending)
            pending = None
    if pending:
        result.append(pending)
    return result


class DellStorageClient:
    def __init__(self, device: Device):
        self.device = device
        self.base_url = f"https://{device.ip_address}:{int(device.storage_api_port or 443)}"
        self.username = str(device.storage_username or "").strip()
        self.password = decrypt_password(device.storage_password_enc or "")
        self.session = requests.Session()
        self.session.verify = False
        self.session.timeout = 10
        self.session_key = ""

    def close(self) -> None:
        self.session.close()

    def _get_xml(self, path: str) -> ET.Element:
        response = self.session.get(
            f"{self.base_url}{path}",
            headers={"datatype": "xml", **({"sessionkey": self.session_key} if self.session_key else {})},
            timeout=12,
            verify=False,
        )
        if response.status_code != 200:
            raise StorageApiError(f"存储 API {path} 返回 HTTP {response.status_code}")
        try:
            return ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise StorageApiError(f"存储 API {path} 返回内容不是 XML") from exc

    def login(self) -> None:
        if not self.username or not self.password:
            raise StorageApiError("未配置存储只读账号")
        response = self.session.get(
            f"{self.base_url}/api/login/",
            auth=(self.username, self.password),
            headers={"legacy-username": self.username, "datatype": "xml"},
            timeout=12,
            verify=False,
        )
        if response.status_code != 200:
            raise StorageApiError(f"存储只读账号认证失败（HTTP {response.status_code}）")
        try:
            root = ET.fromstring(response.content)
        except ET.ParseError as exc:
            raise StorageApiError("存储登录返回内容不是 XML") from exc
        values = {}
        for obj in root.findall(".//OBJECT"):
            values.update(_props(obj))
        if str(values.get("response-type") or "").lower() != "success":
            raise StorageApiError(str(values.get("response") or "存储只读账号认证失败"))
        self.session_key = str(values.get("response") or "").strip()
        if not self.session_key:
            raise StorageApiError("存储登录未返回会话密钥")

    def fetch(self) -> Dict[str, Any]:
        self.login()
        try:
            ports_root = self._get_xml("/api/show/ports")
            return {
                "system": _objects(self._get_xml("/api/show/system"), "system"),
                "controllers": _objects(self._get_xml("/api/show/controllers"), "controllers"),
                "enclosures": _objects(self._get_xml("/api/show/enclosures"), "enclosures"),
                "drives": _objects(self._get_xml("/api/show/disks"), "drives"),
                "fans": _objects(self._get_xml("/api/show/fans"), "fan"),
                "power_supplies": (
                    _objects(self._get_xml("/api/show/power-supplies"), "power-supply")
                    or _objects(self._get_xml("/api/show/power-supplies"), "power-supplies")
                ),
                "network_parameters": _objects(self._get_xml("/api/show/network-parameters"), "network-parameters"),
                "ports": _port_objects(ports_root),
            }
        finally:
            self.close()


def _component_status(health: str, status: str) -> str:
    if not _status_ok(health) and health:
        return health
    if not _status_ok(status) and status:
        return status
    return "正常"


def collect_dell_storage(device: Device) -> Dict[str, Any]:
    """采集并转换为现有 DeviceMetric.components 结构。"""
    raw = DellStorageClient(device).fetch()
    system = (raw["system"] or [{}])[0]
    controllers = raw["controllers"]
    enclosures = raw["enclosures"]
    drives = raw["drives"]
    fans = raw["fans"]
    psus = raw["power_supplies"]

    cpus: List[Dict[str, Any]] = []
    memory_modules: List[Dict[str, Any]] = []
    for index, controller in enumerate(controllers, 1):
        cid = controller.get("controller-id") or str(index)
        cpu_type = controller.get("sc-cpu-type") or "未知"
        cpu_speed = controller.get("sc-cpu-speed") or ""
        cpus.append({
            "index": index,
            "name": f"控制器 {cid}",
            "model": f"{cpu_type}{f' @ {cpu_speed} MHz' if cpu_speed else ''}",
            "cores": None,
            "threads": None,
            "status_label": f"控制器 {_component_status(controller.get('health'), controller.get('status'))}",
        })
        memory_mb = _number(controller.get("system-memory-size"))
        if memory_mb:
            memory_modules.append({
                "index": index,
                "name": f"控制器 {cid} 系统内存",
                "bank": f"Controller {cid}",
                "size_gb": round(memory_mb / 1024, 1),
              })

    temperatures: List[Dict[str, Any]] = []
    for index, enclosure in enumerate(enclosures, 1):
        temp = _number(enclosure.get("dctemp"))
        if temp is not None and temp > 0:
            temperatures.append({
                "index": len(temperatures) + 1,
                "name": f"机箱 {enclosure.get('enclosure-id', index)} 温度",
                "kind": "ambient",
                "value": temp,
                "unit": "°C",
            })
    disk_temps = []
    for index, disk in enumerate(drives, 1):
        temp = _number(disk.get("temperature"))
        if temp is not None and temp > 0:
            disk_temps.append({
                "index": 0,
                "name": f"磁盘 {disk.get('location') or disk.get('slot') or index} 温度",
                "kind": "disk",
                "value": temp,
                "unit": "°C",
            })
    disk_temps.sort(key=lambda item: float(item.get("value") or 0), reverse=True)
    for item in disk_temps[:8]:
        item["index"] = len(temperatures) + 1
        temperatures.append(item)

    fan_rows: List[Dict[str, Any]] = []
    for index, fan in enumerate(fans, 1):
        speed = _number(fan.get("speed"))
        fan_rows.append({
            "index": index,
            "name": fan.get("location") or fan.get("name") or f"风扇 {index}",
            "value": speed,
            "unit": "RPM",
            "percent": None,
            "status_label": _component_status(fan.get("health"), fan.get("status")),
        })

    psu_rows: List[Dict[str, Any]] = []
    enclosure_power_total = sum(_number(item.get("enclosure-power")) or 0 for item in enclosures)
    for index, psu in enumerate(psus, 1):
        watts = _number(psu.get("power-supply"))
        psu_ok = _status_ok(psu.get("health")) and _status_ok(psu.get("status"))
        if watts is None and enclosure_power_total and psus:
            watts = round(enclosure_power_total / len(psus), 2)
        psu_rows.append({
            "index": index,
            "name": psu.get("name") or psu.get("location") or f"电源 {index}",
            "model": psu.get("model") or "",
            "status": "ok" if psu_ok else "fault",
            "status_label": _component_status(psu.get("health"), psu.get("status")),
            "watts": watts,
            "rating_watts": None,
        })

    disk_rows: List[Dict[str, Any]] = []
    disk_total_gb = 0.0
    disk_fault_count = 0
    for index, disk in enumerate(drives, 1):
        health = str(disk.get("health") or "").strip()
        state = str(disk.get("state") or "").strip()
        status = str(disk.get("status") or "").strip()
        reason = str(disk.get("health-reason") or "").strip()
        reason_lower = reason.lower()
        spun_down = (
            "spun down" in reason_lower
            or "spin down" in reason_lower
            or "standby" in state.lower()
        )
        fault = (not spun_down) and (
            (health and not _status_ok(health))
            or any(
                word in f"{state} {status}".lower()
                for word in ("fault", "failed", "degraded", "critical")
            )
        )
        if fault:
            disk_fault_count += 1
        size_gb = _size_gb(disk.get("size"))
        if size_gb:
            disk_total_gb += size_gb
        if spun_down:
            label = "在位 · 休眠（已降速）"
        elif fault:
            label = f"在位 · {health or state or status or '故障'}"
            if reason and reason_lower != "the component is healthy.":
                label += f"：{reason}"
        else:
            label = "在位 · 正常"
        disk_rows.append({
            "index": index,
            "name": f"磁盘 {disk.get('location') or disk.get('slot') or index}",
            "model": disk.get("model") or "",
            "size_gb": size_gb,
            "status": "fault" if fault else ("standby" if spun_down else "ok"),
            "status_label": label,
            "temperature": _number(disk.get("temperature")),
        })

    summary = {
        "cpu_count": len(cpus),
        "memory_module_count": len(memory_modules),
        "memory_total_gb": round(sum(float(item.get("size_gb") or 0) for item in memory_modules), 1),
        "temperature_count": len(temperatures),
        "fan_count": len(fan_rows),
        "power_supply_count": len(psu_rows),
        "disk_count": len(disk_rows),
        "disk_total_gb": round(disk_total_gb, 1),
        "disk_fault_count": disk_fault_count,
    }
    components = {
        "vendor": "Dell PowerVault",
        "model": system.get("product-id") or device.model,
        "cpus": cpus,
        "memory_modules": memory_modules,
        "temperatures": temperatures,
        "fans": fan_rows,
        "power_supplies": psu_rows,
        "disks": disk_rows,
        "summary": summary,
    }

    max_temp = max((float(item["value"]) for item in temperatures if item.get("value") is not None), default=None)
    psu_failure = any(item.get("status") == "fault" for item in psu_rows)
    enclosure_power = enclosure_power_total
    custom = {
        "server_components": components,
        "storage_api": {
            "source": "Dell PowerVault ME5 XML API",
            "system_name": system.get("system-name") or "",
            "system_health": system.get("health") or "",
            "enclosure_power_w": round(enclosure_power, 2),
            "cache_memory_gb": round(
                sum((_number(item.get("cache-memory-size")) or 0) for item in controllers) / 1024,
                1,
            ),
            "disk_fault_count": disk_fault_count,
        },
    }
    if max_temp is not None:
        hottest = max(temperatures, key=lambda item: float(item.get("value") or 0))
        custom["temperature_sensor"] = {
            "value": max_temp,
            "name": hottest.get("name") or "存储温度",
            "kind": "disk" if hottest.get("kind") == "disk" else "ambient",
            "unit": "°C",
        }
    interfaces: List[Dict[str, Any]] = []
    ports = raw.get("ports") or []
    for index, port in enumerate(ports, 1):
        port_name = str(port.get("port") or port.get("durable-id") or f"port{index}")
        port_type = str(port.get("port-type") or port.get("media") or "port")
        speed = _speed_bps(port.get("actual-speed"))
        ip_address = str(port.get("ip-address") or "").strip()
        sfp = str(port.get("sfp-status") or "").strip()
        desc_parts = [port_type]
        if speed:
            desc_parts.append(f"{speed / 1_000_000_000:g}Gb" if speed >= 1_000_000_000 else f"{speed / 1_000_000:g}Mb")
        if ip_address:
            desc_parts.append(ip_address)
        if sfp:
            desc_parts.append(f"SFP {sfp}")
        interfaces.append({
            "index": f"storage-port-{port_name}",
            "name": f"{port.get('controller') or ''}-{port_name}".strip("-"),
            "type": port_type,
            "mtu": None,
            "speed": speed,
            "mac": port.get("mac-address") or None,
            "oper_status": "up" if _status_ok(port.get("status")) else "down",
            "admin_status": "up",
            "description": " · ".join(desc_parts),
            "in_octets": None,
            "out_octets": None,
            "in_errors": None,
            "out_errors": None,
        })
    for index, net in enumerate(raw.get("network_parameters") or [], 1):
        ip_address = str(net.get("ip-address") or "").strip()
        speed = _speed_bps(net.get("link-speed"))
        interfaces.append({
            "index": f"storage-mgmt-{net.get('durable-id') or index}",
            "name": f"管理口 {net.get('name') or net.get('durable-id') or index}",
            "type": "management",
            "mtu": None,
            "speed": speed,
            "mac": net.get("mac-address") or None,
            "oper_status": "up" if _status_ok(net.get("health")) else "down",
            "admin_status": "up",
            "description": f"管理口 · {ip_address}" if ip_address else "管理口",
            "in_octets": None,
            "out_octets": None,
            "in_errors": None,
            "out_errors": None,
        })
    up_ports = sum(1 for item in interfaces if item.get("oper_status") == "up")
    custom["storage_network"] = {
        "port_count": len(interfaces),
        "up_count": up_ports,
        "down_count": len(interfaces) - up_ports,
        "ports": [
            {"name": item["name"], "type": item["type"], "speed": item["speed"], "status": item["oper_status"], "ip": item["description"]}
            for item in interfaces
        ],
    }

    return {
        "temperature": max_temp,
        "power_status": "failure" if psu_failure else "normal",
        "disk_total": round(disk_total_gb * 1024, 2) if disk_total_gb else None,
        "custom": custom,
        "components": components,
        "interfaces": interfaces,
    }
