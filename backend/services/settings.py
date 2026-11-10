"""系统设置服务：默认值、读取、校验与保存"""
import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from sqlalchemy.orm import Session

from ..config import Config
from ..models.settings import SystemSetting
from .internet_time import internet_year

logger = logging.getLogger(__name__)

DEFAULT_SYSTEM_NAME = "智能运维服务平台"
SECURITY_BASELINE_KEY = "security_baseline_v2"
WEB_ACCESS_BASELINE_KEY = "web_access_baseline_v1"
WEB_HTTPS_BASELINE_KEY = "web_https_baseline_v1"
# 旧版本默认名称：只在用户没有改过名称时迁移，避免覆盖自定义名称
# 历史旧名称以转义形式保留，仅用于兼容已有数据，不再作为产品展示名称
LEGACY_SYSTEM_NAMES = {"\u0053\u004e\u004d\u0050 \u7f51\u7ba1\u76d1\u63a7\u7cfb\u7edf", "\u7f51\u7ba1\u76d1\u63a7\u7cfb\u7edf", "智能化运维服务平台"}
COPYRIGHT_OPENSOURCE_NAME = "智能运维服务平台 · 开源版"
COPYRIGHT_COMMERCIAL_NAME = "智能运维服务平台"
AUTO_COPYRIGHT_NAMES = {
    "智能运维服务平台",
    "智能运维服务平台 · 商业版",
    "大连伊莱科技有限公司",
    "大连伊莱科技有限公司 · 商业版",
    COPYRIGHT_OPENSOURCE_NAME,
    COPYRIGHT_COMMERCIAL_NAME,
}
DEFAULT_COPYRIGHT_NAME = COPYRIGHT_OPENSOURCE_NAME
DEFAULT_COPYRIGHT_TEXT = f"© {datetime.now().year} {DEFAULT_COPYRIGHT_NAME} 版权所有"
LEGACY_COPYRIGHT_TEXTS = {
    "© 2026 智能运维服务平台 版权所有",
    "© 2026 大连伊莱科技有限公司 版权所有",
    "大连伊莱科技有限公司 · 张羡",
    "智能运维服务平台",
    "内部测试公司 版权所有",
}


def edition_copyright_name() -> str:
    """按当前授权版本返回版权名称；默认安装/未授权为开源版。"""
    try:
        from . import license_manager

        status = license_manager.get_license_status()
        edition = str(status.get("edition") or "").strip().lower()
        if edition == "commercial":
            return COPYRIGHT_COMMERCIAL_NAME
    except Exception:
        pass
    return COPYRIGHT_OPENSOURCE_NAME


def apply_license_copyright(db: Session, force: bool = False) -> Dict[str, str]:
    """把版权名称同步到当前授权版本。

    默认只替换系统自动生成的版权名称，避免覆盖有权限用户自定义的品牌；
    force=True 时用于授权激活等明确需要切换版本的场景。
    """
    name_row = db.query(SystemSetting).filter(SystemSetting.key == "copyright_name").first()
    text_row = db.query(SystemSetting).filter(SystemSetting.key == "copyright_text").first()
    current = str(name_row.value or "").strip() if name_row else ""
    if not force and current and current not in AUTO_COPYRIGHT_NAMES:
        return {"copyright_name": current, "copyright_text": str(text_row.value or "") if text_row else ""}
    target = edition_copyright_name()
    timezone_row = db.query(SystemSetting).filter(SystemSetting.key == "timezone").first()
    timezone_name = str(timezone_row.value or "Asia/Shanghai") if timezone_row else "Asia/Shanghai"
    text = format_copyright(target, timezone_name=timezone_name)
    if name_row is None:
        db.add(SystemSetting(key="copyright_name", value=target))
    elif str(name_row.value or "").strip() != target:
        name_row.value = target
    if text_row is None:
        db.add(SystemSetting(key="copyright_text", value=text))
    elif str(text_row.value or "").strip() != text:
        text_row.value = text
    db.flush()
    return {"copyright_name": target, "copyright_text": text}


def format_copyright(name: str, year: Optional[int] = None, timezone_name: str = "Asia/Shanghai") -> str:
    """生成标准版权文字：© 年份 自定义名称 版权所有。"""
    clean_name = str(name or "").strip() or DEFAULT_COPYRIGHT_NAME
    use_year = int(year) if year is not None else internet_year(timezone_name)
    return f"© {use_year} {clean_name} 版权所有"


def extract_copyright_name(text: Any) -> str:
    """从旧版权文字中提取自定义名称，兼容标准格式和纯名称。"""
    raw = str(text or "").strip()
    if not raw:
        return ""
    match = re.match(r"^©\s*\d{4}\s*(.*?)\s*版权所有\s*$", raw)
    if match:
        return match.group(1).strip()
    if raw.endswith("版权所有"):
        return raw[:-4].strip(" ·-") or ""
    return raw

