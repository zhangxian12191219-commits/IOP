"""资产导入导出

支持 Excel(.xlsx) 与 CSV(.csv)：
- 导出：把设备（含机柜、U 位、功率）导出为表格
- 模板：带表头、示例行与填写说明
- 导入：逐行校验（必填、IP 格式、类型、机柜/U位/功率），
        支持 skip（跳过已存在）/ update（更新）/ fail（冲突报错）三种模式
"""
import csv
import io
import json
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from sqlalchemy.orm import Session

from ..models.models import Device
from ..models.room import Cabinet, Room
from ..models.user import Group
from ..services import license_manager
from ..services.placement import validate_placement

# (表头, 字段名, 列宽, 示例, 是否必填)
COLUMNS: List[Tuple[str, str, int, str, bool]] = [
    ("设备名称", "name", 22, "核心交换机-01", True),
    ("IP地址", "ip_address", 16, "10.20.0.2", True),
    ("设备类型", "device_type", 12, "交换机", True),
    ("资产群组", "group_name", 14, "网络运维组", False),
    ("SNMP版本", "snmp_version", 10, "v2c", False),
    ("Community", "community", 12, "public", False),
    ("SNMP端口", "port", 10, 161, False),
    ("v3用户名", "v3_username", 14, "", False),
    ("v3安全级别", "v3_security_level", 14, "authPriv", False),
    ("v3认证协议", "v3_auth_protocol", 12, "SHA", False),
    ("v3认证密码", "v3_auth_password", 14, "", False),
    ("v3加密协议", "v3_priv_protocol", 12, "AES", False),
    ("v3加密密码", "v3_priv_password", 14, "", False),
    ("厂商", "vendor", 12, "Huawei", False),
    ("型号", "model", 18, "S5735", False),
    ("序列号", "serial_number", 16, "", False),
    ("位置", "location", 16, "数据中心-A区", False),
    ("机房", "room", 14, "数据中心A区", False),
    ("机柜", "cabinet", 16, "A01-核心网络柜", False),
    ("起始U位", "u_position", 10, 20, False),
    ("占用U数", "u_height", 10, 2, False),
    ("额定功率(W)", "power_watts", 12, 800, False),
    ("是否监控", "is_enabled", 10, "是", False),
    ("标签", "tags", 14, "", False),
    ("描述", "description", 24, "", False),
]

HEADER_TO_KEY = {header: key for header, key, *_ in COLUMNS}

DEVICE_TYPE_ALIASES = {
    "路由器": "router", "router": "router",
    "交换机": "switch", "switch": "switch",
    "防火墙": "firewall", "firewall": "firewall",
    "安全设备": "security", "security": "security",
    "安全网关": "security",
    "无线ap": "wireless", "无线 ap": "wireless", "无线": "wireless",
    "wireless": "wireless", "ap": "wireless", "wifi": "wireless",
    "负载均衡": "loadbalancer", "负载均衡器": "loadbalancer",
    "loadbalancer": "loadbalancer", "load-balancer": "loadbalancer", "lb": "loadbalancer",
    "存储": "storage", "存储设备": "storage", "storage": "storage", "san": "storage",
    "摄像头": "camera", "摄像机": "camera", "camera": "camera", "ipc": "camera",
    "打印机": "printer", "printer": "printer",
    "ups": "ups", "ups电源": "ups", "ups 电源": "ups",
    "办公终端": "pc", "工作站": "pc", "pc": "pc", "workstation": "pc",
    "服务器": "server", "server": "server",
    "其他": "other", "其它": "other", "other": "other",
}

SNMP_VERSION_ALIASES = {
    "v1": "v1", "1": "v1",
    "v2c": "v2c", "v2": "v2c", "2c": "v2c", "2": "v2c",
    "v3": "v3", "3": "v3",
}

TRUTHY = {"是", "y", "yes", "true", "1", "开", "启用"}
FALSY = {"否", "n", "no", "false", "0", "关", "停用"}

HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
REQUIRED_FILL = PatternFill("solid", fgColor="C00000")
HEADER_FONT = Font(color="FFFFFF", bold=True)


def _header_row_style(ws, required_flags: List[bool]) -> None:
    for idx, (header, _key, width, _example, required) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=idx, value=header + (" *" if required else ""))
        cell.fill = REQUIRED_FILL if required else HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[get_column_letter(idx)].width = width


def build_template() -> bytes:
    """生成导入模板（含表头、示例行、填写说明）"""
    wb = Workbook()
    ws = wb.active
    ws.title = "设备导入"
    _header_row_style(ws, [c[4] for c in COLUMNS])
    for idx, (_header, _key, _w, example, _req) in enumerate(COLUMNS, start=1):
        ws.cell(row=2, column=idx, value=example)
    ws.freeze_panes = "A2"

    guide = wb.create_sheet("填写说明")
    lines = [
        ("智能运维服务平台 · 资产导入说明", ""),
        ("", ""),
        ("必填列", "带 * 的列：设备名称、IP地址、设备类型"),
        ("设备类型", "可填 路由器/交换机/防火墙/安全设备，或 router/switch/firewall/security"),
        ("SNMP版本", "v1 / v2c / v3，默认 v2c"),
        ("v3 相关", "仅 SNMP版本=v3 时需要：用户名、安全级别、认证/加密协议与密码"),
        ("是否监控", "是 / 否，默认 是"),
        ("机房/机柜", "填写已存在的机房名与机柜名；不填则设备不上架"),
        ("资产群组", "填写已存在的群组名称；普通用户只能看到所属群组的设备"),
        ("起始U位", "机柜最底部为 1；留空表示自动分配最低空闲 U 位"),
        ("占用U数", "如 1U 交换机填 1，2U 设备填 2，默认 1"),
        ("额定功率(W)", "设备额定功率，用于机柜功率校验，默认 0"),
        ("功率规则", "同一机柜内所有设备功率之和不得超过机柜额定功率，超限的行会导入失败"),
        ("U位规则", "设备 U 位不能越界，也不能与其他设备重叠"),
        ("导入模式", "跳过已存在(按IP) / 更新已存在 / 冲突报错"),
        ("", ""),
        ("提示", "建议先导出当前资产作为数据参考，再据此修改后导入。"),
    ]
    for r, (a, b) in enumerate(lines, start=1):
        guide.cell(row=r, column=1, value=a).font = Font(bold=(r == 1), size=12 if r == 1 else 10)
        guide.cell(row=r, column=2, value=b)
    guide.column_dimensions["A"].width = 16
    guide.column_dimensions["B"].width = 90

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _cell_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def _parse_bool(value: Any, default: bool = True) -> bool:
    text = _cell_text(value).lower()
    if not text:
        return default
    if text in TRUTHY:
        return True
    if text in FALSY:
        return False
    raise ValueError(f"无法识别的“是否监控”取值: {value}")


def _parse_int(value: Any, field: str) -> Optional[int]:
    text = _cell_text(value)
    if not text:
        return None
    try:
        return int(float(text))
    except ValueError:
        raise ValueError(f"{field} 必须是数字: {value}") from None


def _parse_float(value: Any, field: str) -> Optional[float]:
    text = _cell_text(value)
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"{field} 必须是数字: {value}") from None


def _parse_tags(value: Any) -> List[str]:
    text = _cell_text(value)
    if not text:
        return []
    return [t.strip() for t in re.split(r"[,;，；|/]+", text) if t.strip()]


