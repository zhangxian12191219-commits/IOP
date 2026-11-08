"""日志接口：转发状态 / 发送测试 / 最近日志查看"""
import logging
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from ..config import Config
from ..services import log_forward

router = APIRouter(prefix="/api/logs", tags=["日志"])

logger = logging.getLogger(__name__)


@router.get("/forward/status")
def forward_status():
    """日志转发状态与统计"""
    forwarder = log_forward.forwarder
    return {
        "settings": forwarder.describe(),
        "stats": dict(forwarder.stats),
        "queue_size": forwarder._queue.qsize(),  # noqa: SLF001
        "queue_capacity": log_forward.MAX_QUEUE,
        "app_log_file": str(Path(Config.LOG_DIR) / "backend.log"),
    }


@router.post("/forward/test")
def forward_test():
    """发送一条测试日志到当前配置的转发目标（不受启用开关限制）"""
    forwarder = log_forward.forwarder
    if not forwarder.config:
        raise HTTPException(status_code=400, detail="尚未加载日志转发配置")
    result = forwarder.send_test()
    if result.get("ok"):
        logger.info("日志转发测试成功: type=%s", result.get("type"))
    else:
        logger.warning("日志转发测试失败: %s", result.get("error"))
    return result


@router.get("/recent")
def recent_logs(
    lines: int = Query(200, ge=10, le=2000),
    level: Optional[str] = Query(None, description="按级别过滤：ERROR/WARNING/INFO"),
    keyword: Optional[str] = Query(None, description="关键字过滤"),
):
    """读取后端日志文件最近的若干行（用于页面排查，不代替专业日志平台）"""
    log_file = Path(Config.LOG_DIR) / "backend.log"
    if not log_file.exists():
        return {"lines": [], "file": str(log_file), "size": 0, "note": "日志文件尚未生成"}

    # 只读取文件尾部，避免大文件占内存
    max_bytes = 512 * 1024
    size = log_file.stat().st_size
    with log_file.open("rb") as fh:
        if size > max_bytes:
            fh.seek(-max_bytes, 2)
            fh.readline()  # 丢弃可能被截断的首行
        raw = fh.read()
    text = raw.decode("utf-8", errors="replace")

    level_upper = (level or "").upper()
    items = []
    for line in text.splitlines():
        if level_upper and f"[{level_upper}]" not in line:
            continue
        if keyword and keyword not in line:
            continue
        items.append(line)
    items = items[-lines:]

    return {
        "lines": items,
        "file": str(log_file),
        "size": size,
        "total_matched": len(items),
    }
