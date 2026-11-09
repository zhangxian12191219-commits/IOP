"""网管系统主应用"""
import asyncio
import hmac
import logging
import logging.handlers
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse

import uvicorn
from fastapi import Depends, FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from .config import Config
from .models.database import get_db, init_db, SessionLocal, engine
from .snmp.collector import DataCollector
from .routes import assets, monitor, topology, notifications, rooms, discovery, tools, notes, license as license_routes, alert_rules
from .routes import im as im_routes
from .routes import ai as ai_routes
from .routes import cascade as cascade_routes
from .routes import auth as auth_routes
from .routes import virtualization as virtualization_routes
from .routes import users as user_routes
from .routes import cluster as cluster_routes
from .routes import network as network_routes
from .routes import config_backups as config_backup_routes
from .routes import settings as settings_routes
from .routes import audit as audit_routes
from .routes import system as system_routes
from .routes import update as update_routes
from .routes import mibs as mib_routes
from .routes import vendors as vendor_routes
from .routes import logs as log_routes
from .routes import bigscreen as bigscreen_routes
from .routes import sharing as sharing_routes
from .routes import inspection as inspection_routes
from .routes import credentials as credential_routes
from .certificates import routes as certificate_routes
from .certificates import manager as certificate_manager
from .certificates.scheduler import CertificateScheduler
from .models.user import User
from .services import auth
from .services import settings as settings_service
from .services import builtin_mibs
from .services import realert
from .services import log_forward
from .services import icon_presets
from .services import web_gateway as web_gateway_service
from .services import audit as audit_service
from .services import security
from .services import license_manager
from .services import systemd_notify
from .services import metrics as metrics_service
from .services import backup as backup_service
from .services import host_status as host_status_service
from .services import inspection as inspection_service
from .services.cache import KEY_DASHBOARD, cache
from .services import cluster_manager
from .services import cascade_tunnel
from .services.config_backup import scheduler as config_backup_scheduler
from .services.virtualization import scheduler as virtualization_scheduler
from .services.discovery_scheduler import DiscoveryScheduler, backfill_device_sources
from .website import routes as website_routes
from .website.scheduler import WebsiteScheduler

