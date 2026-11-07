"""内置设备图标库与厂商自动匹配

- 启动时把内置 SVG 图标写入 UPLOAD_DIR/presets/，通过 /uploads/presets/<id>.svg 访问
- 设备 icon 字段只需保存这个短 URL（不会撑大数据库字段）
- 厂商匹配：按厂商关键字 → 厂商图标，未匹配则按设备类型 → 类型图标
"""
import logging
from pathlib import Path
from typing import Dict, List, Optional

from ..config import Config

logger = logging.getLogger(__name__)

PRESET_SUBDIR = "presets"

TYPE_COLORS: Dict[str, tuple] = {
    "router": ("#3b82f6", "#1d4ed8"),
    "switch": ("#22c55e", "#15803d"),
    "firewall": ("#ef4444", "#b91c1c"),
    "security": ("#f59e0b", "#b45309"),
    "server": ("#8b5cf6", "#6d28d9"),
    "wireless": ("#06b6d4", "#0e7490"),
    "loadbalancer": ("#14b8a6", "#0f766e"),
    "storage": ("#64748b", "#334155"),
    "printer": ("#a855f7", "#7e22ce"),
    "camera": ("#0ea5e9", "#0369a1"),
    "ups": ("#eab308", "#a16207"),
    "pc": ("#f97316", "#c2410c"),
}

TYPE_PRESETS = [
    ("router", "路由器", "router"),
    ("switch", "交换机", "switch"),
    ("firewall", "防火墙", "firewall"),
    ("security", "安全设备", "security"),
    ("server", "服务器", "server"),
    ("wireless", "无线 AP", "wireless"),
    ("loadbalancer", "负载均衡", "loadbalancer"),
    ("storage", "存储设备", "storage"),
    ("printer", "打印机", "printer"),
    ("camera", "摄像头", "camera"),
    ("ups", "UPS 电源", "ups"),
    ("pc", "办公终端", "pc"),
]

# (id, 显示名, 厂商关键字, 颜色, 徽标文字, 字号)
VENDOR_PRESETS = [
    ("vendor-cisco", "Cisco 思科", ("cisco", "思科"), ("#1ba0d7", "#0b6f9e"), "CISCO", 12),
    ("vendor-huawei", "Huawei 华为", ("huawei", "华为"), ("#cf0a2c", "#8c0018"), "HUAWEI", 11),
    ("vendor-h3c", "H3C 新华三", ("h3c", "新华三"), ("#d71920", "#8f0d13"), "H3C", 14),
    ("vendor-ruijie", "Ruijie 锐捷", ("ruijie", "锐捷"), ("#0b5cad", "#063f79"), "Ruijie", 11.5),
    ("vendor-fortinet", "Fortinet 飞塔", ("fortinet", "飞塔"), ("#ee3124", "#a5160c"), "Fortinet", 9.5),
    ("vendor-sangfor", "Sangfor 深信服", ("sangfor", "深信服"), ("#0058a3", "#003a6b"), "Sangfor", 10),
    ("vendor-topsec", "Topsec 天融信", ("topsec", "天融信"), ("#e60012", "#99000c"), "TopSec", 11),
    ("vendor-hikvision", "Hikvision 海康", ("hikvision", "海康"), ("#e60012", "#8f000b"), "HIK", 14),
    ("vendor-dahua", "Dahua 大华", ("dahua", "大华"), ("#0066b3", "#003f70"), "DAHUA", 12),
    ("vendor-tplink", "TP-Link 普联", ("tp-link", "tplink", "普联"), ("#06a9e0", "#046d92"), "TP-LINK", 9.5),
    ("vendor-juniper", "Juniper 瞻博", ("juniper", "瞻博"), ("#84b135", "#4d7013"), "Juniper", 10),
    ("vendor-arista", "Arista", ("arista",), ("#004b87", "#002d52"), "Arista", 12),
    ("vendor-mikrotik", "MikroTik", ("mikrotik", "routeros"), ("#e11d48", "#9f1239"), "MikroTik", 9.5),
    ("vendor-ubiquiti", "Ubiquiti 优倍快", ("ubiquiti", "ubnt", "优倍快"), ("#0559c9", "#04377c"), "UBNT", 13),
]


