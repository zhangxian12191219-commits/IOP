#!/usr/bin/env python3
"""轻量安全门禁：扫描高危模式并检查关键安全配置。

这不是完整 SAST 替代品，不能代替人工 OWASP 审计；每次发布仍必须执行
SECURITY.md 中的人工检查清单。
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SKIP_DIRS = {"node_modules", "dist", "data", ".git", "__pycache__", "release"}
TEXT_SUFFIXES = {".py", ".js", ".vue", ".ts", ".env", ".yml", ".yaml", ".md", ".example"}
findings: list[tuple[str, str, str]] = []


def files():
    for path in ROOT.rglob("*"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        if path.is_file() and (path.suffix in TEXT_SUFFIXES or path.name.endswith(".env.example")):
            yield path


def add(level: str, message: str, path: Path | None = None, line: int | None = None):
    location = ""
    if path is not None:
        location = f"{path.relative_to(ROOT)}"
        if line:
            location += f":{line}"
    findings.append((level, message, location))


def scan_patterns():
    patterns = [
        ("FAIL", "shell=True", re.compile(r"shell\s*=\s*True")),
        ("FAIL", "eval/exec 动态执行", re.compile(r"(?<![\w.])(?:eval|exec)\s*\(")),
        ("FAIL", "pickle 反序列化", re.compile(r"\bpickle\.loads?\s*\(")),
        ("FAIL", "yaml.load 未使用 safe_load", re.compile(r"\byaml\.load\s*\(")),
        ("WARN", "v-html 需确认内容已转义", re.compile(r"v-html\s*=")),
        ("WARN", "innerHTML 需确认内容已转义", re.compile(r"\.innerHTML\s*=")),
        ("WARN", "URL 查询参数携带 token", re.compile(r"[?&]token=")),
    ]
    for path in files():
        if path.name == "security_check.py" or path.suffix == ".md":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            for level, message, pattern in patterns:
                if pattern.search(line):
                    add(level, message, path, number)


def check_config():
    app = (ROOT / "backend" / "config.py").read_text(encoding="utf-8", errors="replace")
    if 'AUTH_DEFAULT_PASSWORD = os.getenv("AUTH_DEFAULT_PASSWORD", "")' not in app:
        add("FAIL", "初始管理员密码仍存在公开默认值", ROOT / "backend" / "config.py")
    if "_resolve_auth_secret" not in app or "data" not in app:
        add("FAIL", "AUTH_SECRET 没有安全随机持久化机制", ROOT / "backend" / "config.py")
    if "CORS_ORIGINS" not in app:
        add("FAIL", "CORS 没有显式白名单配置", ROOT / "backend" / "config.py")
    main = (ROOT / "backend" / "app.py").read_text(encoding="utf-8", errors="replace")
    if 'allow_origins=["*"]' in main:
        add("FAIL", "CORS 仍允许通配符来源", ROOT / "backend" / "app.py")
    for header in ("X-Content-Type-Options", "X-Frame-Options", "Referrer-Policy"):
        if header not in main:
            add("FAIL", f"缺少安全响应头 {header}", ROOT / "backend" / "app.py")
    ai_route = (ROOT / "backend" / "routes" / "ai.py").read_text(encoding="utf-8", errors="replace")
    for marker in ("asset_scope", "device_ids", "created_by"):
        if marker not in ai_route:
            add("FAIL", f"AI 接口缺少对象级范围控制标记：{marker}", ROOT / "backend" / "routes" / "ai.py")


def check_secret_files():
    for relative in ("data/.auth_secret", "data/initial_admin_password.txt", "data/license.key"):
        path = ROOT / relative
        if path.exists():
            add("INFO", "本机敏感文件存在，发布包必须排除 data/ 目录", path)
    # 授权私钥绝不能进入产品源码/安装包；仅允许销售方离线保存。
    for path in ROOT.rglob("*.pem"):
        if "data" in path.parts or "node_modules" in path.parts:
            continue
        if "private" in path.name.lower():
            add("FAIL", "产品目录中发现授权私钥", path)
    manager = (ROOT / "backend" / "services" / "license_manager.py").read_text(encoding="utf-8", errors="replace")
    if "BEGIN PRIVATE KEY" in manager or "PRIVATE_KEY_HEX" in manager:
        add("FAIL", "授权私钥/私钥材料被写入产品代码", ROOT / "backend" / "services" / "license_manager.py")
    if "Ed25519PublicKey.from_public_bytes" not in manager:
        add("FAIL", "授权签名验签缺失", ROOT / "backend" / "services" / "license_manager.py")
    if "is_blocked" not in manager:
        add("FAIL", "授权无效状态没有统一阻断", ROOT / "backend" / "services" / "license_manager.py")


def main() -> int:
    scan_patterns()
    check_config()
    check_secret_files()
    counts = {"FAIL": 0, "WARN": 0, "INFO": 0}
    for level, message, location in findings:
        counts[level] = counts.get(level, 0) + 1
        print(f"[{level}] {message}" + (f" — {location}" if location else ""))
    print(f"\n结果：FAIL={counts['FAIL']} WARN={counts['WARN']} INFO={counts['INFO']}")
    if counts["FAIL"]:
        print("安全门禁未通过，请修复 FAIL 项后重新执行。")
        return 1
    print("安全门禁通过；WARN 项仍需按 SECURITY.md 人工确认。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
