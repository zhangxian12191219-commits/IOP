"""互联网时间辅助：用于版权年份等需要与公网时间保持一致的显示。"""
from __future__ import annotations

import email.utils
import logging
import threading
import time
from datetime import datetime, timezone
from typing import Optional
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

_CACHE_SECONDS = 3600
_cache: Optional[int] = None
_cache_at = 0.0
_lock = threading.Lock()
_SOURCES = ("https://www.baidu.com", "https://www.aliyun.com")


def _timezone(name: str):
    try:
        return ZoneInfo(name or "Asia/Shanghai")
    except Exception:  # noqa: BLE001
        return timezone.utc


def _http_date() -> Optional[datetime]:
    for url in _SOURCES:
        try:
            request = Request(url, method="HEAD", headers={"User-Agent": "SNMP-Monitor/1.0"})
            with urlopen(request, timeout=2) as response:
                raw = response.headers.get("Date")
            if not raw:
                continue
            parsed = email.utils.parsedate_to_datetime(raw)
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed
        except Exception as exc:  # noqa: BLE001
            logger.debug("获取互联网时间失败 %s: %s", url, exc)
    return None


def internet_year(timezone_name: str = "Asia/Shanghai") -> int:
    """返回互联网时间对应的年份；无公网时回退本机当前年份。"""
    global _cache, _cache_at
    now_mono = time.monotonic()
    if _cache is not None and now_mono - _cache_at < _CACHE_SECONDS:
        return _cache
    with _lock:
        if _cache is not None and time.monotonic() - _cache_at < _CACHE_SECONDS:
            return _cache
        utc_now = datetime.now(timezone.utc)
        internet_now = _http_date()
        if internet_now is None:
            year = utc_now.astimezone(_timezone(timezone_name)).year
        else:
            year = internet_now.astimezone(_timezone(timezone_name)).year
        _cache = int(year)
        _cache_at = time.monotonic()
        return _cache


def invalidate_cache() -> None:
    global _cache, _cache_at
    with _lock:
        _cache = None
        _cache_at = 0.0
