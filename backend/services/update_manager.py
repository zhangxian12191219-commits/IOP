"""系统更新：更新包校验、在线下载、更新任务编排。"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from ..config import Config, PROJECT_ROOT

UPDATE_ROOT = PROJECT_ROOT / "data" / "updates"
UPLOAD_DIR = UPDATE_ROOT / "uploads"
STAGING_DIR = UPDATE_ROOT / "staging"
JOBS_DIR = UPDATE_ROOT / "jobs"
BACKUP_DIR = UPDATE_ROOT / "backups"
MAX_ZIP_BYTES = 512 * 1024 * 1024
MAX_UNCOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024
MAX_MEMBERS = 20000
DEFAULT_BACKUP_RETENTION = 5
TERMINAL_STATUSES = {"success", "failed", "rolled_back"}
SERVICE_NAME = "snmp-nms"


class UpdateError(Exception):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def ensure_dirs() -> None:
    for path in (UPDATE_ROOT, UPLOAD_DIR, STAGING_DIR, JOBS_DIR, BACKUP_DIR):
        path.mkdir(parents=True, exist_ok=True)


def read_version() -> Dict[str, Any]:
    for path in (
        PROJECT_ROOT / "backend" / "version.json",
        PROJECT_ROOT / "frontend" / "dist" / "version.json",
    ):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and data.get("version"):
            return {
                "version": str(data["version"]),
                "display_version": str(data.get("display_version") or data["version"]),
                "build": str(data.get("build") or ""),
                "build_id": str(data.get("build_id") or ""),
                "built_at": str(data.get("built_at") or ""),
            }
    return {"version": "unknown", "display_version": "unknown"}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _zip_members(zf: zipfile.ZipFile) -> Tuple[list[zipfile.ZipInfo], Optional[str]]:
    members = [info for info in zf.infolist() if not info.is_dir()]
    if not members:
        raise UpdateError("更新包是空压缩包")
    if len(members) > MAX_MEMBERS:
        raise UpdateError(f"更新包文件数量超过限制（最多 {MAX_MEMBERS} 个）")
    total = sum(max(0, int(info.file_size or 0)) for info in members)
    if total > MAX_UNCOMPRESSED_BYTES:
        raise UpdateError("更新包解压后体积超过 2GB 限制")

    roots = {info.filename.split("/", 1)[0] for info in members}
    prefix: Optional[str] = None
    if len(roots) == 1:
        candidate = next(iter(roots))
        if (
            f"{candidate}/run_backend.py" in {i.filename for i in members}
            and any(i.filename.startswith(f"{candidate}/backend/") for i in members)
        ):
            prefix = candidate
    for info in members:
        name = info.filename.replace("\\", "/")
        parts = [part for part in name.split("/") if part]
        if not parts or name.startswith("/") or ".." in parts:
            raise UpdateError(f"更新包包含不安全路径: {name}")
        mode = (info.external_attr >> 16) & 0o170000
        if mode == 0o120000:
            raise UpdateError(f"更新包不能包含符号链接: {name}")
    return members, prefix


def _extract_zip(zip_path: Path, stage: Path) -> Dict[str, Any]:
    ensure_dirs()
    stage.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(zip_path) as zf:
            members, prefix = _zip_members(zf)
            for info in members:
                name = info.filename.replace("\\", "/")
                if prefix:
                    name = name[len(prefix) + 1:]
                parts = [part for part in name.split("/") if part]
                if not parts:
                    continue
                target = stage.joinpath(*parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst, length=1024 * 1024)
                try:
                    mode = (info.external_attr >> 16) & 0o777
                    if mode:
                        os.chmod(target, mode)
                except OSError:
                    pass
    except zipfile.BadZipFile as exc:
        raise UpdateError("文件不是有效的 ZIP 更新包") from exc
    except UpdateError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise UpdateError(f"解压更新包失败: {exc}") from exc

    missing = [
        name for name in ("run_backend.py", "backend/version.json", "frontend/dist/index.html")
        if not (stage / name).exists()
    ]
    if missing:
        raise UpdateError("更新包结构不正确，缺少: " + ", ".join(missing))
    try:
        data = json.loads((stage / "backend" / "version.json").read_text(encoding="utf-8"))
        version = str(data.get("version") or "").strip()
    except (OSError, ValueError) as exc:
        raise UpdateError(f"无法读取更新包版本: {exc}") from exc
    if not version:
        raise UpdateError("更新包 backend/version.json 缺少 version 字段")
    # 先做 Python 语法检查，避免把无法启动的后端替换上线
    check = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(stage / "backend")],
        capture_output=True, text=True, timeout=120,
    )
    if check.returncode != 0:
        raise UpdateError("更新包后端 Python 语法检查失败: " + (check.stderr or check.stdout)[-2000:])
    return {
        "version": version,
        "display_version": str(data.get("display_version") or version),
        "build": str(data.get("build") or ""),
        "build_id": str(data.get("build_id") or ""),
        "built_at": str(data.get("built_at") or ""),
        "stage": str(stage),
    }


def save_upload(upload_file, filename: str = "") -> Path:
    """流式保存上传文件，返回保存路径。"""
    ensure_dirs()
    suffix = ".zip"
    safe_name = Path(filename or "update.zip").name
    if not safe_name.lower().endswith(".zip"):
        suffix = Path(safe_name).suffix or ".zip"
    target = UPLOAD_DIR / f"upload-{int(time.time())}-{secrets.token_hex(4)}{suffix}"
    total = 0
    try:
        with target.open("wb") as out:
            while True:
                chunk = upload_file.file.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_ZIP_BYTES:
                    raise UpdateError("更新包超过 512MB 限制")
                out.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    if total == 0:
        target.unlink(missing_ok=True)
        raise UpdateError("上传文件为空")
    return target


def download_url(url: str, sha256: str = "") -> Path:
    """下载在线更新包并校验大小/可选 SHA256。"""
    ensure_dirs()
    if not re.match(r"^https?://", url, re.I):
        raise UpdateError("在线更新地址必须是 http:// 或 https:// URL")
    target = UPLOAD_DIR / f"online-{int(time.time())}-{secrets.token_hex(4)}.zip"
    try:
        request = urllib.request.Request(url, headers={"User-Agent": "SNMP-NMS-Updater/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response, target.open("wb") as out:
            total = 0
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                total += len(chunk)
                if total > MAX_ZIP_BYTES:
                    raise UpdateError("在线更新包超过 512MB 限制")
                out.write(chunk)
        if total == 0:
            raise UpdateError("在线更新包为空")
        if sha256 and _sha256(target).lower() != sha256.lower():
            raise UpdateError("在线更新包 SHA256 校验失败")
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return target


def fetch_online_metadata(url: str) -> Dict[str, Any]:
    """支持 latest.json、目录地址或 zip 直链。"""
    if not re.match(r"^https?://", url, re.I):
        raise UpdateError("请先填写合法的在线更新地址")
    parsed = urllib.parse.urlparse(url)
    path = parsed.path.lower()
    if path.endswith(".zip"):
        return {"download_url": url, "version": "", "notes": "ZIP 直链"}

    metadata_url = url if path.endswith(".json") else url.rstrip("/") + "/latest.json"
    try:
        request = urllib.request.Request(metadata_url, headers={"User-Agent": "SNMP-NMS-Updater/1.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = response.read(1024 * 1024)
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise UpdateError(f"获取在线更新信息失败: {exc}") from exc
    if not isinstance(data, dict):
        raise UpdateError("在线更新 latest.json 格式不正确")
    file_url = data.get("download_url") or data.get("url") or data.get("file")
    if not file_url:
        raise UpdateError("latest.json 缺少 download_url / file 字段")
    download = urllib.parse.urljoin(metadata_url, str(file_url))
    return {
        "download_url": download,
        "version": str(data.get("version") or ""),
        "display_version": str(data.get("display_version") or data.get("version") or ""),
        "notes": str(data.get("notes") or ""),
        "sha256": str(data.get("sha256") or ""),
        "source": metadata_url,
    }


def prepare_package(zip_path: Path, source: str = "upload") -> Dict[str, Any]:
    job_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"
    stage = STAGING_DIR / job_id
    info = _extract_zip(zip_path, stage)
    info.update({
        "job_id": job_id,
        "zip_path": str(zip_path),
        "source": source,
        "sha256": _sha256(zip_path),
        "uploaded_name": zip_path.name,
    })
    return info


def _requirements_changed(stage: Path) -> bool:
    old = PROJECT_ROOT / "backend" / "requirements.txt"
    new = stage / "backend" / "requirements.txt"
    if not new.exists():
        return False
    if not old.exists():
        return True
    return old.read_bytes() != new.read_bytes()


def restart_mode() -> str:
    if Path("/.dockerenv").exists():
        return "docker"
    if os.name == "nt":
        return "process"
    if Path(f"/etc/systemd/system/{SERVICE_NAME}.service").exists():
        return "systemd"
    if (PROJECT_ROOT / "start.sh").exists():
        return "start_sh"
    return "process"


def _job_path(job_id: str) -> Path:
    return JOBS_DIR / f"{job_id}.json"


def _write_job(job_id: str, data: Dict[str, Any]) -> None:
    path = _job_path(job_id)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _version_key(value: Any) -> tuple:
    parts = []
    for item in str(value or "").split("."):
        try:
            parts.append(int(item))
        except (TypeError, ValueError):
            parts.append(0)
    return tuple(parts)


def _reconcile_stale_job(data: Dict[str, Any], path: Path) -> Dict[str, Any]:
    """服务重启会结束更新执行器，启动后收敛遗留的 restarting 任务。"""
    if data.get("status") in TERMINAL_STATUSES:
        return data
    try:
        age = time.time() - path.stat().st_mtime
    except OSError:
        age = 0
    if data.get("status") == "restarting":
        current = str(read_version().get("version") or "")
        old = str(data.get("current_version") or "")
        target = str(data.get("new_version_raw") or data.get("new_version") or "")
        # 新进程已经开始服务后只需 8 秒即可确认，不再固定等 2 分钟。
        if age > 8 and current == target:
            data["status"] = "success"
            data["message"] = "更新完成，服务已重启并运行新版本"
        elif age > 8 and current and current != old and _version_key(current) > _version_key(old):
            data["status"] = "success"
            data["message"] = f"更新任务已由当前版本 {current} 取代"
        elif age > 120 and current and current == old:
            data["status"] = "failed"
            data["message"] = "更新进程重启后未完成，当前仍为旧版本"
        elif age > 120:
            data["status"] = "rolled_back"
            data["message"] = f"更新未完成，当前版本为 {current or 'unknown'}"
        else:
            return data
        data["updated_at"] = _now()
        try:
            _write_job(data["job_id"], data)
        except Exception:  # noqa: BLE001
            pass
    elif age > 1800 and data.get("status") in ("queued", "backup", "applying", "dependencies"):
        current = str(read_version().get("version") or "")
        old = str(data.get("current_version") or "")
        data["status"] = "success" if current and current != old else "failed"
        data["message"] = "更新任务超时，已自动收敛" if data["status"] == "success" else "更新任务超时，未完成"
        data["updated_at"] = _now()
        try:
            _write_job(data["job_id"], data)
        except Exception:  # noqa: BLE001
            pass
    return data


def active_job() -> Optional[Dict[str, Any]]:
    ensure_dirs()
    jobs = sorted(JOBS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    for path in jobs[:5]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        data = _reconcile_stale_job(data, path)
        if data.get("status") not in TERMINAL_STATUSES:
            try:
                age = time.time() - path.stat().st_mtime
            except OSError:
                age = 0
            if age < 2 * 3600:
                return data
    return None


def start_update(package: Dict[str, Any], *, source: str, username: str = "",
                 install_dependencies: bool = True) -> Dict[str, Any]:
    ensure_dirs()
    if restart_mode() == "docker":
        raise UpdateError("当前为 Docker 容器部署，请在宿主机更新镜像后执行 docker compose up -d；不支持容器内自更新")
    existing = active_job()
    if existing:
        raise UpdateError(f"已有更新任务正在执行: {existing.get('job_id')}")
    current = read_version()
    new_version = package["version"]
    job_id = package["job_id"]
    job = {
        "job_id": job_id,
        "status_token": secrets.token_urlsafe(24),
        "status": "queued",
        "message": "更新任务已创建，等待更新进程执行",
        "source": source,
        "username": username,
        "current_version": current.get("display_version") or current.get("version"),
        "new_version": package.get("display_version") or new_version,
        "new_version_raw": new_version,
        "build": package.get("build", ""),
        "zip_path": package["zip_path"],
        "stage_dir": package["stage"],
        "sha256": package.get("sha256", ""),
        "install_dependencies": bool(install_dependencies and _requirements_changed(Path(package["stage"]))),
        "app_dir": str(PROJECT_ROOT),
        "backup_dir": str(BACKUP_DIR / job_id),
        "log_path": str(UPDATE_ROOT / f"update-{job_id}.log"),
        "status_path": str(_job_path(job_id)),
        "restart_mode": restart_mode(),
        "service_name": SERVICE_NAME,
        "port": int(Config.API_PORT),
        "pid": os.getpid(),
        "retention": DEFAULT_BACKUP_RETENTION,
        "created_at": _now(),
        "updated_at": _now(),
    }
    _write_job(job_id, job)

    runner_src = Path(__file__).with_name("update_runner.py")
    if not runner_src.exists():
        raise UpdateError("更新执行器不存在，无法启动更新")
    runner = UPDATE_ROOT / f"runner-{job_id}.py"
    shutil.copy2(runner_src, runner)

    log = (UPDATE_ROOT / f"update-{job_id}.log").open("ab")
    cmd = [sys.executable, str(runner), str(_job_path(job_id))]
    kwargs = {
        "cwd": str(PROJECT_ROOT),
        "stdout": log,
        "stderr": log,
        "close_fds": True,
    }
    try:
        if os.name == "nt":
            kwargs["creationflags"] = 0x00000008 | 0x00000200  # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP
            subprocess.Popen(cmd, **kwargs)
        else:
            kwargs["start_new_session"] = True
            subprocess.Popen(cmd, **kwargs)
    finally:
        log.close()
    return job


def load_job(job_id: Optional[str] = None) -> Optional[Dict[str, Any]]:
    ensure_dirs()
    if job_id:
        path = _job_path(job_id)
    else:
        jobs = sorted(JOBS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        path = jobs[0] if jobs else None
    if path is None or not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    data = _reconcile_stale_job(data, path)
    return data


def _backup_metadata(path: Path) -> Dict[str, Any]:
    meta_path = path / "backup-meta.json"
    try:
        data = json.loads(meta_path.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    try:
        data = json.loads((path / "backend" / "version.json").read_text(encoding="utf-8"))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError):
        pass
    return {}


def _safe_backup_path(job_id: str) -> Path:
    if not re.match(r"^[0-9A-Za-z._-]{1,100}$", str(job_id or "")):
        raise UpdateError("版本备份标识不合法")
    path = (BACKUP_DIR / job_id).resolve()
    if path.parent != BACKUP_DIR.resolve() or not path.is_dir():
        raise UpdateError("版本备份不存在")
    return path


def list_backups(limit: int = DEFAULT_BACKUP_RETENTION) -> list[Dict[str, Any]]:
    """版本文件列表；只暴露元信息，不返回服务器绝对路径。"""
    ensure_dirs()
    items = []
    dirs = [p for p in BACKUP_DIR.glob("*") if p.is_dir()]
    dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    # 默认仅保留最近 5 个版本目录
    for old in dirs[limit:]:
        shutil.rmtree(old, ignore_errors=True)
    for path in dirs[:limit]:
        meta = _backup_metadata(path)
        file_count = 0
        size_bytes = 0
        for file in path.rglob("*"):
            if file.is_file() and file.name != "backup-meta.json":
                file_count += 1
                try:
                    size_bytes += file.stat().st_size
                except OSError:
                    pass
        items.append({
            "job_id": path.name,
            "version": meta.get("version") or "unknown",
            "display_version": meta.get("display_version") or meta.get("version") or "unknown",
            "build": meta.get("build") or "",
            "build_id": meta.get("build_id") or "",
            "created_at": meta.get("created_at") or datetime.fromtimestamp(
                path.stat().st_mtime, timezone.utc
            ).isoformat(),
            "size_bytes": size_bytes,
            "file_count": file_count,
        })
    return items


def backup_files(job_id: str, limit: int = 500) -> Dict[str, Any]:
    """查看指定历史版本备份中的文件清单。"""
    ensure_dirs()
    path = _safe_backup_path(job_id)
    meta = _backup_metadata(path)
    files = []
    truncated = False
    for file in sorted(path.rglob("*")):
        if not file.is_file() or file.name == "backup-meta.json":
            continue
        if len(files) >= limit:
            truncated = True
            break
        try:
            size = file.stat().st_size
        except OSError:
            size = 0
        files.append({
            "path": file.relative_to(path).as_posix(),
            "size_bytes": size,
        })
    return {
        "job_id": job_id,
        "version": meta.get("version") or "unknown",
        "display_version": meta.get("display_version") or meta.get("version") or "unknown",
        "build": meta.get("build") or "",
        "created_at": meta.get("created_at"),
        "files": files,
        "total": len(files),
        "truncated": truncated,
    }


def delete_backup(backup_id: str) -> Dict[str, Any]:
    """删除历史版本备份；更新/回退执行期间禁止删除。"""
    ensure_dirs()
    existing = active_job()
    if existing:
        raise UpdateError("系统更新/版本回退正在执行，完成前不能删除历史版本")
    path = _safe_backup_path(backup_id)
    meta = _backup_metadata(path)
    result = {
        "job_id": backup_id,
        "version": meta.get("version") or "unknown",
        "display_version": meta.get("display_version") or meta.get("version") or "unknown",
    }
    shutil.rmtree(path)
    return result


def start_rollback(backup_id: str, *, username: str = "", force: bool = False) -> Dict[str, Any]:
    """从历史备份目录启动版本回退。"""
    ensure_dirs()
    if restart_mode() == "docker":
        raise UpdateError("当前为 Docker 容器部署，请在宿主机回退镜像；不支持容器内回退")
    existing = active_job()
    if existing:
        raise UpdateError(f"已有更新/回退任务正在执行: {existing.get('job_id')}")
    source_dir = _safe_backup_path(backup_id)
    required = ("run_backend.py", "backend/version.json", "frontend/dist/index.html")
    missing = [name for name in required if not (source_dir / name).exists()]
    if missing:
        raise UpdateError("版本备份不完整，缺少: " + ", ".join(missing))
    meta = _backup_metadata(source_dir)
    target_version = str(meta.get("version") or "").strip()
    if not target_version:
        raise UpdateError("版本备份缺少版本信息，无法回退")
    current = read_version()
    if not force and target_version == str(current.get("version") or ""):
        raise UpdateError("目标备份与当前版本相同；如需重装该版本请选择强制回退")
    job_id = f"{datetime.now().strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(3)}"
    job = {
        "job_id": job_id,
        "status": "queued",
        "message": "版本回退任务已创建，等待回退进程执行",
        "source": "rollback",
        "username": username,
        "current_version": current.get("display_version") or current.get("version"),
        "new_version": meta.get("display_version") or target_version,
        "new_version_raw": target_version,
        "build": meta.get("build", ""),
        "zip_path": "",
        "stage_dir": str(source_dir),
        "sha256": "",
        "install_dependencies": bool(_requirements_changed(source_dir)),
        "app_dir": str(PROJECT_ROOT),
        "backup_dir": str(BACKUP_DIR / job_id),
        "log_path": str(UPDATE_ROOT / f"update-{job_id}.log"),
        "status_path": str(_job_path(job_id)),
        "restart_mode": restart_mode(),
        "service_name": SERVICE_NAME,
        "port": int(Config.API_PORT),
        "pid": os.getpid(),
        "retention": DEFAULT_BACKUP_RETENTION,
        "created_at": _now(),
        "updated_at": _now(),
    }
    _write_job(job_id, job)
    _launch_runner(job)
    return job


def _launch_runner(job: Dict[str, Any]) -> None:
    runner_src = Path(__file__).with_name("update_runner.py")
    if not runner_src.exists():
        raise UpdateError("更新执行器不存在，无法启动更新")
    runner = UPDATE_ROOT / f"runner-{job['job_id']}.py"
    shutil.copy2(runner_src, runner)
    log = (UPDATE_ROOT / f"update-{job['job_id']}.log").open("ab")
    cmd = [sys.executable, str(_job_path(job["job_id"]))]
    kwargs = {
        "cwd": str(PROJECT_ROOT),
        "stdout": log,
        "stderr": log,
        "close_fds": True,
    }
    try:
        if os.name == "nt":
            kwargs["creationflags"] = 0x00000008 | 0x00000200
            subprocess.Popen(cmd, **kwargs)
        else:
            kwargs["start_new_session"] = True
            subprocess.Popen(cmd, **kwargs)
    finally:
        log.close()
