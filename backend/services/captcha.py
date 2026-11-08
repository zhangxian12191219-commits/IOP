"""登录验证码：Pillow 生成 PNG，内存存储（一次性、2 分钟有效）

无 Pillow 时自动降级为 SVG 文本验证码（仍校验，但强度较低）。
"""
import base64
import io
import logging
import random
import secrets
import threading
import time
from typing import Dict, Optional, Tuple

from .cache import cache

logger = logging.getLogger(__name__)

# 去掉易混淆字符（0/O、1/I/l）
ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
CAPTCHA_TTL = 120          # 有效期（秒）
MAX_CAPTCHAS = 500         # 内存中最多保留数量

_store: Dict[str, Tuple[str, float]] = {}
_lock = threading.Lock()

_COLORS = [
    (30, 64, 120), (140, 40, 60), (20, 110, 80),
    (110, 60, 20), (70, 40, 130), (10, 90, 110),
]


def _cleanup(now: float) -> None:
    expired = [k for k, (_code, exp) in _store.items() if exp < now]
    for key in expired:
        _store.pop(key, None)
    # 超过上限时丢弃最早的一批
    if len(_store) > MAX_CAPTCHAS:
        for key in list(_store.keys())[: len(_store) - MAX_CAPTCHAS]:
            _store.pop(key, None)


def _new_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(4))


def _svg_captcha(code: str) -> str:
    """降级方案：SVG 文本验证码"""
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" width="130" height="44">',
        '<rect width="130" height="44" fill="#f5f7fa"/>',
    ]
    for i in range(6):
        parts.append(
            f'<line x1="{random.randint(0,130)}" y1="{random.randint(0,44)}" '
            f'x2="{random.randint(0,130)}" y2="{random.randint(0,44)}" '
            f'stroke="#c0c4cc" stroke-width="1"/>'
        )
    for i, ch in enumerate(code):
        x = 16 + i * 28 + random.randint(-3, 3)
        y = 32 + random.randint(-3, 3)
        angle = random.randint(-20, 20)
        color = _COLORS[i % len(_COLORS)]
        parts.append(
            f'<text x="{x}" y="{y}" font-family="monospace" font-size="28" '
            f'font-weight="bold" fill="rgb({color[0]},{color[1]},{color[2]})" '
            f'transform="rotate({angle} {x} {y})">{ch}</text>'
        )
    parts.append("</svg>")
    svg = "".join(parts)
    data = base64.b64encode(svg.encode("utf-8")).decode("ascii")
    return f"data:image/svg+xml;base64,{data}"


def _png_captcha(code: str) -> Optional[str]:
    """Pillow 生成带干扰的 PNG 验证码，返回 data URI"""
    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageFont
    except Exception:  # noqa: BLE001
        return None

    width, height = 130, 44
    image = Image.new("RGB", (width, height), (245, 247, 250))
    draw = ImageDraw.Draw(image)

    try:
        font = ImageFont.load_default(size=30)
    except TypeError:  # Pillow < 10.1
        font = ImageFont.load_default()

    # 干扰线
    for _ in range(7):
        draw.line(
            (
                random.randint(0, width),
                random.randint(0, height),
                random.randint(0, width),
                random.randint(0, height),
            ),
            fill=(random.randint(150, 210),) * 3,
            width=1,
        )

    # 逐字符旋转粘贴
    for index, char in enumerate(code):
        char_img = Image.new("RGBA", (44, 44), (0, 0, 0, 0))
        char_draw = ImageDraw.Draw(char_img)
        color = _COLORS[index % len(_COLORS)]
        char_draw.text((8, 2), char, font=font, fill=color)
        char_img = char_img.rotate(
            random.randint(-24, 24), resample=Image.BICUBIC, expand=False
        )
        image.paste(
            char_img,
            (10 + index * 29 + random.randint(-2, 2), random.randint(-3, 3)),
            char_img,
        )

    # 干扰点
    for _ in range(120):
        draw.point(
            (random.randint(0, width), random.randint(0, height)),
            fill=(random.randint(120, 200),) * 3,
        )

    image = image.filter(ImageFilter.SMOOTH)
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    data = base64.b64encode(buffer.getvalue()).decode("ascii")
    return f"data:image/png;base64,{data}"


def generate() -> Dict[str, object]:
    """生成验证码，返回 id 与图片（data URI）

    验证码存储在共享缓存（Redis 优先），多实例负载均衡下任意实例都可校验。
    """
    code = _new_code()
    captcha_id = secrets.token_urlsafe(16)
    now = time.time()

    if cache.enabled:
        cache.set(f"captcha:{captcha_id}", {"code": code, "exp": now + CAPTCHA_TTL},
                  CAPTCHA_TTL)
    else:
        with _lock:
            _cleanup(now)
            _store[captcha_id] = (code, now + CAPTCHA_TTL)

    image = _png_captcha(code) or _svg_captcha(code)
    return {
        "captcha_id": captcha_id,
        "image": image,
        "expires_in": CAPTCHA_TTL,
        "length": len(code),
    }


def verify(captcha_id: str, code: str) -> bool:
    """校验验证码（一次性，校验后立即失效）"""
    if not captcha_id or not code:
        return False

    if cache.enabled:
        key = f"captcha:{captcha_id}"
        item, hit = cache.get(key)
        cache.delete(key)
        if not hit or not isinstance(item, dict):
            return False
        if float(item.get("exp") or 0) < time.time():
            return False
        return str(item.get("code", "")).upper() == str(code).strip().upper()

    with _lock:
        item = _store.pop(captcha_id, None)
    if not item:
        return False
    expected, expire_at = item
    if expire_at < time.time():
        return False
    return expected.upper() == str(code).strip().upper()


def enabled(db) -> bool:
    """验证码是否启用（读取系统配置）"""
    try:
        from .settings import get_value

        return bool(get_value(db, "captcha_enabled"))
    except Exception:  # noqa: BLE001
        return True
