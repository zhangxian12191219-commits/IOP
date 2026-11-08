"""独立系统更新执行器。

由 API 复制到 data/updates 后以独立进程运行，避免更新过程中 API 自身
被替换或重启而导致更新中断。只依赖 Python 标准库。
"""
from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

IGNORED_DIRS = {"data", ".venv", "node_modules", "__pycache__", ".git", ".pytest_cache"}
IGNORED_FILES = {
    ".env", "snmp-nms.env", "snmp_monitor.db", "snmp_monitor.db-shm",
    "snmp_monitor.db-wal", ".DS_Store", "backup-meta.json",
}


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_job(path: str) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def write_job(job: dict) -> None:
    path = Path(job["status_path"])
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(job, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def set_status(job: dict, status: str, message: str, **extra) -> None:
    job.update({"status": status, "message": message, "updated_at": now(), **extra})
    write_job(job)
    print(f"[{status}] {message}", flush=True)


def ignore_entries(directory: str, names: list[str]) -> set[str]:
    ignored = set()
    for name in names:
        if name in IGNORED_DIRS or name in IGNORED_FILES:
            ignored.add(name)
            continue
        if name.endswith((".db", ".db-shm", ".db-wal", ".pyc")):
            ignored.add(name)
    return ignored


def backup_code(job: dict) -> None:
    app = Path(job["app_dir"])
    backup = Path(job["backup_dir"])
    if backup.exists():
        shutil.rmtree(backup)
    backup.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(app, backup, ignore=ignore_entries, symlinks=True)
    version = {}
    try:
        version = json.loads((app / "backend" / "version.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    metadata = {
        "version": str(version.get("version") or job.get("current_version") or "unknown"),
        "display_version": str(version.get("display_version") or job.get("current_version") or "unknown"),
        "build": str(version.get("build") or ""),
        "build_id": str(version.get("build_id") or ""),
        "created_at": now(),
        "backup_job_id": job.get("job_id"),
        "reason": job.get("source") or "update",
    }
    try:
        (backup / "backup-meta.json").write_text(
            json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        print(f"写入版本元信息失败: {exc}", flush=True)


def prune_backups(job: dict) -> None:
    """默认只保留最近 5 个版本备份目录。"""
    try:
        keep = max(1, int(job.get("retention") or 5))
        backup_root = Path(job["backup_dir"]).parent
        dirs = [p for p in backup_root.iterdir() if p.is_dir()]
        dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        for old in dirs[keep:]:
            shutil.rmtree(old, ignore_errors=True)
    except Exception as exc:  # noqa: BLE001
        print(f"清理旧版本备份失败: {exc}", flush=True)


def apply_code(job: dict) -> None:
    app = Path(job["app_dir"])
    stage = Path(job["stage_dir"])
    shutil.copytree(stage, app, dirs_exist_ok=True, ignore=ignore_entries)
    for cache in app.rglob("__pycache__"):
        if cache.is_dir():
            shutil.rmtree(cache, ignore_errors=True)


def restore_code(job: dict) -> None:
    app = Path(job["app_dir"])
    backup = Path(job["backup_dir"])
    shutil.copytree(backup, app, dirs_exist_ok=True, ignore=ignore_entries)


def python_for_app(app: Path) -> str:
    candidates = [
        app / ".venv" / "bin" / "python",
        app / ".venv" / "Scripts" / "python.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable


def install_dependencies(job: dict, requirements_path: Path | None = None) -> None:
    if not job.get("install_dependencies"):
        return
    app = Path(job["app_dir"])
    requirements = requirements_path or (app / "backend" / "requirements.txt")
    if not requirements.exists():
        return
    set_status(job, "dependencies", "正在安装新增 Python 依赖")
    result = subprocess.run(
        [python_for_app(app), "-m", "pip", "install", "-r", str(requirements),
         "--disable-pip-version-check"],
        cwd=str(app), capture_output=True, text=True, timeout=900,
    )
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "")[-3000:]
        raise RuntimeError(f"依赖安装失败:\n{tail}")


def restart_service(job: dict) -> None:
    mode = job.get("restart_mode")
    app = Path(job["app_dir"])
    if mode == "systemd":
        set_status(job, "restarting", "正在重启 systemd 服务")
        result = subprocess.run(
            ["systemctl", "restart", job.get("service_name") or "snmp-nms"],
            timeout=180, capture_output=True, text=True,
        )
        if result.returncode == 0:
            return
        # 普通服务用户通常没有 systemctl 重启权限；向主进程发送 SIGTERM，
        # 由 systemd 的 Restart=always 自动拉起新版本。
        old_pid = int(job.get("pid") or 0)
        if old_pid and old_pid != os.getpid():
            os.kill(old_pid, signal.SIGTERM)
            return
        raise RuntimeError(f"systemd 重启失败: {result.stderr or result.stdout}")
    if mode == "start_sh" and (app / "start.sh").exists():
        set_status(job, "restarting", "正在通过 start.sh 重启服务")
        subprocess.run(["bash", str(app / "start.sh"), "restart"],
                       cwd=str(app), timeout=180, check=True)
        return

    # 无 systemd、无 start.sh：结束旧进程后直接拉起 run_backend.py
    set_status(job, "restarting", "正在重启应用进程")
    old_pid = int(job.get("pid") or 0)
    if old_pid and old_pid != os.getpid():
        try:
            if os.name == "nt":
                subprocess.run(["taskkill", "/PID", str(old_pid), "/F"],
                               capture_output=True, timeout=30)
            else:
                os.kill(old_pid, signal.SIGTERM)
        except Exception:
            pass
        time.sleep(2)
    log_path = Path(job["log_path"]).with_name("backend-restart.log")
    log = log_path.open("ab")
    kwargs = {"cwd": str(app), "stdout": log, "stderr": log, "close_fds": True}
    if os.name == "nt":
        kwargs["creationflags"] = 0x00000008 | 0x00000200
    else:
        kwargs["start_new_session"] = True
    try:
        subprocess.Popen(
            [python_for_app(app), str(app / "run_backend.py"), str(job.get("port") or 8000)],
            **kwargs,
        )
    finally:
        log.close()


def wait_health(job: dict, seconds: int = 60) -> bool:
    """快速探测存活，再做完整健康检查；旧版本没有 live 接口时自动回退。"""
    base = f"http://127.0.0.1:{int(job.get('port') or 8000)}"
    live_url = base + "/api/health/live"
    full_url = base + "/api/health"
    deadline = time.time() + seconds
    started = time.time()
    while time.time() < deadline:
        live_ok = False
        try:
            with urllib.request.urlopen(live_url, timeout=1.0) as response:
                live_ok = str(json.loads(response.read().decode("utf-8")).get("status")) == "ok"
        except Exception:  # noqa: BLE001 - 旧版本或服务尚未监听
            live_ok = False
        # 完整健康检查最多 2 秒；live 可用时再验证数据库，旧版本回退直接检查完整接口。
        try:
            with urllib.request.urlopen(full_url, timeout=2.0) as response:
                data = json.loads(response.read().decode("utf-8"))
                if str(data.get("status")) == "ok":
                    return True
        except Exception:  # noqa: BLE001
            if live_ok:
                # 数据库尚未就绪，不立即判失败，继续快速轮询。
                pass
        elapsed = time.time() - started
        time.sleep(0.4 if elapsed < 15 else 0.8)
    return False

def main() -> int:
    if len(sys.argv) < 2:
        return 2
    job = load_job(sys.argv[1])
    try:
        time.sleep(2)
        set_status(job, "backup", "正在备份当前程序文件")
        backup_code(job)
        # 先安装新包依赖，成功后才替换代码；依赖失败时当前服务保持运行
        set_status(job, "dependencies", "正在预安装新版本 Python 依赖")
        try:
            install_dependencies(job, Path(job["stage_dir"]) / "backend" / "requirements.txt")
        except Exception as dep_exc:  # noqa: BLE001
            set_status(
                job, "rolled_back",
                f"依赖安装失败，未替换程序文件；当前服务保持运行: {dep_exc}",
            )
            return 1
        set_status(job, "applying", "正在替换程序文件")
        apply_code(job)
        restart_service(job)
        if wait_health(job):
            prune_backups(job)
            set_status(job, "success", "更新完成，服务已重启并通过健康检查")
            return 0
        set_status(job, "rollback", "新版本健康检查失败，正在回滚")
        restore_code(job)
        restart_service(job)
        if wait_health(job):
            prune_backups(job)
            set_status(job, "rolled_back", "新版本健康检查失败，已回滚到旧版本")
        else:
            set_status(job, "failed", "更新失败且回滚后健康检查仍未通过，请手工检查")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"更新异常: {exc}", flush=True)
        try:
            if Path(job.get("backup_dir", "")).exists():
                set_status(job, "rollback", f"更新异常，正在回滚: {exc}")
                restore_code(job)
                try:
                    restart_service(job)
                    wait_health(job, 60)
                except Exception:
                    pass
            set_status(job, "rolled_back" if Path(job.get("backup_dir", "")).exists() else "failed",
                       f"更新失败: {exc}")
        except Exception as inner:
            print(f"回滚异常: {inner}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