logging.basicConfig(
    level=getattr(logging, Config.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# 日志同时写入轮转文件，便于排查「意外退出」原因（容器/服务器重启后仍可查）
try:
    _log_dir = Path(Config.LOG_DIR)
    _log_dir.mkdir(parents=True, exist_ok=True)
    _file_handler = logging.handlers.RotatingFileHandler(
        _log_dir / "backend.log",
        maxBytes=Config.LOG_MAX_MB * 1024 * 1024,
        backupCount=Config.LOG_BACKUP_COUNT,
        encoding="utf-8",
    )
    _file_handler.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    logging.getLogger().addHandler(_file_handler)
except Exception as _exc:  # noqa: BLE001
    logging.getLogger("snmp-monitor").warning("无法写日志文件: %s", _exc)

logger = logging.getLogger("snmp-monitor")

START_TIME = time.time()

# 全局对象（生命周期内赋值）
collector: DataCollector | None = None
website_scheduler: WebsiteScheduler | None = None
certificate_scheduler: CertificateScheduler | None = None
_shutting_down = False


async def _supervised(name: str, factory, shutdown_event: asyncio.Event):
    """守护后台任务：异常/意外结束时自动重启（指数退避，最长 60 秒）"""
    backoff = 5
    while not shutdown_event.is_set():
        try:
            logger.info("后台任务启动: %s", name)
            await factory()
            if shutdown_event.is_set():
                break
            logger.warning("后台任务意外结束: %s，%s 秒后重启", name, backoff)
        except asyncio.CancelledError:
            logger.info("后台任务取消: %s", name)
            raise
        except Exception:  # noqa: BLE001
            logger.exception("后台任务异常: %s，%s 秒后重启", name, backoff)

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=backoff)
        except asyncio.TimeoutError:
            pass
        backoff = min(backoff * 2, 60)
    logger.info("后台任务已退出: %s", name)


async def _audit_cleanup_loop() -> None:
    """按配置的保留天数定期清理审计日志（启动先执行一次，之后每 6 小时）"""
    while True:
        db = SessionLocal()
        try:
            days = int(settings_service.get_value(db, "audit_retention_days") or 0)
            audit_service.cleanup(db, days)
        except Exception as exc:  # noqa: BLE001
            logger.warning("审计日志清理失败: %s", exc)
        finally:
            db.close()
        await asyncio.sleep(6 * 3600)


async def _im_cleanup_loop() -> None:
    """即时通信消息与附件按 15 天保留，启动先清理一次，之后每小时检查。"""
    while True:
        db = SessionLocal()
        try:
            result = im_routes.cleanup_expired_messages(db)
            if result.get("messages"):
                logger.info("即时通信到期清理: %s 条消息，%s 个附件", result["messages"], result["files"])
        except Exception as exc:  # noqa: BLE001
            logger.warning("即时通信到期清理失败: %s", exc)
            try:
                db.rollback()
            except Exception:
                pass
        finally:
            db.close()
        await asyncio.sleep(3600)


async def _backup_loop() -> None:
    """数据库自动备份：启动检查一次，之后每 30 分钟检查是否到期"""
    while True:
        db = SessionLocal()
        try:
            if settings_service.get_value(db, "backup_enabled"):
                hours = int(settings_service.get_value(db, "backup_interval_hours") or 24)
                retention = int(settings_service.get_value(db, "backup_retention_count") or 7)
                if backup_service.is_due(hours):
                    try:
                        result = backup_service.create_backup("auto", retention)
                        audit_service.record(
                            db, None, module="system", action="create",
                            target_type="backup", target_name=result["name"],
                            after={"file": result["name"], "size": result["size"],
                                   "method": result.get("method")},
                            message=f"自动数据库备份（{result.get('method')}，{result['size']} 字节）",
                            operator="system",
                        )
                    except Exception as exc:  # noqa: BLE001
                        logger.error("自动数据库备份失败: %s", exc)
                        audit_service.record(
                            db, None, module="system", action="create",
                            target_type="backup", target_name="自动数据库备份",
                            status="failed", message=str(exc)[:800],
                            operator="system",
                        )
        except Exception as exc:  # noqa: BLE001
            logger.warning("自动备份检查失败: %s", exc)
        finally:
            db.close()
        await asyncio.sleep(1800)


async def _systemd_heartbeat_loop() -> None:
    """systemd Watchdog 心跳（未配置 WatchdogSec 时只发送一次 READY）"""
    interval = systemd_notify.watchdog_interval()
    if interval <= 0:
        return
    logger.info("systemd watchdog 心跳已启动，间隔 %.1f 秒", interval)
    while True:
        await asyncio.sleep(interval)
        systemd_notify.watchdog()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    global collector, website_scheduler, _shutting_down

    init_db()
    # 写入内置设备图标库（/uploads/presets/*.svg）
    icon_presets.ensure_presets()
    db = SessionLocal()

    # 首次启动创建内置角色、示例群组与默认管理员
    auth.seed_defaults(db)
    # 初始化系统配置默认值
    settings_service.ensure_defaults(db)
    # 旧数据回填资产来源：带“自动发现”标签的历史设备标记为自动发现
    try:
        if backfill_device_sources(db):
            logger.info("已回填历史资产来源标记")
    except Exception as exc:  # noqa: BLE001
        logger.warning("资产来源回填失败（不影响启动）: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass
    # 补齐内置厂商 MIB 常用对象库（交换机/服务器/存储）
    try:
        builtin_result = builtin_mibs.ensure_builtin_mibs(db)
        if builtin_result.get("created"):
            logger.info("已补齐 %s 个内置厂商 MIB 库", len(builtin_result["created"]))
    except Exception as exc:  # noqa: BLE001
        logger.warning("导入内置 MIB 库失败（不影响启动）: %s", exc)
        try:
            db.rollback()
        except Exception:
            pass

    # 应用 Web 系统配置中的 Redis/缓存参数；未配置时回退内存缓存
    try:
        runtime_settings = settings_service.get_all(db)
        # 数据库里未保存 Redis 地址时，回退到运维通过环境变量设置的 REDIS_URL，
        # 避免外部已手动接入但 Web 配置仍为空导致缓存被误判为内存模式。
        redis_url = str(runtime_settings.get("redis_url") or "").strip() or str(Config.REDIS_URL or "").strip()
        cache.reconfigure(
            enabled=bool(runtime_settings.get("redis_enabled")),
            url=redis_url,
            ttl_topology=int(runtime_settings.get("cache_ttl_topology") or 5),
            ttl_dashboard=int(runtime_settings.get("cache_ttl_dashboard") or 3),
        )
    except Exception as exc:  # noqa: BLE001
        logger.error("缓存配置初始化失败，使用默认缓存: %s", exc)

    # 日志转发：安装 Handler 并应用配置（可热更新）
    log_forward.install_handler()
    try:
        log_forward.apply_config(settings_service.get_all(db))
    except Exception as exc:  # noqa: BLE001
        logger.error("日志转发初始化失败: %s", exc)

    collector = DataCollector(db)
    website_scheduler = WebsiteScheduler(db)
    certificate_scheduler = CertificateScheduler(db)

    shutdown_event = asyncio.Event()
    discovery_scheduler = DiscoveryScheduler(shutdown_event)
    app.state.shutdown_event = shutdown_event

    background = Config.RUN_BACKGROUND_TASKS
    collect_task = website_task = audit_task = backup_task = systemd_task = config_backup_task = virtualization_task = discovery_task = im_cleanup_task = certificate_task = inspection_task = realert_task = None
    if background:
        collect_task = asyncio.create_task(
            _supervised("SNMP 采集", collector.run_continuous, shutdown_event)
        )
        website_task = asyncio.create_task(
            _supervised("网站监控调度", website_scheduler.start, shutdown_event)
        )
        certificate_task = asyncio.create_task(
            _supervised("证书监控调度", certificate_scheduler.start, shutdown_event)
        )
        audit_task = asyncio.create_task(
            _supervised("审计日志清理", _audit_cleanup_loop, shutdown_event)
        )
        im_cleanup_task = asyncio.create_task(
            _supervised("即时通信到期清理", _im_cleanup_loop, shutdown_event)
        )
        backup_task = asyncio.create_task(
            _supervised("数据库自动备份", _backup_loop, shutdown_event)
        )
        config_backup_task = asyncio.create_task(config_backup_scheduler.start(shutdown_event))
        virtualization_task = asyncio.create_task(virtualization_scheduler.start(shutdown_event))
        discovery_task = asyncio.create_task(
            _supervised("定时自动发现", discovery_scheduler.start, shutdown_event)
        )
        inspection_task = asyncio.create_task(
            _supervised("设备巡检调度", inspection_service.scheduler_loop, shutdown_event)
        )
        realert_task = asyncio.create_task(
            _supervised("严重告警再提醒", lambda: realert.realert_loop(shutdown_event), shutdown_event)
        )
        logger.info("后台采集/网站调度/证书监控/定时发现/设备巡检/严重告警再提醒/审计清理/即时通信清理/自动备份/配置备份/虚拟化同步任务已启动（带异常自动重启）")
    else:
        logger.info(
            "RUN_BACKGROUND_TASKS=0，本实例为无状态从节点：不运行采集/调度/备份/清理任务"
        )

    if systemd_notify.enabled():
        systemd_notify.ready(
            "SNMP Monitor ready" + ("" if background else " (worker)")
        )
        if systemd_notify.watchdog_interval() > 0:
            systemd_task = asyncio.create_task(_systemd_heartbeat_loop())

    app.state.collect_task = collect_task
    app.state.website_task = website_task
    app.state.certificate_task = certificate_task
    app.state.audit_task = audit_task
    app.state.im_cleanup_task = im_cleanup_task
    app.state.backup_task = backup_task
    app.state.systemd_task = systemd_task
    app.state.config_backup_task = config_backup_task
    app.state.virtualization_task = virtualization_task
    app.state.discovery_task = discovery_task
    app.state.inspection_task = inspection_task
    app.state.realert_task = realert_task
    cluster_manager.start_loop()
    try:
        await cascade_tunnel.manager.start()
    except Exception as exc:  # noqa: BLE001
        logger.warning("级联隧道启动失败: %s", exc)

    # 按「登录与安全」配置启动 HTTP/HTTPS 登录网关（内部应用仍监听 API_PORT）
    try:
        web_values = settings_service.get_all(db)
        if os.getenv("WEB_FORCE_HTTP", "0").strip().lower() in ("1", "true", "yes", "on"):
            if str(web_values.get("web_protocol") or "http").lower() != "http":
                logger.warning("WEB_FORCE_HTTP 已启用，本次启动强制使用 HTTP:80")
                settings_service.save(db, {
                    "web_protocol": "http",
                    "web_login_port": 80,
                    "web_http_enabled": True,
                    "web_https_enabled": False,
                    "web_https_redirect_http": False,
                })
                web_values = settings_service.get_all(db)
        if str(web_values.get("web_protocol") or "http").lower() == "https":
            try:
                device_cert = certificate_manager.ensure_web_login_certificate(db, "system")
                settings_service.save(db, {"web_ssl_certificate_id": device_cert.id})
            except Exception as cert_exc:  # noqa: BLE001
                logger.warning("自动签发 Web 登录证书失败，将继续使用已有证书: %s", cert_exc)
        gateway_status = await web_gateway_service.gateway.apply_from_settings(db, probe=False)
        if gateway_status.get("running"):
            logger.info("HTTP/HTTPS 登录网关已启动: %s", gateway_status.get("listeners"))
    except Exception as exc:  # noqa: BLE001
        logger.warning("HTTP/HTTPS 登录网关未启动: %s", exc)
        # HTTPS 启动失败时自动回退 HTTP，保证管理员仍能通过浏览器登录修复配置
        try:
            current_values = settings_service.get_all(db)
            if str(current_values.get("web_protocol") or "http").lower() == "https":
                settings_service.save(db, {
                    "web_protocol": "http",
                    "web_login_port": 80,
                    "web_http_enabled": True,
                    "web_https_enabled": False,
                    "web_https_redirect_http": False,
                })
                fallback_status = await web_gateway_service.gateway.apply_from_settings(db, probe=False)
                logger.error(
                    "HTTPS 登录启动失败，已自动回退 HTTP:80（%s）；请访问 HTTP 端口修复",
                    fallback_status.get("listeners"),
                )
        except Exception as fallback_exc:  # noqa: BLE001
            logger.error("HTTPS 失败后 HTTP 应急登录也启动失败: %s", fallback_exc)

    try:
        yield
    finally:
        _shutting_down = True
        logger.info("正在停止后台任务…")
        shutdown_event.set()
        systemd_notify.stopping("Stopping SNMP Monitor")
        try:
            cluster_manager.mark_offline(db)
        except Exception:  # noqa: BLE001
            pass
        await cluster_manager.stop_loop()
        try:
            await cascade_tunnel.manager.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            await config_backup_scheduler.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            await virtualization_scheduler.stop()
        except Exception:  # noqa: BLE001
            pass
        try:
            await discovery_scheduler.stop()
        except Exception:  # noqa: BLE001
            pass

        if collector:
            collector.stop()
        if collect_task:
            collect_task.cancel()
        if audit_task:
            audit_task.cancel()
        if im_cleanup_task:
            im_cleanup_task.cancel()
        if backup_task:
            backup_task.cancel()
        if discovery_task:
            discovery_task.cancel()
        if inspection_task:
            inspection_task.cancel()
        if systemd_task:
            systemd_task.cancel()
        if certificate_task:
            certificate_task.cancel()
        if realert_task:
            realert_task.cancel()
        for task in (collect_task, audit_task, im_cleanup_task, backup_task, discovery_task, inspection_task, systemd_task, certificate_task, realert_task):
            if not task:
                continue
            try:
                await task
            except asyncio.CancelledError:
                pass

        if website_scheduler and website_task:
            await website_scheduler.stop()
        if website_task:
            website_task.cancel()
            try:
                await website_task
            except asyncio.CancelledError:
                pass
        if certificate_scheduler:
            await certificate_scheduler.stop()
        try:
            await web_gateway_service.gateway.stop()
        except Exception:  # noqa: BLE001
            pass

        db.close()


app = FastAPI(
    title="智能运维服务平台",
    description="基于 SNMP 的网络设备与安全设备监控系统（含资产管理、拓扑、网站监控）",
    version="1.1.0",
    lifespan=lifespan,
)

# 默认同源部署，不开启跨域。仅在明确配置 CORS_ORIGINS 时放行指定来源。
# 禁止使用通配符来源，避免任意站点携带用户浏览器凭据调用接口。
cors_origins = [origin for origin in getattr(Config, "CORS_ORIGINS", []) if origin != "*"]
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type", "Accept", "X-Requested-With"],
    )
# 大屏首屏 JS/CSS 体积较大，启用 gzip 压缩降低新标签页加载时间
app.add_middleware(GZipMiddleware, minimum_size=1024)


# ==================== 安全响应头 ====================
@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "camera=(), geolocation=(), microphone=(self)")
    response.headers.setdefault(
        "Content-Security-Policy",
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; font-src 'self' data:; connect-src 'self' ws: wss:; "
        "media-src 'self' blob:; worker-src 'self' blob:; object-src 'none'; "
        "base-uri 'self'; frame-ancestors 'self'; form-action 'self'",
    )
    # 历史自定义 SVG 图标直接打开时强制沙箱，阻止 SVG 内脚本执行。
    if request.url.path.startswith("/uploads/") and request.url.path.lower().endswith(".svg"):
        response.headers["Content-Security-Policy"] = "sandbox"
    return response


