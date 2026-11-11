"""资产路由 - 设备CRUD接口"""
import io
import re
import uuid
from pathlib import Path
from urllib.parse import quote

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import Any, Dict, Optional, List
from datetime import datetime, timedelta

from ..config import Config
from ..models.database import get_db
from ..models.models import (
    Alert, Device, DeviceConnection, DeviceInterface, DeviceMetric, InterfaceMetric,
)
from ..models.alert_rule import DeviceAlertRule
from ..models.maintenance import DeviceMaintenance
from ..models.mib import MibFile
from ..models.room import Cabinet, Room
from ..models.user import Group, User
from ..models.schemas import DeviceCreate, DeviceUpdate, DeviceOut, MaintenanceCreate
from ..services.placement import validate_placement
from ..services import asset_io, asset_qr, icon_presets, license_manager, alert_rules as alert_rule_service
from ..services.cache import invalidate_topology
from ..services import asset_scope, audit
from ..services.virtualization_crypto import encrypt_password
from ..services.cache import invalidate_all
from ..services.warranty_alerts import check_warranty_alerts
from ..notify import notify_alert_sync

router = APIRouter(prefix="/api/assets", tags=["资产管理"])

EXCEL_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

# 自定义采集 OID：允许的指标与 OID 格式
CUSTOM_METRIC_KEYS = ("cpu", "memory", "temperature", "power")
OID_PATTERN = re.compile(r"^\d+(\.\d+){2,}$")
CUSTOM_METRIC_KEY_PATTERN = re.compile(r"^[a-z][a-z0-9_]{0,29}$")
MONITOR_TYPES = {"snmp", "ping", "tcp", "api", "ipmi"}


class ProbeTestRequest(BaseModel):
    host: str
    monitor_type: str = "ping"
    tcp_port: int = 80
    timeout: int = 5


class ApiTestRequest(BaseModel):
    host: str
    vendor: Optional[str] = None
    model: Optional[str] = None
    storage_username: Optional[str] = None
    storage_password: Optional[str] = None
    storage_api_port: int = 443
    api_auth_type: str = "auto"
    api_base_path: Optional[str] = None
    api_paths: Optional[Dict[str, Any]] = None
    device_id: Optional[int] = None
    timeout: int = 12


class IpmiTestRequest(BaseModel):
    host: str
    ipmi_username: Optional[str] = None
    ipmi_password: Optional[str] = None
    ipmi_protocol: str = "auto"
    ipmi_port: int = 623
    device_id: Optional[int] = None


class AssetGroupCreate(BaseModel):
    name: str
    code: Optional[str] = None
    description: Optional[str] = None


def _validate_monitor_config(data: dict) -> None:
    """校验接入方式：SNMP / ICMP Ping / TCP 端口。"""
    if "monitor_type" in data:
        method = str(data.get("monitor_type") or "snmp").strip().lower()
        if method not in MONITOR_TYPES:
            raise HTTPException(status_code=400, detail="接入方式必须是 snmp、ping、tcp、api 或 ipmi")
        data["monitor_type"] = method
    method = data.get("monitor_type")
    if method == "tcp" or "tcp_port" in data:
        try:
            tcp_port = int(data.get("tcp_port") or 80)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="TCP端口必须是数字") from None
        if not 1 <= tcp_port <= 65535:
            raise HTTPException(status_code=400, detail="TCP端口必须在 1~65535 之间")
        data["tcp_port"] = tcp_port


def _warranty_info(device: Device) -> dict:
    """维保到期信息：剩余天数（负数表示已过期）"""
    raw = (device.warranty_until or "").strip()
    days_left = None
    expired = False
    if raw:
        try:
            expire = datetime.strptime(raw, "%Y-%m-%d").date()
            days_left = (expire - datetime.utcnow().date()).days
            expired = days_left < 0
        except ValueError:
            pass
    return {
        "warranty_days_left": days_left,
        "warranty_expired": expired,
        "warranty_expiring": days_left is not None and 0 <= days_left <= 30,
    }


def _validate_custom_config(db: Session, data: dict, device: Device | None = None) -> None:
    """校验收到的 MIB 引用与自定义 OID 配置"""
    mib_id = data.get("mib_id")
    if mib_id and not db.query(MibFile).filter(MibFile.id == mib_id).first():
        raise HTTPException(status_code=400, detail="所选 MIB 不存在")

    custom = data.get("custom_oids")
    if custom is not None:
        if not isinstance(custom, dict):
            raise HTTPException(status_code=400, detail="自定义 OID 必须是对象（指标 → OID）")

        clean: dict = {}
        for key, value in custom.items():
            if key not in CUSTOM_METRIC_KEYS:
                raise HTTPException(
                    status_code=400,
                    detail=f"不支持的采集指标：{key}（可选 {', '.join(CUSTOM_METRIC_KEYS)}）",
                )
            if value is None or str(value).strip() == "":
                continue
            text = str(value).strip()
            if not OID_PATTERN.match(text):
                raise HTTPException(
                    status_code=400, detail=f"OID 格式不正确：{text}（示例 1.3.6.1.2.1.25.3.3.1.2）"
                )
            clean[key] = text
        data["custom_oids"] = clean

    # 自定义指标（光功率、风扇转速等任意 OID 指标）
    metrics = data.get("custom_metrics")
    if metrics is not None:
        if not isinstance(metrics, list):
            raise HTTPException(status_code=400, detail="custom_metrics 必须是数组")
        if len(metrics) > 20:
            raise HTTPException(status_code=400, detail="自定义指标最多 20 个")
        clean_metrics = []
        used_keys = set()
        for item in metrics:
            if not isinstance(item, dict):
                raise HTTPException(status_code=400, detail="自定义指标格式错误")
            key = str(item.get("key") or "").strip().lower()
            if not CUSTOM_METRIC_KEY_PATTERN.match(key):
                raise HTTPException(
                    status_code=400,
                    detail=f"指标标识不合法：{key or '(空)'}（小写字母开头，可含数字和下划线）",
                )
            if key in used_keys:
                raise HTTPException(status_code=400, detail=f"指标标识重复：{key}")
            used_keys.add(key)
            oid = str(item.get("oid") or "").strip()
            if not oid or not OID_PATTERN.match(oid):
                raise HTTPException(status_code=400, detail=f"指标 {key} 的 OID 格式不正确")
            name = str(item.get("name") or key).strip()[:60]
            unit = str(item.get("unit") or "").strip()[:20]
            try:
                scale = float(item.get("scale") or 1)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"指标 {key} 的系数必须是数字") from None
            if scale == 0:
                scale = 1
            clean_metrics.append({
                "key": key, "name": name, "oid": oid, "unit": unit, "scale": scale,
            })
        data["custom_metrics"] = clean_metrics

    # 服务器硬件传感器（CPU温度/内存物理状态/电源电压电流功率/硬盘状态与使用率/风扇/进排风温度等）
    sensors = data.get("server_sensors")
    if sensors is not None:
        if not isinstance(sensors, list):
            raise HTTPException(status_code=400, detail="server_sensors 必须是数组")
        if len(sensors) > 20:
            raise HTTPException(status_code=400, detail="服务器硬件传感器最多 20 个")
        clean_sensors = []
        used_keys = set()
        for item in sensors:
            if not isinstance(item, dict):
                raise HTTPException(status_code=400, detail="服务器传感器格式错误")
            key = str(item.get("key") or "").strip().lower()
            if not CUSTOM_METRIC_KEY_PATTERN.match(key):
                raise HTTPException(status_code=400, detail=f"传感器标识不合法：{key or '(空)'}")
            if key in used_keys:
                raise HTTPException(status_code=400, detail=f"传感器标识重复：{key}")
            used_keys.add(key)
            oid = str(item.get("oid") or "").strip()
            if not oid:
                continue
            if not OID_PATTERN.match(oid):
                raise HTTPException(status_code=400, detail=f"传感器 {key} 的 OID 格式不正确")
            try:
                scale = float(item.get("scale") or 1)
            except (TypeError, ValueError):
                raise HTTPException(status_code=400, detail=f"传感器 {key} 的系数必须是数字") from None
            if scale == 0:
                scale = 1
            clean_sensors.append({
                "key": key,
                "name": str(item.get("name") or key).strip()[:60],
                "oid": oid,
                "unit": str(item.get("unit") or "").strip()[:20],
                "scale": scale,
                "kind": str(item.get("kind") or "value").strip()[:20],
            })
        data["server_sensors"] = clean_sensors