def _type_glyph(device_type: str) -> str:
    """返回 64x64 视口内的白色线条图标（内部 14~50 区域）"""
    if device_type == "router":
        return (
            '<circle cx="32" cy="31" r="9" fill="none" stroke="#fff" stroke-width="2.6"/>'
            '<path d="M32 13v6M32 43v6M14 31h6M44 31h6" stroke="#fff" stroke-width="2.6" stroke-linecap="round"/>'
            '<path d="M29 18l3-3 3 3M29 44l3 3 3-3M19 28l-3 3 3 3M45 28l3 3-3 3" '
            'fill="none" stroke="#fff" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/>'
        )
    if device_type == "switch":
        return (
            '<path d="M16 25h26M35 19l6 6-6 6" fill="none" stroke="#fff" stroke-width="2.6" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
            '<path d="M48 39H22M29 33l-6 6 6 6" fill="none" stroke="#fff" stroke-width="2.6" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
        )
    if device_type == "firewall":
        return (
            '<rect x="16" y="18" width="32" height="28" rx="3" fill="none" stroke="#fff" stroke-width="2.4"/>'
            '<path d="M16 27h32M16 36h32M26 18v9M38 18v9M26 36v10M38 36v10" '
            'stroke="#fff" stroke-width="2" opacity="0.9"/>'
        )
    if device_type == "security":
        return (
            '<path d="M32 14l14 5v10c0 9-6 16-14 20-8-4-14-11-14-20V19l14-5z" '
            'fill="none" stroke="#fff" stroke-width="2.4" stroke-linejoin="round"/>'
            '<path d="M25 31l5 5 9-10" fill="none" stroke="#fff" stroke-width="2.6" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
        )
    if device_type == "server":
        return (
            '<rect x="19" y="14" width="26" height="36" rx="3" fill="none" stroke="#fff" stroke-width="2.4"/>'
            '<path d="M19 24h26M19 34h26M19 44h26" stroke="#fff" stroke-width="2.2"/>'
            '<circle cx="24" cy="19" r="1.6" fill="#fff"/><circle cx="24" cy="29" r="1.6" fill="#fff"/>'
            '<circle cx="24" cy="39" r="1.6" fill="#fff"/>'
        )
    if device_type == "wireless":
        return (
            '<path d="M17 29a21 21 0 0 1 30 0M23 35a14 14 0 0 1 18 0M28.5 41a6.5 6.5 0 0 1 7 0" '
            'fill="none" stroke="#fff" stroke-width="2.6" stroke-linecap="round"/>'
            '<circle cx="32" cy="47" r="2.8" fill="#fff"/>'
        )
    if device_type == "loadbalancer":
        return (
            '<circle cx="20" cy="32" r="5" fill="none" stroke="#fff" stroke-width="2.4"/>'
            '<path d="M25 32h8M33 32l7-10M33 32l7 10M33 32h10" fill="none" stroke="#fff" '
            'stroke-width="2.2" stroke-linecap="round"/>'
            '<circle cx="48" cy="22" r="3.5" fill="none" stroke="#fff" stroke-width="2"/>'
            '<circle cx="48" cy="42" r="3.5" fill="none" stroke="#fff" stroke-width="2"/>'
            '<circle cx="49" cy="32" r="3.5" fill="none" stroke="#fff" stroke-width="2"/>'
        )
    if device_type == "storage":
        return (
            '<rect x="18" y="15" width="28" height="10" rx="3" fill="none" stroke="#fff" stroke-width="2.3"/>'
            '<rect x="18" y="27" width="28" height="10" rx="3" fill="none" stroke="#fff" stroke-width="2.3"/>'
            '<rect x="18" y="39" width="28" height="10" rx="3" fill="none" stroke="#fff" stroke-width="2.3"/>'
            '<circle cx="23" cy="20" r="1.5" fill="#fff"/><circle cx="23" cy="32" r="1.5" fill="#fff"/>'
            '<circle cx="23" cy="44" r="1.5" fill="#fff"/>'
        )
    if device_type == "printer":
        return (
            '<rect x="18" y="15" width="28" height="12" rx="2" fill="none" stroke="#fff" stroke-width="2.3"/>'
            '<rect x="13" y="27" width="38" height="15" rx="3" fill="none" stroke="#fff" stroke-width="2.3"/>'
            '<rect x="22" y="37" width="20" height="12" rx="2" fill="#fff" opacity="0.92"/>'
        )
    if device_type == "camera":
        return (
            '<rect x="13" y="21" width="26" height="20" rx="3" fill="none" stroke="#fff" stroke-width="2.4"/>'
            '<path d="M39 27l11-6v20l-11-6z" fill="none" stroke="#fff" stroke-width="2.4" stroke-linejoin="round"/>'
            '<circle cx="23" cy="31" r="4" fill="none" stroke="#fff" stroke-width="2.2"/>'
        )
    if device_type == "ups":
        return (
            '<rect x="15" y="21" width="28" height="20" rx="3" fill="none" stroke="#fff" stroke-width="2.4"/>'
            '<path d="M21 41v4M37 41v4" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/>'
            '<path d="M30 24l-4 8h6l-3 8" fill="none" stroke="#fff" stroke-width="2.2" '
            'stroke-linecap="round" stroke-linejoin="round"/>'
        )
    # pc
    return (
        '<rect x="14" y="16" width="36" height="24" rx="3" fill="none" stroke="#fff" stroke-width="2.4"/>'
        '<path d="M26 47h12M32 40v7" stroke="#fff" stroke-width="2.4" stroke-linecap="round"/>'
    )