# ==================== 静态资源缓存策略 ====================
@app.middleware("http")
async def static_cache_headers(request: Request, call_next):
    """Vite 产物文件名带 hash，可长期缓存；HTML 保持 no-cache 以便发版后立即更新。

    - /static/*：public, max-age=1 年, immutable → 浏览器不再反复发条件请求（减少 304 日志）
    - HTML 入口：no-cache → 每次重新校验入口，避免旧 index 引用已删除的 hash 文件
    """
    response = await call_next(request)
    if request.method == "GET":
        if request.url.path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif response.headers.get("content-type", "").startswith("text/html"):
            response.headers["Cache-Control"] = "no-cache"
    return response


# ==================== 认证与权限中间件 ====================
@app.middleware("http")
async def auth_middleware(request: Request, call_next):
    """统一鉴权：/api 下除白名单外均需 Bearer Token，并按模块校验权限"""
    path = request.url.path
    method = request.method

    # 登录网关正常时，8000 内部端口只允许本机 SSH 隧道/回滚使用。
    # 非本机访问必须先走 HTTP/HTTPS 网关，连登录页和健康检查也不放行。
    client_host = request.client.host if request.client else ""
    is_local_client = client_host in ("127.0.0.1", "::1", "localhost")
    # 只信任 Web 网关注入的共享密钥头；不能仅凭 X-Forwarded-Host 判断，
    # 否则外部客户端可伪造该头绕过内部端口限制。
    gateway = web_gateway_service.gateway
    supplied_gateway_token = request.headers.get("x-snmp-nms-gateway", "")
    is_gateway_proxy = bool(
        supplied_gateway_token
        and gateway.proxy_token
        and hmac.compare_digest(supplied_gateway_token, gateway.proxy_token)
        and request.headers.get("x-forwarded-host")
    )
    is_local_health_probe = is_local_client and path in ("/api/health", "/api/health/live")
    if web_gateway_service.gateway.should_block_direct() and not is_gateway_proxy and not is_local_health_probe:
        direct_port = request.url.port or request.scope.get("server", ("", None))[1]
        if int(direct_port or 0) == int(getattr(Config, "API_PORT", 8000)):
            return JSONResponse(
                {
                    "detail": "内部应用端口不对外提供访问，请使用系统配置中启用的 HTTP/HTTPS 登录端口。",
                    "code": "web_gateway_required",
                },
                status_code=403,
            )

    # 非 API（前端页面/静态资源）与白名单直接放行
    if not path.startswith("/api") or auth.is_public(method, path):
        return await call_next(request)

    # 登录网关启用后，禁止普通客户端绕过网关直连内部端口。
    if web_gateway_service.gateway.should_block_direct() and not is_gateway_proxy and not is_local_health_probe:
        return JSONResponse(
            {
                "detail": "请通过系统配置中启用的 HTTP/HTTPS 登录网关端口访问；内部应用端口不对外提供登录入口。",
                "code": "web_gateway_required",
            },
            status_code=403,
        )

    # 支持 Authorization: Bearer <token>，也兼容 ?token=（用于导出下载链接）
    header = request.headers.get("authorization") or ""
    token = ""
    if header.lower().startswith("bearer "):
        token = header[7:].strip()
    if not token:
        token = request.query_params.get("token") or ""

    if not token:
        return JSONResponse({"detail": "未登录，请先登录"}, status_code=401)

    try:
        payload = auth.decode_token(token)
        user_id = int(payload.get("sub") or 0)
    except (ValueError, TypeError) as exc:
        return JSONResponse({"detail": f"登录已失效: {exc}"}, status_code=401)

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if not user or not user.is_active:
            return JSONResponse({"detail": "用户不存在或已被禁用"}, status_code=401)
        token_iat = int(payload.get("iat") or 0)
        changed_at = user.password_changed_at
        if changed_at and token_iat and token_iat < int(changed_at.timestamp()) - 5:
            return JSONResponse({"detail": "密码已修改，请重新登录"}, status_code=401)

        request.state.user_id = user.id
        request.state.username = user.username
        request.state.is_superuser = bool(user.is_superuser)

        # 系统配置（含对接/缓存/授权参数）只允许超级管理员查看和修改；
        # 告警声音信息是普通用户播放告警提示所需的只读数据，单独放行。
        settings_read_allowed = (
            path.rstrip("/") == "/api/settings/alert-sound"
            and method in ("GET", "HEAD", "OPTIONS")
        )
        if path.startswith("/api/settings") and not user.is_superuser and not settings_read_allowed:
            return JSONResponse(
                {"detail": "系统配置仅超级管理员可查看和修改"},
                status_code=403,
            )

        # 集群/负载均衡配置仅超级管理员
        if path.startswith("/api/cluster") and not user.is_superuser:
            return JSONResponse(
                {"detail": "集群与负载均衡配置仅超级管理员可查看和修改"},
                status_code=403,
            )

        # 系统更新会替换程序并重启服务，仅超级管理员可操作
        if path.startswith("/api/system/update") and not user.is_superuser:
            return JSONResponse(
                {"detail": "系统更新仅超级管理员可操作"},
                status_code=403,
            )

        # 主机网络/服务/防火墙/计划任务仅超级管理员
        if path.startswith("/api/network") and not user.is_superuser:
            return JSONResponse(
                {"detail": "主机网络配置仅超级管理员可操作"},
                status_code=403,
            )

        # 告警渠道/日志仅超级管理员可见和配置
        if path.startswith("/api/notifications") and not user.is_superuser:
            return JSONResponse(
                {"detail": "告警渠道仅超级管理员可查看和配置"},
                status_code=403,
            )

        # 用户/角色/群组管理仅超级管理员；普通用户只允许读写自己的 /api/users/me
        if (
            path.startswith(("/api/users", "/api/roles", "/api/groups"))
            and not user.is_superuser
            and path.rstrip("/") != "/api/users/me"
        ):
            return JSONResponse(
                {"detail": "用户/角色/群组管理仅超级管理员可操作"},
                status_code=403,
            )

        need = auth.required_permission(method, path)
        if need and not auth.has_permission(user, need):
            return JSONResponse(
                {"detail": f"无权限执行该操作（{need}），请联系管理员分配角色"},
                status_code=403,
            )

        # 系统更新不属于授权功能模块，也不受授权到期限制；
        # 仍要求管理员登录，并继续受超级管理员权限校验。
        if path.startswith("/api/system/update"):
            return await call_next(request)

        # 商业授权到期后，已登录会话也不能继续使用管理功能；
        # 授权接口本身保留，便于持有有效签名授权码的管理员续期。
        if license_manager.is_blocked() and not path.startswith("/api/license"):
            return JSONResponse(
                {
                    "detail": "商业授权无效、被篡改或已到期，系统禁止登录和继续使用，请更新授权文件后恢复。",
                    "code": "license_blocked",
                },
                status_code=403,
            )

        # 模块级功能授权（旧授权没有 features 字段时默认全部功能）
        feature_prefixes = (
            ("/api/assets", "assets"),
            ("/api/credentials", "credentials"),
            ("/api/alerts", "alerts"),
            ("/api/topology", "topology"),
            ("/api/bigscreen", "bigscreen"),
            ("/api/website", "website"),
            ("/api/rooms", "rooms"),
            ("/api/im", "im"),
            ("/api/ai", "ai"),
            ("/api/cascade", "cascade"),
            ("/api/inspection", "inspection"),
            ("/api/mibs", "mib"),
            ("/api/cluster", "cluster"),
            ("/api/network", "network"),
            ("/api/config-backups", "config_backup"),
            ("/api/virtualization", "virtualization"),
            ("/api/tools", "tools"),
            ("/api/audit", "audit"),
            ("/api/system", "backup"),
            ("/api/logs", "log_forward"),
        )
        # 系统时间/NTP 属于基础运维能力，不随「数据库与系统备份」功能授权开关
        skip_time_feature = path.startswith("/api/system/time")
        for prefix, feature in feature_prefixes:
            if skip_time_feature and prefix == "/api/system":
                continue
            if path.startswith(prefix) and not license_manager.has_feature(feature):
                return JSONResponse(
                    {
                        "detail": f"当前授权未包含「{license_manager.FEATURE_CATALOG.get(feature, feature)}」功能，请联系销售方升级授权。",
                        "code": "feature_not_licensed",
                    },
                    status_code=403,
                )
    finally:
        db.close()

    return await call_next(request)


