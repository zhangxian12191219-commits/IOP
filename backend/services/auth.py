"""认证与权限服务

- 密码哈希：PBKDF2-HMAC-SHA256（标准库，无额外依赖）
- 访问令牌：HMAC-SHA256 签名的 JWT（header.payload.signature）
- 权限模型：模块 + 动作，如 assets:view / assets:edit；"*" 表示全部
"""
import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Set

from sqlalchemy.orm import Session

from fastapi import Depends, HTTPException, Request

from ..config import Config, PROJECT_ROOT
from ..models.database import get_db
from ..models.user import Group, Role, User

logger = logging.getLogger(__name__)

PBKDF2_ITERATIONS = 120_000

# ==================== 权限点目录 ====================
# (权限点, 名称, 所属模块)
PERMISSIONS: List[Dict[str, str]] = [
    {"code": "assets:view", "name": "查看资产", "module": "资产管理"},
    {"code": "assets:edit", "name": "管理资产（增删改/导入）", "module": "资产管理"},
    {"code": "monitor:view", "name": "查看监控与告警", "module": "监控中心"},
    {"code": "monitor:edit", "name": "确认告警/触发采集", "module": "监控中心"},
    {"code": "topology:view", "name": "查看拓扑", "module": "网络拓扑"},
    {"code": "topology:edit", "name": "编辑拓扑/自动发现", "module": "网络拓扑"},
    {"code": "virtualization:view", "name": "查看虚拟化管理", "module": "虚拟化管理"},
    {"code": "virtualization:edit", "name": "管理虚拟化平台连接", "module": "虚拟化管理"},
    {"code": "rooms:view", "name": "查看机房与机柜", "module": "机房管理"},
    {"code": "rooms:edit", "name": "管理机房/机柜/开门", "module": "机房管理"},
    {"code": "website:view", "name": "查看网站监控", "module": "网站监控"},
    {"code": "website:edit", "name": "管理网站监控", "module": "网站监控"},
    {"code": "notifications:view", "name": "查看通知配置", "module": "告警渠道"},
    {"code": "notifications:edit", "name": "管理通知通道", "module": "告警渠道"},
    {"code": "users:view", "name": "查看用户/角色/群组", "module": "用户管理"},
    {"code": "users:edit", "name": "管理用户/角色/群组", "module": "用户管理"},
    {"code": "settings:view", "name": "查看系统配置", "module": "系统配置"},
    {"code": "settings:edit", "name": "修改系统配置", "module": "系统配置"},
    {"code": "audit:view", "name": "查看审计日志", "module": "审计日志"},
    {"code": "audit:edit", "name": "导出/清理审计日志", "module": "审计日志"},
    # ---- 资产运维细分：原有角色通过 assets:view / assets:edit 继承，保持兼容 ----
    {"code": "discovery:view", "name": "查看自动发现", "module": "资产运维", "description": "查看扫描结果、发现历史和待纳管设备"},
    {"code": "discovery:edit", "name": "执行扫描与纳管", "module": "资产运维", "description": "扫描网段、探测端口、把发现设备加入资产"},
    {"code": "inspection:view", "name": "查看设备巡检", "module": "资产运维", "description": "查看巡检任务、巡检结果和报告"},
    {"code": "inspection:edit", "name": "管理设备巡检", "module": "资产运维", "description": "创建巡检任务、执行巡检、上传报告"},
    {"code": "config_backup:view", "name": "查看配置备份", "module": "资产运维", "description": "查看网络设备配置备份和差异"},
    {"code": "config_backup:edit", "name": "管理配置备份", "module": "资产运维", "description": "执行备份、恢复配置、维护备份策略"},
    {"code": "credentials:view", "name": "查看设备凭据", "module": "资产运维", "description": "查看巡检/备份使用的设备账号列表（不回显明文密码）"},
    {"code": "credentials:edit", "name": "管理设备凭据", "module": "资产运维", "description": "新增、修改、删除巡检/备份凭据"},
    {"code": "mib:view", "name": "查看 MIB 管理", "module": "资产运维", "description": "查看 MIB 文件、对象和指标模板"},
    {"code": "mib:edit", "name": "管理 MIB 管理", "module": "资产运维", "description": "上传解析 MIB、绑定指标、删除 MIB 文件"},
    {"code": "tools:view", "name": "查看系统工具", "module": "资产运维", "description": "查看诊断、网络测试、批量工具"},
    {"code": "tools:edit", "name": "执行系统工具", "module": "资产运维", "description": "执行 Ping、端口、路由、抓包等诊断操作"},
    # ---- AI ----
    {"code": "ai:view", "name": "查看 AI 智能运维", "module": "AI 智能运维", "description": "打开 AI 运维页和 AI 大屏、查看分析结果"},
    {"code": "ai:use", "name": "使用 AI 对话与分析", "module": "AI 智能运维", "description": "发起对话、调用只读工具、生成报告"},
    {"code": "ai:config", "name": "配置 AI 模型", "module": "AI 智能运维", "description": "配置模型地址、密钥、TTS 和智能体参数（高风险）"},
    # ---- 大屏 ----
    {"code": "bigscreen:view", "name": "查看大屏展示", "module": "大屏展示", "description": "查看大屏管理、预览和分享"},
    {"code": "bigscreen:edit", "name": "管理大屏展示", "module": "大屏展示", "description": "创建、编辑、删除和分享大屏"},
    # ---- 授权与系统边界 ----
    {"code": "license:view", "name": "查看授权信息", "module": "授权与系统", "description": "查看授权版本、资产额度和功能模块"},
    {"code": "license:edit", "name": "激活和更换授权", "module": "授权与系统", "description": "激活、更换、停用商业授权（高风险）"},
    {"code": "cascade:view", "name": "查看级联管理", "module": "授权与系统", "description": "查看总部分支级联配置和状态"},
    {"code": "cascade:edit", "name": "管理级联配置", "module": "授权与系统", "description": "修改级联角色、隧道和分支配置（高风险）"},
    {"code": "cluster:view", "name": "查看集群状态", "module": "授权与系统", "description": "查看集群节点、负载和同步状态"},
    {"code": "cluster:edit", "name": "管理集群", "module": "授权与系统", "description": "修改集群节点和负载均衡配置（高风险）"},
    {"code": "network:view", "name": "查看主机网络", "module": "授权与系统", "description": "查看主机网络接口和路由"},
    {"code": "network:edit", "name": "管理主机网络", "module": "授权与系统", "description": "修改主机网络配置（高风险）"},
    {"code": "backup:view", "name": "查看系统备份", "module": "授权与系统", "description": "查看数据库和系统备份列表"},
    {"code": "backup:edit", "name": "管理/下载系统备份", "module": "授权与系统", "description": "创建、下载、删除和恢复系统备份（高风险）"},
]
ALL_PERMISSIONS: Set[str] = {p["code"] for p in PERMISSIONS}
MODULE_PERMISSIONS = {p["module"]: p for p in PERMISSIONS}

