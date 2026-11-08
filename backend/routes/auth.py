"""认证路由 - 登录 / 当前用户 / 修改密码"""
import logging
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Security
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from ..config import Config
from ..models.database import get_db
from ..models.models import Device
from ..models.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    TotpCodeRequest,
    TotpDisableRequest,
)
from ..models.user import User
from ..services import license_manager
from ..services.auth import (
    create_token,
    get_current_user,
    hash_password,
    user_to_dict,
    verify_password,
)
from ..services import captcha as captcha_service
from ..services import settings as settings_service
from ..services import audit, password_policy, security
from ..services import totp as totp_service

router = APIRouter(prefix="/api/auth", tags=["认证"])
logger = logging.getLogger(__name__)


def _password_expiry_info(db: Session, user: User) -> dict:
    """返回当前用户的密码有效期和首次登录改密状态。"""
    days = int(settings_service.get_value(db, "password_expiry_days") or 0)
    first_login_enabled = bool(settings_service.get_value(db, "first_login_password_change"))
    must_change = first_login_enabled and bool(getattr(user, "must_change_password", False))
    changed = user.password_changed_at or user.created_at or datetime.utcnow()
    if days <= 0:
        return {
            "password_expiry_days": 0,
            "password_changed_at": changed.isoformat() if changed else None,
            "password_expires_at": None,
            "password_days_left": None,
            "password_change_required": must_change,
            "password_change_reason": "first_login" if must_change else None,
        }
    expires_at = changed + timedelta(days=days)
    remaining = (expires_at - datetime.utcnow()).total_seconds() / 86400
    expired = remaining <= 0
    reason = "first_login" if must_change else ("expired" if expired else None)
    return {
        "password_expiry_days": days,
        "password_changed_at": changed.isoformat() if changed else None,
        "password_expires_at": expires_at.isoformat(),
        "password_days_left": max(0, int(remaining)),
        "password_change_required": must_change or expired,
        "password_change_reason": reason,
    }


def _totp_policy(db: Session) -> str:
    value = str(settings_service.get_value(db, "totp_policy") or "off").strip().lower()
    return value if value in ("off", "all", "selected") else "off"


def _totp_required_for(db: Session, user: User) -> bool:
    policy = _totp_policy(db)
    if policy == "all":
        return True
    if policy != "selected":
        return False
    raw = str(settings_service.get_value(db, "totp_required_user_ids") or "")
    ids = {item.strip() for item in raw.split(",") if item.strip().isdigit()}
    return str(getattr(user, "id", "")) in ids


def _user_payload(db: Session, user: User) -> dict:
    data = user_to_dict(user)
    data.update(_password_expiry_info(db, user))
    data["totp_enabled"] = bool(user.totp_enabled and user.totp_secret)
    data["totp_required"] = _totp_required_for(db, user)
    return data


def _totp_issuer(db: Session) -> str:
    """otpauth 链接中的发行方名称：默认取系统名称，便于在身份验证器里识别。"""
    name = str(settings_service.get_value(db, "system_name") or "").strip() or "SNMP NMS"
    return name[:64]

# 仅用于在 OpenAPI/Swagger 中声明 Bearer 鉴权（实际校验在全局中间件）
bearer_scheme = HTTPBearer(auto_error=False)


