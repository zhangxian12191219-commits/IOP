#!/usr/bin/env bash
set -euo pipefail

# 修复从 ZIP/文件同步工具解压后丢失的执行位。
# 即使用户没有执行权限，也可以直接运行：
#   bash deploy/apply-permissions.sh

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

shopt -s nullglob
FILES=(
  start.sh
  uninstall.sh
  run_backend.py
  seed_demo.py
  deploy/install-systemd.sh
  deploy/snmp-nms-healthcheck.sh
  deploy/apply-permissions.sh
  tools/*.py
)

for file in "${FILES[@]}"; do
  [ -f "$file" ] || continue
  chmod 0755 "$file"
  echo "chmod 0755 $file"
done

echo "部署脚本执行权限已修复。"