# 默认配置：key -> (默认值, 类型, 说明)
DEFAULTS: Dict[str, Tuple[Any, str, str]] = {
    "system_name": (DEFAULT_SYSTEM_NAME, "str", "系统名称（登录页/侧边栏/浏览器标题）"),
    "login_subtitle": ("设备监测 · 机房与网站监测 · 即时通信 · 设备备份 · 虚拟化纳管 · 智能运维", "str", "登录页副标题（可在系统配置中自定义）"),
    "system_logo": ("", "str", "系统图标（登录页/侧边栏/浏览器标签）"),
    "copyright_enabled": (True, "bool", "登录页显示自定义版权信息"),
    "copyright_name": (DEFAULT_COPYRIGHT_NAME, "str", "版权自定义名称"),
    "copyright_text": (DEFAULT_COPYRIGHT_TEXT, "str", "登录页版权文字（由名称和年份自动生成）"),
    "copyright_color": ("#94a3b8", "str", "登录页版权文字颜色（#RRGGBB）"),
    "language": ("zh-CN", "str", "界面语言：中文/English/日本語/한국어/Deutsch/Français/Español/Português/Русский/العربية/हिन्दी"),
    "timezone": ("Asia/Shanghai", "str", "显示时区，如 Asia/Shanghai、UTC"),
    "refresh_interval": (30, "int", "前端页面自动刷新间隔（秒，5~600）"),
    "auto_logout_minutes": (30, "int", "无操作自动注销时间（分钟，0 表示不注销）"),
    "auto_login": (False, "bool", "自动登录：关闭时关闭浏览器即退出"),
    "captcha_enabled": (True, "bool", "登录验证码开关"),
    # ---- 登录安全 ----
    "login_lock_enabled": (True, "bool", "登录失败锁定开关"),
    "login_max_attempts": (5, "int", "连续登录失败达到该次数后锁定账号（3~20）"),
    "login_lock_minutes": (15, "int", "账号锁定时长（分钟，1~1440）"),
    "ip_whitelist_enabled": (False, "bool", "API IP 白名单开关"),
    "ip_whitelist": ("", "str", "允许访问的 IP/CIDR，逗号或换行分隔"),
    "trust_proxy": (False, "bool", "信任 X-Forwarded-For（反向代理后开启）"),
    "audit_retention_days": (180, "int", "审计日志保留天数（0 表示永久保留）"),
    # ---- 密码复杂度（对所有用户生效） ----
    "password_min_length": (8, "int", "密码最小长度（4~32 位）"),
    "password_require_uppercase": (True, "bool", "密码必须包含大写字母"),
    "password_require_lowercase": (True, "bool", "密码必须包含小写字母"),
    "password_require_digit": (True, "bool", "密码必须包含数字"),
    "password_require_special": (True, "bool", "密码必须包含特殊字符"),
    "password_expiry_days": (90, "int", "密码有效期（天，0 表示永久）"),
    "first_login_password_change": (True, "bool", "首次登录必须修改密码"),
    # ---- 二次身份验证策略（管理员配置，用户在个人账户绑定） ----
    "totp_policy": ("off", "str", "二次验证策略：off 关闭 / all 全部用户 / selected 指定用户"),
    "totp_required_user_ids": ("", "str", "指定需要二次验证的用户 ID，逗号分隔"),
    # ---- Web 登录网关（HTTP/HTTPS 协议与端口） ----
    "web_http_enabled": (False, "bool", "启用 HTTP 登录（HTTPS 模式下仅用于 80→443 跳转）"),
    "web_http_port": (80, "int", "HTTP 跳转端口（默认 80）"),
    "web_https_enabled": (True, "bool", "启用 HTTPS 登录"),
    "web_https_port": (443, "int", "HTTPS 登录端口（默认 443）"),
    "web_protocol": ("https", "str", "Web 登录协议：http 或 https（默认 https）"),
    "web_login_port": (443, "int", "Web 登录端口（默认 HTTPS 443）"),
    "web_https_redirect_http": (True, "bool", "启用 HTTPS 后 HTTP 自动跳转到 HTTPS"),
    "web_ssl_certificate_id": (0, "int", "HTTPS 使用证书（0=自动使用最新免费证书）"),
    # ---- 数据库自动备份 ----
    "backup_enabled": (True, "bool", "数据库自动备份开关"),
    "backup_interval_hours": (24, "int", "自动备份间隔（小时，1~168）"),
    "backup_retention_count": (7, "int", "保留最近几份备份（1~90）"),
    # ---- 设备巡检报告保留 ----
    "inspection_report_retention_days": (15, "int", "巡检报告保留天数（默认 15 天，0 表示永久保留）"),
    "inspection_office_enabled": (False, "bool", "启用巡检报告在线 Office 编辑"),
    "inspection_office_document_server_url": ("", "str", "ONLYOFFICE Document Server 地址"),
    "inspection_office_public_base_url": ("", "str", "产品对外访问地址（Document Server 可访问）"),
    "inspection_office_jwt_secret": ("", "str", "ONLYOFFICE JWT 密钥"),
    # ---- 总部/分支级联 ----
    "cascade_enabled": (False, "bool", "启用级联隧道"),
    "cascade_role": ("standalone", "str", "级联角色：standalone/hq/branch"),
    "cascade_node_name": ("", "str", "分支节点名称"),
    "cascade_hq_url": ("", "str", "总部地址，例如 https://hq.example.com"),
    "cascade_token_enc": ("", "str", "分支接入令牌（加密存储）"),
    "cascade_sync_interval": (60, "int", "分支数据同步间隔（秒，30~3600）"),
    "cascade_verify_tls": (True, "bool", "校验总部 TLS 证书"),
    "cascade_tunnel_port": (9527, "int", "级联隧道专用端口（1~65535）"),
    # ---- AI 运维 ----
    "ai_enabled": (False, "bool", "启用AI智能运维"),
    "ai_base_url": ("https://api.openai.com/v1", "str", "OpenAI兼容模型地址"),
    "ai_model": ("gpt-4o-mini", "str", "模型名称"),
    "ai_api_key_enc": ("", "str", "模型 API Key（加密存储）"),
    "ai_temperature": ("0.2", "str", "模型温度"),
    "ai_max_tokens": (1200, "int", "模型最大输出 Token"),
    "ai_wake_word": ("你好玄武", "str", "AI运维大屏语音唤醒词"),
    "ai_name": ("玄武", "str", "AI 助手名称"),
    "ai_voice_gender": ("male", "str", "AI 默认音色性别：male / female"),
    "ai_voice_name": ("", "str", "AI 指定浏览器语音名称，留空按性别选择"),
    # ---- 上级平台告警汇聚 ----
    "upstream_ingest_token": ("", "str", "上级平台接收入口令牌"),
    # ---- 系统在线更新 ----
    "update_online_url": ("", "str", "在线更新服务地址（支持 latest.json、目录 URL 或 zip 直链）"),
    # ---- 网络设备配置备份 ----
    "config_backup_enabled": (False, "bool", "设备配置自动备份开关"),
    "config_backup_interval_hours": (24, "int", "设备配置自动备份间隔（小时，1~168）"),
    "config_backup_retention_count": (30, "int", "每台设备保留配置备份份数（1~200）"),
    "config_backup_concurrency": (3, "int", "配置备份并发数（1~10）"),
    "config_backup_timeout": (45, "int", "SSH 配置读取超时（秒，10~180）"),
    "config_backup_storage_enabled": (False, "bool", "启用配置备份外部存储"),
    "config_backup_storage_type": ("webdav", "str", "外部存储类型：webdav/sftp"),
    "config_backup_webdav_url": ("", "str", "WebDAV 地址"),
    "config_backup_webdav_username": ("", "str", "WebDAV 用户名"),
    "config_backup_webdav_password": ("", "str", "WebDAV 密码"),
    "config_backup_webdav_path": ("/snmp-monitor/config-backups", "str", "WebDAV 备份目录"),
    "config_backup_webdav_verify_tls": (True, "bool", "WebDAV 校验 TLS 证书"),
    "config_backup_sftp_host": ("", "str", "SFTP 主机"),
    "config_backup_sftp_port": (22, "int", "SFTP 端口"),
    "config_backup_sftp_username": ("", "str", "SFTP 用户名"),
    "config_backup_sftp_password": ("", "str", "SFTP 密码"),
    "config_backup_sftp_path": ("/snmp-monitor/config-backups", "str", "SFTP 备份目录"),
    "config_backup_sftp_timeout": (15, "int", "SFTP 超时秒"),
    # ---- 告警声音 ----
    "alert_sound_file": ("", "str", "旧版自定义告警声音文件名（兼容，作为紧急级别）"),
    "alert_sound_file_info": ("", "str", "提示级别自定义告警声音文件名"),
    "alert_sound_file_warning": ("", "str", "警告级别自定义告警声音文件名"),
    "alert_sound_file_critical": ("", "str", "严重级别自定义告警声音文件名"),
    "alert_sound_file_emergency": ("", "str", "紧急级别自定义告警声音文件名"),
    "alert_sound_interval": (60, "int", "未处理告警声音提醒间隔（秒，10~3600）"),
    # ---- 告警详细语音播报 ----
    "alert_broadcast_enabled": (True, "bool", "启用告警详细语音播报"),
    "alert_broadcast_counts": (True, "bool", "播报各级告警数量"),
    "alert_broadcast_details": (True, "bool", "播报具体告警内容"),
    "alert_broadcast_levels": ("info,warning,critical,emergency", "str", "详细播报包含的级别"),
    "alert_broadcast_max_items": (3, "int", "每级最多播报内容条数（1~20）"),
    "alert_realert_minutes": (30, "int", "活动告警人工确认后的再提醒间隔（分钟，1~1440）"),
    "collection_interval": (Config.COLLECTION_INTERVAL, "int", "后台 SNMP 采集间隔（秒，10~3600）"),
    # ---- 虚拟机告警规则 ----
    "vm_alert_cpu_enabled": (True, "bool", "虚拟机 CPU 使用率告警开关"),
    "vm_alert_cpu_threshold": (80, "int", "虚拟机 CPU 使用率告警阈值（%）"),
    "vm_alert_memory_enabled": (True, "bool", "虚拟机内存使用率告警开关"),
    "vm_alert_memory_threshold": (85, "int", "虚拟机内存使用率告警阈值（%）"),
    "vm_alert_disk_enabled": (True, "bool", "虚拟机磁盘使用率告警开关"),
    "vm_alert_disk_threshold": (85, "int", "虚拟机磁盘使用率告警阈值（%）"),
    "vm_alert_shutdown_enabled": (True, "bool", "虚拟机已关机告警开关"),
    # ---- 日志转发 ----
    "log_forward_enabled": (False, "bool", "日志转发开关"),
    "log_forward_type": ("syslog", "str", "转发目标：syslog / http / file"),
    "log_forward_min_level": ("INFO", "str", "转发最低日志级别：DEBUG/INFO/WARNING/ERROR"),
    "log_forward_host": ("", "str", "syslog 服务器地址"),
    "log_forward_port": (514, "int", "syslog 端口（1~65535）"),
    "log_forward_protocol": ("udp", "str", "syslog 协议：udp / tcp"),
    "log_forward_format": ("rfc5424", "str", "syslog 格式：rfc5424 / rfc3164"),
    "log_forward_facility": ("local0", "str", "syslog facility（local0~local7 等）"),
    "log_forward_app_name": ("snmp-nms", "str", "syslog 应用名"),
    "log_forward_http_url": ("", "str", "HTTP Webhook 接收地址"),
    "log_forward_http_headers": ("", "str", "HTTP 请求头（JSON 或每行 Key: Value）"),
    "log_forward_file_path": ("", "str", "文件转发路径（追加写）"),
    # ---- 外部数据库对接（仅超管可见） ----
    "integration_enabled": (False, "bool", "外部数据库对接开关"),
    "integration_name": ("", "str", "对接名称（如资产库、CMDB 数据库）"),
    "integration_db_type": ("mysql", "str", "数据库类型：mysql / postgresql / sqlite"),
    "integration_host": ("", "str", "数据库主机（MySQL/PostgreSQL）"),
    "integration_port": (3306, "int", "数据库端口（MySQL 3306 / PostgreSQL 5432）"),
    "integration_database": ("", "str", "数据库名称（MySQL/PostgreSQL）"),
    "integration_username": ("", "str", "数据库用户名（MySQL/PostgreSQL）"),
    "integration_password": ("", "str", "数据库密码（仅超级管理员可见）"),
    "integration_sqlite_path": ("", "str", "SQLite 数据库文件路径"),
    "integration_charset": ("utf8mb4", "str", "MySQL 字符集（默认 utf8mb4）"),
    "integration_timeout": (10, "int", "数据库连接超时（秒，1~60）"),
    "integration_sync_interval": (60, "int", "对接同步间隔（分钟，1~1440）"),
    # ---- Redis/缓存（仅超管可见） ----
    "redis_enabled": (Config.CACHE_ENABLED, "bool", "Redis 缓存开关；关闭后使用进程内缓存"),
    "redis_url": (Config.REDIS_URL, "str", "Redis 连接地址，如 redis://:密码@主机:6379/0"),
    "cache_ttl_topology": (Config.CACHE_TTL_TOPOLOGY, "int", "拓扑缓存 TTL（秒，1~300）"),
    "cache_ttl_dashboard": (Config.CACHE_TTL_DASHBOARD, "int", "总览缓存 TTL（秒，1~60）"),
    # ---- 集群与负载均衡（仅超管可见） ----
    "cluster_enabled": (False, "bool", "启用多节点集群"),
    "cluster_name": ("", "str", "集群名称"),
    "cluster_heartbeat_interval": (30, "int", "节点心跳间隔（秒，10~300）"),
    "lb_enabled": (False, "bool", "启用负载均衡配置"),
    "lb_strategy": ("round_robin", "str", "负载均衡策略：round_robin / least_conn / ip_hash"),
    "lb_public_url": ("", "str", "负载均衡对外访问地址"),
    "lb_sticky": (False, "bool", "负载均衡会话保持"),
}

