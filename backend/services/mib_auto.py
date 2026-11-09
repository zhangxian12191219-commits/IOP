"""MIB 自动识别、取值验证、指标归类与学习档案。

流程：
1. 读取设备 sysDescr / sysObjectID，结合资产厂商型号形成指纹；
2. 在已导入 MIB 中按厂商、型号、设备类别和历史成功率排序候选；
3. 对候选 MIB 的推荐 OID 做真实 SNMP 取值和范围校验；
4. 仅绑定通过校验的 OID，并写入设备 custom_oids/custom_metrics；
5. 保存匹配档案，后续同类设备自动提高该 MIB 的优先级。

只读探测阶段不会修改设备；绑定阶段仅修改平台内设备的 MIB 引用和指标映射。
"""
from __future__ import annotations

import asyncio
import hashlib
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..models.mib import MibFile, MibObject
from ..models.mib_auto import MibMatchProfile
from ..models.models import Device, DeviceMetric
from ..config import Config
from ..snmp.snmp_client import SNMPClient
from . import mib_parser

CORE_METRIC_KEYS = {"cpu", "memory", "temperature", "power"}
CATEGORY_UNITS = {
    "cpu": "%", "memory": "%", "storage": "%", "temperature": "°C",
    "power": "", "optical": "dBm", "fan": "RPM", "session": "个", "interface": "",
}
VENDOR_ALIASES = {
    "cisco": "Cisco", "华为": "Huawei", "huawei": "Huawei", "h3c": "H3C",
    "华三": "H3C", "锐捷": "Ruijie", "ruijie": "Ruijie", "juniper": "Juniper",
    "fortinet": "Fortinet", "飞塔": "Fortinet", "dell": "Dell", "戴尔": "Dell",
    "futurematrix": "FutureMatrix", "future matrix": "FutureMatrix",
    "hpe": "HPE", "hp": "HPE", "联想": "Lenovo", "lenovo": "Lenovo",
    "浪潮": "Inspur", "inspur": "Inspur", "中兴": "ZTE", "zte": "ZTE",
    "烽火": "FiberHome", "fiberhome": "FiberHome", "深信服": "Sangfor",
    "sangfor": "Sangfor", "天融信": "Topsec", "topsec": "Topsec",
    "迪普": "DPtech", "dptech": "DPtech", "启明星辰": "Venustech",
    "venustech": "Venustech", "绿盟": "NSFOCUS", "nsfocus": "NSFOCUS",
    "奇安信": "QiAnXin", "qianxin": "QiAnXin", "安恒": "DBAPPSecurity",
    "dbappsecurity": "DBAPPSecurity",
    "山石": "Hillstone", "hillstone": "Hillstone", "aruba": "Aruba",
    "神州数码": "DigitalChina", "digitalchina": "DigitalChina",
    "爱数": "AISHU", "aishu": "AISHU", "anybackup": "AISHU",
    "鼎甲": "Dingjia", "dingjia": "Dingjia", "dbackup": "Dingjia",
    "宏杉": "MacroSAN", "macrosan": "MacroSAN",
    "腾凌": "Tengling", "tengling": "Tengling",
}
CATEGORY_WORDS = {
    "cpu": ("cpu", "处理器", "processor", "load"),
    "memory": ("memory", "内存", "mem", "ram"),
    "storage": ("storage", "disk", "存储", "磁盘", "卷"),
    "temperature": ("temperature", "温度", "temp", "thermal"),
    "power": ("power", "电源", "psu", "供电"),
    "optical": ("optical", "光功率", "dbm", "光模块"),
    "fan": ("fan", "风扇", "转速"),
    "session": ("session", "会话", "连接数"),
    "interface": ("interface", "接口", "端口", "port"),
}


def _norm(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip()).lower()


def _canonical_vendor(value: Any) -> str:
    """把中英文厂商别名归一，供 MIB 库候选评分使用。"""
    text = _norm(value)
    if not text:
        return ""
    for key, canonical in VENDOR_ALIASES.items():
        if key in text:
            return _norm(canonical)
    return text


def _fingerprint(vendor: str, model: str, sys_object_id: str, sys_descr: str) -> str:
    raw = "|".join((_norm(vendor), _norm(model), _norm(sys_object_id), _norm(sys_descr)[:180]))
    return hashlib.sha1(raw.encode("utf-8", errors="replace")).hexdigest()


def _infer_vendor(text: str) -> str:
    lowered = _norm(text)
    for key, value in VENDOR_ALIASES.items():
        if key in lowered:
            return value
    return ""


