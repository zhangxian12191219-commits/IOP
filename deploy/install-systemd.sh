#!/usr/bin/env bash
# ============================================================================
# 智能运维服务平台 - systemd 一键安装（含健康检查定时器）
#
# 用法（root）:
#   sudo bash deploy/install-systemd.sh                 # 安装/升级并启动
#   sudo bash deploy/install-systemd.sh --build-frontend# 同时构建前端
#   sudo bash deploy/install-systemd.sh --offline       # 离线安装（仅使用包内文件）
#   sudo bash deploy/install-systemd.sh --no-postgres --no-redis      # 不自动安装数据库/缓存
#   sudo bash deploy/install-systemd.sh --with-postgres --with-redis  # 已有环境强制对接
#   sudo APP_DIR=/data/snmp-monitor bash deploy/install-systemd.sh
#
# 数据库 / 缓存:
#   - 新装默认自动安装 PostgreSQL + Redis，创建数据库/用户并生成随机密码写入环境变量文件
#   - 安装或验证失败时安全回退 SQLite / 进程内缓存，并打印明确警告，不会中断安装
#   - 离线包可放置 offline/os-packages/debian/*.deb 或 offline/os-packages/rhel/*.rpm
#   - 离线包未包含系统包时不会伪造安装成功，会明确提示并回退
#
# 说明:
#   - 以 systemd 服务方式运行，崩溃/异常退出后 3 秒自动重启（Restart=always）
#   - 每 2 分钟健康检查一次，进程假死时自动重启
#   - 代码同步到 APP_DIR（默认 /opt/snmp-monitor），数据在 APP_DIR/data
# ============================================================================
set -eu
# 兼容不支持 pipefail 的 bash / ash；支持时再启用，避免安装直接中断
if (set -o pipefail) 2>/dev/null; then
  set -o pipefail
fi

SERVICE="snmp-nms"
APP_USER="${APP_USER:-root}"
APP_DIR="${APP_DIR:-/opt/snmp-monitor}"
PORT="${PORT:-8000}"
PYTHON_BIN="${PYTHON_BIN:-}"
BUILD_FRONTEND=0
OFFLINE_MODE=0
# 新装默认自动安装 PostgreSQL + Redis；设为 0 或使用 --no-postgres/--no-redis 可关闭
AUTO_PROVISION_SERVICES="${AUTO_PROVISION_SERVICES:-1}"
WANT_POSTGRES=""
WANT_REDIS=""
PG_DB_NAME="${PG_DB_NAME:-snmp_nms}"
PG_DB_USER="${PG_DB_USER:-nms}"
PG_HOST="${PG_HOST:-127.0.0.1}"
PG_PORT="${PG_PORT:-5432}"
REDIS_HOST="${REDIS_HOST:-127.0.0.1}"
REDIS_PORT="${REDIS_PORT:-6379}"
REDIS_DB_INDEX="${REDIS_DB_INDEX:-0}"
ENV_CREATED=0
ENV_FILE=""

for arg in "$@"; do
  case "$arg" in
    --build-frontend) BUILD_FRONTEND=1 ;;
    --offline) OFFLINE_MODE=1 ;;
    --with-postgres) WANT_POSTGRES=1 ;;
    --no-postgres) WANT_POSTGRES=0 ;;
    --with-redis) WANT_REDIS=1 ;;
    --no-redis) WANT_REDIS=0 ;;
    -h|--help) sed -n '2,/^# =====/p' "$0"; exit 0 ;;
    *) echo "未知参数: $arg"; exit 1 ;;
  esac
done

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

info() { echo -e "\033[32m==>\033[0m $*"; }
warn() { echo -e "\033[33m!! \033[0m $*"; }
die() { echo -e "\033[31m!! \033[0m $*" >&2; exit 1; }

# ===========================================================================
# 系统依赖（PostgreSQL / Redis）辅助函数
# 原则：只做可验证的安装与对接；任何一步失败都返回非 0 并由调用方安全回退，
#       不伪造成功、不中断安装。
# ===========================================================================
OFFLINE_OS_PKGDIR="$APP_DIR/offline/os-packages"
PKG_FAMILY=""
PG_SERVICE=""
PG_PASSWORD=""
PG_URL=""
REDIS_SERVICE=""
REDIS_PASSWORD=""
REDIS_URL_VALUE=""
DB_SUMMARY="SQLite（内置，无需外部数据库）"
CACHE_SUMMARY="进程内缓存"

have() { command -v "$1" >/dev/null 2>&1; }

rand_hex() {
  # 生成随机十六进制串（默认 16 字节 = 32 字符）；密码仅含 0-9a-f，可安全写入 URL
  local bytes="${1:-16}"
  if have openssl; then
    openssl rand -hex "$bytes" 2>/dev/null && return 0
  fi
  if [[ -r /dev/urandom ]] && have od && have tr; then
    head -c "$bytes" /dev/urandom | od -An -tx1 | tr -d ' \n' && return 0
  fi
  return 1
}

