# ---------- 阶段 1：构建前端 ----------
FROM node:20-alpine AS webbuild

WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json* ./
RUN if [ -f package-lock.json ]; then npm ci --no-audit --no-fund; \
    else npm install --no-audit --no-fund; fi
COPY frontend/ ./
# 可选：CI 传入递增构建号；不传时使用 frontend/version-state.json 自动 +1
ARG NMS_BUILD_NUMBER=""
ENV NMS_BUILD_NUMBER=${NMS_BUILD_NUMBER}
RUN npm run build


# ---------- 阶段 2：运行时 ----------
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    TZ=Asia/Shanghai

WORKDIR /app

# iputils-ping: ICMP 探测；curl: 健康检查；tzdata: 时区
RUN apt-get update \
    && apt-get install -y --no-install-recommends iputils-ping curl tzdata \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend ./backend
COPY run_backend.py seed_demo.py ./
COPY tools ./tools
COPY mibs ./mibs
COPY --from=webbuild /build/frontend/dist ./frontend/dist
# 版本信息由前端构建阶段生成，必须带入运行镜像，否则会沿用源码中的旧版本
COPY --from=webbuild /build/frontend/dist/version.json ./backend/version.json

# 数据库、上传文件、日志都放在 /data 卷里，便于持久化
RUN mkdir -p /data/uploads /data/logs
ENV DATABASE_URL=sqlite:////data/snmp_monitor.db \
    UPLOAD_DIR=/data/uploads \
    LOG_DIR=/data/logs \
    LICENSE_FILE=/data/license.key \
    API_HOST=0.0.0.0 \
    API_PORT=8000

EXPOSE 80 443 8000

# 健康检查：容器启动 30 秒后每 30 秒探测一次
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

# 优雅停机：docker stop 发送 SIGTERM，uvicorn 会等待在途请求
STOPSIGNAL SIGTERM

CMD ["python", "run_backend.py", "8000"]
