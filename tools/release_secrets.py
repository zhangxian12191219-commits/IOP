#!/usr/bin/env python3
"""发布内容敏感信息扫描。

在构建前扫描源码，在加密后扫描最终发布目录；任何命中都阻止生成 ZIP。
这是发布门禁，不替代人工安全审计。
"""
from __future__ import annotations

import os
import re
from pathlib import Path

SKIP_DIRS = {
    ".git", ".venv", "node_modules", "__pycache__", "data", "vendor",
    "offline", ".pytest_cache", ".idea", ".vscode",
}
TEXT_SUFFIXES = {
    ".py", ".js", ".vue", ".ts", ".json", ".md", ".txt", ".yml", ".yaml",
    ".sh", ".ps1", ".bat", ".conf", ".ini", ".toml", ".html", ".css",
    ".example", ".env",
}
BLOCKED_NAMES = {
    ".env", ".env.local", ".env.production", ".env.development",
    "license.key", "machine_binding.json", "machine_id",
    "id_rsa", "id_ed25519", "snmp_monitor.db",
}
BLOCKED_SUFFIXES = {".db", ".db-shm", ".db-wal", ".sqlite", ".sqlite3", ".pem", ".key", ".p12", ".pfx"}
# 真正带 base64 内容的私钥块；排除界面里的 BEGIN 占位提示。
PRIVATE_KEY_RE = re.compile(
    r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----\s+[A-Za-z0-9+/=\r\n]{80,}?-----END [A-Z0-9 ]*PRIVATE KEY-----"
)
API_TOKEN_RE = re.compile(
    r"\b(?:"
    r"sk-[A-Za-z0-9_-]{20,}"
    r"|gh[pousr]_[A-Za-z0-9]{20,}"
    r"|xox[baprs]-[A-Za-z0-9-]{10,}"
    r"|AKIA[0-9A-Z]{16}"
    r"|AIza[0-9A-Za-z_-]{35}"
    r")\b"
)
# 私网地址示例很多，不能一律视为敏感；真实部署地址通过
# IOP_SENSITIVE_LITERALS（逗号分隔）在构建环境中注入检查。
# 只检查明显的弱默认值，避免把界面字段名或示例当成口令。
WEAK_DEFAULT_RE = re.compile(
    r"(?im)^[ \t]*(AUTH_DEFAULT_PASSWORD|POSTGRES_PASSWORD|DB_PASSWORD|AUTH_SECRET)[ \t]*=[ \t]*([^\r\n]*)"
)
PLACEHOLDER_MARKERS = (
    "<", "${", "#", "change", "example", "replace", "your", "strong", "密码",
    "_resolve", "os.getenv", "getenv",
)
SENSITIVE_LITERALS = tuple(
    item.strip() for item in (os.getenv("IOP_SENSITIVE_LITERALS") or "").split(",") if item.strip()
)


def _iter_files(root: Path):
    root = Path(root)
    for path in root.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if not path.is_file():
            continue
        name = path.name
        if name in BLOCKED_NAMES or path.suffix.lower() in BLOCKED_SUFFIXES:
            yield path
            continue
        if name == "code_key.bin" or path.suffix.lower() == ".pye":
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            if path.stat().st_size > 2 * 1024 * 1024:
                continue
        except OSError:
            continue
        yield path


def scan_tree(root: Path, ignore_runtime: bool = False) -> list[str]:
    findings: list[str] = []
    root = Path(root)
    for path in _iter_files(root):
        name = path.name
        if ignore_runtime and (name.startswith("snmp_monitor.db") or name == "code_key.bin"):
            continue
        if name in BLOCKED_NAMES or path.suffix.lower() in BLOCKED_SUFFIXES:
            findings.append(f"敏感文件: {path.relative_to(root)}")
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if PRIVATE_KEY_RE.search(text):
            findings.append(f"私钥内容: {path.relative_to(root)}")
        if API_TOKEN_RE.search(text):
            findings.append(f"疑似 API/访问令牌: {path.relative_to(root)}")
        for match in WEAK_DEFAULT_RE.finditer(text):
            value = (match.group(2) or "").strip().lower()
            if value and not any(marker in value for marker in PLACEHOLDER_MARKERS):
                findings.append(f"弱默认口令 [{match.group(1)}]: {path.relative_to(root)}")
        for literal in SENSITIVE_LITERALS:
            if literal in text:
                findings.append(f"敏感值: {path.relative_to(root)}")
    return findings