# 设备自定义图标：允许的格式与文件头校验
ICON_DIR = Path(Config.UPLOAD_DIR) / "icons"
ICON_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
ICON_URL_PREFIX = "/uploads/icons"
ICON_MAGIC = [
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
    (b"RIFF", ".webp"),  # 需再校验 WEBP 标识
]


def _icon_dir() -> Path:
    ICON_DIR.mkdir(parents=True, exist_ok=True)
    return ICON_DIR


def _validate_icon(content: bytes, filename: str, content_type: str) -> str:
    """校验图标文件，返回保存用的扩展名"""
    limit = Config.MAX_ICON_SIZE_MB * 1024 * 1024
    if not content:
        raise HTTPException(status_code=400, detail="图标文件为空")
    if len(content) > limit:
        raise HTTPException(
            status_code=400, detail=f"图标不能超过 {Config.MAX_ICON_SIZE_MB}MB"
        )

    ext = Path(filename or "").suffix.lower()
    if ext not in ICON_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="仅支持 PNG / JPG / GIF / WEBP 图标；SVG 自定义图标已禁用",
        )

    # 文件头校验，防止改扩展名上传其它文件
    if ext in (".png", ".jpg", ".jpeg", ".gif", ".webp"):
        ok = any(content.startswith(magic) for magic, _e in ICON_MAGIC)
        if ext == ".webp":
            ok = content.startswith(b"RIFF") and content[8:12] == b"WEBP"
        elif ext in (".jpg", ".jpeg"):
            ok = content.startswith(b"\xff\xd8\xff")
        elif ext == ".png":
            ok = content.startswith(b"\x89PNG\r\n\x1a\n")
        elif ext == ".gif":
            ok = content[:6] in (b"GIF87a", b"GIF89a")
        if not ok:
            raise HTTPException(status_code=400, detail="文件内容与图片格式不匹配")
    else:  # SVG：简单安全校验
        head = content[:400].lower()
        if b"<svg" not in content[:4000].lower():
            raise HTTPException(status_code=400, detail="SVG 文件内容无效")
        if b"<script" in content.lower() or b"javascript:" in head or b"onload=" in content.lower():
            raise HTTPException(status_code=400, detail="SVG 中包含不安全的脚本内容")

    return ".jpg" if ext == ".jpeg" else ext


def _save_icon(content: bytes, ext: str) -> str:
    """保存图标并返回可访问 URL"""
    name = f"{uuid.uuid4().hex}{ext}"
    target = _icon_dir() / name
    target.write_bytes(content)
    return f"{ICON_URL_PREFIX}/{name}"



def _download_headers(filename: str) -> dict:
    """中文文件名下载头（RFC 5987）"""
    return {
        "Content-Disposition": (
            f"attachment; filename=\"assets\"; filename*=UTF-8''{quote(filename)}"
        )
    }


@router.get("/")
def list_devices(
    request: Request,
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    device_type: Optional[str] = None,
    search: Optional[str] = None,
    cabinet_id: Optional[int] = None,
    room_id: Optional[int] = None,
    group_id: Optional[int] = None,
):
    """获取设备列表（支持按机柜/机房/资产群组过滤；按用户群组限制可见范围）"""
    query = _device_query(db, device_type, search, cabinet_id, room_id, group_id)
    query = asset_scope.scope_device_query(db, request, query)

    total = query.count()
    devices = query.offset((page - 1) * size).limit(size).all()

    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [device_to_dict(db, d) for d in devices],
    }


