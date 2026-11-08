"""内置常用厂商 MIB 对象库。

说明：
- 不是把厂商受版权保护的完整 ASN.1 MIB 文件内置，而是内置「常用对象 + 标准 MIB」
  的对象目录，方便开箱即用、按设备类型筛选和 OID 测试。
- 厂商私有 OID 存在型号/版本差异，完整采集前仍建议导入厂商官方 MIB 文件核对。
- 所有库都包含 SNMPv2-MIB / IF-MIB / HOST-RESOURCES-MIB / ENTITY-MIB 等标准对象。
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from ..models.mib import MibFile, MibObject

CATEGORY_LABELS = {
    "switch": "交换机",
    "server": "服务器",
    "storage": "存储",
    "security": "安全设备",
}


def _obj(name: str, oid: str, category: str, description: str,
         syntax: str = "INTEGER", score: int = 5) -> Dict[str, Any]:
    return {
        "name": name,
        "oid": oid,
        "syntax": syntax,
        "access": "read-only",
        "status": "current",
        "description": description,
        "category": category,
        "score": score,
    }


SYSTEM_OBJECTS = [
    _obj("sysDescr", "1.3.6.1.2.1.1.1.0", "", "设备系统描述", "DisplayString", 2),
    _obj("sysUpTime", "1.3.6.1.2.1.1.3.0", "", "设备运行时长", "TimeTicks", 2),
    _obj("sysName", "1.3.6.1.2.1.1.5.0", "", "设备名称", "DisplayString", 2),
]

SWITCH_OBJECTS = [
    _obj("ifNumber", "1.3.6.1.2.1.2.1.0", "interface", "接口数量", "Integer32"),
    _obj("ifDescr", "1.3.6.1.2.1.2.2.1.2", "interface", "接口描述"),
    _obj("ifOperStatus", "1.3.6.1.2.1.2.2.1.8", "interface", "接口运行状态"),
    _obj("ifInErrors", "1.3.6.1.2.1.2.2.1.14", "interface", "接口入方向错误包"),
    _obj("ifOutErrors", "1.3.6.1.2.1.2.2.1.20", "interface", "接口出方向错误包"),
    _obj("ifHCInOctets", "1.3.6.1.2.1.31.1.1.1.6", "interface", "接口入方向高速字节计数", "Counter64"),
    _obj("ifHCOutOctets", "1.3.6.1.2.1.31.1.1.1.10", "interface", "接口出方向高速字节计数", "Counter64"),
    # 交换机可能不支持 HOST-RESOURCES，但作为标准对象候选提供，便于“推荐 OID”兜底
    _obj("hrProcessorLoad", "1.3.6.1.2.1.25.3.3.1.2", "cpu", "处理器负载（标准 HOST-RESOURCES）"),
    _obj("hrMemorySize", "1.3.6.1.2.1.25.2.2", "memory", "主机内存大小（标准 HOST-RESOURCES）", "Integer32"),
    _obj("hrStorageSize", "1.3.6.1.2.1.25.2.3.1.5", "storage", "存储总容量（标准 HOST-RESOURCES）", "Integer32"),
    _obj("hrStorageUsed", "1.3.6.1.2.1.25.2.3.1.6", "storage", "存储已用容量（标准 HOST-RESOURCES）", "Integer32"),
    _obj("entPhySensorValue", "1.3.6.1.2.1.99.1.1.1.4", "temperature", "物理传感器读数（标准 ENTITY-SENSORS）", "Integer32"),
    _obj("entPhySensorFanValue", "1.3.6.1.2.1.99.1.1.1.4", "fan", "风扇/转速类传感器读数（标准 ENTITY-SENSORS，按 entPhySensorType 筛选）", "Integer32"),
    _obj("entPhySensorPowerValue", "1.3.6.1.2.1.99.1.1.1.4", "power", "电源/电压/电流类传感器读数（标准 ENTITY-SENSORS，按 entPhySensorType 筛选）", "Integer32"),
]

SERVER_OBJECTS = [
    _obj("hrProcessorLoad", "1.3.6.1.2.1.25.3.3.1.2", "cpu", "处理器负载（百分比）"),
    _obj("hrMemorySize", "1.3.6.1.2.1.25.2.2", "memory", "主机内存大小", "Integer32"),
    _obj("hrStorageDescr", "1.3.6.1.2.1.25.2.3.1.3", "storage", "存储/文件系统描述"),
    _obj("hrStorageAllocationUnits", "1.3.6.1.2.1.25.2.3.1.4", "storage", "存储分配单元", "Integer32"),
    _obj("hrStorageSize", "1.3.6.1.2.1.25.2.3.1.5", "storage", "存储总容量", "Integer32"),
    _obj("hrStorageUsed", "1.3.6.1.2.1.25.2.3.1.6", "storage", "存储已用容量", "Integer32"),
    _obj("entPhysicalModelName", "1.3.6.1.2.1.47.1.1.1.13", "", "物理实体型号"),
    _obj("entPhysicalSerialNum", "1.3.6.1.2.1.47.1.1.1.11", "", "物理实体序列号"),
    _obj("entPhysicalMfgName", "1.3.6.1.2.1.47.1.1.1.12", "", "物理实体厂商"),
    _obj("entPhySensorValue", "1.3.6.1.2.1.99.1.1.1.4", "temperature", "物理传感器读数（温度/电压/风扇等）", "Integer32"),
    _obj("entPhySensorFanValue", "1.3.6.1.2.1.99.1.1.1.4", "fan", "风扇/转速类传感器读数（按 entPhySensorType 筛选）", "Integer32"),
    _obj("entPhySensorPowerValue", "1.3.6.1.2.1.99.1.1.1.4", "power", "电源/电压/电流类传感器读数（按 entPhySensorType 筛选）", "Integer32"),
    _obj("hrStorageAllocationUnits", "1.3.6.1.2.1.25.2.3.1.4", "storage", "存储分配单元", "Integer32"),
]

STORAGE_OBJECTS = [
    _obj("hrStorageDescr", "1.3.6.1.2.1.25.2.3.1.3", "storage", "存储池/文件系统描述"),
    _obj("hrStorageAllocationUnits", "1.3.6.1.2.1.25.2.3.1.4", "storage", "存储分配单元", "Integer32"),
    _obj("hrStorageSize", "1.3.6.1.2.1.25.2.3.1.5", "storage", "存储总容量", "Integer32"),
    _obj("hrStorageUsed", "1.3.6.1.2.1.25.2.3.1.6", "storage", "存储已用容量", "Integer32"),
    _obj("entPhysicalModelName", "1.3.6.1.2.1.47.1.1.1.13", "", "控制器/机框型号"),
    _obj("entPhysicalSerialNum", "1.3.6.1.2.1.47.1.1.1.11", "", "控制器/机框序列号"),
    _obj("entPhysicalClass", "1.3.6.1.2.1.47.1.1.1.5", "", "物理实体类型", "INTEGER"),
]

HUAWEI_SWITCH_EXTRA = [
    _obj("hwEntityCpuUsage", "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.5", "cpu", "华为实体 CPU 使用率"),
    _obj("hwEntityMemUsage", "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.7", "memory", "华为实体内存使用率"),
    _obj("hwEntityTemperature", "1.3.6.1.4.1.2011.5.25.31.1.1.1.1.11", "temperature", "华为实体温度"),
    _obj("hwEntityFanSpeed", "1.3.6.1.4.1.2011.5.25.31.1.1.10.1.5", "fan", "华为实体风扇转速"),
    _obj("hwEntityPwrCurrent", "1.3.6.1.4.1.2011.5.25.31.1.1.18.1.7", "power", "华为电源电流"),
    _obj("hwEntityPwrVoltage", "1.3.6.1.4.1.2011.5.25.31.1.1.18.1.8", "power", "华为电源电压"),
    _obj("hwEntityPwrPower", "1.3.6.1.4.1.2011.5.25.31.1.1.18.1.10", "power", "华为电源功率"),
]

FUTUREMATRIX_SWITCH_EXTRA = [
    _obj("fmEntityCpuUsage", "1.3.6.1.4.1.56813.5.25.31.1.1.1.1.5", "cpu", "FutureMatrix 实体 CPU 使用率"),
    _obj("fmEntityMemUsage", "1.3.6.1.4.1.56813.5.25.31.1.1.1.1.7", "memory", "FutureMatrix 实体内存使用率"),
    _obj("fmEntityTemperature", "1.3.6.1.4.1.56813.5.25.31.1.1.1.1.11", "temperature", "FutureMatrix 实体温度"),
    _obj("fmEntityFanSpeed", "1.3.6.1.4.1.56813.5.25.31.1.1.10.1.5", "fan", "FutureMatrix 实体风扇转速/占空比"),
    _obj("fmEntityPwrCurrent", "1.3.6.1.4.1.56813.5.25.31.1.1.18.1.7", "power", "FutureMatrix 电源电流"),
    _obj("fmEntityPwrVoltage", "1.3.6.1.4.1.56813.5.25.31.1.1.18.1.8", "power", "FutureMatrix 电源电压"),
    _obj("fmEntityPwrPower", "1.3.6.1.4.1.56813.5.25.31.1.1.18.1.10", "power", "FutureMatrix 电源功率"),
]

H3C_SWITCH_EXTRA = [
    _obj("hh3cEntityExtCpuUsage", "1.3.6.1.4.1.25506.2.6.1.1.1.1.6", "cpu", "H3C 实体 CPU 使用率"),
    _obj("hh3cEntityExtMemUsage", "1.3.6.1.4.1.25506.2.6.1.1.1.1.8", "memory", "H3C 实体内存使用率"),
    _obj("hh3cEntityExtMemSize", "1.3.6.1.4.1.25506.2.6.1.1.1.1.10", "memory", "H3C 实体内存容量"),
    _obj("hh3cEntityExtTemperature", "1.3.6.1.4.1.25506.2.6.1.1.1.1.12", "temperature", "H3C 实体温度"),
    _obj("hh3cEntityExtVoltage", "1.3.6.1.4.1.25506.2.6.1.1.1.1.14", "power", "H3C 实体电压"),
    _obj("hh3cEntityExtCurrentPower", "1.3.6.1.4.1.25506.2.6.1.3.1.1.3", "power", "H3C 实体当前功率（毫瓦）"),
]

DELL_SERVER_EXTRA = [
    _obj("dellPhysicalDiskSize", "1.3.6.1.4.1.674.10892.5.5.1.20.130.4.1.11", "storage", "Dell 物理磁盘容量（MB）"),
    _obj("dellPhysicalDiskName", "1.3.6.1.4.1.674.10892.5.5.1.20.130.4.1.2", "storage", "Dell 物理磁盘名称"),
    _obj("dellPhysicalDiskModel", "1.3.6.1.4.1.674.10892.5.5.1.20.130.4.1.6", "storage", "Dell 物理磁盘型号"),
    _obj("dellPhysicalDiskSlot", "1.3.6.1.4.1.674.10892.5.5.1.20.130.4.1.55", "storage", "Dell 物理磁盘槽位"),
    _obj("dellFanSpeed", "1.3.6.1.4.1.674.10892.5.4.700.12.1.6", "fan", "Dell 风扇转速（RPM）"),
    _obj("dellFanName", "1.3.6.1.4.1.674.10892.5.4.700.12.1.8", "fan", "Dell 风扇名称"),
    _obj("dellTemperatureProbeReading", "1.3.6.1.4.1.674.10892.5.4.700.20.1.6", "temperature", "Dell 温度探头读数（0.1℃）"),
    _obj("dellTemperatureProbeName", "1.3.6.1.4.1.674.10892.5.4.700.20.1.8", "temperature", "Dell 温度探头名称（CPU/主板/进风/排风）"),
    _obj("dellPowerSupplyOutputWatts", "1.3.6.1.4.1.674.10892.5.4.600.12.1.16", "power", "Dell 电源输出功率（W）"),
    _obj("dellPowerSupplyInputVoltage", "1.3.6.1.4.1.674.10892.5.4.600.12.1.9", "power", "Dell 电源输入电压（V）"),
    _obj("dellPowerSupplyName", "1.3.6.1.4.1.674.10892.5.4.600.12.1.8", "power", "Dell 电源名称"),
    _obj("dellProcessorName", "1.3.6.1.4.1.674.10892.5.4.1100.30.1.26", "cpu", "Dell CPU 插槽名称"),
    _obj("dellProcessorModel", "1.3.6.1.4.1.674.10892.5.4.1100.30.1.23", "cpu", "Dell CPU 型号"),
    _obj("dellProcessorCores", "1.3.6.1.4.1.674.10892.5.4.1100.30.1.17", "cpu", "Dell CPU 核心数"),
    _obj("dellProcessorThreads", "1.3.6.1.4.1.674.10892.5.4.1100.30.1.19", "cpu", "Dell CPU 线程数"),
    _obj("dellMemoryDeviceName", "1.3.6.1.4.1.674.10892.5.4.1100.50.1.8", "memory", "Dell 内存插槽名称"),
    _obj("dellMemoryDeviceBank", "1.3.6.1.4.1.674.10892.5.4.1100.50.1.10", "memory", "Dell 内存通道"),
    _obj("dellMemoryDeviceSize", "1.3.6.1.4.1.674.10892.5.4.1100.50.1.14", "memory", "Dell 内存容量（KB）"),
]

HUAWEI_SERVER_IBMC_EXTRA = [
    _obj("hwIbmcDeviceName", "1.3.6.1.4.1.2011.2.235.1.1.1.6.0", "", "iBMC 设备名称", "DisplayString"),
    _obj("hwIbmcSystemCpuUsage", "1.3.6.1.4.1.2011.2.235.1.1.1.23.0", "cpu", "iBMC 系统 CPU 使用率（%）"),
    _obj("hwIbmcSystemMemUsage", "1.3.6.1.4.1.2011.2.235.1.1.1.25.0", "memory", "iBMC 系统内存使用率（%）"),
    _obj("hwIbmcPowerInputPower", "1.3.6.1.4.1.2011.2.235.1.1.6.50.1.8", "power", "iBMC 电源输入功率（W）"),
    _obj("hwIbmcPowerStatus", "1.3.6.1.4.1.2011.2.235.1.1.6.50.1.7", "power", "iBMC 电源健康状态"),
    _obj("hwIbmcPowerName", "1.3.6.1.4.1.2011.2.235.1.1.6.50.1.13", "power", "iBMC 电源名称（PS1/PS2）", "DisplayString"),
    _obj("hwIbmcPowerRating", "1.3.6.1.4.1.2011.2.235.1.1.6.50.1.6", "power", "iBMC 电源额定功率（W）"),
    _obj("hwIbmcFanSpeed", "1.3.6.1.4.1.2011.2.235.1.1.8.50.1.2", "fan", "iBMC 风扇转速（RPM）"),
    _obj("hwIbmcFanStatus", "1.3.6.1.4.1.2011.2.235.1.1.8.50.1.4", "fan", "iBMC 风扇健康状态"),
    _obj("hwIbmcFanName", "1.3.6.1.4.1.2011.2.235.1.1.8.50.1.7", "fan", "iBMC 风扇名称", "DisplayString"),
    _obj("hwIbmcSensorReading", "1.3.6.1.4.1.2011.2.235.1.1.13.50.1.2", "temperature", "iBMC 传感器读数（温度/电压等）", "DisplayString"),
    _obj("hwIbmcSensorStatus", "1.3.6.1.4.1.2011.2.235.1.1.13.50.1.9", "temperature", "iBMC 传感器状态", "DisplayString"),
    _obj("hwIbmcCpuModel", "1.3.6.1.4.1.2011.2.235.1.1.15.50.1.4", "cpu", "iBMC CPU 型号", "DisplayString"),
    _obj("hwIbmcCpuName", "1.3.6.1.4.1.2011.2.235.1.1.15.50.1.10", "cpu", "iBMC CPU 名称/槽位", "DisplayString"),
    _obj("hwIbmcCpuCores", "1.3.6.1.4.1.2011.2.235.1.1.15.50.1.12", "cpu", "iBMC CPU 核心数"),
    _obj("hwIbmcCpuThreads", "1.3.6.1.4.1.2011.2.235.1.1.15.50.1.13", "cpu", "iBMC CPU 线程数"),
    _obj("hwIbmcDiskStatus", "1.3.6.1.4.1.2011.2.235.1.1.13.50.1.9", "storage", "iBMC 硬盘在位/健康状态（DISK0-DISKD）", "DisplayString"),
]

CISCO_SWITCH_EXTRA = [
    _obj("cpmCPUTotal5minRev", "1.3.6.1.4.1.9.9.109.1.1.1.1.8", "cpu", "Cisco 5 分钟 CPU 使用率"),
    _obj("ciscoMemoryPoolUsed", "1.3.6.1.4.1.9.9.48.1.1.1.5", "memory", "Cisco 内存池已用"),
    _obj("ciscoMemoryPoolFree", "1.3.6.1.4.1.9.9.48.1.1.1.6", "memory", "Cisco 内存池空闲"),
    _obj("ciscoEnvMonTemperatureStatusValue", "1.3.6.1.4.1.9.9.13.1.3.1.3", "temperature", "Cisco 环境温度"),
]

HILLSTONE_FIREWALL_EXTRA = [
    _obj("sysCPU", "1.3.6.1.4.1.28557.2.2.1.3.0", "cpu", "Hillstone CPU 使用率（%）"),
    _obj("sysTotalMemory", "1.3.6.1.4.1.28557.2.2.1.4.0", "memory", "Hillstone 总内存（KB）"),
    _obj("sysCurMemory", "1.3.6.1.4.1.28557.2.2.1.5.0", "memory", "Hillstone 当前内存（KB）"),
    _obj("hillstoneTemperatureValue", "1.3.6.1.4.1.28557.2.28.1.2.1.3", "temperature", "Hillstone 温度"),
]

VENDOR_ROOT = {
    "ruijie": ("ruijieEnterpriseRoot", "1.3.6.1.4.1.4881", "锐捷企业 OID 根"),
    "maipu": ("maipuEnterpriseRoot", "1.3.6.1.4.1.5651", "迈普企业 OID 根"),
    "huawei": ("huaweiEnterpriseRoot", "1.3.6.1.4.1.2011", "华为企业 OID 根"),
    "futurematrix": ("futurematrixEnterpriseRoot", "1.3.6.1.4.1.56813", "FutureMatrix 企业 OID 根"),
    "h3c": ("h3cEnterpriseRoot", "1.3.6.1.4.1.25506", "H3C 企业 OID 根"),
    "dell": ("dellEnterpriseRoot", "1.3.6.1.4.1.674", "戴尔企业 OID 根"),
    "hillstone": ("hillstoneEnterpriseRoot", "1.3.6.1.4.1.28557", "Hillstone 企业 OID 根"),
}


def _root(vendor: str) -> List[Dict[str, Any]]:
    item = VENDOR_ROOT.get(vendor)
    if not item:
        return []
    name, oid, desc = item
    return [_obj(name, oid, "", desc, "OBJECT IDENTIFIER", 1)]


LIBRARIES: List[Dict[str, Any]] = [
    {
        "key": "switch-h3c", "vendor": "H3C", "category": "switch",
        "name": "H3C 交换机常用 MIB", "module": "H3C-SWITCH-COMMON",
        "device_model": "H3C S5130S-52S-HI / H3C Comware 7.1.070",
        "models": ["H3C S5130S-52S-HI", "H3C Comware 7.1.070", "S5130", "S5560", "S6520"],
        "description": "H3C Comware 交换机（实机识别 S5130S-52S-HI / 7.1.070）：标准接口/流量 + HH3C 实体 CPU/内存/温度/电压/功率",
        "objects": SYSTEM_OBJECTS + SWITCH_OBJECTS + H3C_SWITCH_EXTRA + _root("h3c"),
    },
    {
        "key": "switch-huawei", "vendor": "华为", "category": "switch",
        "name": "华为交换机常用 MIB", "module": "HUAWEI-SWITCH-COMMON",
        "device_model": "Huawei S5735S-L48T4S-A1 / S5735S-L48T4X-A1 / CE6850-48S6Q-HI",
        "models": ["S5735S-L48T4S-A1", "S5735S-L48T4X-A1", "CE6850-48S6Q-HI", "S5735S", "CE6850"],
        "description": "华为 S/CE 系列交换机（实机识别 S5735S / CE6850）：标准接口/流量 + HUAWEI-ENTITY-EXTENT CPU/内存/温度",
        "objects": SYSTEM_OBJECTS + SWITCH_OBJECTS + HUAWEI_SWITCH_EXTRA + _root("huawei"),
    },
    {
        "key": "switch-futurematrix", "vendor": "FutureMatrix", "category": "switch",
        "name": "FutureMatrix 交换机常用 MIB", "module": "FUTUREMATRIX-SWITCH-COMMON",
        "device_model": "FutureMatrix S5735S-L48T4S-A1 / S5735S-L48T4X-A1",
        "models": ["FutureMatrix S5735S", "S5735S-L48T4S-A1", "S5735S-L48T4X-A1", "S5735S"],
        "description": "FutureMatrix（华为子品牌）S5735S：标准接口/流量 + 56813 企业实体 CPU/内存/温度/风扇/电源",
        "objects": SYSTEM_OBJECTS + SWITCH_OBJECTS + FUTUREMATRIX_SWITCH_EXTRA + _root("futurematrix"),
    },
    {
        "key": "firewall-hillstone", "vendor": "Hillstone", "category": "security",
        "name": "山石 Hillstone 防火墙常用 MIB", "module": "HILLSTONE-FIREWALL-COMMON",
        "device_model": "Hillstone SG-6000-C3100 / SG-6000-E5260",
        "models": ["SG-6000-C3100", "SG-6000-E5260", "SG-6000"],
        "description": "Hillstone StoneOS（实机识别 SG-6000-C3100 / E5260）：标准接口/流量 + 系统 CPU/内存/温度",
        "objects": SYSTEM_OBJECTS + SWITCH_OBJECTS + HILLSTONE_FIREWALL_EXTRA + _root("hillstone"),
    },
    {
        "key": "switch-ruijie", "vendor": "锐捷", "category": "switch",
        "name": "锐捷交换机常用 MIB", "module": "RUIJIE-SWITCH-COMMON",
        "description": "锐捷 RGOS 交换机：标准接口/流量对象 + 锐捷企业 OID 根",
        "objects": SYSTEM_OBJECTS + SWITCH_OBJECTS + _root("ruijie"),
    },
    {
        "key": "switch-cisco", "vendor": "思科", "category": "switch",
        "name": "思科交换机常用 MIB", "module": "CISCO-SWITCH-COMMON",
        "description": "Cisco Catalyst/Nexus：标准接口对象 + CISCO-PROCESS/MEMORY/ENVMON",
        "objects": SYSTEM_OBJECTS + SWITCH_OBJECTS + CISCO_SWITCH_EXTRA,
    },
    {
        "key": "switch-maipu", "vendor": "迈普", "category": "switch",
        "name": "迈普交换机常用 MIB", "module": "MAIPU-SWITCH-COMMON",
        "description": "迈普 MyPower 交换机：标准接口/流量对象 + 迈普企业 OID 根",
        "objects": SYSTEM_OBJECTS + SWITCH_OBJECTS + _root("maipu"),
    },
    {
        "key": "server-huawei", "vendor": "华为", "category": "server",
        "name": "华为服务器 iBMC 常用 MIB", "module": "HUAWEI-SERVER-IBMC-COMMON",
        "device_model": "RH2288 V3 / RH2288H V3 / RH2285 V3 / 1288H V3 / 2288H V5 / 1288H V5",
        "models": ["RH2288 V3", "RH2288H V3", "RH2285 V3", "1288H V3", "2288H V5", "1288H V5"],
        "description": "华为 FusionServer iBMC：系统 CPU/内存 + PSU 功率/状态 + 风扇转速 + CPU/主板/进出风温度 + 硬盘在位状态（RH2288 V3 实机验证）",
        "objects": SYSTEM_OBJECTS + SERVER_OBJECTS + HUAWEI_SERVER_IBMC_EXTRA + _root("huawei"),
    },
    {
        "key": "server-taishan", "vendor": "泰山", "category": "server",
        "name": "泰山服务器常用 MIB", "module": "TAISHAN-SERVER-COMMON",
        "description": "华为泰山服务器：HOST-RESOURCES + ENTITY + 传感器标准对象",
        "objects": SYSTEM_OBJECTS + SERVER_OBJECTS + _root("huawei"),
    },
    {
        "key": "server-h3c", "vendor": "H3C", "category": "server",
        "name": "H3C 服务器常用 MIB", "module": "H3C-SERVER-COMMON",
        "description": "H3C UniServer：HOST-RESOURCES + ENTITY + 传感器标准对象",
        "objects": SYSTEM_OBJECTS + SERVER_OBJECTS + _root("h3c"),
    },
    {
        "key": "server-dell", "vendor": "戴尔", "category": "server",
        "name": "戴尔服务器常用 MIB", "module": "DELL-SERVER-COMMON",
        "device_model": "Dell PowerEdge / iDRAC (Dell-EMC)",
        "models": ["Dell PowerEdge", "iDRAC", "Dell-EMC"],
        "description": "Dell PowerEdge/iDRAC（实机识别 Dell-EMC iDRAC）：HOST-RESOURCES + ENTITY + 传感器 + 物理磁盘容量",
        "objects": SYSTEM_OBJECTS + SERVER_OBJECTS + DELL_SERVER_EXTRA + _root("dell"),
    },
    {
        "key": "storage-huawei", "vendor": "华为", "category": "storage",
        "name": "华为存储常用 MIB", "module": "HUAWEI-STORAGE-COMMON",
        "description": "华为 OceanStor：标准存储容量/实体对象 + 华为企业 OID 根",
        "objects": SYSTEM_OBJECTS + STORAGE_OBJECTS + _root("huawei"),
    },
    {
        "key": "storage-h3c", "vendor": "H3C", "category": "storage",
        "name": "H3C 存储常用 MIB", "module": "H3C-STORAGE-COMMON",
        "description": "H3C UniStor：标准存储容量/实体对象 + H3C 企业 OID 根",
        "objects": SYSTEM_OBJECTS + STORAGE_OBJECTS + _root("h3c"),
    },
    {
        "key": "storage-dell", "vendor": "戴尔", "category": "storage",
        "name": "戴尔存储常用 MIB", "module": "DELL-STORAGE-COMMON",
        "device_model": "Dell PowerVault ME5 / ME5084 / ME5224 / PowerStore / Unity / SC",
        "models": ["PowerVault ME5", "ME5084", "ME5224", "PowerStore", "Unity", "SC"],
        "description": "Dell PowerVault ME5/ME5084/ME5224、PowerStore、Unity、SC：标准存储容量/实体对象 + Dell 企业 OID 根",
        "objects": SYSTEM_OBJECTS + STORAGE_OBJECTS + _root("dell"),
    },
]

# 仅保留当前资产实际可落地的厂商库；其他厂商/存储/服务器库不再内置，避免“能导入但采不全”。
_KEEP_BUILTIN_KEYS = {
    "switch-h3c",
    "switch-huawei",
    "switch-futurematrix",
    "firewall-hillstone",
    "server-dell",
    "server-huawei",
    "storage-dell",
    "storage-huawei",
    "storage-h3c",
}
# 安全厂商对象库由独立模块维护，启动时一起导入/更新
from .security_mibs import SECURITY_LIBRARIES  # noqa: E402

LIBRARIES.extend(SECURITY_LIBRARIES)
_KEEP_BUILTIN_KEYS.update({item["key"] for item in SECURITY_LIBRARIES})
LIBRARIES = [item for item in LIBRARIES if item["key"] in _KEEP_BUILTIN_KEYS]


def cleanup_obsolete_builtins(db: Session) -> Dict[str, Any]:
    """删除当前内置目录之外的旧内置库，并解除设备引用。"""
    from ..models.models import Device

    obsolete = (
        db.query(MibFile)
        .filter(MibFile.is_builtin == True)  # noqa: E712
        .filter(~MibFile.builtin_key.in_(list(_KEEP_BUILTIN_KEYS)))
        .all()
    )
    deleted = []
    for mib in obsolete:
        db.query(Device).filter(Device.mib_id == mib.id).update(
            {Device.mib_id: None}, synchronize_session=False
        )
        deleted.append({"id": mib.id, "module": mib.module_name, "name": mib.filename})
        db.delete(mib)
    if deleted:
        db.commit()
    return {"deleted": len(deleted), "items": deleted}


def catalog() -> List[Dict[str, Any]]:
    return [
        {
            "key": item["key"],
            "name": item["name"],
            "vendor": item["vendor"],
            "category": item["category"],
            "category_label": CATEGORY_LABELS.get(item["category"], item["category"]),
            "module": item["module"],
            "description": item["description"],
            "device_model": item.get("device_model") or "",
            "models": item.get("models") or [],
            "object_count": len(item["objects"]),
        }
        for item in LIBRARIES
    ]


def _library_objects(item: Dict[str, Any]) -> List[Dict[str, Any]]:
    seen = set()
    result = []
    for obj in item["objects"]:
        if obj["name"] in seen:
            continue
        seen.add(obj["name"])
        result.append(obj)
    return result


def _write_objects(db: Session, mib: MibFile, objects: List[Dict[str, Any]]) -> None:
    for obj in objects:
        db.add(MibObject(
            mib_id=mib.id,
            name=obj["name"][:160],
            oid=obj["oid"][:200],
            syntax=obj.get("syntax") or "",
            access=obj.get("access") or "read-only",
            status=obj.get("status") or "current",
            description=obj.get("description") or "",
            category=obj.get("category") or "",
            score=obj.get("score") or 5,
        ))
    mib.object_count = len(objects)
    mib.readable_count = len(objects)
    mib.categories = sorted({
        obj["category"] for obj in objects if obj.get("category")
    })


def ensure_builtin_mibs(db: Session, only_keys: Optional[List[str]] = None) -> Dict[str, Any]:
    """导入缺失的内置厂商库，并同步已有内置库的对象定义。"""
    wanted = set(only_keys or [])
    created = []
    updated = []
    for item in LIBRARIES:
        if wanted and item["key"] not in wanted:
            continue
        existing = (
            db.query(MibFile)
            .filter(MibFile.module_name == item["module"])
            .first()
        )
        if existing:
            if not existing.is_builtin:
                # 兼容手工导入过同名模块：只补充内置标记，不覆盖用户对象
                existing.is_builtin = True
                existing.builtin_key = item["key"]
                existing.device_category = item["category"]
                existing.vendor = item["vendor"]
                existing.device_model = (item.get("device_model") or existing.device_model or "")[:120]
                existing.note = f"内置常用对象库。{item['description']}。完整厂商私有 MIB 请导入官方文件。"
                db.commit()
                continue

            objects = _library_objects(item)
            current = {
                row[0]: (row[1], row[2])
                for row in db.query(MibObject.name, MibObject.oid, MibObject.category)
                .filter(MibObject.mib_id == existing.id)
                .all()
            }
            desired = {
                obj["name"]: (obj["oid"], obj.get("category"))
                for obj in objects
            }
            if current != desired or (existing.object_count or 0) != len(objects):
                db.query(MibObject).filter(MibObject.mib_id == existing.id).delete(
                    synchronize_session=False
                )
                _write_objects(db, existing, objects)
                updated.append(item["key"])
            meta_changed = False
            if existing.device_category != item["category"]:
                existing.device_category = item["category"]
                meta_changed = True
            if existing.vendor != item["vendor"]:
                existing.vendor = item["vendor"]
                meta_changed = True
            desired_model = (item.get("device_model") or existing.device_model or "")[:120]
            if (existing.device_model or "") != desired_model:
                existing.device_model = desired_model
                meta_changed = True
            note = f"内置常用对象库。{item['description']}。完整厂商私有 MIB 请导入官方文件。"
            if existing.note != note:
                existing.note = note
                meta_changed = True
            if meta_changed:
                db.commit()
            continue

        objects = _library_objects(item)
        mib = MibFile(
            filename=f"[内置] {item['name']}.mib",
            module_name=item["module"],
            size=0,
            object_count=0,
            readable_count=0,
            unresolved_count=0,
            categories=[],
            imports=[],
            note=f"内置常用对象库。{item['description']}。完整厂商私有 MIB 请导入官方文件。",
            is_builtin=True,
            builtin_key=item["key"],
            device_category=item["category"],
            vendor=item["vendor"],
            device_model=(item.get("device_model") or "")[:120],
        )
        db.add(mib)
        db.flush()
        _write_objects(db, mib, objects)
        created.append(item["key"])
    if created or updated:
        db.commit()
    return {"created": created, "updated": updated, "total": len(created) + len(updated)}
