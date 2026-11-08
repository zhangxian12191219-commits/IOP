#!/usr/bin/env bash
# ============================================================================
# 智能运维服务平台 - 一键卸载脚本
#
# 用法：
#   sudo bash uninstall.sh                 # 交互选择：保留数据 / 彻底删除
#   sudo bash uninstall.sh --keep-data     # 停止并移除服务/容器，保留程序和数据
#   sudo bash uninstall.sh --purge         # 停止并删除服务/容器，彻底删除程序和数据
#   sudo bash uninstall.sh --purge --yes   # 免二次确认彻底删除（谨慎）
#   sudo APP_DIR=/data/snmp-monitor bash uninstall.sh --keep-data
#
# 默认保留程序和数据，但会清除部署环境变量文件和安装时注册的系统用户；
# --purge 还会删除数据库、授权文件、上传文件、日志和程序目录。
# ============================================================================
set -euo pipefail

SERVICE="snmp-nms"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="${APP_DIR:-$ROOT}"
APP_USER="${APP_USER:-snmp}"
MODE=""
ASSUME_YES=0
KEEP_USER=0
DOCKER_COMPOSE=""

usage() {
  cat <<'EOF'
用法: sudo bash uninstall.sh [选项]

选项:
  --keep-data      停止并移除服务/容器，保留程序和 data 目录（默认交互模式推荐）
  --purge          彻底卸载：删除服务/容器、程序目录、数据库、授权、上传文件和日志
  --yes, -y        跳过彻底删除的二次确认
  --keep-user      保留安装时创建的系统用户（默认会删除）
  --remove-user    兼容旧参数，删除系统用户（默认行为）
  -h, --help       显示帮助

环境变量文件和系统用户:
  默认删除 deploy/snmp-nms.env、$APP_DIR/.env 以及安装时创建的 snmp 系统用户/用户组
  如系统用户为其他服务共用，请使用 --keep-user 保留用户

环境变量:
  APP_DIR          安装目录，默认取脚本所在目录
  APP_USER         系统服务用户，默认 snmp

示例:
  sudo bash uninstall.sh --keep-data
  sudo APP_DIR=/data/snmp-monitor bash uninstall.sh --purge
  docker compose down -v        # Docker 用户也可直接使用 Compose 命令彻底清理
EOF
}

die() {
  echo "[错误] $*" >&2
  exit 1
}

info() {
  echo "[信息] $*"
}

warn() {
  echo "[警告] $*" >&2
}

remove_deployment_env() {
  local file
  for file in \
    "$APP_DIR/deploy/snmp-nms.env" \
    "$APP_DIR/.env" \
    "/etc/sysconfig/snmp-nms" \
    "/etc/default/snmp-nms"; do
    if [[ -f "$file" ]]; then
      rm -f -- "$file"
      info "已删除环境变量配置: $file"
    fi
  done
}

remove_service_user() {
  if [[ "$KEEP_USER" == "1" ]]; then
    info "按 --keep-user 保留系统用户: $APP_USER"
    return 0
  fi
  if id -u "$APP_USER" >/dev/null 2>&1; then
    info "删除安装时创建的系统用户: $APP_USER"
    userdel "$APP_USER" 2>/dev/null || warn "无法删除用户 $APP_USER（可能有残留进程或用户被共用），请手工检查"
  fi
  if getent group "$APP_USER" >/dev/null 2>&1; then
    groupdel "$APP_USER" 2>/dev/null || warn "无法删除用户组 $APP_USER，请手工检查"
  fi
}

for arg in "$@"; do
  case "$arg" in
    --keep-data) MODE="keep" ;;
    --purge) MODE="purge" ;;
    --yes|-y) ASSUME_YES=1 ;;
    --keep-user) KEEP_USER=1 ;;
    --remove-user) KEEP_USER=0 ;;
    -h|--help) usage; exit 0 ;;
    *) die "未知参数: $arg（使用 --help 查看用法）" ;;
  esac
