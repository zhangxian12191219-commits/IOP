#!/usr/bin/env bash
# 在联网且与目标发行版一致的机器上收集 PostgreSQL/Redis 离线包。
set -eu
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET=""
for arg in "$@"; do
  case "$arg" in
    --target=*) TARGET="${arg#*=}" ;;
    --target) shift; TARGET="${1:-}";;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
  esac
done
[[ -n "$TARGET" ]] || { echo "用法: sudo bash deploy/prepare-offline-os-packages.sh --target debian|rhel" >&2; exit 1; }
case "$TARGET" in
  debian)
    command -v apt-get >/dev/null || { echo "需要 apt-get" >&2; exit 1; }
    OUT="$ROOT/offline/os-packages/debian"; mkdir -p "$OUT"
    apt-get update
    apt-get install -y --download-only postgresql postgresql-client redis-server ipmitool
    find /var/cache/apt/archives -maxdepth 1 -name '*.deb' -exec cp -f {} "$OUT"/ \;
    ;;
  rhel)
    command -v dnf >/dev/null || { echo "需要 dnf" >&2; exit 1; }
    OUT="$ROOT/offline/os-packages/rhel"; mkdir -p "$OUT"
    dnf install -y 'dnf-command(download)' || true
    dnf download --resolve --destdir "$OUT" postgresql-server postgresql redis ipmitool
    ;;
  *) echo "未知目标: $TARGET" >&2; exit 1 ;;
esac
echo "系统包已放入: $OUT"
echo "请连同 offline/wheels 一起复制到离线发布包。"