# ==================== IP 白名单中间件 ====================
@app.middleware("http")
async def ip_whitelist_middleware(request: Request, call_next):
    """API 访问 IP 白名单（/api/health 始终放行，便于监控探活）

    - 默认关闭；在「系统配置 → 登录与安全」开启
    - 紧急绕过：环境变量 IP_WHITELIST_BYPASS=1 后重启服务
    """
    path = request.url.path
    if not path.startswith("/api") or path.rstrip("/") in ("/api/health", "/api/health/live"):
        return await call_next(request)
    if (os.getenv("IP_WHITELIST_BYPASS") or "").strip().lower() in ("1", "true", "yes", "on"):
        return await call_next(request)

    db = SessionLocal()
    try:
        cfg = security.get_security_config(db)
        if not cfg.get("ip_whitelist_enabled"):
            return await call_next(request)
        client = security.client_ip(request, bool(cfg.get("trust_proxy")))
        allowed = security.ip_allowed(client, cfg.get("ip_whitelist") or "")
    finally:
        db.close()

    if not allowed:
        return JSONResponse(
            {
                "detail": (
                    f"当前 IP（{client or 'unknown'}）不在 IP 白名单中，禁止访问。"
                    "如为误配置，可在服务器设置环境变量 IP_WHITELIST_BYPASS=1 后重启。"
                )
            },
            status_code=403,
        )
    return await call_next(request)