done

if [[ $EUID -ne 0 ]]; then
  HINT=""
  if [[ "$MODE" == "purge" ]]; then HINT="--purge"; elif [[ "$MODE" == "keep" ]]; then HINT="--keep-data"; fi
  die "请使用 root 执行：sudo bash uninstall.sh ${HINT}"
fi

# 安装目录安全检查，避免误删根目录/上级目录
APP_DIR="$(cd "$APP_DIR" 2>/dev/null && pwd)" || die "安装目录不存在: $APP_DIR"
[[ -n "$APP_DIR" && "$APP_DIR" != "/" ]] || die "APP_DIR 不合法，拒绝执行"
case "$APP_DIR" in
  /bin|/boot|/dev|/etc|/home|/opt|/root|/srv|/usr|/var|/tmp) die "APP_DIR 指向系统目录，拒绝执行: $APP_DIR" ;;
esac
if [[ ! -f "$APP_DIR/run_backend.py" && ! -f "$APP_DIR/docker-compose.yml" ]]; then
  die "目录 $APP_DIR 不像 智能运维服务平台安装目录（缺少 run_backend.py / docker-compose.yml）"
fi

if [[ -z "$MODE" ]]; then
  if [[ ! -t 0 ]]; then
    die "非交互模式请显式指定 --keep-data 或 --purge"
  fi
  echo "=================================================================="
  echo " 智能运维服务平台一键卸载"
  echo " 安装目录: $APP_DIR"
  echo "------------------------------------------------------------------"
  echo " 1) 保留程序和 data 数据目录，移除服务/容器/环境变量/系统用户（推荐）"
  echo " 2) 彻底删除：服务、容器、程序、数据库、授权、上传文件和日志"
  echo " 3) 取消"
  echo "=================================================================="
  echo " 两种模式都会清除部署环境变量配置和安装时创建的 $APP_USER 系统用户"
  echo "=================================================================="
  read -r -p "请选择 [1/2/3，默认 1]: " choice
  choice="${choice:-1}"
  case "$choice" in
    1) MODE="keep" ;;
    2) MODE="purge" ;;
    3) echo "已取消"; exit 0 ;;
    *) die "无效选择: $choice" ;;
  esac
fi

if [[ "$MODE" == "purge" && "$ASSUME_YES" != "1" ]]; then
  warn "即将彻底删除以下内容，且不可恢复："
  echo "  程序目录: $APP_DIR"
  echo "  数据目录: $APP_DIR/data"
  echo "  Docker 命名卷: postgres-data / redis-data / app-data（如适用）"
  echo "  数据库、授权文件、上传文件、日志、备份和配置文件"
  read -r -p "确认继续？输入 DELETE 确认，其他任意内容取消: " confirm_text
  [[ "$confirm_text" == "DELETE" ]] || { echo "已取消"; exit 0; }
fi

# 识别部署方式
HAS_SYSTEMD=0
HAS_DOCKER=0
HAS_MANUAL=0
if command -v systemctl >/dev/null 2>&1; then
  if [[ -f "/etc/systemd/system/${SERVICE}.service" ]] \
    || systemctl list-unit-files --no-legend "${SERVICE}.service" 2>/dev/null | grep -q "^${SERVICE}.service"; then
    HAS_SYSTEMD=1
  fi
fi
if command -v docker >/dev/null 2>&1 && [[ -f "$APP_DIR/docker-compose.yml" ]]; then
  if docker compose version >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker compose"
  elif command -v docker-compose >/dev/null 2>&1; then
    DOCKER_COMPOSE="docker-compose"
  fi
  if [[ -n "$DOCKER_COMPOSE" ]]; then
    if (cd "$APP_DIR" && $DOCKER_COMPOSE ps -aq 2>/dev/null | grep -q .); then
      HAS_DOCKER=1
    elif docker volume ls -q 2>/dev/null | grep -Eq "(postgres-data|redis-data|app-data)$"; then
      HAS_DOCKER=1
    fi
  fi