def _infer_model(text: str, vendor: str) -> str:
    if not text:
        return ""
    raw = str(text)
    # 常见 sysDescr 中的型号片段，不作为唯一依据；仅作为展示/候选排序辅助
    match = re.search(r"\b([A-Z]{1,6}[- ]?\d{2,6}[A-Z0-9-]*)\b", raw)
    if match:
        return match.group(1).strip()
    if vendor:
        match = re.search(rf"{re.escape(vendor)}[\s/_-]+([A-Za-z0-9][A-Za-z0-9._-]{{2,40}})", raw, re.I)
        if match:
            return match.group(1).strip()
    return ""


def _candidate_score(device: Device, mib: MibFile, learned: bool) -> int:
    vendor = _canonical_vendor(device.vendor)
    model = _norm(device.model)
    mib_vendor = _canonical_vendor(mib.vendor)
    mib_model = _norm(mib.device_model)
    score = 0
    if vendor and mib_vendor:
        if vendor == mib_vendor or vendor in mib_vendor or mib_vendor in vendor:
            score += 40
        else:
            score -= 25
    if model and mib_model:
        if model == mib_model or model in mib_model or mib_model in model:
            score += 32
        else:
            score -= 8
    if device.device_type and mib.device_category:
        if _norm(device.device_type) == _norm(mib.device_category):
            score += 8
        elif mib.device_category not in ("", "custom"):
            score -= 2
    if mib.is_builtin:
        score += 2
    if learned:
        score += 90
    return score


def _profile_for(db: Session, fingerprint: str, vendor: str, model: str) -> Optional[MibMatchProfile]:
    profile = db.query(MibMatchProfile).filter(MibMatchProfile.fingerprint == fingerprint).first()
    if profile:
        return profile
    vendor_key, model_key = _norm(vendor), _norm(model)
    if not vendor_key:
        return None
    candidates = db.query(MibMatchProfile).filter(MibMatchProfile.vendor == vendor or MibMatchProfile.vendor.ilike(f"%{vendor}%")).limit(20).all()
    for item in candidates:
        if model_key and _norm(item.model) and (model_key in _norm(item.model) or _norm(item.model) in model_key):
            return item
    return candidates[0] if candidates and not model_key else None


def _candidate_objects(db: Session, mib_id: int) -> List[Dict[str, Any]]:
    rows = db.query(MibObject).filter(MibObject.mib_id == mib_id).all()
    return [{
        "id": row.id, "mib_id": row.mib_id, "name": row.name, "oid": row.oid,
        "syntax": row.syntax, "access": row.access, "status": row.status,
        "description": row.description, "category": row.category,
        "score": row.score or 0,
    } for row in rows]


