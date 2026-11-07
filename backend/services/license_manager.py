"""商业授权：Ed25519 签名授权文件、机器码绑定与资产数量限制。

私钥不随系统发布；授权文件只能由持有私钥的销售方生成。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import math
import os
import platform
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from fastapi import HTTPException

from ..config import Config

# 仅内置公钥；对应私钥由销售方离线保存，不进入安装包
PUBLIC_KEY_HEX = "2602be026250bd0d34c16d14a0342fc83fb20bc1be0a290dd2ef6ab392548ccf"
LICENSE_VERSION = 1
LICENSE_PLATFORM_VERSION = "2.10.0"

# 授权功能目录：销售方可按购买模块签发；旧授权没有 features 字段时默认全部功能，
# 保证升级兼容；新授权可通过 --features / 签发平台按模块下发。
FEATURE_CATALOG = {
    "assets": "资产管理与 SNMP 采集",
    "topology": "网络拓扑",
    "bigscreen": "大屏展示",
    "website": "网站监控（含 HTTPS 证书、批量导入与状态码）",
    "rooms": "机房管理与 3D 数字孪生",
    "im": "即时通信与音视频通话",
    "inspection": "设备巡检",
    "credentials": "设备凭据（巡检/备份共用）",
    "mib": "MIB 管理",
    "ai": "AI智能运维（对话、分析、报告与AI大屏）",
    "cascade": "总部分支级联（加密隧道、分支数据与级联通信）",
    "cluster": "集群与负载均衡",
    "network": "主机网络配置",
    "virtualization": "虚拟化管理（VMware / H3C CAS / KVM）",
    "tools": "系统工具",
    "alerts": "告警中心",
    "audit": "审计日志",
    "backup": "数据库与系统备份",
    "config_backup": "网络设备配置备份",
    "log_forward": "日志转发",
}
ALL_FEATURES = tuple(FEATURE_CATALOG.keys())

EDITION_LABELS = {
    "opensource": "开源版",
    "commercial": "商业版",
}
# 两档版本均提供全部功能，默认永久授权；资产额度分别为 50 / 100。
OPENSOURCE_FEATURES = tuple(FEATURE_CATALOG.keys())


def normalize_edition(value: Any) -> str:
    """只保留开源版/商业版；旧版授权中的标准版、试用版等统一归入商业版。"""
    text = str(value or "").strip().lower()
    return "opensource" if text == "opensource" else "commercial"


def edition_label(value: Any) -> str:
    return EDITION_LABELS.get(normalize_edition(value), "商业版")



class LicenseError(Exception):
    """授权文件校验失败。"""


class LicenseExpired(LicenseError):
    """授权已到期。"""


def _b64decode(value: str) -> bytes:
    padded = value + "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(padded.encode("ascii"))


def _b64encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def canonical_payload(payload: Dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _windows_machine_guid() -> str:
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography") as key:
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return str(value or "")
    except Exception:  # noqa: BLE001
        return ""


def _read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return ""


def _hardware_fingerprint() -> str:
    """稳定硬件指纹；明确排除 IP、主机名和 MAC，避免换网/升级失效。"""
    parts = [platform.system(), platform.machine()]
    if platform.system() == "Windows":
        parts.append(_windows_machine_guid())
    else:
        for path in (
            "/etc/machine-id",
            "/var/lib/dbus/machine-id",
            "/sys/class/dmi/id/product_uuid",
            "/sys/class/dmi/id/board_serial",
            "/sys/class/dmi/id/product_serial",
        ):
            value = _read_text(Path(path))
            if value and value.lower() not in ("none", "unknown", "to be filled by o.e.m."):
                parts.append(f"{path}:{value}")
        # 部分虚拟机没有 DMI 序列号，用系统盘序列号补充；仍不读取 IP/主机名/MAC。
        try:
            for disk in sorted(Path("/sys/block").glob("*"))[:4]:
                serial = _read_text(disk / "device" / "serial") or _read_text(disk / "serial")
                if serial:
                    parts.append(f"disk:{disk.name}:{serial}")
        except OSError:
            pass
    raw = "|".join(part for part in parts if part)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _binding_file() -> Path:
    return Path(Config.LICENSE_FILE).with_name("machine_binding.json")


def _binding_key() -> bytes:
    return hashlib.sha256((Config.AUTH_SECRET or "snmp-monitor-machine-binding-v2").encode("utf-8")).digest()


def _binding_payload(binding: Dict[str, Any]) -> bytes:
    return canonical_payload({
        "version": 2,
        "mode": binding.get("mode") or "",
        "machine_id": binding.get("machine_id") or "",
        "hardware_hash": binding.get("hardware_hash") or "",
        "nonce": binding.get("nonce") or "",
    })


def _binding_signature(binding: Dict[str, Any]) -> str:
    return hmac.new(_binding_key(), _binding_payload(binding), hashlib.sha256).hexdigest()


def _read_binding() -> Optional[Dict[str, Any]]:
    path = _binding_file()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict) or data.get("version") != 2:
            return {"invalid": True}
        if not hmac.compare_digest(str(data.get("signature") or ""), _binding_signature(data)):
            return {"invalid": True}
        return data
    except (OSError, ValueError, TypeError):
        return {"invalid": True}


def _write_binding(mode: str, machine_id: str, hardware_hash: str, nonce: str) -> str:
    data = {
        "version": 2,
        "mode": mode,
        "machine_id": (machine_id or "").lower(),
        "hardware_hash": hardware_hash,
        "nonce": nonce,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    data["signature"] = _binding_signature(data)
    path = _binding_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(temp, 0o600)
    except OSError:
        pass
    temp.replace(path)
    _write_machine_id(machine_id)
    return machine_id.lower()


def _new_hardware_binding(hardware_hash: str) -> str:
    nonce = uuid.uuid4().hex
    machine_id = hashlib.sha256(f"machine-v2|{hardware_hash}|{nonce}".encode("utf-8")).hexdigest()[:32]
    return _write_binding("hardware", machine_id, hardware_hash, nonce)


def _machine_id_file() -> Path:
    """机器码持久化文件与 license.key 同目录；升级时必须保留 data/。"""
    return Path(Config.LICENSE_FILE).with_name("machine_id")


def _write_machine_id(machine_id: str) -> str:
    path = _machine_id_file()
    value = (machine_id or "").strip().lower()
    if len(value) != 32 or any(ch not in "0123456789abcdef" for ch in value):
        raise ValueError("机器码格式不正确")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(".tmp")
        temp.write_text(value + "\n", encoding="utf-8")
        try:
            os.chmod(temp, 0o600)
        except OSError:
            pass
        temp.replace(path)
        return value
    except OSError:
        return value


def _read_machine_id_file() -> str:
    path = _machine_id_file()
    try:
        value = path.read_text(encoding="utf-8").strip().lower()
        if len(value) == 32 and all(ch in "0123456789abcdef" for ch in value):
            return value
    except OSError:
        pass
    return ""


def _decode_license_payload(token: str) -> Dict[str, Any]:
    """仅校验签名和版本，不校验机器码；用于继承旧授权的机器绑定。"""
    value = (token or "").strip().lstrip("\ufeff").strip()
    if not value:
        raise LicenseError("授权码为空")
    if value.startswith("NMS1-"):
        value = value[5:]
    if value.count(".") != 1:
        raise LicenseError("授权码格式不正确")
    payload_part, signature_part = value.split(".", 1)
    payload_bytes = _b64decode(payload_part)
    signature = _b64decode(signature_part)
    public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY_HEX))
    public_key.verify(signature, canonical_payload(json.loads(payload_bytes)))
    payload = json.loads(payload_bytes)
    if not isinstance(payload, dict) or int(payload.get("version") or 0) != LICENSE_VERSION:
        raise LicenseError("授权内容格式不正确")
    return payload


def get_machine_id() -> str:
    """返回绑定硬件的稳定机器码；旧版本机器码做一次性迁移。

    - 新安装：随机安装 ID + 硬件指纹 + 签名绑定，不再从 license.key 继承；
    - 旧版本：已有 data/machine_id 且授权匹配时迁移为绑定记录；
    - 复制账号目录到新硬件：绑定失效，机器码重新计算，授权无法验证。
    """
    hardware_hash = _hardware_fingerprint()
    binding = _read_binding()
    if binding and not binding.get("invalid"):
        if binding.get("hardware_hash") == hardware_hash:
            machine_id = str(binding.get("machine_id") or "").lower()
            if len(machine_id) == 32 and all(ch in "0123456789abcdef" for ch in machine_id):
                return machine_id
        # 绑定文件被复制到另一台硬件：不覆盖绑定，返回不同的硬件绑定值，
        # 这样原机器恢复后仍可继续使用原授权。
        return hashlib.sha256(f"machine-mismatch|{hardware_hash}".encode("utf-8")).hexdigest()[:32]
    if binding and binding.get("invalid"):
        # 绑定文件被篡改/签名失效：不信任旧 machine_id，重新绑定当前硬件。
        return _new_hardware_binding(hardware_hash)
    legacy = _read_machine_id_file()
    token = read_license_token()
    if legacy:
        inherited = ""
        if token:
            try:
                payload = _decode_license_payload(token)
                inherited = str(payload.get("machine_id") or "").replace("-", "").lower()
            except Exception:  # noqa: BLE001
                inherited = ""
        # 旧安装升级：machine_id 与现有签名授权一致时才迁移；
        # 新机器只有 license.key、没有 machine_id 的情况不会继承授权机器码。
        if len(legacy) == 32 and (not token or inherited == legacy):
            return _write_binding("legacy", legacy, hardware_hash, uuid.uuid4().hex)
    return _new_hardware_binding(hardware_hash)


def format_machine_code(machine_id: str) -> str:
    compact = (machine_id or "").replace("-", "").upper()
    return "-".join(compact[i:i + 4] for i in range(0, len(compact), 4))


def _license_path() -> Path:
    return Path(Config.LICENSE_FILE)


def _parse_expiry(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        text = str(value).strip().replace("Z", "+00:00")
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except (TypeError, ValueError) as exc:
        raise LicenseError("授权到期时间格式不正确") from exc


def verify_token(token: str, allow_expired: bool = False) -> Dict[str, Any]:
    value = (token or "").strip().lstrip("\ufeff").strip()
    if not value:
        raise LicenseError("授权码为空")
    if value.startswith("NMS1-"):
        value = value[5:]
    if value.count(".") != 1:
        raise LicenseError("授权码格式不正确")
    payload_part, signature_part = value.split(".", 1)
    try:
        payload_bytes = _b64decode(payload_part)
        signature = _b64decode(signature_part)
    except Exception as exc:  # noqa: BLE001
        raise LicenseError("授权码编码无效") from exc
    try:
        public_key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(PUBLIC_KEY_HEX))
        public_key.verify(signature, canonical_payload(json.loads(payload_bytes)))
    except (InvalidSignature, ValueError, json.JSONDecodeError) as exc:
        raise LicenseError("授权签名无效，文件可能已被篡改") from exc
    try:
        payload = json.loads(payload_bytes)
    except json.JSONDecodeError as exc:
        raise LicenseError("授权内容不是有效 JSON") from exc
    if not isinstance(payload, dict):
        raise LicenseError("授权内容格式不正确")
    if int(payload.get("version") or 0) != LICENSE_VERSION:
        raise LicenseError("授权版本不受支持")
    machine_id = str(payload.get("machine_id") or "").replace("-", "").lower()
    if machine_id != get_machine_id():
        raise LicenseError("授权码与当前机器不匹配")
    try:
        max_assets = int(payload.get("max_assets") or 0)
    except (TypeError, ValueError) as exc:
        raise LicenseError("授权资产数量无效") from exc
    if max_assets <= 0:
        raise LicenseError("授权资产数量必须大于 0")
    try:
        max_nodes = int(payload.get("max_nodes") or 1)
    except (TypeError, ValueError) as exc:
        raise LicenseError("授权集群节点数无效") from exc
    if max_nodes <= 0:
        raise LicenseError("授权集群节点数必须大于 0")
    raw_features = payload.get("features")
    if raw_features is None:
        # 兼容旧授权：未声明功能模块时视为全部当前功能
        features = list(ALL_FEATURES)
    elif isinstance(raw_features, list):
        features = [str(item).strip() for item in raw_features if str(item).strip() in FEATURE_CATALOG]
    else:
        raise LicenseError("授权功能列表格式不正确")
    expires_at = _parse_expiry(payload.get("expires_at"))
    now = datetime.now(timezone.utc)
    if expires_at and expires_at <= now and not allow_expired:
        raise LicenseExpired("授权已过期")
    return {
        "licensee": str(payload.get("licensee") or "未命名客户"),
        "machine_id": machine_id,
        "max_assets": max_assets,
        "max_nodes": max_nodes,
        "features": features,
        "issued_at": payload.get("issued_at"),
        "expires_at": expires_at.isoformat() if expires_at else None,
        "edition": normalize_edition(payload.get("edition")),
        "edition_label": edition_label(payload.get("edition")),
        "price": payload.get("price"),
        "price_text": str(payload.get("price_text") or ""),
        "duration_days": payload.get("duration_days"),
        "product_version": str(payload.get("product_version") or ""),
        "issued_by": str(payload.get("issued_by") or "智能运维服务平台授权签发平台"),
        "version": LICENSE_VERSION,
    }


def read_license_token() -> str:
    path = _license_path()
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8-sig").strip()
    except OSError:
        return ""


# 供每个已登录 API 请求快速判断授权是否到期；按授权文件 mtime 缓存，
# 但到期时间每次按当前时间重新比较，保证运行中跨过到期点也会立即生效。
_expiry_cache: Dict[str, Any] = {"mtime": None, "size": None, "expires_ts": None}


def _trial_path() -> Path:
    return Path(Config.LICENSE_TRIAL_START_FILE)


def _trial_period() -> tuple[datetime, datetime]:
    """返回内置试用的开始时间和到期时间；首次调用时写入试用开始时间。"""
    path = _trial_path()
    started: Optional[datetime] = None
    try:
        if path.exists():
            started = _parse_expiry(path.read_text(encoding="utf-8").strip())
    except (OSError, LicenseError):
        started = None
    if started is None:
        started = datetime.now(timezone.utc)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(started.isoformat(), encoding="utf-8")
        except OSError:
            # 文件不可写时至少保证当前进程内试用可用
            pass
    expires = started + timedelta(days=max(1, int(Config.LICENSE_TRIAL_DAYS)))
    return started, expires


_blocked_cache: Dict[str, Any] = {"mtime": None, "size": None, "blocked": False}


def is_blocked() -> bool:
    """商业授权被篡改/无效时一并阻断，避免 invalid 绕过 expired 检查。

    未放授权文件仍视为开源版，不阻断；只有存在但无法验证的授权才阻断。
    """
    token = read_license_token()
    if not token:
        return False
    path = _license_path()
    try:
        stat = path.stat()
    except OSError:
        return False
    if (
        _blocked_cache.get("mtime") == stat.st_mtime
        and _blocked_cache.get("size") == stat.st_size
    ):
        return bool(_blocked_cache.get("blocked"))
    blocked = False
    try:
        license_data = verify_token(token, allow_expired=True)
        expires_at = _parse_expiry(license_data.get("expires_at"))
        blocked = bool(expires_at and expires_at <= datetime.now(timezone.utc))
    except LicenseError:
        blocked = True
    except Exception:
        blocked = True
    _blocked_cache.update(mtime=stat.st_mtime, size=stat.st_size, blocked=blocked)
    return blocked


def is_expired() -> bool:
    """当前商业授权或内置试用是否已到期。"""
    now = datetime.now(timezone.utc)
    if not read_license_token():
        # 未激活商业授权时为永久开源版，不因时间到期
        return False

    path = _license_path()
    try:
        stat = path.stat()
    except OSError:
        _expiry_cache.update(mtime=None, size=None, expires_ts=None)
        return False
    if (
        _expiry_cache.get("mtime") == stat.st_mtime
        and _expiry_cache.get("size") == stat.st_size
    ):
        expires_ts = _expiry_cache.get("expires_ts")
        return bool(expires_ts is not None and expires_ts <= now.timestamp())
    expires_ts = None
    try:
        token = read_license_token()
        if token:
            license_data = verify_token(token, allow_expired=True)
            expires_at = _parse_expiry(license_data.get("expires_at"))
            expires_ts = expires_at.timestamp() if expires_at else None
    except LicenseError:
        expires_ts = None
    _expiry_cache.update(mtime=stat.st_mtime, size=stat.st_size, expires_ts=expires_ts)
    return bool(expires_ts is not None and expires_ts <= now.timestamp())


def _status_from_license(license_data: Dict[str, Any], asset_count: int) -> Dict[str, Any]:
    expires_at = license_data.get("expires_at")
    days_left = None
    if expires_at:
        expire_dt = _parse_expiry(expires_at)
        days_left = max(0, (expire_dt - datetime.now(timezone.utc)).days) if expire_dt else None
    max_assets = int(license_data["max_assets"])
    edition = normalize_edition(license_data.get("edition"))
    return {
        "status": "licensed",
        "licensed": True,
        "trial": False,
        "valid": True,
        "licensee": license_data["licensee"],
        "edition": edition,
        "edition_label": edition_label(edition),
        "max_assets": max_assets,
        "assets_used": asset_count,
        "assets_remaining": max(0, max_assets - asset_count),
        "over_limit": asset_count > max_assets,
        "max_nodes": int(license_data.get("max_nodes") or 1),
        "features": list(license_data.get("features") or []),
        "features_detail": [
            {"key": key, "name": FEATURE_CATALOG.get(key, key)}
            for key in (license_data.get("features") or [])
            if key in FEATURE_CATALOG
        ],
        "expires_at": expires_at,
        "days_left": days_left,
        "issued_at": license_data.get("issued_at"),
        "price": license_data.get("price"),
        "price_text": license_data.get("price_text") or "",
        "duration_days": license_data.get("duration_days"),
        "product_version": license_data.get("product_version") or "",
        "issued_by": license_data.get("issued_by") or "智能运维服务平台授权签发平台",
        "platform_version": LICENSE_PLATFORM_VERSION,
        "machine_id": get_machine_id(),
        "machine_code": format_machine_code(get_machine_id()),
        "message": "授权有效",
    }


def get_license_status(asset_count: int = 0) -> Dict[str, Any]:
    token = read_license_token()
    if not token:
        # 未激活商业授权时默认开源版：永久使用，50 台资产，全部功能可用。
        limit = max(1, int(getattr(Config, "LICENSE_OPENSOURCE_MAX_ASSETS", 50)))
        return {
            "status": "opensource",
            "licensed": False,
            "trial": False,
            "valid": True,
            "licensee": "开源版",
            "edition": "opensource",
            "edition_label": "开源版",
            "max_assets": limit,
            "assets_used": asset_count,
            "assets_remaining": max(0, limit - asset_count),
            "over_limit": asset_count > limit,
            "max_nodes": 1,
            "features": list(OPENSOURCE_FEATURES),
            "features_detail": [
                {"key": key, "name": FEATURE_CATALOG.get(key, key)}
                for key in OPENSOURCE_FEATURES
            ],
            "expires_at": None,
            "days_left": None,
            "issued_at": None,
            "price": 0,
            "price_text": "免费",
            "duration_days": None,
            "product_version": "",
            "issued_by": "开源版",
            "platform_version": LICENSE_PLATFORM_VERSION,
            "machine_id": get_machine_id(),
            "machine_code": format_machine_code(get_machine_id()),
            "message": "开源版永久使用，资产上限 50 台，全部功能可用。",
        }
    try:
        license_data = verify_token(token, allow_expired=True)
    except LicenseError as exc:
        return {
            "status": "invalid",
            "licensed": False,
            "trial": False,
            "valid": False,
            "licensee": "-",
            "edition": "-",
            "edition_label": "-",
            "max_assets": 0,
            "assets_used": asset_count,
            "assets_remaining": 0,
            "over_limit": asset_count > 0,
            "max_nodes": 0,
            "features": [],
            "features_detail": [],
            "expires_at": None,
            "days_left": None,
            "issued_at": None,
            "product_version": "",
            "issued_by": "-",
            "platform_version": LICENSE_PLATFORM_VERSION,
            "machine_id": get_machine_id(),
            "machine_code": format_machine_code(get_machine_id()),
            "message": f"授权无效：{exc}",
        }
    expires_at = _parse_expiry(license_data.get("expires_at"))
    if expires_at and expires_at <= datetime.now(timezone.utc):
        return {
            "status": "expired",
            "licensed": False,
            "trial": False,
            "valid": False,
            "licensee": license_data["licensee"],
            "edition": normalize_edition(license_data.get("edition")),
            "edition_label": edition_label(license_data.get("edition")),
            "max_assets": int(license_data["max_assets"]),
            "assets_used": asset_count,
            "assets_remaining": 0,
            "over_limit": True,
            "max_nodes": 0,
            "features": list(license_data.get("features") or []),
            "features_detail": [
                {"key": key, "name": FEATURE_CATALOG.get(key, key)}
                for key in (license_data.get("features") or []) if key in FEATURE_CATALOG
            ],
            "expires_at": license_data.get("expires_at"),
            "days_left": 0,
            "issued_at": license_data.get("issued_at"),
            "product_version": license_data.get("product_version") or "",
            "issued_by": license_data.get("issued_by") or "智能运维服务平台授权签发平台",
            "platform_version": LICENSE_PLATFORM_VERSION,
            "machine_id": get_machine_id(),
            "machine_code": format_machine_code(get_machine_id()),
            "message": "授权已到期。系统已禁止登录和管理界面访问，请更新授权文件后恢复。",
        }
    return _status_from_license(license_data, asset_count)


def activate_license(token: str) -> Dict[str, Any]:
    try:
        license_data = verify_token(token)
    except LicenseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    path = _license_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_suffix(".tmp")
    temp_path.write_text((token or "").strip(), encoding="utf-8")
    try:
        os.chmod(temp_path, 0o600)
    except OSError:
        pass
    temp_path.replace(path)
    _expiry_cache.update(mtime=None, size=None, expires_ts=None)
    _blocked_cache.update(mtime=None, size=None, blocked=False)
    return _status_from_license(license_data, 0)


def deactivate_license() -> None:
    path = _license_path()
    if path.exists():
        path.unlink()
    _expiry_cache.update(mtime=None, size=None, expires_ts=None)
    _blocked_cache.update(mtime=None, size=None, blocked=False)


def get_asset_limit() -> int:
    status = get_license_status()
    if status["status"] == "licensed":
        return int(status["max_assets"])
    if status["status"] == "opensource":
        return int(status["max_assets"])
    return 0


def has_feature(feature: str) -> bool:
    status = get_license_status()
    if str(feature) in (status.get("features") or []):
        return True
    # 2.5.0 之前签发的旧授权没有机房/即时通信模块，升级后默认兼容放行；
    # 新平台签发的授权会显式列出用户购买的模块。
    if feature in ("rooms", "im"):
        product_version = str(status.get("product_version") or "")
        if not product_version:
            return True
        try:
            parts = tuple(int(part) for part in product_version.split(".")[:3])
            return parts < (2, 5, 0)
        except (TypeError, ValueError):
            return True
    if feature == "inspection":
        product_version = str(status.get("product_version") or "")
        if not product_version:
            return True
        try:
            parts = tuple(int(part) for part in product_version.split(".")[:3])
            return parts < (2, 16, 26)
        except (TypeError, ValueError):
            return True
    return False


def check_feature(feature: str) -> None:
    """模块级授权校验；旧授权默认全部功能，因此不会误伤升级用户。"""
    status = get_license_status()
    if status.get("status") in ("expired", "invalid"):
        return  # 统一由授权到期中间件处理
    if feature not in (status.get("features") or []):
        raise HTTPException(
            status_code=403,
            detail=f"当前授权未包含「{FEATURE_CATALOG.get(feature, feature)}」功能，请联系销售方升级授权。",
        )


def check_asset_capacity(db, additional: int = 1) -> Dict[str, Any]:
    """创建资产前统一校验数量授权；不足时抛出 403。"""
    from ..models.models import Device

    used = db.query(Device).count()
    status = get_license_status(used)
    limit = int(status.get("max_assets") or 0)
    if status["status"] in ("expired", "invalid"):
        limit = 0
    if used + max(1, additional) > limit:
        if status["status"] == "opensource":
            reason = f"当前为开源版，资产上限为 {limit} 台（已使用 {used} 台）"
        elif status["status"] == "expired":
            reason = "商业授权已到期，无法继续新增资产"
        elif status["status"] == "invalid":
            reason = f"授权无效，无法继续新增资产：{status.get('message', '')}"
        else:
            reason = f"资产授权上限为 {limit} 台（已使用 {used} 台）"
        raise HTTPException(
            status_code=403,
            detail=f"{reason}，请续期/升级授权或删除不再使用的资产。",
        )
    return status