def _device_query(
    db: Session,
    device_type: Optional[str] = None,
    search: Optional[str] = None,
    cabinet_id: Optional[int] = None,
    room_id: Optional[int] = None,
    group_id: Optional[int] = None,
    ids: Optional[str] = None,
):
    query = db.query(Device)
    if device_type:
        query = query.filter(Device.device_type == device_type)
    if search:
        query = query.filter(
            Device.name.contains(search) | Device.ip_address.contains(search)
        )
    if cabinet_id is not None:
        query = query.filter(Device.cabinet_id == cabinet_id)
    if room_id is not None:
        cabinet_ids = [
            c.id for c in db.query(Cabinet).filter(Cabinet.room_id == room_id).all()
        ]
        query = query.filter(Device.cabinet_id.in_(cabinet_ids or [-1]))
    if group_id is not None:
        query = query.filter(Device.group_id == group_id)
    if ids:
        try:
            id_list = [int(item) for item in ids.split(",") if item.strip()]
        except ValueError:
            raise HTTPException(status_code=400, detail="设备 ID 列表格式不正确")
        query = query.filter(Device.id.in_(id_list or [-1]))
    return query.order_by(Device.id)


# ==================== 导入 / 导出 ====================
@router.get("/export")
def export_devices(
    request: Request,
    fmt: str = Query("xlsx", alias="format", pattern="^(xlsx|csv)$"),
    device_type: Optional[str] = None,
    search: Optional[str] = None,
    cabinet_id: Optional[int] = None,
    room_id: Optional[int] = None,
    group_id: Optional[int] = None,
    ids: Optional[str] = Query(None, description="选中设备 ID，逗号分隔"),
    db: Session = Depends(get_db),
):
    """导出设备资产（xlsx / csv，支持筛选；可传 ids 仅导出选中设备；按用户群组限制）"""
    query = _device_query(
        db, device_type, search, cabinet_id, room_id, group_id, ids
    )
    devices = asset_scope.scope_device_query(db, request, query).all()
    stamp = datetime.now().strftime("%Y%m%d_%H%M")

    if fmt == "csv":
        content = asset_io.export_csv(db, devices)
        filename = f"设备资产_{stamp}.csv"
        media_type = "text/csv; charset=utf-8"
    else:
        content = asset_io.export_xlsx(db, devices)
        filename = f"设备资产_{stamp}.xlsx"
        media_type = EXCEL_TYPE

    return Response(
        content=content,
        media_type=media_type,
        headers=_download_headers(filename),
    )


@router.get("/import-template")
def download_import_template():
    """下载导入模板（xlsx，含示例行与填写说明）"""
    content = asset_io.build_template()
    return Response(
        content=content,
        media_type=EXCEL_TYPE,
        headers=_download_headers("设备导入模板.xlsx"),
    )


