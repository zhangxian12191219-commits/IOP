"""内置标准 MIB 符号库（用于依赖自动解析与「导入标准 MIB 库」）

不依赖外部 MIB 文件：内置常用标准 MIB 的对象名 → OID 映射，
导入厂商 MIB 时自动用于解析 IMPORTS 中的标准对象（sysDescr/ifIndex/hrProcessorLoad…），
减少「未解析」数量；也作为可浏览的标准 MIB 库导入到数据库。

如需更完整的标准库，可把 .mib 文件放入 `mibs/standard/`，上传/解析时会自动加载。
"""
import logging
from pathlib import Path
from typing import Dict, List

logger = logging.getLogger(__name__)

# 模块名 -> {对象名: OID}
STANDARD_MODULES: Dict[str, Dict[str, str]] = {
    "SNMPv2-MIB": {
        "system": "1.3.6.1.2.1.1",
        "sysDescr": "1.3.6.1.2.1.1.1",
        "sysObjectID": "1.3.6.1.2.1.1.2",
        "sysUpTime": "1.3.6.1.2.1.1.3",
        "sysContact": "1.3.6.1.2.1.1.4",
        "sysName": "1.3.6.1.2.1.1.5",
        "sysLocation": "1.3.6.1.2.1.1.6",
        "sysServices": "1.3.6.1.2.1.1.7",
        "snmpTrapOID": "1.3.6.1.6.3.1.1.4.1",
    },
    "IF-MIB": {
        "interfaces": "1.3.6.1.2.1.2",
        "ifNumber": "1.3.6.1.2.1.2.1",
        "ifTable": "1.3.6.1.2.1.2.2",
        "ifEntry": "1.3.6.1.2.1.2.2.1",
        "ifIndex": "1.3.6.1.2.1.2.2.1.1",
        "ifDescr": "1.3.6.1.2.1.2.2.1.2",
        "ifType": "1.3.6.1.2.1.2.2.1.3",
        "ifMtu": "1.3.6.1.2.1.2.2.1.4",
        "ifSpeed": "1.3.6.1.2.1.2.2.1.5",
        "ifPhysAddress": "1.3.6.1.2.1.2.2.1.6",
        "ifAdminStatus": "1.3.6.1.2.1.2.2.1.7",
        "ifOperStatus": "1.3.6.1.2.1.2.2.1.8",
        "ifLastChange": "1.3.6.1.2.1.2.2.1.9",
        "ifInOctets": "1.3.6.1.2.1.2.2.1.10",
        "ifInUcastPkts": "1.3.6.1.2.1.2.2.1.11",
        "ifInDiscards": "1.3.6.1.2.1.2.2.1.13",
        "ifInErrors": "1.3.6.1.2.1.2.2.1.14",
        "ifOutOctets": "1.3.6.1.2.1.2.2.1.16",
        "ifOutUcastPkts": "1.3.6.1.2.1.2.2.1.17",
        "ifOutDiscards": "1.3.6.1.2.1.2.2.1.19",
        "ifOutErrors": "1.3.6.1.2.1.2.2.1.20",
        "ifMIB": "1.3.6.1.2.1.31",
        "ifMIBObjects": "1.3.6.1.2.1.31.1",
        "ifXTable": "1.3.6.1.2.1.31.1.1",
        "ifXEntry": "1.3.6.1.2.1.31.1.1.1",
        "ifName": "1.3.6.1.2.1.31.1.1.1.1",
        "ifHCInOctets": "1.3.6.1.2.1.31.1.1.1.6",
        "ifHCOutOctets": "1.3.6.1.2.1.31.1.1.1.10",
        "ifHighSpeed": "1.3.6.1.2.1.31.1.1.1.15",
        "ifAlias": "1.3.6.1.2.1.31.1.1.1.18",
    },
    "IP-MIB": {
        "ip": "1.3.6.1.2.1.4",
        "ipForwarding": "1.3.6.1.2.1.4.1",
        "ipDefaultTTL": "1.3.6.1.2.1.4.2",
        "ipInReceives": "1.3.6.1.2.1.4.3",
        "ipInHdrErrors": "1.3.6.1.2.1.4.4",
        "ipInAddrErrors": "1.3.6.1.2.1.4.5",
        "ipForwDatagrams": "1.3.6.1.2.1.4.6",
        "ipOutRequests": "1.3.6.1.2.1.4.10",
        "ipInAddrErrors6": "1.3.6.1.2.1.4.32",
    },
    "ICMP-MIB": {
        "icmp": "1.3.6.1.2.1.5",
        "icmpInMsgs": "1.3.6.1.2.1.5.1",
        "icmpInErrors": "1.3.6.1.2.1.5.2",
        "icmpOutMsgs": "1.3.6.1.2.1.5.14",
        "icmpOutErrors": "1.3.6.1.2.1.5.15",
    },
    "TCP-MIB": {
        "tcp": "1.3.6.1.2.1.6",
        "tcpRtoAlgorithm": "1.3.6.1.2.1.6.1",
        "tcpActiveOpens": "1.3.6.1.2.1.6.5",
        "tcpPassiveOpens": "1.3.6.1.2.1.6.6",
        "tcpAttemptFails": "1.3.6.1.2.1.6.7",
        "tcpEstabResets": "1.3.6.1.2.1.6.8",
        "tcpCurrEstab": "1.3.6.1.2.1.6.9",
        "tcpInSegs": "1.3.6.1.2.1.6.10",
        "tcpOutSegs": "1.3.6.1.2.1.6.11",
    },
    "UDP-MIB": {
        "udp": "1.3.6.1.2.1.7",
        "udpInDatagrams": "1.3.6.1.2.1.7.1",
        "udpNoPorts": "1.3.6.1.2.1.7.2",
        "udpInErrors": "1.3.6.1.2.1.7.3",
        "udpOutDatagrams": "1.3.6.1.2.1.7.4",
    },
    "HOST-RESOURCES-MIB": {
        "host": "1.3.6.1.2.1.25",
        "hrSystem": "1.3.6.1.2.1.25.1",
        "hrSystemUptime": "1.3.6.1.2.1.25.1.1",
        "hrSystemDate": "1.3.6.1.2.1.25.1.2",
        "hrSystemNumUsers": "1.3.6.1.2.1.25.1.5",
        "hrSystemProcesses": "1.3.6.1.2.1.25.1.6",
        "hrSystemMaxProcesses": "1.3.6.1.2.1.25.1.7",
        "hrStorage": "1.3.6.1.2.1.25.2",
        "hrMemorySize": "1.3.6.1.2.1.25.2.2",
        "hrStorageTable": "1.3.6.1.2.1.25.2.3",
        "hrStorageEntry": "1.3.6.1.2.1.25.2.3.1",
        "hrStorageIndex": "1.3.6.1.2.1.25.2.3.1.1",
        "hrStorageType": "1.3.6.1.2.1.25.2.3.1.2",
        "hrStorageDescr": "1.3.6.1.2.1.25.2.3.1.3",
        "hrStorageAllocationUnits": "1.3.6.1.2.1.25.2.3.1.4",
        "hrStorageSize": "1.3.6.1.2.1.25.2.3.1.5",
        "hrStorageUsed": "1.3.6.1.2.1.25.2.3.1.6",
        "hrDevice": "1.3.6.1.2.1.25.3",
        "hrDeviceTable": "1.3.6.1.2.1.25.3.2",
        "hrDeviceEntry": "1.3.6.1.2.1.25.3.2.1",
        "hrDeviceIndex": "1.3.6.1.2.1.25.3.2.1.1",
        "hrDeviceType": "1.3.6.1.2.1.25.3.2.1.2",
        "hrDeviceDescr": "1.3.6.1.2.1.25.3.2.1.3",
        "hrDeviceStatus": "1.3.6.1.2.1.25.3.2.1.5",
        "hrProcessorTable": "1.3.6.1.2.1.25.3.3",
        "hrProcessorEntry": "1.3.6.1.2.1.25.3.3.1",
        "hrProcessorLoad": "1.3.6.1.2.1.25.3.3.1.2",
        "hrSWRun": "1.3.6.1.2.1.25.4",
        "hrSWRunTable": "1.3.6.1.2.1.25.4.2",
        "hrSWRunEntry": "1.3.6.1.2.1.25.4.2.1",
        "hrSWRunIndex": "1.3.6.1.2.1.25.4.2.1.1",
        "hrSWRunName": "1.3.6.1.2.1.25.4.2.1.2",
        "hrSWRunStatus": "1.3.6.1.2.1.25.4.2.1.7",
    },
    "ENTITY-MIB": {
        "entityMIB": "1.3.6.1.2.1.47",
        "entPhysical": "1.3.6.1.2.1.47.1",
        "entPhysicalTable": "1.3.6.1.2.1.47.1.1",
        "entPhysicalEntry": "1.3.6.1.2.1.47.1.1.1",
        "entPhysicalIndex": "1.3.6.1.2.1.47.1.1.1.1",
        "entPhysicalDescr": "1.3.6.1.2.1.47.1.1.1.2",
        "entPhysicalVendorType": "1.3.6.1.2.1.47.1.1.1.3",
        "entPhysicalContainedIn": "1.3.6.1.2.1.47.1.1.1.4",
        "entPhysicalClass": "1.3.6.1.2.1.47.1.1.1.5",
        "entPhysicalName": "1.3.6.1.2.1.47.1.1.1.7",
        "entPhysicalHardwareRev": "1.3.6.1.2.1.47.1.1.1.8",
        "entPhysicalFirmwareRev": "1.3.6.1.2.1.47.1.1.1.9",
        "entPhysicalSoftwareRev": "1.3.6.1.2.1.47.1.1.1.10",
        "entPhysicalSerialNum": "1.3.6.1.2.1.47.1.1.1.11",
        "entPhysicalMfgName": "1.3.6.1.2.1.47.1.1.1.12",
        "entPhysicalModelName": "1.3.6.1.2.1.47.1.1.1.13",
        "entPhysicalIsFRU": "1.3.6.1.2.1.47.1.1.1.16",
    },
    "ENTITY-SENSORS-MIB": {
        "entitySensorMIB": "1.3.6.1.2.1.99",
        "entPhySensor": "1.3.6.1.2.1.99.1",
        "entPhySensorTable": "1.3.6.1.2.1.99.1.1",
        "entPhySensorEntry": "1.3.6.1.2.1.99.1.1.1",
        "entPhySensorType": "1.3.6.1.2.1.99.1.1.1.1",
        "entPhySensorScale": "1.3.6.1.2.1.99.1.1.1.2",
        "entPhySensorPrecision": "1.3.6.1.2.1.99.1.1.1.3",
        "entPhySensorValue": "1.3.6.1.2.1.99.1.1.1.4",
        "entPhySensorOperStatus": "1.3.6.1.2.1.99.1.1.1.5",
        "entPhySensorUnitsDisplay": "1.3.6.1.2.1.99.1.1.1.6",
        "entPhySensorValueTimeStamp": "1.3.6.1.2.1.99.1.1.1.7",
        "entPhySensorValueUpdateRate": "1.3.6.1.2.1.99.1.1.1.8",
    },
    "SNMP-FRAMEWORK-MIB": {
        "snmpFrameworkMIB": "1.3.6.1.6.3.10",
        "snmpEngine": "1.3.6.1.6.3.10.2.1",
        "snmpEngineID": "1.3.6.1.6.3.10.2.1.1",
        "snmpEngineBoots": "1.3.6.1.6.3.10.2.1.2",
        "snmpEngineTime": "1.3.6.1.6.3.10.2.1.3",
        "snmpEngineMaxMessageSize": "1.3.6.1.6.3.10.2.1.4",
    },
}