def read_table(filename: str, content: bytes) -> List[Dict[str, Any]]:
    """读取上传文件为 [{表头: 值}, ...]（跳过空行）"""
    lower = (filename or "").lower()
    rows: List[Dict[str, Any]] = []

    if lower.endswith(".csv"):
        text = None
        for encoding in ("utf-8-sig", "utf-8", "gbk"):
            try:
                text = content.decode(encoding)
                break
            except UnicodeDecodeError:
                continue
        if text is None:
            raise ValueError("CSV 编码无法识别，请使用 UTF-8 或 GBK")
        reader = csv.DictReader(io.StringIO(text))
        for raw in reader:
            rows.append({k: v for k, v in raw.items() if k is not None})
    elif lower.endswith((".xlsx", ".xlsm")):
        try:
            wb = load_workbook(io.BytesIO(content), data_only=True, read_only=True)
        except Exception as exc:  # noqa: BLE001
            raise ValueError(f"Excel 文件解析失败: {exc}") from exc
        ws = wb.active
        values = list(ws.iter_rows(values_only=True))
        if not values:
            return []
        header = [
            ("%s" % (c or "")).replace(" *", "").strip()
            for c in values[0]
        ]
        for row in values[1:]:
            if all(c is None or str(c).strip() == "" for c in row):
                continue
            rows.append({header[i]: row[i] for i in range(min(len(header), len(row)))})
        wb.close()
    else:
        raise ValueError("仅支持 .xlsx 或 .csv 文件")

    return rows


def row_to_fields(row: Dict[str, Any]) -> Dict[str, Any]:
    """把一行表格转换为设备字段（含类型/版本归一化）"""
    data: Dict[str, Any] = {}
    for header, value in row.items():
        key = HEADER_TO_KEY.get((header or "").replace(" *", "").strip())
        if key:
            data[key] = value

    name = _cell_text(data.get("name"))
    ip = _cell_text(data.get("ip_address"))
    raw_type = _cell_text(data.get("device_type"))

    if not name:
        raise ValueError("设备名称不能为空")
    if not ip:
        raise ValueError("IP地址不能为空")
    if not re.match(r"^(\d{1,3}\.){3}\d{1,3}$", ip):
        raise ValueError(f"IP地址格式不正确: {ip}")
    if not raw_type:
        raise ValueError("设备类型不能为空")

    dtype = DEVICE_TYPE_ALIASES.get(raw_type.lower(), DEVICE_TYPE_ALIASES.get(raw_type))
    if not dtype:
        # 允许自定义设备类型：保留用户填写的文本（如「无线控制器」「工业网关」）
        dtype = raw_type.strip()[:40]
        if not dtype:
            raise ValueError("设备类型不能为空")

    version_raw = _cell_text(data.get("snmp_version")).lower() or "v2c"
    version = SNMP_VERSION_ALIASES.get(version_raw)
    if not version:
        raise ValueError(
            f"无法识别 SNMP 版本: {data.get('snmp_version')}（可用 v1/v2c/v3）"
        )

    fields: Dict[str, Any] = {
        "name": name,
        "ip_address": ip,
        "device_type": dtype,
        "snmp_version": version,
        "community": _cell_text(data.get("community")) or "public",
        "port": _parse_int(data.get("port"), "SNMP端口") or 161,
        "v3_username": _cell_text(data.get("v3_username")) or None,
        "v3_security_level": _cell_text(data.get("v3_security_level")) or "authPriv",
        "v3_auth_protocol": (_cell_text(data.get("v3_auth_protocol")) or "SHA").upper(),
        "v3_auth_password": _cell_text(data.get("v3_auth_password")) or None,
        "v3_priv_protocol": (_cell_text(data.get("v3_priv_protocol")) or "AES").upper(),
        "v3_priv_password": _cell_text(data.get("v3_priv_password")) or None,
        "v3_context_name": None,
        "vendor": _cell_text(data.get("vendor")) or None,
        "model": _cell_text(data.get("model")) or None,
        "serial_number": _cell_text(data.get("serial_number")) or None,
        "location": _cell_text(data.get("location")) or None,
        "description": _cell_text(data.get("description")) or None,
        "is_enabled": _parse_bool(data.get("is_enabled"), default=True),
        "tags": _parse_tags(data.get("tags")),
        "u_position": _parse_int(data.get("u_position"), "起始U位"),
        "u_height": _parse_int(data.get("u_height"), "占用U数") or 1,
        "power_watts": _parse_float(data.get("power_watts"), "额定功率") or 0,
        "room_name": _cell_text(data.get("room")),
        "cabinet_name": _cell_text(data.get("cabinet")),
    }

    if fields["u_position"] is not None and fields["u_position"] < 1:
        raise ValueError("起始U位必须大于 0（留空表示自动分配）")
    if fields["u_height"] < 1:
        raise ValueError("占用U数必须大于 0")

    return fields


