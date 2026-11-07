"""品牌信息修改特权口令校验。

口令由授权签发平台使用同一 Ed25519 私钥签发，内容绑定产品机器码和短有效期。
产品端只持有公钥，无法自行生成口令。
"""
from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import Any, Dict

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from . import license_manager

PURPOSE = "branding_unlock"
MAX_CLOCK_SKEW_SECONDS = 300


class PrivilegeError(ValueError):
    pass


def _b64decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _parse_time(value: Any) -> datetime:
    text = str(value or "").strip().replace("Z", "+00:00")
    if not text:
        raise PrivilegeError("特权口令缺少有效期")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError as exc:
        raise PrivilegeError("特权口令有效期格式错误") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def verify_token(token: str) -> Dict[str, Any]:
    raw = str(token or "").strip()
    if not raw or "." not in raw:
        raise PrivilegeError("请输入授权签发平台生成的品牌特权口令")
    payload_part, signature_part = raw.split(".", 1)
    try:
        payload_bytes = _b64decode(payload_part)
        signature = _b64decode(signature_part)
        payload = json.loads(payload_bytes)
    except Exception as exc:  # noqa: BLE001
        raise PrivilegeError("特权口令格式不正确") from exc
    if not isinstance(payload, dict):
        raise PrivilegeError("特权口令内容不正确")
    if str(payload.get("purpose") or "") != PURPOSE:
        raise PrivilegeError("口令用途不正确，请使用「品牌特权口令」而不是授权码")
    machine = str(payload.get("machine_id") or "").replace("-", "").lower()
    current = license_manager.get_machine_id().replace("-", "").lower()
    if machine != current:
        raise PrivilegeError("该特权口令不是为本机机器码生成的")
    try:
        public_key = Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(license_manager.PUBLIC_KEY_HEX)
        )
        public_key.verify(signature, license_manager.canonical_payload(payload))
    except InvalidSignature as exc:
        raise PrivilegeError("特权口令签名无效") from exc
    expires_at = _parse_time(payload.get("expires_at"))
    now = datetime.now(timezone.utc)
    if expires_at <= now:
        raise PrivilegeError("特权口令已过期，请在授权签发平台重新生成")
    issued_at = payload.get("issued_at")
    if issued_at:
        issued = _parse_time(issued_at)
        if issued.timestamp() > now.timestamp() + MAX_CLOCK_SKEW_SECONDS:
            raise PrivilegeError("特权口令签发时间异常")
    return {
        "purpose": PURPOSE,
        "machine_id": machine,
        "issued_at": str(payload.get("issued_at") or ""),
        "expires_at": expires_at.isoformat(),
        "seconds_left": max(0, int((expires_at - now).total_seconds())),
    }