@router.post("/import")
async def import_devices(
    file: UploadFile = File(..., description="xlsx 或 csv 文件"),
    mode: str = Form("skip", description="skip / update / fail"),
    auto_create_cabinet: bool = Form(False, description="机房/机柜不存在时是否自动创建"),
    db: Session = Depends(get_db),
):
    """导入设备资产

    - mode=skip：IP 已存在则跳过（默认）
    - mode=update：IP 已存在则更新
    - mode=fail：IP 已存在则报错
    每行独立校验，失败行返回原因，不影响其它行。
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="请选择要上传的文件")

    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="文件内容为空")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件过大（限制 10MB）")

    try:
        rows = asset_io.read_table(file.filename, content)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not rows:
        raise HTTPException(status_code=400, detail="文件中没有可导入的数据行")

    try:
        result = asset_io.import_devices(
            db, rows, mode=mode, auto_create_cabinet=auto_create_cabinet
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise HTTPException(status_code=500, detail=f"导入失败: {exc}") from exc

    result["filename"] = file.filename
    invalidate_all()
    return result


@router.post("/icons")
async def upload_device_icon(file: UploadFile = File(..., description="PNG/JPG/GIF/WEBP/SVG")):
    """上传设备自定义图标，返回可访问的 URL

    上传后把返回的 url 写入设备的 `icon` 字段即可（资产表单已集成）。
    """
    content = await file.read()
    ext = _validate_icon(content, file.filename or "", file.content_type or "")
    url = _save_icon(content, ext)
    return {
        "url": url,
        "filename": file.filename,
        "size": len(content),
        "content_type": file.content_type,
    }


# ==================== 内置图标库 / 厂商匹配 / 批量图标 ====================
@router.get("/icon-presets")
def list_icon_presets(db: Session = Depends(get_db)):
    """内置图标库（按设备类型 + 按厂商）与厂商匹配规则

    返回的 `presets[].url` 可直接写入设备 `icon` 字段。
    `custom_icons` 为已上传的自定义图标，可在图标选择器里复用。
    """
    custom_urls = [
        row[0]
        for row in db.query(Device.icon)
        .filter(Device.icon.like("/uploads/icons/%"))
        .distinct()
        .all()
        if row[0]
    ]
    return {
        "presets": icon_presets.list_presets(),
        "vendor_rules": icon_presets.vendor_rules(),
        "custom_icons": sorted(custom_urls),
    }


@router.post("/match-icons")
def match_device_icons(payload: dict = Body(default=None), db: Session = Depends(get_db)):
    """按厂商（其次按设备类型）自动匹配内置图标

    请求体（可选）：
      {"overwrite": false}   # true 时覆盖已有图标，默认只补空图标
    """
    overwrite = bool((payload or {}).get("overwrite"))
    devices = db.query(Device).all()
    matched = 0
    skipped = 0
    details = []
    for device in devices:
        if device.icon and not overwrite:
            skipped += 1
            continue
        icon_url = icon_presets.match_preset(device)
        if not icon_url:
            skipped += 1
            continue
        device.icon = icon_url
        matched += 1
        details.append({
            "device_id": device.id,
            "device_name": device.name,
            "vendor": device.vendor,
            "icon": icon_url,
        })
    if matched:
        db.commit()
        invalidate_all()
    return {
        "matched": matched,
        "skipped": skipped,
        "total": len(devices),
        "details": details[:50],
    }


@router.post("/apply-icon")
def apply_icon_to_devices(payload: dict = Body(...), db: Session = Depends(get_db)):
    """按分组（设备类型 / 厂商 / 选中设备 / 全部）批量套用图标

    请求体：
      {"icon": "/uploads/presets/switch.svg", "scope": "type", "value": "switch"}
      {"icon": "/uploads/presets/vendor-huawei.svg", "scope": "vendor", "value": "huawei"}
      {"icon": "/uploads/presets/server.svg", "scope": "ids", "ids": [1, 2, 3]}
      {"icon": "/uploads/presets/router.svg", "scope": "all"}
    """
    icon_url = (payload.get("icon") or "").strip()
    if not icon_presets.is_valid_icon(icon_url):
        raise HTTPException(status_code=400, detail="图标地址不合法")
    if not icon_url:
        raise HTTPException(status_code=400, detail="请选择图标")

    scope = (payload.get("scope") or "type").strip()
    value = payload.get("value")
    ids = payload.get("ids") or []

    query = db.query(Device)
    if scope == "type":
        if not value:
            raise HTTPException(status_code=400, detail="请选择设备类型")
        query = query.filter(Device.device_type == value)
    elif scope == "vendor":
        if not value:
            raise HTTPException(status_code=400, detail="请填写厂商关键字")
        query = query.filter(Device.vendor.ilike(f"%{value}%"))
    elif scope == "ids":
        try:
            device_ids = [int(i) for i in ids]
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="设备 ID 不合法") from None
        if not device_ids:
            raise HTTPException(status_code=400, detail="未选择设备")
        query = query.filter(Device.id.in_(device_ids))
    elif scope != "all":
        raise HTTPException(status_code=400, detail="scope 仅支持 type / vendor / ids / all")

    updated = query.update({Device.icon: icon_url}, synchronize_session=False)
    db.commit()
    invalidate_all()
    return {"updated": int(updated), "icon": icon_url, "scope": scope}


# ==================== 维保记录 ====================
MAINT_TYPE_LABELS = {
    "repair": "维修",
    "inspection": "巡检",
    "parts": "更换配件",
    "other": "其它",
}


def _maintenance_to_dict(item: DeviceMaintenance) -> dict:
    return {
        "id": item.id,
        "device_id": item.device_id,
        "maint_type": item.maint_type,
        "maint_type_label": MAINT_TYPE_LABELS.get(item.maint_type, item.maint_type),
        "title": item.title,
        "description": item.description,
        "engineer": item.engineer,
        "cost": item.cost,
        "maintained_at": item.maintained_at.isoformat() if item.maintained_at else None,
        "created_by": item.created_by,
        "created_at": item.created_at.isoformat() if item.created_at else None,
    }


@router.get("/{device_id}/maintenance")
def list_maintenance(device_id: int, db: Session = Depends(get_db)):
    """设备维保记录列表"""
    if not db.query(Device).filter(Device.id == device_id).first():
        raise HTTPException(status_code=404, detail="设备不存在")
    items = (
        db.query(DeviceMaintenance)
        .filter(DeviceMaintenance.device_id == device_id)
        .order_by(DeviceMaintenance.maintained_at.desc(), DeviceMaintenance.id.desc())
        .all()
    )
    return {"total": len(items), "items": [_maintenance_to_dict(i) for i in items]}


@router.post("/{device_id}/maintenance")
def create_maintenance(
    device_id: int,
    payload: MaintenanceCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    """新增设备维保记录"""
    if not db.query(Device).filter(Device.id == device_id).first():
        raise HTTPException(status_code=404, detail="设备不存在")
    if not payload.title.strip():
        raise HTTPException(status_code=400, detail="请填写维保事项标题")

    operator = getattr(request.state, "username", None)
    item = DeviceMaintenance(
        device_id=device_id,
        maint_type=payload.maint_type or "inspection",
        title=payload.title.strip()[:200],
        description=payload.description,
        engineer=payload.engineer,
        cost=payload.cost,
        maintained_at=payload.maintained_at or datetime.utcnow(),
        created_by=operator,
    )
    db.add(item)
    db.commit()
    db.refresh(item)
    return _maintenance_to_dict(item)


@router.delete("/maintenance/{maintenance_id}")
def delete_maintenance(maintenance_id: int, db: Session = Depends(get_db)):
    """删除维保记录"""
    item = db.query(DeviceMaintenance).filter(
        DeviceMaintenance.id == maintenance_id
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="维保记录不存在")
    db.delete(item)
    db.commit()
    return {"message": "维保记录已删除"}


# ==================== 资产标签二维码 ====================
@router.get("/{device_id}/qrcode")
def get_device_qrcode(
    device_id: int,
    request: Request,
    kind: str = Query("url", pattern="^(url|text)$"),
    db: Session = Depends(get_db),
):
    """生成设备资产标签二维码（返回 base64 PNG 与编码内容）"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    try:
        return asset_qr.device_qr(device, str(request.base_url), kind)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/{device_id}/qrcode.png")
