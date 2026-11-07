"""安全厂商内置 MIB 对象库（来自厂商公开/官方 MIB 归档解析）。

只收录可直接读取并已确认语义的对象，不把 PDF/日志格式说明臆造为可采集 OID。
来源：
- 天融信 NGFW2.3 / NGVONE2.0 MIB（TOS-SYSSTATE/TOS-SYSINFO/TOS-FAN/TOS-POWER）
- 深信服 AF SANGFOR-MIB
- 迪普 DPTECH-SYSTEM-MIB
- 启明星辰天清安全隔离与信息交换系统 MIB 描述表
"""
from __future__ import annotations

from typing import Any, Dict, List


def _obj(name: str, oid: str, category: str, description: str,
         syntax: str = "Integer32", score: int = 6) -> Dict[str, Any]:
    return {
        "name": name, "oid": oid, "syntax": syntax, "access": "read-only",
        "status": "current", "description": description,
        "category": category, "score": score,
    }


COMMON_OBJECTS = [
    _obj("sysDescr", "1.3.6.1.2.1.1.1.0", "", "设备系统描述", "DisplayString", 2),
    _obj("sysObjectID", "1.3.6.1.2.1.1.2.0", "", "设备厂商对象标识", "OBJECT IDENTIFIER", 2),
    _obj("sysUpTime", "1.3.6.1.2.1.1.3.0", "", "设备运行时长", "TimeTicks", 2),
    _obj("sysName", "1.3.6.1.2.1.1.5.0", "", "设备名称", "DisplayString", 2),
    _obj("ifDescr", "1.3.6.1.2.1.2.2.1.2", "interface", "接口描述", "DisplayString", 4),
    _obj("ifOperStatus", "1.3.6.1.2.1.2.2.1.8", "interface", "接口运行状态", "INTEGER", 5),
    _obj("ifHCInOctets", "1.3.6.1.2.1.31.1.1.1.6", "interface", "接口入方向字节计数", "Counter64", 4),
    _obj("ifHCOutOctets", "1.3.6.1.2.1.31.1.1.1.10", "interface", "接口出方向字节计数", "Counter64", 4),
]

TOPSEC_OBJECTS = [
    _obj("topsecEnterpriseRoot", "1.3.6.1.4.1.14331", "", "天融信企业 OID 根", "OBJECT IDENTIFIER", 1),
    _obj("sysProductType", "1.3.6.1.4.1.14331.5.5.1.3.2", "", "设备产品型号", "OCTET STRING", 3),
    _obj("sysProductSN", "1.3.6.1.4.1.14331.5.5.1.3.1", "", "设备序列号", "OCTET STRING", 3),
    _obj("sysSoftwareVersion", "1.3.6.1.4.1.14331.5.5.1.3.3", "", "设备软件版本", "OCTET STRING", 3),
    _obj("sysMaxSession", "1.3.6.1.4.1.14331.5.5.1.3.15", "session", "设备支持的最大会话数", "Integer32", 4),
    _obj("cpuLoad", "1.3.6.1.4.1.14331.5.5.1.4.5", "cpu", "CPU 当前负载（百分比×100）", "Integer32", 12),
    _obj("memoryLoad", "1.3.6.1.4.1.14331.5.5.1.4.6", "memory", "内存当前使用率（百分比×100）", "Integer32", 12),
    _obj("memoryFree", "1.3.6.1.4.1.14331.5.5.1.4.7", "memory", "当前空闲内存（字节）", "Counter64", 8),
    _obj("memoryTotal", "1.3.6.1.4.1.14331.5.5.1.4.8", "memory", "设备总内存（字节）", "Counter64", 5),
    _obj("currentConnections", "1.3.6.1.4.1.14331.5.5.1.4.9", "session", "当前并发连接/会话数", "Counter64", 10),
    _obj("cursessionrate", "1.3.6.1.4.1.14331.5.5.1.4.10", "session", "每秒新建会话数", "Counter64", 7),
    _obj("cputemperature", "1.3.6.1.4.1.14331.5.5.1.4.11", "temperature", "CPU 温度（单位 0.1℃）", "DisplayString", 11),
    _obj("diskLoad", "1.3.6.1.4.1.14331.5.5.1.4.13", "storage", "磁盘使用率（百分比×100）", "Integer32", 8),
    _obj("fanSpeed", "1.3.6.1.4.1.14331.5.5.1.13.2.1.3", "fan", "风扇转速", "Integer32", 9),
    _obj("fanState", "1.3.6.1.4.1.14331.5.5.1.13.2.1.4", "fan", "风扇状态", "Integer32", 5),
    _obj("powerState", "1.3.6.1.4.1.14331.5.5.1.14.1.1.2", "power", "电源状态", "Integer32", 9),
    _obj("voltageState", "1.3.6.1.4.1.14331.5.5.1.15.2.1.4", "power", "电压状态", "Integer32", 4),
]

