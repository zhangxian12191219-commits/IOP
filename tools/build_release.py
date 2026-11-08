#!/usr/bin/env python3
"""构建带版本后缀的发布目录与 ZIP。

用法（在项目根目录执行）：
    python tools/build_release.py

读取 backend/version.json 中的 version，生成：
    <workspace>/IOP-v<version>/
    <workspace>/IOP-v<version>.zip

发布包根目录带版本后缀，系统更新器会自动识别单层版本目录。
"""
from __future__ import annotations

import argparse
import hashlib
import os
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from protect_core import protect_release, verify_release  # noqa: E402
from release_secrets import scan_tree  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PRODUCT_ABBR = "IOP"
DEFAULT_OUTPUT = PROJECT_ROOT.parent
EXCLUDED_DIRS = {
    ".git", ".venv", "node_modules", "__pycache__", ".pytest_cache",
    "data", "screenshots", ".idea", ".vscode",
}
EXCLUDED_FILES = {
    ".env", "snmp-nms.env", "snmp_monitor.db", "snmp_monitor.db-shm",
    "snmp_monitor.db-wal", ".DS_Store",
}
EXCLUDED_SUFFIXES = (".pyc", ".db", ".db-shm", ".db-wal", ".sqlite", ".sqlite3", ".bak")
EXECUTABLE_SUFFIXES = (".sh", ".ps1", ".bat", ".command")
EXECUTABLE_FILES = {
    "run_backend.py",
    "seed_demo.py",
    "tools/build_release.py",
    "tools/license_generator.py",
    "tools/security_check.py",
    "tools/reset_password.py",
    "tools/migrate_db.py",
    "tools/recover_web_gateway.py",
    "offline/bin/busybox",
}


def _is_executable(path: Path, base: Path = PROJECT_ROOT) -> bool:
    if path.suffix.lower() in EXECUTABLE_SUFFIXES:
        return True
    try:
        return path.relative_to(base).as_posix() in EXECUTABLE_FILES
    except ValueError:
        return False


def _skip(path: Path) -> bool:
    name = path.name
    if path.is_dir():
        return name in EXCLUDED_DIRS or name.startswith("tmp-build")
    if name in EXCLUDED_FILES or name.endswith(EXCLUDED_SUFFIXES):
        return True
    if path == PROJECT_ROOT / "deploy" / "snmp-nms.env":
        return True
    return False