# 前端可直接读取的公开配置（登录页 / 外壳）
PUBLIC_KEYS = (
    "system_name",
    "login_subtitle",
    "system_logo",
    "copyright_enabled",
    "copyright_name",
    "copyright_text",
    "copyright_color",
    "language",
    "timezone",
    "captcha_enabled",
    "auto_login",
    "refresh_interval",
    "auto_logout_minutes",
    "alert_sound_interval",
    "alert_broadcast_enabled",
    "alert_broadcast_counts",
    "alert_broadcast_details",
    "alert_broadcast_levels",
    "alert_broadcast_max_items",
    "password_min_length",
    "password_require_uppercase",
    "password_require_lowercase",
    "password_require_digit",
    "password_require_special",
)

LANGUAGES = (
    "zh-CN", "zh-TW", "en-US", "ja-JP", "ko-KR", "de-DE",
    "fr-FR", "es-ES", "pt-BR", "ru-RU", "ar-SA", "hi-IN",
)

# 常用时区（前端下拉也可用，这里仅做合法性校验白名单）
TIMEZONES = (
    "Asia/Shanghai", "Asia/Hong_Kong", "Asia/Taipei", "Asia/Tokyo",
    "Asia/Seoul", "Asia/Singapore", "Asia/Bangkok", "Asia/Kolkata",
    "Asia/Dubai", "Europe/London", "Europe/Paris", "Europe/Berlin",
    "Europe/Moscow", "America/New_York", "America/Chicago",
    "America/Denver", "America/Los_Angeles", "America/Sao_Paulo",
    "Australia/Sydney", "UTC",
)