def _type_svg(preset_id: str) -> str:
    color_from, color_to = TYPE_COLORS[preset_id]
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{color_from}"/>
      <stop offset="1" stop-color="{color_to}"/>
    </linearGradient>
  </defs>
  <rect x="2" y="2" width="60" height="60" rx="15" fill="url(#bg)"/>
  <rect x="3" y="3" width="58" height="58" rx="14" fill="none" stroke="rgba(255,255,255,0.30)" stroke-width="1.5"/>
  {_type_glyph(preset_id)}
</svg>
'''


def _vendor_svg(color_from: str, color_to: str, label: str, font_size: float) -> str:
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" width="64" height="64">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="{color_from}"/>
      <stop offset="1" stop-color="{color_to}"/>
    </linearGradient>
  </defs>
  <rect x="2" y="2" width="60" height="60" rx="15" fill="url(#bg)"/>
  <rect x="3" y="3" width="58" height="58" rx="14" fill="none" stroke="rgba(255,255,255,0.30)" stroke-width="1.5"/>
  <text x="32" y="32" text-anchor="middle" dominant-baseline="central"
        font-family="Arial, Helvetica, sans-serif" font-size="{font_size}" font-weight="700"
        fill="#ffffff" letter-spacing="0.3">{label}</text>
</svg>
'''


def preset_dir() -> Path:
    return Path(Config.UPLOAD_DIR) / PRESET_SUBDIR


def preset_url(preset_id: str) -> str:
    return f"/uploads/{PRESET_SUBDIR}/{preset_id}.svg"


def ensure_presets() -> int:
    """把内置图标写入磁盘（每次启动覆盖，便于升级图标）"""
    directory = preset_dir()
    try:
        directory.mkdir(parents=True, exist_ok=True)
        for preset_id, _name, _device_type in TYPE_PRESETS:
            (directory / f"{preset_id}.svg").write_text(_type_svg(preset_id), encoding="utf-8")
        for preset_id, _name, _keys, (c1, c2), label, size in VENDOR_PRESETS:
            (directory / f"{preset_id}.svg").write_text(
                _vendor_svg(c1, c2, label, size), encoding="utf-8"
            )
        logger.info("内置图标库已就绪: %s（%d 个）", directory, len(TYPE_PRESETS) + len(VENDOR_PRESETS))
        return len(TYPE_PRESETS) + len(VENDOR_PRESETS)
    except Exception as exc:  # noqa: BLE001
        logger.warning("写入内置图标失败: %s", exc)
        return 0


def list_presets() -> List[dict]:
    items = [
        {
            "id": preset_id,
            "name": name,
            "category": "type",
            "device_type": device_type,
            "vendor": None,
            "url": preset_url(preset_id),
        }
        for preset_id, name, device_type in TYPE_PRESETS
    ]
    items += [
        {
            "id": preset_id,
            "name": name,
            "category": "vendor",
            "device_type": None,
            "vendor": keys[0],
            "url": preset_url(preset_id),
        }
        for preset_id, name, keys, _colors, _label, _size in VENDOR_PRESETS
    ]
    return items


def vendor_rules() -> List[dict]:
    return [
        {
            "preset_id": preset_id,
            "preset_url": preset_url(preset_id),
            "name": name,
            "keys": list(keys),
        }
        for preset_id, name, keys, _colors, _label, _size in VENDOR_PRESETS
    ]


def match_preset(device) -> Optional[str]:
    """按厂商关键字优先匹配，其次按设备类型匹配"""
    vendor = (getattr(device, "vendor", None) or "").strip().lower()
    if vendor:
        for preset_id, _name, keys, _colors, _label, _size in VENDOR_PRESETS:
            for key in keys:
                if key in vendor:
                    return preset_url(preset_id)
    device_type = (getattr(device, "device_type", None) or "").strip()
    if device_type in TYPE_COLORS:
        return preset_url(device_type)
    return None


def is_valid_icon(icon: str) -> bool:
    """允许：内置图标 URL、已上传图标 URL、外部 http(s) 图标、或空"""
    if not icon:
        return True
    if icon.startswith("/uploads/") or icon.startswith("http://") or icon.startswith("https://"):
        return ".." not in icon and len(icon) <= 500
    return False