detect_pkg_family() {
  if [[ -n "$PKG_FAMILY" ]]; then
    echo "$PKG_FAMILY"
    return 0
  fi
  if have apt-get; then
    PKG_FAMILY="debian"
  elif have dnf || have yum; then
    PKG_FAMILY="rhel"
  else
    PKG_FAMILY="unknown"
  fi
  echo "$PKG_FAMILY"
}

unit_exists() {
  # $1 完整单元名，如 redis-server.service
  systemctl list-unit-files --type=service --no-legend 2>/dev/null \
    | awk -v u="$1" '$1 == u { found = 1 } END { exit(found ? 0 : 1) }'
}

wait_for_service() {
  local unit="$1" timeout="${2:-30}" i=0
  while [[ $i -lt $timeout ]]; do
    if systemctl is-active --quiet "$unit"; then
      return 0
    fi
    sleep 1
    i=$((i + 1))
  done
  systemctl is-active --quiet "$unit"
}

install_os_packages() {
  # 安装系统包：在线用 apt/dnf；离线优先使用 offline/os-packages 下的本地包
  # 用法: install_os_packages <debian|rhel> 包名...
  local family="$1"
  shift
  local pkgs=("$@")
  local offline_dir
  if [[ "$family" == "debian" ]]; then
    offline_dir="$OFFLINE_OS_PKGDIR/debian"
  else
    offline_dir="$OFFLINE_OS_PKGDIR/rhel"
  fi

  if [[ "$OFFLINE_MODE" == "1" ]]; then
    local files=()
    if [[ -d "$offline_dir" ]]; then
      if [[ "$family" == "debian" ]]; then
        files=("$offline_dir"/*.deb)
      else
        files=("$offline_dir"/*.rpm)
      fi
      # 通配符没有匹配时数组里是字面量路径
      if [[ ${#files[@]} -gt 0 && ! -e "${files[0]}" ]]; then
        files=()
      fi
    fi
    if [[ ${#files[@]} -eq 0 ]]; then
      warn "离线模式：未找到本地系统安装包（$offline_dir），跳过该组件安装"
      return 1
    fi
    info "离线安装系统包（$family）：${files[*]}"
    if [[ "$family" == "debian" ]]; then
      DEBIAN_FRONTEND=noninteractive dpkg -i "${files[@]}" 2>&1 | tail -n 20 || return 1
    else
      rpm -Uvh --replacepkgs "${files[@]}" 2>&1 | tail -n 20 || return 1
    fi
    return 0
  fi

  if [[ "$family" == "debian" ]]; then
    DEBIAN_FRONTEND=noninteractive apt-get update -qq >/dev/null 2>&1 \
      || warn "apt-get update 失败，继续使用现有软件源索引"
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${pkgs[@]}" 2>&1 \
      | tail -n 20 || return 1
  else
    local pm="dnf"
    have dnf || pm="yum"
    "$pm" install -y "${pkgs[@]}" 2>&1 | tail -n 20 || return 1
  fi
  return 0
}

pg_service_name() {
  local found
  found="$(systemctl list-unit-files --type=service --no-legend 2>/dev/null \
    | awk '$1 ~ /^postgresql(-[0-9]+)?\.service$/ { print $1; exit }')"
  if [[ -n "$found" ]]; then
    echo "${found%.service}"
    return 0
  fi
  return 1
}

run_psql_as_postgres() {
  # 以 postgres 系统用户执行 psql（保留参数引用，避免 SQL/路径被拆词）
  if have runuser; then
    runuser -u postgres -- psql -tAq -v ON_ERROR_STOP=1 "$@" && return 0
  fi
  if have su; then
    local quoted="" a
    for a in "$@"; do
      quoted+=" $(printf '%q' "$a")"
    done
    su -s /bin/sh postgres -c "psql -tAq -v ON_ERROR_STOP=1${quoted}" && return 0
  fi
  if have sudo; then
    sudo -u postgres psql -tAq -v ON_ERROR_STOP=1 "$@" && return 0
  fi
  return 1
}

verify_postgres_with_app() {
  # 使用应用实际使用的 psycopg2 驱动验证 TCP + 密码登录
  [[ -x "$VENV_PY" ]] || return 1
  "$VENV_PY" - "$PG_HOST" "$PG_PORT" "$PG_DB_NAME" "$PG_DB_USER" "$PG_PASSWORD" <<'PY' >/dev/null 2>&1
import sys

host, port, dbname, user, password = sys.argv[1:6]
try:
    import psycopg2  # noqa: F401
except Exception:
    sys.exit(2)
try:
    conn = psycopg2.connect(
        host=host, port=int(port), dbname=dbname, user=user,
        password=password, connect_timeout=5,
    )
    cur = conn.cursor()
    cur.execute("SELECT 1")
    cur.fetchone()
    cur.close()
    conn.close()
except Exception:
    sys.exit(3)
PY
}

fix_pg_hba_auth() {
  # RHEL 系默认 pg_hba.conf 对 127.0.0.1 使用 ident，会导致密码登录失败；
  # 仅把本机回环行改为 scram-sha-256，并保留时间戳备份。
  local hba="" cand
  for cand in /var/lib/pgsql/data/pg_hba.conf /etc/postgresql/*/main/pg_hba.conf /var/lib/postgresql/*/main/pg_hba.conf; do
    if [[ -f "$cand" ]]; then
      hba="$cand"
      break
    fi
  done
  if [[ -z "$hba" ]]; then
    warn "未找到 pg_hba.conf，跳过认证方式自动修正"
    return 1
  fi
  cp -a "$hba" "${hba}.bak.snmp-nms.$(date +%Y%m%d%H%M%S)" 2>/dev/null \
    || cp "$hba" "${hba}.bak.snmp-nms" 2>/dev/null || true
  sed -i -E \
    -e 's#^(host[[:space:]]+all[[:space:]]+all[[:space:]]+127\.0\.0\.1/32[[:space:]]+)(ident|md5)([[:space:]].*)?$#\1scram-sha-256\3#' \
    -e 's#^(host[[:space:]]+all[[:space:]]+all[[:space:]]+::1/128[[:space:]]+)(ident|md5)([[:space:]].*)?$#\1scram-sha-256\3#' \
    "$hba"
  # 恢复 SELinux 上下文，避免 sed 重写文件后 postgres 无法读取 pg_hba.conf
  if have restorecon; then
    restorecon "$hba" >/dev/null 2>&1 || true
  fi
  systemctl reload "$PG_SERVICE" >/dev/null 2>&1 \
    || systemctl restart "$PG_SERVICE" >/dev/null 2>&1 || return 1
  sleep 1
  return 0
}

provision_postgresql() {
  local family
  family="$(detect_pkg_family)"

  # 应用必须能加载 psycopg2，否则切换后无法启动
  if ! "$VENV_PY" -c "import psycopg2" >/dev/null 2>&1; then
    warn "Python 虚拟环境缺少 psycopg2（PostgreSQL 驱动），跳过 PostgreSQL 自动对接"
    return 1
  fi

  case "$family" in
    debian)
      if ! have psql; then
        install_os_packages debian postgresql postgresql-client || return 1
      fi
      ;;
    rhel)
      if ! have psql; then
        install_os_packages rhel postgresql-server postgresql \
          || install_os_packages rhel postgresql || return 1
      fi
      if [[ ! -f /var/lib/pgsql/data/PG_VERSION ]] && have postgresql-setup; then
        postgresql-setup --initdb >/dev/null 2>&1 \
          || postgresql-setup initdb >/dev/null 2>&1 || true
      fi
      ;;
    *)
      warn "未识别的包管理器（缺少 apt-get/dnf/yum），无法自动安装 PostgreSQL"
      return 1
      ;;
  esac

  PG_SERVICE="$(pg_service_name || true)"
  if [[ -z "$PG_SERVICE" ]]; then
    warn "未找到 PostgreSQL systemd 服务（postgresql[-版本]）"
    return 1
  fi
  systemctl enable --now "$PG_SERVICE" >/dev/null 2>&1 || true
  if ! wait_for_service "$PG_SERVICE" 30; then
    warn "PostgreSQL 服务（$PG_SERVICE）未能在 30 秒内启动"
    return 1
  fi
  if have pg_isready && ! pg_isready -h "$PG_HOST" -p "$PG_PORT" >/dev/null 2>&1; then
    warn "PostgreSQL 未在 ${PG_HOST}:${PG_PORT} 监听，跳过自动对接"
    return 1
  fi

  PG_PASSWORD="$(rand_hex 16 || true)"
  if [[ -z "$PG_PASSWORD" ]]; then
    warn "无法生成随机密码（缺少 openssl/od），跳过 PostgreSQL 自动对接"
    return 1
  fi

  local tmp_sql
  tmp_sql="$(mktemp /tmp/snmp-nms-pg-XXXXXX.sql 2>/dev/null || mktemp)"
  cat > "$tmp_sql" <<SQL
SET password_encryption = 'scram-sha-256';
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${PG_DB_USER}') THEN
    CREATE ROLE ${PG_DB_USER} LOGIN PASSWORD '${PG_PASSWORD}';
  ELSE
    ALTER ROLE ${PG_DB_USER} WITH LOGIN PASSWORD '${PG_PASSWORD}';
  END IF;
END
\$\$;
SQL
  chmod 644 "$tmp_sql"
  if ! run_psql_as_postgres -f "$tmp_sql"; then
    rm -f "$tmp_sql"
    warn "创建/更新 PostgreSQL 角色失败（无法以 postgres 用户连接数据库）"
    return 1
  fi
  rm -f "$tmp_sql"

  local db_exists=""
  db_exists="$(run_psql_as_postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${PG_DB_NAME}'" 2>/dev/null || true)"
  if [[ "$(printf '%s' "$db_exists" | tr -d '[:space:]')" != "1" ]]; then
    if ! run_psql_as_postgres -c "CREATE DATABASE ${PG_DB_NAME} OWNER ${PG_DB_USER}"; then
      warn "创建 PostgreSQL 数据库 ${PG_DB_NAME} 失败"
      return 1
    fi
  fi
  run_psql_as_postgres -c "ALTER DATABASE ${PG_DB_NAME} OWNER TO ${PG_DB_USER}" >/dev/null 2>&1 || true

  if ! verify_postgres_with_app; then
    warn "PostgreSQL 密码登录验证失败，尝试修正本机 pg_hba.conf（ident/md5 → scram-sha-256）"
    fix_pg_hba_auth || true
    if ! verify_postgres_with_app; then
      warn "PostgreSQL 连通性验证未通过，回退 SQLite"
      return 1
    fi
  fi

  PG_URL="postgresql+psycopg2://${PG_DB_USER}:${PG_PASSWORD}@${PG_HOST}:${PG_PORT}/${PG_DB_NAME}"
  return 0
}

verify_redis_with_app() {
  [[ -x "$VENV_PY" ]] || return 1
  "$VENV_PY" - "$REDIS_URL_VALUE" <<'PY' >/dev/null 2>&1
import sys

try:
    import redis
except Exception:
    sys.exit(2)
try:
    client = redis.Redis.from_url(
        sys.argv[1], decode_responses=True,
        socket_connect_timeout=3, socket_timeout=3,
    )
    if client.ping() is not True:
        sys.exit(3)
    client.close()
except Exception:
    sys.exit(3)
PY
}

provision_redis() {
  local family
  family="$(detect_pkg_family)"

  if ! "$VENV_PY" -c "import redis" >/dev/null 2>&1; then
    warn "Python 虚拟环境缺少 redis 驱动，跳过 Redis 自动对接（使用内存缓存）"
    return 1
  fi

  if ! have redis-cli; then
    case "$family" in
      debian)
        install_os_packages debian redis-server || return 1
        ;;
      rhel)
        install_os_packages rhel redis || install_os_packages rhel valkey || return 1
        ;;
      *)
        warn "未识别的包管理器（缺少 apt-get/dnf/yum），无法自动安装 Redis"
        return 1
        ;;
    esac
  fi
  if ! have redis-cli; then
    warn "未找到 redis-cli，无法验证 Redis 连接"
    return 1
  fi

  local cand svc=""
  for cand in redis-server redis valkey-server valkey; do
    if unit_exists "${cand}.service"; then
      svc="$cand"
      break
    fi
  done
  if [[ -z "$svc" ]]; then
    warn "未找到 Redis/Valkey systemd 服务（redis-server / redis / valkey）"
    return 1
  fi
  REDIS_SERVICE="$svc"
  systemctl enable --now "$svc" >/dev/null 2>&1 || true
  if ! wait_for_service "$svc" 20; then
    warn "Redis 服务（$svc）未能在 20 秒内启动"
    return 1
  fi

  local ping_out=""
  ping_out="$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" ping 2>/dev/null || true)"
  if [[ "$ping_out" != *PONG* ]]; then
    warn "Redis 未返回 PONG（可能已被设置密码），跳过自动对接"
    return 1
  fi

  REDIS_PASSWORD="$(rand_hex 16 || true)"
  if [[ -z "$REDIS_PASSWORD" ]]; then
    warn "无法生成随机密码，Redis 使用本机无密码连接"
    REDIS_URL_VALUE="redis://${REDIS_HOST}:${REDIS_PORT}/${REDIS_DB_INDEX}"
    verify_redis_with_app || return 1
    return 0
  fi

  local conf="" c
  for c in /etc/redis/redis.conf /etc/redis.conf /etc/valkey/valkey.conf /etc/valkey.conf; do
    if [[ -f "$c" ]]; then
      conf="$c"
      break
    fi
  done
  if [[ -z "$conf" ]]; then
    warn "未找到 Redis 配置文件，无法持久化密码；回退本机无密码连接"
    REDIS_URL_VALUE="redis://${REDIS_HOST}:${REDIS_PORT}/${REDIS_DB_INDEX}"
    verify_redis_with_app || return 1
    return 0
  fi

  cp -a "$conf" "${conf}.bak.snmp-nms.$(date +%Y%m%d%H%M%S)" 2>/dev/null \
    || cp "$conf" "${conf}.bak.snmp-nms" 2>/dev/null || true
  if grep -qE '^[[:space:]]*requirepass[[:space:]]' "$conf"; then
    sed -i -E "s#^[[:space:]]*requirepass[[:space:]].*#requirepass ${REDIS_PASSWORD}#" "$conf"
  elif grep -qE '^[[:space:]]*#[[:space:]]*requirepass' "$conf"; then
    sed -i -E "s#^[[:space:]]*#[[:space:]]*requirepass.*#requirepass ${REDIS_PASSWORD}#" "$conf"
  else
    printf '\nrequirepass %s\n' "$REDIS_PASSWORD" >> "$conf"
  fi
  # 恢复 SELinux 上下文，避免 sed 重写配置后 Redis 无法读取
  if have restorecon; then
    restorecon "$conf" >/dev/null 2>&1 || true
  fi
  systemctl restart "$svc" >/dev/null 2>&1 || true
  sleep 1

  ping_out="$(redis-cli -h "$REDIS_HOST" -p "$REDIS_PORT" -a "$REDIS_PASSWORD" ping 2>/dev/null || true)"
  if [[ "$ping_out" != *PONG* ]]; then
    warn "Redis 设置密码后连接失败，配置备份：${conf}.bak.snmp-nms.*；回退内存缓存"
    return 1
  fi
  REDIS_URL_VALUE="redis://:${REDIS_PASSWORD}@${REDIS_HOST}:${REDIS_PORT}/${REDIS_DB_INDEX}"
  verify_redis_with_app || {
    warn "Python redis 驱动无法使用新密码连接 Redis，回退内存缓存"
    return 1
  }
  return 0
}

env_get() {
  [[ -f "$ENV_FILE" ]] || return 0
  grep -E "^[[:space:]]*$1=" "$ENV_FILE" 2>/dev/null | tail -n 1 | cut -d= -f2- || true
}

env_set() {
  # 在 systemd EnvironmentFile 中设置键值（已验证行则替换，注释行则取消注释，否则追加）
  local key="$1" value="$2" escaped
  [[ -f "$ENV_FILE" ]] || return 0
  escaped="$(printf '%s' "$value" | sed -e 's/[&|\\]/\\&/g')"
  if grep -qE "^[[:space:]]*${key}=" "$ENV_FILE"; then
    sed -i "s|^[[:space:]]*${key}=.*|${key}=${escaped}|" "$ENV_FILE"
  elif grep -qE "^[[:space:]]*#[[:space:]]*${key}=" "$ENV_FILE"; then
    sed -i "s|^[[:space:]]*#[[:space:]]*${key}=.*|${key}=${escaped}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}
# ===================== 系统依赖辅助函数结束 =====================

[[ $EUID -eq 0 ]] || die "请使用 root 执行：sudo bash deploy/install-systemd.sh"
command -v systemctl >/dev/null || die "当前系统没有 systemd"

info "源目录: $SRC_DIR"
info "安装目录: $APP_DIR   运行用户: $APP_USER   端口: $PORT"

# ---------- 1) 运行用户 ----------
if ! id -u "$APP_USER" >/dev/null 2>&1; then
  info "创建系统用户 $APP_USER"
  useradd --system --home-dir "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER" 2>/dev/null \
    || useradd -r -d "$APP_DIR" -s /sbin/nologin "$APP_USER"
else
  info "用户已存在: $APP_USER"
fi

# ---------- 2) 同步代码 ----------
if [[ "$SRC_DIR" != "$APP_DIR" ]]; then
  info "同步代码到 $APP_DIR"
  mkdir -p "$APP_DIR"
  if command -v rsync >/dev/null 2>&1; then
    rsync -a --delete \
      --exclude node_modules --exclude .venv --exclude data \
      --exclude __pycache__ --exclude "*.pyc" --exclude "*.db" \
      --exclude deploy/snmp-nms.env \
      "$SRC_DIR"/ "$APP_DIR"/
  else
    tar -C "$SRC_DIR" \
      --exclude=node_modules --exclude=.venv --exclude=data \
      --exclude=__pycache__ --exclude="*.pyc" --exclude="*.db" \
      --exclude=deploy/snmp-nms.env \
      -cf - . | tar -C "$APP_DIR" -xf -
  fi
else
  info "已在安装目录内，跳过代码同步"
fi

mkdir -p "$APP_DIR/data/uploads" "$APP_DIR/data/logs"

# ---------- 2.1) 内置离线 Python 运行时 ----------
OFFLINE_DIR="$APP_DIR/offline"
PY_ARCHIVE="$OFFLINE_DIR/python-linux-x86_64.tar.xz"
if [[ ! -x "$OFFLINE_DIR/python/bin/python3" && -f "$PY_ARCHIVE" ]]; then
  info "解压内置 Python 运行时（xz 极限压缩，离线安装）"
  chmod +x "$OFFLINE_DIR/bin/busybox" 2>/dev/null || true
  if [[ -x "$OFFLINE_DIR/bin/busybox" ]]; then
    "$OFFLINE_DIR/bin/busybox" unxz -c "$PY_ARCHIVE" | "$OFFLINE_DIR/bin/busybox" tar -xf - -C "$OFFLINE_DIR"
  elif command -v tar >/dev/null 2>&1 && tar -xJf "$PY_ARCHIVE" -C "$OFFLINE_DIR" 2>/dev/null; then
    :
  else
    die "无法解压内置 Python；需要包内 offline/bin/busybox 或系统 xz/tar"
  fi
fi
if [[ -x "$OFFLINE_DIR/python/bin/python3" ]]; then
  PYTHON_BIN="$OFFLINE_DIR/python/bin/python3"
  info "使用内置 Python: $PYTHON_BIN"
elif [[ -z "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python3"
fi
command -v "$PYTHON_BIN" >/dev/null || die "未找到 $PYTHON_BIN；离线包应包含 offline/python-linux-x86_64.tar.xz"

# ---------- 3) Python 依赖 ----------
VENV_PY="$APP_DIR/.venv/bin/python"
VENV_PIP="$APP_DIR/.venv/bin/pip"
REQ_FILE="$APP_DIR/backend/requirements.txt"

if [[ -x "$VENV_PY" && -x "$OFFLINE_DIR/python/bin/python3" ]]; then
  VENV_VERSION="$("$VENV_PY" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
  OFFLINE_VERSION="$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>/dev/null || true)"
  if [[ -n "$VENV_VERSION" && -n "$OFFLINE_VERSION" && "$VENV_VERSION" != "$OFFLINE_VERSION" ]]; then
    info "已有虚拟环境 Python $VENV_VERSION 与内置 Python $OFFLINE_VERSION 不一致，重建虚拟环境"
    rm -rf "$APP_DIR/.venv"
  fi
fi
if [[ ! -x "$VENV_PY" ]]; then
  info "创建 Python 虚拟环境: $APP_DIR/.venv"
  "$PYTHON_BIN" -m venv "$APP_DIR/.venv"
else
  info "沿用已有 Python 虚拟环境: $APP_DIR/.venv"
fi

[[ -f "$REQ_FILE" ]] || die "依赖文件不存在: $REQ_FILE"

PY_VERSION="$("$VENV_PY" --version 2>&1)"
if [[ -x "$VENV_PIP" ]]; then
  PIP_VERSION="$("$VENV_PIP" --version 2>&1 | head -n 1)"
else
  PIP_VERSION="虚拟环境无 pip，使用内置 Python pip"
fi
mapfile -t REQ_LINES < <(awk 'NF && $1 !~ /^#/ {print}' "$REQ_FILE")

info "Python: ${PY_VERSION}"
info "pip: ${PIP_VERSION}"
info "依赖文件: $REQ_FILE（共 ${#REQ_LINES[@]} 项）"
info "待安装依赖清单:"
printf '    %s\n' "${REQ_LINES[@]}"

WHEEL_DIR="$APP_DIR/offline/wheels"
if [[ -d "$WHEEL_DIR" ]]; then
  info "检测到离线 wheels，使用 --no-index 安装，不访问互联网"
  if [[ ! -x "$VENV_PIP" ]]; then
    info "虚拟环境未包含 pip，直接将离线 wheels 安装到虚拟环境 site-packages"
    SITE_PACKAGES="$("$VENV_PY" -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')"
    "$PYTHON_BIN" -m pip install --no-index --find-links "$WHEEL_DIR" --no-cache-dir --target "$SITE_PACKAGES" -r "$REQ_FILE"
  else
    "$VENV_PIP" install --no-index --find-links "$WHEEL_DIR" --no-cache-dir --upgrade pip wheel
    "$VENV_PIP" install --no-index --find-links "$WHEEL_DIR" --no-cache-dir -r "$REQ_FILE"
  fi
else
  info "未发现离线 wheels，回退在线安装"
  info "升级 pip / wheel（显示实时下载进度）"
  "$VENV_PIP" install --progress-bar on -U pip wheel
  info "安装项目 Python 依赖，首次安装会下载较多包，请耐心等待..."
  PIP_STARTED_AT="$(date +%s)"
  "$VENV_PIP" install --progress-bar on -r "$REQ_FILE"
  PIP_FINISHED_AT="$(date +%s)"
fi
info "Python 依赖安装完成"

# ---------- 4) 前端 ----------
if [[ "$BUILD_FRONTEND" == "1" ]]; then
  if command -v npm >/dev/null 2>&1; then
    info "构建前端"
    ( cd "$APP_DIR/frontend" && npm install --no-audit --no-fund && npm run build )
  else
    warn "未安装 Node.js/npm，跳过前端构建"
  fi
fi
if [[ ! -f "$APP_DIR/frontend/dist/index.html" ]]; then
  warn "未找到 frontend/dist（前端页面无法访问）"
  warn "请在开发机执行 npm run build 后拷贝 dist，或安装 Node.js 后重新执行："
  warn "  sudo bash deploy/install-systemd.sh --build-frontend"
fi

# ---------- 5) 环境变量文件 ----------
ENV_FILE="$APP_DIR/deploy/snmp-nms.env"
if [[ ! -f "$ENV_FILE" ]]; then
  info "生成环境变量文件 $ENV_FILE"
  cp "$APP_DIR/deploy/snmp-nms.env.example" "$ENV_FILE"
  ENV_CREATED=1
  SECRET="$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
  sed -i "s|^AUTH_SECRET=.*|AUTH_SECRET=${SECRET}|" "$ENV_FILE"
  sed -i "s|^DATABASE_URL=.*|DATABASE_URL=sqlite:////${APP_DIR#/}/data/snmp_monitor.db|" "$ENV_FILE"
  sed -i "s|^UPLOAD_DIR=.*|UPLOAD_DIR=${APP_DIR}/data/uploads|" "$ENV_FILE"
  sed -i "s|^LOG_DIR=.*|LOG_DIR=${APP_DIR}/data/logs|" "$ENV_FILE" 2>/dev/null || true
  info "已生成随机 AUTH_SECRET；管理员初始密码文件: ${APP_DIR}/data/initial_admin_password.txt"
  info "查看初始密码: sudo cat ${APP_DIR}/data/initial_admin_password.txt（首次登录必须修改）"
else
  info "沿用已有环境变量文件: $ENV_FILE"
fi

# 兼容历史/Windows 换行：CR 会并入 systemd EnvironmentFile 的变量值，统一去掉
if [[ -f "$ENV_FILE" ]]; then
  sed -i 's/\r$//' "$ENV_FILE" 2>/dev/null || true
fi

# 兼容旧版本默认温度阈值：旧样例为 70，现行默认预警 80 / 告警 90
if [[ -f "$ENV_FILE" ]]; then
  if grep -q '^TEMPERATURE_THRESHOLD=70$' "$ENV_FILE"; then
    sed -i 's/^TEMPERATURE_THRESHOLD=70$/TEMPERATURE_THRESHOLD=80/' "$ENV_FILE"
    info "已将旧版 TEMPERATURE_THRESHOLD=70 更新为 80"
  fi
  if ! grep -q '^TEMPERATURE_CRITICAL_THRESHOLD=' "$ENV_FILE"; then
    printf '
TEMPERATURE_CRITICAL_THRESHOLD=90
' >> "$ENV_FILE"
  fi
fi

# ---------- 5.1) PostgreSQL / Redis 自动安装与对接 ----------
# 仅新装默认开启；已有环境变量文件时不自动切换，避免 SQLite 数据“看不见”。
# 任何失败都只回退到 SQLite / 内存缓存并打印警告，不中断安装。
# >>> 5.1-BLOCK-START（测试脚本按此标记提取本段逻辑）
DB_TARGET=""
REDIS_TARGET=""
if [[ "$ENV_CREATED" == "1" ]]; then
  DB_TARGET="${WANT_POSTGRES:-$AUTO_PROVISION_SERVICES}"
  REDIS_TARGET="${WANT_REDIS:-$AUTO_PROVISION_SERVICES}"
else
  DB_TARGET="${WANT_POSTGRES:-0}"
  REDIS_TARGET="${WANT_REDIS:-0}"
fi

if [[ "$OFFLINE_MODE" == "1" ]]; then
  if [[ -d "$OFFLINE_OS_PKGDIR" ]] && { [[ -n "$(ls -A "$OFFLINE_OS_PKGDIR/debian" 2>/dev/null || true)" ]] || [[ -n "$(ls -A "$OFFLINE_OS_PKGDIR/rhel" 2>/dev/null || true)" ]]; }; then
    info "检测到离线系统包目录: $OFFLINE_OS_PKGDIR"
  else
    warn "离线包未包含系统安装包（约定：offline/os-packages/debian/*.deb 或 offline/os-packages/rhel/*.rpm）"
    warn "本次将跳过 PostgreSQL/Redis 系统包安装，安全回退 SQLite / 进程内缓存"
  fi
fi

if [[ "$DB_TARGET" == "1" ]]; then
  EXISTING_DB_URL="$(env_get DATABASE_URL || true)"
  if [[ "$EXISTING_DB_URL" == postgresql* ]]; then
    info "环境变量文件已配置 PostgreSQL，跳过自动安装与密码重置"
  else
    if [[ "$ENV_CREATED" != "1" ]]; then
      warn "检测到已有环境变量文件：切换到 PostgreSQL 不会迁移现有 SQLite 数据，已备份原配置"
      cp -a "$ENV_FILE" "${ENV_FILE}.bak.$(date +%Y%m%d%H%M%S)" 2>/dev/null || true
    fi
    info "开始安装并验证 PostgreSQL（${PG_HOST}:${PG_PORT}）..."
    if provision_postgresql; then
      env_set DATABASE_URL "$PG_URL"
      info "PostgreSQL 已安装并完成对接: ${PG_HOST}:${PG_PORT}/${PG_DB_NAME}"
    else
      warn "PostgreSQL 自动安装/对接未完成，已安全回退 SQLite（平台仍可正常启动）"
      warn "如需重试：sudo bash deploy/install-systemd.sh --with-postgres"
    fi
  fi
else
  info "跳过 PostgreSQL 自动安装（使用内置 SQLite）"
fi

if [[ "$REDIS_TARGET" == "1" ]]; then
  EXISTING_REDIS_URL="$(env_get REDIS_URL || true)"
  if [[ -n "$EXISTING_REDIS_URL" ]]; then
    info "环境变量文件已配置 REDIS_URL，跳过自动安装与密码重置"
  else
    info "开始安装并验证 Redis（${REDIS_HOST}:${REDIS_PORT}）..."
    if provision_redis; then
      env_set REDIS_URL "$REDIS_URL_VALUE"
      env_set CACHE_ENABLED "1"
      info "Redis 已安装并完成对接: ${REDIS_HOST}:${REDIS_PORT}/${REDIS_DB_INDEX}"
    else
      warn "Redis 自动安装/对接未完成，已安全回退进程内缓存（平台仍可正常启动）"
      warn "如需重试：sudo bash deploy/install-systemd.sh --with-redis"
    fi
  fi
else
  info "跳过 Redis 自动安装（使用进程内缓存）"
fi

# 以最终生效的环境变量文件为准生成摘要
FINAL_DB_URL="$(env_get DATABASE_URL || true)"
case "$FINAL_DB_URL" in
  postgresql*) DB_SUMMARY="PostgreSQL（${PG_HOST}:${PG_PORT}/${PG_DB_NAME}，密码已写入环境变量文件）" ;;
  mysql*) DB_SUMMARY="MySQL（沿用已有配置）" ;;
  sqlite*) DB_SUMMARY="SQLite（内置数据库，无需外部服务）" ;;
  "") DB_SUMMARY="未配置（应用默认使用 SQLite）" ;;
  *) DB_SUMMARY="已配置（${FINAL_DB_URL%%:*}）" ;;
esac
FINAL_REDIS_URL="$(env_get REDIS_URL || true)"
if [[ -n "$FINAL_REDIS_URL" ]]; then
  CACHE_SUMMARY="Redis（${REDIS_HOST}:${REDIS_PORT}/${REDIS_DB_INDEX}，密码已写入环境变量文件）"
else
  CACHE_SUMMARY="进程内缓存（未配置 Redis）"
fi
info "数据库: $DB_SUMMARY"
info "缓存  : $CACHE_SUMMARY"
# <<< 5.1-BLOCK-END

# 环境变量文件可能包含 PostgreSQL/Redis 随机密码，收紧为仅属主可读
if [[ -f "$ENV_FILE" ]]; then
  chmod 600 "$ENV_FILE" 2>/dev/null || true
fi

chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# ---------- 6) systemd 单元 ----------
info "安装 systemd 单元"
# 通过 systemd 单元模板保留 root + ProtectSystem=no；否则自动安装 traceroute 无法写 /usr
sed -e "s|^User=.*|User=${APP_USER}|" \
    -e "s|^Group=.*|Group=${APP_USER}|" \
    -e "s|^WorkingDirectory=.*|WorkingDirectory=${APP_DIR}|" \
    -e "s|^EnvironmentFile=.*|EnvironmentFile=-${APP_DIR}/deploy/snmp-nms.env|" \
    -e "s|^ExecStart=.*|ExecStart=${APP_DIR}/.venv/bin/python run_backend.py ${PORT}|" \
    -e "s|^ReadWritePaths=.*|ReadWritePaths=${APP_DIR} /usr|" \
    -e "s|^Environment=PATH=.*|Environment=PATH=${APP_DIR}/.venv/bin:/usr/local/bin:/usr/bin:/usr/sbin:/bin:/sbin|" \
    "$APP_DIR/deploy/snmp-nms.service" > "/etc/systemd/system/${SERVICE}.service"

install -m 755 "$APP_DIR/deploy/snmp-nms-healthcheck.sh" /usr/local/bin/snmp-nms-healthcheck
install -m 644 "$APP_DIR/deploy/snmp-nms-healthcheck.service" "/etc/systemd/system/${SERVICE}-healthcheck.service"
install -m 644 "$APP_DIR/deploy/snmp-nms-healthcheck.timer" "/etc/systemd/system/${SERVICE}-healthcheck.timer"

systemctl daemon-reload
systemctl enable --now "${SERVICE}.service"
systemctl enable --now "${SERVICE}-healthcheck.timer"
info "已启用 ${SERVICE}.service 开机自启；可在系统配置 →「开机自启」页查看或切换"

# ---------- 7) 状态 ----------
sleep 3
info "服务状态:"
systemctl --no-pager --lines=5 status "${SERVICE}.service" || true

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
[[ -z "$IP" ]] && IP="<服务器IP>"
cat <<EOF

============================================================
 安装完成 ✅
 管理界面 : https://${IP}/         # 默认 HTTPS 443（自签名证书首次需信任）
 HTTP 入口 : http://${IP}/          # 仅 308 跳转到 HTTPS
 监控大屏 : https://${IP}/bigscreen
 内部端口 : 127.0.0.1:${PORT}      # 仅供本机健康检查/排障
 API 文档 : http://127.0.0.1:${PORT}/docs  # 仅本机内部端口
 数据库   : ${DB_SUMMARY}
 缓存     : ${CACHE_SUMMARY}
 连接状态 : 登录后「系统配置 → 数据库与缓存」查看 PostgreSQL / Redis 实际连通性
 默认账号 : admin
 初始密码 : ${APP_DIR}/data/initial_admin_password.txt（首次登录必须修改）
 查看密码 : sudo cat ${APP_DIR}/data/initial_admin_password.txt
 授权模式 : 首次安装默认为开源版（10 台资产、永久、免费；仅级联管理和集群不可用）

 常用命令:
   systemctl status ${SERVICE}       # 查看状态
   systemctl restart ${SERVICE}      # 重启
   journalctl -u ${SERVICE} -f       # 实时日志
   tail -f ${APP_DIR}/data/logs/backend.log
   systemctl list-timers ${SERVICE}-healthcheck.timer   # 健康检查定时器

 防意外退出:
   - 服务异常退出后 3 秒自动重启（Restart=always，无重启次数上限）
   - 健康检查定时器每 2 分钟探测 /api/health，假死自动重启
   - 后台采集/网站调度任务异常也会自动重新拉起
============================================================
EOF