# 旧权限向新细粒度权限的兼容映射：现有角色无需重新配置即可继续使用。
PERMISSION_IMPLICATIONS: Dict[str, Set[str]] = {
    "assets:view": {
        "discovery:view", "inspection:view", "config_backup:view",
        "credentials:view", "mib:view", "tools:view",
    },
    "assets:edit": {
        "discovery:view", "discovery:edit", "inspection:view", "inspection:edit",
        "config_backup:view", "config_backup:edit", "credentials:view", "credentials:edit",
        "mib:view", "mib:edit", "tools:view", "tools:edit",
    },
    "monitor:view": {"bigscreen:view", "ai:view", "ai:use"},
    "monitor:edit": {"bigscreen:view", "bigscreen:edit", "ai:view", "ai:use"},
    "settings:view": {"license:view", "cascade:view", "cluster:view", "network:view", "backup:view"},
    "settings:edit": {
        "license:view", "license:edit", "cascade:view", "cascade:edit",
        "cluster:view", "cluster:edit", "network:view", "network:edit",
        "backup:view", "backup:edit",
    },
    "ai:config": {"ai:view", "ai:use"},
    "ai:use": {"ai:view"},
}
for _code in list(ALL_PERMISSIONS):
    if _code.endswith(":edit"):
        PERMISSION_IMPLICATIONS.setdefault(_code, set()).add(_code.rsplit(":", 1)[0] + ":view")


def expand_permissions(permissions: Iterable[str]) -> Set[str]:
    """展开权限继承关系；"*" 返回全部，供后端校验和前端菜单共用。"""
    result: Set[str] = set()
    queue = [str(item) for item in permissions or []]
    while queue:
        code = queue.pop()
        if code == "*":
            return set(ALL_PERMISSIONS)
        if not code or code in result:
            continue
        result.add(code)
        queue.extend(PERMISSION_IMPLICATIONS.get(code, ()))
    return result

