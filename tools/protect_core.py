#!/usr/bin/env python3
"""发布构建：加密核心后端模块。

核心模块在发布目录中转换为 AES-256-GCM 加密的 .pye，并删除 .py。
源码开发目录不受影响；运行时由 backend.protected_loader 在内存中解密。
"""
from __future__ import annotations

import os
import secrets
from pathlib import Path
from typing import Iterable

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

MAGIC = b"IOP1"
KEY_FILE = "code_key.bin"

# 只保护授权、认证、AI、更新和存储 API 等核心服务模块。
CORE_MODULES: tuple[str, ...] = (
    "backend/services/license_manager.py",
    "backend/services/auth.py",
    "backend/services/ai_agent.py",
    "backend/services/ai_ops.py",
    "backend/services/storage_api.py",
    "backend/services/api_collector.py",
    "backend/services/ipmi_collector.py",
    "backend/services/update_manager.py",
    "backend/services/virtualization_crypto.py",
    "backend/services/privilege.py",
)


def _build_key() -> bytes:
    raw = (os.getenv("IOP_CODE_KEY") or "").strip()
    if raw:
        try:
            key = bytes.fromhex(raw)
        except ValueError as exc:
            raise SystemExit("IOP_CODE_KEY 必须是 64 位十六进制字符串") from exc
        if len(key) != 32:
            raise SystemExit("IOP_CODE_KEY 必须是 32 字节（64 位十六进制）")
        return key
    return secrets.token_bytes(32)


def protect_release(release_dir: Path) -> list[str]:
    """加密发布目录中的核心模块，返回实际保护的文件列表。"""
    release_dir = Path(release_dir)
    backend_dir = release_dir / "backend"
    if not backend_dir.is_dir():
        raise SystemExit(f"发布目录缺少 backend: {release_dir}")

    key = _build_key()
    (backend_dir / KEY_FILE).write_bytes(key)
    protected: list[str] = []
    for relative in CORE_MODULES:
        source = release_dir / relative
        if not source.is_file():
            continue
        payload = source.read_bytes()
        module_name = relative[:-3].replace("/", ".").replace("\\", ".")
        nonce = secrets.token_bytes(12)
        ciphertext = AESGCM(key).encrypt(nonce, payload, module_name.encode("utf-8"))
        target = source.with_suffix(".pye")
        target.write_bytes(MAGIC + nonce + ciphertext)
        source.unlink()
        protected.append(relative)
    return protected


def verify_release(release_dir: Path) -> list[str]:
    """构建后强制校验：密钥存在、核心模块均为 .pye、没有明文 .py 残留。"""
    release_dir = Path(release_dir)
    backend_dir = release_dir / "backend"
    key_file = backend_dir / KEY_FILE
    if not key_file.is_file() or len(key_file.read_bytes()) != 32:
        raise SystemExit(f"加密密钥缺失或长度错误: {key_file}")
    missing: list[str] = []
    leaked: list[str] = []
    for relative in CORE_MODULES:
        source = release_dir / relative
        protected = source.with_suffix(".pye")
        if not protected.is_file():
            missing.append(relative)
        if source.exists():
            leaked.append(relative)
    if missing or leaked:
        detail = []
        if missing:
            detail.append("缺少 .pye: " + ", ".join(missing))
        if leaked:
            detail.append("仍有明文 .py: " + ", ".join(leaked))
        raise SystemExit("核心模块加密校验失败；" + "；".join(detail))
    return [str(release_dir / rel).replace(str(release_dir) + "/", "") for rel in CORE_MODULES]
