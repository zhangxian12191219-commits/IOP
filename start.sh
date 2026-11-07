#!/usr/bin/env bash
# ============================================================================
# 智能运维服务平台 - Linux 启动脚本（前台 / 后台守护）
#
# 前台（适合 systemd / Docker / 容器编排）:
#   ./start.sh                    启动后端（8000），已构建前端时由后端托管页面
#   ./start.sh --build            先构建前端再启动
#   ./start.sh --dev              开发模式：后端 8000 + 前端 vite 5173
#   ./start.sh --seed             先载入演示数据再启动
#
# 后台守护（无 systemd 时使用，后端崩溃自动重启）:
#   ./start.sh start [--build] [--seed]   后台启动并守护
#   ./start.sh stop | restart | status | logs
#
# 生产环境更推荐 systemd：sudo bash deploy/install-systemd.sh
# ============================================================================
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"

PYTHON="${PYTHON_BIN:-python3}"
PORT="${API_PORT:-8000}"
PID_DIR="$ROOT/data/run"
LOG_DIR="$ROOT/data/logs"
CONSOLE_LOG="$LOG_DIR/console.log"
DB_LOG="$LOG_DIR/backend.log"
SUPERVISOR_PID="$PID_DIR/supervisor.pid"
BACKEND_PID="$PID_DIR/backend.pid"
PYTHON="${PYTHON_BIN:-python3}"

mkdir -p "$PID_DIR" "$LOG_DIR"

# ---------------- 内部：守护循环 ----------------
if [ "${1:-}" = "__supervise" ]; then
  shift || true
  SUP_PORT="${1:-$PORT}"
  echo $$ > "$SUPERVISOR_PID"
  CHILD=""
  cleanup() {
    echo "[$(date '+%F %T')] 收到停止信号，正在停止后端..." >> "$CONSOLE_LOG"
    if [ -n "$CHILD" ] && kill -0 "$CHILD" 2>/dev/null; then
      kill "$CHILD" 2>/dev/null || true
      wait "$CHILD" 2>/dev/null || true
    fi
    rm -f "$SUPERVISOR_PID" "$BACKEND_PID"
    exit 0
  }
  trap cleanup TERM INT
  echo "[$(date '+%F %T')] 守护进程启动，端口 $SUP_PORT" >> "$CONSOLE_LOG"

  while true; do
    "$PYTHON" run_backend.py "$SUP_PORT" >> "$CONSOLE_LOG" 2>&1 &
    CHILD=$!
    echo "$CHILD" > "$BACKEND_PID"
    if wait "$CHILD"; then
      CODE=0
    else
      CODE=$?
    fi
    echo "[$(date '+%F %T')] 后端进程退出（code=$CODE），5 秒后自动重启" >> "$CONSOLE_LOG"
    sleep 5
  done
fi

# ---------------- 依赖准备 ----------------
prepare() {
  echo "==> Python: $($PYTHON --version 2>&1)"
  if ! $PYTHON -c "import fastapi, sqlalchemy, pysnmp, aiohttp" >/dev/null 2>&1; then
    echo "==> 安装后端依赖..."
    if ! $PYTHON -m pip install -r backend/requirements.txt; then
      echo "!! 全局安装失败，尝试安装到 ./vendor（启动脚本会自动挂载）"
      $PYTHON -m pip install --target "$ROOT/vendor" -r backend/requirements.txt
    fi
  fi
}

# ---------------- 子命令 ----------------
cmd_status() {
  local ok=0
  if [ -f "$SUPERVISOR_PID" ] && kill -0 "$(cat "$SUPERVISOR_PID")" 2>/dev/null; then
    echo "守护进程: 运行中 (pid $(cat "$SUPERVISOR_PID"))"
  else
    echo "守护进程: 未运行"
    ok=1
  fi
  if [ -f "$BACKEND_PID" ] && kill -0 "$(cat "$BACKEND_PID")" 2>/dev/null; then
    echo "后端进程: 运行中 (pid $(cat "$BACKEND_PID"))"
  else
    echo "后端进程: 未运行"
    ok=1
  fi
  if command -v curl >/dev/null 2>&1; then
    if curl -fsS --max-time 5 "http://127.0.0.1:$PORT/api/health" 2>/dev/null; then
      echo ""
      echo "健康检查: 正常"
    else
      echo "健康检查: 失败（http://127.0.0.1:$PORT/api/health）"
      ok=1
    fi
  fi
  return $ok
}