SANGFOR_OBJECTS = [
    _obj("sangforEnterpriseRoot", "1.3.6.1.4.1.35047", "", "深信服企业 OID 根", "OBJECT IDENTIFIER", 1),
    _obj("sfDeviceDescr", "1.3.6.1.4.1.35047.1.1", "", "深信服设备描述", "DisplayString", 3),
    _obj("sfSysCpuCostRate", "1.3.6.1.4.1.35047.1.3", "cpu", "CPU 当前使用率（%）", "Integer32", 8),
    _obj("sfCpuAllCostRate", "1.3.6.1.4.1.35047.1.19.3", "cpu", "CPU 总使用率（%）", "Integer32", 12),
    _obj("sfCpuLoadLast1Min", "1.3.6.1.4.1.35047.1.16.1.3", "cpu", "CPU 最近 1 分钟负载（%）", "Integer32", 10),
    _obj("sfCpuLoadLast5Min", "1.3.6.1.4.1.35047.1.16.1.4", "cpu", "CPU 最近 5 分钟负载（%）", "Integer32", 8),
    _obj("sfIntSysFreeMemory", "1.3.6.1.4.1.35047.1.13.3", "memory", "空闲内存", "Integer32", 9),
    _obj("sfIntSysTotalMemory", "1.3.6.1.4.1.35047.1.13.4", "memory", "总内存", "Integer32", 7),
    _obj("sfSysMemoryUsage", "1.3.6.1.4.1.35047.1.13.5", "memory", "内存使用百分比", "DisplayString", 12),
    _obj("sfDiskUsedPercent", "1.3.6.1.4.1.35047.1.5.1.6", "storage", "磁盘使用百分比", "DisplayString", 9),
    _obj("sfIntDiskSize", "1.3.6.1.4.1.35047.1.5.1.7", "storage", "磁盘容量（MB）", "Integer32", 6),
    _obj("sfIntDiskUsed", "1.3.6.1.4.1.35047.1.5.1.8", "storage", "磁盘已用（MB）", "Integer32", 6),
    _obj("sfCpuTemp", "1.3.6.1.4.1.35047.1.16.1.6", "temperature", "CPU 温度（℃）", "DisplayString", 9),
    _obj("sfIntCpuTemp", "1.3.6.1.4.1.35047.1.16.1.7", "temperature", "CPU 温度（℃）", "Integer32", 12),
    _obj("sfTempSensorReading", "1.3.6.1.4.1.35047.1.59.1.3", "temperature", "温度传感器读数（℃）", "Integer32", 10),
    _obj("sfTempMotherBoard", "1.3.6.1.4.1.35047.1.59.1.4", "temperature", "主板温度（℃）", "Integer32", 9),
    _obj("sfFanSpeed", "1.3.6.1.4.1.35047.1.14.1.3", "fan", "风扇转速（RPM）", "Integer32", 10),
    _obj("sfFanState", "1.3.6.1.4.1.35047.1.14.1.4", "fan", "风扇状态", "Integer32", 6),
    _obj("sfPowerState", "1.3.6.1.4.1.35047.1.15.1.3", "power", "电源状态", "Integer32", 10),
    _obj("sfCurSession", "1.3.6.1.4.1.35047.1.27.3", "session", "当前并发会话数", "Integer32", 10),
    _obj("sfTotalSessions", "1.3.6.1.4.1.35047.1.27.2", "session", "总会话数", "Integer32", 7),
    _obj("sfNewSessionPerSec", "1.3.6.1.4.1.35047.1.27.4", "session", "每秒新建会话数", "Integer32", 7),
    _obj("sfUsers", "1.3.6.1.4.1.35047.1.23", "session", "系统用户数", "Counter32", 4),
]