def _select_oids(objects: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    recommended = mib_parser.recommend(objects, per_category=2)
    selected = []
    seen = set()
    for category, items in recommended.items():
        for obj in items:
            oid = str(obj.get("oid") or "").strip()
            if not oid or oid in seen:
                continue
            if (obj.get("access") or "").lower() in ("not-accessible", "accessible-for-notify"):
                continue
            seen.add(oid)
            selected.append({**obj, "category": category})
    return selected


def _numeric(value: Any) -> Optional[float]:
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def validate_value(category: str, raw: Any) -> Tuple[bool, str]:
    """对真实 SNMP 返回值做类别范围校验。"""
    if raw is None:
        return False, "未取到值"
    text = str(raw).strip()
    if not text:
        return False, "值为空"
    lowered = text.lower()
    if lowered.startswith(("no such", "no access", "nosuch", "timeout")):
        return False, f"SNMP 返回 {text}"
    if category == "interface":
        return True, "可读取"
    if category == "power":
        if any(word in lowered for word in ("normal", "abnormal", "fail", "fault", "on", "off", "up", "down", "ok")):
            return True, "状态值可识别"
        number = _numeric(text)
        if number is not None and 0 <= number <= 10:
            return True, "状态值在 0~10"
        return False, "电源值不在可识别范围"
    number = _numeric(text)
    if number is None:
        return False, "不是数值"
    ranges = {
        "cpu": (0, 100), "memory": (0, 100), "storage": (0, 100),
        "temperature": (-40, 250), "optical": (-80, 25),
        "fan": (0, 100000),
    }
    low, high = ranges.get(category, (-1e12, 1e12))
    if low <= number <= high:
        return True, f"数值 {number:g} 在 {low:g}~{high:g}"
    return False, f"数值 {number:g} 超出 {low:g}~{high:g}"


async def _probe(client: SNMPClient, oid: str) -> Tuple[Any, str]:
    """GET 优先；兼容标量实例 .0 与表列 walk。"""
    raw = await client.get(oid)
    used = oid
    if raw is None and not oid.endswith(".0"):
        raw = await client.get(oid + ".0")
        used = oid + ".0"
    if raw is None:
        rows = await client.walk(oid, max_rows=1)
        if rows:
            used, raw = rows[0]
    return raw, used


async def analyze_device(db: Session, device: Device) -> Dict[str, Any]:
    vendor = (device.vendor or "").strip()
    model = (device.model or "").strip()
    sys_descr = ""
    sys_object_id = ""
    sys_name = ""
    reachable = False
    test_error = ""
    client = None
    try:
        client = SNMPClient.from_device(
            device,
            timeout=max(2, int(Config.SNMP_TIMEOUT or 3)),
            retries=max(1, int(Config.SNMP_RETRIES or 1)),
        )
        info = await client.get_system_info()
        sys_descr = str(info.get("sysdescr") or "")
        sys_name = str(info.get("sysname") or "")
        sys_object_id = str(await client.get("1.3.6.1.2.1.1.2.0") or "")
        test_error = str(info.get("error") or "")[:300]
        reachable = bool(sys_descr or sys_name or sys_object_id)
        if not reachable and not test_error:
            test_error = "SNMP 未返回 sysDescr/sysName/sysObjectID，请检查 Community、ACL、端口和 SNMP 版本"
        if not vendor:
            vendor = _infer_vendor(sys_descr)
        if not model:
            model = _infer_model(sys_descr, vendor)
    except Exception as exc:  # noqa: BLE001
        test_error = str(exc)[:300]
    finally:
        pass

    fingerprint = _fingerprint(vendor, model, sys_object_id, sys_descr)
    latest_metric = (
        db.query(DeviceMetric)
        .filter(DeviceMetric.device_id == device.id)
        .order_by(DeviceMetric.collected_at.desc())
        .first()
    )
    cached_values = {
        "cpu": getattr(latest_metric, "cpu_usage", None),
        "memory": getattr(latest_metric, "memory_usage", None),
        "storage": getattr(latest_metric, "disk_usage", None),
        "temperature": getattr(latest_metric, "temperature", None),
        "power": 1 if getattr(latest_metric, "power_status", None) == "failure" else (0 if latest_metric else None),
    }
    profile = _profile_for(db, fingerprint, vendor, model)
    mibs = db.query(MibFile).all()
    ranked = []
    for mib in mibs:
        learned = bool(profile and profile.mib_id == mib.id)
        score = _candidate_score(device, mib, learned)
        if score < 0:
            continue
        ranked.append((score, learned, mib))
    ranked.sort(key=lambda item: (item[0], item[2].object_count or 0), reverse=True)

    candidates: List[Dict[str, Any]] = []
    for score, learned, mib in ranked[:3]:
        objects = _candidate_objects(db, mib.id)
        selected = _select_oids(objects)

        async def probe_one(obj):
            raw, used = await _probe(client, obj["oid"]) if client else (None, obj["oid"])
            valid, reason = validate_value(obj["category"] or "", raw)
            return {
                "name": obj["name"], "oid": obj["oid"], "instance_oid": used,
                "category": obj["category"], "syntax": obj.get("syntax") or "",
                "value": None if raw is None else str(raw)[:300],
                "valid": valid, "reason": reason,
                "confidence": min(99, max(1, int(obj.get("score") or 0))),
            }

        if not reachable:
            # 设备不可达时不做无意义的逐 OID 超时探测；仅展示最近采集值供人工判断。
            metrics = []
            for obj in selected:
                cached = cached_values.get(obj.get("category") or "")
                metrics.append({
                    "name": obj["name"], "oid": obj["oid"], "instance_oid": obj["oid"],
                    "category": obj["category"], "syntax": obj.get("syntax") or "",
                    "value": None if cached is None else str(cached),
                    "cached_value": None if cached is None else str(cached),
                    "valid": False,
                    "reason": (
                        "设备 SNMP 不可达，显示最近采集值；未做 OID 验证"
                        if cached is not None else "设备 SNMP 不可达，且没有最近采集值"
                    ),
                    "confidence": min(99, max(1, int(obj.get("score") or 0))),
                })
        else:
            metrics = list(await asyncio.gather(*[probe_one(obj) for obj in selected])) if selected else []
        valid = [item for item in metrics if item["valid"]]
        confidence = min(99, 25 + max(0, score) + len(valid) * 10)
        candidates.append({
            "mib_id": mib.id, "filename": mib.filename, "module_name": mib.module_name,
            "vendor": mib.vendor or "", "device_model": mib.device_model or "",
            "device_category": mib.device_category or "", "categories": mib.categories or [],
            "score": score, "confidence": confidence, "learned": learned,
            "valid_count": len(valid), "tested_count": len(metrics),
            "metrics": metrics,
            "recommendation": (
                "已通过真实 SNMP 取值验证，可绑定并归类"
                if valid else ("可读取但未通过范围校验，建议人工复核" if metrics else "没有可测试的推荐 OID")
            ),
        })
    return {
        "device": {
            "id": device.id, "name": device.name, "ip_address": device.ip_address,
            "vendor": vendor, "model": model, "device_type": device.device_type,
        },
        "fingerprint": fingerprint,
        "snmp": {
            "reachable": reachable, "sys_name": sys_name,
            "sys_descr": sys_descr[:500], "sys_object_id": sys_object_id,
            "error": test_error,
            "cached_metrics_at": latest_metric.collected_at.isoformat() if latest_metric and latest_metric.collected_at else None,
        },
        "learned_profile": {
            "mib_id": profile.mib_id if profile else None,
            "success_count": profile.success_count if profile else 0,
        },
        "candidates": candidates,
        "best": candidates[0] if candidates else None,
        "message": (
            "未找到已导入 MIB，请先导入厂商 MIB 或内置库"
            if not candidates else
            ("未读取到 SNMP 指纹，候选仅按资产厂商/型号排序" if not reachable else "已完成 MIB 候选和 OID 取值验证")
        ),
    }


def _profile_upsert(db: Session, device: Device, mib: MibFile, metric_map: Dict[str, Any], fingerprint: str) -> MibMatchProfile:
    profile = db.query(MibMatchProfile).filter(MibMatchProfile.fingerprint == fingerprint).first()
    if not profile:
        profile = MibMatchProfile(fingerprint=fingerprint)
        db.add(profile)
    profile.vendor = device.vendor or ""
    profile.model = device.model or ""
    profile.sys_descr = (device.description or "")[:2000]
    profile.sys_object_id = ""
    profile.mib_id = mib.id
    profile.metric_map = metric_map
    profile.success_count = int(profile.success_count or 0) + 1
    profile.last_used_at = datetime.utcnow()
    return profile


def bind_device(db: Session, device: Device, mib_id: int, metrics: List[Dict[str, Any]], fingerprint: str = "") -> Dict[str, Any]:
    mib = db.query(MibFile).filter(MibFile.id == mib_id).first()
    if not mib:
        raise ValueError("MIB 不存在")
    object_rows = {
        row.oid: row for row in db.query(MibObject).filter(MibObject.mib_id == mib.id).all()
    }
    if not object_rows:
        raise ValueError("该 MIB 没有可解析的 OID 对象")
    clean_metrics = []
    custom_oids = dict(device.custom_oids or {})
    custom_metrics = list(device.custom_metrics or [])
    used_keys = {str(item.get("key") or "") for item in custom_metrics}
    metric_map: Dict[str, Any] = {}
    for item in metrics or []:
        if not isinstance(item, dict) or not item.get("valid"):
            continue
        oid = str(item.get("oid") or "").strip()
        obj = object_rows.get(oid)
        if not obj:
            continue
        category = str(item.get("category") or obj.category or "").strip()
        if category not in CATEGORY_UNITS:
            category = "interface"
        value_ok, value_reason = validate_value(category, item.get("value"))
        if not value_ok:
            continue
        mapping = {
            "category": category, "name": item.get("name") or obj.name,
            "oid": oid, "value": item.get("value"),
            "reason": item.get("reason") or value_reason,
        }
        metric_map[category] = mapping
        if category in CORE_METRIC_KEYS:
            custom_oids[category] = oid
        else:
            key = re.sub(r"[^a-z0-9_]", "_", f"mib_{category}")[:30]
            base = key
            suffix = 2
            while key in used_keys:
                key = f"{base[:27]}_{suffix}"
                suffix += 1
            used_keys.add(key)
            custom_metrics.append({
                "key": key, "name": item.get("name") or obj.name,
                "oid": oid, "unit": CATEGORY_UNITS.get(category, ""), "scale": 1,
            })
        clean_metrics.append(mapping)
    if not clean_metrics:
        raise ValueError("没有通过验证的指标可绑定")
    device.mib_id = mib.id
    device.custom_oids = custom_oids
    device.custom_metrics = custom_metrics[:20]
    if not fingerprint:
        fingerprint = _fingerprint(device.vendor or "", device.model or "", "", device.description or "")
    profile = _profile_upsert(db, device, mib, metric_map, fingerprint)
    db.flush()
    return {
        "message": f"已绑定 {mib.module_name or mib.filename}，归类 {len(clean_metrics)} 个通过验证的指标",
        "mib_id": mib.id, "mib_name": mib.module_name or mib.filename,
        "metrics": clean_metrics, "custom_oids": custom_oids,
        "custom_metrics": device.custom_metrics,
        "profile_id": profile.id, "success_count": profile.success_count,
        "fingerprint": fingerprint,
    }
