"""密码复杂度策略

配置项由「系统配置 → 登录与安全」维护，所有创建用户、重置密码、
修改自己密码的入口统一调用本服务校验。
"""
import re

from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import settings as settings_service


def get_policy(db: Session) -> dict:
    return {
        "min_length": int(settings_service.get_value(db, "password_min_length") or 8),
        "require_uppercase": bool(settings_service.get_value(db, "password_require_uppercase")),
        "require_lowercase": bool(settings_service.get_value(db, "password_require_lowercase")),
        "require_digit": bool(settings_service.get_value(db, "password_require_digit")),
        "require_special": bool(settings_service.get_value(db, "password_require_special")),
    }


def describe_policy(db: Session) -> str:
    policy = get_policy(db)
    parts = [f"至少 {policy['min_length']} 位"]
    if policy["require_uppercase"]:
        parts.append("包含大写字母")
    if policy["require_lowercase"]:
        parts.append("包含小写字母")
    if policy["require_digit"]:
        parts.append("包含数字")
    if policy["require_special"]:
        parts.append("包含特殊字符")
    return "密码需" + "、".join(parts)


def validate_password(db: Session, password: str) -> None:
    """校验密码复杂度；不符合时抛出 400，detail 可直接展示给用户"""
    policy = get_policy(db)
    password = password or ""
    if len(password) < policy["min_length"]:
        raise HTTPException(
            status_code=400,
            detail=f"密码长度至少 {policy['min_length']} 位",
        )
    if policy["require_uppercase"] and not any(ch.isupper() for ch in password):
        raise HTTPException(status_code=400, detail="密码必须包含大写字母")
    if policy["require_lowercase"] and not any(ch.islower() for ch in password):
        raise HTTPException(status_code=400, detail="密码必须包含小写字母")
    if policy["require_digit"] and not any(ch.isdigit() for ch in password):
        raise HTTPException(status_code=400, detail="密码必须包含数字")
    if policy["require_special"] and not re.search(r"[^A-Za-z0-9]", password):
        raise HTTPException(status_code=400, detail="密码必须包含特殊字符")
