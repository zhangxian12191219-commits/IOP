"""TOTP 二次身份验证服务（RFC 6238，纯标准库实现）

- 算法：HMAC-SHA1、6 位数字、30 秒步长
- 兼容 Google Authenticator / Microsoft Authenticator / 腾讯身份验证器 等标准 TOTP 应用
- 校验允许前后各 1 个时间窗口（共 ±30 秒时钟偏差）
- 不引入新依赖：Base32 密钥、otpauth:// 链接均用标准库生成；
  二维码优先使用项目已有的 qrcode + Pillow，缺少 Pillow 时回退为纯标准库 PNG 编码
"""
import base64
import binascii
import hashlib
import hmac
import io
import logging
import re
import secrets
import struct
import time
import zlib
from typing import Any, Dict, Optional
from urllib.parse import quote, urlencode

logger = logging.getLogger(__name__)

# TOTP 标准参数（Google / 腾讯等身份验证器通用）
DIGITS = 6
STEP = 30
WINDOW = 1
ALGORITHM = "SHA1"
SECRET_BYTES = 20          # 160 bit，Base32 后 32 个字符
MIN_SECRET_LENGTH = 16
MAX_SECRET_LENGTH = 128
ISSUER_MAX_LENGTH = 64

_BASE32_ALPHABET = set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")
_SPACE_RE = re.compile(r"[\s\-]+")


# ==================== 密钥 ====================

def generate_secret(length: int = SECRET_BYTES) -> str:
    """生成新的 Base32 密钥（默认 160 bit，可被所有标准身份验证器识别）"""
    size = max(10, min(64, int(length or SECRET_BYTES)))
    return base64.b32encode(secrets.token_bytes(size)).decode("ascii").rstrip("=")


def normalize_secret(secret: Any) -> str:
    """规范化用户输入的密钥：去空格/短横线、转大写、去掉填充符。

    非法密钥抛 ValueError，便于接口层返回明确提示而不是 500。
    """
    text = _SPACE_RE.sub("", str(secret or "")).upper().rstrip("=")
    if not text:
        raise ValueError("TOTP 密钥为空")
    if len(text) < MIN_SECRET_LENGTH or len(text) > MAX_SECRET_LENGTH:
        raise ValueError("TOTP 密钥长度不合法")
    if any(char not in _BASE32_ALPHABET for char in text):
        raise ValueError("TOTP 密钥不是合法的 Base32 字符串")
    return text


def _decode_secret(secret: Any) -> bytes:
    text = normalize_secret(secret)
    padding = "=" * ((8 - len(text) % 8) % 8)
    try:
        return base64.b32decode(text + padding, casefold=True)
    except (binascii.Error, ValueError) as exc:  # pragma: no cover - 已被 normalize 拦截
        raise ValueError("TOTP 密钥解码失败") from exc


# ==================== 算法 ====================

def hotp(secret: Any, counter: int, digits: int = DIGITS) -> str:
    """RFC 4226 HOTP：HMAC-SHA1 动态截断"""
    key = _decode_secret(secret)
    counter = int(counter)
    if counter < 0:
        counter = 0
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    code = int.from_bytes(digest[offset:offset + 4], "big") & 0x7FFFFFFF
    return str(code % (10 ** int(digits))).zfill(int(digits))