# ==================== 密码 ====================
def hash_password(password: str) -> str:
    """生成密码哈希，格式: pbkdf2$iterations$salt$hash"""
    if not password:
        raise ValueError("密码不能为空")
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt), PBKDF2_ITERATIONS
    )
    return f"pbkdf2${PBKDF2_ITERATIONS}${salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """校验密码"""
    if not stored or not password:
        return False
    try:
        algo, iterations, salt, expected = stored.split("$", 3)
        if algo != "pbkdf2":
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(salt), int(iterations)
        )
        return hmac.compare_digest(digest.hex(), expected)
    except Exception:  # noqa: BLE001
        return False


# ==================== Token ====================
def _b64encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64decode(text: str) -> bytes:
    padding = "=" * (-len(text) % 4)
    return base64.urlsafe_b64decode(text + padding)


def create_token(user: User, hours: Optional[int] = None) -> str:
    """签发访问令牌"""
    ttl = int(hours or Config.AUTH_TOKEN_HOURS)
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": str(user.id),
        "username": user.username,
        "iat": now,
        "exp": now + ttl * 3600,
    }
    segments = [
        _b64encode(json.dumps(header, separators=(",", ":")).encode()),
        _b64encode(json.dumps(payload, separators=(",", ":")).encode()),
    ]
    signing_input = ".".join(segments).encode("ascii")
    signature = hmac.new(
        Config.AUTH_SECRET.encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    segments.append(_b64encode(signature))
    return ".".join(segments)


def decode_token(token: str) -> Dict[str, Any]:
    """解析并校验令牌，失败抛 ValueError"""
    if not token or token.count(".") != 2:
        raise ValueError("令牌格式错误")
    head_b64, payload_b64, sig_b64 = token.split(".")
    signing_input = f"{head_b64}.{payload_b64}".encode("ascii")
    expected = hmac.new(
        Config.AUTH_SECRET.encode("utf-8"), signing_input, hashlib.sha256
    ).digest()
    try:
        actual = _b64decode(sig_b64)
    except Exception as exc:  # noqa: BLE001
        raise ValueError("令牌签名无效") from exc
    if not hmac.compare_digest(expected, actual):
        raise ValueError("令牌签名无效")

    try:
        payload = json.loads(_b64decode(payload_b64))
    except Exception as exc:  # noqa: BLE001
        raise ValueError("令牌内容无效") from exc

    if payload.get("exp") and int(payload["exp"]) < int(time.time()):
        raise ValueError("令牌已过期")
    return payload


# ==================== 权限 ====================
def user_permission_set(user: User) -> Set[str]:
    """汇总用户所有角色的权限点"""
    if not user:
        return set()
    if user.is_superuser:
        return set(ALL_PERMISSIONS)
    raw: Set[str] = set()
    for role in user.roles or []:
        raw.update(role.permissions or [])
    return expand_permissions(raw)


def has_permission(user: Optional[User], permission: str) -> bool:
    if not user:
        return False
    if user.is_superuser:
        return True
    return permission in user_permission_set(user)


PERMISSION_LABELS = {p["code"]: p["name"] for p in PERMISSIONS}


def permission_labels(perms: Iterable[str]) -> List[str]:
    return [PERMISSION_LABELS.get(p, p) for p in perms]


# ==================== 路径 → 权限 ====================
MODULE_PREFIXES = [
    ("/api/assets", "assets"),
    ("/api/cluster", "cluster"),
    ("/api/network", "network"),
    ("/api/config-backups", "config_backup"),
    ("/api/discovery", "discovery"),
    ("/api/inspection", "inspection"),
    ("/api/credentials", "credentials"),
    ("/api/tools", "tools"),
    ("/api/mibs", "mib"),
    ("/api/snmp", "assets"),
    ("/api/monitor", "monitor"),
    ("/api/dashboard", "monitor"),
    ("/api/topology", "topology"),
    ("/api/virtualization", "virtualization"),
    ("/api/bigscreen", "bigscreen"),
    ("/api/rooms", "rooms"),
    ("/api/website", "website"),
    ("/api/notifications", "notifications"),
    ("/api/users", "users"),
    ("/api/roles", "users"),
    ("/api/groups", "users"),
    ("/api/settings", "settings"),
    ("/api/logs", "settings"),
    ("/api/audit", "audit"),
    ("/api/license", "license"),
    ("/api/cascade", "cascade"),
    ("/api/ai", "ai"),
]

PUBLIC_PATHS = {
    "/api/health",
    "/api/health/live",
    "/api/auth/login",
    "/api/settings/public",
    "/api/settings/captcha",
    "/api/settings/version",
    "/api/license/public-status",
    "/api/license/activate-public",
    "/api/notifications/upstream/ingest",
    "/api/cascade/tunnel",
}
PUBLIC_PREFIXES = ("/docs", "/redoc", "/openapi.json", "/static", "/assets", "/api/system/update/public-status")


def required_permission(method: str, path: str) -> Optional[str]:
    """根据请求方法与路径推导所需权限；返回 None 表示无需权限（仅需登录）"""
    if path.startswith("/api/auth"):
        return None
    # OID 测试是只读探测，查看资产权限即可
    if path.rstrip("/") == "/api/snmp/test-oid":
        return "assets:view"
    # 告警声音信息只需登录即可读取（用于所有用户播放告警提示）
    if path.rstrip("/") == "/api/settings/alert-sound" and method.upper() in ("GET", "HEAD", "OPTIONS"):
        return None
    # 当前用户自己的账号信息不依赖用户管理权限
    if path.rstrip("/") == "/api/users/me":
        return None
    # 数据库备份包含全部数据，列表/下载/删除均要求 settings:edit
    if path.startswith("/api/system/backups"):
        return "backup:view" if method.upper() in ("GET", "HEAD", "OPTIONS") else "backup:edit"
    if path.startswith("/api/system/update"):
        return "settings:edit"
    if path.startswith("/api/system/host-status"):
        return "settings:view"
    if path.startswith("/api/ai"):
        if path.rstrip("/") == "/api/ai/config":
            return "ai:config" if method.upper() not in ("GET", "HEAD", "OPTIONS") else "ai:view"
        if method.upper() in ("GET", "HEAD", "OPTIONS"):
            return "ai:view"
        return "ai:use"
    for prefix, module in MODULE_PREFIXES:
        if path == prefix or path.startswith(prefix + "/") or path.startswith(prefix + "?"):
            action = "view" if method.upper() in ("GET", "HEAD", "OPTIONS") else "edit"
            return f"{module}:{action}"
    # 其它 /api 接口默认要求登录即可
    return None


def is_public(method: str, path: str) -> bool:
    if method.upper() == "OPTIONS":
        return True
    if path in PUBLIC_PATHS:
        return True
    return any(path.startswith(p) for p in PUBLIC_PREFIXES)


# ==================== 默认数据 ====================
DEFAULT_ROLES = [
    {
        "name": "超级管理员",
        "code": "admin",
        "description": "拥有系统全部权限",
        "permissions": ["*"],
        "is_builtin": True,
    },
    {
        "name": "运维管理员",
        "code": "ops",
        "description": "可管理资产、监控、拓扑、机房与网站，不可管理用户、告警渠道或系统配置",
        "permissions": [
            "assets:view", "assets:edit",
            "discovery:view", "discovery:edit",
            "inspection:view", "inspection:edit",
            "config_backup:view", "config_backup:edit",
            "credentials:view", "credentials:edit",
            "mib:view", "mib:edit", "tools:view", "tools:edit",
            "monitor:view", "monitor:edit",
            "bigscreen:view", "bigscreen:edit",
            "ai:view", "ai:use",
            "topology:view", "topology:edit",
            "virtualization:view",
            "rooms:view", "rooms:edit",
            "website:view", "website:edit",
            "audit:view", "audit:edit",
        ],
        "is_builtin": True,
    },
    {
        "name": "监控查看员",
        "code": "viewer",
        "description": "只读查看各类监控数据",
        "permissions": [
            "assets:view",
            "discovery:view", "inspection:view", "config_backup:view",
            "credentials:view", "mib:view", "tools:view",
            "monitor:view", "bigscreen:view", "ai:view", "ai:use",
            "topology:view", "virtualization:view",
            "rooms:view", "website:view",
        ],
        "is_builtin": True,
    },
]

DEFAULT_GROUPS = [
    {"name": "网络运维组", "code": "network", "description": "负责路由交换等网络设备"},
    {"name": "安全运维组", "code": "security", "description": "负责防火墙与安全设备"},
    {"name": "机房运维组", "code": "datacenter", "description": "负责机房与机柜管理"},
]


def seed_defaults(db: Session) -> None:
    """首次启动创建内置角色、示例群组与管理员账号"""
    if db.query(Role).count() == 0:
        for item in DEFAULT_ROLES:
            db.add(Role(**item))
        db.commit()
        logger.info("已创建内置角色: %s", ", ".join(r["name"] for r in DEFAULT_ROLES))

    if db.query(Group).count() == 0:
        for item in DEFAULT_GROUPS:
            db.add(Group(**item))
        db.commit()
        logger.info("已创建示例用户群组: %s", ", ".join(g["name"] for g in DEFAULT_GROUPS))

    # 内置角色权限补齐（升级后新增权限点自动合并，不覆盖已有的额外权限）
    changed = False
    for item in DEFAULT_ROLES:
        role = db.query(Role).filter(Role.code == item["code"]).first()
        if not role:
            continue
        if role.code == "admin":
            if role.permissions != ["*"]:
                role.permissions = ["*"]
                changed = True
            continue
        current = list(role.permissions or [])
        # 这些模块只允许超级管理员；内置角色升级时同步移除旧权限
        restricted = {
            "notifications:view", "notifications:edit",
            "users:view", "users:edit",
            "settings:view", "settings:edit",
            "license:view", "license:edit",
        }
        current = [p for p in current if p not in restricted]
        merged = current + [p for p in item["permissions"] if p not in current]
        if merged != list(role.permissions or []):
            role.permissions = merged
            changed = True
    if changed:
        db.commit()
        logger.info("已同步内置角色权限点")

    if db.query(User).count() == 0:
        admin_role = db.query(Role).filter(Role.code == "admin").first()
        initial_password = (Config.AUTH_DEFAULT_PASSWORD or "").strip()
        generated_password = not initial_password
        if generated_password:
            initial_password = secrets.token_urlsafe(15)
        admin = User(
            username=Config.AUTH_DEFAULT_ADMIN,
            password_hash=hash_password(initial_password),
            real_name="系统管理员",
            is_active=True,
            is_superuser=True,
            must_change_password=True,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        if admin_role:
            admin.roles.append(admin_role)
        db.add(admin)
        db.commit()
        if generated_password:
            password_file = PROJECT_ROOT / "data" / "initial_admin_password.txt"
            try:
                password_file.parent.mkdir(parents=True, exist_ok=True)
                password_file.write_text(initial_password, encoding="utf-8")
                try:
                    os.chmod(password_file, 0o600)
                except OSError:
                    pass
                logger.warning(
                    "已创建管理员 %s，随机初始密码保存在 %s，登录后必须修改；"
                    "请勿把该文件提交到版本库",
                    Config.AUTH_DEFAULT_ADMIN,
                    password_file,
                )
            except OSError as exc:
                logger.error(
                    "已创建管理员 %s，但初始密码文件写入失败（%s）；"
                    "请设置 AUTH_DEFAULT_PASSWORD 后重建管理员",
                    Config.AUTH_DEFAULT_ADMIN,
                    exc,
                )
        else:
            logger.warning(
                "已创建管理员 %s（使用环境变量初始密码），首次登录必须修改密码！",
                Config.AUTH_DEFAULT_ADMIN,
            )


# ==================== FastAPI 依赖 ====================
def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    """从 request.state（由鉴权中间件写入）取当前用户"""
    user_id = getattr(request.state, "user_id", None)
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    user = db.query(User).filter(User.id == int(user_id)).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="用户不存在或已被禁用")
    return user


def require_permission(permission: str):
    """路由级权限校验依赖（中间件已做统一校验，这里用于关键接口二次确认）"""

    def checker(current: User = Depends(get_current_user)) -> User:
        if not has_permission(current, permission):
            raise HTTPException(status_code=403, detail=f"无权限执行该操作：{permission}")
        return current

    return checker


def user_to_dict(user: User, include_roles: bool = True) -> Dict[str, Any]:
    """用户序列化（不含密码）"""
    perms = sorted(user_permission_set(user))
    data: Dict[str, Any] = {
        "id": user.id,
        "username": user.username,
        "real_name": user.real_name,
        "email": user.email,
        "phone": user.phone,
        "is_active": user.is_active,
        "is_superuser": user.is_superuser,
        "last_login": user.last_login.isoformat() if user.last_login else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "permissions": perms,
    }
    if include_roles:
        data["roles"] = [{"id": r.id, "name": r.name, "code": r.code} for r in user.roles]
        data["role_ids"] = [r.id for r in user.roles]
        data["groups"] = [{"id": g.id, "name": g.name, "code": g.code} for g in user.groups]
        data["group_ids"] = [g.id for g in user.groups]
    return data