def get_device_qrcode_png(
    device_id: int,
    request: Request,
    kind: str = Query("url", pattern="^(url|text)$"),
    box_size: int = Query(8, ge=3, le=16),
    db: Session = Depends(get_db),
):
    """直接下载/打印二维码 PNG"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    payload = asset_qr.device_tag_payload(device, str(request.base_url))
    content = payload["url"] if kind == "url" else asset_qr.device_qr(device, str(request.base_url), "text")["content"]
    try:
        png = asset_qr.build_qr_png(content, box_size=box_size)
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    filename = f"device-{device.id}-qrcode.png"
    return Response(
        content=png,
        media_type="image/png",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@router.post("/groups")
def create_asset_group(
    payload: AssetGroupCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    """设备编辑时直接新建资产群组（资产编辑权限即可）。"""
    name = str(payload.name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="群组名称不能为空")
    if len(name) > 100:
        raise HTTPException(status_code=400, detail="群组名称不能超过 100 个字符")
    if db.query(Group).filter(Group.name == name).first():
        raise HTTPException(status_code=400, detail="群组名称已存在")
    group = Group(
        name=name,
        code=(payload.code or "").strip() or None,
        description=(payload.description or "").strip() or None,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    audit.record(
        db, request, module="assets", action="create",
        target_type="group", target_id=group.id, target_name=group.name,
        after={"name": group.name, "code": group.code, "description": group.description},
        message=f"编辑设备时新建资产群组 {group.name}",
    )
    return {"id": group.id, "name": group.name, "code": group.code, "description": group.description}


@router.get("/groups")
def list_asset_groups(db: Session = Depends(get_db)):
    """资产表单/筛选使用的群组列表（assets:view 权限即可读取）"""
    groups = db.query(Group).order_by(Group.id).all()
    return {
        "total": len(groups),
        "items": [
            {"id": group.id, "name": group.name, "code": group.code}
            for group in groups
        ],
    }


@router.post("/test-ipmi")
async def test_ipmi(payload: IpmiTestRequest, request: Request, db: Session = Depends(get_db)):
    """测试 IPMI 1.5/2.0（RMCP/RMCP+）只读连通性。"""
    from types import SimpleNamespace
    from ..services.ipmi_collector import probe_ipmi

    if not (payload.host or "").strip():
        raise HTTPException(status_code=400, detail="请输入 IPMI IP 或主机名")
    saved = None
    if payload.device_id:
        saved = db.query(Device).filter(Device.id == payload.device_id).first()
        if saved:
            asset_scope.require_device_access(db, request, saved)
    supplied_password = str(payload.ipmi_password or "").strip()
    password_enc = encrypt_password(supplied_password) if supplied_password else (saved.ipmi_password_enc if saved else "")
    device = SimpleNamespace(
        ip_address=payload.host.strip(),
        ipmi_username=payload.ipmi_username or (saved.ipmi_username if saved else "") or "",
        ipmi_password_enc=password_enc,
        ipmi_protocol=payload.ipmi_protocol or (saved.ipmi_protocol if saved else "auto"),
        ipmi_port=int(payload.ipmi_port or 623),
    )
    return probe_ipmi(device)


@router.post("/test-api")
async def test_api(payload: ApiTestRequest, request: Request, db: Session = Depends(get_db)):
    """测试统一 API 接入：仅执行只读登录/查询，不修改厂商设备。"""
    from types import SimpleNamespace
    from ..services.api_collector import probe_api

    if not (payload.host or "").strip():
        raise HTTPException(status_code=400, detail="请输入 IP 或主机名")
    saved = None
    if payload.device_id:
        saved = db.query(Device).filter(Device.id == payload.device_id).first()
        if saved:
            asset_scope.require_device_access(db, request, saved)
    supplied_password = str(payload.storage_password or "").strip()
    if supplied_password:
        password_enc = encrypt_password(supplied_password)
    else:
        password_enc = saved.storage_password_enc if saved else ""
    device = SimpleNamespace(
        ip_address=payload.host.strip(),
        vendor=payload.vendor or (saved.vendor if saved else "") or "",
        model=payload.model or (saved.model if saved else "") or "",
        device_type="storage",
        storage_username=payload.storage_username or (saved.storage_username if saved else "") or "",
        storage_password_enc=password_enc,
        storage_api_port=int(payload.storage_api_port or 443),
        api_auth_type=payload.api_auth_type or (saved.api_auth_type if saved else "auto"),
        api_base_path=payload.api_base_path or (saved.api_base_path if saved else "") or "",
        api_paths=payload.api_paths or (saved.api_paths if saved else {}) or {},
    )
    return probe_api(device)


@router.get("/{device_id}")
def get_device(device_id: int, request: Request, db: Session = Depends(get_db)):
    """获取设备详情（按群组校验）"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    asset_scope.require_device_access(db, request, device)
    return device_to_dict(db, device)


@router.post("/test-probe")
async def test_probe(payload: ProbeTestRequest):
    """测试 Ping / TCP 接入方式（SNMP 请使用 /api/snmp/test）。"""
    from ..website.monitor import WebsiteMonitor

    host = (payload.host or "").strip()
    if not host:
        raise HTTPException(status_code=400, detail="请输入 IP 或主机名")
    method = (payload.monitor_type or "ping").lower()
    if method not in {"ping", "tcp"}:
        raise HTTPException(status_code=400, detail="该接口只支持 ping 或 tcp")
    timeout = max(1, min(15, int(payload.timeout or 5)))
    monitor = WebsiteMonitor()
    if method == "tcp":
        port = max(1, min(65535, int(payload.tcp_port or 80)))
        result = await monitor.check_tcp(host, port, timeout=timeout)
        reachable = bool(result.get("is_alive"))
        latency = result.get("response_time") or 0
        error = result.get("error_message") or ""
        target = f"{host}:{port}"
    else:
        result = await monitor.check_ping(host, timeout=timeout)
        reachable = bool(result.get("is_alive"))
        latency = result.get("avg_latency") or result.get("response_time") or 0
        error = result.get("error_message") or ""
        target = host
    return {
        "reachable": reachable,
        "method": method,
        "target": target,
        "latency_ms": round(float(latency or 0), 2),
        "error": error,
        "final_ip": result.get("final_ip") or host,
    }


@router.post("/")
def create_device(payload: DeviceCreate, request: Request, db: Session = Depends(get_db)):
    """创建设备（可同时上架到机柜，会校验 U 位与功率）"""
    existing = db.query(Device).filter(Device.ip_address == payload.ip_address).first()
    if existing:
        raise HTTPException(status_code=400, detail="该IP地址已存在")

    license_manager.check_asset_capacity(db)
    data = payload.model_dump()
    storage_password = str(data.pop("storage_password", None) or "").strip()
    if storage_password:
        data["storage_password_enc"] = encrypt_password(storage_password)
    else:
        data.pop("storage_password_enc", None)
    ipmi_password = str(data.pop("ipmi_password", None) or "").strip()
    if ipmi_password:
        data["ipmi_password_enc"] = encrypt_password(ipmi_password)
    else:
        data.pop("ipmi_password_enc", None)
    _validate_monitor_config(data)
    _validate_custom_config(db, data)

    # 资产群组：普通用户只能创建到自己的群组，未指定时默认第一个群组
    allowed_groups = asset_scope.allowed_group_ids(db, request)
    group_id = data.get("group_id")
    if group_id is not None:
        group = db.query(Group).filter(Group.id == group_id).first()
        if not group:
            raise HTTPException(status_code=400, detail="所选资产群组不存在")
        if allowed_groups is not None and group_id not in allowed_groups:
            raise HTTPException(status_code=403, detail="无权将设备分配到该群组")
    elif allowed_groups is not None:
        data["group_id"] = allowed_groups[0] if allowed_groups else None

    # 机柜上架校验：U 位范围/冲突 + 功率不得超机柜额定
    cabinet_id = data.get("cabinet_id")
    if cabinet_id:
        cabinet = db.query(Cabinet).filter(Cabinet.id == cabinet_id).first()
        if not cabinet:
            raise HTTPException(status_code=400, detail="所选机柜不存在")
        data["u_position"] = validate_placement(
            db,
            cabinet,
            data.get("u_position"),
            data.get("u_height"),
            data.get("power_watts"),
        )
    else:
        data["cabinet_id"] = None
        data["u_position"] = None

    device = Device(**data)
    device.source = "manual"
    device.discovered_at = None
    if device.tags is None:
        device.tags = []
    if device.custom_oids is None:
        device.custom_oids = {}
    if device.custom_metrics is None:
        device.custom_metrics = []
    if device.server_sensors is None:
        device.server_sensors = []
    device.created_at = datetime.utcnow()
    device.updated_at = datetime.utcnow()
    db.add(device)
    db.commit()
    invalidate_all()
    db.refresh(device)
    for notification in check_warranty_alerts(db, [device.id]):
        notify_alert_sync(notification)
    return device_to_dict(db, device)