DPTECH_OBJECTS = [
    _obj("dptechEnterpriseRoot", "1.3.6.1.4.1.31648", "", "迪普企业 OID 根", "OBJECT IDENTIFIER", 1),
    _obj("dpCpuRatio", "1.3.6.1.4.1.31648.3.15.3", "cpu", "CPU 30 秒平均使用率（%）", "Integer32", 12),
    _obj("dpCpu1MinRatio", "1.3.6.1.4.1.31648.3.15.23", "cpu", "CPU 1 分钟平均使用率（%）", "Integer32", 9),
    _obj("dpCpu5MinsRatio", "1.3.6.1.4.1.31648.3.15.25", "cpu", "CPU 5 分钟平均使用率（%）", "Integer32", 7),
    _obj("dpMemRatio", "1.3.6.1.4.1.31648.3.15.5", "memory", "内存使用率（%）", "Integer32", 12),
    _obj("dpMem1MinRatio", "1.3.6.1.4.1.31648.3.15.27", "memory", "内存 1 分钟平均使用率（%）", "Integer32", 9),
    _obj("dpMemSize", "1.3.6.1.4.1.31648.3.10", "memory", "内存容量（MB）", "Integer32", 5),
    _obj("dpDiskSize", "1.3.6.1.4.1.31648.3.12", "storage", "磁盘容量（GB）", "Integer32", 6),
    _obj("dpCpuTemperature", "1.3.6.1.4.1.31648.3.15.4", "temperature", "CPU 温度（℃）", "Integer32", 12),
    _obj("dpMainboardTemperature", "1.3.6.1.4.1.31648.3.15.8", "temperature", "主板温度（℃）", "Integer32", 10),
    _obj("dpBoardTemperature", "1.3.6.1.4.1.31648.3.19.1.1", "temperature", "板卡温度（℃）", "INTEGER", 8),
    _obj("dpFanStatus", "1.3.6.1.4.1.31648.3.15.12.1.3", "fan", "风扇状态（0正常/1故障/2缺失）", "INTEGER", 10),
    _obj("dpPowerStatus", "1.3.6.1.4.1.31648.3.15.11.1.3", "power", "电源状态（0正常/1故障/2缺失）", "INTEGER", 11),
    _obj("dpSession", "1.3.6.1.4.1.31648.3.15.9", "session", "当前会话数", "Gauge32", 10),
    _obj("dpNewSessionSpeed", "1.3.6.1.4.1.31648.3.15.14", "session", "每秒新建会话数", "Gauge32", 7),
    _obj("dpUserOnline", "1.3.6.1.4.1.31648.3.15.15", "session", "在线用户数", "Gauge32", 5),
]

