#!/usr/bin/env bash
# 智能运维服务平台 - 健康检查与自动恢复
# 由 snmp-nms-healthcheck.timer 每 2 分钟调用；进程假死（端口无响应）时自动重启服务
set -uo pipefail

URL="${HEALTH_URL:-http://127.0.0.1:8000/api/health}"
TIMEOUT="${HEALTH_TIMEOUT:-5}"
SERVICE="${SERVICE_NAME:-snmp-nms}"

log() {
  if command -v logger >/dev/null 2>&1; then
    logger -t snmp-nms-healthcheck "$*"
  fi
  echo "[$(date '+%F %T')] $*"
}

# 服务正在启动/重载时不要重启；数据库迁移可能持续数分钟。
state=$(systemctl show -p ActiveState --value "$SERVICE" 2>/dev/null || true)
if [[ "$state" == "activating" || "$state" == "reloading" ]]; then
  log "服务处于 $state，跳过本轮健康检查重启"
  exit 0
fi

if curl -fsS --max-time "$TIMEOUT" "$URL" >/dev/null 2>&1; then
  exit 0
fi

log "健康检查失败（$URL），尝试重启 $SERVICE"
systemctl restart "$SERVICE" 2>/dev/null || true
sleep 5

if curl -fsS --max-time "$TIMEOUT" "$URL" >/dev/null 2>&1; then
  log "重启成功，服务已恢复"
  exit 0
fi

log "重启后仍不可用，请检查 journalctl -u $SERVICE -n 100"
exit 1