@router.put("/{device_id}")
def update_device(
    device_id: int,
    payload: DeviceUpdate,
    request: Request,
    db: Session = Depends(get_db),
):
    """更新设备（按群组校验；普通用户只能分配到自己的群组）"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    asset_scope.require_device_access(db, request, device)

    data = payload.model_dump(exclude_unset=True)
    storage_password = str(data.pop("storage_password", None) or "").strip()
    if storage_password:
        data["storage_password_enc"] = encrypt_password(storage_password)
    ipmi_password = str(data.pop("ipmi_password", None) or "").strip()
    if ipmi_password:
        data["ipmi_password_enc"] = encrypt_password(ipmi_password)
    _validate_monitor_config(data)
    if "group_id" in data:
        group_id = data.get("group_id")
        if group_id is not None:
            group = db.query(Group).filter(Group.id == group_id).first()
            if not group:
                raise HTTPException(status_code=400, detail="所选资产群组不存在")
            allowed_groups = asset_scope.allowed_group_ids(db, request)
            if allowed_groups is not None and group_id not in allowed_groups:
                raise HTTPException(status_code=403, detail="无权将设备分配到该群组")
    if "ip_address" in data and data["ip_address"] != device.ip_address:
        dup = db.query(Device).filter(Device.ip_address == data["ip_address"]).first()
        if dup:
            raise HTTPException(status_code=400, detail="该IP地址已存在")

    if "custom_oids" in data or "custom_metrics" in data or "server_sensors" in data or "mib_id" in data:
        _validate_custom_config(db, data, device)

    # SNMPv3 密码：为空表示不修改，避免前端回传空值覆盖旧密码
    for secret_key in ("v3_auth_password", "v3_priv_password"):
        if secret_key in data and not data[secret_key]:
            data.pop(secret_key)

    # 机柜上架校验（涉及机柜/U位/高度/功率任一变化时）
    placement_keys = {"cabinet_id", "u_position", "u_height", "power_watts"}
    if placement_keys & set(data.keys()):
        cabinet_id = data.get("cabinet_id", device.cabinet_id)
        if cabinet_id:
            cabinet = db.query(Cabinet).filter(Cabinet.id == cabinet_id).first()
            if not cabinet:
                raise HTTPException(status_code=400, detail="所选机柜不存在")
            data["u_position"] = validate_placement(
                db,
                cabinet,
                data.get("u_position", device.u_position),
                data.get("u_height", device.u_height),
                data.get("power_watts", device.power_watts),
                exclude_device_id=device.id,
            )
            data["cabinet_id"] = cabinet.id
        else:
            data["cabinet_id"] = None
            data["u_position"] = None

    for key, value in data.items():
        setattr(device, key, value)

    device.updated_at = datetime.utcnow()
    db.commit()
    invalidate_all()
    db.refresh(device)
    for notification in check_warranty_alerts(db, [device.id]):
        notify_alert_sync(notification)
    invalidate_topology()
    return device_to_dict(db, device)


def _purge_device_records(db: Session, device_id: int) -> None:
    """删除设备关联数据（接口/指标/告警/维保/拓扑/接口历史）"""
    db.query(DeviceInterface).filter(DeviceInterface.device_id == device_id).delete(
        synchronize_session=False
    )
    db.query(InterfaceMetric).filter(InterfaceMetric.device_id == device_id).delete(
        synchronize_session=False
    )
    db.query(DeviceMetric).filter(DeviceMetric.device_id == device_id).delete(
        synchronize_session=False
    )
    db.query(Alert).filter(Alert.device_id == device_id).delete(
        synchronize_session=False
    )
    db.query(DeviceMaintenance).filter(
        DeviceMaintenance.device_id == device_id
    ).delete(synchronize_session=False)
    db.query(DeviceConnection).filter(
        (DeviceConnection.source_device_id == device_id)
        | (DeviceConnection.dest_device_id == device_id)
    ).delete(synchronize_session=False)


@router.post("/bulk-update")
def bulk_update_devices(
    request: Request,
    payload: dict = Body(..., description="{ids:[...], fields:{...}}"),
    db: Session = Depends(get_db),
):
    """批量修改设备（仅允许指定字段，按群组校验）"""
    ids = payload.get("ids") or []
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=400, detail="请选择要修改的设备")
    try:
        device_ids = list(dict.fromkeys(int(item) for item in ids))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="设备 ID 列表格式不正确")

    fields = payload.get("fields") or {}
    if not isinstance(fields, dict) or not fields:
        raise HTTPException(status_code=400, detail="请选择要修改的字段")
    allowed_fields = {"group_id", "location", "vendor", "tags", "is_enabled", "device_type"}
    unknown = set(fields) - allowed_fields
    if unknown:
        raise HTTPException(status_code=400, detail=f"不支持批量修改字段: {', '.join(sorted(unknown))}")

    if "group_id" in fields:
        group_id = fields.get("group_id")
        if group_id is not None:
            group = db.query(Group).filter(Group.id == group_id).first()
            if not group:
                raise HTTPException(status_code=400, detail="所选资产群组不存在")
            allowed_groups = asset_scope.allowed_group_ids(db, request)
            if allowed_groups is not None and group_id not in allowed_groups:
                raise HTTPException(status_code=403, detail="无权将设备分配到该群组")

    if "is_enabled" in fields:
        fields["is_enabled"] = bool(fields["is_enabled"])
    if "tags" in fields:
        tags = fields["tags"]
        if isinstance(tags, str):
            tags = [item.strip() for item in tags.split(",") if item.strip()]
        elif isinstance(tags, list):
            tags = [str(item).strip() for item in tags if str(item).strip()]
        else:
            tags = []
        fields["tags"] = tags
    for key in ("location", "vendor", "device_type"):
        if key in fields and fields[key] is not None:
            fields[key] = str(fields[key]).strip()

    devices = db.query(Device).filter(Device.id.in_(device_ids)).all()
    if len(devices) != len(device_ids):
        raise HTTPException(status_code=404, detail="部分设备不存在，请刷新列表后重试")
    for device in devices:
        asset_scope.require_device_access(db, request, device)

    now = datetime.utcnow()
    for device in devices:
        for key, value in fields.items():
            setattr(device, key, value)
        device.updated_at = now
    db.commit()
    invalidate_all()
    return {"updated": len(devices), "message": f"已批量修改 {len(devices)} 台设备"}


@router.post("/bulk-delete")
def bulk_delete_devices(
    request: Request,
    payload: dict = Body(..., description="{ids:[...]}"),
    db: Session = Depends(get_db),
):
    """批量删除设备（逐台校验群组权限，需要前端二次确认）"""
    ids = payload.get("ids") or []
    if not isinstance(ids, list) or not ids:
        raise HTTPException(status_code=400, detail="请选择要删除的设备")
    try:
        device_ids = list(dict.fromkeys(int(item) for item in ids))
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="设备 ID 列表格式不正确")

    devices = db.query(Device).filter(Device.id.in_(device_ids)).all()
    if len(devices) != len(device_ids):
        raise HTTPException(status_code=404, detail="部分设备不存在，请刷新列表后重试")
    for device in devices:
        asset_scope.require_device_access(db, request, device)

    for device in devices:
        _purge_device_records(db, device.id)
        db.delete(device)
    db.commit()
    invalidate_all()
    return {"deleted": len(devices), "message": f"已批量删除 {len(devices)} 台设备"}


@router.delete("/{device_id}")
def delete_device(device_id: int, request: Request, db: Session = Depends(get_db)):
    """删除设备（按群组校验；同时清理接口、指标、告警与拓扑连接）"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    asset_scope.require_device_access(db, request, device)

    _purge_device_records(db, device_id)
    db.delete(device)
    db.commit()
    invalidate_all()
    return {"message": "设备已删除"}


