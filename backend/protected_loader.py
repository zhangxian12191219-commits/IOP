"""核心服务模块的运行时解密导入器。

发布构建可以把 backend/services 下的核心模块加密为 .pye 并删除 .py。
源码开发目录没有 code_key.bin 和 .pye 时，本模块自动不启用。
"""
from __future__ import annotations

import importlib.abc
import importlib.util
import os
import sys
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_MAGIC = b"IOP1"
_KEY_FILE = Path(__file__).with_name("code_key.bin")
_installed = False


def _load_key() -> Optional[bytes]:
    try:
        key = _KEY_FILE.read_bytes()
    except OSError:
        return None
    return key if len(key) == 32 else None


def _decrypt(path: Path, key: bytes, fullname: str) -> bytes:
    payload = path.read_bytes()
    if len(payload) < len(_MAGIC) + 12 + 16 or not payload.startswith(_MAGIC):
        raise ImportError(f"受保护模块格式无效: {path}")
    nonce = payload[len(_MAGIC):len(_MAGIC) + 12]
    ciphertext = payload[len(_MAGIC) + 12:]
    return AESGCM(key).decrypt(nonce, ciphertext, fullname.encode("utf-8"))


class _ProtectedLoader(importlib.abc.Loader):
    def __init__(self, path: Path, key: bytes, fullname: str):
        self.path = path
        self.key = key
        self.fullname = fullname

    def create_module(self, spec):
        return None

    def exec_module(self, module) -> None:
        source = _decrypt(self.path, self.key, self.fullname)
        filename = str(self.path.with_suffix(".py"))
        code = compile(source, filename, "exec")
        module.__file__ = filename
        module.__loader__ = self
        exec(code, module.__dict__)


class _ProtectedFinder(importlib.abc.MetaPathFinder):
    def __init__(self, package_root: Path, key: bytes):
        self.package_root = package_root
        self.key = key

    def find_spec(self, fullname, path=None, target=None):
        if not fullname.startswith("backend."):
            return None
        parts = fullname.split(".")[1:]
        if not parts:
            return None
        candidate = self.package_root.joinpath(*parts).with_suffix(".pye")
        if not candidate.is_file():
            return None
        return importlib.util.spec_from_loader(
            fullname,
            _ProtectedLoader(candidate, self.key, fullname),
            origin=str(candidate),
        )


def _remove_stale_sources(package_root: Path) -> None:
    """升级覆盖安装时删除旧的明文 .py 和 .pyc，避免受保护模块仍有源码。"""
    for protected in package_root.rglob("*.pye"):
        source = protected.with_suffix(".py")
        try:
            if source.is_file():
                source.unlink()
        except OSError:
            pass
        try:
            cache_dir = source.parent / "__pycache__"
            if cache_dir.is_dir():
                for cached in cache_dir.glob(f"{source.stem}.*.pyc"):
                    try:
                        cached.unlink()
                    except OSError:
                        pass
        except OSError:
            pass


def install() -> None:
    """安装受保护模块查找器；没有密钥或重复调用时安全跳过。"""
    global _installed
    if _installed:
        return
    key = _load_key()
    if key is None:
        return
    package_root = Path(__file__).resolve().parent
    _remove_stale_sources(package_root)
    sys.meta_path.insert(0, _ProtectedFinder(package_root, key))
    _installed = True
