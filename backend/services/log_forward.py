"""日志转发服务

支持把系统日志转发到：
- syslog（UDP / TCP，RFC5424 / RFC3164）
- HTTP Webhook（JSON 批量 POST，自定义请求头）
- 本地文件（追加写）

特性：
- 异步队列 + 后台发送线程，日志发送绝不阻塞业务请求
- 队列满时丢弃并计数，失败重试由下一批自然完成
- 运行统计：已发送 / 失败 / 丢弃 / 最后错误 / 最后发送时间
- 配置热生效：系统配置保存后立即应用，无需重启
"""
import json
import logging
import logging.handlers
import queue
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

# 日志级别 → syslog severity
SEVERITY = {
    "CRITICAL": 2, "ERROR": 3, "WARNING": 4,
    "INFO": 6, "DEBUG": 7, "NOTSET": 6,
}

FACILITIES = {
    "kern": 0, "user": 1, "mail": 2, "daemon": 3, "auth": 4,
    "syslog": 5, "lpr": 6, "news": 7, "cron": 9, "authpriv": 10,
    "ftp": 11, "local0": 16, "local1": 17, "local2": 18, "local3": 19,
    "local4": 20, "local5": 21, "local6": 22, "local7": 23,
}

LEVEL_NAMES = {"DEBUG": 10, "INFO": 20, "WARNING": 30, "ERROR": 40, "CRITICAL": 50}

MAX_QUEUE = 5000


