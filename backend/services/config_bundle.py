"""配置项导入导出：系统配置 + 通知通道

- 导出为 JSON（敏感字段脱敏）
- 导入前自动备份当前配置到 data/backups/
- 导入只覆盖导出包中出现的配置项，不删除其它配置
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..config import Config
from ..models.notifications import NotificationChannel
from . import settings as settings_service
from . import privilege as privilege_service
from .audit import mask_sensitive

logger = logging.getLogger(__name__)

FORMAT_NAME = "snmp-monitor-config"
FORMAT_VERSION = 1
MASK = "******"

# 通知通道中需要脱敏的配置字段
_CHANNEL_SECRET_KEYS = (
    "password", "smtp_password", "token", "secret", "webhook_url",
    "app_secret", "sign", "key", "sms_key",
)


def _backup_dir() -> Path:
    directory = Path(Config.LOG_DIR).parent / "backups"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _is_masked(value: Any) -> bool:
    return value == MASK


def export_config(db: Session) -> Dict[str, Any]:
    """导出配置（系统配置 + 通知通道），敏感字段脱敏"""
    settings = settings_service.get_all(db)
    masked_settings = mask_sensitive(settings)

    channels: List[Dict[str, Any]] = []
    for channel in db.query(NotificationChannel).order_by(NotificationChannel.id).all():
        config = dict(channel.config or {})
        for key in list(config.keys()):
            if any(secret in key.lower() for secret in _CHANNEL_SECRET_KEYS):
                config[key] = MASK if config[key] not in (None, "") else config[key]
        channels.append({
            "name": channel.name,
            "channel_type": channel.channel_type,
            "enabled": bool(channel.enabled),
            "min_level": channel.min_level,
            "config": config,
        })

    return {
        "format": FORMAT_NAME,
        "version": FORMAT_VERSION,
        "exported_at": datetime.utcnow().isoformat() + "Z",
        "app_version": "1.1.0",
        "settings": masked_settings,
        "notification_channels": channels,
    }


def _backup_current(db: Session) -> str:
    payload = export_config(db)
    filename = f"config-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    path = _backup_dir() / filename
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return str(path)


def _merge_channel_config(existing: dict, incoming: dict) -> Tuple[dict, bool]:
    """合并通道配置；脱敏字段保留原值，返回 (配置, 是否含未提供密钥)"""
    merged = dict(existing or {})
    masked_present = False
    for key, value in (incoming or {}).items():
        if _is_masked(value):
            masked_present = True
            continue
        merged[key] = value
    return merged, masked_present


def import_config(
    db: Session,
    data: Dict[str, Any],
    dry_run: bool = False,
    privilege_token: str = "",
) -> Dict[str, Any]:
    """导入配置，返回统计与警告"""
    if not isinstance(data, dict):
        raise ValueError("配置文件格式错误（应为 JSON 对象）")
    if data.get("format") != FORMAT_NAME:
        raise ValueError("不是本系统的配置文件")
    try:
        version = int(data.get("version") or 0)
    except (TypeError, ValueError):
        version = 0
    if version > FORMAT_VERSION:
        raise ValueError(f"配置文件版本（{version}）高于当前系统支持版本（{FORMAT_VERSION}）")

    raw_settings = data.get("settings") or {}
    if not isinstance(raw_settings, dict):
        raise ValueError("settings 字段格式错误")

    # 忽略脱敏占位与未知 key
    proposed = {
        key: value
        for key, value in raw_settings.items()
        if not _is_masked(value)
    }
    normalized, errors = settings_service.validate(proposed)
    if errors:
        raise ValueError("；".join(errors))

    current = settings_service.get_all(db)
    changed = {
        key: value for key, value in normalized.items()
        if current.get(key) != value
    }
    copyright_keys = {"copyright_enabled", "copyright_name", "copyright_text", "copyright_color"}
    if copyright_keys.intersection(changed):
        try:
            privilege_service.verify_token(privilege_token)
        except privilege_service.PrivilegeError as exc:
            raise ValueError(f"导入内容包含版权信息修改，需要品牌特权口令：{exc}") from exc

    channels = data.get("notification_channels") or []
    if not isinstance(channels, list):
        raise ValueError("notification_channels 字段格式错误")

    warnings: List[str] = []
    channel_new = 0
    channel_updated = 0

    if dry_run:
        # 仅做校验与差异统计，不落库
        for item in channels:
            if not isinstance(item, dict) or not item.get("name"):
                warnings.append("存在缺少名称的通知通道，已跳过")
                continue
            exists = (
                db.query(NotificationChannel)
                .filter(NotificationChannel.name == item["name"])
                .first()
            )
            if exists:
                channel_updated += 1
            else:
                channel_new += 1
        return {
            "dry_run": True,
            "settings_changed": list(changed.keys()),
            "settings_count": len(changed),
            "channel_new": channel_new,
            "channel_updated": channel_updated,
            "warnings": warnings,
        }

    backup_path = _backup_current(db)

    if changed:
        settings_service.save(db, changed)

    for item in channels:
        if not isinstance(item, dict) or not item.get("name"):
            warnings.append("存在缺少名称的通知通道，已跳过")
            continue
        name = str(item["name"]).strip()[:100]
        channel_type = str(item.get("channel_type") or "email")[:20]
        if channel_type not in ("email", "webhook", "sms", "upstream"):
            warnings.append(f"通道「{name}」类型不支持：{channel_type}，已跳过")
            continue
        min_level = item.get("min_level") or "warning"
        incoming_config = item.get("config") or {}
        if not isinstance(incoming_config, dict):
            warnings.append(f"通道「{name}」config 格式错误，已跳过")
            continue

        existing = (
            db.query(NotificationChannel)
            .filter(NotificationChannel.name == name)
            .first()
        )
        if existing:
            merged, masked = _merge_channel_config(existing.config or {}, incoming_config)
            existing.channel_type = channel_type
            existing.enabled = bool(item.get("enabled", True))
            existing.min_level = min_level
            existing.config = merged
            existing.updated_at = datetime.utcnow()
            if masked:
                warnings.append(f"通道「{name}」含脱敏字段，已保留原有密钥/密码")
            channel_updated += 1
        else:
            _, masked = _merge_channel_config({}, incoming_config)
            db.add(NotificationChannel(
                name=name,
                channel_type=channel_type,
                enabled=bool(item.get("enabled", True)),
                min_level=min_level,
                config=incoming_config,
            ))
            if masked:
                warnings.append(f"新增通道「{name}」含脱敏字段，请导入后手动补全密码/Token")
            channel_new += 1

    db.commit()

    return {
        "dry_run": False,
        "settings_count": len(changed),
        "settings_changed": list(changed.keys()),
        "channel_new": channel_new,
        "channel_updated": channel_updated,
        "warnings": warnings,
        "backup_file": backup_path,
    }
