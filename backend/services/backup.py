"""数据库自动备份

- SQLite：使用 sqlite3 在线 backup API（业务运行中也可安全备份）
- MySQL：优先 mysqldump；PostgreSQL：优先 pg_dump（需客户端工具）
- 外部工具不可用时回退为 SQLAlchemy 逻辑 JSON 导出
- 按保留数量自动清理旧备份
"""
import json
import logging
import os
import sqlite3
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from sqlalchemy.engine.url import make_url

from ..config import Config
from ..models.database import Base, engine

logger = logging.getLogger(__name__)

BACKUP_PREFIX = "db-backup-"
ALLOWED_SUFFIX = (".db", ".sql", ".json")


def backup_dir() -> Path:
    directory = Path(Config.LOG_DIR).parent / "backups"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _timestamp() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def _backup_files() -> List[Path]:
    directory = backup_dir()
    if not directory.exists():
        return []
    files = [
        path for path in directory.glob(f"{BACKUP_PREFIX}*")
        if path.is_file() and path.suffix in ALLOWED_SUFFIX
    ]
    files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
    return files


def _file_info(path: Path) -> Dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.name,
        "size": stat.st_size,
        "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(timespec="seconds"),
        "download_url": f"/api/system/backups/{path.name}/download",
    }


def list_backups() -> List[Dict[str, Any]]:
    return [_file_info(path) for path in _backup_files()]


def latest_backup() -> Optional[Dict[str, Any]]:
    files = _backup_files()
    return _file_info(files[0]) if files else None


def _sqlite_backup(url, dest: Path) -> Dict[str, Any]:
    source_path = url.database or "snmp_monitor.db"
    source = Path(source_path)
    if not source.is_absolute():
        source = Path.cwd() / source
    if not source.exists():
        raise FileNotFoundError(f"SQLite 数据库不存在: {source}")
    with sqlite3.connect(str(source)) as src, sqlite3.connect(str(dest)) as dst:
        src.backup(dst)
    return {"method": "sqlite-backup", "source": str(source)}


def _cmd_backup(cmd: List[str], dest: Path, env: Optional[dict] = None) -> Dict[str, Any]:
    with dest.open("wb") as output:
        proc = subprocess.run(
            cmd, stdout=output, stderr=subprocess.PIPE,
            env=env, timeout=600, check=False,
        )
    if proc.returncode != 0:
        error = proc.stderr.decode("utf-8", errors="replace")[-500:]
        dest.unlink(missing_ok=True)
        raise RuntimeError(error or f"备份命令退出码 {proc.returncode}")
    return {"method": cmd[0]}


def _logical_backup(dest: Path) -> Dict[str, Any]:
    """回退方案：所有表导出为 JSON（按表分组）"""
    payload: Dict[str, Any] = {
        "format": "snmp-monitor-logical-backup",
        "exported_at": datetime.utcnow().isoformat(),
        "tables": {},
    }
    with engine.connect() as conn:
        for table in Base.metadata.sorted_tables:
            rows = conn.execute(table.select()).mappings().all()
            payload["tables"][table.name] = [
                json.loads(json.dumps(dict(row), ensure_ascii=False, default=str))
                for row in rows
            ]
    dest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return {"method": "logical-json"}


def create_backup(reason: str = "manual", retention: int = 7) -> Dict[str, Any]:
    """创建一次备份，返回文件信息；失败抛异常"""
    directory = backup_dir()
    url = make_url(Config.DATABASE_URL)
    driver = (url.drivername or "").lower()
    stamp = _timestamp()

    try:
        if driver.startswith("sqlite"):
            dest = directory / f"{BACKUP_PREFIX}{stamp}.db"
            info = _sqlite_backup(url, dest)
        elif driver.startswith("mysql"):
            dest = directory / f"{BACKUP_PREFIX}{stamp}.sql"
            cmd = [
                "mysqldump",
                "-h", url.host or "127.0.0.1",
                "-P", str(url.port or 3306),
                "-u", url.username or "root",
            ]
            if url.password:
                cmd.append(f"-p{url.password}")
            cmd += [
                "--single-transaction", "--quick", "--lock-tables=false",
                url.database or "",
            ]
            try:
                info = _cmd_backup(cmd, dest)
            except (FileNotFoundError, RuntimeError) as exc:
                logger.warning("mysqldump 不可用，回退逻辑备份: %s", exc)
                dest = directory / f"{BACKUP_PREFIX}{stamp}.json"
                info = _logical_backup(dest)
        elif driver.startswith("postgresql"):
            dest = directory / f"{BACKUP_PREFIX}{stamp}.sql"
            cmd = ["pg_dump", "-h", url.host or "127.0.0.1",
                   "-p", str(url.port or 5432), "-U", url.username or "postgres",
                   "--no-owner", "--clean", "--if-exists", url.database or ""]
            env = dict(os.environ)
            if url.password:
                env["PGPASSWORD"] = url.password
            try:
                info = _cmd_backup(cmd, dest, env)
            except (FileNotFoundError, RuntimeError) as exc:
                logger.warning("pg_dump 不可用，回退逻辑备份: %s", exc)
                dest = directory / f"{BACKUP_PREFIX}{stamp}.json"
                info = _logical_backup(dest)
        else:
            dest = directory / f"{BACKUP_PREFIX}{stamp}.json"
            info = _logical_backup(dest)

        retention = max(1, int(retention or 1))
        files = _backup_files()
        for old in files[retention:]:
            try:
                old.unlink()
            except OSError as exc:  # noqa: BLE001
                logger.warning("清理旧备份失败 %s: %s", old, exc)

        result = _file_info(dest)
        result.update(info)
        result["reason"] = reason
        logger.info("数据库备份完成: %s（%s，%d 字节）", dest.name, info.get("method"), result["size"])
        return result
    except Exception:
        logger.exception("数据库备份失败")
        raise


def delete_backup(name: str) -> bool:
    """删除指定备份（只允许备份目录下的 db-backup-* 文件）"""
    safe = Path(name).name
    if not safe.startswith(BACKUP_PREFIX) or Path(safe).suffix not in ALLOWED_SUFFIX:
        raise ValueError("非法的备份文件名")
    path = backup_dir() / safe
    if not path.exists():
        return False
    path.unlink()
    return True


def is_due(interval_hours: int) -> bool:
    if interval_hours <= 0:
        return False
    latest = latest_backup()
    if not latest:
        return True
    try:
        from datetime import timedelta

        created = datetime.fromisoformat(latest["created_at"])
        return datetime.now() - created >= timedelta(hours=interval_hours)
    except (ValueError, TypeError):
        return True