INT_RANGES = {
    "refresh_interval": (5, 600),
    "auto_logout_minutes": (0, 1440),
    "web_http_port": (1, 65535),
    "web_https_port": (1, 65535),
    "web_login_port": (1, 65535),
    "web_ssl_certificate_id": (0, 10**9),
    "collection_interval": (10, 3600),
    "alert_realert_minutes": (1, 1440),
    "vm_alert_cpu_threshold": (1, 100),
    "vm_alert_memory_threshold": (1, 100),
    "vm_alert_disk_threshold": (1, 100),
    "log_forward_port": (1, 65535),
    "login_max_attempts": (3, 20),
    "login_lock_minutes": (1, 1440),
    "audit_retention_days": (0, 3650),
    "backup_interval_hours": (1, 168),
    "backup_retention_count": (1, 90),
    "alert_sound_interval": (10, 3600),
    "alert_broadcast_max_items": (1, 20),
    "password_min_length": (4, 32),
    "password_expiry_days": (0, 36500),
    "integration_port": (1, 65535),
    "integration_timeout": (1, 60),
    "integration_sync_interval": (1, 1440),
    "cache_ttl_topology": (1, 300),
    "cache_ttl_dashboard": (1, 60),
    "cluster_heartbeat_interval": (10, 300),
    "config_backup_interval_hours": (1, 168),
    "config_backup_retention_count": (1, 200),
    "config_backup_concurrency": (1, 10),
    "config_backup_timeout": (10, 180),
    "cascade_tunnel_port": (1, 65535),
    "config_backup_sftp_port": (1, 65535),
    "config_backup_sftp_timeout": (3, 120),
}

