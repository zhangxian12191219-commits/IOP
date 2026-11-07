"""SNMP 客户端 - 基于 pysnmp 的异步实现（支持 v1/v2c）

对外提供:
- SNMPClient.get(oid)           单值查询
- SNMPClient.walk(oid)          子树遍历
- SNMPClient.get_system_info()  系统信息
- SNMPClient.get_cpu_usage()    CPU 使用率（多厂商 OID 回退）
- SNMPClient.get_memory_info()  内存使用
- SNMPClient.get_temperature()  温度（实体传感器 / Cisco）
- SNMPClient.get_power_status() 电源状态
- SNMPClient.get_interfaces()   接口表（含流量计数）
- SNMPClient.get_lldp_neighbors() LLDP/CDP 邻居
"""
import asyncio
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

try:
    from pysnmp.hlapi.v3arch.asyncio import (
        SnmpEngine,
        CommunityData,
        UsmUserData,
        UdpTransportTarget,
        ContextData,
        ObjectType,
        ObjectIdentity,
        get_cmd,
        walk_cmd,
        # SNMPv3 认证协议
        usmNoAuthProtocol,
        usmHMACMD5AuthProtocol,
        usmHMACSHAAuthProtocol,
        usmHMAC128SHA224AuthProtocol,
        usmHMAC192SHA256AuthProtocol,
        usmHMAC256SHA384AuthProtocol,
        usmHMAC384SHA512AuthProtocol,
        # SNMPv3 加密协议
        usmNoPrivProtocol,
        usmDESPrivProtocol,
        usmAesCfb128Protocol,
        usmAesCfb192Protocol,
        usmAesCfb256Protocol,
    )
    HAS_PYSNMP = True
except ImportError:  # pragma: no cover
    HAS_PYSNMP = False
    SnmpEngine = CommunityData = UsmUserData = UdpTransportTarget = ContextData = None
    ObjectType = ObjectIdentity = get_cmd = walk_cmd = None
    usmNoAuthProtocol = usmHMACMD5AuthProtocol = usmHMACSHAAuthProtocol = None
    usmHMAC128SHA224AuthProtocol = usmHMAC192SHA256AuthProtocol = None
    usmHMAC256SHA384AuthProtocol = usmHMAC384SHA512AuthProtocol = None
    usmNoPrivProtocol = usmDESPrivProtocol = None
    usmAesCfb128Protocol = usmAesCfb192Protocol = usmAesCfb256Protocol = None

# 认证协议映射
AUTH_PROTOCOLS = {
    "none": lambda: usmNoAuthProtocol,
    "md5": lambda: usmHMACMD5AuthProtocol,
    "sha": lambda: usmHMACSHAAuthProtocol,
    "sha1": lambda: usmHMACSHAAuthProtocol,
    "sha224": lambda: usmHMAC128SHA224AuthProtocol,
    "sha256": lambda: usmHMAC192SHA256AuthProtocol,
    "sha384": lambda: usmHMAC256SHA384AuthProtocol,
    "sha512": lambda: usmHMAC384SHA512AuthProtocol,
}

# 加密协议映射
PRIV_PROTOCOLS = {
    "none": lambda: usmNoPrivProtocol,
    "des": lambda: usmDESPrivProtocol,
    "aes": lambda: usmAesCfb128Protocol,
    "aes128": lambda: usmAesCfb128Protocol,
    "aes192": lambda: usmAesCfb192Protocol,
    "aes256": lambda: usmAesCfb256Protocol,
    "3des": lambda: usmDESPrivProtocol,
}

# 共享 SNMP 引擎（单事件循环下可复用，避免重复初始化 MIB 视图）
_SHARED_ENGINE = None


def _get_engine():
    global _SHARED_ENGINE
    if _SHARED_ENGINE is None:
        _SHARED_ENGINE = SnmpEngine()
    return _SHARED_ENGINE


def _crypto_available() -> bool:
    """SNMPv3 加密（DES/AES）依赖 cryptography 或 pycryptodomex"""
    try:
        import cryptography  # noqa: F401
        return True
    except ImportError:
        pass
    try:
        import Cryptodome  # noqa: F401
        return True
    except ImportError:
        return False


class SNMPError(Exception):
    """SNMP 操作异常"""


# ---------- 标准 OID ----------
OID_SYS_DESCR = "1.3.6.1.2.1.1.1.0"
OID_SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
OID_SYS_CONTACT = "1.3.6.1.2.1.1.4.0"
OID_SYS_NAME = "1.3.6.1.2.1.1.5.0"
OID_SYS_LOCATION = "1.3.6.1.2.1.1.6.0"

# ifTable / ifXTable
OID_IF_INDEX = "1.3.6.1.2.1.2.2.1.1"
OID_IF_DESCR = "1.3.6.1.2.1.2.2.1.2"
OID_IF_TYPE = "1.3.6.1.2.1.2.2.1.3"
OID_IF_MTU = "1.3.6.1.2.1.2.2.1.4"
OID_IF_SPEED = "1.3.6.1.2.1.2.2.1.5"
OID_IF_PHYS_ADDRESS = "1.3.6.1.2.1.2.2.1.6"
OID_IF_ADMIN_STATUS = "1.3.6.1.2.1.2.2.1.7"
OID_IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"
OID_IF_IN_OCTETS = "1.3.6.1.2.1.2.2.1.10"
OID_IF_IN_ERRORS = "1.3.6.1.2.1.2.2.1.14"
OID_IF_OUT_OCTETS = "1.3.6.1.2.1.2.2.1.16"
OID_IF_OUT_ERRORS = "1.3.6.1.2.1.2.2.1.20"
OID_IF_NAME = "1.3.6.1.2.1.31.1.1.1.1"
OID_IF_HC_IN_OCTETS = "1.3.6.1.2.1.31.1.1.1.6"
OID_IF_HC_OUT_OCTETS = "1.3.6.1.2.1.31.1.1.1.10"

# HOST-RESOURCES-MIB
OID_HR_PROCESSOR_LOAD = "1.3.6.1.2.1.25.3.3.1.2"
OID_HR_STORAGE_TYPE = "1.3.6.1.2.1.25.2.3.1.2"
OID_HR_STORAGE_DESCR = "1.3.6.1.2.1.25.2.3.1.3"
OID_HR_STORAGE_UNITS = "1.3.6.1.2.1.25.2.3.1.4"
OID_HR_STORAGE_SIZE = "1.3.6.1.2.1.25.2.3.1.5"
OID_HR_STORAGE_USED = "1.3.6.1.2.1.25.2.3.1.6"

# ENTITY-SENSORS-MIB（温度/风扇/电源等实体传感器）
OID_ENT_SENSOR_TYPE = "1.3.6.1.2.1.99.1.1.1.1"
OID_ENT_SENSOR_SCALE = "1.3.6.1.2.1.99.1.1.1.2"
OID_ENT_SENSOR_PRECISION = "1.3.6.1.2.1.99.1.1.1.3"
OID_ENT_SENSOR_VALUE = "1.3.6.1.2.1.99.1.1.1.4"
OID_ENT_SENSOR_STATUS = "1.3.6.1.2.1.99.1.1.1.5"
OID_ENT_PHYS_DESCR = "1.3.6.1.2.1.47.1.1.1.1.2"
OID_ENT_PHYS_CLASS = "1.3.6.1.2.1.47.1.1.1.1.5"

