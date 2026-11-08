"""资产标签二维码生成（Pillow + qrcode）"""
import base64
import io
import json
import logging
from typing import Any

logger = logging.getLogger("snmp-monitor.qrcode")

try:
    import qrcode
    from qrcode.constants import ERROR_CORRECT_M
    HAS_QRCODE = True
except Exception:  # noqa: BLE001
    HAS_QRCODE = False


def device_tag_payload(device, base_url: str) -> dict:
    """资产标签内容（JSON，便于扫码后识别资产）"""
    return {
        "type": "snmp-nms-device",
        "id": device.id,
        "name": device.name,
        "asset_no": device.asset_no or "",
        "ip": device.ip_address,
        "device_type": device.device_type,
        "location": device.location or "",
        "url": f"{base_url.rstrip('/')}/devices/{device.id}",
    }


def build_qr_png(content: str, box_size: int = 8, border: int = 2) -> bytes:
    """生成二维码 PNG 字节"""
    if not HAS_QRCODE:
        raise RuntimeError("未安装 qrcode 依赖，请执行 pip install -r backend/requirements.txt")
    qr = qrcode.QRCode(
        version=None,
        error_correction=ERROR_CORRECT_M,
        box_size=max(3, min(16, int(box_size))),
        border=max(1, min(8, int(border))),
    )
    qr.add_data(content)
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def device_qr(device, base_url: str, kind: str = "url") -> dict:
    """生成设备资产标签二维码（返回 base64 PNG 与内容）"""
    payload = device_tag_payload(device, base_url)
    if kind == "text":
        content = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    else:
        content = payload["url"]

    png = build_qr_png(content)
    return {
        "content": content,
        "kind": kind,
        "payload": payload,
        "png_base64": base64.b64encode(png).decode("ascii"),
        "size": len(png),
    }