# 枚举型配置的合法值
ENUMS = {
    "totp_policy": ["off", "all", "selected"],
    "web_protocol": ["http", "https"],
    "log_forward_type": ["syslog", "http", "file"],
    "log_forward_min_level": ["DEBUG", "INFO", "WARNING", "ERROR"],
    "log_forward_protocol": ["udp", "tcp"],
    "log_forward_format": ["rfc5424", "rfc3164"],
    "integration_db_type": ["mysql", "postgresql", "sqlite"],
    "lb_strategy": ["round_robin", "least_conn", "ip_hash"],
    "config_backup_storage_type": ["webdav", "sftp"],
    "log_forward_facility": [
        "kern", "user", "mail", "daemon", "auth", "syslog",
        "lpr", "news", "cron", "authpriv", "ftp",
        "local0", "local1", "local2", "local3",
        "local4", "local5", "local6", "local7",
    ],
}


def _parse_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def to_typed(key: str, raw: Any) -> Any:
    """把字符串值转换为对应类型"""
    _default, kind, _desc = DEFAULTS[key]
    if kind == "int":
        try:
            return int(raw)
        except (TypeError, ValueError):
            return DEFAULTS[key][0]
    if kind == "bool":
        return _parse_bool(raw)
    return "" if raw is None else str(raw)