# 标准根节点/常用 OID（保留原有的少量常用项）
COMMON_ROOTS = {
    "iso": "1",
    "org": "1.3",
    "dod": "1.3.6",
    "internet": "1.3.6.1",
    "directory": "1.3.6.1.1",
    "mgmt": "1.3.6.1.2",
    "mib-2": "1.3.6.1.2.1",
    "mib_2": "1.3.6.1.2.1",
    "transmission": "1.3.6.1.2.1.10",
    "experimental": "1.3.6.1.3",
    "private": "1.3.6.1.4",
    "enterprises": "1.3.6.1.4.1",
    "security": "1.3.6.1.5",
    "snmpV2": "1.3.6.1.6",
    "zeroDotZero": "0.0",
}

KNOWN_MODULES = set(STANDARD_MODULES) | {
    "SNMPv2-SMI", "SNMPv2-TC", "SNMPv2-CONF", "SNMPv2-TM",
    "IANAifType-MIB", "RFC1213-MIB", "RMON-MIB", "MAU-MIB",
    "SNMP-TARGET-MIB", "SNMP-NOTIFICATION-MIB", "SNMP-COMMUNITY-MIB",
    "SNMP-USER-BASED-SM-MIB", "SNMP-VIEW-BASED-ACM-MIB",
    "HOST-RESOURCES-TYPES", "SNMPv2-USEC", "SNMPv2-MIB-1990",
}


