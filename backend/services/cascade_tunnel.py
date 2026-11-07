"""级联隧道运行时。

- 分支：主动通过 WSS 连接总部，不开放入站端口；
- 总部：认证分支令牌并保存快照/消息；
- 业务帧使用令牌派生的 Fernet 密钥二次加密；
- 自动重连、心跳、周期快照和待投递消息。
"""
from __future__ import annotations

import asyncio
import json
import logging
import ssl
from datetime import datetime
from typing import Any, Dict, Optional
from urllib.parse import urlparse

import aiohttp

from ..models.cascade import CascadeMessage, CascadeNode
from ..models.database import SessionLocal
from . import cascade as cascade_service
from . import settings as settings_service

logger = logging.getLogger("snmp-monitor.cascade")


class CascadeTunnelManager:
    def __init__(self):
        self._branch_task: Optional[asyncio.Task] = None
        self._branch_stop = asyncio.Event()
        self._branch_ws = None
        self._branch_state: Dict[str, Any] = {"connected": False, "last_error": "", "last_sync": None}
        self._hq_connections: Dict[str, Any] = {}
        self._lock = asyncio.Lock()

    def branch_state(self) -> Dict[str, Any]:
        return dict(self._branch_state)

    async def start(self) -> None:
        db = SessionLocal()
        try:
            config = cascade_service.get_config(db)
        finally:
            db.close()
        if config["enabled"] and config["role"] == "branch" and config["hq_url"] and config["token"]:
            self._branch_stop.clear()
            if not self._branch_task or self._branch_task.done():
                self._branch_task = asyncio.create_task(self._branch_loop(), name="cascade-branch")
                logger.info("级联分支隧道已启动: %s", config["hq_url"])

    async def stop(self) -> None:
        self._branch_stop.set()
        ws = self._branch_ws
        self._branch_ws = None
        if ws is not None:
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass
        task = self._branch_task
        self._branch_task = None
        if task:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        for ws in list(self._hq_connections.values()):
            try:
                await ws.close()
            except Exception:  # noqa: BLE001
                pass
        self._hq_connections.clear()
        self._branch_state = {"connected": False, "last_error": "隧道已停止", "last_sync": None}

    async def reload(self) -> None:
        await self.stop()
        await self.start()

    def _branch_ws_url(self, hq_url: str, tunnel_port: Optional[int] = None) -> str:
        raw = str(hq_url or "").strip().rstrip("/")
        parsed = urlparse(raw)
        if parsed.scheme not in ("http", "https"):
            raise ValueError("总部地址必须以 http:// 或 https:// 开头")
        if not parsed.hostname:
            raise ValueError("总部地址缺少主机名")
        scheme = "wss" if parsed.scheme == "https" else "ws"
        # 级联隧道走独立端口，不再复用 Web 登录端口。
        port = int(tunnel_port or parsed.port or (443 if parsed.scheme == "https" else 80))
        host = parsed.hostname
        netloc = f"[{host}]" if ":" in host else host
        netloc = f"{netloc}:{port}"
        path = parsed.path.rstrip("/")
        if not path.endswith("/api/cascade/tunnel"):
            path = f"{path}/api/cascade/tunnel"
        return f"{scheme}://{netloc}{path}"

    async def _branch_loop(self) -> None:
        backoff = 5
        while not self._branch_stop.is_set():
            db = SessionLocal()
            try:
                config = cascade_service.get_config(db)
            finally:
                db.close()
            if not (config["enabled"] and config["role"] == "branch" and config["hq_url"] and config["token"]):
                break
            try:
                await self._branch_session(config)
                backoff = 5
            except asyncio.CancelledError:
                raise
            except Exception as exc:  # noqa: BLE001
                self._branch_state = {
                    "connected": False,
                    "last_error": str(exc)[:300],
                    "last_sync": self._branch_state.get("last_sync"),
                }
                logger.warning("级联分支连接失败: %s", exc)
            if self._branch_stop.is_set():
                break
            try:
                await asyncio.wait_for(self._branch_stop.wait(), timeout=backoff)
            except asyncio.TimeoutError:
                pass
            backoff = min(backoff * 2, 60)

    async def _branch_session(self, config: Dict[str, Any]) -> None:
        url = self._branch_ws_url(config["hq_url"], config.get("tunnel_port"))
        ssl_context = None
        if url.startswith("wss://") and not config["verify_tls"]:
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
        timeout = aiohttp.ClientTimeout(total=None, sock_connect=20, sock_read=90)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.ws_connect(
                url, headers={"Authorization": f"Bearer {config['token']}"},
                ssl=ssl_context, heartbeat=30, autoping=True,
            ) as ws:
                self._branch_ws = ws
                self._branch_state = {"connected": True, "last_error": "", "last_sync": None}
                db = SessionLocal()
                try:
                    snapshot = cascade_service.build_snapshot(db)
                finally:
                    db.close()
                hello = {
                    "type": "hello",
                    "node_name": config["node_name"] or "分支节点",
                    "version": snapshot.get("version") or "",
                    "snapshot": snapshot,
                }
                await ws.send_str(cascade_service.encrypt_frame(config["token"], hello))
                last_sync = datetime.utcnow().timestamp()

                async def send_snapshot():
                    nonlocal last_sync
                    db = SessionLocal()
                    try:
                        snap = cascade_service.build_snapshot(db)
                    finally:
                        db.close()
                    await ws.send_str(cascade_service.encrypt_frame(config["token"], {
                        "type": "snapshot", "snapshot": snap,
                    }))
                    last_sync = datetime.utcnow().timestamp()
                    self._branch_state["last_sync"] = snap.get("generated_at")

                while not self._branch_stop.is_set() and not ws.closed:
                    try:
                        message = await asyncio.wait_for(ws.receive(), timeout=5)
                    except asyncio.TimeoutError:
                        message = None
                    if message is not None:
                        if message.type == aiohttp.WSMsgType.TEXT:
                            try:
                                payload = cascade_service.decrypt_frame(config["token"], message.data)
                            except ValueError as exc:
                                self._branch_state["last_error"] = str(exc)
                                continue
                            if payload.get("type") == "chat":
                                db = SessionLocal()
                                try:
                                    cascade_service.add_message(
                                        db, "hq", str(payload.get("sender") or "总部"),
                                        str(payload.get("content") or ""), "hq_to_branch", delivered=True,
                                    )
                                finally:
                                    db.close()
                            elif payload.get("type") == "sync_request":
                                await send_snapshot()
                        elif message.type in (aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR):
                            break
                    now = datetime.utcnow().timestamp()
                    if now - last_sync >= int(config["sync_interval"] or 60):
                        await send_snapshot()
                    else:
                        await ws.send_str(cascade_service.encrypt_frame(config["token"], {
                            "type": "heartbeat", "at": datetime.utcnow().isoformat(),
                        }))
        self._branch_ws = None
        self._branch_state["connected"] = False

    # ---------- 总部侧 ----------
    def register_hq(self, node_key: str, ws) -> None:
        self._hq_connections[node_key] = ws

    def unregister_hq(self, node_key: str, ws) -> None:
        if self._hq_connections.get(node_key) is ws:
            self._hq_connections.pop(node_key, None)

    def hq_connected(self, node_key: str) -> bool:
        return node_key in self._hq_connections

    async def send_to_branch(self, node: CascadeNode, payload: Dict[str, Any]) -> bool:
        ws = self._hq_connections.get(node.node_key)
        token = cascade_service.node_token(node)
        if ws is None or not token:
            return False
        try:
            # Starlette WebSocket 使用 send_text；aiohttp 客户端才使用 send_str
            await ws.send_text(cascade_service.encrypt_frame(token, payload))
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("向分支 %s 发送失败: %s", node.name, exc)
            self._hq_connections.pop(node.node_key, None)
            return False

    async def deliver_pending(self, node: CascadeNode) -> None:
        if not self.hq_connected(node.node_key):
            return
        db = SessionLocal()
        try:
            rows = (
                db.query(CascadeMessage)
                .filter(
                    CascadeMessage.node_key == node.node_key,
                    CascadeMessage.direction == "hq_to_branch",
                    CascadeMessage.delivered.is_(False),
                )
                .order_by(CascadeMessage.created_at.asc())
                .limit(100)
                .all()
            )
            for row in rows:
                sent = await self.send_to_branch(node, {
                    "type": "chat", "sender": row.sender, "content": row.content,
                    "message_id": row.id, "created_at": row.created_at.isoformat() if row.created_at else None,
                })
                if not sent:
                    break
                row.delivered = True
            db.commit()
        finally:
            db.close()

    async def send_branch_chat(self, content: str) -> bool:
        ws = self._branch_ws
        if ws is None or ws.closed:
            return False
        db = SessionLocal()
        try:
            config = cascade_service.get_config(db)
        finally:
            db.close()
        if not config["token"]:
            return False
        await ws.send_str(cascade_service.encrypt_frame(config["token"], {
            "type": "chat", "sender": config["node_name"] or "分支节点", "content": content,
        }))
        return True


manager = CascadeTunnelManager()