def ensure_defaults(db: Session) -> None:
    """补齐缺失的默认配置项，并清理已废弃的配置项"""
    removed = db.query(SystemSetting).filter(
        SystemSetting.key.in_((
            "integration_url",
            "integration_auth_type",
            "integration_token",
            "integration_header_name",
        ))
    ).delete(synchronize_session=False)
    existing = {row.key for row in db.query(SystemSetting).all()}
    missing = [k for k in DEFAULTS if k not in existing]
    changed = bool(removed)

    for key in missing:
        default, _kind, _desc = DEFAULTS[key]
        db.add(SystemSetting(key=key, value=str(default)))
        changed = True
    # 后续迁移需要读取新插入的默认项；Session 为 autoflush=False，先显式 flush。
    db.flush()

    # 级联隧道专用端口旧默认值迁移：早期默认 8443，新默认 9527。
    tunnel_port_row = db.query(SystemSetting).filter(SystemSetting.key == "cascade_tunnel_port").first()
    if tunnel_port_row and str(tunnel_port_row.value or "").strip() == "8443":
        tunnel_port_row.value = "9527"
        changed = True

    # 告警详细语音播报默认开启一次性迁移；之后用户手动关闭不再被覆盖。
    broadcast_marker = db.query(SystemSetting).filter(
        SystemSetting.key == "alert_broadcast_default_on_migrated"
    ).first()
    if broadcast_marker is None:
        broadcast_row = db.query(SystemSetting).filter(
            SystemSetting.key == "alert_broadcast_enabled"
        ).first()
        if broadcast_row is None:
            db.add(SystemSetting(key="alert_broadcast_enabled", value="True"))
        else:
            broadcast_row.value = "True"
        db.add(SystemSetting(key="alert_broadcast_default_on_migrated", value="True"))
        changed = True

    # 旧版本默认系统名称迁移；用户自定义的名称保持不变
    name_row = db.query(SystemSetting).filter(SystemSetting.key == "system_name").first()
    if name_row and str(name_row.value or "").strip() in LEGACY_SYSTEM_NAMES:
        name_row.value = DEFAULT_SYSTEM_NAME
        changed = True
        logger.info("系统名称已从旧默认值迁移为：%s", DEFAULT_SYSTEM_NAME)

    # 版权名称迁移：旧版只存版权文字，自动提取其中的自定义名称并按标准格式重写。
    copyright_text_row = db.query(SystemSetting).filter(SystemSetting.key == "copyright_text").first()
    copyright_name_row = db.query(SystemSetting).filter(SystemSetting.key == "copyright_name").first()
    old_text = str(copyright_text_row.value or "").strip() if copyright_text_row else ""
    old_name = str(copyright_name_row.value or "").strip() if copyright_name_row else ""
    if "copyright_name" in missing or not old_name:
        old_name = extract_copyright_name(old_text) or DEFAULT_COPYRIGHT_NAME
    if old_name in AUTO_COPYRIGHT_NAMES:
        old_name = edition_copyright_name()
    if copyright_name_row is None:
        copyright_name_row = SystemSetting(key="copyright_name", value=old_name)
        db.add(copyright_name_row)
    elif copyright_name_row.value != old_name:
        copyright_name_row.value = old_name
        changed = True
    timezone_row = db.query(SystemSetting).filter(SystemSetting.key == "timezone").first()
    timezone_name = str(timezone_row.value or "Asia/Shanghai") if timezone_row else "Asia/Shanghai"
    standard_text = format_copyright(old_name, timezone_name=timezone_name)
    if copyright_text_row is None:
        db.add(SystemSetting(key="copyright_text", value=standard_text))
        changed = True
    elif str(copyright_text_row.value or "").strip() != standard_text:
        copyright_text_row.value = standard_text
        changed = True
    if old_text in LEGACY_COPYRIGHT_TEXTS:
        enabled_row = db.query(SystemSetting).filter(SystemSetting.key == "copyright_enabled").first()
        if enabled_row is None:
            db.add(SystemSetting(key="copyright_enabled", value="True"))
        else:
            enabled_row.value = "True"
        changed = True
    if changed:
        logger.info("版权信息已规范化为：%s", standard_text)

    # 登录安全基线一次性迁移：密码大小写/特殊字符 + 90 天有效期
    baseline_row = db.query(SystemSetting).filter(SystemSetting.key == SECURITY_BASELINE_KEY).first()
    if not baseline_row:
        security_updates = {
            "password_require_uppercase": True,
            "password_require_lowercase": True,
            "password_require_special": True,
            "password_expiry_days": 90,
        }
        for key, new_value in security_updates.items():
            row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
            if row is None:
                db.add(SystemSetting(key=key, value=str(new_value)))
            elif key == "password_expiry_days":
                try:
                    old_value = int(row.value or 0)
                except (TypeError, ValueError):
                    old_value = 0
                if old_value <= 0:
                    row.value = "90"
            elif _parse_bool(row.value) is False:
                row.value = "True"
        db.add(SystemSetting(key=SECURITY_BASELINE_KEY, value="1"))
        changed = True
        logger.info("已应用登录安全基线：密码大小写/特殊字符 + 90 天有效期")

    # 旧版登录端口默认 8000，新基线改为 HTTP:80 并默认启用 HTTP 登录
    web_baseline_row = db.query(SystemSetting).filter(SystemSetting.key == WEB_ACCESS_BASELINE_KEY).first()
    if not web_baseline_row:
        http_enabled_row = db.query(SystemSetting).filter(SystemSetting.key == "web_http_enabled").first()
        if http_enabled_row is None:
            db.add(SystemSetting(key="web_http_enabled", value="True"))
        elif _parse_bool(http_enabled_row.value) is False:
            http_enabled_row.value = "True"
        http_port_row = db.query(SystemSetting).filter(SystemSetting.key == "web_http_port").first()
        if http_port_row is None:
            db.add(SystemSetting(key="web_http_port", value="80"))
        elif str(http_port_row.value or "").strip() in ("", "0", "8000"):
            http_port_row.value = "80"
        db.add(SystemSetting(key=WEB_ACCESS_BASELINE_KEY, value="1"))
        changed = True
        logger.info("已应用 Web 登录基线：默认启用 HTTP 80 端口")

    # HTTPS 是唯一登录入口时，历史配置中的 HTTP 登录也必须自动关闭
    https_row = db.query(SystemSetting).filter(SystemSetting.key == "web_https_enabled").first()
    http_row = db.query(SystemSetting).filter(SystemSetting.key == "web_http_enabled").first()
    protocol_row = db.query(SystemSetting).filter(SystemSetting.key == "web_protocol").first()
    login_port_row = db.query(SystemSetting).filter(SystemSetting.key == "web_login_port").first()
    if protocol_row is None:
        protocol_row = SystemSetting(
            key="web_protocol",
            value="https" if (https_row is not None and _parse_bool(https_row.value)) else "http",
        )
        db.add(protocol_row)
        changed = True
    elif "web_protocol" in missing:
        # 新装/升级时，按已有的 HTTPS 开关决定初始协议，而不是固定 http
        protocol_row.value = "https" if (https_row is not None and _parse_bool(https_row.value)) else "http"
        changed = True
    protocol = str(protocol_row.value or "").strip().lower()
    if protocol not in ("http", "https"):
        protocol = "https" if (https_row is not None and _parse_bool(https_row.value)) else "http"
        protocol_row.value = protocol
        changed = True
    if https_row is not None:
        https_wanted = protocol == "https"
        if _parse_bool(https_row.value) is not https_wanted:
            https_row.value = "True" if https_wanted else "False"
            changed = True
    if http_row is not None:
        http_wanted = protocol == "http"
        if _parse_bool(http_row.value) is not http_wanted:
            http_row.value = "True" if http_wanted else "False"
            changed = True
    if login_port_row is None:
        port_key = "web_https_port" if protocol == "https" else "web_http_port"
        port_source = db.query(SystemSetting).filter(SystemSetting.key == port_key).first()
        default_port = 443 if protocol == "https" else 80
        login_port_row = SystemSetting(
            key="web_login_port",
            value=str((port_source.value if port_source else default_port) or default_port),
        )
        db.add(login_port_row)
        changed = True
    elif "web_login_port" in missing:
        port_key = "web_https_port" if protocol == "https" else "web_http_port"
        port_source = db.query(SystemSetting).filter(SystemSetting.key == port_key).first()
        default_port = 443 if protocol == "https" else 80
        login_port_row.value = str((port_source.value if port_source else default_port) or default_port)
        changed = True
    elif str(login_port_row.value or "").strip() in ("", "0", "8000"):
        login_port_row.value = "443" if protocol == "https" else "80"
        changed = True

    # 旧版默认 HTTP:80 迁移为默认 HTTPS:443；已有自定义 HTTP 端口/协议不强制迁移
    https_baseline_row = db.query(SystemSetting).filter(SystemSetting.key == WEB_HTTPS_BASELINE_KEY).first()
    if not https_baseline_row:
        current_protocol = str(protocol_row.value or "http").strip().lower()
        current_login_port = str(login_port_row.value or "").strip()
        current_https = _parse_bool(https_row.value) if https_row is not None else False
        if (
            current_protocol == "http"
            and current_login_port in ("", "80")
            and not current_https
        ):
            protocol_row.value = "https"
            login_port_row.value = "443"
            if https_row is not None:
                https_row.value = "True"
            if http_row is not None:
                http_row.value = "False"
            redirect_row = db.query(SystemSetting).filter(SystemSetting.key == "web_https_redirect_http").first()
            if redirect_row is None:
                db.add(SystemSetting(key="web_https_redirect_http", value="True"))
            else:
                redirect_row.value = "True"
            changed = True
            logger.info("默认登录已迁移为 HTTPS:443（HTTP:80 仅跳转）")
        db.add(SystemSetting(key=WEB_HTTPS_BASELINE_KEY, value="1"))
        changed = True

    if changed:
        db.commit()
        if missing:
            logger.info("已初始化系统配置项: %s", ", ".join(missing))
    elif removed:
        db.commit()
        logger.info("已清理 %s 项废弃配置", removed)


