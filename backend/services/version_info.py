"""版本信息服务：读取构建时自动生成的版本信息。"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from ..config import PROJECT_ROOT

VERSION_FILE = PROJECT_ROOT / "backend" / "version.json"
DIST_VERSION_FILE = PROJECT_ROOT / "frontend" / "dist" / "version.json"
PACKAGE_FILE = PROJECT_ROOT / "frontend" / "package.json"


def _read_json(path: Path) -> Optional[Dict[str, Any]]:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, ValueError):
        return None


def _package_version() -> str:
    data = _read_json(PACKAGE_FILE) or {}
    return str(data.get("version") or "1.0.0").strip() or "1.0.0"
def _normalize_auto(data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not data:
        return None
    version = str(data.get("version") or "").strip()
    if not version:
        return None
    build = str(data.get("build") or "").strip()
    display_version = str(data.get("display_version") or "").strip()
    if not display_version:
        display_version = f"{version}+{build}" if build else version
    return {
        "version": version,
        "display_version": display_version,
        "build": build,
        "build_id": str(data.get("build_id") or "").strip(),
        "built_at": str(data.get("built_at") or "").strip(),
        "source": "auto",
    }


def _build_timestamp(data: Dict[str, Any], path: Path) -> float:
    """用构建时间排序；缺失时回退文件修改时间。"""
    raw = str(data.get("built_at") or "").strip()
    if raw:
        try:
            return datetime.fromisoformat(raw.replace("Z", "+00:00")).timestamp()
        except ValueError:
            pass
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def auto_version() -> Optional[Dict[str, Any]]:
    """读取最新一份构建版本。

    Docker 多阶段构建只会把 frontend/dist 带入运行镜像，因此 dist/version.json
    必须优先参与选择；本地开发/打包则 backend/version.json 与 dist/version.json 同步。
    """
    candidates = []
    for path in (VERSION_FILE, DIST_VERSION_FILE):
        raw = _read_json(path)
        item = _normalize_auto(raw)
        if item and raw is not None:
            candidates.append((_build_timestamp(raw, path), item))
    if not candidates:
        return None
    return max(candidates, key=lambda pair: pair[0])[1]


def get_version_info(db: Session) -> Dict[str, Any]:
    auto = auto_version()
    if auto:
        effective = {**auto, "source": "auto"}
    else:
        effective = {
            "version": _package_version(),
            "display_version": _package_version(),
            "build": "",
            "build_id": "",
            "built_at": "",
            "source": "fallback",
        }
    return {
        "effective": effective,
        "auto": auto,
        "auto_available": bool(auto),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