# 注册路由
app.include_router(auth_routes.router)
app.include_router(user_routes.users_router)
app.include_router(user_routes.roles_router)
app.include_router(user_routes.groups_router)
app.include_router(settings_routes.router)
# 系统时间 / NTP 设置（/api/system/time，与系统配置共用超管权限）
app.include_router(settings_routes.time_router)
app.include_router(audit_routes.router)
app.include_router(system_routes.router)
app.include_router(update_routes.router)
app.include_router(mib_routes.router)
app.include_router(vendor_routes.router)
app.include_router(cluster_routes.router)
app.include_router(network_routes.router)
app.include_router(config_backup_routes.router)
app.include_router(inspection_routes.router)
app.include_router(credential_routes.router)
app.include_router(log_routes.router)
app.include_router(assets.router)
app.include_router(discovery.router)
app.include_router(tools.router)
app.include_router(notes.router)
app.include_router(license_routes.router)
app.include_router(alert_rules.router)
app.include_router(monitor.router)
app.include_router(topology.router)
app.include_router(virtualization_routes.router)
app.include_router(notifications.router)
app.include_router(rooms.router)
app.include_router(website_routes.router)
app.include_router(certificate_routes.router, prefix="/api/website")
app.include_router(bigscreen_routes.router)
app.include_router(sharing_routes.router)
app.include_router(im_routes.router)
app.include_router(ai_routes.router)
app.include_router(cascade_routes.router)


@app.get("/api/health/live")
def health_live():
    """更新/重启期间使用的轻量存活探针，不访问数据库和缓存。"""
    return {"status": "ok", "service": "SNMP Monitor", "uptime_seconds": int(time.time() - START_TIME)}


