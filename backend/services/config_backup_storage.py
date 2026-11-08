"""设备配置备份的外部存储：WebDAV / SFTP。

数据库仍保存配置正文，作为本地兜底；启用外部存储后，成功备份会额外上传一份。
外部存储失败不回滚设备备份，只记录 storage_status/storage_error。
"""
from __future__ import annotations

import io
import logging
import re
from typing import Any, Dict, Optional
from urllib.parse import quote, urlparse

import requests

logger = logging.getLogger("snmp-monitor.config-backup.storage")


def _clean_part(value: str, fallback: str = "item") -> str:
    text = re.sub(r"[^0-9A-Za-z_.\-\u4e00-\u9fa5]+", "_", str(value or ""))
    return text.strip("_")[:80] or fallback


def build_key(record) -> str:
    """生成稳定的外部对象路径。"""
    return f"{record.device_id}/{record.id}-{str(record.sha256 or '')[:12]}.cfg"


def _enabled(values: Dict[str, Any]) -> bool:
    return bool(values.get("config_backup_storage_enabled"))


def describe(values: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "enabled": _enabled(values),
        "type": str(values.get("config_backup_storage_type") or "webdav"),
    }


def _webdav_base(values: Dict[str, Any]) -> str:
    base = str(values.get("config_backup_webdav_url") or "").strip().rstrip("/")
    if not base:
        raise ValueError("未配置 WebDAV 地址")
    parsed = urlparse(base)
    if parsed.scheme not in ("http", "https"):
        raise ValueError("WebDAV 地址必须以 http:// 或 https:// 开头")
    return base


def _webdav_url(values: Dict[str, Any], key: str) -> str:
    base = _webdav_base(values)
    path = str(values.get("config_backup_webdav_path") or "").strip().strip("/")
    parts = [part for part in (path, key) if part]
    return base + "/" + "/".join(quote(part, safe="/-_.~") for part in parts)


def _webdav_auth(values: Dict[str, Any]):
    username = str(values.get("config_backup_webdav_username") or "").strip()
    password = str(values.get("config_backup_webdav_password") or "")
    return (username, password) if username else None


def _sftp_connect(values: Dict[str, Any]):
    import paramiko

    host = str(values.get("config_backup_sftp_host") or "").strip()
    if not host:
        raise ValueError("未配置 SFTP 主机")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host,
        port=int(values.get("config_backup_sftp_port") or 22),
        username=str(values.get("config_backup_sftp_username") or ""),
        password=str(values.get("config_backup_sftp_password") or ""),
        timeout=float(values.get("config_backup_sftp_timeout") or 15),
        banner_timeout=float(values.get("config_backup_sftp_timeout") or 15),
        auth_timeout=float(values.get("config_backup_sftp_timeout") or 15),
        look_for_keys=False,
        allow_agent=False,
    )
    return client, client.open_sftp()


def _sftp_mkdirs(sftp, path: str) -> None:
    parts = [part for part in path.strip("/").split("/") if part]
    current = "/" if path.startswith("/") else ""
    for part in parts:
        current = f"{current}/{part}" if current and current != "/" else f"/{part}" if path.startswith("/") else part
        try:
            sftp.stat(current)
        except OSError:
            sftp.mkdir(current)


def _sftp_path(values: Dict[str, Any], key: str) -> str:
    base = str(values.get("config_backup_sftp_path") or "").strip().strip("/")
    return ("/" if str(values.get("config_backup_sftp_path") or "").startswith("/") else "") + "/".join(
        part for part in (base, key) if part
    )


def upload(values: Dict[str, Any], record, text: str) -> Dict[str, Any]:
    if not _enabled(values):
        return {"status": "disabled", "key": "", "error": ""}
    storage_type = str(values.get("config_backup_storage_type") or "webdav").lower()
    key = build_key(record)
    data = (text or "").encode("utf-8")
    try:
        if storage_type == "webdav":
            response = requests.put(
                _webdav_url(values, key), data=data, auth=_webdav_auth(values),
                verify=bool(values.get("config_backup_webdav_verify_tls", True)),
                timeout=20,
            )
            if response.status_code >= 300:
                raise RuntimeError(f"WebDAV HTTP {response.status_code}: {response.text[:200]}")
        elif storage_type == "sftp":
            client, sftp = _sftp_connect(values)
            try:
                remote = _sftp_path(values, key)
                _sftp_mkdirs(sftp, remote.rsplit("/", 1)[0])
                sftp.putfo(io.BytesIO(data), remote)
            finally:
                sftp.close()
                client.close()
        else:
            raise ValueError(f"不支持的外部存储类型: {storage_type}")
        return {"status": "success", "key": key, "error": "", "type": storage_type}
    except Exception as exc:  # noqa: BLE001
        logger.warning("配置备份上传外部存储失败 %s: %s", key, exc)
        return {"status": "failed", "key": key, "error": str(exc)[:1000], "type": storage_type}


def download(values: Dict[str, Any], key: str) -> Optional[str]:
    if not key:
        return None
    storage_type = str(values.get("config_backup_storage_type") or "webdav").lower()
    try:
        if storage_type == "webdav":
            response = requests.get(
                _webdav_url(values, key), auth=_webdav_auth(values),
                verify=bool(values.get("config_backup_webdav_verify_tls", True)),
                timeout=20,
            )
            if response.status_code == 404:
                return None
            if response.status_code >= 300:
                raise RuntimeError(f"WebDAV HTTP {response.status_code}")
            return response.content.decode("utf-8", errors="replace")
        if storage_type == "sftp":
            client, sftp = _sftp_connect(values)
            try:
                with sftp.open(_sftp_path(values, key), "rb") as handle:
                    return handle.read().decode("utf-8", errors="replace")
            finally:
                sftp.close()
                client.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("从外部存储下载配置失败 %s: %s", key, exc)
    return None


def delete(values: Dict[str, Any], key: str) -> bool:
    if not key or not _enabled(values):
        return False
    storage_type = str(values.get("config_backup_storage_type") or "webdav").lower()
    try:
        if storage_type == "webdav":
            response = requests.delete(
                _webdav_url(values, key), auth=_webdav_auth(values),
                verify=bool(values.get("config_backup_webdav_verify_tls", True)),
                timeout=15,
            )
            return response.status_code < 300 or response.status_code == 404
        if storage_type == "sftp":
            client, sftp = _sftp_connect(values)
            try:
                sftp.remove(_sftp_path(values, key))
                return True
            finally:
                sftp.close()
                client.close()
    except Exception as exc:  # noqa: BLE001
        logger.warning("删除外部配置备份失败 %s: %s", key, exc)
    return False