fi
if [[ -x "$APP_DIR/start.sh" ]] && [[ -f "$APP_DIR/data/run/supervisor.pid" || -f "$APP_DIR/data/run/backend.pid" ]]; then
  HAS_MANUAL=1
fi

info "部署方式: systemd=$HAS_SYSTEMD docker=$HAS_DOCKER manual=$HAS_MANUAL"
info "处理模式: $([[ "$MODE" == "purge" ]] && echo '彻底删除' || echo '保留数据')"

# systemd 服务、健康检查定时器、健康检查二进制
if [[ "$HAS_SYSTEMD" == "1" ]]; then
  info "停止并移除 systemd 服务"
  systemctl disable --now "${SERVICE}-healthcheck.timer" 2>/dev/null || true
  systemctl disable --now "${SERVICE}.service" 2>/dev/null || true
  rm -f \
    "/etc/systemd/system/${SERVICE}.service" \
    "/etc/systemd/system/${SERVICE}-healthcheck.service" \
    "/etc/systemd/system/${SERVICE}-healthcheck.timer" \
    "/usr/local/bin/snmp-nms-healthcheck"
  rm -rf "/etc/systemd/system/${SERVICE}.service.d"
  systemctl daemon-reload
  systemctl reset-failed 2>/dev/null || true
fi

# Docker Compose 容器
if [[ "$HAS_DOCKER" == "1" ]]; then
  info "停止 Docker Compose 服务"
  if [[ "$MODE" == "purge" ]]; then
    (cd "$APP_DIR" && $DOCKER_COMPOSE down -v) || warn "docker compose down -v 执行失败，请手工检查"
  else
    (cd "$APP_DIR" && $DOCKER_COMPOSE down) || warn "docker compose down 执行失败，请手工检查"
  fi
fi

# 非 systemd 的 start.sh 守护进程
if [[ "$HAS_MANUAL" == "1" && "$HAS_SYSTEMD" != "1" ]]; then
  info "停止手动启动的后台进程"
  if [[ -x "$APP_DIR/start.sh" ]]; then
    (cd "$APP_DIR" && ./start.sh stop) || warn "start.sh stop 执行失败，请手工检查"
  fi
fi

# 清除部署环境变量和安装时注册的系统用户，保证恢复到初始化系统状态
remove_deployment_env
remove_service_user

# 保留模式：程序和数据保留，但服务注册、环境变量和系统用户已清除
if [[ "$MODE" == "keep" ]]; then
  info "服务已停止并移除；程序保留在: $APP_DIR"
  info "数据保留在: $APP_DIR/data"
  info "部署环境变量和系统用户已清除；如需彻底删除，请执行: sudo bash $APP_DIR/uninstall.sh --purge"
  exit 0
fi

# 彻底删除前停止所有可能仍占用目录的进程
if [[ "$HAS_SYSTEMD" != "1" && "$HAS_DOCKER" != "1" ]]; then
  pkill -f "$APP_DIR/run_backend.py" 2>/dev/null || true
  pkill -f "uvicorn.*app:app" 2>/dev/null || true
fi

info "删除程序和数据目录: $APP_DIR"
case "$APP_DIR" in
  *".."*) die "APP_DIR 包含 ..，拒绝删除: $APP_DIR" ;;
esac
rm -rf -- "$APP_DIR"

echo "=================================================================="
echo " 卸载完成"
echo "------------------------------------------------------------------"
echo " 已停止并移除 systemd/Docker/手动启动相关服务"
echo " 已删除部署环境变量文件和注册的系统用户"
echo " 已删除程序目录、SQLite 数据、授权文件、上传文件和日志"
echo " 如使用外部 PostgreSQL/Redis，请另行清理对应数据库、用户或缓存"
echo " 请手工检查 Nginx/Caddy/防火墙配置和系统备份文件"
echo "=================================================================="