VENUSTECH_OBJECTS = [
    _obj("venustechEnterpriseRoot", "1.3.6.1.4.1.15227", "", "启明星辰企业 OID 根", "OBJECT IDENTIFIER", 1),
    _obj("siType", "1.3.6.1.4.1.15227.200.1.1.0", "", "设备型号", "OCTET STRING", 3),
    _obj("siName", "1.3.6.1.4.1.15227.200.1.2.0", "", "设备名称", "OCTET STRING", 3),
    _obj("siSerial", "1.3.6.1.4.1.15227.200.1.3.0", "", "设备序列号", "OCTET STRING", 3),
    _obj("siHWVersion", "1.3.6.1.4.1.15227.200.1.4.0", "", "硬件版本", "OCTET STRING", 2),
    _obj("siSWVersion", "1.3.6.1.4.1.15227.200.1.5.0", "", "软件版本", "OCTET STRING", 2),
    _obj("srCPUPercent", "1.3.6.1.4.1.15227.200.2.1.1.4", "cpu", "全 CPU 使用率（%）", "INTEGER", 12),
    _obj("srCPUUser", "1.3.6.1.4.1.15227.200.2.1.1.2", "cpu", "用户 CPU 占用率（%）", "INTEGER", 8),
    _obj("srCPUSystem", "1.3.6.1.4.1.15227.200.2.1.1.3", "cpu", "系统 CPU 占用率（%）", "INTEGER", 8),
    _obj("srMemTotalReal", "1.3.6.1.4.1.15227.200.2.2.1.0", "memory", "物理内存总量（kB）", "INTEGER", 6),
    _obj("srMemTotalFree", "1.3.6.1.4.1.15227.200.2.2.2.0", "memory", "空闲内存（kB）", "INTEGER", 8),
    _obj("srMemPercent", "1.3.6.1.4.1.15227.200.2.2.3.0", "memory", "内存使用率（%）", "INTEGER", 12),
    _obj("srDiskTotal", "1.3.6.1.4.1.15227.200.2.3.1.2.1", "storage", "磁盘总容量（kB）", "INTEGER", 6),
    _obj("srDiskUsed", "1.3.6.1.4.1.15227.200.2.3.1.3.1", "storage", "磁盘可用容量（kB）", "INTEGER", 6),
    _obj("srDiskPercent", "1.3.6.1.4.1.15227.200.2.3.1.4.1", "storage", "磁盘使用率（%）", "INTEGER", 10),
    _obj("GAPHASTATUS", "1.3.6.1.4.1.15227.1.61.1.1.0", "", "双机热备状态", "OCTET STRING", 5),
    _obj("GAPHAROLE", "1.3.6.1.4.1.15227.1.61.1.2.0", "", "双机热备角色", "OCTET STRING", 5),
]

SECURITY_LIBRARIES: List[Dict[str, Any]] = [
    {
        "key": "security-topsec", "vendor": "天融信", "category": "security",
        "name": "天融信 NGFW 安全设备常用 MIB", "module": "TOPSEC-SECURITY-COMMON",
        "description": "天融信 NGFW/NGVONE：CPU、内存、温度、风扇、电源、会话及设备信息",
        "objects": COMMON_OBJECTS + TOPSEC_OBJECTS,
    },
    {
        "key": "security-sangfor", "vendor": "深信服", "category": "security",
        "name": "深信服 AF/安全设备常用 MIB", "module": "SANGFOR-SECURITY-COMMON",
        "description": "深信服 AF：CPU、内存、磁盘、温度、风扇、电源和会话",
        "objects": COMMON_OBJECTS + SANGFOR_OBJECTS,
    },
    {
        "key": "security-dptech", "vendor": "迪普", "category": "security",
        "name": "迪普 DPtech 安全设备常用 MIB", "module": "DPTECH-SECURITY-COMMON",
        "description": "迪普 DPtech：CPU、内存、磁盘、CPU/主板温度、风扇、电源、会话",
        "objects": COMMON_OBJECTS + DPTECH_OBJECTS,
    },
    {
        "key": "security-venustech", "vendor": "启明星辰", "category": "security",
        "name": "启明星辰天清安全设备常用 MIB", "module": "VENUSTECH-SECURITY-COMMON",
        "description": "启明星辰天清：CPU、内存、磁盘、会话及双机状态",
        "objects": COMMON_OBJECTS + VENUSTECH_OBJECTS,
    },
]