def resolve_cabinet(
    db: Session, room_name: str, cabinet_name: str, auto_create: bool
) -> Optional[Cabinet]:
    """按机房名 + 机柜名定位机柜；不存在时按需自动创建"""
    if not cabinet_name:
        return None

    room = None
    if room_name:
        room = db.query(Room).filter(Room.name == room_name).first()
        if not room:
            if not auto_create:
                raise ValueError(f"机房不存在: {room_name}")
            room = Room(name=room_name)
            db.add(room)
            db.flush()

    query = db.query(Cabinet).filter(Cabinet.name == cabinet_name)
    if room:
        query = query.filter(Cabinet.room_id == room.id)
    cabinet = query.first()

    if cabinet:
        return cabinet

    if not auto_create:
        raise ValueError(f"机柜不存在: {cabinet_name}")
    if not room:
        raise ValueError("自动创建机柜需要同时填写机房名称")
    count = db.query(Cabinet).filter(Cabinet.room_id == room.id).count()
    cabinet = Cabinet(
        room_id=room.id,
        name=cabinet_name,
        row_index=count // 4,
        col_index=count % 4,
        u_capacity=42,
        power_capacity_w=6000,
    )
    db.add(cabinet)
    db.flush()
    return cabinet


# ==================== 导出 ====================
def export_rows(db: Session, devices: List[Device]) -> List[List[Any]]:
    """把设备列表转换为导出行"""
    rows: List[List[Any]] = []
    for d in devices:
        cabinet = (
            db.query(Cabinet).filter(Cabinet.id == d.cabinet_id).first()
            if d.cabinet_id else None
        )
        room = db.query(Room).filter(Room.id == cabinet.room_id).first() if cabinet else None
        values = {
            "name": d.name,
            "ip_address": d.ip_address,
            "group_name": (db.query(Group).filter(Group.id == d.group_id).first().name if d.group_id else ""),
            "device_type": {
                "router": "路由器", "switch": "交换机",
                "firewall": "防火墙", "security": "安全设备",
            }.get(d.device_type, d.device_type),
            "snmp_version": d.snmp_version,
            "community": d.community,
            "port": d.port,
            "v3_username": d.v3_username,
            "v3_security_level": d.v3_security_level,
            "v3_auth_protocol": d.v3_auth_protocol,
            # 导出不包含密码，仅在有密码时标注
            "v3_auth_password": "******" if d.v3_auth_password else "",
            "v3_priv_protocol": d.v3_priv_protocol,
            "v3_priv_password": "******" if d.v3_priv_password else "",
            "vendor": d.vendor,
            "model": d.model,
            "serial_number": d.serial_number,
            "location": d.location,
            "room": room.name if room else "",
            "cabinet": cabinet.name if cabinet else "",
            "u_position": d.u_position,
            "u_height": d.u_height or 1,
            "power_watts": d.power_watts or 0,
            "is_enabled": "是" if d.is_enabled else "否",
            "tags": ",".join(d.tags or []),
            "description": d.description,
        }
        rows.append([values.get(key, "") for _h, key, *_ in COLUMNS])
    return rows


