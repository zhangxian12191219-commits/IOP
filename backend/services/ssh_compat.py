"""老网络设备 SSH 兼容连接。

部分交换机/防火墙只支持 ssh-rsa / diffie-hellman-group14-sha1 等旧算法，
新版 Paramiko 默认禁用后会出现：
  Incompatible ssh peer (no acceptable host key)
本模块在协商时显式加入常见旧算法，同时保留新算法。
"""
from __future__ import annotations

import re
import socket
import time
from typing import Any, Tuple

OLD_KEY_TYPES = (
    "ssh-ed25519",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
    "rsa-sha2-512",
    "rsa-sha2-256",
    "ssh-rsa",
    "ssh-dss",
)
OLD_KEX = (
    "curve25519-sha256",
    "curve25519-sha256@libssh.org",
    "ecdh-sha2-nistp256",
    "ecdh-sha2-nistp384",
    "ecdh-sha2-nistp521",
    "diffie-hellman-group-exchange-sha256",
    "diffie-hellman-group16-sha512",
    "diffie-hellman-group14-sha256",
    "diffie-hellman-group14-sha1",
    "diffie-hellman-group1-sha1",
)
OLD_CIPHERS = (
    "chacha20-poly1305@openssh.com",
    "aes128-ctr",
    "aes192-ctr",
    "aes256-ctr",
    "aes128-cbc",
    "aes192-cbc",
    "aes256-cbc",
    "3des-cbc",
)


def open_shell(
    host: str,
    port: int,
    username: str,
    password: str,
    timeout: int = 15,
) -> Tuple[Any, Any]:
    """用兼容算法建立 SSH shell，返回 (transport, channel)。"""
    try:
        import paramiko
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("服务器未安装 paramiko，无法执行 SSH") from exc

    sock = socket.create_connection((host, int(port or 22)), timeout=timeout)
    transport = paramiko.Transport(sock)
    transport.banner_timeout = timeout
    transport.auth_timeout = timeout
    try:
        options = transport.get_security_options()

        def merge(attribute: str, old_values: tuple[str, ...]) -> None:
            current = getattr(options, attribute, ()) or ()
            # Paramiko 的 SecurityOptions 可能在当前环境不支持部分旧算法，
            # 只追加当前实现认识的候选，设置失败时保持原值。
            merged = list(current)
            for item in old_values:
                if item not in merged:
                    merged.append(item)
            try:
                setattr(options, attribute, tuple(merged))
            except (ValueError, TypeError, AttributeError):
                pass

        merge("key_types", OLD_KEY_TYPES)
        merge("kex", OLD_KEX)
        merge("ciphers", OLD_CIPHERS)
        transport.start_client(timeout=timeout)
        transport.auth_password(username=username, password=password)
        channel = transport.open_session(timeout=timeout)
        channel.get_pty(width=512, height=4096)
        channel.invoke_shell()
        channel.settimeout(0.8)
        return transport, channel
    except Exception:
        try:
            transport.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            sock.close()
        except Exception:  # noqa: BLE001
            pass
        raise


_PAGING_PROMPT_RE = re.compile(
    r"(?:--+\s*More\s*--+|<\s*-+\s*More\s*-+\s*>|----\s*More\s*----|Press\s+any\s+key)",
    re.IGNORECASE,
)


def read_shell_until_idle(
    channel: Any,
    timeout: int,
    idle_seconds: float = 0.8,
    advance_paging: bool = True,
) -> str:
    """读取 shell 输出；遇到 More 分页提示自动回车继续，避免只读到第一屏。"""
    deadline = time.monotonic() + timeout
    last_data = time.monotonic()
    chunks = []
    tail = ""
    pages = 0
    while time.monotonic() < deadline:
        try:
            data = channel.recv(65535)
        except Exception:  # noqa: BLE001
            data = b""
        if data:
            text = data.decode("utf-8", errors="replace")
            chunks.append(text)
            tail += text
            last_data = time.monotonic()
            if advance_paging and _PAGING_PROMPT_RE.search(tail):
                if pages < 500:
                    channel.send("\n")
                    pages += 1
                # 清除已处理的提示，避免旧提示反复触发回车
                tail = ""
        elif chunks and (time.monotonic() - last_data) >= idle_seconds:
            break
        else:
            time.sleep(0.08)
    return "".join(chunks)
