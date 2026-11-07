"""缓存服务（Redis 优先，未配置/连接失败时自动回退内存缓存）

用途：拓扑、总览、大屏等聚合接口在设备量大时避免重复计算与压垮数据库。
- REDIS_URL 可用时使用 Redis（多进程/多实例共享）
- 未配置或连接失败时使用进程内 TTL 缓存（单实例足够）
- 值统一 JSON 序列化，接口可返回 X-Cache: HIT/MISS 便于排查
"""
import json
import logging
import threading
import time
from typing import Any, Dict, Optional, Tuple

from ..config import Config

logger = logging.getLogger("snmp-monitor.cache")


class Cache:
    """TTL 缓存（Redis / 内存自动回退）"""

    def __init__(self):
        self.enabled = Config.CACHE_ENABLED
        self.redis_url = Config.REDIS_URL
        self.ttl_topology = Config.CACHE_TTL_TOPOLOGY
        self.ttl_dashboard = Config.CACHE_TTL_DASHBOARD
        self._redis = None
        self._redis_tried = False
        self._redis_ok = False
        self._memory: Dict[str, Tuple[float, str]] = {}
        self._lock = threading.Lock()
        self._stats = {"hits": 0, "misses": 0, "errors": 0}

    def reconfigure(
        self,
        enabled: bool,
        url: str = "",
        ttl_topology: int = 5,
        ttl_dashboard: int = 3,
    ) -> None:
        """应用 Web 系统配置中的缓存参数，重建 Redis 懒连接。"""
        self.enabled = bool(enabled)
        self.redis_url = (url or "").strip()
        self.ttl_topology = max(1, int(ttl_topology or 5))
        self.ttl_dashboard = max(1, int(ttl_dashboard or 3))
        self._redis = None
        self._redis_tried = False
        self._redis_ok = False
        with self._lock:
            self._memory.clear()
        logger.info(
            "缓存配置已应用: enabled=%s mode=%s",
            self.enabled,
            "redis" if self.redis_url else "memory",
        )

    def test_connection(self, url: Optional[str] = None) -> Dict[str, Any]:
        """测试 Redis 连接，不改变当前缓存实例。"""
        target = (url or self.redis_url or "").strip()
        if not target:
            return {"ok": False, "backend": "memory", "error": "未配置 Redis 地址，当前使用内存缓存"}
        started = time.perf_counter()
        client = None
        try:
            import redis

            client = redis.Redis.from_url(
                target,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            client.ping()
            info = client.info()
            return {
                "ok": True,
                "backend": "redis",
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "version": info.get("redis_version"),
                "clients": info.get("connected_clients"),
            }
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False,
                "backend": "memory",
                "latency_ms": round((time.perf_counter() - started) * 1000, 1),
                "error": str(exc),
            }
        finally:
            if client is not None:
                try:
                    client.close()
                except Exception:  # noqa: BLE001
                    pass

    # ---------- Redis 连接（懒加载） ----------
    def _ensure_redis(self):
        if self._redis_tried:
            return
        self._redis_tried = True
        if not self.redis_url:
            logger.info("未配置 REDIS_URL，使用内存缓存")
            return
        try:
            import redis

            client = redis.Redis.from_url(
                self.redis_url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            client.ping()
            self._redis = client
            self._redis_ok = True
            logger.info("Redis 缓存已启用: %s", self.redis_url)
        except Exception as exc:  # noqa: BLE001
            self._redis = None
            self._redis_ok = False
            logger.warning("Redis 不可用，回退内存缓存: %s", exc)

    @property
    def backend(self) -> str:
        if not self.enabled:
            return "disabled"
        self._ensure_redis()
        return "redis" if self._redis_ok else "memory"

    # ---------- 基础操作 ----------
    def get(self, key: str) -> Tuple[Optional[Any], bool]:
        """返回 (值, 是否命中)"""
        if not self.enabled:
            return None, False
        self._ensure_redis()

        if self._redis_ok and self._redis is not None:
            try:
                raw = self._redis.get(key)
                if raw is None:
                    self._stats["misses"] += 1
                    return None, False
                self._stats["hits"] += 1
                return json.loads(raw), True
            except Exception as exc:  # noqa: BLE001
                self._stats["errors"] += 1
                logger.debug("Redis 读取失败，回退内存: %s", exc)

        with self._lock:
            item = self._memory.get(key)
            if not item:
                self._stats["misses"] += 1
                return None, False
            expire_at, raw = item
            if expire_at < time.time():
                self._memory.pop(key, None)
                self._stats["misses"] += 1
                return None, False
            self._stats["hits"] += 1
            return json.loads(raw), True

    def set(self, key: str, value: Any, ttl: int) -> None:
        if not self.enabled or ttl <= 0:
            return
        try:
            raw = json.dumps(value, ensure_ascii=False, default=str)
        except Exception as exc:  # noqa: BLE001
            logger.debug("缓存序列化失败 %s: %s", key, exc)
            return

        self._ensure_redis()
        if self._redis_ok and self._redis is not None:
            try:
                self._redis.setex(key, ttl, raw)
                return
            except Exception as exc:  # noqa: BLE001
                self._stats["errors"] += 1
                logger.debug("Redis 写入失败，回退内存: %s", exc)

        now = time.time()
        with self._lock:
            # 简单清理过期项，避免内存无限增长
            if len(self._memory) > 2000:
                expired = [k for k, (exp, _) in self._memory.items() if exp < now]
                for k in expired:
                    self._memory.pop(k, None)
                if len(self._memory) > 2000:
                    for k in list(self._memory.keys())[: len(self._memory) - 2000]:
                        self._memory.pop(k, None)
            self._memory[key] = (now + ttl, raw)

    def delete(self, key: str) -> None:
        if not self.enabled:
            return
        self._ensure_redis()
        if self._redis_ok and self._redis is not None:
            try:
                self._redis.delete(key)
            except Exception:  # noqa: BLE001
                pass
        with self._lock:
            self._memory.pop(key, None)

    def delete_prefix(self, prefix: str) -> int:
        """按前缀清理（用于写操作后主动失效）"""
        if not self.enabled:
            return 0
        self._ensure_redis()
        removed = 0
        if self._redis_ok and self._redis is not None:
            try:
                keys = list(self._redis.scan_iter(match=f"{prefix}*", count=500))
                if keys:
                    removed += int(self._redis.delete(*keys))
            except Exception as exc:  # noqa: BLE001
                logger.debug("Redis 前缀清理失败: %s", exc)
        with self._lock:
            for key in [k for k in self._memory if k.startswith(prefix)]:
                self._memory.pop(key, None)
                removed += 1
        return removed

    def get_or_set(self, key: str, ttl: int, producer) -> Tuple[Any, bool]:
        """读取缓存；未命中时调用 producer() 计算并写入"""
        value, hit = self.get(key)
        if hit:
            return value, True
        value = producer()
        self.set(key, value, ttl)
        return value, False

    def info(self) -> Dict[str, Any]:
        backend = self.backend
        data: Dict[str, Any] = {
            "enabled": self.enabled,
            "backend": backend,
            "redis_url_set": bool(self.redis_url),
            "stats": dict(self._stats),
        }
        if backend == "memory":
            with self._lock:
                data["memory_keys"] = len(self._memory)
        if backend == "redis" and self._redis is not None:
            try:
                info = self._redis.info()
                data["redis_version"] = info.get("redis_version")
                data["redis_clients"] = info.get("connected_clients")
            except Exception:  # noqa: BLE001
                pass
        data["ttl"] = {
            "topology": self.ttl_topology,
            "dashboard": self.ttl_dashboard,
        }
        return data

    def clear(self) -> int:
        removed = self.delete_prefix("")
        with self._lock:
            self._memory.clear()
        return removed


cache = Cache()


# ---------- 业务缓存 key ----------
KEY_TOPOLOGY = "topology:graph"
KEY_DASHBOARD = "dashboard:stats"


def invalidate_topology() -> None:
    cache.delete_prefix("topology:")


def invalidate_dashboard() -> None:
    cache.delete(KEY_DASHBOARD)


def invalidate_all() -> None:
    invalidate_topology()
    invalidate_dashboard()