@router.put("/{device_id}/toggle")
def toggle_device(device_id: int, request: Request, db: Session = Depends(get_db)):
    """启用/禁用设备监控（按群组校验）"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    asset_scope.require_device_access(db, request, device)

    device.is_enabled = not device.is_enabled
    device.updated_at = datetime.utcnow()
    db.commit()
    invalidate_all()
    db.refresh(device)
    return device_to_dict(db, device)


TEMPERATURE_KIND_LABELS = {
    "cpu": "CPU 温度",
    "board": "主板温度",
    "inlet": "进风温度",
    "exhaust": "排风温度",
    "ambient": "环境温度",
    "other": "其他温度",
}


def _temperature_info(metric_data: Optional[dict]) -> Dict[str, Any]:
    if not metric_data:
        return {}
    custom = metric_data.get("custom") or {}
    components = metric_data.get("components") or custom.get("server_components") or {}
    sensor = custom.get("temperature_sensor") if isinstance(custom, dict) else None
    if not isinstance(sensor, dict):
        temps = components.get("temperatures") if isinstance(components, dict) else []
        if temps:
            hottest = max(temps, key=lambda item: float(item.get("value") or 0))
            sensor = {
                "name": hottest.get("name"),
                "kind": hottest.get("kind"),
                "unit": hottest.get("unit") or "°C",
                "value": hottest.get("value"),
            }
        else:
            sensor = {}
    kind = str(sensor.get("kind") or "other")
    name = str(sensor.get("name") or "").strip()
    value = metric_data.get("temperature")
    return {
        "value": value,
        "name": name,
        "kind": kind,
        "kind_label": TEMPERATURE_KIND_LABELS.get(kind, "温度传感器"),
        "label": "最高部件温度" if name else "设备最高温度",
        "unit": "°C",
        "source": "server_components" if name else "snmp",
    }


def _device_alert_rules(db: Session, device: Device, metric: Optional[DeviceMetric], offline: bool) -> List[dict]:
    """资产列表展示的规则摘要：指标、当前值、阈值、当前级别。"""
    rows = (
        db.query(DeviceAlertRule)
        .filter(DeviceAlertRule.device_id == device.id)
        .order_by(DeviceAlertRule.id.asc())
        .all()
    )
    metrics = metric_to_dict(metric) or {}
    result = []
    for rule in rows:
        value = alert_rule_service.metric_value(rule, metrics, offline=offline)
        triggered = bool(
            rule.enabled
            and value is not None
            and alert_rule_service.condition_matches(value, rule.operator or "gt", float(rule.threshold))
        )
        result.append({
            "id": rule.id,
            "name": rule.name,
            "metric": rule.metric,
            "metric_label": alert_rule_service.rule_metric_label(rule),
            "custom_key": rule.custom_key or "",
            "current_value": value,
            "unit": alert_rule_service.rule_unit(rule),
            "operator": rule.operator or "gt",
            "operator_text": alert_rule_service.OPERATORS.get(rule.operator or "gt", rule.operator or "gt"),
            "threshold": rule.threshold,
            "condition": alert_rule_service.condition_text(rule),
            "level": rule.level or "warning",
            "level_label": alert_rule_service.level_label(rule),
            "enabled": bool(rule.enabled),
            "triggered": triggered,
            "current_level": (rule.level or "warning") if triggered else None,
            "current_level_label": alert_rule_service.level_label(rule) if triggered else None,
            "source": "manual",
            "source_label": "自定义",
            "builtin": False,
        })

    return result


def _storage_api_configured(device: Device) -> bool:
    """存储设备是否已经配置过 API 对接字段。"""
    paths = device.api_paths if isinstance(device.api_paths, dict) else {}
    return bool(
        device.device_type == "storage"
        and (
            device.storage_username
            or device.storage_password_enc
            or str(device.api_auth_type or "auto").strip().lower() not in ("", "auto")
            or str(device.api_base_path or "").strip()
            or str(paths.get("login") or "").strip()
            or str(paths.get("metrics") or "").strip()
        )
    )


def _effective_monitor_type(device: Device) -> str:
    """兼容历史存储 API 设备：已配置 API 字段时按 API 对接展示。"""
    method = str(device.monitor_type or "snmp").strip().lower()
    if method not in ("api", "ipmi") and _storage_api_configured(device):
        return "api"
    return method if method in MONITOR_TYPES else "snmp"


def device_to_dict(db: Session, device: Device) -> dict:
    """设备对象转字典（附带最新指标与告警数）"""
    metric = (
        db.query(DeviceMetric)
        .filter(DeviceMetric.device_id == device.id)
        .order_by(DeviceMetric.collected_at.desc())
        .first()
    )

    mib_name = None
    if device.mib_id:
        mib = db.query(MibFile).filter(MibFile.id == device.mib_id).first()
        mib_name = mib.module_name if mib else None

    maintenance_count = (
        db.query(DeviceMaintenance)
        .filter(DeviceMaintenance.device_id == device.id)
        .count()
    )

    alert_count = (
        db.query(Alert)
        .filter(
            Alert.device_id == device.id,
            Alert.is_acknowledged == False,  # noqa: E712
            Alert.resolved_at.is_(None),
            Alert.is_hidden.isnot(True),
        )
        .count()
    )

    # 机柜 / 机房信息（用于列表与详情展示）
    cabinet_info = None
    if device.cabinet_id:
        cabinet = db.query(Cabinet).filter(Cabinet.id == device.cabinet_id).first()
        if cabinet:
            room = db.query(Room).filter(Room.id == cabinet.room_id).first()
            cabinet_info = {
                "id": cabinet.id,
                "name": cabinet.name,
                "room_id": cabinet.room_id,
                "room_name": room.name if room else None,
                "room_building": room.building if room else None,
                "room_floor": room.floor if room else None,
                "room_location": room.location if room else None,
                "u_capacity": cabinet.u_capacity,
                "power_capacity_w": cabinet.power_capacity_w,
            }

    group = db.query(Group).filter(Group.id == device.group_id).first() if device.group_id else None

    return {
        "id": device.id,
        "name": device.name,
        "ip_address": device.ip_address,
        "device_type": device.device_type,
        "monitor_type": _effective_monitor_type(device),
        "tcp_port": device.tcp_port or 80,
        "group_id": device.group_id,
        "group_name": group.name if group else None,
        "snmp_version": device.snmp_version,
        "community": device.community,
        "port": device.port,
        # 机柜上架与功率
        "cabinet_id": device.cabinet_id,
        "cabinet": cabinet_info,
        "u_position": device.u_position,
        "u_height": device.u_height or 1,
        "power_watts": device.power_watts or 0,
        # SNMPv3：不回传密码明文，仅告知是否已配置
        "v3_username": device.v3_username,
        "v3_security_level": device.v3_security_level,
        "v3_auth_protocol": device.v3_auth_protocol,
        "v3_priv_protocol": device.v3_priv_protocol,
        "v3_context_name": device.v3_context_name,
        "v3_auth_password_set": bool(device.v3_auth_password),
        "v3_priv_password_set": bool(device.v3_priv_password),
        "storage_username": device.storage_username,
        "storage_password_set": bool(device.storage_password_enc),
        "storage_api_port": device.storage_api_port or 443,
        "api_auth_type": device.api_auth_type or "auto",
        "api_base_path": device.api_base_path or "",
        "api_paths": device.api_paths or {},
        "ipmi_username": device.ipmi_username,
        "ipmi_password_set": bool(device.ipmi_password_enc),
        "ipmi_protocol": device.ipmi_protocol or "auto",
        "ipmi_port": device.ipmi_port or 623,
        "location": device.location,
        "vendor": device.vendor,
        "model": device.model,
        "serial_number": device.serial_number,
        "description": device.description,
        "is_enabled": device.is_enabled,
        "tags": device.tags or [],
        "source": device.source or "manual",
        "discovered_at": device.discovered_at.isoformat() if device.discovered_at else None,
        "icon": device.icon,
        # 维保 / 资产标签
        "asset_no": device.asset_no,
        "purchase_date": device.purchase_date,
        "warranty_start": device.warranty_start,
        "warranty_until": device.warranty_until,
        "maintenance_vendor": device.maintenance_vendor,
        "maintenance_contact": device.maintenance_contact,
        "maintenance_phone": device.maintenance_phone,
        "maintenance_count": maintenance_count,
        **_warranty_info(device),
        # MIB 采集优化
        "mib_id": device.mib_id,
        "mib_name": mib_name,
        "custom_oids": device.custom_oids or {},
        "custom_metrics": device.custom_metrics or [],
        "server_sensors": device.server_sensors or [],
        "created_at": device.created_at.isoformat() if device.created_at else None,
        "updated_at": device.updated_at.isoformat() if device.updated_at else None,
        "metric": metric_to_dict(metric) if metric else None,
        "is_online": bool(
            metric
            and metric.collected_at
            and (datetime.utcnow() - metric.collected_at) <= timedelta(minutes=10)
        ),
        "alert_rules": _device_alert_rules(
            db,
            device,
            metric,
            bool(
                db.query(Alert)
                .filter(
                    Alert.device_id == device.id,
                    Alert.alert_type == "offline",
                    Alert.resolved_at.is_(None),
                )
                .first()
            ),
        ),
        "alert_count": alert_count,
    }


def metric_to_dict(metric: Optional[DeviceMetric]) -> Optional[dict]:
    """指标对象转字典"""
    if not metric:
        return None
    return {
        "cpu_usage": metric.cpu_usage,
        "memory_usage": metric.memory_usage,
        "memory_total": metric.memory_total,
        "memory_used": metric.memory_used,
        "disk_usage": metric.disk_usage,
        "disk_total": metric.disk_total,
        "disk_used": metric.disk_used,
        "temperature": metric.temperature,
        "temperature_info": _temperature_info({
            "temperature": metric.temperature,
            "custom": metric.custom or {},
            "components": (metric.custom or {}).get("server_components") or {},
        }),
        "power_status": metric.power_status,
        "uptime": metric.uptime,
        "custom": metric.custom or {},
        "components": (metric.custom or {}).get("server_components") or {},
        "collected_at": metric.collected_at.isoformat() if metric.collected_at else None,
    }
