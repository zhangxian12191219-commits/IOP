"""SNMP 数据采集器 - 定时采集设备监控数据与机房温湿度并写入数据库"""
import asyncio
import json
import logging
import math
import random
import re
import socket
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import aiohttp
from sqlalchemy.orm import Session

from ..config import Config
from ..models.alert_rule import DeviceAlertRule
from ..models.models import (
    Device, DeviceMetric, DeviceInterface, InterfaceMetric, Alert,
)
from ..models.room import Cabinet, Room, RoomSensor, RoomSensorReading
from ..notify import notify_alert
from ..services import alert_rules
from ..services import alert_rules as alert_rule_service
from ..services.storage_api import collect_dell_storage, is_dell_storage
from ..services import alert_suppression
from ..services.alert_recovery import build_recovery_payload
from ..services.cache import invalidate_dashboard
from ..services.warranty_alerts import check_warranty_alerts
from .snmp_client import (
    H3C_CPU_USAGE_OID, H3C_MEMORY_USAGE_OID,
    HUAWEI_CPU_USAGE_OID, HUAWEI_MEMORY_USAGE_OID,
    SNMPClient, SNMPError,
)

try:
    import serial  # pyserial
except ImportError:  # pragma: no cover
    serial = None
try:
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover
    mqtt = None

logger = logging.getLogger(__name__)


