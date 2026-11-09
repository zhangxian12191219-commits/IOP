#!/usr/bin/env bash
# ============================================================================
# 音视频 TURN 中转配置（Linux）
#
# 用法（root）:
#   sudo bash deploy/setup-turn.sh --host 192.0.2.10
#   sudo bash deploy/setup-turn.sh --host 192.0.2.10 --force-relay
#   sudo bash deploy/setup-turn.sh --host 192.0.2.10 --port 3478 \
#        --min-port 49160 --max-port 49200
#
# 说明:
#   - 使用发布包内 offline/coturn-linux-x86_64.tar.gz 的独立 coturn；
#   - 不替换系统 OpenSSL / libevent，避免 ABI 冲突；
#   - 自动写入 /opt/snmp-monitor/deploy/snmp-nms.env 并重启平台；
#   - 防火墙启用 firewalld 时自动放行 3478 和 relay 端口。
# ============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BUNDLE="$ROOT/offline/coturn-linux-x86_64.tar.gz"
APP_DIR="${APP_DIR:-/opt/snmp-monitor}"
ENV_FILE="$APP_DIR/deploy/snmp-nms.env"
TURN_HOST=""
TURN_PORT=3478
MIN_PORT=49160
MAX_PORT=49200
TURN_USER="nms"
TURN_PASSWORD=""
FORCE_RELAY="0"
TURN_HOME="/opt/coturn"

info() { echo "==> $*"; }
warn() { echo "!! $*" >&2; }
die() { echo "!! $*" >&2; exit 1; }

while [[ $# -gt 0 ]]; do
  case "$1" in
    --host) TURN_HOST="${2:-}"; shift 2 ;;
    --port) TURN_PORT="${2:-}"; shift 2 ;;
    --min-port) MIN_PORT="${2:-}"; shift 2 ;;
    --max-port) MAX_PORT="${2:-}"; shift 2 ;;
    --user) TURN_USER="${2:-}"; shift 2 ;;
    --password) TURN_PASSWORD="${2:-}"; shift 2 ;;
    --force-relay) FORCE_RELAY="1"; shift ;;
    -h|--help) sed -n '2,22p' "$0"; exit 0 ;;
    *) die "未知参数: $1" ;;
  esac
done

[[ $EUID -eq 0 ]] || die "请使用 root 执行"
[[ -f "$BUNDLE" ]] || die "缺少 $BUNDLE，请使用完整离线发布包"
[[ -n "$TURN_HOST" ]] || die "必须指定 --host <客户端可访问的服务器 IP/DNS>"
command -v systemctl >/dev/null || die "需要 systemd"

if [[ -z "$TURN_PASSWORD" ]]; then
  if command -v openssl >/dev/null 2>&1; then
    TURN_PASSWORD="$(openssl rand -hex 16)"
  else
    TURN_PASSWORD="$(head -c 16 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  fi
fi
[[ -n "$TURN_PASSWORD" ]] || die "无法生成 TURN 密码"

info "解压独立 coturn 到 $TURN_HOME"
rm -rf "$TURN_HOME"
mkdir -p "$TURN_HOME"
if command -v tar >/dev/null 2>&1; then
  tar -xzf "$BUNDLE" -C "$TURN_HOME"
elif [[ -x "$ROOT/offline/bin/busybox" ]]; then
  "$ROOT/offline/bin/busybox" tar -xzf "$BUNDLE" -C "$TURN_HOME"
else
  die "系统缺少 tar，且离线包没有 offline/bin/busybox"
fi

info "写入 /etc/turnserver.conf"
mkdir -p /var/log/coturn
cat >/etc/turnserver.conf <<EOF
listening-port=${TURN_PORT}
listening-ip=${TURN_HOST}
relay-ip=${TURN_HOST}
fingerprint
lt-cred-mech
realm=iop-turn
user=${TURN_USER}:${TURN_PASSWORD}
min-port=${MIN_PORT}
max-port=${MAX_PORT}
no-multicast-peers
simple-log
log-file=/var/log/coturn/turnserver.log
EOF
chmod 600 /etc/turnserver.conf

info "安装 coturn systemd 服务"
cat >/etc/systemd/system/coturn.service <<EOF
[Unit]
Description=coturn TURN server for IOP
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
Environment=LD_LIBRARY_PATH=${TURN_HOME}/lib
ExecStart=${TURN_HOME}/bin/turnserver -c /etc/turnserver.conf
Restart=always
RestartSec=3
LimitNOFILE=1048576

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable coturn >/dev/null 2>&1 || true
systemctl restart coturn

if [[ -f "$ENV_FILE" ]]; then
  info "写入平台 WebRTC 配置: $ENV_FILE"
  if [[ -x "$APP_DIR/.venv/bin/python" ]]; then
    PY="$APP_DIR/.venv/bin/python"
  else
    PY="python3"
  fi
  "$PY" - "$ENV_FILE" "$TURN_HOST" "$TURN_PORT" "$TURN_USER" "$TURN_PASSWORD" "$FORCE_RELAY" <<'PY'
import sys
from pathlib import Path
p = Path(sys.argv[1])
host, port, user, password, force = sys.argv[2:7]
values = {
    "WEBRTC_STUN_URLS": f"stun:{host}:{port}",
    "WEBRTC_TURN_URLS": f"turn:{host}:{port}?transport=udp,turn:{host}:{port}?transport=tcp",
    "WEBRTC_TURN_USERNAME": user,
    "WEBRTC_TURN_CREDENTIAL": password,
    "WEBRTC_FORCE_RELAY": force,
}
lines = []
for line in p.read_text(encoding="utf-8").splitlines():
    key = line.split("=", 1)[0].strip() if "=" in line else ""
    if key in values:
        continue
    lines.append(line)
lines += [f"{key}={value}" for key, value in values.items()]
p.write_text("\n".join(lines) + "\n", encoding="utf-8")
p.chmod(0o600)
PY
else
  warn "未找到 $ENV_FILE；请先安装平台，再重新执行本脚本"
fi

if command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --state >/dev/null 2>&1; then
  info "firewalld 放行 TURN 端口"
  firewall-cmd --permanent --add-port="${TURN_PORT}/tcp" >/dev/null || true
  firewall-cmd --permanent --add-port="${TURN_PORT}/udp" >/dev/null || true
  firewall-cmd --permanent --add-port="${MIN_PORT}-${MAX_PORT}/udp" >/dev/null || true
  firewall-cmd --reload >/dev/null || true
fi

if systemctl list-unit-files snmp-nms.service >/dev/null 2>&1; then
  info "重启平台使 WebRTC 配置生效"
  systemctl restart snmp-nms
fi

sleep 2
info "TURN 服务状态: $(systemctl is-active coturn)"
info "平台服务状态: $(systemctl is-active snmp-nms 2>/dev/null || echo unknown)"
info "TURN 地址: turn:${TURN_HOST}:${TURN_PORT}"
info "TURN 用户: ${TURN_USER}"
info "TURN 密码已写入: ${ENV_FILE}（WEBRTC_TURN_CREDENTIAL）"
info "请确认客户端可访问 ${TURN_HOST} 的 ${TURN_PORT}/TCP、${TURN_PORT}/UDP 和 ${MIN_PORT}-${MAX_PORT}/UDP"
