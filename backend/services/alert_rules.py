"""自定义告警规则：指标定义、条件判断和序列化。"""
import re
from typing import Any, Dict, Optional

from ..models.alert_rule import DeviceAlertRule

METRICS = {
    "cpu_usage": {"label": "CPU 使用率", "unit": "%", "numeric": True},
    "memory_usage": {"label": "内存使用率", "unit": "%", "numeric": True},
    "temperature": {"label": "最高部件温度", "unit": "°C", "numeric": True},
    "fan_speed": {"label": "风扇转速（最高）", "unit": "RPM", "numeric": True},
    "disk_usage": {"label": "磁盘使用率", "unit": "%", "numeric": True},
    "power": {"label": "电源故障", "unit": "", "numeric": True},
    "offline": {"label": "设备离线", "unit": "", "numeric": True},
    "uptime": {"label": "运行时间", "unit": "秒", "numeric": True},
    "custom": {"label": "自定义指标", "unit": "", "numeric": True, "requires_key": True},
}
LEVELS = {
    "info": {"label": "提示", "rank": 0, "color": "#38bdf8"},
    "warning": {"label": "警告", "rank": 1, "color": "#fbbf24"},
    "critical": {"label": "严重", "rank": 2, "color": "#fb7185"},
    "emergency": {"label": "紧急", "rank": 3, "color": "#ef4444"},
}
OPERATORS = {
    "gt": ">",
    "gte": "≥",
    "lt": "<",
    "lte": "≤",
    "eq": "=",
    "ne": "≠",
}


def level_label(rule: DeviceAlertRule) -> str:
    return (rule.level_label or "").strip() or LEVELS.get(rule.level, LEVELS["warning"])["label"]


def rule_metric_label(rule: DeviceAlertRule) -> str:
    meta = METRICS.get(rule.metric, METRICS["custom"])
    if rule.metric == "custom" and rule.custom_key:
        return f"{meta['label']}（{rule.custom_key}）"
    return meta["label"]


def rule_unit(rule: DeviceAlertRule) -> str:
    return METRICS.get(rule.metric, {}).get("unit", "")


def condition_text(rule: DeviceAlertRule) -> str:
    operator = OPERATORS.get(rule.operator, rule.operator)
    unit = rule_unit(rule)
    return f"{rule_metric_label(rule)} {operator} {rule.threshold:g}{unit}"


def _component_metric_value(metrics: Dict[str, Any], key: str) -> Optional[float]:
    """把仪表盘组件指标 key（如 srv_component_temp_0）解析为采集值。"""
    custom = metrics.get("custom") or {}
    components = custom.get("server_components") or metrics.get("components") or {}
    text = str(key or "")
    if text == "srv_power_watts":
        values = [float(item.get("watts")) for item in components.get("power_supplies") or [] if item.get("watts") is not None]
        return sum(values) if values else None
    if text == "srv_power_voltage":
        values = [float(item.get("voltage")) for item in components.get("power_supplies") or [] if item.get("voltage") is not None]
        return sum(values) / len(values) if values else None
    if text == "srv_disk_usage":
        return metrics.get("disk_usage")
    if text in ("srv_inlet_temp", "srv_exhaust_temp", "srv_cpu_temp"):
        pattern = {
            "srv_inlet_temp": r"inlet|进气|进风",
            "srv_exhaust_temp": r"exhaust|排气|排风",
            "srv_cpu_temp": r"cpu|处理器",
        }[text]
        for item in components.get("temperatures") or []:
            if re.search(pattern, str(item.get("name") or ""), re.I):
                try:
                    return float(item.get("value"))
                except (TypeError, ValueError):
                    return None
        return None
    match = re.match(r"srv_component_temp_(\d+)$", text)
    if match:
        items = components.get("temperatures") or []
        index = int(match.group(1))
        if index < len(items):
            try:
                return float(items[index].get("value"))
            except (TypeError, ValueError):
                return None
        return None
    match = re.match(r"srv_component_fan_(\d+)$", text)
    if match:
        items = components.get("fans") or []
        index = int(match.group(1))
        if index < len(items):
            try:
                return float(items[index].get("value"))
            except (TypeError, ValueError):
                return None
    match = re.match(r"srv_component_psu_(watts|voltage)_(\d+)$", text)
    if match:
        items = components.get("power_supplies") or []
        index = int(match.group(2))
        if index < len(items):
            try:
                return float(items[index].get(match.group(1)))
            except (TypeError, ValueError):
                return None
    match = re.match(r"srv_component_disk_(\d+)$", text)
    if match:
        items = components.get("disks") or []
        index = int(match.group(1))
        if index < len(items):
            try:
                return float(items[index].get("size_gb"))
            except (TypeError, ValueError):
                return None
    return None


def metric_value(rule: DeviceAlertRule, metrics: Dict[str, Any], offline: bool = False) -> Optional[float]:
    try:
        if rule.metric == "custom":
            values = metrics.get("custom") or {}
            if not isinstance(values, dict) or not rule.custom_key:
                return None
            value = values.get(rule.custom_key)
            if value is None:
                value = _component_metric_value(metrics, rule.custom_key)
        elif rule.metric == "fan_speed":
            values = metrics.get("custom") or {}
            direct = values.get("srv_fan_speed") if isinstance(values, dict) else None
            fans = ((values.get("server_components") or {}).get("fans") or []) if isinstance(values, dict) else []
            candidates = []
            if direct is not None:
                candidates.append(float(direct))
            for fan in fans:
                try:
                    candidates.append(float(fan.get("value")))
                except (TypeError, ValueError):
                    continue
            value = max(candidates) if candidates else None
        elif rule.metric == "power":
            value = 1 if metrics.get("power_status") == "failure" else 0
        elif rule.metric == "offline":
            value = 1 if offline else 0
        else:
            value = metrics.get(rule.metric)
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def condition_matches(value: float, operator: str, threshold: float) -> bool:
    if operator == "gt":
        return value > threshold
    if operator == "gte":
        return value >= threshold
    if operator == "lt":
        return value < threshold
    if operator == "lte":
        return value <= threshold
    if operator == "eq":
        return value == threshold
    if operator == "ne":
        return value != threshold
    return False


def rule_to_dict(rule: DeviceAlertRule) -> Dict[str, Any]:
    return {
        "id": rule.id,
        "device_id": rule.device_id,
        "name": rule.name,
        "metric": rule.metric,
        "metric_label": rule_metric_label(rule),
        "custom_key": rule.custom_key,
        "operator": rule.operator,
        "threshold": rule.threshold,
        "unit": rule_unit(rule),
        "condition": condition_text(rule),
        "level": rule.level,
        "level_label": level_label(rule),
        "notify_channel_ids": rule.notify_channel_ids or [],
        "enabled": bool(rule.enabled),
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
        "updated_at": rule.updated_at.isoformat() if rule.updated_at else None,
    }