@router.post("/login")
def login(payload: LoginRequest, request: Request, db: Session = Depends(get_db)):
    """账号密码登录，返回访问令牌与用户信息

    安全策略：连续失败达到阈值会临时锁定账号（可在系统配置里调整）。
    """
    username = (payload.username or "").strip()
    if not username or not payload.password:
        raise HTTPException(status_code=400, detail="请输入用户名和密码")

    # 商业授权到期后直接禁止登录；授权文件可由管理员在服务器侧替换后恢复
    license_status = license_manager.get_license_status(db.query(Device).count())
    if license_status.get("status") in ("expired", "invalid"):
        expires_at = (license_status.get("expires_at") or "").replace("T", " ")
        audit.record(
            db, request, module="security", action="login",
            target_type="user", target_name=username,
            status="failed", message="商业授权已到期，拒绝登录",
            operator=username,
        )
        raise HTTPException(
            status_code=403,
            detail=("商业授权无效或被篡改，系统禁止登录。请联系管理员更新授权文件。"
                    if license_status.get("status") == "invalid"
                    else f"商业授权已到期（{expires_at or '已过期'}），系统禁止登录。请联系管理员更新授权文件。"),
        )

    cfg = security.get_security_config(db)
    client = security.client_ip(request, bool(cfg.get("trust_proxy")))
    lock_enabled = bool(cfg.get("login_lock_enabled"))

    # 1) 账号锁定检查
    if lock_enabled:
        locked = security.get_lock(db, username)
        if locked:
            audit.record(
                db, request, module="security", action="login",
                target_type="user", target_name=username,
                status="failed", message="账号锁定期间尝试登录",
                operator=username,
            )
            raise HTTPException(
                status_code=429,
                detail=security.lock_message(locked["seconds_left"]),
            )

    # 2) 验证码开关由系统配置控制
    if settings_service.get_value(db, "captcha_enabled"):
        if not captcha_service.verify(
            payload.captcha_id or "", payload.captcha_code or ""
        ):
            raise HTTPException(status_code=400, detail="验证码错误或已过期，请刷新后重试")

    # 3) 账号密码校验
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(payload.password, user.password_hash):
        info = None
        if lock_enabled:
            info = security.register_failure(
                db, username, client,
                int(cfg.get("login_max_attempts") or 5),
                int(cfg.get("login_lock_minutes") or 15),
            )
            if info.get("locked_until"):
                audit.record(
                    db, request, module="security", action="login",
                    target_type="user", target_name=username,
                    status="failed",
                    message=f"连续登录失败 {info['fail_count']} 次，账号已锁定",
                    operator=username,
                )
                raise HTTPException(
                    status_code=429,
                    detail=security.lock_message(
                        int((info["locked_until"] - datetime.utcnow()).total_seconds())
                    ),
                )
        detail = "用户名或密码错误"
        if info and info.get("remaining_attempts") is not None:
            if info["remaining_attempts"] <= 3:
                detail += f"，还可尝试 {info['remaining_attempts']} 次"
        raise HTTPException(status_code=401, detail=detail)
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账号已被禁用，请联系管理员")

    # 3.5) 二次身份验证（TOTP）：密码正确后才要求，缺失/错误都不签发令牌
    if bool(user.totp_enabled):
        if not user.totp_secret:
            # 状态异常（启用但密钥丢失）时失败关闭，避免绕过二次验证
            audit.record(
                db, request, module="security", action="login",
                target_type="user", target_id=user.id, target_name=username,
                status="failed", message="二次身份验证配置异常：已启用但缺少密钥",
                operator=username, operator_id=user.id,
            )
            raise HTTPException(
                status_code=403,
                detail="该账号二次身份验证配置异常（缺少密钥），请联系管理员重置后再登录",
            )
        submitted_code = str(payload.totp_code or "")
        if not totp_service.verify_code(user.totp_secret, submitted_code):
            missing = not submitted_code.strip()
            audit.record(
                db, request, module="security", action="login",
                target_type="user", target_id=user.id, target_name=username,
                status="failed",
                message=(
                    "二次身份验证失败：未提交动态验证码"
                    if missing else "二次身份验证失败：动态验证码错误或已过期"
                ),
                operator=username, operator_id=user.id,
            )
            if missing:
                return JSONResponse(
                    status_code=401,
                    content={
                        "detail": "该账号已启用二次身份验证，请输入身份验证器中的 6 位动态验证码",
                        "code": "totp_required",
                        "totp_required": True,
                    },
                )
            return JSONResponse(
                status_code=401,
                content={
                    "detail": "动态验证码不正确或已过期，请重新输入",
                    "code": "totp_invalid",
                    "totp_required": True,
                },
            )

    # 4) 登录成功：清除失败计数并记录审计。
    # 这些是登录后的非关键写操作；SQLite 极端写锁冲突时记录告警，
    # 但不能因为清理失败而拒绝已经通过密码/二次验证的登录。
    try:
        if lock_enabled:
            security.clear_failures(db, username)
        # 兼容历史用户：首次登录时开始计算密码有效期，避免上线即被判过期；
        # 开启「首次登录必须修改密码」后，历史未登录账号也会被标记。
        if not user.password_changed_at:
            user.password_changed_at = datetime.utcnow()
        if (
            settings_service.get_value(db, "first_login_password_change")
            and user.last_login is None
        ):
            user.must_change_password = True
        user.last_login = datetime.utcnow()
        db.commit()
    except OperationalError as exc:
        db.rollback()
        logger.warning("登录状态写入失败，但密码验证已通过，继续登录: %s", exc)
    audit.record(
        db, request, module="security", action="login",
        target_type="user", target_id=user.id, target_name=username,
        status="success", message=f"登录成功（IP: {client or '-'}）",
        operator=username, operator_id=user.id,
    )

    return {
        "token": create_token(user),
        "token_type": "bearer",
        "expires_in_hours": Config.AUTH_TOKEN_HOURS,
        "user": _user_payload(db, user),
    }