def export_xlsx(db: Session, devices: List[Device]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "设备资产"
    _header_row_style(ws, [c[4] for c in COLUMNS])
    for row_idx, row in enumerate(export_rows(db, devices), start=2):
        for col_idx, value in enumerate(row, start=1):
            ws.cell(row=row_idx, column=col_idx, value=value)
    ws.freeze_panes = "A2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{len(devices) + 1}"

    info = wb.create_sheet("导出信息")
    info["A1"] = "导出时间"
    info["B1"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    info["A2"] = "设备数量"
    info["B2"] = len(devices)
    info["A3"] = "说明"
    info["B3"] = "SNMPv3 密码不会导出（显示为 ******），导入时该列留空表示沿用原密码"
    info.column_dimensions["A"].width = 12
    info.column_dimensions["B"].width = 90

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_csv(db: Session, devices: List[Device]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([header + (" *" if required else "") for header, _k, _w, _e, required in COLUMNS])
    for row in export_rows(db, devices):
        writer.writerow(row)
    # 加 BOM，保证 Excel 打开中文不乱码
    return buf.getvalue().encode("utf-8-sig")


# ==================== 导入 ====================
def import_devices(
    db: Session,
    rows: List[Dict[str, Any]],
    mode: str = "skip",
    auto_create_cabinet: bool = False,
) -> Dict[str, Any]:
    """执行导入，逐行独立校验（单行失败不影响其他行）"""
    mode = (mode or "skip").lower()
    if mode not in ("skip", "update", "fail"):
        raise ValueError("导入模式仅支持 skip / update / fail")

    created = updated = skipped = 0
    errors: List[Dict[str, Any]] = []
    total = len(rows)

    for idx, row in enumerate(rows, start=2):  # 第 1 行是表头
        try:
            with db.begin_nested():
                fields = row_to_fields(row)
                room_name = fields.pop("room_name", "")
                cabinet_name = fields.pop("cabinet_name", "")
                group_name = str(fields.pop("group_name", "") or "").strip()
                if group_name:
                    group = db.query(Group).filter(Group.name == group_name).first()
                    if not group:
                        raise ValueError(f"资产群组不存在: {group_name}")
                    fields["group_id"] = group.id

                existing = (
                    db.query(Device)
                    .filter(Device.ip_address == fields["ip_address"])
                    .first()
                )

                if existing and mode == "skip":
                    skipped += 1
                    continue
                if existing and mode == "fail":
                    raise ValueError(f"IP 已存在: {fields['ip_address']}")

                cabinet = resolve_cabinet(db, room_name, cabinet_name, auto_create_cabinet)

                if cabinet:
                    # 密码列若为 ****** 视为沿用
                    for secret in ("v3_auth_password", "v3_priv_password"):
                        if fields.get(secret) == "******":
                            fields[secret] = existing.__dict__.get(secret) if existing else None
                    fields["cabinet_id"] = cabinet.id
                    fields["u_position"] = validate_placement(
                        db,
                        cabinet,
                        fields.get("u_position"),
                        fields.get("u_height"),
                        fields.get("power_watts"),
                        exclude_device_id=existing.id if existing else None,
                    )
                else:
                    fields["cabinet_id"] = None
                    fields["u_position"] = None

                if existing:
                    for key, value in fields.items():
                        setattr(existing, key, value)
                    existing.updated_at = datetime.utcnow()
                    updated += 1
                else:
                    license_manager.check_asset_capacity(db)
                    device = Device(**fields)
                    device.created_at = datetime.utcnow()
                    device.updated_at = datetime.utcnow()
                    db.add(device)
                    created += 1
        except Exception as exc:  # noqa: BLE001
            message = getattr(exc, "detail", None) or str(exc)
            errors.append({"row": idx, "ip": _cell_text(row.get("IP地址")), "message": message})

    db.commit()
    return {
        "total": total,
        "created": created,
        "updated": updated,
        "skipped": skipped,
        "failed": len(errors),
        "errors": errors[:200],
    }