# 厂商 CPU / 内存 / 温度 / 电源
VENDOR_CPU_OIDS = [
    "1.3.6.1.4.1.9.2.1.56.0",              # Cisco avgBusy5
    "1.3.6.1.4.1.9.2.1.57.0",              # Cisco avgBusy1
    "1.3.6.1.4.1.2011.6.3.4.1.2.0",        # Huawei
    "1.3.6.1.4.1.25506.2.6.1.1.1.1.6",     # H3C
    "1.3.6.1.4.1.12356.101.4.1.3.0",       # Fortinet
    "1.3.6.1.4.1.28557.2.2.1.3.0",         # Hillstone sysCPU
]
VENDOR_CPU_WALK = [
    "1.3.6.1.4.1.9.9.109.1.1.1.1.8",       # Cisco CPU 5s per core
    "1.3.6.1.4.1.2011.6.3.4.1.3",          # Huawei per-entity
    "1.3.6.1.4.1.25506.2.6.1.1.1.1.6",     # 华三实体 CPU
    "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.5",  # 华为实体 CPU
]
VENDOR_MEMORY_USAGE_WALK = [
    "1.3.6.1.4.1.25506.2.6.1.1.1.1.8",     # 华三实体内存使用率
    "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.7",  # 华为实体内存使用率（hwEntityMemUsage）
]
H3C_MEMORY_USAGE_OID = "1.3.6.1.4.1.25506.2.6.1.1.1.1.8"
H3C_MEMORY_SIZE_OID = "1.3.6.1.4.1.25506.2.6.1.1.1.1.10"
HUAWEI_MEMORY_USAGE_OID = "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.7"
HUAWEI_MEMORY_STANDBY_OID = "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.3"
HUAWEI_CPU_USAGE_OID = "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.5"
H3C_CPU_USAGE_OID = "1.3.6.1.4.1.25506.2.6.1.1.1.1.6"
VENDOR_MEM_WALK = [
    ("1.3.6.1.4.1.9.9.48.1.1.1.5", "1.3.6.1.4.1.9.9.48.1.1.1.6"),   # Cisco used/free
    ("1.3.6.1.4.1.2011.6.3.5.1.1.2", "1.3.6.1.4.1.2011.6.3.5.1.1.3"),
]
VENDOR_TEMP_WALK = [
    "1.3.6.1.4.1.9.9.91.1.1.1.4",          # Cisco entSensorValue
    "1.3.6.1.4.1.2011.6.3.1.1.1.12",       # Huawei hwEntityTemperature
    "1.3.6.1.4.1.25506.2.6.1.1.1.1.12",    # 华三实体温度
    "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.11", # 华为实体温度
    "1.3.6.1.4.1.28557.2.28.1.2.1.3",      # Hillstone 温度表
]
VENDOR_POWER_WALK = [
    "1.3.6.1.4.1.9.9.13.1.5.1.3",          # Cisco ciscoEnvMonSupplyState
    "1.3.6.1.4.1.2011.6.3.1.1.1.9",        # Huawei power state
]

# LLDP 邻居
OID_LLDP_REM_CHASSIS_ID = "1.0.8802.1.1.2.1.4.1.1.6"
OID_LLDP_REM_CHASSIS_SUBTYPE = "1.0.8802.1.1.2.1.4.1.1.5"
OID_LLDP_REM_PORT_ID = "1.0.8802.1.1.2.1.4.1.1.7"
OID_LLDP_REM_SYS_NAME = "1.0.8802.1.1.2.1.4.1.1.9"
OID_LLDP_REM_MAN_ADDR = "1.0.8802.1.1.2.1.4.1.1.4"
OID_LLDP_LOC_PORT_DESC = "1.0.8802.1.1.2.1.3.7.1.4"
OID_CDP_CACHE_ADDRESS = "1.3.6.1.4.1.9.9.23.1.2.1.1.4"
OID_CDP_CACHE_DEVID = "1.3.6.1.4.1.9.9.23.1.2.1.1.6"
OID_CDP_CACHE_DEVPORT = "1.3.6.1.4.1.9.9.23.1.2.1.1.7"
OID_CDP_CACHE_PLATFORM = "1.3.6.1.4.1.9.9.23.1.2.1.1.8"

IF_OPER_MAP = {"1": "up", "2": "down", "3": "testing", "4": "unknown",
               "5": "dormant", "6": "notpresent", "7": "lowerLayerDown"}
IF_ADMIN_MAP = {"1": "up", "2": "down", "3": "testing"}

# entPhySensorType: 温度相关类型
TEMP_SENSOR_TYPES = {
    "8",   # celsius
    "9",   # fahrenheit
    "10",  # kelvin
}


def _as_int(value: Any) -> Optional[int]:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None


def _as_float(value: Any) -> Optional[float]:
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def _last_index(oid: str) -> str:
    """取 OID 的最后一段作为索引"""
    return oid.rstrip(".").split(".")[-1]


def _decode_octets(value: Any) -> Optional[str]:
    """把可能为 bytes 的 SNMP 值解码为可读字符串"""
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="ignore").strip("\x00").strip()
        except Exception:
            return value.hex()
    if isinstance(value, str):
        return value.strip()
    return None


def _decode_mac(value: Any) -> Optional[str]:
    """把 ifPhysAddress 字节转换为 aa:bb:cc:dd:ee:ff"""
    try:
        raw = value.encode("latin-1") if isinstance(value, str) else bytes(value)
    except Exception:
        return None
    if len(raw) != 6:
        return None
    return ":".join(f"{byte:02x}" for byte in raw)