@router.get("/me")
def get_me(
    _credentials: HTTPAuthorizationCredentials = Security(bearer_scheme),
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """当前登录用户信息（含权限点）"""
    return _user_payload(db, current)


@router.post("/change-password")
def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """修改自己的密码"""
    if not verify_password(payload.old_password, current.password_hash):
        raise HTTPException(status_code=400, detail="原密码不正确")
    if payload.old_password == payload.new_password:
        raise HTTPException(status_code=400, detail="新密码不能与原密码相同")

    password_policy.validate_password(db, payload.new_password)
    current.password_hash = hash_password(payload.new_password)
    current.password_changed_at = datetime.utcnow()
    current.must_change_password = False
    current.updated_at = datetime.utcnow()
    db.commit()
    audit.record(
        db, request, module="users", action="update",
        target_type="user", target_id=current.id, target_name=current.username,
        before={}, after={"password": "******"},
        message="用户修改了自己的密码",
        operator=current.username, operator_id=current.id,
    )
    return {"message": "密码修改成功", "user": _user_payload(db, current)}


# ==================== 二次身份验证（TOTP） ====================

def _totp_status(current: User, db: Session) -> dict:
    return {
        "enabled": bool(current.totp_enabled and current.totp_secret),
        "configured": bool(current.totp_secret),
        "required": _totp_required_for(db, current),
        "policy": _totp_policy(db),
        "account": current.username,
        "issuer": _totp_issuer(db),
        "algorithm": totp_service.ALGORITHM,
        "digits": totp_service.DIGITS,
        "period": totp_service.STEP,
        "window": totp_service.WINDOW,
        "apps": ["Google Authenticator", "Tencent Authenticator", "Microsoft Authenticator"],
    }


@router.get("/2fa/status")
def get_totp_status(
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """当前登录用户的二次身份验证状态"""
    return _totp_status(current, db)


@router.post("/2fa/setup")
def setup_totp(
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """生成 TOTP 密钥与二维码（仅当前用户，启用前可重复生成覆盖旧密钥）"""
    if bool(current.totp_enabled) and current.totp_secret:
        raise HTTPException(status_code=400, detail="二次身份验证已启用，如需更换密钥请先停用")

    secret = totp_service.generate_secret()
    issuer = _totp_issuer(db)
    try:
        payload = totp_service.setup_payload(secret, current.username, issuer)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    current.totp_secret = payload["secret"]
    current.totp_enabled = False
    current.updated_at = datetime.utcnow()
    db.commit()
    audit.record(
        db, request, module="security", action="update",
        target_type="user", target_id=current.id, target_name=current.username,
        after={"totp": "setup"},
        message="生成二次身份验证密钥，等待输入动态验证码确认启用",
        operator=current.username, operator_id=current.id,
    )
    return {
        **payload,
        "message": "请使用身份验证器扫描二维码或手动输入密钥，然后输入 6 位动态验证码完成启用",
        "status": _totp_status(current, db),
    }


@router.post("/2fa/enable")
def enable_totp(
    payload: TotpCodeRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """校验一次动态验证码后启用二次身份验证"""
    if not current.totp_secret:
        raise HTTPException(status_code=400, detail="请先生成二次身份验证密钥并扫码绑定")
    if bool(current.totp_enabled):
        return {"message": "二次身份验证已启用", "status": _totp_status(current, db)}
    if not totp_service.verify_code(current.totp_secret, payload.code):
        audit.record(
            db, request, module="security", action="update",
            target_type="user", target_id=current.id, target_name=current.username,
            status="failed", message="启用二次身份验证失败：动态验证码错误",
            operator=current.username, operator_id=current.id,
        )
        raise HTTPException(status_code=400, detail="动态验证码不正确或已过期，请确认身份验证器时间是否准确")

    current.totp_enabled = True
    current.updated_at = datetime.utcnow()
    db.commit()
    audit.record(
        db, request, module="security", action="update",
        target_type="user", target_id=current.id, target_name=current.username,
        after={"totp": "enabled"},
        message="已启用二次身份验证（TOTP）",
        operator=current.username, operator_id=current.id,
    )
    return {"message": "二次身份验证已启用，下次登录需要输入动态验证码", "status": _totp_status(current, db)}


@router.post("/2fa/disable")
def disable_totp(
    payload: TotpDisableRequest,
    request: Request,
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """停用二次身份验证（需当前密码 + 有效动态验证码）"""
    if _totp_required_for(db, current):
        raise HTTPException(status_code=400, detail="管理员已要求该账号开启二次验证，不能停用")
    if not current.totp_enabled and not current.totp_secret:
        raise HTTPException(status_code=400, detail="当前账号尚未启用二次身份验证")
    if not verify_password(payload.password or "", current.password_hash):
        raise HTTPException(status_code=400, detail="当前密码不正确")
    if current.totp_secret and not totp_service.verify_code(current.totp_secret, payload.code):
        audit.record(
            db, request, module="security", action="update",
            target_type="user", target_id=current.id, target_name=current.username,
            status="failed", message="停用二次身份验证失败：动态验证码错误",
            operator=current.username, operator_id=current.id,
        )
        raise HTTPException(status_code=400, detail="动态验证码不正确或已过期")

    current.totp_enabled = False
    current.totp_secret = None
    current.updated_at = datetime.utcnow()
    db.commit()
    audit.record(
        db, request, module="security", action="update",
        target_type="user", target_id=current.id, target_name=current.username,
        after={"totp": "disabled"},
        message="已停用二次身份验证（TOTP）",
        operator=current.username, operator_id=current.id,
    )
    return {"message": "二次身份验证已停用", "status": _totp_status(current, db)}
