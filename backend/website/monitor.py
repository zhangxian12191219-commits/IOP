"""网站监控模块 - HTTP/HTTPS 存活探测、TCP 端口探测、ICMP Ping

提供:
- WebsiteMonitor.check_http()   HTTP/HTTPS 探测（状态码、关键字、耗时分解）
- WebsiteMonitor.check_tcp()    TCP 端口连通性
- WebsiteMonitor.check_ping()   ICMP Ping
- WebsiteMonitor.check_ip()     IP 可用性
- WebsiteMonitor.check_all()    按 target.monitor_type 分发
"""
import asyncio
import locale
import logging
import os
import re
import socket
import ssl
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse, urlsplit, urlunsplit, parse_qsl, urlencode

import aiohttp

try:
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.x509.oid import NameOID
    HAS_X509 = True
except ImportError:  # 证书明细解析为可选能力
    x509 = None
    hashes = None
    NameOID = None
    HAS_X509 = False

logger = logging.getLogger(__name__)

try:
    import dns.resolver
    HAS_DNS = True
except ImportError:  # dns 解析为可选能力
    dns = None
    HAS_DNS = False


class WebsiteMonitor:
    """网站 / IP 探测器"""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.session: Optional[aiohttp.ClientSession] = None

    async def start(self) -> None:
        if self.session and not self.session.closed:
            return
        connector = aiohttp.TCPConnector(ssl=None, limit=0, enable_cleanup_closed=True)
        self.session = aiohttp.ClientSession(connector=connector)

    async def stop(self) -> None:
        if self.session and not self.session.closed:
            await self.session.close()
        self.session = None

    # ---------- HTTPS 证书 ----------
    async def check_certificate(self, host: str, port: int = 443,
                                timeout: int = 10) -> Dict[str, Any]:
        """读取 HTTPS 证书明细（即使证书已过期也尽量读取）。

        使用不校验证书的临时 TLS 连接，仅用于读取证书；网站存活校验仍由
        check_http 使用正常校验逻辑完成。
        """
        result: Dict[str, Any] = {
            "host": host,
            "port": port,
            "owner": "",
            "subject_organization": "",
            "subject_common_name": "",
            "issuer": "",
            "issuer_organization": "",
            "valid_from": None,
            "valid_to": None,
            "days_left": None,
            "serial_number": "",
            "san": [],
            "status": "unknown",
            "error": "",
        }
        if not host:
            result["error"] = "证书域名不能为空"
            return result
        if not HAS_X509:
            result["error"] = "服务端缺少 cryptography 依赖，无法解析证书"
            return result

        writer = None
        try:
            connect_host = host.encode("idna").decode("ascii")
            context = ssl.create_default_context()
            context.check_hostname = False
            context.verify_mode = ssl.CERT_NONE
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    connect_host, int(port or 443),
                    ssl=context, server_hostname=connect_host,
                ),
                timeout=max(2, min(int(timeout or 10), 10)),
            )
            ssl_object = writer.get_extra_info("ssl_object")
            der = ssl_object.getpeercert(binary_form=True) if ssl_object else None
            if not der:
                raise ValueError("未能读取服务器证书")

            cert = x509.load_der_x509_certificate(der)

            def first_attr(name, oid) -> str:
                attrs = name.get_attributes_for_oid(oid) if name else []
                return str(attrs[0].value).strip() if attrs else ""

            subject_org = first_attr(cert.subject, NameOID.ORGANIZATION_NAME)
            subject_cn = first_attr(cert.subject, NameOID.COMMON_NAME)
            issuer_org = first_attr(cert.issuer, NameOID.ORGANIZATION_NAME)
            issuer_cn = first_attr(cert.issuer, NameOID.COMMON_NAME)

            not_before = getattr(cert, "not_valid_before_utc", None)
            not_after = getattr(cert, "not_valid_after_utc", None)
            if not_before is None:
                not_before = cert.not_valid_before.replace(tzinfo=timezone.utc)
            if not_after is None:
                not_after = cert.not_valid_after.replace(tzinfo=timezone.utc)
            if not_before.tzinfo is None:
                not_before = not_before.replace(tzinfo=timezone.utc)
            if not_after.tzinfo is None:
                not_after = not_after.replace(tzinfo=timezone.utc)

            now = datetime.now(timezone.utc)
            days_left = (not_after - now).days
            san = []
            try:
                ext = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName)
                san = ext.value.get_values_for_type(x509.DNSName)
            except Exception:  # 没有 SAN 扩展时不视为失败
                san = []

            result.update({
                "owner": subject_org or subject_cn or host,
                "subject_organization": subject_org,
                "subject_common_name": subject_cn,
                "issuer": issuer_org or issuer_cn or "",
                "issuer_organization": issuer_org,
                "valid_from": not_before.isoformat(),
                "valid_to": not_after.isoformat(),
                "days_left": days_left,
                "serial_number": format(cert.serial_number, "X"),
                "san": san,
                "status": "expired" if not_after <= now else "valid",
                "error": "",
            })
        except asyncio.TimeoutError:
            result["error"] = f"读取证书超时({timeout}s)"
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            result["error"] = str(exc)
        finally:
            if writer is not None:
                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass
        return result

    # ---------- HTTP / HTTPS ----------
    @staticmethod
    def _cache_busted_url(url: str, interval: int) -> str:
        """按固定时间桶替换缓存参数，避免被安全设备缓存/误拦截。"""
        seconds = max(0, int(interval or 0))
        if seconds <= 0:
            return url
        try:
            parts = urlsplit(url)
            query = [
                (key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
                if key != "_nms_cache"
            ]
            query.append(("_nms_cache", str(int(time.time() // seconds))))
            return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))
        except Exception:  # noqa: BLE001
            return url

    @staticmethod
    def _status_matches(status: int, expected_statuses: Optional[str], expected_status: int) -> bool:
        spec = str(expected_statuses or "").strip()
        if not spec:
            return not expected_status or status == int(expected_status)
        for token in spec.replace("，", ",").split(","):
            token = token.strip()
            if not token:
                continue
            if "-" in token:
                try:
                    start, end = [int(value.strip()) for value in token.split("-", 1)]
                    if start <= status <= end:
                        return True
                except (TypeError, ValueError):
                    continue
            else:
                try:
                    if status == int(token):
                        return True
                except (TypeError, ValueError):
                    continue
        return False

    async def check_http(
        self,
        url: str,
        method: str = "GET",
        expected_status: int = 200,
        expected_keywords: Optional[List[str]] = None,
        timeout: int = 10,
        collect_cert: bool = True,
        ignore_https_errors: bool = True,
        cache_bust_seconds: int = 0,
        expected_statuses: Optional[str] = None,
        cert_extra_hosts: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """HTTP/HTTPS 存活探测

        Returns dict: is_alive / status_code / response_time / dns_resolve_time /
                      tcp_connect_time / ssl_time / content_length / final_ip / http_error
        """
        result: Dict[str, Any] = {
            "is_alive": False,
            "status_code": 0,
            "response_time": 0.0,
            "dns_resolve_time": 0.0,
            "tcp_connect_time": 0.0,
            "ssl_time": 0.0,
            "content_length": 0,
            "final_ip": "",
            "http_error": "",
        }

        if not url:
            result["http_error"] = "URL 为空"
            return result
        if "://" not in url:
            url = "http://" + url
        request_url = self._cache_busted_url(url, cache_bust_seconds)

        start_time = time.time()

        if self.session is None or self.session.closed:
            await self.start()

        try:
            # 1) DNS 解析
            dns_start = time.time()
            hostname = urlparse(request_url).hostname
            if hostname:
                try:
                    if HAS_DNS:
                        records = dns.resolver.resolve(hostname, "A")
                        ips = [str(r) for r in records]
                    else:
                        infos = await asyncio.get_running_loop().getaddrinfo(
                            hostname, None, family=socket.AF_INET
                        )
                        ips = [i[4][0] for i in infos]
                    result["final_ip"] = ips[0] if ips else ""
                except Exception as exc:  # noqa: BLE001
                    result["dns_error"] = f"DNS解析失败: {exc}"
            result["dns_resolve_time"] = round((time.time() - dns_start) * 1000, 2)

            # 2) SSL 上下文：按目标选择是否校验证书
            ssl_context = None
            if request_url.lower().startswith("https://"):
                ssl_start = time.time()
                if ignore_https_errors:
                    ssl_context = False
                else:
                    ssl_context = ssl.create_default_context()
                result["ssl_time"] = round((time.time() - ssl_start) * 1000, 2)

            # 3) 发起请求
            request_start = time.time()
            headers = {"User-Agent": "SNMP-NMS-Monitor/1.1"}
            if cache_bust_seconds:
                headers["Cache-Control"] = "no-cache, no-store, max-age=0"
                headers["Pragma"] = "no-cache"
            async with self.session.request(
                method.upper(),
                request_url,
                timeout=aiohttp.ClientTimeout(total=timeout),
                ssl=ssl_context,
                allow_redirects=True,
                headers=headers,
            ) as response:
                body = await response.read()
                result["status_code"] = response.status
                result["content_length"] = len(body)
                result["tcp_connect_time"] = round(
                    (time.time() - request_start) * 1000, 2
                )
                result["response_time"] = round((time.time() - start_time) * 1000, 2)

                if expected_keywords:
                    text = body.decode("utf-8", errors="ignore").lower()
                    for keyword in expected_keywords:
                        if keyword and keyword.strip().lower() not in text:
                            result["http_error"] = f"响应中未找到关键字: {keyword}"
                            break

                if not self._status_matches(response.status, expected_statuses, expected_status):
                    if expected_statuses:
                        result["http_error"] = (
                            f"状态码 {response.status} 不在允许范围 {expected_statuses}"
                        )
                    else:
                        result["http_error"] = (
                            f"期望状态码 {expected_status}, 实际 {response.status}"
                        )
                elif not result["http_error"]:
                    result["is_alive"] = True

        except asyncio.TimeoutError:
            result["http_error"] = f"请求超时({timeout}s)"
            result["response_time"] = round((time.time() - start_time) * 1000, 2)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            result["http_error"] = str(exc)
            result["response_time"] = round((time.time() - start_time) * 1000, 2)

        # HTTPS 证书信息单独读取，网页请求失败（例如证书过期）时仍可得到到期信息
        if collect_cert and request_url.lower().startswith("https://"):
            parsed = urlparse(request_url)
            if parsed.hostname:
                try:
                    primary = await self.check_certificate(
                        parsed.hostname, parsed.port or 443, timeout
                    )
                    extras = []
                    seen = {parsed.hostname}
                    for host in (cert_extra_hosts or []):
                        host = str(host or "").strip()
                        if not host or host in seen:
                            continue
                        seen.add(host)
                        extras.append(await self.check_certificate(host, 443, timeout))
                    if extras:
                        primary["extra_certificates"] = extras
                    result["cert_info"] = primary
                except asyncio.CancelledError:
                    raise
                except Exception as exc:  # noqa: BLE001
                    result["cert_info"] = {"error": str(exc)}

        return result

    # ---------- TCP ----------
    async def check_tcp(self, host: str, port: int, timeout: int = 5) -> Dict[str, Any]:
        """TCP 端口连通性探测"""
        result: Dict[str, Any] = {
            "is_alive": False,
            "response_time": 0.0,
            "final_ip": "",
            "error_message": "",
        }
        start_time = time.time()

        try:
            infos = await asyncio.get_running_loop().getaddrinfo(
                host, port, type=socket.SOCK_STREAM
            )
            ip = infos[0][4][0]
            result["final_ip"] = ip
        except Exception as exc:  # noqa: BLE001
            result["error_message"] = f"DNS解析失败: {exc}"
            return result

        try:
            _, writer = await asyncio.wait_for(
                asyncio.open_connection(host, port), timeout=timeout
            )
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass
            result["is_alive"] = True
            result["response_time"] = round((time.time() - start_time) * 1000, 2)
        except asyncio.TimeoutError:
            result["error_message"] = f"TCP连接超时({timeout}s)"
            result["response_time"] = round((time.time() - start_time) * 1000, 2)
        except Exception as exc:  # noqa: BLE001
            result["error_message"] = str(exc)
            result["response_time"] = round((time.time() - start_time) * 1000, 2)

        return result

    # ---------- ICMP ----------
    @staticmethod
    def _decode_ping_output(raw: bytes) -> str:
        """Windows 中文控制台可能是 GBK，Linux 为 UTF-8。"""
        for encoding in ("utf-8", locale.getpreferredencoding(False), "gbk"):
            try:
                return raw.decode(encoding)
            except (UnicodeDecodeError, LookupError):
                continue
        return raw.decode("utf-8", errors="replace")

    async def check_ping(self, host: str, timeout: int = 5) -> Dict[str, Any]:
        """ICMP Ping 探测（Windows / Linux 命令兼容）"""
        result: Dict[str, Any] = {
            "is_alive": False,
            "response_time": 0.0,
            "packet_loss": 100.0,
            "avg_latency": 0.0,
            "final_ip": "",
            "error_message": "",
        }

        started = time.perf_counter()
        try:
            if os.name == "nt":
                cmd = ["ping", "-n", "1", "-w", str(int(timeout * 1000)), host]
            else:
                cmd = ["ping", "-c", "1", "-W", str(int(timeout)), host]

            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await asyncio.wait_for(proc.communicate(), timeout=timeout + 5)
            output = self._decode_ping_output(stdout or b"")

            if proc.returncode == 0:
                result["is_alive"] = True
                result["packet_loss"] = 0.0

                # 优先解析单个 ICMP 包的时间字段：
                #   Linux 中文: 时间=0.126 毫秒
                #   Linux 英文: time=0.126 ms
                #   Windows:    时间=12ms / 时间<1ms / time=12ms
                # 不能直接匹配统计行里的 "time 0ms"，否则延迟永远是 0。
                latency: Optional[float] = None
                match = re.search(
                    r"(?:时间|time)\s*[=＝:]\s*([\d.]+)\s*(?:ms|毫秒)",
                    output,
                    re.IGNORECASE,
                )
                if match:
                    latency = float(match.group(1))
                else:
                    rtt = re.search(
                        r"rtt[^=]*=\s*([\d.]+)/([\d.]+)/([\d.]+)",
                        output,
                        re.IGNORECASE,
                    )
                    if rtt:
                        latency = float(rtt.group(2))
                    elif re.search(
                        r"(?:时间|time)\s*<\s*1\s*(?:ms|毫秒)",
                        output,
                        re.IGNORECASE,
                    ):
                        latency = 0.5
                if latency is None:
                    # 输出格式未知时用进程往返耗时兜底，至少不能显示 0ms
                    latency = max(0.01, (time.perf_counter() - started) * 1000)
                result["response_time"] = round(latency, 3)
                result["avg_latency"] = round(latency, 3)

                loss = re.search(r"([\d.]+)%\s*packet loss", output, re.IGNORECASE)
                if loss:
                    result["packet_loss"] = float(loss.group(1))
                ip_match = re.search(r"\(([\d.]+)\)", output) or \
                    re.search(r"(?:来自|from)\s+([\d.]+)", output, re.IGNORECASE)
                if ip_match:
                    result["final_ip"] = ip_match.group(1)
            else:
                result["error_message"] = "Ping 失败，主机不可达"
        except asyncio.TimeoutError:
            result["error_message"] = "Ping 超时"
        except Exception as exc:  # noqa: BLE001
            result["error_message"] = str(exc)

        return result

    # ---------- IP 可用性 ----------
    async def check_ip(self, ip: str, timeout: int = 3) -> Dict[str, Any]:
        """IP 可用性探测（基于 Ping）"""
        ping = await self.check_ping(ip, timeout)
        return {
            "is_reachable": ping["is_alive"],
            "latency_ms": ping["avg_latency"],
            "packet_loss": ping["packet_loss"],
            "final_ip": ping.get("final_ip") or ip,
            "error_message": ping["error_message"],
        }

    # 兼容旧命名
    async def check_ip_availability(self, ip: str, timeout: int = 3) -> Dict[str, Any]:
        return await self.check_ip(ip, timeout)

    # ---------- 分发 ----------
    async def check_all(self, target: Any) -> Dict[str, Any]:
        """按 target.monitor_type 执行对应探测

        - http/https : HTTP 存活探测（附带 ping 辅助信息）
        - tcp        : TCP 端口连通性（附带 ping）
        - ping       : ICMP Ping（可选 IP 可用性）
        """
        results: Dict[str, Any] = {
            "http_result": None,
            "tcp_result": None,
            "ping_result": None,
            "ip_result": None,
        }

        timeout = target.timeout or 10
        mtype = (target.monitor_type or "http").lower()
        host = target.domain or target.ip_address or ""
        if not host and target.url:
            parsed = urlparse(
                target.url if "://" in target.url else f"http://{target.url}"
            )
            host = parsed.hostname or ""

        tasks: List = []

        if mtype in ("http", "https"):
            if target.url:
                extra_cert_hosts = []
                root_domain = str(getattr(target, "cert_root_domain", "") or "").strip()
                if root_domain:
                    extra_cert_hosts.append(root_domain)
                for item in str(getattr(target, "cert_subdomains", "") or "").replace(";", ",").split(","):
                    host_item = item.strip()
                    if host_item and host_item not in extra_cert_hosts:
                        extra_cert_hosts.append(host_item)
                tasks.append(("http", self.check_http(
                    url=target.url,
                    method=target.method or "GET",
                    expected_status=target.expected_status or 200,
                    expected_keywords=(
                        target.expected_keywords.split(",")
                        if target.expected_keywords else None
                    ),
                    timeout=timeout,
                    collect_cert=(getattr(target, "cert_monitor_enabled", True) is not False),
                    ignore_https_errors=getattr(target, "ignore_https_errors", True) is not False,
                    cache_bust_seconds=int(getattr(target, "cache_bust_seconds", 0) or 0),
                    expected_statuses=getattr(target, "expected_statuses", "") or "",
                    cert_extra_hosts=extra_cert_hosts,
                )))
            if host:
                tasks.append(("ping", self.check_ping(host, timeout)))

        elif mtype == "tcp":
            if host:
                tasks.append(("tcp", self.check_tcp(host, target.port or 80, timeout)))
                tasks.append(("ping", self.check_ping(host, timeout)))

        elif mtype == "ping":
            if host:
                tasks.append(("ping", self.check_ping(host, timeout)))
            if target.ip_address:
                tasks.append(("ip", self.check_ip(target.ip_address, timeout)))

        if tasks:
            checked = await asyncio.gather(
                *[t[1] for t in tasks], return_exceptions=True
            )
            for (name, _), value in zip(tasks, checked):
                if isinstance(value, Exception):
                    logger.warning("探测子任务 %s 异常: %s", name, value)
                    continue
                results[f"{name}_result"] = value

        return results

    async def run_check(self, target) -> Optional[Dict[str, Any]]:
        """执行一次检查，异常时返回 None"""
        try:
            return await self.check_all(target)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.error("网站监控检查失败: %s", exc)
            return None