class SNMPClient:
    """异步 SNMP 客户端（支持 v1 / v2c / v3）"""

    def __init__(
        self,
        host: str,
        community: str = "public",
        version: str = "v2c",
        port: int = 161,
        timeout: int = 3,
        retries: int = 1,
        # ---- SNMPv3 (USM) ----
        v3_username: Optional[str] = None,
        v3_security_level: str = "authPriv",
        v3_auth_protocol: str = "SHA",
        v3_auth_password: Optional[str] = None,
        v3_priv_protocol: str = "AES",
        v3_priv_password: Optional[str] = None,
        v3_context_name: Optional[str] = None,
        v3_context_engine_id: Optional[str] = None,
    ):
        self.host = host
        self.community = community
        self.version = (version or "v2c").lower()
        self.port = int(port or 161)
        self.timeout = int(timeout or 3)
        self.retries = int(retries or 1)

        self.v3_username = v3_username
        self.v3_security_level = (v3_security_level or "authPriv").lower()
        self.v3_auth_protocol = (v3_auth_protocol or "SHA").lower()
        self.v3_auth_password = v3_auth_password
        self.v3_priv_protocol = (v3_priv_protocol or "AES").lower()
        self.v3_priv_password = v3_priv_password
        self.v3_context_name = v3_context_name
        self.last_error = ""
        self.v3_context_engine_id = v3_context_engine_id

    @classmethod
    def from_device(cls, device, timeout: int = 3, retries: int = 1) -> "SNMPClient":
        """由 Device ORM 对象构造客户端（含 v3 参数）"""
        return cls(
            host=device.ip_address,
            community=device.community or "public",
            version=device.snmp_version or "v2c",
            port=device.port or 161,
            timeout=timeout,
            retries=retries,
            v3_username=getattr(device, "v3_username", None),
            v3_security_level=getattr(device, "v3_security_level", None) or "authPriv",
            v3_auth_protocol=getattr(device, "v3_auth_protocol", None) or "SHA",
            v3_auth_password=getattr(device, "v3_auth_password", None),
            v3_priv_protocol=getattr(device, "v3_priv_protocol", None) or "AES",
            v3_priv_password=getattr(device, "v3_priv_password", None),
            v3_context_name=getattr(device, "v3_context_name", None),
        )

    # ---------- 底层 ----------
    def _auth(self):
        """按版本构造认证信息：v1/v2c -> CommunityData，v3 -> UsmUserData

        pysnmp 7 的 UsmUserData 不接收 securityLevel 参数，
        安全级别由 authKey / privKey 是否为空、以及协议是否为 NoAuth/NoPriv 推导：
          noAuthNoPriv -> 无 key + usmNoAuthProtocol + usmNoPrivProtocol
          authNoPriv   -> authKey + authProtocol + usmNoPrivProtocol
          authPriv     -> authKey + privKey + 认证/加密协议
        """
        if self.version == "v3":
            if not self.v3_username:
                raise SNMPError("SNMPv3 需要配置用户名(v3_username)")

            level = self.v3_security_level
            auth_key = None
            priv_key = None
            auth_proto = AUTH_PROTOCOLS["none"]()
            priv_proto = PRIV_PROTOCOLS["none"]()

            if level in ("authnopriv", "authpriv"):
                auth_key = self.v3_auth_password or None
                if not auth_key:
                    raise SNMPError("SNMPv3 安全级别需要认证密码(v3_auth_password)")
                auth_proto = AUTH_PROTOCOLS.get(
                    self.v3_auth_protocol, AUTH_PROTOCOLS["sha"]
                )()

            if level == "authpriv":
                priv_key = self.v3_priv_password or None
                if not priv_key:
                    raise SNMPError("SNMPv3 authPriv 需要加密密码(v3_priv_password)")
                if not _crypto_available():
                    raise SNMPError(
                        "SNMPv3 加密通信需要 cryptography 库，"
                        "请执行: pip install cryptography（或 pip install 'pysnmp[crypto]'）"
                    )
                priv_proto = PRIV_PROTOCOLS.get(
                    self.v3_priv_protocol, PRIV_PROTOCOLS["aes"]
                )()

            return UsmUserData(
                userName=self.v3_username,
                authKey=auth_key,
                privKey=priv_key,
                authProtocol=auth_proto,
                privProtocol=priv_proto,
            )

        mp_model = 0 if self.version == "v1" else 1
        return CommunityData(self.community, mpModel=mp_model)

    def _context(self):
        """构造上下文（SNMPv3 支持 contextName / contextEngineId）"""
        engine_id = self.v3_context_engine_id if self.version == "v3" else None
        name = (self.v3_context_name if self.version == "v3" else None) or ""
        return ContextData(
            contextEngineId=engine_id.encode() if isinstance(engine_id, str) else engine_id,
            contextName=name.encode() if isinstance(name, str) else name,
        )

    async def _transport(self):
        return await UdpTransportTarget.create(
            (self.host, self.port),
            timeout=self.timeout,
            retries=self.retries,
        )

    @staticmethod
    def _value_of(var_bind) -> Any:
        """从 ObjectType 中提取 Python 值"""
        try:
            return var_bind[1]
        except Exception:
            return None

    async def get(self, oid: str) -> Optional[str]:
        """查询单个 OID"""
        if not HAS_PYSNMP:
            raise SNMPError("pysnmp 未安装，请执行 pip install pysnmp")
        try:
            transport = await self._transport()
            err_indication, err_status, err_index, var_binds = await get_cmd(
                _get_engine(),
                self._auth(),
                transport,
                self._context(),
                ObjectType(ObjectIdentity(oid)),
            )
            if err_indication is not None or err_status:
                self.last_error = f"GET {oid}: {err_indication or err_status}"
                logger.debug("SNMP GET %s %s -> %s / %s",
                             self.host, oid, err_indication, err_status)
                return None
            if not var_binds:
                self.last_error = f"GET {oid}: 空响应"
                return None
            value = self._value_of(var_binds[0])
            if isinstance(value, bytes):
                return _decode_octets(value)
            if value is None:
                return None
            # OctetString.prettyPrint 会给出可读字符串
            pretty = getattr(var_binds[0][1], "prettyPrint", None)
            return str(pretty()) if callable(pretty) else str(value)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.last_error = f"GET {oid}: {exc}"[:300]
            logger.debug("SNMP GET %s %s 失败: %s", self.host, oid, exc)
            return None

    async def walk(self, oid: str, max_rows: Optional[int] = None) -> List[Tuple[str, Any]]:
        """遍历子树，返回 [(oid, value), ...]；max_rows 用于全量遍历时限制结果规模。"""
        if not HAS_PYSNMP:
            raise SNMPError("pysnmp 未安装，请执行 pip install pysnmp")
        out: List[Tuple[str, Any]] = []
        try:
            transport = await self._transport()
            async for err_indication, err_status, err_index, var_binds in walk_cmd(
                _get_engine(),
                self._auth(),
                transport,
                self._context(),
                ObjectType(ObjectIdentity(oid)),
                lexicographicMode=False,
            ):
                if err_indication is not None or err_status:
                    self.last_error = f"WALK {oid}: {err_indication or err_status}"[:300]
                    break
                for vb in var_binds:
                    name = vb[0]
                    value = vb[1]
                    pretty = getattr(value, "prettyPrint", None)
                    out.append((str(name), pretty() if callable(pretty) else value))
                    if max_rows is not None and len(out) >= max_rows:
                        return out
            return out
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.last_error = f"WALK {oid}: {exc}"[:300]
            logger.debug("SNMP WALK %s %s 失败: %s", self.host, oid, exc)
            return out

    async def get_many(self, oids: List[str]) -> Dict[str, Optional[str]]:
        """并发查询多个 OID"""
        values = await asyncio.gather(*[self.get(o) for o in oids])
        return dict(zip(oids, values))

    # ---------- 业务 ----------
    async def get_numeric(self, oid: str) -> Optional[float]:
        """GET 单个 OID 并解析为数值

        兼容 "85"、"85%"、"85.5"、"45 C"、"1.2 Gbps" 等返回格式；
        No Such Object / Instance 等返回 None。
        """
        raw = await self.get(oid)
        if raw is None:
            return None
        text = str(raw).strip()
        if not text:
            return None
        lowered = text.lower()
        if lowered.startswith(("no such", "no access", "nosuch")):
            return None
        match = re.search(r"-?\d+(?:\.\d+)?", text)
        if not match:
            return None
        try:
            return float(match.group(0))
        except ValueError:
            return None

    async def get_system_info(self) -> Dict[str, Any]:
        data = await self.get_many([
            OID_SYS_DESCR, OID_SYS_NAME, OID_SYS_LOCATION,
            OID_SYS_UPTIME, OID_SYS_CONTACT,
        ])
        uptime_ticks = _as_int(data.get(OID_SYS_UPTIME))
        return {
            "sysdescr": data.get(OID_SYS_DESCR),
            "sysname": data.get(OID_SYS_NAME),
            "syslocation": data.get(OID_SYS_LOCATION),
            "syscontact": data.get(OID_SYS_CONTACT),
            # sysUpTime 单位为 1/100 秒
            "uptime": int(uptime_ticks / 100) if uptime_ticks is not None else None,
            "error": "" if any(data.values()) else self.last_error,
        }

    async def get_cpu_usage(self) -> Optional[float]:
        """CPU 使用率（%），按厂商 OID 逐级回退"""
        for oid in VENDOR_CPU_OIDS:
            raw = await self.get(oid)
            val = _as_float(raw)
            if val is not None and 0 <= val <= 100:
                return round(val, 2)

        # HOST-RESOURCES: 各核负载取平均
        rows = await self.walk(OID_HR_PROCESSOR_LOAD)
        loads = [v for v in (_as_float(r[1]) for r in rows) if v is not None]
        if loads:
            return round(sum(loads) / len(loads), 2)

        for oid in VENDOR_CPU_WALK:
            rows = await self.walk(oid)
            values = {
                _last_index(o): _as_float(v)
                for o, v in rows
                if _as_float(v) is not None and 0 <= _as_float(v) <= 100
            }
            if not values:
                continue
            if oid == HUAWEI_CPU_USAGE_OID:
                # 华为 CPU 同内存：class=9 的单板中 standbyStatus=4 为主用主控板。
                classes = {
                    _last_index(o): _as_int(v)
                    for o, v in await self.walk(OID_ENT_PHYS_CLASS)
                }
                standby = {
                    _last_index(o): _as_int(v)
                    for o, v in await self.walk(HUAWEI_MEMORY_STANDBY_OID)
                }
                active = [
                    idx for idx, cls in classes.items()
                    if cls == 9 and standby.get(idx) == 4 and idx in values
                ]
                if active:
                    return round(max(values[idx] for idx in active), 2)
                module_values = [values[idx] for idx in classes if classes.get(idx) == 9 and idx in values]
                return round(max(module_values or list(values.values())), 2)
            if oid == H3C_CPU_USAGE_OID:
                # 华三 CPU 也是模块级表；用内存容量最大的主模块，避免被线卡 CPU 顶高。
                sizes = {
                    _last_index(o): _as_float(v)
                    for o, v in await self.walk(H3C_MEMORY_SIZE_OID)
                }
                candidates = [(sizes.get(idx) or 0.0, value, idx) for idx, value in values.items()]
                positive = [item for item in candidates if item[0] > 0]
                if positive:
                    return round(max(positive, key=lambda item: item[0])[1], 2)
                return round(max(values.values()), 2)
            if max(values.values()) > 0:
                return round(max(values.values()), 2)

        return None

    async def get_memory_info(self) -> Dict[str, Any]:
        """内存使用（单位 MB）"""
        result = {"total": None, "used": None, "usage": None}

        # Hillstone: sysTotalMemory/sysCurMemory（KB）
        total_kb = _as_float(await self.get("1.3.6.1.4.1.28557.2.2.1.4.0"))
        used_kb = _as_float(await self.get("1.3.6.1.4.1.28557.2.2.1.5.0"))
        if total_kb and used_kb is not None:
            return {
                "total": round(total_kb / 1024, 2),
                "used": round(used_kb / 1024, 2),
                "usage": round(min(100.0, used_kb / total_kb * 100), 2),
            }

        # 0) 厂商实体表直接给出内存使用率。
        # H3C 的 hh3cEntityExtMemUsage 是按“Module Level 1”逐板卡返回；
        # 不能取 max，否则某块线卡 90% 会把整机内存顶成 90%。
        # 用 hh3cEntityExtMemSize 找内存最大的主模块，并记录候选值便于排障。
        for oid in VENDOR_MEMORY_USAGE_WALK:
            rows = await self.walk(oid)
            vals = [v for v in (_as_float(r[1]) for r in rows) if v is not None and 0 <= v <= 100]
            if not vals:
                continue
            if oid == H3C_MEMORY_USAGE_OID:
                sizes = {
                    _last_index(o): _as_float(v)
                    for o, v in await self.walk(H3C_MEMORY_SIZE_OID)
                }
                candidates = []
                for o, raw in rows:
                    usage = _as_float(raw)
                    if usage is None or not 0 <= usage <= 100:
                        continue
                    idx = _last_index(o)
                    candidates.append((sizes.get(idx) or 0.0, usage, idx))
                logger.debug("H3C 内存候选 entity/size/usage: %s", candidates)
                positive = [item for item in candidates if item[0] > 0]
                if positive:
                    size, usage, _idx = max(positive, key=lambda item: item[0])
                    # hh3cEntityExtMemSize 在不同平台可能为 KB 或字节，仅作展示估算。
                    total_mb = size / 1024 if size < 100_000_000 else size / 1024 / 1024
                    return {
                        "total": round(total_mb, 2),
                        "used": round(total_mb * usage / 100, 2),
                        "usage": round(usage, 2),
                    }
                # 没有容量表时，主模块通常是较早的实体；退化为最小非零值，
                # 避免 max 被高负载线卡误导。
                usage = round(min((v for v in vals if v > 0), default=vals[0]), 2)
                return {"total": 0.0, "used": 0.0, "usage": usage}
            if oid == HUAWEI_MEMORY_USAGE_OID:
                # 华为官方算法：实体表中 class=9 是单板，standbyStatus=4 是主用主控板；
                # 读取主用主控板对应实例的 hwEntityMemUsage，不能对整表取 max。
                classes = {
                    _last_index(o): _as_int(v)
                    for o, v in await self.walk(OID_ENT_PHYS_CLASS)
                }
                standby = {
                    _last_index(o): _as_int(v)
                    for o, v in await self.walk(HUAWEI_MEMORY_STANDBY_OID)
                }
                usage_by_index = {
                    _last_index(o): _as_float(v)
                    for o, v in rows
                    if _as_float(v) is not None and 0 <= _as_float(v) <= 100
                }
                active = [
                    idx for idx, cls in classes.items()
                    if cls == 9 and standby.get(idx) == 4 and idx in usage_by_index
                ]
                if active:
                    usage = round(max(usage_by_index[idx] for idx in active), 2)
                    logger.debug("华为主用主控内存 entity=%s usage=%s", active, usage)
                    return {"total": 0.0, "used": 0.0, "usage": usage}
                # 没有 standby 信息时，退化为单板 class=9 中的最大值。
                module_usage = [usage_by_index[idx] for idx in classes if classes.get(idx) == 9 and idx in usage_by_index]
                fallback = module_usage or vals
                usage = round(max(fallback), 2)
                logger.debug("华为内存回退候选 module=%s usage=%s", module_usage, usage)
                return {"total": 0.0, "used": 0.0, "usage": usage}
            if max(vals) > 0:
                usage = round(max(vals), 2)
                return {"total": 0.0, "used": 0.0, "usage": usage}

        # 1) Cisco memory pool
        used_rows = await self.walk(VENDOR_MEM_WALK[0][0])
        free_rows = await self.walk(VENDOR_MEM_WALK[0][1])
        if used_rows:
            used = sum(v for v in (_as_int(r[1]) for r in used_rows) if v)
            free = sum(v for v in (_as_int(r[1]) for r in free_rows) if v)
            if used + free > 0:
                total_mb = (used + free) / (1024 * 1024)
                used_mb = used / (1024 * 1024)
                return {
                    "total": round(total_mb, 2),
                    "used": round(used_mb, 2),
                    "usage": round(used_mb / total_mb * 100, 2),
                }

        # 2) HOST-RESOURCES hrStorageTable（挑物理内存行）
        types = {_last_index(o): v for o, v in await self.walk(OID_HR_STORAGE_TYPE)}
        descrs = {_last_index(o): _decode_octets(v) for o, v in await self.walk(OID_HR_STORAGE_DESCR)}
        units = {_last_index(o): _as_int(v) for o, v in await self.walk(OID_HR_STORAGE_UNITS)}
        sizes = {_last_index(o): _as_int(v) for o, v in await self.walk(OID_HR_STORAGE_SIZE)}
        useds = {_last_index(o): _as_int(v) for o, v in await self.walk(OID_HR_STORAGE_USED)}

        for idx, descr in descrs.items():
            label = (descr or "").lower()
            # hrStorageRam = 2
            if types.get(idx) == "2" or "memory" in label or "ram" in label:
                unit = units.get(idx) or 1
                size = sizes.get(idx) or 0
                used = useds.get(idx) or 0
                total_b = size * unit
                used_b = used * unit
                if total_b > 0:
                    total_mb = total_b / (1024 * 1024)
                    used_mb = used_b / (1024 * 1024)
                    return {
                        "total": round(total_mb, 2),
                        "used": round(used_mb, 2),
                        "usage": round(used_mb / total_mb * 100, 2),
                    }

        return result

    async def get_disk_info(self) -> Dict[str, Any]:
        """磁盘容量/使用率（HOST-RESOURCES 固定磁盘/可移动磁盘汇总）"""
        types = {_last_index(o): v for o, v in await self.walk(OID_HR_STORAGE_TYPE)}
        units = {_last_index(o): _as_int(v) for o, v in await self.walk(OID_HR_STORAGE_UNITS)}
        sizes = {_last_index(o): _as_int(v) for o, v in await self.walk(OID_HR_STORAGE_SIZE)}
        useds = {_last_index(o): _as_int(v) for o, v in await self.walk(OID_HR_STORAGE_USED)}
        descrs = {_last_index(o): _decode_octets(v) for o, v in await self.walk(OID_HR_STORAGE_DESCR)}
        total_bytes = 0
        used_bytes = 0
        per_disk: List[Dict[str, Any]] = []
        for idx, stype in types.items():
            label = (descrs.get(idx) or "").lower()
            # hrStorageFixedDisk=4 / hrStorageRemovableDisk=5；同时兼容常见存储描述
            if str(stype) in ("4", "5") or str(stype).endswith((".4", ".5")) or "disk" in label or "storage" in label or "volume" in label or label.strip() == "/":
                unit = units.get(idx) or 1
                size = sizes.get(idx) or 0
                used = useds.get(idx) or 0
                if size > 0:
                    total_bytes += size * unit
                    used_bytes += min(size, used) * unit
                    per_disk.append({
                        "index": idx,
                        "name": descrs.get(idx) or f"Disk {idx}",
                        "total_mb": round(size * unit / 1024 / 1024, 2),
                        "used_mb": round(min(size, used) * unit / 1024 / 1024, 2),
                    })
        if total_bytes <= 0:
            return {}
        usage = max(0.0, min(100.0, used_bytes / total_bytes * 100))
        return {
            "usage": round(usage, 2),
            "total_mb": round(total_bytes / 1024 / 1024, 2),
            "used_mb": round(used_bytes / 1024 / 1024, 2),
            "disks": per_disk,
        }

    async def get_disk_usage(self) -> Optional[float]:
        info = await self.get_disk_info()
        return info.get("usage")

    async def get_temperature(self) -> Optional[float]:
        """温度（摄氏度）"""
        # Dell iDRAC temperatureProbeReading，单位 0.1℃
        try:
            dell_rows = await self.walk("1.3.6.1.4.1.674.10892.5.4.700.20.1.6", max_rows=64)
            dell_values = [
                _as_float(v) / 10.0 for _, v in dell_rows
                if _as_float(v) is not None and 0 <= (_as_float(v) or 0) <= 2000
            ]
            if dell_values:
                return round(max(dell_values), 1)
        except Exception as exc:  # noqa: BLE001
            logger.debug("Dell 温度读取失败 %s: %s", self.host, exc)

        # 1) ENTITY-SENSORS-MIB
        types = {_last_index(o): str(v).strip() for o, v in await self.walk(OID_ENT_SENSOR_TYPE)}
        scales = {_last_index(o): v for o, v in await self.walk(OID_ENT_SENSOR_SCALE)}
        values = {_last_index(o): _as_float(v) for o, v in await self.walk(OID_ENT_SENSOR_VALUE)}

        temps: List[float] = []
        for idx, val in values.items():
            if val is None:
                continue
            stype = types.get(idx)
            if stype is not None and stype not in TEMP_SENSOR_TYPES:
                continue
            scale = _as_int(scales.get(idx)) or 0
            # entPhySensorScale: 9 = units(1), 8 = milli, 7 = micro ...
            if scale == 8:
                val = val / 1000.0
            elif scale == 7:
                val = val / 1_000_000.0
            elif scale == 10:
                val = val * 10
            # 过滤明显异常值
            if -40 <= val <= 200 and stype in TEMP_SENSOR_TYPES:
                temps.append(val)

        if temps:
            return round(max(temps), 1)

        # 2) 厂商 MIB 回退
        for oid in VENDOR_TEMP_WALK:
            rows = await self.walk(oid)
            vals = []
            for _, v in rows:
                fv = _as_float(v)
                if fv is None:
                    continue
                if -40 <= fv <= 200:
                    vals.append(fv)
                elif -400 <= fv <= 2000:  # 可能是 0.1 精度
                    vals.append(fv / 10.0)
            if vals:
                return round(max(vals), 1)

        return None

    async def get_power_status(self) -> str:
        """电源状态: normal / failure / unknown"""
        # 1) 厂商电源传感状态（1=normal, 2=warning, 3=critical, ...）
        for oid in VENDOR_POWER_WALK:
            rows = await self.walk(oid)
            if not rows:
                continue
            states = [_as_int(v) for _, v in rows]
            states = [s for s in states if s is not None]
            if not states:
                continue
            # Cisco ciscoEnvMonSupplyState: 1 normal, 2 warning, 3 critical, 4 shutdown, 5 notPresent, 6 notFunctioning
            if all(s == 1 for s in states):
                return "normal"
            return "failure"

        # 2) ENTITY-SENSORS: 电源类传感器状态 (1=ok, 2=unavailable, 3=nonoperational)
        stypes = {_last_index(o): str(v).strip() for o, v in await self.walk(OID_ENT_SENSOR_TYPE)}
        statuses = {_last_index(o): _as_int(v) for o, v in await self.walk(OID_ENT_SENSOR_STATUS)}
        power_states = [
            st for idx, st in statuses.items()
            if stypes.get(idx) in {"3", "4", "5", "6"}  # volts/amps/watts/... 类电源传感器
        ]
        if power_states:
            return "normal" if all(s == 1 for s in power_states) else "failure"

        return "unknown"

    async def _walk_value_map(self, root: str, decode: bool = False) -> Dict[str, Any]:
        """读取一张 SNMP 表，按最后一级索引建映射。"""
        rows = await self.walk(root, max_rows=512)
        return {
            _last_index(oid): (_decode_octets(value) if decode else value)
            for oid, value in rows
        }

    @staticmethod
    def _temperature_kind(name: str) -> str:
        text = str(name or "").lower()
        if "cpu" in text or "processor" in text:
            return "cpu"
        if "inlet" in text or "intake" in text or "进风" in text:
            return "inlet"
        if "exhaust" in text or "outlet" in text or "排风" in text:
            return "exhaust"
        if (
            "board" in text or "motherboard" in text or "mainboard" in text
            or "pch" in text or "主板" in text
        ):
            return "board"
        if "ambient" in text or "环境" in text:
            return "ambient"
        return "other"

    async def _walk_table_map(self, root: str) -> Dict[str, Dict[str, Any]]:
        """遍历一张 SNMP 表，返回 {字段: {完整索引: 原始值}}。

        适用于字符串索引（如华为 iBMC sensorName），不能只取最后一段索引。
        """
        rows = await self.walk(root, max_rows=5000)
        prefix = root.rstrip(".") + "."
        table: Dict[str, Dict[str, Any]] = {}
        for oid, value in rows:
            if not oid.startswith(prefix):
                continue
            parts = oid[len(prefix):].split(".")
            if len(parts) < 2:
                continue
            field, index = parts[0], ".".join(parts[1:])
            table.setdefault(field, {})[index] = value
        return table

    async def _walk_column_map(self, root: str, decode: bool = False) -> Dict[str, Any]:
        """只遍历表的一列，保留完整索引；适合传感器这种字符串索引大表。"""
        rows = await self.walk(root, max_rows=512)
        prefix = root.rstrip(".") + "."
        return {
            oid[len(prefix):]: (_decode_octets(value) if decode else value)
            for oid, value in rows
            if oid.startswith(prefix)
        }

    @staticmethod
    def _ibmc_sensor_oid(field: str, name: str) -> str:
        """华为 iBMC sensorName 索引：1 字节长度 17 + 17 字节定长名称。"""
        raw = str(name).encode("ascii", errors="ignore")[:17].ljust(17, b"\x00")
        return (
            "1.3.6.1.4.1.2011.2.235.1.1.13.50.1.{}.17.{}".format(
                field, ".".join(str(byte) for byte in raw)
            )
        )

    async def get_server_components(self) -> Dict[str, Any]:
        """服务器组件明细（Dell iDRAC 优先，其他厂商走 ENTITY 传感器）。

        返回结构中的每条记录都带名称，避免把 CPU、主板、进风、排风温度混成一个值。
        """
        temperatures: List[Dict[str, Any]] = []
        fans: List[Dict[str, Any]] = []
        power_supplies: List[Dict[str, Any]] = []
        disks: List[Dict[str, Any]] = []
        cpus: List[Dict[str, Any]] = []
        memory_modules: List[Dict[str, Any]] = []
        vendor = ""

        try:
            # Dell iDRAC temperatureProbeTable
            temp_values = await self._walk_value_map(
                "1.3.6.1.4.1.674.10892.5.4.700.20.1.6"
            )
            temp_names = await self._walk_value_map(
                "1.3.6.1.4.1.674.10892.5.4.700.20.1.8", decode=True
            )
            for idx, raw in temp_values.items():
                value = _as_float(raw)
                if value is None:
                    continue
                value = value / 10.0
                if not (-40 <= value <= 200):
                    continue
                name = str(temp_names.get(idx) or f"温度传感器 {idx}")
                temperatures.append({
                    "index": idx, "name": name, "value": round(value, 1),
                    "unit": "°C", "kind": self._temperature_kind(name),
                })
            # Dell iDRAC fanTable
            fan_values = await self._walk_value_map(
                "1.3.6.1.4.1.674.10892.5.4.700.12.1.6"
            )
            fan_names = await self._walk_value_map(
                "1.3.6.1.4.1.674.10892.5.4.700.12.1.8", decode=True
            )
            for idx, raw in fan_values.items():
                value = _as_float(raw)
                if value is None or value < 0:
                    continue
                fans.append({
                    "index": idx, "name": str(fan_names.get(idx) or f"风扇 {idx}"),
                    "value": round(value, 0), "unit": "RPM",
                })
            # Dell powerSupplyTable
            power_watts = await self._walk_value_map(
                "1.3.6.1.4.1.674.10892.5.4.600.12.1.16"
            )
            power_volts = await self._walk_value_map(
                "1.3.6.1.4.1.674.10892.5.4.600.12.1.9"
            )
            power_names = await self._walk_value_map(
                "1.3.6.1.4.1.674.10892.5.4.600.12.1.8", decode=True
            )
            for idx in sorted(set(power_watts) | set(power_volts), key=lambda x: (int(x) if str(x).isdigit() else 0)):
                name = str(power_names.get(idx) or f"电源 {idx}").replace(" Status", "")
                watts = _as_float(power_watts.get(idx))
                volts = _as_float(power_volts.get(idx))
                if watts is None and volts is None:
                    continue
                power_supplies.append({
                    "index": idx, "name": name,
                    "watts": round(watts, 1) if watts is not None else None,
                    "voltage": round(volts, 1) if volts is not None else None,
                    "unit": "W",
                })
            # Dell physical disk table（Status/FailurePredicted 必须一起采集）
            disk_sizes = await self._walk_value_map(
                "1.3.6.1.4.1.674.10892.5.5.1.20.130.4.1.11"
            )
            disk_names = await self._walk_value_map(
                "1.3.6.1.4.1.674.10892.5.5.1.20.130.4.1.2", decode=True
            )
            disk_models = await self._walk_value_map(
                "1.3.6.1.4.1.674.10892.5.5.1.20.130.4.1.6", decode=True
            )
            disk_slots = await self._walk_value_map(
                "1.3.6.1.4.1.674.10892.5.5.1.20.130.4.1.55", decode=True
            )
            disk_statuses = await self._walk_value_map(
                "1.3.6.1.4.1.674.10892.5.5.1.20.130.4.1.1"
            )
            disk_failure_predicted = await self._walk_value_map(
                "1.3.6.1.4.1.674.10892.5.5.1.20.130.4.1.19"
            )
            disk_state = await self._walk_value_map(
                "1.3.6.1.4.1.674.10892.5.5.1.20.130.4.1.4"
            )
            disk_indices = set(disk_sizes) | set(disk_names) | set(disk_statuses)
            for idx in sorted(disk_indices, key=lambda x: int(x) if str(x).isdigit() else 0):
                size_mb = _as_float(disk_sizes.get(idx))
                status_num = _as_int(disk_statuses.get(idx))
                predicted = _as_int(disk_failure_predicted.get(idx))
                state_num = _as_int(disk_state.get(idx))
                name = str(disk_names.get(idx) or disk_slots.get(idx) or f"硬盘 {idx}")
                # Dell physicalDiskState（.4）：1/2=Ready、3=Online、7=Rebuilding、
                # 8=Ready、15=Resync、24=Rebuild、35/40=维护状态，这些不是故障。
                # 只有明确 Offline/Failed/Removed/Predictive 等才报警。
                state_labels = {
                    0: "未知", 1: "就绪", 2: "就绪", 3: "在线", 4: "外部盘",
                    5: "离线", 6: "故障", 7: "重建中", 8: "就绪", 11: "已移除",
                    15: "重新同步", 24: "重建中", 25: "无介质", 26: "格式化中",
                    28: "诊断中", 34: "预测故障", 35: "初始化中", 39: "不兼容",
                    40: "清除中", 41: "不支持", 53: "不兼容",
                }
                fault_states = {5, 6, 11, 34, 39, 41, 53}
                fault = state_num in fault_states
                status_label = state_labels.get(state_num, "正常")
                if fault:
                    status_label = f"故障（{status_label}）"
                else:
                    status_label = "正常"
                disks.append({
                    "index": idx, "name": name,
                    "model": str(disk_models.get(idx) or ""),
                    "size_gb": round(size_mb / 1024, 2) if size_mb and size_mb > 0 else None,
                    "unit": "GB",
                    "status": "fault" if fault else "ok",
                    "status_label": f"在位 · {status_label}" if not fault else f"在位 · {status_label}",
                })
            # Dell CPU table
            cpu_names = await self._walk_value_map(
                "1.3.6.1.4.1.674.10892.5.4.1100.30.1.26", decode=True
            )
            cpu_models = await self._walk_value_map(
                "1.3.6.1.4.1.674.10892.5.4.1100.30.1.23", decode=True
            )
            cpu_cores = await self._walk_value_map(
                "1.3.6.1.4.1.674.10892.5.4.1100.30.1.17"
            )
            cpu_threads = await self._walk_value_map(
                "1.3.6.1.4.1.674.10892.5.4.1100.30.1.19"
            )
            for idx in sorted(set(cpu_names) | set(cpu_models), key=lambda x: (int(x) if str(x).isdigit() else 0)):
                cpus.append({
                    "index": idx,
                    "name": str(cpu_names.get(idx) or f"CPU {idx}"),
                    "model": str(cpu_models.get(idx) or ""),
                    "cores": _as_int(cpu_cores.get(idx)),
                    "threads": _as_int(cpu_threads.get(idx)),
                })
            # Dell memory device table
            mem_names = await self._walk_value_map(
                "1.3.6.1.4.1.674.10892.5.4.1100.50.1.8", decode=True
            )
            mem_banks = await self._walk_value_map(
                "1.3.6.1.4.1.674.10892.5.4.1100.50.1.10", decode=True
            )
            mem_sizes = await self._walk_value_map(
                "1.3.6.1.4.1.674.10892.5.4.1100.50.1.14"
            )
            for idx, raw in mem_sizes.items():
                size_kb = _as_float(raw)
                if size_kb is None or size_kb <= 0:
                    continue
                memory_modules.append({
                    "index": idx,
                    "name": str(mem_names.get(idx) or f"内存 {idx}"),
                    "bank": str(mem_banks.get(idx) or ""),
                    "size_gb": round(size_kb / 1024 / 1024, 2),
                    "unit": "GB",
                })
            if any((temperatures, fans, power_supplies, disks, cpus, memory_modules)):
                vendor = "Dell"
        except Exception as exc:  # noqa: BLE001
            logger.debug("Dell 组件明细读取失败 %s: %s", self.host, exc)

        # 华为 iBMC 仅在非 Dell 设备上执行，避免 Dell 服务器被华为表污染
        if vendor != "Dell":
            # 华为 iBMC（HUAWEI-SERVER-iBMC-MIB）专用表：
            # powerSupply .6，fan .8，sensor .13，cpu .15。只遍历 4 张表，避免逐字段超时。
            try:
                huawei_root = "1.3.6.1.4.1.2011.2.235.1.1"
                # 常见 RH2288/CE 等 iBMC：PSU 1-2、Fan 1-8、CPU 1-2。
                # 先并发点查这些固定索引，比逐表遍历快很多；失败再回退整表遍历。
                direct: Dict[str, Any] = {}
                power_oids: Dict[tuple, str] = {}
                for idx in ("1", "2"):
                    for field in ("4", "6", "7", "8", "9", "13"):
                        power_oids[(field, idx)] = f"{huawei_root}.6.50.1.{field}.{idx}"
                fan_oids: Dict[tuple, str] = {}
                for idx in [str(i) for i in range(1, 9)]:
                    for field in ("2", "3", "4", "7", "8"):
                        fan_oids[(field, idx)] = f"{huawei_root}.8.50.1.{field}.{idx}"
                cpu_oids: Dict[tuple, str] = {}
                for idx in ("1", "2"):
                    for field in ("4", "10", "12", "13"):
                        cpu_oids[(field, idx)] = f"{huawei_root}.15.50.1.{field}.{idx}"
                all_oids = list(power_oids.values()) + list(fan_oids.values()) + list(cpu_oids.values())
                direct = await self.get_many(all_oids)
                power_table: Dict[str, Dict[str, Any]] = {}
                fan_table: Dict[str, Dict[str, Any]] = {}
                cpu_table: Dict[str, Dict[str, Any]] = {}
                for (field, idx), oid in power_oids.items():
                    power_table.setdefault(field, {})[idx] = direct.get(oid)
                for (field, idx), oid in fan_oids.items():
                    fan_table.setdefault(field, {})[idx] = direct.get(oid)
                for (field, idx), oid in cpu_oids.items():
                    cpu_table.setdefault(field, {})[idx] = direct.get(oid)
                if not any(power_table.values()) and not any(fan_table.values()) and not any(cpu_table.values()):
                    power_table = await self._walk_table_map(huawei_root + ".6.50.1")
                    fan_table = await self._walk_table_map(huawei_root + ".8.50.1")
                    cpu_table = await self._walk_table_map(huawei_root + ".15.50.1")

                # 电源：字段 4 型号、6 额定功率、7 状态、8 输入功率、9 在位、13 名称。
                power_names = power_table.get("13", {})
                for idx in sorted(set(power_names) | set(power_table.get("8", {})), key=lambda x: int(x) if str(x).isdigit() else 0):
                    watts = _as_float(power_table.get("8", {}).get(idx))
                    status = _as_int(power_table.get("7", {}).get(idx))
                    if watts is None and status is None:
                        continue
                    power_supplies.append({
                        "index": idx,
                        "name": str(_decode_octets(power_names.get(idx)) or f"电源 {idx}"),
                        "model": str(_decode_octets(power_table.get("4", {}).get(idx)) or ""),
                        "watts": round(watts, 1) if watts is not None else None,
                        "voltage": None,
                        "rating_watts": _as_int(power_table.get("6", {}).get(idx)),
                        "status": status,
                        "status_label": {1: "正常", 2: "轻微", 3: "严重", 4: "致命", 5: "不在位", 6: "未知"}.get(status, "未知"),
                        "present": _as_int(power_table.get("9", {}).get(idx)) == 2,
                        "unit": "W",
                    })

                # 风扇：字段 2 转速 RPM、3 在位、4 状态、7 名称、8 百分比。
                fan_names = fan_table.get("7", {})
                for idx in sorted(set(fan_names) | set(fan_table.get("2", {})), key=lambda x: int(x) if str(x).isdigit() else 0):
                    speed = _as_float(fan_table.get("2", {}).get(idx))
                    if speed is None or speed < 0:
                        continue
                    status = _as_int(fan_table.get("4", {}).get(idx))
                    fans.append({
                        "index": idx,
                        "name": str(_decode_octets(fan_names.get(idx)) or f"风扇 {idx}"),
                        "value": round(speed, 0),
                        "unit": "RPM",
                        "percent": _as_int(fan_table.get("8", {}).get(idx)),
                        "status": status,
                        "status_label": {1: "正常", 2: "轻微", 3: "严重", 4: "致命", 5: "不在位", 6: "未知"}.get(status, "未知"),
                        "present": _as_int(fan_table.get("3", {}).get(idx)) == 2,
                    })

                # 温度：直接构造常用 iBMC 传感器 OID，避免遍历整张 136 行传感器表。
                temp_names = [
                    "Inlet Temp", "Outlet Temp", "PCH Temp", "RAID Temp", "RearDisk1 Temp",
                    "CPU1 Core Rem", "CPU1 MEM Temp", "CPU1 VDDQ Temp", "CPU1 VRD Temp",
                    "CPU2 Core Rem", "CPU2 MEM Temp", "CPU2 VDDQ Temp", "CPU2 VRD Temp",
                ]
                temp_oids: Dict[str, str] = {}
                for name in temp_names:
                    temp_oids[name] = self._ibmc_sensor_oid("2", name)
                    temp_oids[name + "|status"] = self._ibmc_sensor_oid("9", name)
                temp_values = await self.get_many(list(temp_oids.values()))
                for name in temp_names:
                    value = _as_float(temp_values.get(temp_oids[name]))
                    if value is None or not -40 <= value <= 200:
                        continue
                    # DTS 等名称可能返回负值/无效值，已由上界过滤；其余作为对应部件温度保留。
                    temperatures.append({
                        "index": name,
                        "name": name,
                        "value": round(value, 1),
                        "unit": "°C",
                        "kind": self._temperature_kind(name),
                        "status": str(temp_values.get(temp_oids[name + "|status"]) or "").strip(),
                    })

                # 硬盘：DISK0~DISKD，reading 为 na，但 status=0x8001 表示在位。
                disk_names = [f"DISK{i}" for i in range(10)] + ["DISKA", "DISKB", "DISKC", "DISKD"]
                disk_oids = {name: self._ibmc_sensor_oid("9", name) for name in disk_names}
                disk_values = await self.get_many(list(disk_oids.values()))
                for name in disk_names:
                    status = str(disk_values.get(disk_oids[name]) or "").strip()
                    present = status.lower() not in ("0x8000", "na", "absent", "")
                    if present:
                        disks.append({
                            "index": name,
                            "name": name,
                            "model": "",
                            "size_gb": None,
                            "unit": "GB",
                            "status": status,
                            "status_label": "在位",
                            "present": True,
                        })


                # CPU：字段 10 名称、4 型号、12 核心、13 线程。
                cpu_names = cpu_table.get("10", {})
                for idx in sorted(set(cpu_names), key=lambda x: int(x) if str(x).isdigit() else 0):
                    cpus.append({
                        "index": idx,
                        "name": str(_decode_octets(cpu_names.get(idx)) or f"CPU {idx}"),
                        "model": str(_decode_octets(cpu_table.get("4", {}).get(idx)) or ""),
                        "cores": _as_int(cpu_table.get("12", {}).get(idx)),
                        "threads": _as_int(cpu_table.get("13", {}).get(idx)),
                    })

                if any((temperatures, fans, power_supplies, disks, cpus)):
                    vendor = "Huawei iBMC"
            except Exception as exc:  # noqa: BLE001
                logger.debug("华为 iBMC 组件明细读取失败 %s: %s", self.host, exc)


        # 非 Dell/华为或表缺失时，回退 ENTITY-SENSORS，至少保留多个温度/风扇点
        if not temperatures and not fans:
            try:
                values = await self._walk_value_map(OID_ENT_SENSOR_VALUE)
                types = await self._walk_value_map(OID_ENT_SENSOR_TYPE)
                scales = await self._walk_value_map(OID_ENT_SENSOR_SCALE)
                names = await self._walk_value_map(OID_ENT_PHYS_DESCR, decode=True)
                for idx, raw in values.items():
                    value = _as_float(raw)
                    if value is None:
                        continue
                    scale = _as_int(scales.get(idx)) or 0
                    if scale == 8:
                        value /= 1000.0
                    elif scale == 7:
                        value /= 1_000_000.0
                    elif scale == 10:
                        value *= 10
                    name = str(names.get(idx) or f"传感器 {idx}")
                    if str(types.get(idx)) in TEMP_SENSOR_TYPES and -40 <= value <= 200:
                        temperatures.append({
                            "index": idx, "name": name, "value": round(value, 1),
                            "unit": "°C", "kind": self._temperature_kind(name),
                        })
                    elif str(types.get(idx)) in {"6", "9"}:
                        fans.append({
                            "index": idx, "name": name, "value": round(value, 0), "unit": "RPM",
                        })
            except Exception as exc:  # noqa: BLE001
                logger.debug("ENTITY 组件明细读取失败 %s: %s", self.host, exc)

        def _bad_text(value: Any) -> bool:
            text = str(value or "").strip().lower()
            return text.startswith(("no such", "no access", "nosuch", "timeout", "no response")) or text in ("na", "n/a", "unknown")

        cpus = [item for item in cpus if not _bad_text(item.get("name")) and not _bad_text(item.get("model"))]
        memory_modules = [item for item in memory_modules if not _bad_text(item.get("name"))]
        disks = [
            item for item in disks
            if not _bad_text(item.get("name")) and not _bad_text(item.get("status_label")) and not _bad_text(item.get("status"))
        ]
        return {
            "vendor": vendor or "Generic",
            "cpus": cpus,
            "memory_modules": memory_modules,
            "temperatures": temperatures,
            "fans": fans,
            "power_supplies": power_supplies,
            "disks": disks,
            "summary": {
                "cpu_count": len(cpus),
                "memory_module_count": len(memory_modules),
                "memory_total_gb": round(sum(float(x.get("size_gb") or 0) for x in memory_modules), 2),
                "fan_count": len(fans),
                "power_supply_count": len(power_supplies),
                "disk_count": len(disks),
                "disk_total_gb": round(sum(float(x.get("size_gb") or 0) for x in disks), 2),
                "temperature_count": len(temperatures),
            },
        }

    async def get_interfaces(self) -> List[Dict[str, Any]]:
        """接口表：状态 + 流量计数（支持 64 位 HC 计数器）"""
        names = {_last_index(o): _decode_octets(v) for o, v in await self.walk(OID_IF_NAME)}
        descrs = {_last_index(o): _decode_octets(v) for o, v in await self.walk(OID_IF_DESCR)}
        types = {_last_index(o): _as_int(v) for o, v in await self.walk(OID_IF_TYPE)}
        mtus = {_last_index(o): _as_int(v) for o, v in await self.walk(OID_IF_MTU)}
        speeds = {_last_index(o): _as_int(v) for o, v in await self.walk(OID_IF_SPEED)}
        macs = {_last_index(o): _decode_mac(v) for o, v in await self.walk(OID_IF_PHYS_ADDRESS)}
        admins = {_last_index(o): str(v).strip() for o, v in await self.walk(OID_IF_ADMIN_STATUS)}
        opers = {_last_index(o): str(v).strip() for o, v in await self.walk(OID_IF_OPER_STATUS)}
        in_octets = {_last_index(o): _as_int(v) for o, v in await self.walk(OID_IF_IN_OCTETS)}
        out_octets = {_last_index(o): _as_int(v) for o, v in await self.walk(OID_IF_OUT_OCTETS)}
        in_errs = {_last_index(o): _as_int(v) for o, v in await self.walk(OID_IF_IN_ERRORS)}
        out_errs = {_last_index(o): _as_int(v) for o, v in await self.walk(OID_IF_OUT_ERRORS)}

        # 64 位计数器优先
        hc_in = {_last_index(o): _as_int(v) for o, v in await self.walk(OID_IF_HC_IN_OCTETS)}
        hc_out = {_last_index(o): _as_int(v) for o, v in await self.walk(OID_IF_HC_OUT_OCTETS)}

        indices = set(opers) | set(names) | set(descrs)
        result: List[Dict[str, Any]] = []
        for idx in sorted(indices, key=lambda x: (int(x) if x.isdigit() else 0)):
            oper = opers.get(idx)
            admin = admins.get(idx)
            result.append({
                "index": idx,
                "name": names.get(idx) or descrs.get(idx) or f"if{idx}",
                "description": descrs.get(idx) or "",
                "mac": macs.get(idx),
                "type": types.get(idx),
                "mtu": mtus.get(idx),
                "speed": speeds.get(idx),
                "admin_status": IF_ADMIN_MAP.get(admin or "", "unknown"),
                "oper_status": IF_OPER_MAP.get(oper or "", "unknown"),
                "in_octets": hc_in.get(idx) if hc_in.get(idx) is not None else in_octets.get(idx),
                "out_octets": hc_out.get(idx) if hc_out.get(idx) is not None else out_octets.get(idx),
                "in_errors": in_errs.get(idx),
                "out_errors": out_errs.get(idx),
            })
        return result

    async def get_lldp_neighbors(self) -> List[Dict[str, Any]]:
        """LLDP 邻居（回退 CDP），返回 [{local_port_num, remote_sys_name, remote_chassis_id, remote_port_id, remote_mgmt_ip}]

        优化: 先只 walk sysName 一列，若为空则判定不支持 LLDP 并快速回退 CDP，
        避免对不支持该 MIB 的设备做多次无效 walk。
        """
        neighbours: Dict[str, Dict[str, Any]] = {}

        # 1) 先探测 LLDP 是否有邻居
        sysnames = {o: _decode_octets(v) for o, v in await self.walk(OID_LLDP_REM_SYS_NAME)}

        if sysnames:
            chassis = {o: _decode_octets(v) for o, v in await self.walk(OID_LLDP_REM_CHASSIS_ID)}
            ports = {o: _decode_octets(v) for o, v in await self.walk(OID_LLDP_REM_PORT_ID)}
            for oid, name in sysnames.items():
                # lldpRemEntry 索引为 lldpRemTimeMark.lldpRemLocalPortNum.lldpRemIndex
                parts = oid.split(".")
                if len(parts) < 3:
                    continue
                neighbours[oid] = {
                    "local_port_num": parts[-2],
                    "remote_sys_name": name,
                    "remote_chassis_id": chassis.get(oid) or "",
                    "remote_port_id": ports.get(oid) or "",
                    "remote_mgmt_ip": "",
                }
            return list(neighbours.values())

        # 2) CDP 回退（Cisco）
        dev_ids = {o: _decode_octets(v) for o, v in await self.walk(OID_CDP_CACHE_DEVID)}
        if not dev_ids:
            return []

        dev_ports = {o: _decode_octets(v) for o, v in await self.walk(OID_CDP_CACHE_DEVPORT)}
        platforms = {o: _decode_octets(v) for o, v in await self.walk(OID_CDP_CACHE_PLATFORM)}
        for oid, dev_id in dev_ids.items():
            parts = oid.split(".")
            neighbours[oid] = {
                "local_port_num": parts[-2] if len(parts) >= 2 else "",
                "remote_sys_name": dev_id or "",
                "remote_chassis_id": dev_id or "",
                "remote_port_id": dev_ports.get(oid) or "",
                "remote_mgmt_ip": "",
                "platform": platforms.get(oid) or "",
            }

        return list(neighbours.values())

    async def self_test(self) -> Dict[str, Any]:
        """连通性自检"""
        info = await self.get_system_info()
        return {
            "reachable": info.get("sysdescr") is not None or info.get("sysname") is not None,
            "host": self.host,
            "sys_name": info.get("sysname"),
            "sys_descr": info.get("sysdescr"),
            "uptime": info.get("uptime"),
        }


async def test_connection(
    host: str,
    community: str = "public",
    version: str = "v2c",
    port: int = 161,
    timeout: int = 3,
    **v3_kwargs: Any,
) -> Dict[str, Any]:
    """测试 SNMP 连通性（供 API 调用，支持 v3 参数透传）"""
    client = SNMPClient(
        host=host,
        community=community,
        version=version,
        port=port,
        timeout=timeout,
        **v3_kwargs,
    )
    result = await client.self_test()
    result["version"] = version
    return result
