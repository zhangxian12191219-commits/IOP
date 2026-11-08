"""商业授权信息与激活接口"""
from typing import Any, Dict

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..models.models import Device
from ..models.user import User
from ..services import auth as auth_service
from ..services import audit as audit_service
from ..services import license_manager
from ..services import privilege as privilege_service
from ..services import settings as settings_service

router = APIRouter(prefix="/api/license", tags=["商业授权"])


class LicenseActivatePayload(BaseModel):
    token: str = Field(..., min_length=20, max_length=20000)


def _current_user(current: User = Depends(auth_service.get_current_user)) -> User:
    return current


def _require(current: User) -> None:
    if not current.is_superuser:
        raise HTTPException(status_code=403, detail="商业授权仅超级管理员可查看和操作")


def _status(db: Session) -> dict:
    count = db.query(Device).count()
    return license_manager.get_license_status(count)


@router.get("/public-status")
def public_license_status(db: Session = Depends(get_db)):
    """登录页使用的授权状态；授权到期时附带机器码用于申请续期。"""
    status = _status(db)
    data = {
        "status": status.get("status"),
        "valid": status.get("valid"),
        "trial": status.get("trial"),
        "licensed": status.get("licensed"),
        "licensee": status.get("licensee"),
        "edition": status.get("edition"),
        "expires_at": status.get("expires_at"),
        "days_left": status.get("days_left"),
        "max_assets": status.get("max_assets"),
        "assets_used": status.get("assets_used"),
        "edition_label": status.get("edition_label"),
        "features": status.get("features") or [],
        "price": status.get("price"),
        "price_text": status.get("price_text") or "",
        "duration_days": status.get("duration_days"),
        "message": status.get("message"),
    }
    # 到期后登录页需要展示机器码，便于向销售方申请续期授权；
    # 有效授权/试用状态下仍不暴露机器码。
    if status.get("status") == "expired":
        data["machine_code"] = status.get("machine_code")
    return data


@router.post("/activate-public")
def activate_license_public(
    payload: LicenseActivatePayload,
    request: Request,
    db: Session = Depends(get_db),
):
    """授权到期后，在登录页免登录更换授权。

    只允许当前授权已经到期时使用；新授权仍必须通过 Ed25519 签名、
    机器码绑定和有效期校验，不能通过该接口绕过授权。
    """
    current = _status(db)
    if current.get("status") != "expired":
        raise HTTPException(
            status_code=403,
            detail="当前授权尚未到期，请登录后在「授权信息」中更新授权。",
        )
    try:
        status = license_manager.activate_license(payload.token)
        settings_service.apply_license_copyright(db, force=True)
        db.commit()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"授权更新失败: {exc}") from exc
    audit_service.record(
        db,
        request,
        module="license",
        action="update",
        target_type="license",
        target_name=status.get("licensee") or "license",
        status="success",
        message="登录页上传到期续期授权",
        operator="login-renewal",
    )
    return status


@router.get("")
def license_info(db: Session = Depends(get_db), current: User = Depends(_current_user)):
    _require(current)
    return _status(db)


@router.post("/activate")
def activate_license(
    payload: LicenseActivatePayload,
    db: Session = Depends(get_db),
    current: User = Depends(_current_user),
):
    _require(current)
    license_manager.activate_license(payload.token)
    settings_service.apply_license_copyright(db, force=True)
    db.commit()
    return _status(db)


@router.delete("")
def deactivate_license(db: Session = Depends(get_db), current: User = Depends(_current_user)):
    _require(current)
    license_manager.deactivate_license()
    settings_service.apply_license_copyright(db, force=True)
    db.commit()
    return _status(db)

@router.post("/privilege/verify")
def verify_privilege(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current: User = Depends(_current_user),
):
    """验证品牌信息修改特权口令（绑定机器码、短有效期）。"""
    _require(current)
    try:
        info = privilege_service.verify_token(str(payload.get("token") or ""))
    except privilege_service.PrivilegeError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    audit_service.record(
        db, request, module="license", action="verify",
        target_type="branding_privilege", target_name="品牌特权口令",
        message=f"验证品牌修改特权口令，剩余 {info['seconds_left']} 秒",
        operator=current.username,
    )
    return {"ok": True, **info}