cmd_start() {
  prepare
  if [ -f "$SUPERVISOR_PID" ] && kill -0 "$(cat "$SUPERVISOR_PID")" 2>/dev/null; then
    echo "服务已在运行（pid $(cat "$SUPERVISOR_PID")），如需重启请执行: ./start.sh restart"
    return 0
  fi

  # 前端构建
  if [ "$BUILD_FRONTEND" = "1" ]; then
    if command -v npm >/dev/null 2>&1; then
      echo "==> 构建前端..."
      ( cd frontend && { [ -d node_modules ] || npm install --no-audit --no-fund; } && npm run build )
    else
      echo "!! 未安装 npm，跳过前端构建"
    fi
  fi

  if [ "$SEED" = "1" ]; then
    echo "==> 载入演示数据..."
    $PYTHON seed_demo.py || true
  fi

  echo "==> 后台启动（守护模式，崩溃自动重启）"
  nohup bash "$0" __supervise "$PORT" >> "$CONSOLE_LOG" 2>&1 &
  sleep 3
  cmd_status || true
  echo ""
  echo "    管理界面: http://<服务器IP>:$PORT"
  echo "    监控大屏: http://<服务器IP>:$PORT/bigscreen"
  echo "    API 文档: http://<服务器IP>:$PORT/docs"
  echo "    控制台日志: $CONSOLE_LOG"
  echo "    应用日志  : $DB_LOG"
}

cmd_stop() {
  local stopped=0
  if [ -f "$SUPERVISOR_PID" ]; then
    local spid
    spid="$(cat "$SUPERVISOR_PID")"
    if kill -0 "$spid" 2>/dev/null; then
      echo "==> 停止守护进程 (pid $spid)"
      kill -TERM "$spid" 2>/dev/null || true
      stopped=1
    fi
  fi
  # 兜底：残留后端进程
  if [ -f "$BACKEND_PID" ]; then
    local bpid
    bpid="$(cat "$BACKEND_PID")"
    if kill -0 "$bpid" 2>/dev/null; then
      kill -TERM "$bpid" 2>/dev/null || true
      stopped=1
    fi
  fi
  sleep 2
  # 仍存活则强制结束
  for f in "$SUPERVISOR_PID" "$BACKEND_PID"; do
    if [ -f "$f" ] && kill -0 "$(cat "$f")" 2>/dev/null; then
      kill -KILL "$(cat "$f")" 2>/dev/null || true
    fi
  done
  rm -f "$SUPERVISOR_PID" "$BACKEND_PID"
  [ "$stopped" = "1" ] && echo "已停止" || echo "服务未在运行"
}

cmd_logs() {
  echo "==> 控制台日志: $CONSOLE_LOG （Ctrl+C 退出）"
  touch "$CONSOLE_LOG"
  if [ -f "$DB_LOG" ]; then
    tail -n 50 -f "$CONSOLE_LOG" "$DB_LOG"
  else
    tail -n 50 -f "$CONSOLE_LOG"
  fi
}

# ---------------- 参数解析 ----------------
START_ARGS=("$@")
COMMAND="foreground"
BUILD_FRONTEND=0
SEED=0
MODE="prod"

if [ $# -gt 0 ]; then
  case "$1" in
    start|stop|restart|status|logs)
      COMMAND="$1"; shift || true ;;
  esac
fi

for arg in "$@"; do
  case "$arg" in
    --build) BUILD_FRONTEND=1; MODE="build" ;;
    --dev)   MODE="dev" ;;
    --seed)  SEED=1 ;;
    -h|--help) sed -n '2,18p' "$0"; exit 0 ;;
    *) echo "未知参数: $arg"; exit 1 ;;
  esac
done

case "$COMMAND" in
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  restart) cmd_stop; START_ARGS=("$@"); cmd_start ;;
  status)  cmd_status ;;
  logs)    cmd_logs ;;
  foreground)
    prepare
    if [ "$MODE" = "dev" ]; then
      if [ ! -d frontend/node_modules ]; then
        echo "==> 安装前端依赖..."
        (cd frontend && npm install)
      fi
      echo "==> 开发模式：后端 :$PORT，前端 :5173"
      $PYTHON run_backend.py "$PORT" &
      BACKEND_PID_DEV=$!
      trap 'kill $BACKEND_PID_DEV 2>/dev/null || true' EXIT
      (cd frontend && VITE_API_TARGET="http://localhost:$PORT" npm run dev)
      exit 0
    fi

    if [ "$BUILD_FRONTEND" = "1" ]; then
      if [ ! -d frontend/node_modules ]; then
        echo "==> 安装前端依赖..."
        (cd frontend && npm install)
      fi
      echo "==> 构建前端..."
      (cd frontend && npm run build)
    fi

    if [ "$SEED" = "1" ]; then
      echo "==> 载入演示数据..."
      $PYTHON seed_demo.py
    fi

    echo "==> 前台启动（交给 systemd/Docker 守护）: http://0.0.0.0:$PORT"
    echo "    管理界面: http://<服务器IP>:$PORT"
    echo "    监控大屏: http://<服务器IP>:$PORT/bigscreen"
    echo "    API 文档: http://<服务器IP>:$PORT/docs"
    exec $PYTHON run_backend.py "$PORT"
    ;;
esac