def totp(secret: Any, at: Optional[float] = None, step: int = STEP, digits: int = DIGITS) -> str:
    """RFC 6238 TOTP：按时间窗口生成动态验证码"""
    timestamp = int(time.time() if at is None else at)
    return hotp(secret, timestamp // max(1, int(step)), digits)


def verify_code(
    secret: Any,
    code: Any,
    window: int = WINDOW,
    at: Optional[float] = None,
    step: int = STEP,
    digits: int = DIGITS,
) -> bool:
    """校验动态验证码，允许 window 个前后时间窗口（默认 ±1，即 ±30 秒）"""
    text = _SPACE_RE.sub("", str(code or ""))
    if not text or not text.isdigit() or len(text) != digits:
        return False
    if not str(secret or "").strip():
        return False
    try:
        key = _decode_secret(secret)
    except ValueError:
        return False

    timestamp = int(time.time() if at is None else at)
    counter = timestamp // max(1, int(step))
    for offset in range(-int(window), int(window) + 1):
        candidate_counter = counter + offset
        if candidate_counter < 0:
            continue
        digest = hmac.new(
            key, struct.pack(">Q", candidate_counter), hashlib.sha1
        ).digest()
        index = digest[-1] & 0x0F
        candidate = int.from_bytes(digest[index:index + 4], "big") & 0x7FFFFFFF
        expected = str(candidate % (10 ** digits)).zfill(digits)
        if hmac.compare_digest(expected, text):
            return True
    return False


# ==================== otpauth URI ====================

def _safe_issuer(issuer: Any) -> str:
    text = str(issuer or "").strip() or "SNMP NMS"
    return text[:ISSUER_MAX_LENGTH]


def provisioning_uri(secret: Any, account: Any, issuer: Any = "SNMP NMS") -> str:
    """生成标准 otpauth://totp 链接（Google/腾讯身份验证器均可扫码或手动输入）"""
    key = normalize_secret(secret) if secret else ""
    name = str(account or "").strip() or "user"
    label = f"{_safe_issuer(issuer)}:{name}"
    params = urlencode(
        {
            "secret": key,
            "issuer": _safe_issuer(issuer),
            "algorithm": ALGORITHM,
            "digits": DIGITS,
            "period": STEP,
        },
        quote_via=quote,
    )
    return f"otpauth://totp/{quote(label, safe='')}?{params}"


# ==================== 二维码 ====================

def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def _matrix_to_png(matrix, scale: int = 8) -> bytes:
    """把二维码矩阵编码为 8bit 灰度 PNG（纯标准库，无需 Pillow）"""
    rows = len(matrix)
    cols = len(matrix[0]) if rows else 0
    if not rows or not cols:
        raise ValueError("二维码矩阵为空")
    scale = max(2, min(16, int(scale)))
    raw = bytearray()
    for row in matrix:
        line = bytearray([0])  # PNG 过滤类型 0
        for value in row:
            pixel = 0 if value else 255
            line.extend(bytes([pixel]) * scale)
        for _ in range(scale):
            raw.extend(line)
    header = struct.pack(">IIBBBBB", cols * scale, rows * scale, 8, 0, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + _png_chunk(b"IEND", b"")
    )


def qr_png(content: str, box_size: int = 8, border: int = 2) -> Optional[bytes]:
    """生成二维码 PNG 字节；缺少 qrcode 依赖时返回 None（不影响密钥与链接返回）"""
    try:
        import qrcode
        from qrcode.constants import ERROR_CORRECT_M
    except Exception as exc:  # noqa: BLE001
        logger.warning("二维码生成不可用（缺少 qrcode 依赖）: %s", exc)
        return None

    box = max(3, min(16, int(box_size)))
    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=ERROR_CORRECT_M,
            box_size=box,
            border=max(1, min(8, int(border))),
        )
        qr.add_data(content)
        qr.make(fit=True)
    except Exception as exc:  # noqa: BLE001
        logger.warning("二维码矩阵生成失败: %s", exc)
        return None

    # 优先使用 Pillow 渲染（项目已有依赖），失败时回退纯标准库编码
    try:
        image = qr.make_image(fill_color="black", back_color="white")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        data = buffer.getvalue()
        if data:
            return data
    except Exception as exc:  # noqa: BLE001
        logger.debug("Pillow 渲染二维码失败，改用内置编码: %s", exc)

    try:
        return _matrix_to_png(qr.get_matrix(), scale=box)
    except Exception as exc:  # noqa: BLE001
        logger.warning("二维码 PNG 编码失败: %s", exc)
        return None


def qr_data_url(content: str, box_size: int = 8, border: int = 2) -> Optional[str]:
    """二维码 data URL（前端可直接 <img src> 显示）"""
    png = qr_png(content, box_size=box_size, border=border)
    if not png:
        return None
    return "data:image/png;base64," + base64.b64encode(png).decode("ascii")


def setup_payload(secret: str, account: str, issuer: str) -> Dict[str, Any]:
    """二次验证初始化数据：密钥 + otpauth 链接 + 二维码 data URL"""
    uri = provisioning_uri(secret, account, issuer)
    return {
        "secret": normalize_secret(secret),
        "otpauth_uri": uri,
        "qr_code": qr_data_url(uri),
        "issuer": _safe_issuer(issuer),
        "account": str(account or ""),
        "algorithm": ALGORITHM,
        "digits": DIGITS,
        "period": STEP,
    }