@app.get("/api/health")
def health_check(db: Session = Depends(get_db)):
    """健康检查（Docker / systemd / 负载均衡探活用）

    - 数据库可用、进程正常返回 200
    - 数据库异常返回 503，便于守护脚本自动重启
    """
    db_ok = True
    db_error = None
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        db_ok = False
        db_error = str(exc)
        logger.error("健康检查失败：数据库不可用 %s", exc)

    payload = {
        "status": "ok" if db_ok else "degraded",
        "service": "SNMP Monitor",
        "version": "1.1.0",
        "instance_id": Config.INSTANCE_ID,
        "background_tasks": bool(Config.RUN_BACKGROUND_TASKS),
        "uptime_seconds": int(time.time() - START_TIME),
        "database": "ok" if db_ok else "error",
        "database_type": engine.dialect.name,
        "collector_running": bool(collector and collector.running),
        "website_scheduler_running": bool(
            website_scheduler and getattr(website_scheduler, "running", False)
        ),
        "systemd_watchdog": bool(systemd_notify.watchdog_interval() > 0),
        "metrics_url": "/metrics",
        "cache": cache.info(),
        "time": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if db_error:
        payload["error"] = db_error

    return JSONResponse(payload, status_code=200 if db_ok else 503)


@app.get("/api/system/host-status")
def host_status(db: Session = Depends(get_db)):
    """当前主机 CPU / 内存 / 磁盘 / 网卡、Web 网关、中间件与端口状态。"""
    payload = host_status_service.collect_host_status(
        db,
        collector_running=bool(collector and collector.running),
        scheduler_running=bool(
            website_scheduler and getattr(website_scheduler, "running", False)
        ),
        background_tasks=bool(Config.RUN_BACKGROUND_TASKS),
        systemd_watchdog=bool(systemd_notify.watchdog_interval() > 0),
        start_time=START_TIME,
    )
    values = settings_service.get_all(db)
    gateway = web_gateway_service.gateway.snapshot()
    cache_info = cache.info()
    listeners = gateway.get("listeners") or []
    protocol = gateway.get("protocol") or str(values.get("web_protocol") or "http")
    login_port = int(gateway.get("login_port") or values.get("web_login_port") or 80)
    web_running = bool(gateway.get("running") and listeners)
    payload["web"] = {
        "status": "running" if web_running else "error",
        "protocol": protocol,
        "login_port": login_port,
        "internal_port": int(gateway.get("internal_port") or Config.API_PORT),
        "listeners": listeners,
        "self_signed": bool(gateway.get("self_signed")),
        "error": gateway.get("error") or "",
    }
    payload["gateway"] = gateway
    payload["cache"] = cache_info
    payload["middleware"] = {
        "database": payload.get("database") or {},
        "cache": cache_info,
    }
    cache_status = "disabled" if cache_info.get("backend") == "disabled" else "running"
    cache_detail = (
        f"Redis {cache_info.get('redis_version') or ''}".strip()
        if cache_info.get("backend") == "redis"
        else "内存缓存（Redis 未启用或不可用）"
    )
    payload["services"] = list(payload.get("services") or []) + [
        {
            "key": "web_gateway",
            "name": "Web 登录网关",
            "status": "running" if web_running else "error",
            "detail": (
                f"{protocol.upper()} :{login_port} · 监听 {len(listeners)} 个入口"
                if web_running else (gateway.get("error") or "网关未运行")
            ),
        },
        {
            "key": "cache",
            "name": "缓存 / Redis",
            "status": cache_status,
            "detail": cache_detail,
        },
    ]

    expected = [
        {"port": login_port, "service": f"Web 登录入口（{protocol.upper()}）", "critical": True},
        {"port": 80, "service": "HTTP 访问端口", "critical": False},
        {"port": 443, "service": "HTTPS 访问端口", "critical": False},
        {"port": int(Config.API_PORT), "service": "内部 API 端口（网关拦截）", "critical": True, "scope": "internal"},
    ]
    try:
        db_port = db.get_bind().url.port if db.get_bind() is not None else None
        db_name = db.get_bind().url.get_backend_name() if db.get_bind() is not None else ""
        if db_port:
            expected.append({"port": int(db_port), "service": f"数据库（{db_name}）", "critical": True})
    except Exception:  # noqa: BLE001
        pass
    redis_url = str(getattr(cache, "redis_url", "") or "")
    if redis_url:
        try:
            parsed = urlparse(redis_url)
            if parsed.port:
                expected.append({"port": int(parsed.port), "service": "Redis 缓存", "critical": False})
        except Exception:  # noqa: BLE001
            pass
    payload["ports"] = host_status_service.collect_port_status(expected)
    return payload


@app.get("/metrics")
def prometheus_metrics(request: Request):
    """Prometheus 指标（纯文本 exposition format）

    若设置 METRICS_TOKEN，则需 `Authorization: Bearer <token>` 或 `?token=<token>`。
    """
    token = (Config.METRICS_TOKEN or "").strip()
    if token:
        header = request.headers.get("authorization") or ""
        provided = header[7:].strip() if header.lower().startswith("bearer ") else ""
        provided = provided or request.query_params.get("token", "")
        if provided != token:
            return JSONResponse({"detail": "metrics token invalid"}, status_code=401)

    db = SessionLocal()
    db_ok = True
    try:
        try:
            db.execute(text("SELECT 1"))
        except Exception as exc:  # noqa: BLE001
            db_ok = False
            logger.error("metrics 查询数据库失败: %s", exc)
        content = metrics_service.collect(
            db,
            uptime_seconds=time.time() - START_TIME,
            collector_running=bool(collector and collector.running),
            scheduler_running=bool(
                website_scheduler and getattr(website_scheduler, "running", False)
            ),
            db_ok=db_ok,
            instance_id=Config.INSTANCE_ID,
            background_tasks=bool(Config.RUN_BACKGROUND_TASKS),
        )
    finally:
        db.close()
    return Response(
        content=content,
        media_type="text/plain; version=0.0.4; charset=utf-8",
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """兜底异常处理：记录堆栈并返回 500，避免异常导致连接异常/进程退出"""
    logger.exception("未处理异常 %s %s", request.method, request.url.path)
    return JSONResponse(
        {"detail": "服务器内部错误，请查看服务日志"},
        status_code=500,
    )


@app.post("/api/snmp/test")
async def snmp_test(request: Request, payload: dict):
    """测试 SNMP 设备连通性（不落库，支持 v1/v2c/v3）

    请求体示例:
      v2c: {"ip_address":"10.0.0.1","community":"public","snmp_version":"v2c","port":161}
      v3:  {"ip_address":"10.0.0.1","snmp_version":"v3","port":161,
            "v3_username":"monitor","v3_security_level":"authPriv",
            "v3_auth_protocol":"SHA","v3_auth_password":"...",
            "v3_priv_protocol":"AES","v3_priv_password":"..."}

    也可以传 {"device_id": 1} 直接复用已保存的设备配置（含 v3 密码）。
    """
    from .snmp.snmp_client import SNMPClient, test_connection

    payload = payload or {}

    # 支持按 device_id 复用已保存配置
    if payload.get("device_id"):
        from .models.models import Device

        db = SessionLocal()
        try:
            device = db.query(Device).filter(Device.id == int(payload["device_id"])).first()
            if not device:
                return {"reachable": False, "error": "设备不存在"}
            from .services import asset_scope
            asset_scope.require_device_access(db, request, device)
            client = SNMPClient.from_device(device, timeout=Config.SNMP_TIMEOUT)
            result = await client.self_test()
            result["version"] = device.snmp_version
            result["device_id"] = device.id
            return result
        except Exception as exc:  # noqa: BLE001
            return {"reachable": False, "error": str(exc)}
        finally:
            db.close()

    host = payload.get("ip_address") or payload.get("host")
    if not host:
        return {"reachable": False, "error": "缺少 ip_address"}

    try:
        result = await test_connection(
            host=host,
            community=payload.get("community") or Config.SNMP_COMMUNITY_V2,
            version=payload.get("snmp_version") or "v2c",
            port=int(payload.get("port") or 161),
            timeout=int(payload.get("timeout") or Config.SNMP_TIMEOUT),
            v3_username=payload.get("v3_username"),
            v3_security_level=payload.get("v3_security_level") or "authPriv",
            v3_auth_protocol=payload.get("v3_auth_protocol") or "SHA",
            v3_auth_password=payload.get("v3_auth_password"),
            v3_priv_protocol=payload.get("v3_priv_protocol") or "AES",
            v3_priv_password=payload.get("v3_priv_password"),
            v3_context_name=payload.get("v3_context_name"),
        )
        return result
    except Exception as exc:  # noqa: BLE001
        return {"reachable": False, "error": str(exc)}


@app.post("/api/snmp/test-oid")
async def snmp_test_oid(request: Request, payload: dict):
    """测试单个 OID 是否可读（供 MIB 对象/自定义指标一键验证）

    请求体：
      {"device_id": 1, "oid": "1.3.6.1.2.1.1.1.0"}          # 复用设备凭据（含 v3 密码）
      {"ip_address":"10.0.0.1","community":"public","snmp_version":"v2c",
       "port":161,"oid":"1.3.6.1.2.1.1.1.0"}              # 未保存设备时可直接传凭据
    """
    import re as _re

    from .snmp.snmp_client import SNMPClient

    payload = payload or {}
    oid = str(payload.get("oid") or "").strip().lstrip(".")
    if not oid:
        return {"ok": False, "error": "缺少 oid"}
    if not _re.fullmatch(r"\d+(\.\d+){2,}", oid):
        return {"ok": False, "error": f"OID 格式不正确：{oid}"}

    db = SessionLocal()
    client = None
    device = None
    try:
        if payload.get("device_id"):
            from .models.models import Device
            from .services import asset_scope

            device = db.query(Device).filter(Device.id == int(payload["device_id"])).first()
            if not device:
                return {"ok": False, "error": "设备不存在"}
            asset_scope.require_device_access(db, request, device)
            if "demo" in (device.tags or []):
                return {
                    "ok": False, "oid": oid, "elapsed_ms": 0,
                    "device_id": device.id, "device_name": device.name,
                    "error": "演示设备不会发起真实 SNMP 请求，请对真实设备测试",
                }
            client = SNMPClient.from_device(device, timeout=Config.SNMP_TIMEOUT)
        else:
            from .models.user import User
            from .services import auth as auth_service
            probe_user = db.query(User).filter(User.id == int(getattr(request.state, "user_id", 0) or 0)).first()
            if not probe_user or not auth_service.has_permission(probe_user, "assets:edit"):
                return {"ok": False, "error": "未保存设备的临时 SNMP 探测需要资产编辑权限"}
            host = payload.get("ip_address") or payload.get("host")
            if not host:
                return {"ok": False, "error": "缺少 ip_address 或 device_id"}
            client = SNMPClient(
                host=host,
                community=payload.get("community") or Config.SNMP_COMMUNITY_V2,
                version=payload.get("snmp_version") or "v2c",
                port=int(payload.get("port") or 161),
                timeout=int(payload.get("timeout") or Config.SNMP_TIMEOUT),
                retries=Config.SNMP_RETRIES,
                v3_username=payload.get("v3_username"),
                v3_security_level=payload.get("v3_security_level") or "authPriv",
                v3_auth_protocol=payload.get("v3_auth_protocol") or "SHA",
                v3_auth_password=payload.get("v3_auth_password"),
                v3_priv_protocol=payload.get("v3_priv_protocol") or "AES",
                v3_priv_password=payload.get("v3_priv_password"),
                v3_context_name=payload.get("v3_context_name"),
            )

        started = time.time()
        try:
            raw = await client.get(oid)
        except Exception as exc:  # noqa: BLE001
            return {
                "ok": False, "oid": oid,
                "error": str(exc), "elapsed_ms": int((time.time() - started) * 1000),
            }
        elapsed = int((time.time() - started) * 1000)
        if raw is None:
            return {
                "ok": False, "oid": oid, "elapsed_ms": elapsed,
                "error": "No Such Object / 该 OID 在当前设备上不可读",
            }
        numeric = None
        match = _re.search(r"-?\d+(?:\.\d+)?", str(raw))
        if match:
            try:
                numeric = float(match.group(0))
            except ValueError:
                numeric = None
        return {
            "ok": True,
            "oid": oid,
            "value": str(raw),
            "numeric": numeric,
            "elapsed_ms": elapsed,
            "device_id": device.id if device else None,
            "device_name": device.name if device else None,
            "host": client.host,
        }
    finally:
        db.close()


@app.get("/api/dashboard")
def dashboard_stats(request: Request, response: Response):
    """仪表盘统计数据（按用户所属资产群组过滤设备与设备告警）"""
    from datetime import datetime, timedelta
    from .models.models import Device, Alert
    from .models.website import WebsiteAlert
    from .services import asset_scope

    db = SessionLocal()
    try:
        visible_ids = asset_scope.visible_device_ids(db, request)
        device_query = db.query(Device)
        alert_query = db.query(Alert)
        if visible_ids is not None:
            device_query = device_query.filter(Device.id.in_(visible_ids or [-1]))
            alert_query = alert_query.filter(Alert.device_id.in_(visible_ids or [-1]))

        total_devices = device_query.count()
        enabled_devices = device_query.filter(Device.is_enabled == True).count()  # noqa: E712
        unack_alerts = (
            alert_query.filter(Alert.is_acknowledged == False).count()  # noqa: E712
            + db.query(WebsiteAlert).filter(WebsiteAlert.is_acknowledged == False).count()  # noqa: E712
        )

        device_types: dict[str, int] = {}
        for device in device_query.all():
            device_types[device.device_type] = device_types.get(device.device_type, 0) + 1

        recent_since = datetime.utcnow() - timedelta(hours=24)
        recent_alerts = (
            alert_query.filter(Alert.created_at > recent_since).count()
            + db.query(WebsiteAlert).filter(WebsiteAlert.created_at > recent_since).count()
        )

        response.headers["X-Cache"] = "BYPASS"
        return {
            "total_devices": total_devices,
            "enabled_devices": enabled_devices,
            "unack_alerts": unack_alerts,
            "recent_alerts_24h": recent_alerts,
            "device_type_distribution": device_types,
            "metric_thresholds": {
                "cpu_usage": Config.CPU_THRESHOLD,
                "memory_usage": Config.MEMORY_THRESHOLD,
                "temperature": Config.TEMPERATURE_THRESHOLD,
                "temperature_critical": Config.TEMPERATURE_CRITICAL_THRESHOLD,
                "disk_usage": Config.DISK_THRESHOLD,
            },
        }
    finally:
        db.close()


@app.get("/api/dashboard/alert-trend")
def dashboard_alert_trend(request: Request):
    """首页最近 24 小时设备告警趋势（按用户资产群组过滤）"""
    from datetime import datetime, timedelta
    from .models.models import Alert
    from .services import asset_scope

    db = SessionLocal()
    try:
        visible_ids = asset_scope.visible_device_ids(db, request)
        now = datetime.utcnow()
        start = now - timedelta(hours=24)
        query = db.query(Alert.created_at).filter(Alert.created_at >= start)
        if visible_ids is not None:
            query = query.filter(Alert.device_id.in_(visible_ids or [-1]))
        rows = query.all()

        counts = [0] * 24
        for (created_at,) in rows:
            if not created_at:
                continue
            index = int((created_at - start).total_seconds() // 3600)
            if 0 <= index < 24:
                counts[index] += 1

        trend = []
        for index in range(24):
            point_time = start + timedelta(hours=index)
            trend.append({
                "time": point_time.strftime("%H:00"),
                "count": counts[index],
            })
        return {"alert_trend": trend}
    finally:
        db.close()


# ==================== 上传文件（设备自定义图标等）====================
from fastapi.staticfiles import StaticFiles  # noqa: E402

_UPLOAD_DIR = Path(Config.UPLOAD_DIR)
(_UPLOAD_DIR / "icons").mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_UPLOAD_DIR)), name="uploads")
logger.info("上传目录: %s", _UPLOAD_DIR)


