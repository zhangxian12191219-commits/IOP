"""按厂商/型号自动套用 MIB 模板

模板不硬编码 OID，而是给出「对象名关键字」：套用时在已导入的 MIB 中查找匹配对象并填入 OID，
避免不同型号 OID 不一致；找不到时提示需要先导入对应 MIB。
"""
from typing import Any, Dict, List, Optional

TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "cisco-ios",
        "name": "Cisco IOS / IOS-XE / NX-OS",
        "vendor_keys": ["cisco", "思科"],
        "model_keywords": ["catalyst", "nexus", "isr", "asr", "ios", "c9", "c3"],
        "device_types": ["router", "switch", "firewall"],
        "mib_modules": [
            "CISCO-SMI", "CISCO-PROCESS-MIB", "CISCO-MEMORY-POOL-MIB",
            "CISCO-ENTITY-SENSOR-MIB", "CISCO-ENVMON-MIB",
        ],
        "metric_hints": {
            "cpu": ["cpmCPUTotal5min", "cpmCPUTotal1min", "avgBusy", "cpuUsage"],
            "memory": ["ciscoMemoryPoolUsed", "ciscoMemoryPoolFree", "memPoolUsed"],
            "temperature": ["ciscoEnvMonTemperature", "entPhySensorValue", "tempValue"],
            "power": ["ciscoEnvMonSupplyState", "powerStatus"],
        },
        "custom_metric_hints": [
            {"key": "optical_rx", "name": "光模块收光功率", "unit": "dBm",
             "patterns": ["rxpower", "rxoptical", "opticalrx", "receivepower"]},
            {"key": "optical_tx", "name": "光模块发光功率", "unit": "dBm",
             "patterns": ["txpower", "txoptical", "opticaltx", "transmitpower"]},
            {"key": "fan_speed", "name": "风扇转速", "unit": "RPM",
             "patterns": ["fanspeed", "fanrpm", "fan_speed"]},
        ],
    },
    {
        "id": "huawei-ibmc",
        "name": "Huawei FusionServer iBMC（RH2288 等）",
        "vendor_keys": ["huawei", "华为"],
        "model_keywords": ["rh2288", "rh2288h", "rh2285", "1288h", "2288h", "ibmc", "fusionserver"],
        "device_types": ["server"],
        "mib_modules": ["HUAWEI-SERVER-IBMC-MIB", "HUAWEI-ENTITY-EXTENT-MIB"],
        "metric_hints": {
            "cpu": ["hwIbmcSystemCpuUsage", "hwEntityCpuUsage", "cpuUsage"],
            "memory": ["hwIbmcSystemMemUsage", "hwEntityMemUsage", "hwEntityMemSize"],
            "temperature": ["hwIbmcSensorReading", "hwEntityTemperature", "entPhySensorValue"],
            "power": ["hwIbmcPowerInputPower", "hwEntityPwrPower", "powerStatus"],
        },
        "custom_metric_hints": [
            {"key": "fan_speed", "name": "风扇转速", "unit": "RPM",
             "patterns": ["hwibmcfanspeed", "hwentityfanspeed", "fanspeed"]},
            {"key": "power_watts", "name": "电源功率", "unit": "W",
             "patterns": ["hwibmcpowerinputpower", "hwentitypwrpower"]},
            {"key": "disk_status", "name": "硬盘状态", "unit": "",
             "patterns": ["hwibmcdiskstatus", "diskstatus"]},
        ],
    },
    {
        "id": "huawei-vrp",
        "name": "Huawei VRP（S 系列交换机 / AR 路由器）",
        "vendor_keys": ["huawei", "华为"],
        "model_keywords": ["s57", "s67", "s77", "s127", "ar", "ce", "ne"],
        "device_types": ["router", "switch", "firewall"],
        "mib_modules": ["HUAWEI-MIB", "HUAWEI-ENTITY-EXTENT-MIB", "HUAWEI-ENTITY-SENSOR-MIB"],
        "metric_hints": {
            "cpu": ["hwEntityCpuUsage", "hwCpuDevTable", "cpuUsage"],
            "memory": ["hwEntityMemUsage", "hwEntityMemSize", "memUsage"],
            "temperature": ["hwEntityTemperature", "entPhySensorValue", "temperature"],
            "power": ["hwEntityPwrState", "hwPowerState", "powerStatus"],
        },
        "custom_metric_hints": [
            {"key": "optical_rx", "name": "光模块收光功率", "unit": "dBm",
             "patterns": ["rxpower", "rxoptical", "opticalrx", "receivepower"]},
            {"key": "optical_tx", "name": "光模块发光功率", "unit": "dBm",
             "patterns": ["txpower", "txoptical", "opticaltx", "transmitpower"]},
            {"key": "fan_speed", "name": "风扇转速", "unit": "%",
             "patterns": ["fanspeed", "fanrpm", "fan_speed"]},
            {"key": "power_watts", "name": "电源功率", "unit": "W",
             "patterns": ["hwentitypwrpower"], "aggregate": "max"},
            {"key": "power_voltage", "name": "电源电压", "unit": "V",
             "patterns": ["hwentitypwrvoltage"], "scale": 0.001, "aggregate": "max"},
        ],
    },
    {
        "id": "hillstone-stoneos",
        "name": "Hillstone StoneOS 防火墙",
        "vendor_keys": ["hillstone", "山石"],
        "model_keywords": ["sg-", "stoneos", "hillstone"],
        "device_types": ["firewall", "security", "switch"],
        "mib_modules": ["HILLSTONE-SYSTEM-MIB", "HILLSTONE-TEMPERATURE-MIB", "HILLSTONE-FIREWALL-COMMON"],
        "metric_hints": {
            "cpu": ["sysCPU"],
            "memory": ["sysTotalMemory", "sysCurMemory"],
            "temperature": ["hillstoneTemperatureValue"],
        },
        "custom_metric_hints": [],
    },
    {
        "id": "h3c-comware",
        "name": "H3C Comware",
        "vendor_keys": ["h3c", "新华三", "华三", "hp", "comware"],
        "model_keywords": ["s5130", "s5560", "s6520", "msr", "s125"],
        "device_types": ["router", "switch", "firewall"],
        "mib_modules": ["HH3C-SMI", "HH3C-ENTITY-EXT-MIB", "HH3C-ENTITY-SENSOR-MIB"],
        "metric_hints": {
            "cpu": ["hh3cEntityExtCpuUsage", "cpuUsage", "avgBusy"],
            "memory": ["hh3cEntityExtMemUsage", "memUsage"],
            "temperature": ["hh3cEntityExtTemperature", "entPhySensorValue"],
            "power": ["hh3cEntityExtPower", "powerStatus"],
        },
        "custom_metric_hints": [
            {"key": "optical_rx", "name": "光模块收光功率", "unit": "dBm",
             "patterns": ["rxpower", "opticalrx", "rxoptical"]},
            {"key": "fan_speed", "name": "风扇转速", "unit": "RPM",
             "patterns": ["fanspeed", "fanrpm", "entphysensorfan"]},
            {"key": "power_watts", "name": "当前功率", "unit": "W",
             "patterns": ["hh3centityextcurrentpower", "currentpower"],
             "scale": 0.001, "aggregate": "max"},
        ],
    },
    {
        "id": "ruijie-rgos",
        "name": "Ruijie RGOS",
        "vendor_keys": ["ruijie", "锐捷"],
        "model_keywords": ["rg-", "s57", "s29", "s62", "s65"],
        "device_types": ["router", "switch"],
        "mib_modules": ["RUIJIE-SMI", "RUIJIE-ENTITY-MIB"],
        "metric_hints": {
            "cpu": ["rgCpuUsage", "cpuUsage", "avgBusy"],
            "memory": ["rgMemUsage", "memUsage"],
            "temperature": ["rgTemperature", "entPhySensorValue"],
            "power": ["rgPowerStatus", "powerStatus"],
        },
        "custom_metric_hints": [
            {"key": "optical_rx", "name": "光模块收光功率", "unit": "dBm",
             "patterns": ["rxpower", "opticalrx"]},
            {"key": "fan_speed", "name": "风扇转速", "unit": "RPM",
             "patterns": ["fanspeed", "fanrpm"]},
        ],
    },
    {
        "id": "fortinet-fortios",
        "name": "Fortinet FortiOS",
        "vendor_keys": ["fortinet", "飞塔", "fortigate"],
        "model_keywords": ["fortigate", "fg-", "fgt"],
        "device_types": ["firewall", "security"],
        "mib_modules": ["FORTINET-MIB", "FORTINET-FORTIGATE-MIB"],
        "metric_hints": {
            "cpu": ["fgCpuUsage", "cpuUsage"],
            "memory": ["fgMemUsage", "memUsage"],
            "temperature": ["fgTemperature", "entPhySensorValue"],
            "power": ["fgPowerStatus", "powerStatus"],
        },
        "custom_metric_hints": [
            {"key": "optical_rx", "name": "光模块收光功率", "unit": "dBm",
             "patterns": ["rxpower", "opticalrx"]},
        ],
    },
    {
        "id": "sangfor",
        "name": "Sangfor 深信服",
        "vendor_keys": ["sangfor", "深信服"],
        "model_keywords": ["af", "ac", "ngaf", "aes"],
        "device_types": ["firewall", "security"],
        "mib_modules": ["SANGFOR-MIB", "SANGFOR-ENTITY-MIB"],
        "metric_hints": {
            "cpu": ["sfCpuUsage", "cpuUsage"],
            "memory": ["sfMemUsage", "memUsage"],
            "temperature": ["sfTemperature", "entPhySensorValue"],
            "power": ["sfPowerStatus", "powerStatus"],
        },
        "custom_metric_hints": [],
    },
    {
        "id": "topsec",
        "name": "Topsec 天融信",
        "vendor_keys": ["topsec", "天融信"],
        "model_keywords": ["ngfw", "tog", "top"],
        "device_types": ["firewall", "security"],
        "mib_modules": ["TOPSEC-MIB", "TOPSEC-SYSTEM-MIB"],
        "metric_hints": {
            "cpu": ["topCpuUsage", "cpuUsage"],
            "memory": ["topMemUsage", "memUsage"],
            "temperature": ["topTemperature", "entPhySensorValue"],
            "power": ["topPowerStatus", "powerStatus"],
        },
        "custom_metric_hints": [],
    },
    {
        "id": "juniper-junos",
        "name": "Juniper Junos",
        "vendor_keys": ["juniper", "瞻博", "junos"],
        "model_keywords": ["ex", "mx", "srx", "qfx", "acx"],
        "device_types": ["router", "switch", "firewall"],
        "mib_modules": ["JUNIPER-MIB", "JUNIPER-ENTITY-MIB"],
        "metric_hints": {
            "cpu": ["jnxOperatingCPU", "jnxBoxDescr", "cpuUsage"],
            "memory": ["jnxOperatingBuffer", "jnxOperatingMemory", "memUsage"],
            "temperature": ["jnxOperatingTemp", "entPhySensorValue"],
            "power": ["jnxOperatingState", "powerStatus"],
        },
        "custom_metric_hints": [
            {"key": "optical_rx", "name": "光模块收光功率", "unit": "dBm",
             "patterns": ["rxpower", "opticalrx"]},
        ],
    },
    {
        "id": "dell-idrac",
        "name": "Dell PowerEdge / iDRAC",
        "vendor_keys": ["dell", "戴尔", "emc"],
        "model_keywords": ["poweredge", "idrac", "r7", "r6", "r5"],
        "device_types": ["server"],
        "mib_modules": ["DELL-SERVER-COMMON", "MIB-DELL-10892"],
        "metric_hints": {
            "cpu": ["hrProcessorLoad"],
            "memory": ["hrMemorySize"],
            "temperature": ["entPhySensorValue"],
            "power": ["dellPowerSupplyOutputWatts", "entPhySensorValue"],
        },
        "custom_metric_hints": [
            {"key": "disk_total_gb", "name": "物理磁盘总容量", "unit": "GB",
             "patterns": ["dellphysicaldisksize"], "scale": 0.0009765625, "aggregate": "sum"},
            {"key": "fan_speed", "name": "风扇转速", "unit": "RPM",
             "patterns": ["dellfanspeed"], "aggregate": "max"},
            {"key": "power_watts", "name": "电源输出功率", "unit": "W",
             "patterns": ["dellpowersupplyoutputwatts"], "aggregate": "sum"},
            {"key": "power_voltage", "name": "电源输入电压", "unit": "V",
             "patterns": ["dellpowersupplyinputvoltage"], "aggregate": "max"},
        ],
    },
    {
        "id": "topsec-ngfw",
        "name": "天融信 NGFW / NGVONE 安全网关",
        "vendor_keys": ["topsec", "天融信"],
        "model_keywords": ["ngfw", "ngvone", "tog", "topsec", "昆仑"],
        "device_types": ["firewall", "security"],
        "mib_modules": ["TOPSEC-SECURITY-COMMON"],
        "metric_hints": {
            "cpu": ["cpuLoad"],
            "memory": ["memoryLoad", "memoryFree"],
            "temperature": ["cputemperature"],
            "power": ["powerState"],
        },
        "custom_metric_hints": [
            {"key": "fan_speed", "name": "风扇转速", "unit": "RPM",
             "patterns": ["fanspeed"], "aggregate": "max"},
            {"key": "session_count", "name": "当前会话数", "unit": "个",
             "patterns": ["currentconnections", "cursessiontotal"], "aggregate": "max"},
        ],
    },
    {
        "id": "sangfor-security",
        "name": "深信服 AF / 安全设备",
        "vendor_keys": ["sangfor", "深信服"],
        "model_keywords": ["af", "ngaf", "ac", "aes", "sangfor"],
        "device_types": ["firewall", "security"],
        "mib_modules": ["SANGFOR-SECURITY-COMMON"],
        "metric_hints": {
            "cpu": ["sfCpuAllCostRate", "sfSysCpuCostRate"],
            "memory": ["sfSysMemoryUsage", "sfIntSysFreeMemory"],
            "temperature": ["sfIntCpuTemp", "sfTempSensorReading"],
            "power": ["sfPowerState"],
        },
        "custom_metric_hints": [
            {"key": "fan_speed", "name": "风扇转速", "unit": "RPM",
             "patterns": ["sfFanSpeed"], "aggregate": "max"},
            {"key": "session_count", "name": "当前会话数", "unit": "个",
             "patterns": ["sfCurSession", "sfTotalSessions"], "aggregate": "max"},
            {"key": "disk_usage", "name": "磁盘使用率", "unit": "%",
             "patterns": ["sfSysDiskUsage", "sfDiskUsedPercent"]},
        ],
    },
    {
        "id": "dptech-security",
        "name": "迪普 DPtech 安全设备",
        "vendor_keys": ["dptech", "迪普"],
        "model_keywords": ["dptech", "dp-", "waf", "adx", "fw"],
        "device_types": ["firewall", "security"],
        "mib_modules": ["DPTECH-SECURITY-COMMON"],
        "metric_hints": {
            "cpu": ["dpCpuRatio"],
            "memory": ["dpMemRatio"],
            "temperature": ["dpCpuTemperature", "dpMainboardTemperature"],
            "power": ["dpPowerStatus"],
        },
        "custom_metric_hints": [
            {"key": "fan_speed", "name": "风扇状态", "unit": "",
             "patterns": ["dpFanStatus"], "aggregate": "max"},
            {"key": "session_count", "name": "当前会话数", "unit": "个",
             "patterns": ["dpSession"], "aggregate": "max"},
        ],
    },
    {
        "id": "venustech-security",
        "name": "启明星辰天清安全设备",
        "vendor_keys": ["venustech", "启明星辰"],
        "model_keywords": ["天清", "venustech", "netgap", "安全隔离"],
        "device_types": ["firewall", "security"],
        "mib_modules": ["VENUSTECH-SECURITY-COMMON"],
        "metric_hints": {
            "cpu": ["srCPUPercent"],
            "memory": ["srMemPercent"],
            "power": [],
        },
        "custom_metric_hints": [
            {"key": "disk_usage", "name": "磁盘使用率", "unit": "%",
             "patterns": ["srDiskPercent"]},
            {"key": "ha_status", "name": "双机热备状态", "unit": "",
             "patterns": ["GAPHASTATUS"]},
        ],
    },
    {
        "id": "generic-snmp",
        "name": "通用 SNMP 模板（HOST-RESOURCES / ENTITY-SENSORS）",
        "vendor_keys": [],
        "model_keywords": [],
        "device_types": ["router", "switch", "firewall", "security", "server"],
        "mib_modules": ["HOST-RESOURCES-MIB", "ENTITY-SENSORS-MIB", "ENTITY-MIB"],
        "metric_hints": {
            "cpu": ["hrProcessorLoad"],
            "memory": ["hrStorageUsed", "hrStorageSize"],
            "temperature": ["entPhySensorValue"],
            "power": ["entPhySensorValue"],
        },
        "custom_metric_hints": [
            {"key": "fan_speed", "name": "风扇转速", "unit": "RPM",
             "patterns": ["fanspeed", "fanrpm", "rpm"]},
        ],
    },
]