def symbol_map() -> Dict[str, str]:
    """所有标准对象名 → OID（用于解析依赖）"""
    mapping: Dict[str, str] = dict(COMMON_ROOTS)
    for symbols in STANDARD_MODULES.values():
        mapping.update(symbols)
    return mapping


def known_modules() -> set:
    return set(KNOWN_MODULES)


def library_objects() -> List[Dict[str, str]]:
    """标准库对象列表（用于导入为可浏览的 MIB 文件）"""
    items: List[Dict[str, str]] = []
    for module, symbols in STANDARD_MODULES.items():
        for name, oid in symbols.items():
            items.append({
                "name": name,
                "oid": oid,
                "module": module,
                "syntax": "",
                "access": "read-only",
                "status": "current",
                "description": f"标准 {module} 对象",
                "category": "",
            })
    return items


def standard_dir() -> Path:
    from ..config import PROJECT_ROOT

    return Path(PROJECT_ROOT) / "mibs" / "standard"


def load_standard_dir_symbols() -> Dict[str, str]:
    """解析 mibs/standard/ 下的 MIB 文件并返回对象映射（可选扩展）"""
    from . import mib_parser

    directory = standard_dir()
    mapping: Dict[str, str] = {}
    if not directory.exists():
        return mapping
    for path in sorted(directory.glob("*.mib")) + sorted(directory.glob("*.txt")):
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
            parsed = mib_parser.parse_mib(text, path.name, known_oids=mapping)
            for obj in parsed.get("objects", []):
                if obj.get("oid"):
                    mapping[obj["name"]] = obj["oid"]
        except Exception as exc:  # noqa: BLE001
            logger.warning("解析标准 MIB 目录文件失败 %s: %s", path.name, exc)
    return mapping