# ==================== 单服务部署：托管前端构建产物 ====================
# 若存在 frontend/dist，则由后端直接提供前端页面，无需额外启动 Node 服务。
_DIST_DIR = Path(__file__).resolve().parent.parent / "frontend" / "dist"

if (_DIST_DIR / "index.html").exists():
    from fastapi.responses import FileResponse
    from fastapi.staticfiles import StaticFiles

    # 构建产物放在 /static 下，避免与前端路由 /assets、/devices 冲突
    _static_dir = _DIST_DIR / "static"
    if _static_dir.exists():
        app.mount(
            "/static",
            StaticFiles(directory=str(_static_dir)),
            name="static",
        )

    @app.get("/{full_path:path}", include_in_schema=False)
    async def spa_fallback(full_path: str):
        """SPA 路由回退：非 API 路径统一返回 index.html"""
        if full_path == "api" or full_path.startswith("api/"):
            return JSONResponse({"detail": "接口不存在"}, status_code=404)
        candidate = (_DIST_DIR / full_path).resolve()
        try:
            candidate.relative_to(_DIST_DIR.resolve())
        except ValueError:
            return FileResponse(_DIST_DIR / "index.html")
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST_DIR / "index.html")

    logger.info("已启用前端静态托管: %s", _DIST_DIR)


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=Config.API_HOST,
        port=Config.API_PORT,
        reload=False,
    )
