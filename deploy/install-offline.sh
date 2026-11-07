#!/usr/bin/env bash
# 离线安装入口：必须从完整离线发布包运行。
# 包内包含 Linux x86_64 独立 Python、全部 Python wheels 和前端 dist。
# PostgreSQL / Redis 的系统安装包按约定放在 offline/os-packages/{debian,rhel}/：
#   - Debian/Ubuntu: offline/os-packages/debian/*.deb
#   - RHEL/Rocky/Alma: offline/os-packages/rhel/*.rpm
# 未包含系统包时不会伪造安装成功：脚本会明确提示并安全回退 SQLite / 进程内缓存。
set -eu
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
[[ -f "$ROOT/offline/python-linux-x86_64.tar.xz" ]] || { echo "缺少 offline/python-linux-x86_64.tar.xz，请使用完整离线包" >&2; exit 1; }
[[ -d "$ROOT/offline/wheels" ]] || { echo "缺少 offline/wheels，请使用完整离线包" >&2; exit 1; }

OS_PKG_DIR="$ROOT/offline/os-packages"
if [[ -d "$OS_PKG_DIR" ]] && { [[ -n "$(ls -A "$OS_PKG_DIR/debian" 2>/dev/null || true)" ]] || [[ -n "$(ls -A "$OS_PKG_DIR/rhel" 2>/dev/null || true)" ]]; }; then
  echo "==> 检测到离线系统包目录 offline/os-packages（debian/rhel），安装时优先使用本地包"
else
  echo "!! 提示：离线包未包含 offline/os-packages/debian 或 offline/os-packages/rhel 系统安装包"
  echo "!! PostgreSQL / Redis 将无法离线安装，安装脚本会安全回退 SQLite / 进程内缓存并给出警告"
fi

exec bash "$ROOT/deploy/install-systemd.sh" --offline "$@"