def get_all(db: Session, include_public_only: bool = False) -> Dict[str, Any]:
    """读取全部配置（带类型转换）"""
    rows = {row.key: row.value for row in db.query(SystemSetting).all()}
    result: Dict[str, Any] = {}
    for key in DEFAULTS:
        if include_public_only and key not in PUBLIC_KEYS:
            continue
        result[key] = to_typed(key, rows.get(key, DEFAULTS[key][0]))
    # 版权文字始终由“名称 + 互联网年份”生成，避免跨年后仍显示旧年份。
    copyright_name = str(result.get("copyright_name") or "").strip()
    if not copyright_name:
        copyright_name = extract_copyright_name(result.get("copyright_text")) or DEFAULT_COPYRIGHT_NAME
    result["copyright_name"] = copyright_name
    result["copyright_text"] = format_copyright(
        copyright_name, timezone_name=str(result.get("timezone") or "Asia/Shanghai")
    )
    return result


def get_value(db: Session, key: str) -> Any:
    """读取单个配置项"""
    if key in ("copyright_text", "copyright_name"):
        return get_all(db).get(key)
    row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
    if not row:
        return DEFAULTS[key][0]
    return to_typed(key, row.value)


def validate(mapping: Dict[str, Any]) -> Tuple[Dict[str, Any], List[str]]:
    """校验并规范化待保存配置，返回 (规范化值, 错误列表)"""
    errors: List[str] = []
    normalized: Dict[str, Any] = {}
    mapping = dict(mapping)
    if "copyright_name" in mapping or "copyright_text" in mapping:
        name = str(mapping.get("copyright_name") or "").strip()
        if not name:
            name = extract_copyright_name(mapping.get("copyright_text")) or DEFAULT_COPYRIGHT_NAME
        mapping["copyright_name"] = name
        mapping["copyright_text"] = format_copyright(
            name, timezone_name=str(mapping.get("timezone") or "Asia/Shanghai")
        )

    for key, value in mapping.items():
        if key not in DEFAULTS:
            errors.append(f"未知配置项: {key}")
            continue
        _default, kind, desc = DEFAULTS[key]

        if kind == "int":
            try:
                num = int(value)
            except (TypeError, ValueError):
                errors.append(f"{desc}：必须是整数")
                continue
            low, high = INT_RANGES.get(key, (0, 10**9))
            if not low <= num <= high:
                errors.append(f"{desc}：取值范围 {low}~{high}")
                continue
            normalized[key] = num
        elif kind == "bool":
            normalized[key] = _parse_bool(value)
        else:
            text = str(value or "").strip()
            if key in ENUMS:
                if text not in ENUMS[key]:
                    errors.append(f"{desc}：仅支持 {', '.join(ENUMS[key])}")
                    continue
                normalized[key] = text
            elif key == "system_name":
                if not text:
                    errors.append("系统名称不能为空")
                    continue
                if len(text) > 60:
                    errors.append("系统名称不能超过 60 个字符")
                    continue
                normalized[key] = text
            elif key == "login_subtitle":
                if len(text) > 200:
                    errors.append("登录页副标题不能超过 200 个字符")
                    continue
                normalized[key] = text
            elif key == "system_logo":
                if len(text) > 500:
                    errors.append("系统图标地址过长")
                    continue
                if text and not (
                    text.startswith("/uploads/")
                    or text.startswith("http://")
                    or text.startswith("https://")
                ):
                    errors.append("系统图标地址不合法")
                    continue
                normalized[key] = text
            elif key == "copyright_name":
                if not text:
                    text = DEFAULT_COPYRIGHT_NAME
                if len(text) > 60:
                    errors.append("版权名称不能超过 60 个字符")
                    continue
                normalized[key] = text
            elif key == "copyright_text":
                if len(text) > 200:
                    errors.append("版权文字不能超过 200 个字符")
                    continue
                normalized[key] = text
            elif key == "copyright_color":
                if not re.match(r"^#[0-9a-fA-F]{6}$", text):
                    errors.append("版权文字颜色必须是 #RRGGBB 格式")
                    continue
                normalized[key] = text.lower()
            elif key == "integration_name":
                if len(text) > 100:
                    errors.append("对接名称不能超过 100 个字符")
                    continue
                normalized[key] = text
            elif key == "integration_host":
                if len(text) > 255:
                    errors.append("数据库主机地址过长")
                    continue
                normalized[key] = text
            elif key in ("integration_database", "integration_username"):
                if len(text) > 255:
                    errors.append("数据库信息过长")
                    continue
                normalized[key] = text
            elif key == "integration_password":
                if len(text) > 2000:
                    errors.append("数据库密码过长")
                    continue
                normalized[key] = text
            elif key == "integration_sqlite_path":
                if len(text) > 500:
                    errors.append("SQLite 数据库路径过长")
                    continue
                normalized[key] = text
            elif key == "integration_charset":
                if len(text) > 32 or (text and not all(ch.isalnum() or ch in "_-" for ch in text)):
                    errors.append("MySQL 字符集格式不合法")
                    continue
                normalized[key] = text
            elif key == "cluster_name":
                if len(text) > 100:
                    errors.append("集群名称不能超过 100 个字符")
                    continue
                normalized[key] = text
            elif key == "lb_public_url":
                if len(text) > 500:
                    errors.append("负载均衡地址过长")
                    continue
                if text and not (text.startswith("http://") or text.startswith("https://")):
                    errors.append("负载均衡地址必须以 http:// 或 https:// 开头")
                    continue
                normalized[key] = text
            elif key == "redis_url":
                if len(text) > 500:
                    errors.append("Redis 地址过长")
                    continue
                if text and not (text.startswith("redis://") or text.startswith("rediss://")):
                    errors.append("Redis 地址必须以 redis:// 或 rediss:// 开头")
                    continue
                normalized[key] = text
            elif key == "language":
                if text not in LANGUAGES:
                    errors.append(f"语言仅支持: {', '.join(LANGUAGES)}")
                    continue
                normalized[key] = text
            elif key == "timezone":
                if text not in TIMEZONES:
                    errors.append("不支持的时区")
                    continue
                normalized[key] = text
            elif key == "log_forward_http_headers":
                if text:
                    try:
                        import json as _json

                        parsed = _json.loads(text)
                        if not isinstance(parsed, dict):
                            errors.append("HTTP 请求头必须是 JSON 对象")
                            continue
                    except _json.JSONDecodeError:
                        # 允许 "Key: Value" 每行一条
                        if all(":" not in line for line in text.splitlines() if line.strip()):
                            errors.append("HTTP 请求头格式错误（JSON 或每行 Key: Value）")
                            continue
                normalized[key] = text
            elif key == "ip_whitelist":
                if len(text) > 4000:
                    errors.append("IP 白名单内容过长（最多 4000 字符）")
                    continue
                from .security import validate_whitelist

                ok, error = validate_whitelist(text)
                if not ok:
                    errors.append(error)
                    continue
                normalized[key] = text
            elif key in ("log_forward_host", "log_forward_http_url", "log_forward_file_path",
                         "log_forward_app_name"):
                if len(text) > 500:
                    errors.append(f"{desc}：内容过长")
                    continue
                normalized[key] = text
            else:
                normalized[key] = text

    return normalized, errors


