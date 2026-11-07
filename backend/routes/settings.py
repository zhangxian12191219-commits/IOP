"""系统配置接口：公开信息 / 读取更新配置 / 登录验证码 / 配置导入导出 / 安全状态"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from ..config import Config
from ..models.database import get_db
from ..services import captcha as captcha_service
from ..services import settings as settings_service
from ..services import audit as audit_service
from ..services import config_bundle
from ..services import security
from ..services import version_info as version_service
from ..services import runtime_config
from ..services import startup as startup_service
from ..services import privilege as privilege_service
from ..services import system_time
from ..services.cache import cache
from ..services import web_gateway as web_gateway_service
from ..certificates import manager as certificate_manager
from ..models.certificate import ManagedCertificate
from ..services.auth import get_current_user, has_permission
from ..models.user import User

router = APIRouter(prefix="/api/settings", tags=["系统配置"])
logger = logging.getLogger(__name__)

# ---- 告警声音文件 ----
SOUND_DIR = Path(Config.UPLOAD_DIR) / "sounds"
SOUND_EXTENSIONS = {".mp3", ".wav", ".ogg", ".m4a"}
SOUND_MAX_BYTES = 2 * 1024 * 1024
SOUND_BASENAME = "alert-custom"
ALERT_SOUND_LEVELS = ("info", "warning", "critical", "emergency")
ALERT_SOUND_LEVEL_KEYS = {level: f"alert_sound_file_{level}" for level in ALERT_SOUND_LEVELS}

# ---- 系统图标文件 ----
LOGO_DIR = Path(Config.UPLOAD_DIR) / "branding"
LOGO_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico"}
LOGO_MAX_BYTES = 2 * 1024 * 1024
LOGO_BASENAME = "system-logo"


def _logo_info(db: Session) -> Dict[str, Any]:
    url = str(settings_service.get_value(db, "system_logo") or "")
    path = None
    if url.startswith("/uploads/branding/"):
        filename = Path(url.split("?", 1)[0]).name
        candidate = LOGO_DIR / filename
        if candidate.is_file():
            path = candidate
    if not path:
        return {"custom": False, "url": "", "filename": "", "size": 0}
    stat = path.stat()
    return {
        "custom": True,
        "url": f"/uploads/branding/{path.name}?v={int(stat.st_mtime)}",
        "filename": path.name,
        "size": stat.st_size,
    }


def _remove_logo_files() -> None:
    if not LOGO_DIR.exists():
        return
    for path in LOGO_DIR.glob(f"{LOGO_BASENAME}.*"):
        try:
            path.unlink()
        except OSError:
            pass


@router.get("/logo")
def get_system_logo(db: Session = Depends(get_db)):
    """当前系统图标信息"""
    return _logo_info(db)


@router.post("/logo")
async def upload_system_logo(
    request: Request,
    file: UploadFile = File(..., description="PNG/JPG/WEBP/GIF/ICO，≤2MB"),
    db: Session = Depends(get_db),
):
    """上传系统图标，用于登录页、侧边栏和浏览器标签"""
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in LOGO_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail="图标格式不支持（可用 png / jpg / jpeg / webp / gif / ico）",
        )
    content = await file.read(LOGO_MAX_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="图标文件为空")
    if len(content) > LOGO_MAX_BYTES:
        raise HTTPException(status_code=413, detail="图标文件不能超过 2MB")

    LOGO_DIR.mkdir(parents=True, exist_ok=True)
    _remove_logo_files()
    filename = f"{LOGO_BASENAME}{suffix}"
    (LOGO_DIR / filename).write_bytes(content)
    url = f"/uploads/branding/{filename}?v={int((LOGO_DIR / filename).stat().st_mtime)}"
    settings_service.save(db, {"system_logo": url})
    audit_service.record(
        db, request, module="settings", action="update",
        target_type="system_logo", target_name=filename,
        after={"filename": filename, "size": len(content)},
        message=f"上传系统图标（{filename}，{len(content)} 字节）",
    )
    return _logo_info(db)


@router.delete("/logo")
def delete_system_logo(request: Request, db: Session = Depends(get_db)):
    """删除系统图标，恢复默认监控图标"""
    _remove_logo_files()
    settings_service.save(db, {"system_logo": ""})
    audit_service.record(
        db, request, module="settings", action="delete",
        target_type="system_logo", target_name="系统图标",
        message="恢复默认系统图标",
    )
    return _logo_info(db)



def _one_sound_info(db: Session, level: str) -> Dict[str, Any]:
    filename = str(settings_service.get_value(db, ALERT_SOUND_LEVEL_KEYS[level]) or "")
    # 兼容旧版单一自定义声音：默认作为紧急级别
    if not filename and level == "emergency":
        filename = str(settings_service.get_value(db, "alert_sound_file") or "")
    filename = Path(filename).name if filename else ""
    path = SOUND_DIR / filename if filename else None
    if not path or not path.is_file():
        return {
            "level": level,
            "custom": False,
            "filename": "",
            "url": "",
            "size": 0,
            "updated_at": None,
        }
    stat = path.stat()
    return {
        "level": level,
        "custom": True,
        "filename": filename,
        "url": f"/uploads/sounds/{filename}?v={int(stat.st_mtime)}",
        "size": stat.st_size,
        "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
    }


def _sound_info(db: Session) -> Dict[str, Any]:
    levels = {level: _one_sound_info(db, level) for level in ALERT_SOUND_LEVELS}
    emergency = levels["emergency"]
    # 兼容旧前端字段（旧上传接口默认对应紧急级别）
    return {
        **emergency,
        "levels": levels,
    }


def _remove_sound_files(level: Optional[str] = None) -> None:
    if not SOUND_DIR.exists():
        return
    levels = (level,) if level in ALERT_SOUND_LEVELS else ALERT_SOUND_LEVELS
    patterns = []
    for item_level in levels:
        patterns.append(f"{SOUND_BASENAME}-{item_level}.*")
    if not level or level == "emergency":
        patterns.append(f"{SOUND_BASENAME}.*")
    for pattern in patterns:
        for path in SOUND_DIR.glob(pattern):
            try:
                path.unlink()
            except OSError:
                pass


@router.get("/alert-sound")
def get_alert_sound(db: Session = Depends(get_db)):
    """分级告警声音信息（每个严重级别单独的自定义文件 / 内置提示音）"""
    return _sound_info(db)


@router.post("/alert-sound")
async def upload_alert_sound(
    request: Request,
    file: UploadFile = File(..., description="mp3/wav/ogg/m4a，≤2MB"),
    level: str = Query("emergency", description="info / warning / critical / emergency"),
    db: Session = Depends(get_db),
):
    """上传指定严重级别的自定义告警声音文件"""
    if level not in ALERT_SOUND_LEVELS:
        raise HTTPException(status_code=400, detail="告警级别不合法")
    suffix = Path(file.filename or "").suffix.lower()
    if suffix not in SOUND_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的声音格式：{suffix or '未知'}（可用 mp3 / wav / ogg / m4a）",
        )
    content = await file.read(SOUND_MAX_BYTES + 1)
    if not content:
        raise HTTPException(status_code=400, detail="声音文件为空")
    if len(content) > SOUND_MAX_BYTES:
        raise HTTPException(status_code=413, detail="声音文件不能超过 2MB")

    SOUND_DIR.mkdir(parents=True, exist_ok=True)
    _remove_sound_files(level)
    filename = f"{SOUND_BASENAME}-{level}{suffix}"
    (SOUND_DIR / filename).write_bytes(content)
    payload = {ALERT_SOUND_LEVEL_KEYS[level]: filename}
    if level == "emergency":
        payload["alert_sound_file"] = ""
    settings_service.save(db, payload)

    audit_service.record(
        db, request, module="settings", action="update",
        target_type="alert_sound", target_name=f"{level}:{filename}",
        after={"level": level, "filename": filename, "size": len(content)},
        message=f"上传 {level} 级别自定义告警声音（{filename}，{len(content)} 字节）",
    )
    return _sound_info(db)


@router.delete("/alert-sound")
def delete_alert_sound(
    request: Request,
    level: str = Query("emergency", description="info / warning / critical / emergency"),
    db: Session = Depends(get_db),
):
    """删除指定级别的自定义声音，恢复该级别的内置提示音"""
    if level not in ALERT_SOUND_LEVELS:
        raise HTTPException(status_code=400, detail="告警级别不合法")
    _remove_sound_files(level)
    payload = {ALERT_SOUND_LEVEL_KEYS[level]: ""}
    if level == "emergency":
        payload["alert_sound_file"] = ""
    settings_service.save(db, payload)
    audit_service.record(
        db, request, module="settings", action="delete",
        target_type="alert_sound", target_name=f"自定义告警声音:{level}",
        message=f"删除 {level} 级别自定义告警声音，恢复内置声音",
    )
    return _sound_info(db)


@router.delete("/alert-sound/all")
def reset_all_alert_sounds(
    request: Request,
    db: Session = Depends(get_db),
):
    """删除全部级别的自定义声音，恢复默认内置设备告警音。"""
    _remove_sound_files(None)
    payload = {key: "" for key in ALERT_SOUND_LEVEL_KEYS.values()}
    payload["alert_sound_file"] = ""
    settings_service.save(db, payload)
    audit_service.record(
        db, request, module="settings", action="delete",
        target_type="alert_sound", target_name="全部自定义告警声音",
        message="恢复全部级别默认内置设备告警音",
    )
    return _sound_info(db)


@router.get("/public")
def public_settings(response: Response, db: Session = Depends(get_db)):
    """公开配置（登录页/前端外壳使用，无需登录）"""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    data = settings_service.get_all(db, include_public_only=True)
    # 登录页只需要这些，避免暴露内部配置
    return data


@router.get("/version")
def get_version(response: Response, db: Session = Depends(get_db)):
    """当前生效版本（自动构建版本优先，手动版本兜底）"""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    return version_service.get_version_info(db)


@router.get("/captcha")
def get_captcha(response: Response, db: Session = Depends(get_db)):
    """获取登录验证码（图片 base64 + id，一次性有效 2 分钟）"""
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    enabled = settings_service.get_value(db, "captcha_enabled")
    if not enabled:
        return {"enabled": False, "captcha_id": None, "image": None}
    payload = captcha_service.generate()
    payload["enabled"] = True
    return payload


@router.get("")
def get_settings(db: Session = Depends(get_db)):
    """读取全部系统配置（需 settings:view 权限）"""
    return _settings_payload(db)


def _settings_payload(db: Session) -> Dict[str, Any]:
    """配置项 + 当前进程实际使用的数据库/缓存连接信息。

    页面里的外部数据库字段可能从未配置过，但后台已通过 DATABASE_URL 接入
    真实数据库；未单独配置外部库时，把运行库参数回填到对应字段，避免页面
    显示“未配置”。密码不回显。
    """
    settings = settings_service.get_all(db)
    # 传 db 以复用当前会话探测数据库连通性（Redis 由缓存服务探测），供“数据库与缓存”页显示实际状态
    runtime = runtime_config.snapshot(settings, db)

    external_configured = any(
        str(settings.get(key) or "").strip()
        for key in ("integration_host", "integration_database", "integration_username", "integration_sqlite_path")
    )
    if not external_configured and not bool(settings.get("integration_enabled")):
        defaults = runtime_config.integration_defaults(runtime["database"])
        if defaults:
            settings.update(defaults)
            runtime["database"]["auto_filled"] = True

    # Redis 地址在数据库里为空时，回退到环境变量 REDIS_URL。
    if not str(settings.get("redis_url") or "").strip() and str(Config.REDIS_URL or "").strip():
        settings["redis_url"] = str(Config.REDIS_URL).strip()
        settings["redis_enabled"] = True

    return {
        "settings": settings,
        "runtime": runtime,
        "defaults": {
            key: {"value": value[0], "description": value[2]}
            for key, value in settings_service.DEFAULTS.items()
        },
        "options": {
            "languages": list(settings_service.LANGUAGES),
            "timezones": list(settings_service.TIMEZONES),
            "ranges": settings_service.INT_RANGES,
        },
    }


@router.get("/web-access/status")
def web_access_status():
    """当前 HTTP/HTTPS 登录网关状态。"""
    return web_gateway_service.gateway.snapshot()


@router.get("/web-access/diagnose")
def diagnose_web_access(db: Session = Depends(get_db)):
    """登录网关、端口和 HTTPS 证书的诊断信息。"""
    values = settings_service.get_all(db)
    status = web_gateway_service.gateway.snapshot()
    hints = []
    cert_id = int(values.get("web_ssl_certificate_id") or 0)
    record = None
    if cert_id:
        record = db.query(ManagedCertificate).filter(ManagedCertificate.id == cert_id).first()
    else:
        record = (
            db.query(ManagedCertificate)
            .filter(ManagedCertificate.source == "acme")
            .order_by(ManagedCertificate.created_at.desc(), ManagedCertificate.id.desc())
            .first()
        )
    certificate = certificate_manager.serialize_certificate(record) if record else None
    self_signed = False
    if record:
        self_signed = bool(
            record.source == "generated"
            or (record.subject and record.issuer and record.subject.strip() == record.issuer.strip())
        )
    if not status.get("running"):
        hints.append("登录网关当前未运行，请确认端口未被占用，并点击「应用并启动网关」。")
        if status.get("error"):
            hints.append(f"网关错误：{status['error']}")
    if values.get("web_https_enabled"):
        if not record:
            hints.append("已启用 HTTPS，但没有可用证书。请选择证书或先申请免费证书。")
        elif self_signed:
            hints.append(
                "当前使用自签名证书，浏览器默认不信任，会显示证书警告或阻止访问。"
                "公网/远端访问请使用受信任 CA 证书；仅内网测试可手动信任证书。"
            )
        if record and record.valid_to and record.valid_to <= datetime.utcnow():
            hints.append("HTTPS 证书已过期，请续期或更换证书。")
        if record and record.san_json:
            hints.append("请确认浏览器访问的域名/IP 与证书 SAN 完全一致；IP 证书必须包含对应 IP SAN。")
    if values.get("web_http_enabled") and values.get("web_https_enabled"):
        if int(values.get("web_http_port") or 0) == int(values.get("web_https_port") or 0):
            hints.append("HTTP 与 HTTPS 端口不能相同。")
    if any(int(values.get(port_key) or 0) in (80, 443) for port_key in ("web_http_port", "web_https_port")):
        hints.append("绑定 80/443 需要 root 或 CAP_NET_BIND_SERVICE；若网关报权限错误，请调整服务权限或改用高位端口。")
    return {
        "status": status,
        "settings": {
            "web_http_enabled": bool(values.get("web_http_enabled")),
            "web_http_port": int(values.get("web_http_port") or 80),
            "web_https_enabled": bool(values.get("web_https_enabled")),
            "web_https_port": int(values.get("web_https_port") or 443),
            "web_https_redirect_http": bool(values.get("web_https_redirect_http", True)),
            "web_ssl_certificate_id": cert_id,
        },
        "certificate": certificate,
        "self_signed": self_signed,
        "direct_fallback": bool(status.get("direct_fallback")),
        "http_redirect": bool(status.get("http_redirect")),
        "hints": hints,
    }


@router.post("/web-access/apply")
async def apply_web_access(db: Session = Depends(get_db)):
    """按当前配置启动/重启 HTTP/HTTPS 登录网关。"""
    try:
        result = await web_gateway_service.gateway.apply_from_settings(db)
    except web_gateway_service.WebGatewayError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "Web 登录网关已更新", **result}


@router.post("/web-access/certificate")
async def upload_web_certificate(
    cert_file: UploadFile = File(...),
    key_file: UploadFile = File(...),
    chain_file: Optional[UploadFile] = File(None),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """上传自定义 Web 登录 HTTPS 证书，并自动设为 HTTPS 证书。"""
    try:
        cert_data = await cert_file.read()
        key_data = await key_file.read()
        chain_data = await chain_file.read() if chain_file else None
    finally:
        await cert_file.close()
        await key_file.close()
        if chain_file:
            await chain_file.close()
    if len(cert_data) > certificate_manager.MAX_CHAIN_BYTES:
        raise HTTPException(status_code=400, detail="证书文件过大")
    if len(key_data) > certificate_manager.MAX_PEM_BYTES:
        raise HTTPException(status_code=400, detail="私钥文件过大")
    if chain_data is not None and len(chain_data) > certificate_manager.MAX_CHAIN_BYTES:
        raise HTTPException(status_code=400, detail="证书链文件过大")
    try:
        record = certificate_manager.import_certificate(
            db,
            cert_data=cert_data,
            key_data=key_data,
            chain_data=chain_data,
            name="Web 登录 SSL 证书",
            monitor_host="",
            monitor_port=443,
            warning_days=30,
            notes="系统配置 → 登录与安全 → 自定义 HTTPS 证书",
            created_by=current.username,
            source="import",
        )
    except certificate_manager.CertificateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    settings_service.save(db, {"web_ssl_certificate_id": record.id})
    return {
        "message": "自定义 SSL 证书已上传并设为 HTTPS 登录证书",
        "certificate": certificate_manager.serialize_certificate(record),
    }


@router.get("/security-info")
def security_info(request: Request, db: Session = Depends(get_db)):
    """登录安全状态：当前 IP + 锁定/白名单配置（用于系统配置页展示）"""
    all_settings = settings_service.get_all(db)
    trust_proxy = bool(all_settings.get("trust_proxy"))
    current_ip = security.client_ip(request, trust_proxy)
    return {
        "current_ip": current_ip,
        "login_lock_enabled": bool(all_settings.get("login_lock_enabled")),
        "login_max_attempts": int(all_settings.get("login_max_attempts") or 5),
        "login_lock_minutes": int(all_settings.get("login_lock_minutes") or 15),
        "ip_whitelist_enabled": bool(all_settings.get("ip_whitelist_enabled")),
        "ip_whitelist": all_settings.get("ip_whitelist") or "",
        "trust_proxy": trust_proxy,
        "audit_retention_days": int(all_settings.get("audit_retention_days") or 0),
        "ip_whitelisted": security.ip_allowed(
            current_ip, all_settings.get("ip_whitelist") or ""
        ),
    }


@router.put("")
async def update_settings(
    request: Request,
    payload: Dict[str, Any] = Body(..., description="仅传需要修改的配置项"),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """更新系统配置（需 settings:edit 权限），返回最新配置。

    Web 登录协议/端口变化后会在同一个请求内自动切换登录网关；
    新配置启动失败会恢复旧配置和旧网关，避免把管理员锁在门外。
    """
    data = payload.get("settings") if isinstance(payload, dict) and "settings" in payload else payload
    if not isinstance(data, dict) or not data:
        raise HTTPException(status_code=400, detail="没有需要保存的配置项")
    data = dict(data)
    data.pop("privilege_token", None)
    cluster_keys = {
        "cluster_enabled", "cluster_name", "cluster_heartbeat_interval",
        "lb_enabled", "lb_strategy", "lb_public_url", "lb_sticky",
    }
    if any(key in data for key in cluster_keys):
        raise HTTPException(status_code=400, detail="集群与负载均衡配置请使用「系统配置 → 集群」保存")

    before_all = settings_service.get_all(db)
    copyright_keys = {"copyright_enabled", "copyright_name", "copyright_text", "copyright_color"}
    changed_copyright = {}
    for key in copyright_keys:
        if key not in data:
            continue
        old_value = before_all.get(key)
        new_value = data.get(key)
        if isinstance(old_value, bool) or isinstance(new_value, bool):
            same = bool(old_value) == bool(new_value)
        else:
            same = str(old_value if old_value is not None else "").strip() == str(new_value if new_value is not None else "").strip()
        if not same:
            changed_copyright[key] = new_value
    if changed_copyright:
        token = payload.get("privilege_token") if isinstance(payload, dict) else ""
        try:
            privilege_service.verify_token(str(token or ""))
        except privilege_service.PrivilegeError as exc:
            raise HTTPException(
                status_code=403,
                detail=f"修改版权信息需要授权签发平台生成的品牌特权口令：{exc}",
            ) from exc

    web_keys = {
        "web_protocol", "web_login_port", "web_http_enabled", "web_http_port",
        "web_https_enabled", "web_https_port", "web_https_redirect_http",
        "web_ssl_certificate_id",
    }
    web_payload = any(key in data for key in web_keys)
    if web_payload:
        data = dict(data)
        protocol = str(data.get("web_protocol") or before_all.get("web_protocol") or "http").strip().lower()
        if protocol not in ("http", "https"):
            raise HTTPException(status_code=400, detail="Web 登录协议只能是 HTTP 或 HTTPS")
        try:
            login_port = int(data.get("web_login_port") or before_all.get("web_login_port") or (443 if protocol == "https" else 80))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=400, detail="Web 登录端口必须是整数") from exc
        data["web_protocol"] = protocol
        data["web_login_port"] = login_port
        if protocol == "https":
            data["web_http_enabled"] = False
            data["web_https_enabled"] = True
            data["web_https_port"] = login_port
            data["web_https_redirect_http"] = True
            # 不再依赖人工上传：自动确保当前设备有一张 10 年有效证书
            try:
                record = certificate_manager.ensure_web_login_certificate(db, current.username)
            except certificate_manager.CertificateError as exc:
                raise HTTPException(status_code=400, detail=f"自动签发设备证书失败: {exc}") from exc
            data["web_ssl_certificate_id"] = record.id
        else:
            data["web_http_enabled"] = True
            data["web_https_enabled"] = False
            data["web_http_port"] = login_port
            data["web_https_redirect_http"] = False

    # HTTPS 登录开启后，HTTP 登录自动关闭；HTTP 端口只作为 308 跳转入口
    https_value = data.get("web_https_enabled")
    if https_value is True or str(https_value).lower() in ("1", "true", "yes", "on"):
        data["web_http_enabled"] = False

    normalized, errors = settings_service.validate(data)
    if errors:
        raise HTTPException(status_code=400, detail="；".join(errors))

    before = {key: before_all.get(key) for key in normalized}
    web_changed = any(
        key in normalized and normalized.get(key) != before_all.get(key)
        for key in web_keys
    )

    try:
        updated = settings_service.save(db, normalized)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    gateway_status = None
    if web_changed:
        try:
            gateway_status = await web_gateway_service.gateway.apply_from_settings(db, probe=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Web 登录网关自动切换失败，回滚旧配置: %s", exc)
            try:
                settings_service.save(db, {key: before_all.get(key) for key in web_keys if key in before_all})
                await web_gateway_service.gateway.apply_from_settings(db, probe=False)
            except Exception as rollback_exc:  # noqa: BLE001
                logger.error("Web 登录网关回滚失败: %s", rollback_exc)
            raise HTTPException(
                status_code=400,
                detail=f"登录协议/端口切换失败，已尝试恢复原配置: {exc}",
            ) from exc

    # 缓存参数保存后立即生效（Redis 不可用时由缓存服务自动回退内存）
    try:
        effective_redis_url = str(updated.get("redis_url") or "").strip() or str(Config.REDIS_URL or "").strip()
        cache.reconfigure(
            enabled=bool(updated.get("redis_enabled")),
            url=effective_redis_url,
            ttl_topology=int(updated.get("cache_ttl_topology") or 5),
            ttl_dashboard=int(updated.get("cache_ttl_dashboard") or 3),
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("应用缓存配置失败: %s", exc)

    # 记录配置变更审计
    audit_service.record(
        db, request, module="settings", action="update",
        target_type="system_settings", target_name="系统配置",
        before=before, after=normalized,
        message=f"修改了 {len(normalized)} 项配置",
    )

    payload = _settings_payload(db)
    return {
        "message": "系统配置已保存",
        "settings": payload["settings"],
        "runtime": payload["runtime"],
        "changed": normalized,
        "gateway": gateway_status or web_gateway_service.gateway.snapshot(),
    }


@router.post("/integration/test")
def test_integration_connection(db: Session = Depends(get_db)):
    """测试已保存的外部数据库连接（仅超管可调用）。"""
    from ..services import external_db

    values = settings_service.get_all(db)
    return external_db.test_connection(values)


@router.post("/redis/test")
def test_redis_connection(db: Session = Depends(get_db)):
    """测试已保存的 Redis 配置（仅超管可调用；未保存时回退环境变量）"""
    values = settings_service.get_all(db)
    url = str(values.get("redis_url") or "").strip() or str(Config.REDIS_URL or "").strip()
    return cache.test_connection(url)


@router.get("/export")
def export_settings(request: Request, db: Session = Depends(get_db)):
    """导出配置（系统配置 + 通知通道，敏感字段脱敏）"""
    bundle = config_bundle.export_config(db)
    audit_service.record(
        db, request, module="config", action="export",
        target_type="config", target_name="配置导出",
        message=f"导出系统配置与 {len(bundle.get('notification_channels') or [])} 个通知通道",
    )
    filename = f"snmp-nms-config-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    return Response(
        content=json.dumps(bundle, ensure_ascii=False, indent=2).encode("utf-8"),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/import")
async def import_settings(
    request: Request,
    file: UploadFile = File(..., description="导出的 JSON 配置文件"),
    dry_run: bool = Query(False, description="仅校验不落库"),
    privilege_token: str = Form(""),
    db: Session = Depends(get_db),
):
    """导入配置（需 settings:edit 权限），导入前自动备份当前配置"""
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="配置文件为空")
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="配置文件过大（限制 5MB）")

    try:
        data = json.loads(content.decode("utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise HTTPException(status_code=400, detail=f"JSON 解析失败：{exc}") from exc

    try:
        result = config_bundle.import_config(db, data, dry_run=dry_run, privilege_token=privilege_token)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if not dry_run:
        audit_service.record(
            db, request, module="config", action="import",
            target_type="config", target_name=file.filename or "配置导入",
            after={
                "settings_changed": result.get("settings_changed"),
                "channel_new": result.get("channel_new"),
                "channel_updated": result.get("channel_updated"),
            },
            message=(
                f"导入配置：修改 {result.get('settings_count')} 项，"
                f"新增通道 {result.get('channel_new')}，更新通道 {result.get('channel_updated')}"
            ),
        )

    result["filename"] = file.filename
    return result


# ==================== 系统时间 / NTP 设置 ====================
# 与「系统配置」保持一致的权限控制：仅超级管理员（且具备 settings 权限点）可操作。
time_router = APIRouter(prefix="/api/system/time", tags=["系统时间"])


def _time_admin(permission: str):
    """系统时间/时区属于主机级高危操作：仅超级管理员可执行"""

    def checker(current: User = Depends(get_current_user)) -> User:
        if not current.is_superuser or not has_permission(current, permission):
            raise HTTPException(status_code=403, detail="系统时间设置仅超级管理员可操作")
        return current

    return checker


def _time_payload(payload: Any) -> Dict[str, Any]:
    """兼容 {settings: {...}} 与扁平两种提交格式"""
    if isinstance(payload, dict) and isinstance(payload.get("settings"), dict):
        return payload["settings"]
    return payload if isinstance(payload, dict) else {}


def _as_bool(value: Any, default: Optional[bool] = None) -> Optional[bool]:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


@time_router.get("")
@time_router.get("/status")
def get_system_time_status(
    db: Session = Depends(get_db),
    current: User = Depends(_time_admin("settings:view")),
):
    """系统时间、时区/UTC 偏移、NTP 状态与服务器、平台信息"""
    return system_time.get_status(db)


@time_router.post("/configure")
def configure_system_time(
    request: Request,
    payload: Dict[str, Any] = Body(..., description="ntp_enabled / ntp_servers / timezone"),
    db: Session = Depends(get_db),
    current: User = Depends(_time_admin("settings:edit")),
):
    """保存并应用 NTP 开关、服务器列表与时区（命令失败时如实返回 ok=false）"""
    data = _time_payload(payload)
    before = system_time.get_ntp_config(db)
    try:
        result = system_time.configure(
            db,
            ntp_enabled=_as_bool(data.get("ntp_enabled")),
            ntp_servers=data.get("ntp_servers"),
            timezone_name=data.get("timezone"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    after = result.get("saved") or system_time.get_ntp_config(db)
    audit_service.record(
        db, request, module="settings", action="update",
        target_type="system_time", target_name="系统时间/NTP",
        before={
            "ntp_enabled": before.get("enabled"),
            "ntp_servers": before.get("servers"),
        },
        after={
            "ntp_enabled": after.get("enabled"),
            "ntp_servers": after.get("servers"),
            "timezone": data.get("timezone"),
            "applied": result.get("ok"),
        },
        status="success" if result.get("ok") else "failed",
        message=str(result.get("message") or "更新 NTP 设置"),
    )
    return result


@time_router.post("/sync")
def sync_system_time(
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(_time_admin("settings:edit")),
):
    """立即同步系统时间（Windows: w32tm /resync；Linux: chronyc/ntpdate/timesyncd）"""
    try:
        result = system_time.sync_now(db)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db, request, module="settings", action="update",
        target_type="system_time", target_name="立即同步时间",
        status="success" if result.get("ok") else "failed",
        message=str(result.get("message") or "立即同步系统时间"),
    )
    return result


@time_router.post("/set")
def set_system_clock(
    request: Request,
    payload: Dict[str, Any] = Body(..., description="datetime（YYYY-MM-DDTHH:MM[:SS]）/ timezone"),
    db: Session = Depends(get_db),
    current: User = Depends(_time_admin("settings:edit")),
):
    """手动设置系统时间（仅在用户明确操作时执行；Windows 使用 PowerShell Set-Date）"""
    data = _time_payload(payload)
    value = data.get("datetime") or data.get("time") or data.get("value")
    try:
        result = system_time.set_system_time(db, value, data.get("timezone"))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db, request, module="settings", action="update",
        target_type="system_time", target_name="手动设置系统时间",
        after={"requested": result.get("requested")},
        status="success" if result.get("ok") else "failed",
        message=str(result.get("message") or "手动设置系统时间"),
    )
    return result

@router.get("/startup")
def get_startup_status(current: User = Depends(get_current_user)):
    """查询系统开机自启状态（systemd / Windows 启动项）。"""
    if not current.is_superuser and not has_permission(current, "settings:view"):
        raise HTTPException(status_code=403, detail="没有查看系统开机自启的权限")
    return startup_service.get_status()


@router.put("/startup")
def set_startup_status(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current: User = Depends(_time_admin("settings:edit")),
):
    """启用或停用系统开机自启；不会启动/停止当前服务。"""
    data = payload.get("settings") if isinstance(payload, dict) and isinstance(payload.get("settings"), dict) else payload
    enabled = bool((data or {}).get("enabled"))
    try:
        status = startup_service.set_enabled(enabled)
    except ValueError as exc:
        audit_service.record(
            db, request, module="settings", action="update",
            target_type="startup", target_name="开机自启",
            status="failed", message=str(exc),
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    audit_service.record(
        db, request, module="settings", action="update",
        target_type="startup", target_name="开机自启",
        after={"enabled": status.get("enabled"), "mode": status.get("mode"), "service": status.get("service")},
        message=("启用系统开机自启" if enabled else "停用系统开机自启"),
    )
    return status

