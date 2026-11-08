"""网管系统配置文件"""
import logging
import os
import secrets
import socket
from pathlib import Path

# 项目根目录（backend 的上一级）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SECURITY_LOGGER = logging.getLogger("snmp-monitor.security")
_INSECURE_SECRETS = {
    "",
    "snmp-nms-change-me-in-production",
    "please-change-this-in-production",
    "please-change-this-to-a-long-random-string",
    "change-me",
}


def _resolve_auth_secret() -> str:
    """优先使用环境变量；否则生成并持久化随机密钥。

    旧版本默认密钥是公开字符串，不能再用于签名。已有虚拟化平台凭据
    使用旧密钥加密时，由 virtualization_crypto 做兼容解密。
    """
    env = (os.getenv("AUTH_SECRET") or "").strip()
    if env and env not in _INSECURE_SECRETS:
        return env
    path = PROJECT_ROOT / "data" / ".auth_secret"
    try:
        if path.is_file():
            value = path.read_text(encoding="utf-8").strip()
            if len(value) >= 32:
                return value
        path.parent.mkdir(parents=True, exist_ok=True)
        value = secrets.token_urlsafe(48)
        path.write_text(value, encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        _SECURITY_LOGGER.warning(
            "未配置安全的 AUTH_SECRET，已生成随机密钥并保存到 %s；"
            "多实例部署请显式设置相同的 AUTH_SECRET",
            path,
        )
        return value
    except OSError as exc:
        _SECURITY_LOGGER.error("无法持久化令牌密钥，将使用进程级随机密钥: %s", exc)
        return secrets.token_urlsafe(48)


LEGACY_AUTH_SECRETS = [
    "snmp-nms-change-me-in-production",
    "please-change-this-in-production",
    "please-change-this-to-a-long-random-string",
    "snmp-monitor",
]


class Config:
    # 数据库配置
    # SQLite:      sqlite:///snmp_monitor.db
    # MySQL:       mysql+pymysql://user:pass@host:3306/snmp_nms?charset=utf8mb4
    # PostgreSQL:  postgresql+psycopg2://user:pass@host:5432/snmp_nms
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///snmp_monitor.db")
    # 非 SQLite 数据库连接池（设备量大时可调大）
    DB_POOL_SIZE = int(os.getenv("DB_POOL_SIZE", "10"))
    DB_MAX_OVERFLOW = int(os.getenv("DB_MAX_OVERFLOW", "20"))
    DB_POOL_RECYCLE = int(os.getenv("DB_POOL_RECYCLE", "1800"))

    # ---- 缓存（Redis 优先，未配置时自动回退内存缓存）----
    CACHE_ENABLED = os.getenv("CACHE_ENABLED", "1") not in ("0", "false", "False", "")
    REDIS_URL = os.getenv("REDIS_URL", "")
    CACHE_TTL_TOPOLOGY = int(os.getenv("CACHE_TTL_TOPOLOGY", "5"))
    CACHE_TTL_DASHBOARD = int(os.getenv("CACHE_TTL_DASHBOARD", "3"))

    # ---- WebRTC（局域网通话）----
    # 局域网内默认可直接使用 host candidate，不需要公网 STUN。
    # 跨 VLAN/防火墙时配置 TURN，例如 turn:192.168.1.10:3478。
    WEBRTC_STUN_URLS = os.getenv("WEBRTC_STUN_URLS", "")
    WEBRTC_TURN_URLS = os.getenv("WEBRTC_TURN_URLS", "")
    WEBRTC_TURN_USERNAME = os.getenv("WEBRTC_TURN_USERNAME", "")
    WEBRTC_TURN_CREDENTIAL = os.getenv("WEBRTC_TURN_CREDENTIAL", "")
    WEBRTC_FORCE_RELAY = os.getenv("WEBRTC_FORCE_RELAY", "0").lower() in ("1", "true", "yes", "on")

    # ---- 多实例部署 ----
    # 多实例时只允许一个实例跑采集/网站调度/备份/清理等后台任务
    RUN_BACKGROUND_TASKS = os.getenv(
        "RUN_BACKGROUND_TASKS", "1"
    ).strip().lower() not in ("0", "false", "no", "off", "")
    INSTANCE_ID = os.getenv("INSTANCE_ID", "") or socket.gethostname()

    # Prometheus /metrics：设置 METRICS_TOKEN 后需带 Bearer/查询参数
    METRICS_TOKEN = os.getenv("METRICS_TOKEN", "")

    # 文件上传目录（设备自定义图标等），Docker 中建议指向数据卷
    UPLOAD_DIR = os.getenv("UPLOAD_DIR", str(PROJECT_ROOT / "data" / "uploads"))
    MAX_ICON_SIZE_MB = int(os.getenv("MAX_ICON_SIZE_MB", "2"))

    # 商业授权：未激活时使用试用资产上限；授权文件默认放在 data 目录
    LICENSE_FILE = os.getenv("LICENSE_FILE", str(PROJECT_ROOT / "data" / "license.key"))
    # 开源版资产额度是产品策略上限，环境变量只能调低，不能放大绕过授权。
    LICENSE_OPENSOURCE_MAX_ASSETS = min(50, max(1, int(os.getenv("LICENSE_OPENSOURCE_MAX_ASSETS", "50"))))
    LICENSE_TRIAL_MAX_ASSETS = min(50, max(1, int(os.getenv("LICENSE_TRIAL_MAX_ASSETS", "50"))))
    LICENSE_TRIAL_DAYS = min(30, max(1, int(os.getenv("LICENSE_TRIAL_DAYS", "30"))))
    LICENSE_TRIAL_START_FILE = os.getenv(
        "LICENSE_TRIAL_START_FILE", str(PROJECT_ROOT / "data" / "trial_started_at")
    )

    # 日志目录与级别（同时输出到控制台与轮转文件，便于排查意外退出）
    LOG_DIR = os.getenv("LOG_DIR", str(PROJECT_ROOT / "data" / "logs"))
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    LOG_MAX_MB = int(os.getenv("LOG_MAX_MB", "10"))
    LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    
    # SNMP配置
    SNMP_COMMUNITY_V2 = os.getenv("SNMP_COMMUNITY", "public")
    SNMP_TIMEOUT = int(os.getenv("SNMP_TIMEOUT", "3"))
    SNMP_RETRIES = int(os.getenv("SNMP_RETRIES", "1"))
    
    # 采集间隔（秒）
    COLLECTION_INTERVAL = int(os.getenv("COLLECTION_INTERVAL", "60"))
    # 严重/紧急告警人工确认后，间隔多少分钟再次告警
    SEVERE_ALERT_REALERT_MINUTES = int(os.getenv("SEVERE_ALERT_REALERT_MINUTES", "30"))
    
    # API配置
    API_HOST = os.getenv("API_HOST", "0.0.0.0")
    API_PORT = int(os.getenv("API_PORT", "8000"))
    
    # 前端代理
    FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
    
    # 告警阈值
    CPU_THRESHOLD = 80
    MEMORY_THRESHOLD = 85
    TEMPERATURE_THRESHOLD = 80
    TEMPERATURE_CRITICAL_THRESHOLD = int(os.getenv("TEMPERATURE_CRITICAL_THRESHOLD", "90"))
    DISK_THRESHOLD = int(os.getenv("DISK_THRESHOLD", "90"))

    # ---- 认证与权限 ----
    # 生产环境优先通过环境变量 AUTH_SECRET 设置固定密钥；
    # 未设置或仍是公开默认值时，自动生成并持久化到 data/.auth_secret。
    AUTH_SECRET = _resolve_auth_secret()
    AUTH_TOKEN_HOURS = int(os.getenv("AUTH_TOKEN_HOURS", "12"))
    # 首次启动自动创建的管理员账号；密码为空时随机生成并写入
    # data/initial_admin_password.txt，首次登录必须修改。
    AUTH_DEFAULT_ADMIN = os.getenv("AUTH_DEFAULT_ADMIN", "admin")
    AUTH_DEFAULT_PASSWORD = os.getenv("AUTH_DEFAULT_PASSWORD", "")

    # CORS：默认不开放跨域；如前后端分域部署，用逗号分隔显式配置。
    CORS_ORIGINS = [
        item.strip() for item in (os.getenv("CORS_ORIGINS", "") or "").split(",")
        if item.strip()
    ]
