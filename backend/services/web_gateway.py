"""可配置的 Web 登录网关。

后端仍监听内部端口（默认 8000）；本网关按登录与安全设置在外层监听
HTTP/HTTPS 端口（默认 80/443），并把 HTTP、静态资源、API 和 WebSocket
反向代理回内部应用。因此启用/切换协议不需要把主服务改成单协议。
"""
from __future__ import annotations

import asyncio
import logging
import hashlib
import hmac
import os
import socket
import ssl
import tempfile
from pathlib import Path
from typing import Any, Dict, Optional

import aiohttp
from aiohttp import web
from sqlalchemy.orm import Session

from ..config import Config
from ..models.certificate import ManagedCertificate
from ..certificates import manager as certificate_manager
from . import settings as settings_service

logger = logging.getLogger(__name__)

HOP_HEADERS = {
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade", "host", "content-length",
}


class WebGatewayError(Exception):
    pass


class WebGateway:
    def __init__(self):
        # 网关与后端同进程；使用稳定共享密钥头标识可信代理，避免依赖来源 IP，
        # 也避免外部客户端伪造 X-Forwarded-Host 绕过内部端口限制。
        self._proxy_token = hmac.new(
            (Config.AUTH_SECRET or "snmp-monitor").encode("utf-8"),
            b"snmp-monitor-web-gateway",
            hashlib.sha256,
        ).hexdigest()
        self._lock = asyncio.Lock()
        self._runner: Optional[web.AppRunner] = None
        self._session: Optional[aiohttp.ClientSession] = None
        self._listeners: list[dict] = []
        self._error = ""
        self._running = False
        self._self_signed = False
        self._direct_fallback = False
        self._redirect_http = False
        self._redirect_https_port = 443
        self._protocol = "http"
        self._login_port = 80
        self._internal_port = int(os.getenv("API_PORT", str(Config.API_PORT or 8000)))
        self._tunnel_port = 0
        self._gateway_ssl_context = None

    @property
    def internal_port(self) -> int:
        return self._internal_port

    def is_running(self) -> bool:
        return bool(self._running)

    def should_block_direct(self) -> bool:
        """网关正常运行时，外部客户端只能通过 HTTP/HTTPS 登录入口访问。

        网关未运行时保留 8000 本机/应急入口；127.0.0.1 永远放行，
        便于 SSH 隧道、服务器本机运维和自动回滚。
        """
        return bool(self._running)

    def snapshot(self) -> dict:
        return {
            "running": self._running,
            "internal_port": self._internal_port,
            "listeners": [
                {key: value for key, value in item.items() if not key.startswith("_")}
                for item in self._listeners
            ],
            "error": self._error,
            "self_signed": self._self_signed,
            "direct_fallback": self._direct_fallback,
            "http_redirect": self._redirect_http,
            "protocol": self._protocol,
            "login_port": self._login_port,
        }

    @property
    def proxy_token(self) -> str:
        return self._proxy_token

    def _proxy_headers(self, request: web.Request) -> Dict[str, str]:
        headers = {
            key: value
            for key, value in request.headers.items()
            if key.lower() not in HOP_HEADERS
        }
        headers["X-Forwarded-Proto"] = "https" if request.secure else "http"
        headers["X-Forwarded-Host"] = request.host
        headers["X-SNMP-NMS-Gateway"] = self._proxy_token
        forwarded = request.headers.get("X-Forwarded-For")
        peer = request.remote or ""
        headers["X-Forwarded-For"] = f"{forwarded}, {peer}" if forwarded else peer
        return headers

    @staticmethod
    def _response_headers(headers) -> Dict[str, str]:
        return {
            key: value
            for key, value in headers.items()
            if key.lower() not in {
                "connection", "keep-alive", "proxy-authenticate",
                "proxy-authorization", "te", "trailers", "transfer-encoding",
                "upgrade",
            }
        }

    def _https_redirect(self, request: web.Request) -> web.Response:
        """HTTP 登录关闭后，将 HTTP 请求 308 跳转到 HTTPS，保留路径和查询参数。"""
        host = request.url.host or ""
        if ":" in host and not host.startswith("["):
            host = f"[{host}]"
        target = f"https://{host}"
        https_port = int(getattr(self, "_redirect_https_port", 443) or 443)
        if https_port != 443:
            target += f":{https_port}"
        target += request.path_qs
        return web.Response(
            status=308,
            headers={"Location": target, "Cache-Control": "no-store"},
            text=f"Redirecting to {target}",
        )

    async def _proxy(self, request: web.Request) -> web.StreamResponse:
        if not self._session:
            return web.Response(status=503, text="Web 网关尚未启动")
        # 专用级联端口只允许隧道端点，避免暴露普通管理/API 入口。
        if self._tunnel_port and request.url.port == self._tunnel_port and not request.path.startswith("/api/cascade/tunnel"):
            return web.Response(status=404, text="Not Found")
        if self._redirect_http and not request.secure:
            return self._https_redirect(request)
        path = request.path_qs
        base = f"http://127.0.0.1:{self._internal_port}"
        target = base + path
        headers = self._proxy_headers(request)

        if request.headers.get("Upgrade", "").lower() == "websocket":
            return await self._proxy_websocket(request, target, headers)

        data = request.content if request.can_read_body else None
        try:
            async with self._session.request(
                request.method,
                target,
                headers=headers,
                data=data,
                allow_redirects=False,
            ) as upstream:
                body = await upstream.read()
                return web.Response(
                    status=upstream.status,
                    body=body,
                    headers=self._response_headers(upstream.headers),
                )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Web 网关代理失败 %s: %s", path, exc)
            return web.Response(status=502, text=f"网关无法访问内部服务: {exc}")

    async def _proxy_websocket(
        self,
        request: web.Request,
        target: str,
        headers: Dict[str, str],
    ) -> web.WebSocketResponse:
        ws_server = web.WebSocketResponse(compress=False)
        await ws_server.prepare(request)
        ws_target = target.replace("http://", "ws://", 1).replace("https://", "wss://", 1)
        ws_headers = {
            key: value
            for key, value in headers.items()
            if not key.lower().startswith("sec-websocket-")
        }
        try:
            async with self._session.ws_connect(ws_target, headers=ws_headers) as ws_client:
                async def client_to_server():
                    try:
                        async for message in ws_client:
                            if message.type == aiohttp.WSMsgType.TEXT:
                                await ws_server.send_str(message.data)
                            elif message.type == aiohttp.WSMsgType.BINARY:
                                await ws_server.send_bytes(message.data)
                            elif message.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                                break
                    finally:
                        try:
                            await ws_server.close()
                        except Exception:  # noqa: BLE001
                            pass

                async def server_to_client():
                    try:
                        async for message in ws_server:
                            if message.type == aiohttp.WSMsgType.TEXT:
                                await ws_client.send_str(message.data)
                            elif message.type == aiohttp.WSMsgType.BINARY:
                                await ws_client.send_bytes(message.data)
                            elif message.type in (aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED):
                                break
                    finally:
                        try:
                            await ws_client.close()
                        except Exception:  # noqa: BLE001
                            pass

                await asyncio.gather(client_to_server(), server_to_client(), return_exceptions=True)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Web 网关 WebSocket 转发失败: %s", exc)
        finally:
            await ws_server.close()
        return ws_server

    def _resolve_certificate(self, db: Session, cert_id: int) -> ManagedCertificate:
        record = None
        if cert_id:
            record = db.query(ManagedCertificate).filter(ManagedCertificate.id == cert_id).first()
            if not record:
                raise WebGatewayError(f"HTTPS 证书 ID {cert_id} 不存在")
        else:
            record = (
                db.query(ManagedCertificate)
                .filter(ManagedCertificate.source == "acme")
                .order_by(ManagedCertificate.created_at.desc(), ManagedCertificate.id.desc())
                .first()
            )
            if not record:
                raise WebGatewayError("当前没有可用的免费证书。请先在「证书管理」申请证书，或上传自定义 SSL 证书")
        if not record.cert_path or not record.key_path:
            raise WebGatewayError("HTTPS 证书缺少证书或私钥文件")
        return record

    @staticmethod
    def _ssl_context(record: ManagedCertificate) -> ssl.SSLContext:
        cert_text = certificate_manager.fullchain_text(record)
        key_path = certificate_manager.file_for_download(record, "key")
        if not cert_text or not key_path or not key_path.is_file():
            raise WebGatewayError("HTTPS 证书或私钥文件不存在")
        temp_path = None
        try:
            fd, temp_path = tempfile.mkstemp(prefix="nms-web-fullchain-", suffix=".pem")
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(cert_text)
            os.chmod(temp_path, 0o600)
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.minimum_version = ssl.TLSVersion.TLSv1_2
            context.load_cert_chain(temp_path, str(key_path))
            return context
        except ssl.SSLError as exc:
            raise WebGatewayError(f"HTTPS 证书加载失败: {exc}") from exc
        finally:
            if temp_path:
                try:
                    Path(temp_path).unlink(missing_ok=True)
                except OSError:
                    pass

    @staticmethod
    def _is_self_signed(record: ManagedCertificate) -> bool:
        if record.source == "generated":
            return True
        subject = str(record.subject or "").strip()
        issuer = str(record.issuer or "").strip()
        return bool(subject and issuer and subject == issuer)

    async def _probe_listener(self, listener: dict) -> None:
        """启动后立即回环自检，避免网关看似启动但实际不可访问。"""
        scheme = listener.get("scheme")
        port = listener.get("port")
        expected = 308 if listener.get("mode") == "redirect" else 200
        url = f"{scheme}://127.0.0.1:{port}/api/health"
        try:
            async with self._session.get(
                url, ssl=False, timeout=8, allow_redirects=False,
            ) as response:
                if response.status != expected:
                    raise WebGatewayError(
                        f"{scheme.upper()} 监听端口 {port} 自检返回 HTTP {response.status}，预期 {expected}"
                    )
        except WebGatewayError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise WebGatewayError(f"{scheme.upper()} 监听端口 {port} 自检失败: {exc}") from exc

    async def _stop_locked(self) -> None:
        self._self_signed = False
        self._direct_fallback = False
        self._redirect_http = False
        self._tunnel_port = 0
        self._gateway_ssl_context = None
        for item in self._listeners:
            site = item.get("_site")
            if site:
                try:
                    await site.stop()
                except Exception:  # noqa: BLE001
                    pass
        self._listeners = []
        if self._runner:
            try:
                await asyncio.wait_for(self._runner.cleanup(), timeout=6)
            except asyncio.TimeoutError:
                logger.warning("Web 登录网关旧连接清理超时，已继续重启")
            except Exception:  # noqa: BLE001
                pass
            self._runner = None
        if self._session:
            try:
                await asyncio.wait_for(self._session.close(), timeout=3)
            except Exception:  # noqa: BLE001
                pass
            self._session = None
        self._running = False

    async def apply_from_settings(self, db: Session, probe: bool = True) -> dict:
        values = settings_service.get_all(db)
        async with self._lock:
            await self._stop_locked()
            self._error = ""
            https_enabled = bool(values.get("web_https_enabled"))
            protocol = str(values.get("web_protocol") or ("https" if https_enabled else "http")).strip().lower()
            if protocol not in ("http", "https"):
                protocol = "https" if https_enabled else "http"
            https_enabled = protocol == "https"
            http_login_enabled = protocol == "http" and bool(values.get("web_http_enabled", True))
            # 默认 HTTPS：HTTP 80 保留为 308 跳转入口；HTTP 登录本身关闭
            http_redirect_enabled = bool(https_enabled and values.get("web_https_redirect_http", True))
            http_enabled = http_login_enabled or http_redirect_enabled
            login_port = int(values.get("web_login_port") or (443 if https_enabled else 80))
            http_port = login_port if http_login_enabled else int(values.get("web_http_port") or 80)
            https_port = login_port if https_enabled else int(values.get("web_https_port") or 443)
            self._protocol = protocol
            self._login_port = login_port
            cert_id = int(values.get("web_ssl_certificate_id") or 0)
            self._redirect_http = http_redirect_enabled
            self._redirect_https_port = https_port
            if not http_enabled and not https_enabled:
                return self.snapshot()
            if http_enabled and https_enabled and http_port == https_port:
                self._error = "HTTP 跳转端口与 HTTPS 端口不能相同"
                raise WebGatewayError(self._error)
            for port in ([http_port] if http_enabled else []) + ([https_port] if https_enabled else []):
                if not 1 <= port <= 65535:
                    self._error = "Web 登录端口必须在 1~65535 之间"
                    raise WebGatewayError(self._error)
                if port == self._internal_port:
                    self._error = f"Web 登录端口不能与内部应用端口 {self._internal_port} 相同"
                    raise WebGatewayError(self._error)
            ssl_context = None
            cert_record = None
            self._self_signed = False
            if https_enabled:
                cert_record = self._resolve_certificate(db, cert_id)
                ssl_context = self._ssl_context(cert_record)
                self._self_signed = self._is_self_signed(cert_record)
                # 自签名证书浏览器默认不信任；保留内部端口用于管理员应急修复
                self._direct_fallback = self._self_signed

            self._gateway_ssl_context = ssl_context
            app = web.Application()
            app.router.add_route("*", "/{tail:.*}", self._proxy)
            self._session = aiohttp.ClientSession(
                auto_decompress=False,
                connector=aiohttp.TCPConnector(local_addr=("127.0.0.1", 0)),
            )
            self._runner = web.AppRunner(app, access_log=None)
            await self._runner.setup()
            try:
                if http_enabled:
                    site = web.TCPSite(
                        self._runner, Config.API_HOST or "0.0.0.0", http_port,
                    )
                    await site.start()
                    self._listeners.append({
                        "protocol": "http", "port": http_port, "scheme": "http",
                        "mode": "redirect" if http_redirect_enabled else "login",
                        "_site": site,
                    })
                if https_enabled:
                    site = web.TCPSite(
                        self._runner, Config.API_HOST or "0.0.0.0", https_port,
                        ssl_context=ssl_context,
                    )
                    await site.start()
                    self._listeners.append({
                        "protocol": "https", "port": https_port, "scheme": "https",
                        "certificate": {
                            "id": cert_record.id,
                            "name": cert_record.name,
                            "primary_host": cert_record.primary_host,
                            "self_signed": self._self_signed,
                        },
                        "_site": site,
                    })
                # 级联隧道使用独立端口；只有启用级联时才额外监听。
                tunnel_enabled = bool(values.get("cascade_enabled"))
                try:
                    tunnel_port = int(values.get("cascade_tunnel_port") or 9527)
                except (TypeError, ValueError):
                    tunnel_port = 9527
                if tunnel_enabled:
                    used_ports = {
                        int(item.get("port") or 0)
                        for item in self._listeners
                    }
                    if not 1 <= tunnel_port <= 65535:
                        self._error = "级联隧道端口必须在 1~65535 之间"
                        raise WebGatewayError(self._error)
                    if tunnel_port == self._internal_port or tunnel_port in used_ports:
                        self._error = f"级联隧道端口 {tunnel_port} 已被 Web 登录/内部端口占用"
                        raise WebGatewayError(self._error)
                    site = web.TCPSite(
                        self._runner, Config.API_HOST or "0.0.0.0", tunnel_port,
                        ssl_context=ssl_context,
                    )
                    await site.start()
                    self._tunnel_port = tunnel_port
                    self._listeners.append({
                        "protocol": "https" if https_enabled else "http",
                        "port": tunnel_port,
                        "scheme": "https" if https_enabled else "http",
                        "mode": "cascade_tunnel",
                        "_site": site,
                    })
                for listener in self._listeners:
                    if probe and listener.get("mode") != "cascade_tunnel":
                        await self._probe_listener(listener)
            except Exception as exc:  # noqa: BLE001
                self._error = f"Web 登录网关启动失败: {exc}"
                await self._stop_locked()
                raise WebGatewayError(self._error) from exc
            self._running = True
            logger.info(
                "Web 登录网关已启动: HTTP=%s(%s) HTTPS=%s 内部端口=%s",
                http_enabled,
                "跳转" if http_redirect_enabled else "登录",
                https_enabled, self._internal_port,
            )
            return self.snapshot()

    async def apply_cascade_tunnel(self, db: Session) -> dict:
        """在不重启 Web 登录入口的情况下，启动/更新/停止级联专用监听端口。"""
        values = settings_service.get_all(db)
        async with self._lock:
            # 先关闭旧隧道监听（不清理共享 runner/session）
            old_tunnel_sites = [
                item.get("_site") for item in self._listeners
                if item.get("mode") == "cascade_tunnel"
            ]
            self._listeners = [
                item for item in self._listeners
                if item.get("mode") != "cascade_tunnel"
            ]
            for old_site in old_tunnel_sites:
                if old_site:
                    try:
                        await old_site.stop()
                    except Exception:  # noqa: BLE001
                        pass
            self._tunnel_port = 0
            if not self._running or not self._runner:
                return self.snapshot()
            enabled = bool(values.get("cascade_enabled"))
            if not enabled:
                return self.snapshot()
            try:
                tunnel_port = int(values.get("cascade_tunnel_port") or 9527)
            except (TypeError, ValueError):
                tunnel_port = 9527
            used_ports = {
                int(item.get("port") or 0)
                for item in self._listeners
                if item.get("mode") != "cascade_tunnel"
            }
            if not 1 <= tunnel_port <= 65535:
                self._error = "级联隧道端口必须在 1~65535 之间"
                return self.snapshot()
            if tunnel_port == self._internal_port or tunnel_port in used_ports:
                self._error = f"级联隧道端口 {tunnel_port} 已被 Web 登录/内部端口占用"
                return self.snapshot()
            try:
                site = web.TCPSite(
                    self._runner, Config.API_HOST or "0.0.0.0", tunnel_port,
                    ssl_context=self._gateway_ssl_context,
                )
                await site.start()
                self._tunnel_port = tunnel_port
                self._listeners.append({
                    "protocol": "https" if self._protocol == "https" else "http",
                    "port": tunnel_port,
                    "scheme": self._protocol,
                    "mode": "cascade_tunnel",
                    "_site": site,
                })
                self._error = ""
            except Exception as exc:  # noqa: BLE001
                self._error = f"级联隧道端口监听失败: {exc}"
                logger.warning(self._error)
            return self.snapshot()

    async def stop(self) -> None:
        async with self._lock:
            await self._stop_locked()
            self._error = ""


gateway = WebGateway()