def _validate_forward_combo(merged: Dict[str, Any]) -> List[str]:
    """跨字段校验：启用日志转发时的必填项与格式"""
    if not merged.get("log_forward_enabled"):
        return []
    errors: List[str] = []
    target = merged.get("log_forward_type") or "syslog"
    if target == "syslog":
        host = (merged.get("log_forward_host") or "").strip()
        if not host:
            errors.append("启用 syslog 转发时，必须填写 syslog 服务器地址")
    elif target == "http":
        url = (merged.get("log_forward_http_url") or "").strip()
        if not url:
            errors.append("启用 HTTP 转发时，必须填写接收地址")
        elif not url.startswith(("http://", "https://")):
            errors.append("HTTP 接收地址必须以 http:// 或 https:// 开头")
    elif target == "file":
        path = (merged.get("log_forward_file_path") or "").strip()
        if not path:
            errors.append("启用文件转发时，必须填写文件路径")
    return errors


def _validate_security_combo(merged: Dict[str, Any]) -> List[str]:
    """跨字段校验：IP 白名单启用时必须填写至少一个地址"""
    if not merged.get("ip_whitelist_enabled"):
        return []
    from .security import parse_whitelist, validate_whitelist

    text = (merged.get("ip_whitelist") or "").strip()
    ok, error = validate_whitelist(text)
    if not ok:
        return [error]
    if not parse_whitelist(text):
        return ["启用 IP 白名单前，请填写至少一个允许访问的 IP 或网段"]
    return []


def save(db: Session, mapping: Dict[str, Any]) -> Dict[str, Any]:
    """保存配置并返回最新全量配置"""
    mapping = dict(mapping)
    if "copyright_name" in mapping or "copyright_text" in mapping:
        name = str(mapping.get("copyright_name") or "").strip()
        if not name:
            name = extract_copyright_name(mapping.get("copyright_text")) or DEFAULT_COPYRIGHT_NAME
        timezone_name = str(mapping.get("timezone") or get_value(db, "timezone") or "Asia/Shanghai")
        mapping["copyright_name"] = name
        mapping["copyright_text"] = format_copyright(name, timezone_name=timezone_name)
    # 跨字段校验（基于「当前配置 + 本次修改」合并结果）
    merged = get_all(db)
    merged.update(mapping)
    combo_errors = _validate_forward_combo(merged)
    combo_errors.extend(_validate_security_combo(merged))
    if combo_errors:
        raise ValueError("；".join(combo_errors))

    for key, value in mapping.items():
        row = db.query(SystemSetting).filter(SystemSetting.key == key).first()
        text = str(value)
        if row:
            row.value = text
        else:
            db.add(SystemSetting(key=key, value=text))
    db.commit()

    # 安全策略缓存失效
    try:
        from .security import invalidate_security_cache

        invalidate_security_cache()
    except Exception:  # noqa: BLE001
        pass

    # 采集间隔变更后同步到运行配置（采集循环每轮都会重新读取）
    if "collection_interval" in mapping:
        Config.COLLECTION_INTERVAL = int(mapping["collection_interval"])
        logger.info("后台采集间隔已调整为 %s 秒", Config.COLLECTION_INTERVAL)

    # 日志转发配置热生效
    if any(key.startswith("log_forward_") for key in mapping):
        apply_log_forward(db)

    return get_all(db)


def apply_log_forward(db: Session) -> Dict[str, Any]:
    """把日志转发配置应用到运行中的转发器"""
    from . import log_forward

    config = get_all(db)
    log_forward.apply_config(config)
    return log_forward.forwarder.describe()
