"""厂商库默认数据与查询辅助。"""
from __future__ import annotations

from typing import Any, Dict, List

from sqlalchemy.orm import Session

from ..models.models import Device
from ..models.mib import MibFile
from ..models.vendor import Vendor

# 名称, 分类, 别名
DEFAULT_VENDORS = [
    ("Huawei", "network", ["华为"]),
    ("H3C", "network", ["华三", "新华三"]),
    ("Cisco", "network", ["思科"]),
    ("Ruijie", "network", ["锐捷"]),
    ("Fortinet", "security", ["飞塔"]),
    ("Hillstone", "security", ["山石"]),
    ("Sangfor", "security", ["深信服"]),
    ("Topsec", "security", ["天融信"]),
    ("NSFOCUS", "security", ["绿盟"]),
    ("QiAnXin", "security", ["奇安信"]),
    ("Juniper", "network", []),
    ("Arista", "network", []),
    ("TP-Link", "network", []),
    ("MikroTik", "network", []),
    ("Ubiquiti", "network", []),
    ("F5", "network", []),
    ("A10", "network", []),
    ("ZTE", "network", ["中兴"]),
    ("Maipu", "network", ["迈普"]),
    ("Hikvision", "camera", ["海康威视"]),
    ("Dahua", "camera", ["大华"]),
    ("Dell", "storage", ["戴尔"]),
    ("HP", "server", ["HPE", "惠普"]),
    ("Lenovo", "server", ["联想"]),
    ("Inspur", "server", ["浪潮"]),
    ("IBM", "server", []),
    ("VMware", "virtualization", []),
    ("Microsoft", "virtualization", []),
    ("Apple", "other", []),
    ("Samsung", "other", []),
    ("Netgear", "network", []),
    ("D-Link", "network", ["友讯"]),
    ("AISHU", "backup", ["爱数", "AnyBackup"]),
    ("Dingjia", "backup", ["鼎甲", "DBackup"]),
    ("MacroSAN", "storage", ["宏杉"]),
    ("Tengling", "storage", ["北京腾凌", "腾凌"]),
]

CATEGORY_LABELS = {
    "network": "网络设备",
    "server": "服务器",
    "storage": "存储",
    "backup": "备份一体机",
    "security": "安全设备",
    "camera": "视频监控",
    "virtualization": "虚拟化",
    "other": "其他",
}


def ensure_builtin_vendors(db: Session) -> int:
    """补齐内置厂商；不覆盖用户已修改的别名/分类/启停状态。"""
    existing = {str(row.name).lower() for row in db.query(Vendor.name).all()}
    created = 0
    for order, (name, category, aliases) in enumerate(DEFAULT_VENDORS):
        if name.lower() in existing:
            continue
        db.add(Vendor(
            name=name,
            aliases=aliases,
            category=category,
            is_builtin=True,
            is_enabled=True,
            sort_order=order,
        ))
        created += 1
    if created:
        db.commit()
    return created


def usage_counts(db: Session, name: str) -> Dict[str, int]:
    device_count = db.query(Device).filter(Device.vendor == name).count()
    mib_count = db.query(MibFile).filter(MibFile.vendor == name).count()
    return {"devices": device_count, "mibs": mib_count, "total": device_count + mib_count}


def vendor_to_dict(db: Session, vendor: Vendor) -> Dict[str, Any]:
    usage = usage_counts(db, vendor.name)
    return {
        "id": vendor.id,
        "name": vendor.name,
        "aliases": vendor.aliases or [],
        "category": vendor.category or "other",
        "category_label": CATEGORY_LABELS.get(vendor.category or "other", "其他"),
        "note": vendor.note or "",
        "is_builtin": bool(vendor.is_builtin),
        "is_enabled": bool(vendor.is_enabled),
        "sort_order": vendor.sort_order or 100,
        "usage": usage,
        "device_count": usage["devices"],
        "mib_count": usage["mibs"],
        "created_at": vendor.created_at.isoformat() if vendor.created_at else None,
        "updated_at": vendor.updated_at.isoformat() if vendor.updated_at else None,
    }
