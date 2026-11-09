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
HAS_OS_PACKAGES=0
if [[ -d "$OS_PKG_DIR" ]] && { [[ -n "$(ls -A "$OS_PKG_DIR/debian" 2>/dev/null || true)" ]] || [[ -n "$(ls -A "$OS_PKG_DIR/rhel" 2>/dev/null || true)" ]]; }; then
  HAS_OS_PACKAGES=1
  echo "==> 检测到离线系统包目录 offline/os-packages，默认优先使用本地 PostgreSQL/Redis 包"
else
  echo "!! 提示：离线包未包含 offline/os-packages/debian 或 offline/os-packages/rhel 系统安装包"
  echo "!! 本次将使用 SQLite / 进程内缓存；如需 PostgreSQL/Redis，请先补齐离线系统包"
fi

ARGS=("$@")
EXPLICIT_SERVICE=0
for arg in "$@"; do
  case "$arg" in
    --with-postgres|--with-redis|--no-postgres|--no-redis) EXPLICIT_SERVICE=1 ;;
  esac
done
# 有离线系统包时默认尝试 PG/Redis；没有系统包时直接使用 SQLite/内存缓存。
# 可用 --no-postgres/--no-redis 强制禁用，或 --with-* 强制尝试。
if [[ "$EXPLICIT_SERVICE" -eq 0 ]]; then
  if [[ "$HAS_OS_PACKAGES" -eq 1 ]]; then
    export AUTO_PROVISION_SERVICES=1
  else
    export AUTO_PROVISION_SERVICES=0
    ARGS+=(--no-postgres --no-redis)
  fi
fi
exec bash "$ROOT/deploy/install-systemd.sh" --offline "${ARGS[@]}"