def list_templates() -> List[Dict[str, Any]]:
    return TEMPLATES


def match_template(vendor: str, model: str = "", device_type: str = "") -> Optional[Dict[str, Any]]:
    """按厂商 + 型号 + 类型匹配最佳模板"""
    vendor_text = (vendor or "").lower()
    model_text = (model or "").lower()
    type_text = (device_type or "").lower()

    best = None
    best_score = 0
    for template in TEMPLATES:
        score = 0
        vendor_keys = template.get("vendor_keys") or []
        if vendor_keys:
            if not any(key.lower() in vendor_text for key in vendor_keys):
                continue
            score += 10
        elif template["id"] != "generic-snmp":
            continue
        for kw in template.get("model_keywords") or []:
            if kw.lower() in model_text:
                score += 5
                break
        if type_text and type_text in (template.get("device_types") or []):
            score += 2
        # 通用模板优先级最低
        if template["id"] == "generic-snmp":
            score -= 5
        if score > best_score:
            best_score = score
            best = template
    return best


def resolve_template(db, template: Dict[str, Any], mib_id: Optional[int] = None,
                     device=None) -> Dict[str, Any]:
    """在已导入 MIB 中按对象名关键字解析模板 OID"""
    from ..models.mib import MibFile, MibObject

    candidate_mib_ids: List[int] = []
    if mib_id:
        candidate_mib_ids = [int(mib_id)]
    elif device is not None and getattr(device, "mib_id", None):
        candidate_mib_ids = [int(device.mib_id)]

    # 优先使用设备/指定 MIB；否则在全部已导入 MIB 中查找
    query = db.query(MibObject)
    if candidate_mib_ids:
        query = query.filter(MibObject.mib_id.in_(candidate_mib_ids))
    objects = query.all()
    if not candidate_mib_ids and objects:
        # 未绑定 MIB 时只允许使用与模板厂商匹配的库，避免 H3C 设备误选到华为对象
        vendor_keys = [str(v).lower() for v in (template.get("vendor_keys") or [])]
        if vendor_keys:
            vendor_mib_ids = {
                mib.id for mib in db.query(MibFile).all()
                if any(key in (mib.vendor or "").lower() for key in vendor_keys)
            }
            if vendor_mib_ids:
                objects = [obj for obj in objects if obj.mib_id in vendor_mib_ids]

    def find_object(patterns: List[str]):
        lowered = [(obj, (obj.name or "").lower()) for obj in objects]
        for pattern in patterns:
            key = pattern.lower()
            for obj, name in lowered:
                if key in name and obj.oid and (obj.access or "").lower() not in (
                    "not-accessible", "accessible-for-notify",
                ):
                    return obj
        return None

    matched: Dict[str, Any] = {}
    missing_metrics: List[str] = []
    for metric, patterns in (template.get("metric_hints") or {}).items():
        obj = find_object(patterns)
        if obj:
            matched[metric] = {"name": obj.name, "oid": obj.oid, "mib_id": obj.mib_id}
        else:
            missing_metrics.append(metric)

    custom_metrics: List[Dict[str, Any]] = []
    missing_custom: List[str] = []
    for hint in template.get("custom_metric_hints") or []:
        obj = find_object(hint.get("patterns") or [])
        if obj:
            custom_metrics.append({
                "key": hint["key"],
                "name": hint.get("name") or hint["key"],
                "oid": obj.oid,
                "unit": hint.get("unit") or "",
                "scale": hint.get("scale") or 1,
                "aggregate": hint.get("aggregate") or "max",
                "source_object": obj.name,
                "mib_id": obj.mib_id,
            })
        else:
            missing_custom.append(hint["key"])

    # 优先绑定“实际匹配到 OID 所属”的 MIB 库。模板里的 MIB 模块名可能与内置库
    # 的聚合模块名不同（如 HUAWEI-SWITCH-COMMON / HUAWEI-SERVER-IBMC-COMMON），
    # 仅按模块名会漏绑，导致资产只填 OID 却没有 mib_id。
    matched_mib = None
    mib_files = db.query(MibFile).all()
    if mib_id:
        matched_mib = next((m for m in mib_files if m.id == int(mib_id)), None)
    if not matched_mib:
        counts: Dict[int, int] = {}
        for info in list(matched.values()) + list(custom_metrics):
            oid_mib_id = info.get("mib_id") if isinstance(info, dict) else None
            if oid_mib_id:
                counts[int(oid_mib_id)] = counts.get(int(oid_mib_id), 0) + 1
        if counts:
            primary_mib_id = max(counts, key=counts.get)
            matched_mib = next((m for m in mib_files if m.id == primary_mib_id), None)
    if not matched_mib:
        module_keys = [m.lower() for m in template.get("mib_modules") or []]
        for mib in mib_files:
            text = f"{(mib.module_name or '').lower()} {(mib.filename or '').lower()}"
            if any(key in text for key in module_keys):
                matched_mib = mib
                break

    imported_modules = {(m.module_name or "").lower() for m in mib_files}
    missing_mibs = [
        module for module in template.get("mib_modules") or []
        if module.lower() not in imported_modules
    ]

    return {
        "template_id": template["id"],
        "template_name": template["name"],
        "mib_id": matched_mib.id if matched_mib else mib_id,
        "mib_name": matched_mib.module_name if matched_mib else None,
        "matched_metrics": matched,
        "custom_metrics": custom_metrics,
        "missing_metrics": missing_metrics,
        "missing_custom_metrics": missing_custom,
        "missing_mibs": missing_mibs,
    }
