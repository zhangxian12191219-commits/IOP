"""虚拟化平台凭据加密。

使用 AUTH_SECRET 派生 Fernet 密钥，数据库中不保存明文密码。
"""
from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken

from ..config import Config, LEGACY_AUTH_SECRETS


def _fernet(secret: str | None = None) -> Fernet:
    raw = (secret if secret is not None else Config.AUTH_SECRET or "snmp-monitor").encode("utf-8")
    key = base64.urlsafe_b64encode(hashlib.sha256(raw).digest())
    return Fernet(key)


def encrypt_password(password: str) -> str:
    if not password:
        return ""
    return _fernet().encrypt(password.encode("utf-8")).decode("ascii")


def decrypt_password(token: str) -> str:
    if not token:
        return ""
    # 兼容旧版本以公开默认 AUTH_SECRET 加密的历史数据；新数据使用当前密钥。
    secrets_to_try = [Config.AUTH_SECRET, *LEGACY_AUTH_SECRETS]
    for secret in dict.fromkeys(secrets_to_try):
        try:
            return _fernet(secret).decrypt(token.encode("ascii")).decode("utf-8")
        except (InvalidToken, ValueError, TypeError):
            continue
    raise ValueError("平台密码无法解密，请重新填写密码")