class LogForwarder:
    """日志转发器（单例使用）"""

    def __init__(self):
        self.enabled = False
        self.target_type = "syslog"          # syslog / http / file
        self.min_level = 20
        self.config: Dict[str, Any] = {}
        self._queue: "queue.Queue[Dict[str, Any]]" = queue.Queue(maxsize=MAX_QUEUE)
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.stats = {
            "sent": 0,
            "failed": 0,
            "dropped": 0,
            "last_error": None,
            "last_sent_at": None,
            "last_test": None,
        }
        self._tcp_sock: Optional[socket.socket] = None

    # ---------- 配置 ----------
    def apply(self, cfg: Dict[str, Any]) -> None:
        """应用配置（可热更新）"""
        with self._lock:
            self.enabled = bool(cfg.get("log_forward_enabled"))
            self.target_type = str(cfg.get("log_forward_type") or "syslog").lower()
            level_name = str(cfg.get("log_forward_min_level") or "INFO").upper()
            self.min_level = LEVEL_NAMES.get(level_name, 20)
            self.config = dict(cfg)
            self._close_tcp()

        if self.enabled and (self._thread is None or not self._thread.is_alive()):
            self._stop.clear()
            self._thread = threading.Thread(
                target=self._worker, name="log-forwarder", daemon=True
            )
            self._thread.start()
            logger.info(
                "日志转发已启用: type=%s min_level=%s", self.target_type, level_name
            )
        elif not self.enabled:
            # 关闭时停止后台线程并清空积压，避免恢复后补发旧日志
            if self._thread is not None and self._thread.is_alive():
                self._stop.set()
            self._thread = None
            while True:
                try:
                    self._queue.get_nowait()
                except queue.Empty:
                    break
            logger.info("日志转发已关闭")

    def describe(self) -> Dict[str, Any]:
        cfg = self.config or {}
        return {
            "enabled": self.enabled,
            "type": self.target_type,
            "min_level": logging.getLevelName(self.min_level),
            "syslog": {
                "host": cfg.get("log_forward_host") or "",
                "port": cfg.get("log_forward_port") or 514,
                "protocol": cfg.get("log_forward_protocol") or "udp",
                "format": cfg.get("log_forward_format") or "rfc5424",
                "facility": cfg.get("log_forward_facility") or "local0",
                "app_name": cfg.get("log_forward_app_name") or "snmp-nms",
            },
            "http": {
                "url": cfg.get("log_forward_http_url") or "",
                "headers": cfg.get("log_forward_http_headers") or "",
            },
            "file": {"path": cfg.get("log_forward_file_path") or ""},
        }

    # ---------- 入队 ----------
    def enqueue(self, record: logging.LogRecord) -> None:
        if not self.enabled or record.levelno < self.min_level:
            return
        item = {
            "time": datetime.fromtimestamp(record.created).astimezone().isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "host": socket.gethostname(),
        }
        if record.exc_info:
            try:
                item["exception"] = logging.Formatter().formatException(record.exc_info)
            except Exception:  # noqa: BLE001
                pass
        try:
            self._queue.put_nowait(item)
        except queue.Full:
            with self._lock:
                self.stats["dropped"] += 1

    # ---------- 后台线程 ----------
    def _worker(self) -> None:
        while not self._stop.is_set():
            batch: List[Dict[str, Any]] = []
            try:
                first = self._queue.get(timeout=1.0)
                batch.append(first)
            except queue.Empty:
                continue

            # 攒批：最多 50 条或 200ms 内
            deadline = time.time() + 0.2
            while len(batch) < 50 and time.time() < deadline:
                try:
                    batch.append(self._queue.get_nowait())
                except queue.Empty:
                    break

            try:
                self._send_batch(batch)
                with self._lock:
                    self.stats["sent"] += len(batch)
                    self.stats["last_sent_at"] = datetime.now().isoformat(timespec="seconds")
            except Exception as exc:  # noqa: BLE001
                with self._lock:
                    self.stats["failed"] += len(batch)
                    self.stats["last_error"] = f"{type(exc).__name__}: {exc}"
                # 失败过多时退避，避免刷屏
                time.sleep(1)

    def _send_batch(self, batch: List[Dict[str, Any]]) -> None:
        if not batch:
            return
        if self.target_type == "http":
            self._send_http(batch)
        elif self.target_type == "file":
            self._send_file(batch)
        else:
            self._send_syslog(batch)

    # ---------- 发送实现 ----------
    def _syslog_pri(self, level: str) -> int:
        facility = self.config.get("log_forward_facility") or "local0"
        return FACILITIES.get(facility, 16) * 8 + SEVERITY.get(level, 6)

    def _format_syslog(self, item: Dict[str, Any]) -> str:
        fmt = str(self.config.get("log_forward_format") or "rfc5424").lower()
        app = str(self.config.get("log_forward_app_name") or "snmp-nms")
        hostname = item.get("host") or socket.gethostname()
        pri = self._syslog_pri(item.get("level", "INFO"))
        msg = f"{item.get('logger')}: {item.get('message')}"
        if item.get("exception"):
            msg += " | " + item["exception"].replace("\n", " ")[:1000]

        if fmt == "rfc3164":
            ts = datetime.now().strftime("%b %d %H:%M:%S")
            return f"<{pri}>{ts} {hostname} {app}: {msg}"

        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")
        pid = os_getpid()
        return f"<{pri}>1 {ts} {hostname} {app} {pid} - - {msg}"

    def _send_syslog(self, batch: List[Dict[str, Any]]) -> None:
        host = str(self.config.get("log_forward_host") or "")
        port = int(self.config.get("log_forward_port") or 514)
        proto = str(self.config.get("log_forward_protocol") or "udp").lower()
        if not host:
            raise ValueError("未配置 syslog 服务器地址")

        lines = [self._format_syslog(item) for item in batch]

        if proto == "tcp":
            self._send_tcp(host, port, lines)
            return

        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(5)
            for line in lines:
                sock.sendto(line.encode("utf-8")[:60000], (host, port))

    def _send_tcp(self, host: str, port: int, lines: List[str]) -> None:
        try:
            if self._tcp_sock is None:
                self._tcp_sock = socket.create_connection((host, port), timeout=5)
                self._tcp_sock.settimeout(5)
            payload = b"".join((line + "\n").encode("utf-8") for line in lines)
            self._tcp_sock.sendall(payload)
        except Exception:
            self._close_tcp()
            raise

    def _close_tcp(self) -> None:
        sock = self._tcp_sock
        self._tcp_sock = None
        if sock is not None:
            try:
                sock.close()
            except Exception:  # noqa: BLE001
                pass

    def _http_headers(self) -> Dict[str, str]:
        raw = self.config.get("log_forward_http_headers") or ""
        headers = {"Content-Type": "application/json"}
        if not raw.strip():
            return headers
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                headers.update({str(k): str(v) for k, v in parsed.items()})
        except json.JSONDecodeError:
            # 兼容 "Key: Value" 每行一条的写法
            for line in raw.splitlines():
                if ":" in line:
                    key, value = line.split(":", 1)
                    headers[key.strip()] = value.strip()
        return headers

    def _send_http(self, batch: List[Dict[str, Any]]) -> None:
        url = str(self.config.get("log_forward_http_url") or "").strip()
        if not url:
            raise ValueError("未配置 HTTP 接收地址")
        payload = {
            "app": "snmp-monitor",
            "host": socket.gethostname(),
            "sent_at": datetime.now(timezone.utc).isoformat(),
            "logs": batch,
        }
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")

        import urllib.request

        request = urllib.request.Request(
            url, data=data, headers=self._http_headers(), method="POST"
        )
        with urllib.request.urlopen(request, timeout=8) as response:
            if response.status >= 400:
                raise RuntimeError(f"HTTP {response.status}")

    def _send_file(self, batch: List[Dict[str, Any]]) -> None:
        path = str(self.config.get("log_forward_file_path") or "").strip()
        if not path:
            raise ValueError("未配置文件路径")
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        with target.open("a", encoding="utf-8") as fh:
            for item in batch:
                fh.write(json.dumps(item, ensure_ascii=False) + "\n")

    # ---------- 测试 ----------
    def send_test(self) -> Dict[str, Any]:
        """同步发送一条测试日志，返回结果（不受启用开关限制）"""
        item = {
            "time": datetime.now().astimezone().isoformat(),
            "level": "INFO",
            "logger": "snmp-monitor.log-forward.test",
            "message": f"日志转发测试 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            "host": socket.gethostname(),
        }
        started = time.time()
        try:
            self._send_batch([item])
            elapsed = round((time.time() - started) * 1000, 1)
            result = {
                "ok": True,
                "type": self.target_type,
                "elapsed_ms": elapsed,
                "message": "测试日志发送成功",
            }
            with self._lock:
                self.stats["last_test"] = {
                    "ok": True, "at": datetime.now().isoformat(timespec="seconds"),
                    "elapsed_ms": elapsed,
                }
            return result
        except Exception as exc:  # noqa: BLE001
            result = {
                "ok": False,
                "type": self.target_type,
                "error": f"{type(exc).__name__}: {exc}",
                "message": "测试日志发送失败",
            }
            with self._lock:
                self.stats["last_test"] = {
                    "ok": False, "at": datetime.now().isoformat(timespec="seconds"),
                    "error": result["error"],
                }
            return result

    def shutdown(self) -> None:
        self._stop.set()
        self._close_tcp()


def os_getpid() -> int:
    import os

    return os.getpid()


forwarder = LogForwarder()


class ForwardHandler(logging.Handler):
    """把日志记录转交给转发器（不阻塞）"""

    def emit(self, record: logging.LogRecord) -> None:  # noqa: D102
        try:
            forwarder.enqueue(record)
        except Exception:  # noqa: BLE001
            pass


_handler: Optional[ForwardHandler] = None


def install_handler() -> None:
    """安装日志转发 Handler（幂等），同时覆盖 uvicorn 访问日志"""
    global _handler
    if _handler is not None:
        return
    _handler = ForwardHandler()
    _handler.setLevel(logging.DEBUG)

    targets = [logging.getLogger()]
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        targets.append(logging.getLogger(name))
    for target in targets:
        target.addHandler(_handler)
    logger.info("日志转发 Handler 已安装")


def apply_config(cfg: Dict[str, Any]) -> None:
    """从系统配置应用转发设置"""
    forwarder.apply(cfg)