class DataCollector:
    """设备指标采集器"""

    def __init__(self, db: Session):
        self.db = db
        self.running = False
        self._task: Optional[asyncio.Task] = None
        # 接口计数器上一次采样: {(device_id, if_index): (时间, in_octets, out_octets)}
        self._last_if_stats: Dict[Any, Any] = {}
        # 接口流量历史采样节流: {device_id: 上次写入时间}
        self._last_if_history: Dict[int, datetime] = {}
        self._last_if_prune: Optional[datetime] = None

    # ---------- 单设备采集 ----------
    async def collect_device(self, device: Device) -> Optional[Dict[str, Any]]:
        method = (getattr(device, "monitor_type", None) or "snmp").lower()
        if method in ("ping", "tcp"):
            return await self._collect_probe(device, method)

        # 戴尔 ME5/PowerVault 采用 API-only：优先采集 API，不再依赖 SNMP/MIB。
        if is_dell_storage(device) and device.storage_username and device.storage_password_enc:
            return await self._collect_dell_storage_api(device)

        # SNMPClient.from_device 会自动带上 SNMPv3 的 USM 参数
        client = SNMPClient.from_device(
            device,
            timeout=Config.SNMP_TIMEOUT,
            retries=Config.SNMP_RETRIES,
        )

        # 先探测可达性，不可达则记录离线告警并跳过
        try:
            info = await client.get_system_info()
        except SNMPError as exc:
            logger.warning("SNMP 会话初始化失败 %s: %s", device.ip_address, exc)
            info = {}

        if not info.get("sysdescr") and not info.get("sysname"):
            self._mark_offline(device)
            return None

        # 本次采集成功，关闭该设备此前未恢复的离线类告警
        self._recover_offline_alerts(device)

        cpu = await client.get_cpu_usage()
        mem = await client.get_memory_info()
        temp = await client.get_temperature()
        power = await client.get_power_status()

        # 设备如绑定 MIB 并配置了自定义 OID，优先用自定义 OID 覆盖对应指标
        overrides = await self._apply_custom_oids(
            client, getattr(device, "custom_oids", None) or {}
        )
        custom_metric_defs = list(getattr(device, "custom_metrics", None) or [])
        custom_metric_defs.extend(getattr(device, "server_sensors", None) or [])
        custom_values = await self._apply_custom_metrics(client, custom_metric_defs)
        storage_result = None
        storage_interfaces_saved = False
        if is_dell_storage(device) and device.storage_username and device.storage_password_enc:
            try:
                storage_result = await asyncio.to_thread(collect_dell_storage, device)
            except Exception as exc:  # noqa: BLE001
                logger.warning("戴尔存储 API 采集失败 %s: %s", device.ip_address, exc)
                custom_values["storage_api_error"] = str(exc)[:300]
        if "cpu" in overrides:
            cpu = overrides["cpu"]
        if "memory" in overrides:
            mem = {"usage": overrides["memory"], "total": None, "used": None}
        if "temperature" in overrides:
            temp = overrides["temperature"]
        if "power" in overrides:
            power = "normal" if overrides["power"] > 0 else "abnormal"

        metrics = {
            "cpu_usage": cpu,
            "memory_usage": mem.get("usage"),
            "memory_total": mem.get("total"),
            "memory_used": mem.get("used"),
            "disk_usage": None,
            "disk_total": None,
            "disk_used": None,
            "temperature": temp,
            "power_status": power,
            "uptime": info.get("uptime"),
            "custom": custom_values,
        }
        if storage_result:
            if storage_result.get("temperature") is not None:
                metrics["temperature"] = storage_result["temperature"]
            if storage_result.get("power_status"):
                metrics["power_status"] = storage_result["power_status"]
            if storage_result.get("disk_total"):
                metrics["disk_total"] = storage_result["disk_total"]
            components = storage_result.get("components") or {}
            summary = components.get("summary") or {}
            if summary.get("memory_total_gb"):
                metrics["memory_total"] = round(float(summary["memory_total_gb"]) * 1024, 2)
            custom_values.update(storage_result.get("custom") or {})
        try:
            disk_info = await client.get_disk_info()
            if disk_info:
                metrics["disk_usage"] = disk_info.get("usage")
                metrics["disk_total"] = disk_info.get("total_mb")
                metrics["disk_used"] = disk_info.get("used_mb")
                custom_values["disk_total_gb"] = round(float(disk_info.get("total_mb") or 0) / 1024, 2)
                custom_values["disk_used_gb"] = round(float(disk_info.get("used_mb") or 0) / 1024, 2)
        except Exception as exc:  # noqa: BLE001
            logger.debug("磁盘容量采集失败 %s: %s", device.ip_address, exc)
        if not metrics.get("disk_total") and custom_values.get("disk_total_gb"):
            try:
                metrics["disk_total"] = round(float(custom_values["disk_total_gb"]) * 1024, 2)
                metrics["disk_used"] = round(float(custom_values.get("disk_used_gb") or 0) * 1024, 2) or None
            except (TypeError, ValueError):
                pass

        # 服务器组件级明细：CPU/内存模块/风扇/电源/硬盘/各类温度分别保留
        if str(getattr(device, "device_type", "") or "").lower() == "server":
            try:
                components = await client.get_server_components()
                summary = (components or {}).get("summary") or {}
                if any(int(summary.get(key) or 0) > 0 for key in (
                    "cpu_count", "memory_module_count", "fan_count",
                    "power_supply_count", "disk_count", "temperature_count",
                )):
                    custom_values["server_components"] = components
                    temperatures = components.get("temperatures") or []
                    if temperatures and "temperature" not in overrides:
                        hottest = max(temperatures, key=lambda item: float(item.get("value") or 0))
                        metrics["temperature"] = float(hottest.get("value"))
                        custom_values["temperature_sensor"] = {
                            "value": float(hottest.get("value") or 0),
                            "name": str(hottest.get("name") or "温度传感器"),
                            "kind": str(hottest.get("kind") or "other"),
                            "unit": str(hottest.get("unit") or "°C"),
                        }
                    if not metrics.get("memory_total") and summary.get("memory_total_gb"):
                        metrics["memory_total"] = round(float(summary["memory_total_gb"]) * 1024, 2)
                    if not metrics.get("disk_total") and summary.get("disk_total_gb"):
                        metrics["disk_total"] = round(float(summary["disk_total_gb"]) * 1024, 2)
            except Exception as exc:  # noqa: BLE001
                logger.debug("服务器组件明细采集失败 %s: %s", device.ip_address, exc)

        self._save_metrics(device, metrics)
        self._check_alerts(device, metrics)
        self._check_storage_disk_alerts(device, metrics)

        # 接口与流量：存储 API 端口优先，避免把管理 Linux 的 eth0/eth1 当业务网卡
        if storage_result and storage_result.get("interfaces"):
            try:
                self._save_interfaces(device, storage_result["interfaces"])
                self._record_interface_history(device)
                storage_interfaces_saved = True
            except Exception as exc:  # noqa: BLE001
                logger.debug("保存存储接口失败 %s: %s", device.ip_address, exc)
        if not storage_interfaces_saved:
            try:
                interfaces = await client.get_interfaces()
                if interfaces:
                    self._save_interfaces(device, interfaces)
                    self._record_interface_history(device)
            except Exception as exc:
                logger.debug("采集接口失败 %s: %s", device.ip_address, exc)

        # 补充资产信息（仅当为空时）
        self._enrich_device(device, info)

        return metrics

    async def _collect_dell_storage_api(self, device: Device) -> Optional[Dict[str, Any]]:
        """戴尔 ME5 存储 API-only 采集：不读取 MIB、不执行自定义 OID。"""
        try:
            storage_result = await asyncio.to_thread(collect_dell_storage, device)
        except Exception as exc:  # noqa: BLE001
            logger.warning("戴尔存储 API 采集失败 %s: %s", device.ip_address, exc)
            self._save_metrics(device, {
                "cpu_usage": None, "memory_usage": None, "memory_total": None, "memory_used": None,
                "disk_usage": None, "disk_total": None, "disk_used": None,
                "temperature": None, "power_status": None, "uptime": None,
                "custom": {"storage_api_error": str(exc)[:500], "storage_api_mode": "api-only"},
            })
            self._mark_offline(device)
            return None

        components = storage_result.get("components") or {}
        summary = components.get("summary") or {}
        custom = dict(storage_result.get("custom") or {})
        custom["storage_api_mode"] = "api-only"
        custom["mib_disabled"] = True
        metrics = {
            "cpu_usage": None,
            "memory_usage": None,
            "memory_total": round(float(summary.get("memory_total_gb") or 0) * 1024, 2) or None,
            "memory_used": None,
            "disk_usage": None,
            "disk_total": storage_result.get("disk_total"),
            "disk_used": None,
            "temperature": storage_result.get("temperature"),
            "power_status": storage_result.get("power_status"),
            "uptime": None,
            "custom": custom,
        }
        self._recover_offline_alerts(device)
        self._save_metrics(device, metrics)
        self._check_alerts(device, metrics)
        self._check_storage_disk_alerts(device, metrics)
        if storage_result.get("interfaces"):
            try:
                self._save_interfaces(device, storage_result["interfaces"])
                self._record_interface_history(device)
            except Exception as exc:  # noqa: BLE001
                logger.debug("保存戴尔存储接口失败 %s: %s", device.ip_address, exc)
        # API 成功后彻底解除该设备的 MIB/OID 绑定，避免后续误走 SNMP 采集。
        if device.mib_id or device.custom_oids or device.custom_metrics or device.server_sensors:
            device.mib_id = None
            device.custom_oids = {}
            device.custom_metrics = []
            device.server_sensors = []
            try:
                self.db.commit()
            except Exception as exc:  # noqa: BLE001
                self.db.rollback()
                logger.warning("解除戴尔存储 MIB 绑定失败 %s: %s", device.ip_address, exc)
        return metrics

    async def _collect_probe(self, device: Device, method: str) -> Dict[str, Any]:
        """Ping / TCP 端口接入：不发起 SNMP，仅记录连通性和延迟。"""
        from ..website.monitor import WebsiteMonitor

        host = (device.ip_address or "").strip()
        timeout = max(1, int(Config.SNMP_TIMEOUT or 3))
        port = int(getattr(device, "tcp_port", None) or 80)
        monitor = WebsiteMonitor()
        if method == "tcp":
            result = await monitor.check_tcp(host, port, timeout=timeout)
            alive = bool(result.get("is_alive"))
            latency = result.get("response_time") or 0
            error = result.get("error_message") or ""
            target = f"{host}:{port}"
        else:
            result = await monitor.check_ping(host, timeout=timeout)
            alive = bool(result.get("is_alive"))
            latency = result.get("avg_latency") or result.get("response_time") or 0
            error = result.get("error_message") or ""
            target = host

        custom = {
            "probe_alive": 1 if alive else 0,
            "probe_latency_ms": round(float(latency or 0), 2),
            "probe_method": method,
            "probe_target": target,
            "probe_error": error[:200],
        }
        metrics = {
            "cpu_usage": None,
            "memory_usage": None,
            "memory_total": None,
            "memory_used": None,
            "disk_usage": None,
            "temperature": None,
            "power_status": None,
            "uptime": None,
            "custom": custom,
        }
        self._save_metrics(device, metrics)
        if not alive:
            self._mark_offline(device)
            logger.info("%s 探测不可达 %s: %s", method.upper(), target, error)
        else:
            self._recover_offline_alerts(device)
            logger.debug("%s 探测正常 %s: %.1fms", method.upper(), target, latency)
        return metrics

    async def _probe_reachability(self, device: Device) -> Dict[str, Any]:
        """轻量探测设备是否在线，不写入指标；用于离线告警恢复检查。"""
        method = (getattr(device, "monitor_type", None) or "snmp").lower()
        host = (device.ip_address or "").strip()
        timeout = max(1, int(Config.SNMP_TIMEOUT or 3))
        if method in ("ping", "tcp"):
            from ..website.monitor import WebsiteMonitor

            port = int(getattr(device, "tcp_port", None) or 80)
            monitor = WebsiteMonitor()
            result = (
                await monitor.check_tcp(host, port, timeout=timeout)
                if method == "tcp"
                else await monitor.check_ping(host, timeout=timeout)
            )
            return {
                "alive": bool(result.get("is_alive")),
                "method": method,
                "latency_ms": round(float(result.get("avg_latency") or result.get("response_time") or 0), 2),
                "error": result.get("error_message") or "",
            }
        client = SNMPClient.from_device(
            device,
            timeout=Config.SNMP_TIMEOUT,
            retries=Config.SNMP_RETRIES,
        )
        started = time.perf_counter()
        try:
            info = await client.get_system_info()
        except Exception as exc:  # noqa: BLE001
            return {
                "alive": False, "method": "snmp",
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "error": str(exc),
            }
        alive = bool(info.get("sysdescr") or info.get("sysname"))
        return {
            "alive": alive,
            "method": "snmp",
            "latency_ms": round((time.perf_counter() - started) * 1000, 1),
            "error": "" if alive else "SNMP 无系统信息响应",
        }

    async def recheck_device(self, device: Device) -> Dict[str, Any]:
        """手动/定时再次探测设备，在线时立即关闭未恢复的离线告警。"""
        result = await self._probe_reachability(device)
        recovered = 0
        if result.get("alive"):
            recovered = self._recover_offline_alerts(device)
        result["recovered"] = recovered
        return result

    def _offline_alert_types(self, device_id: int) -> List[str]:
        rule_ids = [
            row[0] for row in (
                self.db.query(DeviceAlertRule.id)
                .filter(
                    DeviceAlertRule.device_id == device_id,
                    DeviceAlertRule.metric == "offline",
                )
                .all()
            )
        ]
        return ["offline"] + [f"rule_{rule_id}" for rule_id in rule_ids]

    def _recover_offline_alerts(self, device: Device) -> int:
        alert_types = self._offline_alert_types(device.id)
        alerts = (
            self.db.query(Alert)
            .filter(
                Alert.device_id == device.id,
                Alert.resolved_at.is_(None),
                Alert.alert_type.in_(alert_types),
            )
            .all()
        )
        if not alerts:
            return 0
        now = datetime.utcnow()
        for alert in alerts:
            alert.is_acknowledged = True
            alert.resolved_at = now
            alert.resolution = "device_recovered"
        self.db.commit()
        invalidate_dashboard()
        logger.info("设备 %s 已恢复，自动关闭离线告警 %s 条", device.ip_address, len(alerts))
        return len(alerts)

    async def recover_offline_devices(self) -> int:
        """每 15 秒只探测仍有离线告警的设备，尽快同步恢复状态。"""
        offline_rule_ids = [
            row[0] for row in (
                self.db.query(DeviceAlertRule.id)
                .filter(
                    DeviceAlertRule.metric == "offline",
                )
                .all()
            )
        ]
        alert_types = ["offline"] + [f"rule_{rule_id}" for rule_id in offline_rule_ids]
        rows = (
            self.db.query(Alert.device_id)
            .filter(
                Alert.resolved_at.is_(None),
                Alert.alert_type.in_(alert_types),
            )
            .distinct()
            .all()
        )
        device_ids = [row[0] for row in rows if row[0]]
        if not device_ids:
            return 0
        devices = (
            self.db.query(Device)
            .filter(Device.id.in_(device_ids), Device.is_enabled == True)  # noqa: E712
            .all()
        )
        recovered = 0
        for device in devices:
            try:
                result = await self._probe_reachability(device)
                if result.get("alive"):
                    recovered += self._recover_offline_alerts(device)
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                logger.debug("离线告警恢复探测失败 %s: %s", device.ip_address, exc)
                self.db.rollback()
        return recovered

    async def _apply_custom_oids(
        self, client, custom: Dict[str, str]
    ) -> Dict[str, float]:
        """按设备配置的自定义 OID 读取指标（失败自动忽略，回退默认策略）"""
        if not isinstance(custom, dict) or not custom:
            return {}

        result: Dict[str, float] = {}
        for metric in ("cpu", "memory", "temperature", "power"):
            oid = custom.get(metric)
            if not oid:
                continue
            # H3C 内存 OID 是按模块返回的表格，不能按自定义标量取 max；
            # 交给 get_memory_info() 用 hh3cEntityExtMemSize 选择主模块。
            if metric == "memory" and str(oid).strip().startswith(H3C_MEMORY_USAGE_OID):
                logger.info("H3C 内存自定义 OID 使用主模块选择，跳过表 max: %s", oid)
                continue
            if metric == "memory" and str(oid).strip().startswith(HUAWEI_MEMORY_USAGE_OID):
                logger.info("华为内存自定义 OID 使用主用主控选择，跳过表 max: %s", oid)
                continue
            if metric == "cpu" and str(oid).strip().startswith((HUAWEI_CPU_USAGE_OID, H3C_CPU_USAGE_OID)):
                logger.info("CPU 自定义 OID 使用主模块选择，跳过表 max: %s", oid)
                continue
            # 这些是容量/空闲/已用字节数，不是百分比；不能当成内存使用率。
            if metric == "memory" and str(oid).strip().startswith((
                "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.6",   # 华为 hwEntityMemSize
                "1.3.6.1.4.1.25506.2.6.1.1.1.1.10",     # 华三 hh3cEntityExtMemSize
                "1.3.6.1.4.1.9.9.48.1.1.1.5",            # Cisco memory pool used
                "1.3.6.1.4.1.9.9.48.1.1.1.6",            # Cisco memory pool free
                "1.3.6.1.2.1.25.2.2",                     # HOST-RESOURCES 总内存
            )):
                logger.info("内存自定义 OID 是容量而非百分比，跳过: %s", oid)
                continue
            value = None
            try:
                value = await client.get_numeric(oid)
            except Exception as exc:  # noqa: BLE001
                logger.debug("自定义 OID 标量读取失败 %s %s: %s", metric, oid, exc)
            if value is None:
                try:
                    rows = await client.walk(oid)
                    table_values = [
                        float(v) for _, v in rows
                        if (isinstance(v, (int, float)) or str(v).strip().replace(".", "", 1).isdigit())
                    ]
                    if table_values:
                        value = max(table_values)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("自定义 OID 表读取失败 %s %s: %s", metric, oid, exc)
                    continue
            if value is None:
                logger.warning(
                    "自定义 OID 无数据，回退默认采集：%s %s -> %s",
                    client.host, metric, oid,
                )
                continue
            # 内存/CPU 使用率合理范围校验（0~100）
            if metric in ("cpu", "memory") and not 0 <= value <= 100:
                logger.warning(
                    "自定义 OID 数值超出 0~100，忽略：%s %s = %s", metric, oid, value
                )
                continue
            if metric == "temperature" and not -40 <= value <= 200:
                logger.warning(
                    "自定义温度超出合理范围，忽略：%s %s = %s", client.host, oid, value
                )
                continue
            result[metric] = value
        return result

    async def _apply_custom_metrics(self, client, metrics: List[Dict[str, Any]]) -> Dict[str, float]:
        """读取设备配置的自定义指标（光功率、风扇转速等任意 OID）

        支持 scale 系数换算；读取失败/无数据时跳过，不影响常规采集。
        """
        if not isinstance(metrics, list) or not metrics:
            return {}

        values: Dict[str, float] = {}
        for item in metrics[:50]:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            oid = str(item.get("oid") or "").strip()
            if not key or not oid:
                continue
            value = None
            try:
                value = await client.get_numeric(oid)
            except Exception as exc:  # noqa: BLE001
                logger.debug("自定义指标标量读取失败 %s %s: %s", key, oid, exc)
            if value is None:
                try:
                    rows = await client.walk(oid)
                    table_values = [
                        float(v) for _, v in rows
                        if (isinstance(v, (int, float)) or str(v).strip().replace(".", "", 1).isdigit())
                    ]
                    if table_values:
                        mode = str(item.get("aggregate") or "max").lower()
                        if mode == "sum":
                            value = sum(table_values)
                        elif mode == "avg":
                            value = sum(table_values) / len(table_values)
                        else:
                            value = max(table_values)
                except Exception as exc:  # noqa: BLE001
                    logger.debug("自定义指标表读取失败 %s %s: %s", key, oid, exc)
                    continue
            if value is None:
                logger.debug("自定义指标无数据 %s %s -> %s", client.host, key, oid)
                continue
            try:
                scale = float(item.get("scale") or 1)
            except (TypeError, ValueError):
                scale = 1
            if scale and scale != 1:
                value = value * scale
            values[key] = round(value, 3)
        return values

    # ---------- 机房温湿度传感器 ----------
    def _simulate_sensor(self, sensor: RoomSensor) -> tuple:
        """演示传感器：在合理范围内随机游走"""
        temp = sensor.last_temperature if sensor.last_temperature is not None else random.uniform(20.0, 24.0)
        hum = sensor.last_humidity if sensor.last_humidity is not None else random.uniform(42.0, 55.0)
        temp = min(33.0, max(16.0, temp + random.uniform(-0.6, 0.6)))
        hum = min(75.0, max(25.0, hum + random.uniform(-2.0, 2.0)))
        return round(temp, 1), round(hum, 1)

    @staticmethod
    def _sensor_number(value: Any) -> Optional[float]:
        """把 JSON 数值、数字字符串或 {"value": ...} 转成浮点数。"""
        if value is None:
            return None
        if isinstance(value, dict):
            for key in ("value", "current", "reading", "temperature", "humidity"):
                if key in value:
                    return DataCollector._sensor_number(value[key])
            return None
        if isinstance(value, (int, float)):
            return float(value)
        match = re.search(r"-?\d+(?:\.\d+)?", str(value))
        return float(match.group(0)) if match else None

    @staticmethod
    def _json_path(data: Any, path: str) -> Any:
        current = data
        for part in str(path or "").split("."):
            if not part:
                continue
            if isinstance(current, dict):
                current = current.get(part)
            elif isinstance(current, list) and part.isdigit():
                index = int(part)
                current = current[index] if 0 <= index < len(current) else None
            else:
                return None
        return current

    async def _read_sensor_xiaomi(self, sensor: RoomSensor) -> tuple:
        """读取米家/网关 HTTP JSON；支持点路径取值和可选设备 ID/Token。"""
        url = str(sensor.xiaomi_url or "").strip()
        if not url:
            return None, None
        headers = {"Accept": "application/json"}
        token = str(sensor.xiaomi_token or "").strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        params = {}
        device_id = str(sensor.xiaomi_device_id or "").strip()
        if device_id:
            params["device_id"] = device_id
        timeout = aiohttp.ClientTimeout(total=5)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers, params=params) as response:
                if response.status >= 400:
                    raise RuntimeError(f"小米网关 HTTP {response.status}")
                data = await response.json(content_type=None)
        temp = self._sensor_number(self._json_path(data, sensor.xiaomi_temperature_path or "temperature"))
        hum = self._sensor_number(self._json_path(data, sensor.xiaomi_humidity_path or "humidity"))
        return temp, hum

    @staticmethod
    def _modbus_crc16(data: bytes) -> bytes:
        crc = 0xFFFF
        for byte in data:
            crc ^= byte
            for _ in range(8):
                crc = (crc >> 1) ^ 0xA001 if crc & 1 else crc >> 1
        return crc.to_bytes(2, "little")

    @staticmethod
    def _decode_modbus_values(sensor: RoomSensor, values: List[int], start: int,
                              width: int, reg_temp: int, reg_hum: Optional[int]) -> tuple:
        def decode(value_register: int, signed: bool) -> Optional[float]:
            offset = value_register - start
            if offset < 0 or offset + width > len(values):
                return None
            if width == 2:
                words = values[offset:offset + 2]
                if str(sensor.word_order or "big") == "little":
                    words = list(reversed(words))
                raw = (words[0] << 16) | words[1]
                bits = 32
            else:
                raw = values[offset]
                bits = 16
            if signed and raw & (1 << (bits - 1)):
                raw -= 1 << bits
            return float(raw)

        temp = decode(reg_temp, bool(sensor.signed_temperature))
        hum = decode(int(reg_hum), False) if reg_hum is not None else None
        temp = None if temp is None else temp * float(sensor.temperature_scale or 1)
        hum = None if hum is None else hum * float(sensor.humidity_scale or 1)
        return temp, hum

    @classmethod
    def _modbus_read_sync(cls, sensor: RoomSensor) -> tuple:
        """通过 USB-RS485/串口读取 Modbus RTU 寄存器。"""
        if serial is None:
            raise RuntimeError("RS485 需要 pyserial，请安装 pyserial")
        port = str(sensor.serial_port or "").strip()
        if not port:
            return None, None
        slave = int(sensor.slave_id or 1)
        function = int(sensor.function_code or 3)
        if function not in (3, 4):
            raise RuntimeError("Modbus 功能码仅支持 03 / 04")
        width = int(sensor.register_count or 1)
        if width not in (1, 2):
            raise RuntimeError("寄存器数量仅支持 1 / 2")
        reg_temp = int(sensor.register_temperature or 0)
        reg_hum = sensor.register_humidity
        regs = [reg_temp] if reg_hum is None else [reg_temp, int(reg_hum)]
        start = min(regs)
        count = max(regs) + width - start
        body = bytes([slave, function]) + start.to_bytes(2, "big") + count.to_bytes(2, "big")
        request = body + cls._modbus_crc16(body)
        conn = serial.Serial(
            port=port,
            baudrate=int(sensor.baudrate or 9600),
            bytesize=int(sensor.bytesize or 8),
            parity=str(sensor.parity or "N").upper()[:1],
            stopbits=int(sensor.stopbits or 1),
            timeout=float(sensor.serial_timeout or 1.0),
        )
        try:
            conn.reset_input_buffer()
            conn.write(request)
            conn.flush()
            expected = 5 + count * 2
            response = conn.read(expected)
        finally:
            conn.close()
        if len(response) < 5:
            raise RuntimeError("RS485 无响应")
        if response[0] != slave or (response[1] & 0x7F) != function:
            raise RuntimeError("RS485 返回从站/功能码不匹配")
        if response[1] & 0x80:
            raise RuntimeError(f"Modbus 异常码 {response[2]}")
        if len(response) < 5 + count * 2 or cls._modbus_crc16(response[:-2]) != response[-2:]:
            raise RuntimeError("RS485 返回 CRC 校验失败")
        byte_count = response[2]
        if byte_count < count * 2 or len(response) < 3 + byte_count:
            raise RuntimeError("RS485 返回寄存器数量不足")
        values = [
            int.from_bytes(response[3 + i * 2: 5 + i * 2], "big")
            for i in range(byte_count // 2)
        ]

        return cls._decode_modbus_values(sensor, values, start, width, reg_temp, int(reg_hum) if reg_hum is not None else None)

    async def _read_sensor_rs485(self, sensor: RoomSensor) -> tuple:
        return await asyncio.to_thread(self._modbus_read_sync, sensor)

    @classmethod
    def _modbus_tcp_read_sync(cls, sensor: RoomSensor) -> tuple:
        """通过 Modbus TCP 读取温湿度寄存器。"""
        host = str(sensor.modbus_host or "").strip()
        if not host:
            return None, None
        port = int(sensor.modbus_port or 502)
        unit = int(sensor.modbus_unit_id or 1)
        function = int(sensor.function_code or 3)
        if function not in (3, 4):
            raise RuntimeError("Modbus TCP 功能码仅支持 03 / 04")
        width = int(sensor.register_count or 1)
        if width not in (1, 2):
            raise RuntimeError("寄存器数量仅支持 1 / 2")
        reg_temp = int(sensor.register_temperature or 0)
        reg_hum = sensor.register_humidity
        regs = [reg_temp] if reg_hum is None else [reg_temp, int(reg_hum)]
        start = min(regs)
        count = max(regs) + width - start
        transaction = random.randint(1, 65535)
        pdu = bytes([function]) + start.to_bytes(2, "big") + count.to_bytes(2, "big")
        mbap = transaction.to_bytes(2, "big") + b"\x00\x00" + (len(pdu) + 1).to_bytes(2, "big") + bytes([unit])
        request = mbap + pdu
        with socket.create_connection((host, port), timeout=float(sensor.modbus_timeout or 3.0)) as sock:
            sock.settimeout(float(sensor.modbus_timeout or 3.0))
            sock.sendall(request)
            response = sock.recv(7 + 2 + count * 2)
        if len(response) < 9:
            raise RuntimeError("Modbus TCP 无响应")
        if response[6] & 0x80:
            raise RuntimeError(f"Modbus TCP 异常码 {response[8] if len(response) > 8 else '?'}")
        byte_count = response[8]
        if byte_count < count * 2 or len(response) < 9 + byte_count:
            raise RuntimeError("Modbus TCP 返回寄存器数量不足")
        values = [
            int.from_bytes(response[9 + i * 2: 11 + i * 2], "big")
            for i in range(byte_count // 2)
        ]
        return cls._decode_modbus_values(
            sensor, values, start, width, reg_temp,
            int(reg_hum) if reg_hum is not None else None,
        )

    @staticmethod
    def _mqtt_payload_value(payload: bytes, path: str) -> Optional[float]:
        text = payload.decode("utf-8", errors="replace").strip()
        if not text:
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            data = text
        if isinstance(data, dict):
            return DataCollector._sensor_number(DataCollector._json_path(data, path or "temperature"))
        return DataCollector._sensor_number(data)

    @classmethod
    def _mqtt_read_sync(cls, sensor: RoomSensor) -> tuple:
        """订阅一次 MQTT 主题，等待一条 JSON/数值消息作为本轮读数。"""
        if mqtt is None:
            raise RuntimeError("MQTT 需要 paho-mqtt，请安装 paho-mqtt")
        host = str(sensor.mqtt_host or "").strip()
        topic = str(sensor.mqtt_topic or "").strip()
        if not host or not topic:
            return None, None
        result = {}
        event = threading.Event()
        client_id = str(sensor.mqtt_client_id or "").strip() or f"sensor-{sensor.id}-{random.randint(1000,9999)}"
        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        except AttributeError:  # paho-mqtt 1.x
            client = mqtt.Client(client_id=client_id)
        if sensor.mqtt_username:
            client.username_pw_set(str(sensor.mqtt_username), str(sensor.mqtt_password or ""))
        if sensor.mqtt_tls:
            client.tls_set()

        def on_connect(_client, _userdata, _flags, reason_code, _properties=None):
            if str(reason_code) in ("0", "Success"):
                _client.subscribe(topic, qos=0)

        def on_message(_client, _userdata, message):
            result["temperature"] = cls._mqtt_payload_value(message.payload, sensor.mqtt_temperature_path or "temperature")
            result["humidity"] = cls._mqtt_payload_value(message.payload, sensor.mqtt_humidity_path or "humidity")
            event.set()

        client.on_connect = on_connect
        client.on_message = on_message
        try:
            client.connect(host, int(sensor.mqtt_port or 1883), keepalive=10)
            client.loop_start()
            event.wait(float(sensor.mqtt_timeout or 5.0))
        finally:
            client.loop_stop()
            try:
                client.disconnect()
            except Exception:  # noqa: BLE001
                pass
        if not event.is_set():
            raise RuntimeError("MQTT 等待消息超时")
        return result.get("temperature"), result.get("humidity")

    async def _read_sensor_mqtt(self, sensor: RoomSensor) -> tuple:
        return await asyncio.to_thread(self._mqtt_read_sync, sensor)

    async def _read_sensor_snmp(self, sensor: RoomSensor) -> tuple:
        """通过 SNMP 读取传感器 OID（未配置的项返回 None）"""
        if not sensor.ip:
            return None, None
        client = SNMPClient(
            host=sensor.ip,
            community=sensor.community or "public",
            version=sensor.snmp_version or "v2c",
            port=sensor.port or 161,
            timeout=Config.SNMP_TIMEOUT,
            retries=Config.SNMP_RETRIES,
        )
        temp = None
        hum = None
        if sensor.oid_temperature:
            temp = await client.get_numeric(sensor.oid_temperature)
        if sensor.oid_humidity:
            hum = await client.get_numeric(sensor.oid_humidity)
        return temp, hum

    async def _collect_sensors(self) -> int:
        """采集所有启用的机房温湿度传感器"""
        sensors = (
            self.db.query(RoomSensor)
            .filter(RoomSensor.is_enabled == True)  # noqa: E712
            .all()
        )
        if not sensors:
            return 0

        ok = 0
        for sensor in sensors:
            try:
                source = (sensor.source or "demo").lower()
                if source == "snmp":
                    temp, hum = await self._read_sensor_snmp(sensor)
                elif source == "xiaomi":
                    temp, hum = await self._read_sensor_xiaomi(sensor)
                elif source == "rs485":
                    temp, hum = await self._read_sensor_rs485(sensor)
                elif source == "modbus_tcp":
                    temp, hum = await asyncio.to_thread(self._modbus_tcp_read_sync, sensor)
                elif source == "mqtt":
                    temp, hum = await self._read_sensor_mqtt(sensor)
                else:
                    temp, hum = self._simulate_sensor(sensor)

                if temp is None and hum is None:
                    continue

                if temp is not None:
                    sensor.last_temperature = round(temp, 1)
                if hum is not None:
                    sensor.last_humidity = round(hum, 1)
                sensor.last_updated = datetime.utcnow()

                self.db.add(RoomSensorReading(
                    sensor_id=sensor.id,
                    temperature=sensor.last_temperature,
                    humidity=sensor.last_humidity,
                    recorded_at=datetime.utcnow(),
                ))
                self.db.commit()
                self._trim_sensor_readings(sensor.id)
                ok += 1
            except Exception as exc:  # noqa: BLE001
                logger.debug("采集温湿度传感器失败 %s: %s", sensor.name, exc)
                self.db.rollback()

        if ok:
            logger.debug("本轮采集温湿度传感器 %s 个", ok)
        return ok

    def _trim_sensor_readings(self, sensor_id: int, keep: int = 2000) -> None:
        """只保留最近 N 条传感器读数"""
        try:
            total = self.db.query(RoomSensorReading).filter(
                RoomSensorReading.sensor_id == sensor_id
            ).count()
            if total <= keep:
                return
            cutoff_row = (
                self.db.query(RoomSensorReading)
                .filter(RoomSensorReading.sensor_id == sensor_id)
                .order_by(RoomSensorReading.recorded_at.desc())
                .offset(keep - 1)
                .first()
            )
            if cutoff_row and cutoff_row.recorded_at:
                self.db.query(RoomSensorReading).filter(
                    RoomSensorReading.sensor_id == sensor_id,
                    RoomSensorReading.recorded_at < cutoff_row.recorded_at,
                ).delete(synchronize_session=False)
                self.db.commit()
        except Exception as exc:  # noqa: BLE001
            logger.debug("清理传感器历史失败: %s", exc)
            self.db.rollback()

    async def collect_all(self) -> int:
        devices = self.db.query(Device).filter(Device.is_enabled == True).all()

        # 维保到期检查与设备采集解耦，每轮采集都执行
        try:
            for payload in check_warranty_alerts(self.db):
                notify_alert(payload)
        except Exception as exc:  # noqa: BLE001
            logger.warning("维保到期告警检查异常: %s", exc)
            self.db.rollback()

        # 机房温湿度传感器（与设备采集独立，失败不影响设备指标）
        try:
            await self._collect_sensors()
        except Exception as exc:  # noqa: BLE001
            logger.warning("温湿度传感器采集异常: %s", exc)
            self.db.rollback()

        if not devices:
            return 0

        # 演示设备（tags 含 demo）不发起真实 SNMP 请求，改为生成模拟指标
        demo_devices = [d for d in devices if d.tags and "demo" in d.tags]
        real_devices = [d for d in devices if not (d.tags and "demo" in d.tags)]

        for demo in demo_devices:
            try:
                self._append_demo_metric(demo)
                self._append_demo_interface_traffic(demo)
                self._record_interface_history(demo)
            except Exception as exc:  # noqa: BLE001
                logger.debug("写入演示指标失败 %s: %s", demo.name, exc)
                self.db.rollback()

        if not real_devices:
            return len(demo_devices)

        results = await asyncio.gather(
            *[self._safe_collect(d) for d in real_devices],
            return_exceptions=True,
        )
        return len(demo_devices) + sum(
            1 for r in results if r and not isinstance(r, Exception)
        )

    def _append_demo_metric(self, device: Device) -> None:
        """为演示设备生成一条模拟指标（在上一采样点基础上小幅波动）"""
        import random

        last = (
            self.db.query(DeviceMetric)
            .filter(DeviceMetric.device_id == device.id)
            .order_by(DeviceMetric.collected_at.desc())
            .first()
        )
        cpu = last.cpu_usage if last and last.cpu_usage is not None else 30.0
        mem = last.memory_usage if last and last.memory_usage is not None else 50.0
        temp = last.temperature if last and last.temperature is not None else 40.0
        total = last.memory_total if last and last.memory_total else 4096.0

        cpu = max(1.0, min(95.0, cpu + random.uniform(-3.5, 3.5)))
        mem = max(5.0, min(95.0, mem + random.uniform(-1.8, 1.8)))
        temp = max(20.0, min(90.0, temp + random.uniform(-0.8, 0.8)))

        custom = dict(last.custom or {}) if last else {}
        for sensor in (getattr(device, "server_sensors", None) or []):
            key = str(sensor.get("key") or "")
            kind = str(sensor.get("kind") or "value")
            if not key:
                continue
            if kind == "fault":
                custom[key] = 2 if random.random() < 0.08 else 1
            elif kind == "temperature":
                custom[key] = round(random.uniform(32, 78), 1)
            elif kind == "voltage":
                custom[key] = round(random.uniform(215, 245), 1)
            elif kind == "current":
                custom[key] = round(random.uniform(3, 12), 2)
            elif kind == "watts":
                custom[key] = round(random.uniform(320, 860), 0)
            elif kind == "percent":
                custom[key] = round(random.uniform(28, 86), 1)
            elif key.startswith("srv_fan"):
                custom[key] = round(random.uniform(2200, 6800), 0)

        self.db.add(DeviceMetric(
            device_id=device.id,
            cpu_usage=round(cpu, 2),
            memory_usage=round(mem, 2),
            memory_total=total,
            memory_used=round(total * mem / 100, 2),
            temperature=round(temp, 1),
            power_status="normal",
            uptime=(last.uptime or 0) + Config.COLLECTION_INTERVAL,
            custom=custom,
            collected_at=datetime.utcnow(),
        ))
        self.db.commit()

    def _append_demo_interface_traffic(self, device: Device) -> None:
        """为演示设备生成接口流量（累加计数器 + 计算 bps）"""
        import random

        rows = self.db.query(DeviceInterface).filter_by(device_id=device.id).all()
        if not rows:
            return

        elapsed = max(5, Config.COLLECTION_INTERVAL)
        changed = False
        for row in rows:
            if row.if_oper_status != "up":
                row.in_bps = 0.0
                row.out_bps = 0.0
                continue
            # 速率取接口带宽的 3%~35%
            cap = (row.if_speed or 100_000_000) * random.uniform(0.03, 0.35)
            row.in_bps = round(cap * random.uniform(0.8, 1.2), 2)
            row.out_bps = round(cap * random.uniform(0.6, 1.1), 2)
            row.in_octets = (row.in_octets or 0) + row.in_bps * elapsed / 8
            row.out_octets = (row.out_octets or 0) + row.out_bps * elapsed / 8
            row.in_errors = row.in_errors or 0
            row.out_errors = row.out_errors or 0
            row.updated_at = datetime.utcnow()
            changed = True

        if changed:
            self.db.commit()

    # ---------- 接口流量历史 ----------
    INTERFACE_HISTORY_INTERVAL = 300        # 5 分钟一个采样点
    INTERFACE_HISTORY_RETENTION_DAYS = 7    # 保留 7 天

    def _record_interface_history(self, device: Device) -> None:
        """按采样间隔保存所有接口的流量历史，并定期清理过期数据"""
        now = datetime.utcnow()
        last = self._last_if_history.get(device.id)
        if last and (now - last).total_seconds() < self.INTERFACE_HISTORY_INTERVAL:
            return

        rows = self.db.query(DeviceInterface).filter_by(device_id=device.id).all()
        if not rows:
            return

        # 演示设备首次生成历史时，回填最近 24h 的曲线，便于直接体验时间筛选
        has_history = (
            self.db.query(InterfaceMetric.id)
            .filter(InterfaceMetric.device_id == device.id)
            .first()
            is not None
        )
        if not has_history and device.tags and "demo" in device.tags:
            self._seed_demo_interface_history(device, rows, now)

        for row in rows:
            self.db.add(InterfaceMetric(
                device_id=device.id,
                interface_id=row.id,
                if_name=row.if_name,
                in_bps=row.in_bps,
                out_bps=row.out_bps,
                in_octets=row.in_octets,
                out_octets=row.out_octets,
                in_errors=row.in_errors,
                out_errors=row.out_errors,
                oper_status=row.if_oper_status,
                collected_at=now,
            ))
        self._last_if_history[device.id] = now
        self.db.commit()

        # 每小时清理一次超过保留期的历史
        if not self._last_if_prune or (now - self._last_if_prune).total_seconds() >= 3600:
            cutoff = now - timedelta(days=self.INTERFACE_HISTORY_RETENTION_DAYS)
            self.db.query(InterfaceMetric).filter(
                InterfaceMetric.collected_at < cutoff
            ).delete(synchronize_session=False)
            self.db.commit()
            self._last_if_prune = now

    def _seed_demo_interface_history(self, device: Device, rows: List[DeviceInterface], now: datetime) -> None:
        """仅演示设备：回填最近 24 小时、每 30 分钟一个点的接口流量"""
        import random

        for row in rows:
            if row.if_oper_status != "up":
                continue
            base_in = float(row.in_bps or (row.if_speed or 100_000_000) * 0.12)
            base_out = float(row.out_bps or base_in * 0.8)
            for step in range(48, 0, -1):
                point_time = now - timedelta(minutes=step * 30)
                wave = 0.72 + 0.28 * math.sin((step + (row.id % 17)) / 4.2)
                jitter = random.uniform(0.9, 1.1)
                in_bps = round(max(0, base_in * wave * jitter), 2)
                out_bps = round(max(0, base_out * wave * random.uniform(0.88, 1.12)), 2)
                self.db.add(InterfaceMetric(
                    device_id=device.id,
                    interface_id=row.id,
                    if_name=row.if_name,
                    in_bps=in_bps,
                    out_bps=out_bps,
                    in_octets=row.in_octets,
                    out_octets=row.out_octets,
                    in_errors=row.in_errors,
                    out_errors=row.out_errors,
                    oper_status="up",
                    collected_at=point_time,
                ))
        self.db.flush()


    async def _safe_collect(self, device: Device):
        try:
            return await self.collect_device(device)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error("采集设备 %s(%s) 失败: %s", device.name, device.ip_address, exc)
            try:
                self.db.rollback()
            except Exception:
                pass
            return None

    # ---------- 持久化 ----------
    def _save_metrics(self, device: Device, metrics: Dict[str, Any]) -> None:
        record = DeviceMetric(
            device_id=device.id,
            cpu_usage=metrics.get("cpu_usage"),
            memory_usage=metrics.get("memory_usage"),
            memory_total=metrics.get("memory_total"),
            memory_used=metrics.get("memory_used"),
            disk_usage=metrics.get("disk_usage"),
            disk_total=metrics.get("disk_total"),
            disk_used=metrics.get("disk_used"),
            temperature=metrics.get("temperature"),
            power_status=metrics.get("power_status"),
            uptime=metrics.get("uptime"),
            custom=metrics.get("custom") or {},
            collected_at=datetime.utcnow(),
        )
        self.db.add(record)
        self.db.commit()

    def _save_interfaces(self, device: Device, interfaces: List[Dict[str, Any]]) -> None:
        existing = {i.if_index: i for i in
                    self.db.query(DeviceInterface).filter_by(device_id=device.id).all()}
        seen = set()
        now = datetime.utcnow()

        for data in interfaces:
            idx = str(data.get("index"))
            seen.add(idx)
            row = existing.get(idx)
            if row is None:
                row = DeviceInterface(device_id=device.id, if_index=idx)
                self.db.add(row)
            row.if_name = data.get("name")
            row.if_type = str(data.get("type")) if data.get("type") is not None else None
            row.if_mac = data.get("mac")
            row.if_mtu = data.get("mtu")
            row.if_speed = float(data["speed"]) if data.get("speed") else None
            row.if_oper_status = data.get("oper_status")
            row.if_admin_status = data.get("admin_status")
            row.if_description = data.get("description")

            # 流量：保存计数器，并用相邻两次采样差值计算 bps
            in_octets = data.get("in_octets")
            out_octets = data.get("out_octets")
            row.in_octets = in_octets
            row.out_octets = out_octets
            row.in_errors = data.get("in_errors")
            row.out_errors = data.get("out_errors")

            key = (device.id, idx)
            prev = self._last_if_stats.get(key)
            if prev is not None and in_octets is not None and out_octets is not None:
                prev_ts, prev_in, prev_out = prev
                elapsed = (now - prev_ts).total_seconds()
                if elapsed >= 5:
                    if prev_in is not None and in_octets >= prev_in:
                        row.in_bps = round((in_octets - prev_in) * 8 / elapsed, 2)
                    if prev_out is not None and out_octets >= prev_out:
                        row.out_bps = round((out_octets - prev_out) * 8 / elapsed, 2)
            self._last_if_stats[key] = (now, in_octets, out_octets)
            row.updated_at = now

        # 删除已消失的接口
        for idx, row in existing.items():
            if idx not in seen:
                self.db.query(InterfaceMetric).filter(
                    InterfaceMetric.interface_id == row.id
                ).delete(synchronize_session=False)
                self.db.delete(row)
                self._last_if_stats.pop((device.id, idx), None)

        self.db.commit()

    def _enrich_device(self, device: Device, info: Dict[str, Any]) -> None:
        changed = False
        descr = info.get("sysdescr")
        if descr:
            if not device.vendor:
                device.vendor = self._guess_vendor(descr)
                changed = True
            if not device.model:
                device.model = descr.split("\n")[0][:200]
                changed = True
        if not device.location and info.get("syslocation"):
            device.location = info["syslocation"]
            changed = True
        if changed:
            device.updated_at = datetime.utcnow()
            self.db.commit()

    @staticmethod
    def _guess_vendor(descr: str) -> str:
        d = descr.lower()
        for key, name in (
            ("cisco", "Cisco"), ("huawei", "Huawei"), ("h3c", "H3C"),
            ("hpe", "HPE"), ("hp ", "HP"), ("juniper", "Juniper"),
            ("fortinet", "Fortinet"), ("ruijie", "Ruijie"), ("zte", "ZTE"),
            ("hills", "Hillstone"), ("topsec", "TopSec"), ("sangfor", "Sangfor"),
            ("palo alto", "Palo Alto"), ("linux", "Linux"), ("windows", "Windows"),
        ):
            if key in d:
                return name
        return "Unknown"

    def _device_location_context(self, device: Device) -> Dict[str, Any]:
        cabinet = self.db.query(Cabinet).filter(Cabinet.id == device.cabinet_id).first() if device.cabinet_id else None
        room = self.db.query(Room).filter(Room.id == cabinet.room_id).first() if cabinet else None
        return {
            # 设备资产 location 可能是 SNMP sysLocation 的 "unknown"，外发正文不再展示
            "room_name": room.name if room else "",
            "cabinet_name": cabinet.name if cabinet else "",
            "room_floor": room.floor if room else "",
            "room_location": room.location if room else "",
        }

    def _notify_device(self, device: Device, payload: Dict[str, Any]) -> None:
        payload.update(self._device_location_context(device))
        notify_alert(payload)

    def _recover_metric_alerts(self, device: Device, metrics: Dict[str, Any]) -> int:
        """指标恢复到阈值内时，自动把仍激活的告警标记为已恢复。"""
        active = (
            self.db.query(Alert)
            .filter(
                Alert.device_id == device.id,
                Alert.resolved_at.is_(None),
                Alert.alert_type != "offline",
            )
            .all()
        )
        if not active:
            return 0
        rule_ids = {alert.rule_id for alert in active if alert.rule_id}
        rules = {
            rule.id: rule
            for rule in self.db.query(DeviceAlertRule).filter(DeviceAlertRule.id.in_(rule_ids)).all()
        } if rule_ids else {}
        recovered = 0
        recovered_items = []
        for alert in active:
            rule = rules.get(alert.rule_id)
            recovered_value = None
            if rule:
                if rule.metric == "offline":
                    continue
                value = alert_rule_service.metric_value(rule, metrics)
                if value is None:
                    continue
                if alert_rule_service.condition_matches(value, rule.operator or "gt", rule.threshold or 0):
                    continue
                recovered_value = value
            elif alert.alert_type == "power":
                if metrics.get("power_status") != "normal":
                    continue
            elif alert.alert_type in ("cpu", "memory", "temperature", "disk"):
                value = metrics.get({
                    "cpu": "cpu_usage",
                    "memory": "memory_usage",
                    "temperature": "temperature",
                    "disk": "disk_usage",
                }[alert.alert_type])
                if value is None:
                    continue
                recovered_value = value
                threshold = {
                    "cpu": Config.CPU_THRESHOLD,
                    "memory": Config.MEMORY_THRESHOLD,
                    "temperature": Config.TEMPERATURE_THRESHOLD,
                    "disk": getattr(Config, "DISK_THRESHOLD", 90),
                }[alert.alert_type]
                if float(value) > float(threshold):
                    continue
            else:
                continue
            recovered_at = datetime.utcnow()
            alert.resolved_at = recovered_at
            alert.resolution = "metric_recovered"
            alert.is_acknowledged = True
            recovered_items.append((alert, rule, recovered_value, recovered_at))
            recovered += 1
        if recovered:
            self.db.commit()
            invalidate_dashboard()
            for recovered_alert, recovered_rule, recovered_value, recovered_at in recovered_items:
                try:
                    notify_alert(build_recovery_payload(
                        recovered_alert, device, recovered_rule, recovered_value, recovered_at,
                    ))
                except Exception:  # noqa: BLE001
                    logger.exception("发送恢复通知失败: %s", recovered_alert.id)
            logger.info("设备 %s 指标恢复，自动恢复告警 %s 条", device.ip_address, recovered)
        return recovered

    def _check_storage_disk_alerts(self, device: Device, metrics: Dict[str, Any]) -> None:
        """戴尔存储磁盘故障告警：任何故障盘都按紧急告警处理，恢复后自动关闭。"""
        if not is_dell_storage(device):
            return
        custom = metrics.get("custom") or {}
        components = custom.get("server_components") or {}
        disks = components.get("disks") if isinstance(components, dict) else None
        if not isinstance(disks, list):
            return
        faults = [item for item in disks if str(item.get("status") or "") == "fault"]
        active = (
            self.db.query(Alert)
            .filter(
                Alert.device_id == device.id,
                Alert.alert_type == "storage_disk_fault",
                Alert.resolved_at.is_(None),
            )
            .first()
        )
        if not faults:
            if active:
                active.resolved_at = datetime.utcnow()
                active.resolution = "storage_disk_recovered"
                active.is_acknowledged = True
                self.db.commit()
                invalidate_dashboard()
                try:
                    notify_alert({
                        "source": "device",
                        "source_id": active.id,
                        "level": "info",
                        "device_name": device.name,
                        "ip_address": device.ip_address,
                        "alert_type": "storage_disk_fault",
                        "message": f"{device.name} 存储磁盘故障已恢复",
                        "created_at": datetime.utcnow().isoformat(timespec="seconds"),
                    })
                except Exception:  # noqa: BLE001
                    logger.exception("发送存储磁盘恢复通知失败: %s", active.id)
            return

        details = []
        for item in faults[:12]:
            name = str(item.get("name") or "磁盘")
            reason = str(item.get("status_label") or "故障")
            details.append(f"{name}（{reason}）")
        more = f" 等 {len(faults)} 块" if len(faults) > 12 else ""
        message = f"戴尔存储磁盘故障 {len(faults)} 块：{'；'.join(details)}{more}"
        if active:
            changed = False
            if active.message != message:
                active.message = message
                changed = True
            if active.value != float(len(faults)):
                active.value = float(len(faults))
                changed = True
            if active.alert_level != "emergency":
                active.alert_level = "emergency"
                active.level_label = "紧急"
                changed = True
            if changed:
                self.db.commit()
                invalidate_dashboard()
            return

        alert = Alert(
            device_id=device.id,
            alert_type="storage_disk_fault",
            alert_level="emergency",
            level_label="紧急",
            message=message,
            value=float(len(faults)),
            threshold=0,
            created_at=datetime.utcnow(),
        )
        self.db.add(alert)
        self.db.commit()
        invalidate_dashboard()
        self._notify_device(device, {
            "source": "device",
            "source_id": alert.id,
            "level": "emergency",
            "device_name": device.name,
            "ip_address": device.ip_address,
            "alert_type": "storage_disk_fault",
            "message": message,
            "value": float(len(faults)),
            "threshold": 0,
            "created_at": datetime.utcnow().isoformat(timespec="seconds"),
        })

    def _check_alerts(self, device: Device, metrics: Dict[str, Any]) -> None:
        self._recover_metric_alerts(device, metrics)
        alerts: List[Alert] = []
        # 待通知的告警信息（提交后带 ID 分发）
        pending_notify: List[Dict[str, Any]] = []

        rules = (
            self.db.query(DeviceAlertRule)
            .filter(DeviceAlertRule.device_id == device.id, DeviceAlertRule.enabled == True)  # noqa: E712
            .all()
        )
        covered_metrics = {
            rule.metric for rule in rules
            if rule.metric in ("cpu_usage", "memory_usage", "temperature", "fan_speed", "disk_usage", "power")
        }
        # 组件温度规则（CPU2 Temp 等）也要覆盖内置“最高部件温度”，避免内置 80°C 抢先告警。
        for rule in rules:
            key = str(rule.custom_key or "")
            if rule.metric != "custom":
                continue
            if key in ("srv_cpu_temp", "srv_inlet_temp", "srv_exhaust_temp") or key.startswith("srv_component_temp_"):
                covered_metrics.add("temperature")
            elif key in ("srv_disk_usage", "srv_disk_used"):
                covered_metrics.add("disk_usage")
            elif key in ("srv_power_watts", "srv_power_voltage", "srv_power_current", "srv_power_status"):
                covered_metrics.add("power")

        # 自定义规则接管后，关闭此前由内置阈值产生且仍活动的同类告警，避免继续外发旧阈值。
        covered_alert_types = {
            "cpu_usage": "cpu", "memory_usage": "memory", "temperature": "temperature",
            "disk_usage": "disk", "power": "power",
        }
        superseded_types = {covered_alert_types[key] for key in covered_metrics if key in covered_alert_types}
        if superseded_types:
            stale_alerts = (
                self.db.query(Alert)
                .filter(
                    Alert.device_id == device.id,
                    Alert.alert_type.in_(superseded_types),
                    Alert.rule_id.is_(None),
                    Alert.resolved_at.is_(None),
                )
                .all()
            )
            if stale_alerts:
                now = datetime.utcnow()
                for stale in stale_alerts:
                    stale.resolved_at = now
                    stale.resolution = "superseded_by_custom_rule"
                    stale.is_acknowledged = True
                self.db.commit()
                invalidate_dashboard()

        def add_rule_alert(rule: DeviceAlertRule, value: float, offline: bool = False):
            alert_type = f"rule_{rule.id}"
            if alert_suppression.is_suppressed(
                self.db, "device", device_id=device.id,
                alert_type=alert_type, alert_level=rule.level,
            ):
                return
            dup = self.db.query(Alert).filter(
                Alert.device_id == device.id,
                Alert.alert_type == alert_type,
            ).first()
            if dup:
                return
            label = alert_rule_service.level_label(rule)
            metric_label = alert_rule_service.rule_metric_label(rule)
            unit = alert_rule_service.rule_unit(rule)
            message = (
                f"{rule.name}：{metric_label} 当前值 {value:g}{unit}，"
                f"条件 {alert_rule_service.condition_text(rule)}"
            )
            alerts.append(Alert(
                device_id=device.id,
                alert_type=alert_type,
                alert_level=rule.level,
                level_label=label,
                rule_id=rule.id,
                message=message,
                value=value,
                threshold=rule.threshold,
                created_at=datetime.utcnow(),
            ))
            pending_notify.append({
                "source": "device",
                "level": rule.level,
                "device_name": device.name,
                "ip_address": device.ip_address,
                "alert_type": alert_type,
                "message": message,
                "value": value,
                "threshold": rule.threshold,
                "created_at": datetime.utcnow().isoformat(timespec="seconds"),
                "channel_ids": rule.notify_channel_ids or [],
            })

        for rule in rules:
            if rule.metric == "offline":
                continue
            value = alert_rule_service.metric_value(rule, metrics)
            if value is None:
                continue
            if alert_rule_service.condition_matches(value, rule.operator, rule.threshold):
                add_rule_alert(rule, value)

        def add(kind: str, value: Optional[float], threshold: float, unit: str, label: str, metric_key: str, critical_threshold: Optional[float] = None):
            if metric_key in covered_metrics:
                return
            if value is None or value <= threshold:
                return
            level = "critical" if (critical_threshold is not None and value >= critical_threshold) or (critical_threshold is None and value > threshold * 1.15) else "warning"
            if alert_suppression.is_suppressed(
                self.db, "device", device_id=device.id,
                alert_type=kind, alert_level=level,
            ):
                return
            # 同类告警未确认时不重复刷屏
            dup = self.db.query(Alert).filter(
                Alert.device_id == device.id,
                Alert.alert_type == kind,
            ).first()
            if dup:
                return
            message = f"{label} {value}{unit} 超过阈值 {threshold}{unit}"
            alerts.append(Alert(
                device_id=device.id,
                alert_type=kind,
                alert_level=level,
                message=message,
                value=value,
                threshold=threshold,
                created_at=datetime.utcnow(),
            ))
            pending_notify.append({
                "source": "device",
                "level": level,
                "device_name": device.name,
                "ip_address": device.ip_address,
                "alert_type": kind,
                "message": message,
                "value": value,
                "threshold": threshold,
                "created_at": datetime.utcnow().isoformat(timespec="seconds"),
            })

        is_server = str(getattr(device, "device_type", "") or "").lower() == "server"
        if not is_server:
            add("cpu", metrics.get("cpu_usage"), Config.CPU_THRESHOLD, "%", "CPU使用率", "cpu_usage")
            add("memory", metrics.get("memory_usage"), Config.MEMORY_THRESHOLD, "%", "内存使用率", "memory_usage")
        add("disk", metrics.get("disk_usage"), getattr(Config, "DISK_THRESHOLD", 90), "%", "磁盘使用率", "disk_usage")
        sensor = (metrics.get("custom") or {}).get("temperature_sensor") or {}
        temp_name = str(sensor.get("name") or "").strip()
        temp_label = f"最高部件温度（{temp_name}）" if temp_name else "最高部件温度"
        add("temperature", metrics.get("temperature"), Config.TEMPERATURE_THRESHOLD, "°C", temp_label, "temperature", Config.TEMPERATURE_CRITICAL_THRESHOLD)
        if is_server:
            custom_values = metrics.get("custom") or {}
            for key, label in (("srv_fan_fault", "风扇状态"), ("srv_disk_fault", "硬盘状态"), ("srv_mem_fault", "内存物理状态")):
                value = custom_values.get(key)
                try:
                    value = float(value) if value is not None else None
                except (TypeError, ValueError):
                    value = None
                if value is not None and value > 0:
                    add(key, value, 0, "", label, key)

        if metrics.get("power_status") == "failure" and "power" not in covered_metrics:
            if alert_suppression.is_suppressed(
                self.db, "device", device_id=device.id,
                alert_type="power", alert_level="critical",
            ):
                pass
            else:
                dup = self.db.query(Alert).filter(
                    Alert.device_id == device.id,
                    Alert.alert_type == "power",
                ).first()
                if not dup:
                    alerts.append(Alert(
                        device_id=device.id,
                        alert_type="power",
                        alert_level="critical",
                        message="电源状态异常",
                        created_at=datetime.utcnow(),
                    ))
                    pending_notify.append({
                        "source": "device",
                        "level": "critical",
                        "device_name": device.name,
                        "ip_address": device.ip_address,
                        "alert_type": "power",
                        "message": "电源状态异常",
                        "value": None,
                        "threshold": None,
                        "created_at": datetime.utcnow().isoformat(timespec="seconds"),
                    })

        if not alerts:
            return

        self.db.add_all(alerts)
        self.db.commit()

        # 带上告警 ID 后异步分发通知
        for alert, payload in zip(alerts, pending_notify):
            payload["source_id"] = alert.id
            self._notify_device(device, payload)

    def _mark_offline(self, device: Device) -> None:
        method = (getattr(device, "monitor_type", None) or "snmp").lower()
        method_label = {"ping": "ICMP Ping", "tcp": "TCP 端口", "snmp": "SNMP"}.get(method, "SNMP")
        offline_rules = (
            self.db.query(DeviceAlertRule)
            .filter(
                DeviceAlertRule.device_id == device.id,
                DeviceAlertRule.enabled == True,  # noqa: E712
                DeviceAlertRule.metric == "offline",
            )
            .all()
        )
        if offline_rules:
            for rule in offline_rules:
                value = 1.0
                if not alert_rule_service.condition_matches(value, rule.operator, rule.threshold):
                    continue
                alert_type = f"rule_{rule.id}"
                if alert_suppression.is_suppressed(
                    self.db, "device", device_id=device.id,
                    alert_type=alert_type, alert_level=rule.level,
                ):
                    continue
                dup = self.db.query(Alert).filter(
                    Alert.device_id == device.id,
                    Alert.alert_type == alert_type,
                ).first()
                if dup:
                    continue
                message = f"{rule.name}：设备 {device.ip_address} {method_label} 探测失败"
                alert = Alert(
                    device_id=device.id,
                    alert_type=alert_type,
                    alert_level=rule.level,
                    level_label=alert_rule_service.level_label(rule),
                    rule_id=rule.id,
                    message=message,
                    created_at=datetime.utcnow(),
                )
                self.db.add(alert)
                self.db.commit()
                self._notify_device(device, {
                    "source": "device",
                    "source_id": alert.id,
                    "level": rule.level,
                    "device_name": device.name,
                    "ip_address": device.ip_address,
                    "alert_type": alert_type,
                    "message": message,
                    "value": value,
                    "threshold": rule.threshold,
                    "created_at": datetime.utcnow().isoformat(timespec="seconds"),
                    "channel_ids": rule.notify_channel_ids or [],
                })
            return

        dup = self.db.query(Alert).filter(
            Alert.device_id == device.id,
            Alert.alert_type == "offline",
        ).first()
        if not dup and not alert_suppression.is_suppressed(
            self.db, "device", device_id=device.id,
            alert_type="offline", alert_level="critical",
        ):
            alert = Alert(
                device_id=device.id,
                alert_type="offline",
                alert_level="critical",
                message=f"设备 {device.ip_address} {method_label} 探测失败",
                created_at=datetime.utcnow(),
            )
            self.db.add(alert)
            self.db.commit()
            self._notify_device(device, {
                "source": "device",
                "source_id": alert.id,
                "level": "critical",
                "device_name": device.name,
                "ip_address": device.ip_address,
                "alert_type": "offline",
                "message": alert.message,
                "value": None,
                "threshold": None,
                "created_at": datetime.utcnow().isoformat(timespec="seconds"),
            })

    # ---------- 循环 ----------
    def _read_interval(self) -> int:
        """读取系统配置中的采集间隔（每轮重新读取，改配置免重启）"""
        try:
            from ..services.settings import get_value

            interval = int(get_value(self.db, "collection_interval"))
            if 10 <= interval <= 3600:
                Config.COLLECTION_INTERVAL = interval
                return interval
        except Exception:  # noqa: BLE001
            pass
        return max(10, int(Config.COLLECTION_INTERVAL))

    async def run_continuous(self) -> None:
        self.running = True
        interval = self._read_interval()
        logger.info("开始 SNMP 采集循环，间隔 %ss", interval)
        while self.running:
            try:
                count = await self.collect_all()
                logger.info("本轮采集完成，成功 %s 台设备", count)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("采集循环异常: %s", exc)
            interval = self._read_interval()
            remaining = interval
            while self.running and remaining > 0:
                chunk = min(15, remaining)
                await asyncio.sleep(chunk)
                remaining -= chunk
                if not self.running or remaining <= 0:
                    break
                try:
                    recovered = await self.recover_offline_devices()
                    if recovered:
                        logger.info("离线告警实时恢复：本轮恢复 %s 条", recovered)
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    logger.warning("离线告警恢复检查异常: %s", exc)

    def stop(self) -> None:
        self.running = False