def _copy_tree(source: Path, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for child in sorted(source.iterdir(), key=lambda item: item.name):
        if _skip(child):
            continue
        destination = target / child.name
        if child.is_dir():
            _copy_tree(child, destination)
        else:
            if child.suffix.lower() == ".sh":
                # 发布包中的 Shell 脚本必须是 LF，避免 Windows 构建产生 CRLF
                destination.write_bytes(child.read_bytes().replace(b"\r\n", b"\n").replace(b"\r", b"\n"))
                if _is_executable(child):
                    try:
                        os.chmod(destination, 0o755)
                    except OSError:
                        pass
            else:
                shutil.copy2(child, destination)
                if _is_executable(child):
                    try:
                        os.chmod(destination, 0o755)
                    except OSError:
                        pass


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build(output_root: Path, force: bool) -> tuple[Path, Path, str]:
    version_file = PROJECT_ROOT / "backend" / "version.json"
    data = json.loads(version_file.read_text(encoding="utf-8"))
    version = str(data.get("version") or "").strip()
    if not version:
        raise SystemExit("backend/version.json 缺少 version")
    release_name = f"{PRODUCT_ABBR}-v{version}"
    final_release_dir = output_root / release_name
    # 源码目录本身可能按发布名命名（如 IOP-v2.21.25）。此时不能在源码目录上
    # 直接构建，否则 --force 会删除项目自身；改用同级临时构建目录。
    staging_build = final_release_dir.resolve() == PROJECT_ROOT.resolve()
    release_dir = (
        output_root / f".{release_name}-staging"
        if staging_build
        else final_release_dir
    )
    zip_path = output_root / f"{release_name}.zip"
    if release_dir.exists():
        if not force:
            raise SystemExit(f"发布目录已存在: {release_dir}（使用 --force 覆盖）")
        shutil.rmtree(release_dir)
    if zip_path.exists():
        if not force:
            raise SystemExit(f"发布包已存在: {zip_path}（使用 --force 覆盖）")
        zip_path.unlink()

    readme_en = PROJECT_ROOT / "README.en.md"
    if not readme_en.is_file():
        raise SystemExit("缺少英文 README：README.en.md")
    license_file = PROJECT_ROOT / "LICENSE"
    if not license_file.is_file() or license_file.stat().st_size < 100:
        raise SystemExit("缺少开源许可证文件：LICENSE")
    offline_python = PROJECT_ROOT / "offline" / "python-linux-x86_64.tar.xz"
    offline_wheels = PROJECT_ROOT / "offline" / "wheels"
    offline_busybox = PROJECT_ROOT / "offline" / "bin" / "busybox"
    if not offline_python.is_file():
        raise SystemExit("缺少离线 Python 运行时：offline/python-linux-x86_64.tar.xz")
    if not offline_busybox.is_file():
        raise SystemExit("缺少离线解压工具：offline/bin/busybox")
    if not offline_wheels.is_dir() or not any(offline_wheels.glob("*.whl")):
        raise SystemExit("缺少离线 Python wheels：offline/wheels/*.whl")
    source_findings = scan_tree(PROJECT_ROOT, ignore_runtime=True)
    if source_findings:
        raise SystemExit("源码敏感信息检查未通过：\n" + "\n".join(source_findings[:30]))
    _copy_tree(PROJECT_ROOT, release_dir)
    if not (release_dir / "LICENSE").is_file():
        raise SystemExit("发布目录缺少 LICENSE，已阻止生成发布包")
    for script in release_dir.rglob("*.sh"):
        if b"\r" in script.read_bytes():
            raise SystemExit(f"发布包 Shell 脚本仍包含 CR 换行: {script.relative_to(release_dir)}")
    protected = protect_release(release_dir)
    verify_release(release_dir)
    release_findings = scan_tree(release_dir)
    if release_findings:
        raise SystemExit("发布目录敏感信息检查未通过：\n" + "\n".join(release_findings[:30]))
    if protected:
        print(f"protected: {len(protected)} core modules (verified)")
    print("release secrets: clean")
    (release_dir / "RELEASE_VERSION").write_text(version + "\n", encoding="utf-8")

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(release_dir.rglob("*")):
            arcname = f"{release_name}/{path.relative_to(release_dir).as_posix()}"
            if path.is_dir():
                continue
            info = zipfile.ZipInfo.from_file(path, arcname)
            info.create_system = 3
            mode = 0o100755 if _is_executable(path, release_dir) else 0o100644
            info.external_attr = mode << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, path.read_bytes())

    digest = _sha256(zip_path)
    print(f"version: {version}")
    print("readme: README.md (zh-CN), README.en.md (en-US)")
    print("license: LICENSE (MPL-2.0)")
    print(f"offline: {offline_python.name}, busybox, {len(list(offline_wheels.glob('*.whl')))} wheels")
    file_count = sum(1 for p in release_dir.rglob('*') if p.is_file())
    print(f"release_dir: {final_release_dir}")
    print(f"zip: {zip_path}")
    print(f"files: {file_count}")
    print(f"size: {zip_path.stat().st_size / 1024 / 1024:.2f} MB")
    print(f"sha256: {digest.upper()}")
    if staging_build:
        shutil.rmtree(release_dir, ignore_errors=True)
    return final_release_dir, zip_path, digest


def _security_gate() -> None:
    """发布前强制执行静态安全门禁；FAIL 时阻止生成发布包。"""
    script = PROJECT_ROOT / "tools" / "security_check.py"
    if not script.is_file():
        raise SystemExit("安全门禁脚本缺失：tools/security_check.py")
    compile_result = subprocess.run(
        [sys.executable, "-m", "compileall", "-q", str(PROJECT_ROOT / "backend")],
        cwd=str(PROJECT_ROOT),
    )
    if compile_result.returncode != 0:
        raise SystemExit("后端语法/编译检查未通过，已阻止生成发布包")
    result = subprocess.run([sys.executable, str(script)], cwd=str(PROJECT_ROOT))
    if result.returncode != 0:
        raise SystemExit("安全门禁未通过，已阻止生成发布包")


def main() -> int:
    _security_gate()
    parser = argparse.ArgumentParser(description="生成带版本后缀的发布目录和 ZIP")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="输出目录，默认工作区根目录")
    parser.add_argument("--force", action="store_true", help="覆盖同版本已有产物")
    args = parser.parse_args()
    build(Path(args.output).resolve(), bool(args.force))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
