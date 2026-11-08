"""巡检报告 ONLYOFFICE Document Server 集成。"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any, Dict, Optional
from urllib.parse import urlparse

from ..config import Config


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode((text + "=" * (-len(text) % 4)).encode("ascii"))


def _secret() -> str:
    secret = str(getattr(Config, "AUTH_SECRET", "") or "")
    if not secret:
        raise ValueError("系统 AUTH_SECRET 未配置，无法签发在线 Office 访问令牌")
    return secret


def _sign(parts: bytes) -> str:
    return _b64(hmac.new(_secret().encode("utf-8"), parts, hashlib.sha256).digest())


def issue_file_token(report_id: int, action: str, ttl: int = 900) -> str:
    payload = {"r": int(report_id), "a": action, "exp": int(time.time()) + max(60, int(ttl))}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    return f"{body}.{_sign(body.encode('ascii'))}"


def verify_file_token(token: str, action: str, report_id: int) -> bool:
    try:
        body, signature = str(token or "").split(".", 1)
        expected = _sign(body.encode("ascii"))
        if not hmac.compare_digest(signature, expected):
            return False
        payload = json.loads(_unb64(body))
        return (
            str(payload.get("a")) == action
            and int(payload.get("r")) == int(report_id)
            and int(payload.get("exp") or 0) >= int(time.time())
        )
    except Exception:  # noqa: BLE001
        return False


def _jwt(payload: Dict[str, Any], secret: str) -> str:
    header = _b64(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode("utf-8"))
    body = _b64(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header}.{body}".encode("ascii")
    signature = hmac.new(secret.encode("utf-8"), signing_input, hashlib.sha256).digest()
    return f"{header}.{body}.{_b64(signature)}"


def office_settings(values: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "enabled": bool(values.get("inspection_office_enabled")),
        "document_server_url": str(values.get("inspection_office_document_server_url") or "").strip().rstrip("/"),
        "public_base_url": str(values.get("inspection_office_public_base_url") or "").strip().rstrip("/"),
        "jwt_secret": str(values.get("inspection_office_jwt_secret") or ""),
    }


def is_ready(values: Dict[str, Any]) -> bool:
    cfg = office_settings(values)
    return bool(
        cfg["enabled"]
        and cfg["document_server_url"].startswith(("http://", "https://"))
        and cfg["public_base_url"].startswith(("http://", "https://"))
    )


def build_editor_config(values: Dict[str, Any], report, user) -> Optional[Dict[str, Any]]:
    if not is_ready(values):
        return None
    cfg = office_settings(values)
    base = cfg["public_base_url"]
    file_token = issue_file_token(report.id, "file")
    callback_token = issue_file_token(report.id, "callback")
    title = str(report.original_filename or report.title or f"inspection-report-{report.id}")
    if not title.lower().endswith(".docx"):
        title += ".docx"
    try:
        version = int(report_path_mtime(report))
    except Exception:  # noqa: BLE001
        version = int(time.time())
    document = {
        "fileType": "docx",
        "key": f"inspection-{report.id}-{version}",
        "title": title[:200],
        "url": f"{base}/api/inspection/reports/{report.id}/office-file?token={file_token}",
        "permissions": {"edit": True, "download": True, "print": True},
    }
    editor_config = {
        "mode": "edit",
        "lang": "zh-CN",
        "callbackUrl": f"{base}/api/inspection/reports/{report.id}/office-callback?token={callback_token}",
        "user": {
            "id": str(getattr(user, "username", "") or "inspection-user"),
            "name": str(getattr(user, "real_name", "") or getattr(user, "username", "") or "巡检用户"),
        },
        "customization": {
            "autosave": True,
            "forcesave": True,
            "compactHeader": False,
            "toolbarNoTabs": False,
        },
    }
    editor_payload = {
        "document": document,
        "documentType": "word",
        "editorConfig": editor_config,
    }
    if cfg["jwt_secret"]:
        editor_payload["token"] = _jwt(editor_payload, cfg["jwt_secret"])
    return {
        "document_server_url": cfg["document_server_url"],
        "api_js_url": f"{cfg['document_server_url']}/web-apps/apps/api/documents/api.js",
        "config": editor_payload,
    }


def report_path_mtime(report) -> float:
    from . import inspection as inspection_service

    path = inspection_service.report_path(report.filename)
    return path.stat().st_mtime_ns if path.is_file() else 0


def allowed_callback_url(url: str, document_server_url: str) -> bool:
    """回调下载只允许访问已配置的 Document Server 主机，避免任意 SSRF。"""
    try:
        target = urlparse(str(url or ""))
        server = urlparse(str(document_server_url or ""))
        if target.scheme not in ("http", "https"):
            return False
        if not target.hostname or not server.hostname:
            return False
        return target.hostname.lower() == server.hostname.lower()
    except Exception:  # noqa: BLE001
        return False
