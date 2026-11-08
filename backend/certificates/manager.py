"""证书管理核心服务。

- 证书/私钥文件保存在 data/certificates，权限 600，目录权限 700
- 支持 IP SAN 证书导入与本地解析
- 支持通过 certbot 申请/续期 Let's Encrypt 免费证书
- 远程 443 证书监控复用网站监控的 TLS 读取能力
"""
from __future__ import annotations

import hashlib
import ipaddress
import logging
import os
import platform
import re
import shutil
import socket
import subprocess
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import dsa, ec, ed25519, ed448, rsa
from cryptography.x509.oid import NameOID
from sqlalchemy.orm import Session

from ..config import Config
from ..models.certificate import ManagedCertificate
from ..website.monitor import WebsiteMonitor

logger = logging.getLogger(__name__)

CERT_ROOT = Path(__file__).resolve().parents[2] / "data" / "certificates"
CERTBOT_BIN = os.getenv("CERTBOT_BIN", "certbot")
CERTBOT_LIVE_DIR = Path(os.getenv("CERTBOT_LIVE_DIR", "/etc/letsencrypt/live"))
ACME_TIMEOUT_SECONDS = int(os.getenv("ACME_TIMEOUT_SECONDS", "180"))
MAX_PEM_BYTES = 2 * 1024 * 1024
MAX_CHAIN_BYTES = 4 * 1024 * 1024
CERT_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


class CertificateError(Exception):
    """证书业务错误，路由层转换为 400。"""


def _now() -> datetime:
    return datetime.utcnow()


def _naive_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def _ensure_root() -> None:
    CERT_ROOT.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(CERT_ROOT, 0o700)
    except OSError:
        pass


def _cert_dir(cert_id: int) -> Path:
    path = CERT_ROOT / str(int(cert_id))
    path.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(path, 0o700)
    except OSError:
        pass
    return path


def _relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(CERT_ROOT.resolve()).as_posix()
    except ValueError:
        return path.name


def _absolute(relative: Optional[str]) -> Optional[Path]:
    if not relative:
        return None
    value = (CERT_ROOT / relative).resolve()
    try:
        value.relative_to(CERT_ROOT.resolve())
    except ValueError:
        return None
    return value


def _write_private(path: Path, data: str) -> None:
    path.write_text(data, encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass


def _days_left(valid_to: Optional[datetime]) -> Optional[int]:
    if not valid_to:
        return None
    return (valid_to - _now()).days


def _status_for(days: Optional[int], warning_days: int) -> str:
    if days is None:
        return "unknown"
    if days < 0:
        return "expired"
    if days <= max(1, int(warning_days or 30)):
        return "expiring"
    return "valid"


def _load_certificates(data: bytes) -> List[x509.Certificate]:
    if not data:
        raise CertificateError("证书内容为空")
    if len(data) > MAX_CHAIN_BYTES:
        raise CertificateError("证书文件过大")
    try:
        return list(x509.load_pem_x509_certificates(data))
    except Exception:
        # 兼容只含一段 PEM 的旧版 cryptography / 带 BOM 的证书
        text = data.decode("utf-8-sig", errors="ignore")
        blocks = re.findall(
            r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
            text,
            flags=re.S,
        )
        certs = []
        for block in blocks:
            try:
                certs.append(x509.load_pem_x509_certificate(block.encode("utf-8")))
            except Exception as exc:  # noqa: BLE001
                raise CertificateError(f"证书解析失败: {exc}") from exc
        if not certs:
            raise CertificateError("未找到 PEM 证书内容")
        return certs


def _load_private_key(data: bytes):
    if not data:
        raise CertificateError("私钥内容为空")
    if len(data) > MAX_PEM_BYTES:
        raise CertificateError("私钥文件过大")
    try:
        return serialization.load_pem_private_key(data, password=None)
    except Exception as exc:  # noqa: BLE001
        raise CertificateError(f"私钥解析失败（仅支持未加密 PEM 私钥）: {exc}") from exc


def _public_key_der(public_key) -> bytes:
    return public_key.public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _key_type(private_key) -> str:
    if isinstance(private_key, rsa.RSAPrivateKey):
        return f"RSA-{private_key.key_size}"
    if isinstance(private_key, ec.EllipticCurvePrivateKey):
        return f"EC-{private_key.curve.name}"
    if isinstance(private_key, ed25519.Ed25519PrivateKey):
        return "Ed25519"
    if isinstance(private_key, ed448.Ed448PrivateKey):
        return "Ed448"
    if isinstance(private_key, dsa.DSAPrivateKey):
        return f"DSA-{private_key.key_size}"
    return type(private_key).__name__


def _subject_value(name: x509.Name, oid) -> str:
    attrs = name.get_attributes_for_oid(oid) if name else []
    return str(attrs[0].value).strip() if attrs else ""


def _certificate_details(
    leaf: x509.Certificate,
    chain: List[x509.Certificate],
    private_key=None,
) -> Dict[str, Any]:
    not_before = getattr(leaf, "not_valid_before_utc", None) or leaf.not_valid_before
    not_after = getattr(leaf, "not_valid_after_utc", None) or leaf.not_valid_after
    not_before = _naive_utc(not_before)
    not_after = _naive_utc(not_after)
    san_dns: List[str] = []
    san_ips: List[str] = []
    try:
        ext = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        san_dns = [str(value).strip() for value in ext.value.get_values_for_type(x509.DNSName) if str(value).strip()]
        san_ips = [str(value).strip() for value in ext.value.get_values_for_type(x509.IPAddress) if str(value).strip()]
    except x509.ExtensionNotFound:
        pass
    except Exception:
        pass
    cn = _subject_value(leaf.subject, NameOID.COMMON_NAME)
    san = []
    for value in san_dns + san_ips:
        if value not in san:
            san.append(value)
    if not san and cn:
        san = [cn]
    primary = san[0] if san else cn
    # IP 证书优先使用 CN/SAN 中的 IP，避免同时带 DNS SAN 时把 DNS 当成主标识
    try:
        cn_ip = str(ipaddress.ip_address(cn))
    except ValueError:
        cn_ip = ""
    if cn_ip and cn_ip in san_ips:
        primary = cn_ip
    try:
        cert_type = "ip" if (
            san_ips
            or ipaddress.ip_address(primary)
        ) else "domain"
    except ValueError:
        cert_type = "domain"
    try:
        signature_algorithm = leaf.signature_algorithm_oid._name or str(leaf.signature_algorithm_oid)
    except Exception:
        signature_algorithm = str(getattr(leaf, "signature_hash_algorithm", "") or "")
    fingerprint = hashlib.sha256(leaf.public_bytes(serialization.Encoding.DER)).hexdigest()
    return {
        "primary_host": primary,
        "cert_type": cert_type,
        "san": san,
        "san_dns": san_dns,
        "san_ips": san_ips,
        "subject": leaf.subject.rfc4514_string(),
        "issuer": leaf.issuer.rfc4514_string(),
        "serial_number": format(leaf.serial_number, "X"),
        "fingerprint": fingerprint,
        "key_type": _key_type(private_key) if private_key else "",
        "signature_algorithm": signature_algorithm,
        "valid_from": not_before,
        "valid_to": not_after,
        "days_left": _days_left(not_after),
        "status": _status_for(_days_left(not_after), 30),
        "chain_count": len(chain),
    }


def _build_record(
    *,
    name: str,
    details: Dict[str, Any],
    source: str,
    warning_days: int,
    monitor_host: str,
    monitor_port: int,
    created_by: str,
    notes: str,
    auto_renew: bool,
    renew_config: Optional[dict] = None,
) -> ManagedCertificate:
    status = _status_for(details.get("days_left"), warning_days)
    return ManagedCertificate(
        name=name.strip()[:255] or f"证书-{details['primary_host']}",
        cert_type=details.get("cert_type") or "domain",
        source=source,
        primary_host=str(details.get("primary_host") or "")[:255],
        san_json=details.get("san") or [],
        subject=(details.get("subject") or "")[:500],
        issuer=(details.get("issuer") or "")[:500],
        serial_number=(details.get("serial_number") or "")[:200],
        fingerprint=(details.get("fingerprint") or "")[:200],
        key_type=(details.get("key_type") or "")[:50],
        signature_algorithm=(details.get("signature_algorithm") or "")[:100],
        valid_from=details.get("valid_from"),
        valid_to=details.get("valid_to"),
        status=status,
        last_checked_at=_now(),
        monitor_enabled=True,
        monitor_host=(monitor_host or details.get("primary_host") or "")[:255],
        monitor_port=monitor_port or 443,
        warning_days=max(1, min(3650, int(warning_days or 30))),
        auto_renew=bool(auto_renew),
        renew_config=renew_config or {},
        notes=notes or "",
        created_by=created_by or "",
        created_at=_now(),
        updated_at=_now(),
    )


def _store_files(
    record: ManagedCertificate,
    leaf_pem: str,
    key_pem: Optional[str],
    chain_pem: str,
) -> None:
    _ensure_root()
    directory = _cert_dir(record.id)
    cert_path = directory / "cert.pem"
    key_path = directory / "privkey.pem"
    chain_path = directory / "chain.pem"
    _write_private(cert_path, leaf_pem)
    if key_pem:
        _write_private(key_path, key_pem)
        record.key_path = _relative(key_path)
    else:
        try:
            key_path.unlink(missing_ok=True)
        except OSError:
            pass
        record.key_path = None
    if chain_pem.strip():
        _write_private(chain_path, chain_pem)
        record.chain_path = _relative(chain_path)
    else:
        try:
            chain_path.unlink(missing_ok=True)
        except OSError:
            pass
        record.chain_path = None
    record.cert_path = _relative(cert_path)


def import_certificate(
    db: Session,
    *,
    cert_data: bytes,
    key_data: Optional[bytes],
    chain_data: Optional[bytes],
    name: str,
    monitor_host: str = "",
    monitor_port: int = 443,
    warning_days: int = 30,
    notes: str = "",
    created_by: str = "",
    source: str = "import",
    auto_renew: bool = False,
    renew_config: Optional[dict] = None,
) -> ManagedCertificate:
    """导入 PEM 证书/私钥并保存到托管目录，支持 IP SAN。"""
    certs = _load_certificates(cert_data)
    leaf = certs[0]
    extra = list(certs[1:])
    if chain_data:
        extra.extend(_load_certificates(chain_data))
    private_key = _load_private_key(key_data) if key_data else None
    if private_key is not None:
        if _public_key_der(private_key.public_key()) != _public_key_der(leaf.public_key()):
            raise CertificateError("证书和私钥不匹配")
    details = _certificate_details(leaf, extra, private_key)
    if not details.get("primary_host"):
        raise CertificateError("证书中没有可用的域名或 IP")
    record = _build_record(
        name=name,
        details=details,
        source=source,
        warning_days=warning_days,
        monitor_host=monitor_host or details["primary_host"],
        monitor_port=monitor_port,
        created_by=created_by,
        notes=notes,
        auto_renew=auto_renew,
        renew_config=renew_config,
    )
    db.add(record)
    db.flush()
    chain_pem = "".join(
        cert.public_bytes(serialization.Encoding.PEM).decode("utf-8")
        for cert in extra
    )
    leaf_pem = leaf.public_bytes(serialization.Encoding.PEM).decode("utf-8")
    key_pem = None
    if private_key is not None:
        key_pem = key_data.decode("utf-8-sig") if key_data else ""
        if key_pem and not key_pem.endswith("\n"):
            key_pem += "\n"
    _store_files(record, leaf_pem, key_pem, chain_pem)
    db.commit()
    db.refresh(record)
    return record


def _file_text(record: ManagedCertificate, kind: str) -> Optional[str]:
    attr = {"cert": "cert_path", "key": "key_path", "chain": "chain_path"}.get(kind)
    path = _absolute(getattr(record, attr, None)) if attr else None
    if not path or not path.is_file():
        return None
    return path.read_text(encoding="utf-8")


def fullchain_text(record: ManagedCertificate) -> Optional[str]:
    leaf = _file_text(record, "cert")
    if not leaf:
        return None
    return leaf + (_file_text(record, "chain") or "")


def file_for_download(record: ManagedCertificate, kind: str) -> Optional[Path]:
    if kind == "fullchain":
        return None
    attr = {"cert": "cert_path", "key": "key_path", "chain": "chain_path"}.get(kind)
    return _absolute(getattr(record, attr, None)) if attr else None


def _update_from_remote(record: ManagedCertificate, info: Dict[str, Any]) -> None:
    if info.get("error"):
        record.status = "error"
        record.last_error = str(info["error"])[:2000]
        record.last_checked_at = _now()
        return
    valid_to = None
    try:
        valid_to = _naive_utc(datetime.fromisoformat(str(info.get("valid_to")).replace("Z", "+00:00")))
    except (TypeError, ValueError):
        pass
    record.issuer = (info.get("issuer") or record.issuer or "")[:500]
    record.subject = (info.get("subject") or record.subject or "")[:500]
    record.serial_number = (info.get("serial_number") or record.serial_number or "")[:200]
    record.valid_to = valid_to or record.valid_to
    if info.get("san"):
        # 远程 TLS 读取通常只返回 DNS SAN，保留托管证书中的 IP SAN
        merged = list(record.san_json or [])
        for value in list(info.get("san") or []):
            if value not in merged:
                merged.append(value)
        record.san_json = merged
    record.status = _status_for(_days_left(record.valid_to), record.warning_days)
    record.last_error = ""
    record.last_checked_at = _now()


async def refresh_certificate(
    db: Session,
    record: ManagedCertificate,
    monitor: Optional[WebsiteMonitor] = None,
) -> ManagedCertificate:
    """刷新证书状态；优先读取托管文件，开启监控时读取远程 TLS 证书。"""
    owns_monitor = monitor is None
    if owns_monitor:
        monitor = WebsiteMonitor()
        await monitor.start()
    try:
        if record.monitor_enabled and (record.monitor_host or record.primary_host):
            target = (record.monitor_host or record.primary_host or "").strip()
            if target:
                info = await monitor.check_certificate(
                    target,
                    int(record.monitor_port or 443),
                    timeout=8,
                )
                _update_from_remote(record, info)
        else:
            # 关闭远程监控时，仍以托管文件自身的有效期更新状态
            cert_text = _file_text(record, "cert")
            if cert_text:
                try:
                    details = _certificate_details(_load_certificates(cert_text.encode("utf-8"))[0], [])
                    record.valid_to = details.get("valid_to") or record.valid_to
                    record.status = _status_for(details.get("days_left"), record.warning_days)
                    record.last_error = ""
                except Exception as exc:  # noqa: BLE001
                    record.status = "error"
                    record.last_error = str(exc)[:2000]
            record.last_checked_at = _now()
        db.commit()
        db.refresh(record)
        return record
    finally:
        if owns_monitor:
            await monitor.stop()


async def refresh_all(db: Session) -> Dict[str, Any]:
    records = db.query(ManagedCertificate).all()
    monitor = WebsiteMonitor()
    await monitor.start()
    ok = errors = 0
    try:
        for record in records:
            try:
                await refresh_certificate(db, record, monitor)
                if record.status == "error":
                    errors += 1
                else:
                    ok += 1
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                errors += 1
                logger.warning("刷新证书 %s 失败: %s", record.id, exc)
    finally:
        await monitor.stop()
    return {"total": len(records), "ok": ok, "errors": errors}


def _normalize_domains(values: Iterable[str]) -> List[str]:
    domains: List[str] = []
    for item in values:
        for raw in re.split(r"[,;\s]+", str(item or "")):
            value = raw.strip().lower().rstrip(".")
            if not value:
                continue
            if value.startswith("*"):
                raise CertificateError("HTTP-01 暂不支持通配符证书，请使用 DNS 验证方式")
            try:
                ipaddress.ip_address(value)
            except ValueError:
                pass
            else:
                raise CertificateError("免费 ACME 证书不支持公网 IP，请导入 IP 证书")
            if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", value):
                raise CertificateError(f"域名不合法: {value}")
            if value not in domains:
                domains.append(value)
    if not domains:
        raise CertificateError("请至少填写一个域名")
    if len(domains) > 20:
        raise CertificateError("单个证书最多申请 20 个域名")
    return domains


OS_RELEASE_FILE = Path(os.getenv("OS_RELEASE_FILE", "/etc/os-release"))
CERTBOT_INSTALL_TIMEOUT = int(os.getenv("CERTBOT_INSTALL_TIMEOUT", "600"))


def _read_os_release() -> Dict[str, str]:
    data: Dict[str, str] = {}
    try:
        for line in OS_RELEASE_FILE.read_text(encoding="utf-8").splitlines():
            if "=" not in line or line.lstrip().startswith("#"):
                continue
            key, value = line.split("=", 1)
            data[key.strip()] = value.strip().strip("\"'")
    except OSError:
        pass
    return data


def _privilege_prefix() -> List[str]:
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        return []
    sudo = shutil.which("sudo")
    if not sudo:
        raise CertificateError(
            "当前服务不是 root 用户，且未找到 sudo。请使用 root 运行服务，"
            "或配置免密 sudo 后重试。"
        )
    check = subprocess.run(
        [sudo, "-n", "true"], capture_output=True, text=True, timeout=10, check=False,
    )
    if check.returncode != 0:
        raise CertificateError(
            "当前服务用户没有免密 sudo 权限，无法自动安装 certbot。"
            "请以 root 运行服务、配置 NOPASSWD sudo，或手动安装 certbot。"
        )
    return [sudo, "-n"]


def _package_plan(os_info: Dict[str, str]) -> Optional[Dict[str, Any]]:
    """按发行版和可用包管理器返回固定安装命令，不接收用户参数。"""
    distro_id = str(os_info.get("ID") or "").lower()
    like = str(os_info.get("ID_LIKE") or "").lower()
    family = f"{distro_id} {like}"

    def command(manager: str, update: List[str], install: List[str], label: str):
        binary = shutil.which(update[0] if update else install[0])
        if not binary:
            return None
        update_cmd = [binary] + update[1:] if update else []
        install_cmd = [binary] + install[1:]
        return {
            "manager": manager,
            "label": label,
            "update": update_cmd,
            "install": install_cmd,
        }

    candidates: List[Optional[Dict[str, Any]]] = []
    if any(token in family for token in ("debian", "ubuntu", "kali", "raspbian")):
        candidates.append(command("apt", ["apt-get", "update"], ["apt-get", "install", "-y", "certbot"], "Debian/Ubuntu（apt）"))
    if any(token in family for token in ("fedora", "rhel", "centos", "rocky", "almalinux", "openeuler", "kylin", "anolis")):
        candidates.append(command("dnf", [], ["dnf", "install", "-y", "certbot"], "RHEL 系（dnf）"))
        candidates.append(command("yum", [], ["yum", "install", "-y", "certbot"], "RHEL 系（yum）"))
    if any(token in family for token in ("opensuse", "suse")):
        candidates.append(command("zypper", [], ["zypper", "--non-interactive", "install", "certbot"], "openSUSE（zypper）"))
    if "alpine" in family:
        candidates.append(command("apk", [], ["apk", "add", "--no-cache", "certbot"], "Alpine（apk）"))
    if any(token in family for token in ("arch", "manjaro")):
        candidates.append(command("pacman", [], ["pacman", "-Sy", "--noconfirm", "--needed", "certbot"], "Arch（pacman）"))
    # 未识别的 Linux 发行版按实际可用的包管理器兜底
    if not any(candidates):
        candidates.extend([
            command("apt", ["apt-get", "update"], ["apt-get", "install", "-y", "certbot"], "Debian/Ubuntu（apt）"),
            command("dnf", [], ["dnf", "install", "-y", "certbot"], "RHEL 系（dnf）"),
            command("yum", [], ["yum", "install", "-y", "certbot"], "RHEL 系（yum）"),
            command("apk", [], ["apk", "add", "--no-cache", "certbot"], "Alpine（apk）"),
            command("zypper", [], ["zypper", "--non-interactive", "install", "certbot"], "openSUSE（zypper）"),
            command("pacman", [], ["pacman", "-Sy", "--noconfirm", "--needed", "certbot"], "Arch（pacman）"),
        ])
    return next((item for item in candidates if item), None)


def certbot_runtime_info() -> Dict[str, Any]:
    """返回当前操作系统、包管理器、权限与 certbot 安装状态。"""
    is_linux = platform.system().lower() == "linux"
    os_info = _read_os_release() if is_linux else {}
    plan = _package_plan(os_info) if is_linux else None
    path = certbot_path()
    version = ""
    if path:
        try:
            result = subprocess.run(
                [path, "--version"], capture_output=True, text=True,
                timeout=10, check=False,
            )
            version = ((result.stdout or "") + " " + (result.stderr or "")).strip()[:200]
        except Exception:  # noqa: BLE001
            version = ""
    can_install = False
    privilege_note = ""
    if is_linux and plan and not path:
        try:
            _privilege_prefix()
            can_install = True
        except CertificateError as exc:
            privilege_note = str(exc)
    if not is_linux:
        message = "当前不是 Linux，无法自动安装 certbot；请手动安装或在 Linux 服务器上使用在线申请"
    elif path:
        message = "certbot 已安装，可以直接申请免费证书"
    elif plan:
        message = "可以自动安装 certbot" if can_install else (privilege_note or "当前包管理器需要 root 或免密 sudo")
    else:
        message = "未识别的 Linux 发行版或包管理器，请手动安装 certbot"
    return {
        "platform": platform.system(),
        "is_linux": is_linux,
        "distro_id": os_info.get("ID", ""),
        "distro_name": os_info.get("PRETTY_NAME") or os_info.get("NAME", ""),
        "distro_version": os_info.get("VERSION_ID", ""),
        "package_manager": plan.get("manager", "") if plan else "",
        "package_label": plan.get("label", "") if plan else "",
        "can_install": can_install,
        "requires_privilege": bool(is_linux and plan and not path),
        "certbot_available": bool(path),
        "certbot_path": path,
        "certbot_version": version,
        "install_supported": bool(is_linux and plan),
        "message": message,
        "install_commands": (
            [" ".join(plan.get("update") or []), " ".join(plan.get("install") or [])]
            if plan else []
        ),
    }


def install_certbot() -> Dict[str, Any]:
    """按当前 Linux 发行版自动安装 certbot；仅执行固定包管理器命令。"""
    if platform.system().lower() != "linux":
        raise CertificateError("自动安装仅支持 Linux；当前系统不是 Linux")
    path = certbot_path()
    if path:
        return {**certbot_runtime_info(), "already_installed": True, "output": "certbot 已安装"}
    os_info = _read_os_release()
    plan = _package_plan(os_info)
    if not plan:
        raise CertificateError("未识别的 Linux 发行版或包管理器，请手动安装 certbot")
    prefix = _privilege_prefix()
    env = {
        **os.environ,
        "DEBIAN_FRONTEND": "noninteractive",
        "LANG": "C.UTF-8",
    }
    outputs: List[str] = []
    commands = []
    if plan.get("update"):
        commands.append(plan["update"])
    commands.append(plan["install"])
    for command in commands:
        command = prefix + command
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=CERTBOT_INSTALL_TIMEOUT,
                check=False,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise CertificateError(f"certbot 安装超时（>{CERTBOT_INSTALL_TIMEOUT}s）") from exc
        output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
        if output:
            outputs.append(output[-4000:])
        if result.returncode != 0:
            raise CertificateError(
                f"{plan['label']} 安装 certbot 失败（退出码 {result.returncode}）：\n"
                + (output[-2000:] or "无输出")
            )
    info = certbot_runtime_info()
    if not info.get("certbot_available"):
        raise CertificateError(
            "安装命令执行完成，但仍未找到 certbot。请检查 PATH 或手动安装。\n"
            + "\n".join(outputs)[-2000:]
        )
    return {**info, "already_installed": False, "output": "\n".join(outputs)[-4000:]}


def certbot_path() -> str:
    return shutil.which(CERTBOT_BIN) or ""


def certbot_available() -> bool:
    return bool(certbot_path())


def build_certbot_issue_command(
    domains: List[str],
    email: str,
    method: str,
    webroot: str,
    staging: bool,
    cert_name: str,
) -> List[str]:
    if not email or "@" not in email:
        raise CertificateError("请填写有效的 ACME 通知邮箱")
    if method not in ("webroot", "standalone"):
        raise CertificateError("验证方式仅支持 webroot 或 standalone")
    if method == "webroot":
        root = Path(webroot or "").expanduser()
        if not root.is_dir():
            raise CertificateError("Webroot 目录不存在，请先配置网站根目录")
    binary = certbot_path()
    if not binary:
        raise CertificateError(
            "服务器未安装 certbot。请先安装 certbot 并确保域名 80 端口可访问；"
            "安装示例：apt install certbot 或 dnf install certbot"
        )
    command = [
        binary, "certonly", "--non-interactive", "--agree-tos",
        "--email", email, "--cert-name", cert_name, "--expand",
    ]
    if staging:
        command.append("--staging")
    if method == "webroot":
        command.extend(["--webroot", "-w", str(Path(webroot).expanduser())])
    else:
        command.append("--standalone")
    for domain in domains:
        command.extend(["-d", domain])
    return command


def _read_certbot_live(cert_name: str) -> Tuple[bytes, bytes]:
    directory = CERTBOT_LIVE_DIR / cert_name
    fullchain = directory / "fullchain.pem"
    private_key = directory / "privkey.pem"
    if not fullchain.is_file() or not private_key.is_file():
        raise CertificateError(
            f"certbot 已执行，但未找到 {fullchain} 或 {private_key}；"
            "请检查 CERTBOT_LIVE_DIR 配置"
        )
    return fullchain.read_bytes(), private_key.read_bytes()


def _run_command(command: List[str]) -> str:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=ACME_TIMEOUT_SECONDS,
            check=False,
            env={**os.environ, "LANG": "C.UTF-8"},
        )
    except subprocess.TimeoutExpired as exc:
        raise CertificateError(f"证书申请超时（>{ACME_TIMEOUT_SECONDS}s）") from exc
    output = ((result.stdout or "") + "\n" + (result.stderr or "")).strip()
    if result.returncode != 0:
        raise CertificateError(output[-3000:] or "certbot 执行失败")
    return output


def _normalize_cert_subject(value: str) -> Any:
    text = str(value or "").strip().lower()
    if not text:
        raise CertificateError("证书主域名/IP 不能为空")
    if "://" in text or "/" in text:
        raise CertificateError("证书主域名/IP 不要包含协议或路径")
    try:
        return ipaddress.ip_address(text)
    except ValueError:
        pass
    if not re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", text):
        raise CertificateError(f"证书域名不合法: {value}")
    return text


def generate_self_signed_certificate(
    db: Session,
    *,
    name: str,
    common_name: str,
    san_values: Optional[Iterable[str]],
    valid_days: int,
    key_type: str,
    organization: str,
    monitor_host: str,
    monitor_port: int,
    warning_days: int,
    notes: str,
    created_by: str,
    source: str = "generated",
) -> ManagedCertificate:
    """生成自签名 PEM 证书和私钥，并进入证书托管库。"""
    cn = _normalize_cert_subject(common_name)
    values: List[Any] = [cn]
    for item in san_values or []:
        for raw in re.split(r"[,;\s]+", str(item or "")):
            if not raw.strip():
                continue
            normalized = _normalize_cert_subject(raw)
            if normalized not in values:
                values.append(normalized)
    if len(values) > 50:
        raise CertificateError("SAN 数量不能超过 50 个")
    try:
        days = int(valid_days or 365)
    except (TypeError, ValueError):
        raise CertificateError("证书有效期必须是整数") from None
    if not 1 <= days <= 3650:
        raise CertificateError("证书有效期必须在 1~3650 天之间")
    key_type = str(key_type or "rsa2048").lower()
    if key_type == "rsa4096":
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=4096)
    elif key_type == "ec256":
        private_key = ec.generate_private_key(ec.SECP256R1())
    elif key_type == "ec384":
        private_key = ec.generate_private_key(ec.SECP384R1())
    else:
        key_type = "rsa2048"
        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    now = datetime.now(timezone.utc)
    subject_attrs = [x509.NameAttribute(NameOID.COMMON_NAME, str(cn))]
    org = str(organization or "").strip()
    if org:
        subject_attrs.append(x509.NameAttribute(NameOID.ORGANIZATION_NAME, org[:128]))
    subject = x509.Name(subject_attrs)
    san_items = []
    for value in values:
        if isinstance(value, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
            san_items.append(x509.IPAddress(value))
        else:
            san_items.append(x509.DNSName(value))
    builder = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(subject)
        .public_key(private_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=5))
        .not_valid_after(now + timedelta(days=days))
        .add_extension(
            x509.BasicConstraints(ca=False, path_length=None),
            critical=True,
        )
        .add_extension(
            x509.KeyUsage(
                digital_signature=True,
                content_commitment=False,
                key_encipherment=True,
                data_encipherment=False,
                key_agreement=False,
                key_cert_sign=False,
                crl_sign=False,
                encipher_only=False,
                decipher_only=False,
            ),
            critical=True,
        )
        .add_extension(
            x509.ExtendedKeyUsage([x509.ExtendedKeyUsageOID.SERVER_AUTH]),
            critical=False,
        )
        .add_extension(x509.SubjectAlternativeName(san_items), critical=False)
        .add_extension(
            x509.SubjectKeyIdentifier.from_public_key(private_key.public_key()),
            critical=False,
        )
        .add_extension(
            x509.AuthorityKeyIdentifier.from_issuer_public_key(private_key.public_key()),
            critical=False,
        )
    )
    certificate = builder.sign(private_key, hashes.SHA256())
    cert_pem = certificate.public_bytes(serialization.Encoding.PEM)
    key_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    record = import_certificate(
        db,
        cert_data=cert_pem,
        key_data=key_pem,
        chain_data=None,
        name=name or f"自签名-{cn}",
        monitor_host=monitor_host or str(cn),
        monitor_port=monitor_port,
        warning_days=warning_days,
        notes=notes or "自动生成的自签名 PEM 证书",
        created_by=created_by,
        source=source,
    )
    return record


def current_device_hosts() -> List[str]:
    """获取当前设备可用于证书 SAN 的主机名和 IP（用于自动签发登录证书）。"""
    hosts: List[str] = []

    def add(value: str) -> None:
        text = str(value or "").strip().strip("[]").lower()
        if not text or text in hosts:
            return
        try:
            ip = ipaddress.ip_address(text)
        except ValueError:
            if re.fullmatch(r"[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?", text):
                hosts.append(text)
            return
        if ip.is_link_local or ip.is_multicast:
            return
        hosts.append(str(ip))

    try:
        add(socket.gethostname())
        add(socket.getfqdn())
    except OSError:
        pass
    try:
        for item in socket.getaddrinfo(socket.gethostname(), None):
            add(item[4][0])
    except OSError:
        pass
    try:
        import psutil  # optional dependency; use interfaces for the real device IP
        for addresses in psutil.net_if_addrs().values():
            for address in addresses:
                if address.family in (socket.AF_INET, socket.AF_INET6):
                    add(address.address.split("%", 1)[0])
    except Exception:  # noqa: BLE001
        pass
    add("127.0.0.1")
    add("::1")
    return hosts[:50] or ["127.0.0.1"]


def ensure_web_login_certificate(db: Session, created_by: str = "system") -> ManagedCertificate:
    """获取/自动签发当前设备的 10 年 HTTPS 登录证书。"""
    hosts = current_device_hosts()
    now = datetime.now(timezone.utc)
    existing = (
        db.query(ManagedCertificate)
        .filter(ManagedCertificate.source == "auto_device")
        .order_by(ManagedCertificate.created_at.desc(), ManagedCertificate.id.desc())
        .all()
    )
    for record in existing:
        valid_to = record.valid_to
        if valid_to and valid_to.tzinfo is None:
            valid_to = valid_to.replace(tzinfo=timezone.utc)
        if not valid_to or valid_to <= now + timedelta(days=30):
            continue
        san = {str(item).lower() for item in (record.san_json or [])}
        if san.intersection(hosts):
            return record
    # Prefer a real interface IP as CN; otherwise use hostname.
    cn = next((host for host in hosts if ":" not in host and host not in ("127.0.0.1",)), None)
    if not cn:
        cn = next((host for host in hosts if host not in ("127.0.0.1", "::1")), "127.0.0.1")
    record = generate_self_signed_certificate(
        db,
        name=f"设备自动证书-{cn}",
        common_name=cn,
        san_values=hosts,
        valid_days=3650,
        key_type="rsa2048",
        organization="",
        monitor_host=cn,
        monitor_port=443,
        warning_days=30,
        notes="启用 HTTPS 登录时由系统自动签发的当前设备证书，有效期 10 年。",
        created_by=created_by,
        source="auto_device",
    )
    logger.info("已自动签发 Web 登录设备证书: id=%s cn=%s", record.id, cn)
    return record


def apply_acme_certificate(
    db: Session,
    *,
    domains: List[str],
    email: str,
    method: str,
    webroot: str,
    staging: bool,
    auto_renew: bool,
    notes: str,
    created_by: str,
) -> ManagedCertificate:
    hosts = _normalize_domains(domains)
    if db.query(ManagedCertificate).filter(ManagedCertificate.primary_host == hosts[0]).first():
        raise CertificateError(f"证书库中已存在主域名为 {hosts[0]} 的证书，请先删除或改名")
    cert_name = CERT_NAME_RE.sub("-", hosts[0]).strip("-")[:80] or "managed-cert"
    command = build_certbot_issue_command(hosts, email, method, webroot, staging, cert_name)
    output = _run_command(command)
    logger.info("ACME 申请完成 %s: %s", cert_name, output[-500:])
    cert_data, key_data = _read_certbot_live(cert_name)
    record = import_certificate(
        db,
        cert_data=cert_data,
        key_data=key_data,
        chain_data=None,
        name=f"{hosts[0]} 免费证书",
        monitor_host=hosts[0],
        monitor_port=443,
        warning_days=30,
        notes=notes,
        created_by=created_by,
        source="acme",
        auto_renew=auto_renew,
        renew_config={
            "domains": hosts,
            "email": email,
            "method": method,
            "webroot": webroot,
            "staging": bool(staging),
            "cert_name": cert_name,
        },
    )
    return record


def renew_acme_certificate(db: Session, record: ManagedCertificate) -> ManagedCertificate:
    config = record.renew_config or {}
    if record.source != "acme" or not config:
        raise CertificateError("该证书不是由本系统申请的 ACME 证书，无法自动续期")
    cert_name = str(config.get("cert_name") or "").strip()
    if not cert_name:
        raise CertificateError("证书缺少 ACME 续期配置")
    binary = shutil.which(CERTBOT_BIN)
    if not binary:
        raise CertificateError("服务器未安装 certbot，无法续期")
    output = _run_command([
        binary, "renew", "--cert-name", cert_name, "--non-interactive",
    ])
    logger.info("ACME 续期完成 %s: %s", cert_name, output[-500:])
    cert_data, key_data = _read_certbot_live(cert_name)
    certs = _load_certificates(cert_data)
    private_key = _load_private_key(key_data)
    details = _certificate_details(certs[0], certs[1:], private_key)
    _store_files(
        record,
        certs[0].public_bytes(serialization.Encoding.PEM).decode("utf-8"),
        key_data.decode("utf-8-sig"),
        "".join(c.public_bytes(serialization.Encoding.PEM).decode("utf-8") for c in certs[1:]),
    )
    record.valid_from = details.get("valid_from")
    record.valid_to = details.get("valid_to")
    record.issuer = (details.get("issuer") or record.issuer or "")[:500]
    record.subject = (details.get("subject") or record.subject or "")[:500]
    record.serial_number = (details.get("serial_number") or "")[:200]
    record.fingerprint = (details.get("fingerprint") or "")[:200]
    record.status = _status_for(details.get("days_left"), record.warning_days)
    record.last_error = ""
    record.last_renew_error = ""
    record.last_checked_at = _now()
    record.updated_at = _now()
    db.commit()
    db.refresh(record)
    return record


def serialize_certificate(record: ManagedCertificate) -> Dict[str, Any]:
    days = _days_left(record.valid_to)
    status = record.status or _status_for(days, record.warning_days)
    if record.last_error and status not in ("expired", "error"):
        status = "error"
    labels = {
        "valid": "有效",
        "expiring": "即将到期",
        "expired": "已过期",
        "error": "读取异常",
        "unknown": "未知",
    }
    result = {
        "id": record.id,
        "name": record.name,
        "cert_type": record.cert_type or "domain",
        "source": record.source or "import",
        "primary_host": record.primary_host,
        "san": list(record.san_json or []),
        "subject": record.subject or "",
        "issuer": record.issuer or "",
        "serial_number": record.serial_number or "",
        "fingerprint": record.fingerprint or "",
        "key_type": record.key_type or "",
        "signature_algorithm": record.signature_algorithm or "",
        "valid_from": record.valid_from.isoformat() if record.valid_from else None,
        "valid_to": record.valid_to.isoformat() if record.valid_to else None,
        "days_left": days,
        "status": status,
        "status_label": labels.get(status, status),
        "last_error": record.last_error or "",
        "last_checked_at": record.last_checked_at.isoformat() if record.last_checked_at else None,
        "monitor_enabled": record.monitor_enabled is not False,
        "monitor_host": record.monitor_host or record.primary_host or "",
        "monitor_port": record.monitor_port or 443,
        "warning_days": record.warning_days or 30,
        "auto_renew": bool(record.auto_renew),
        "last_renew_error": record.last_renew_error or "",
        "has_private_key": bool(record.key_path),
        "has_chain": bool(record.chain_path),
        "notes": record.notes or "",
        "created_by": record.created_by or "",
        "created_at": record.created_at.isoformat() if record.created_at else None,
        "updated_at": record.updated_at.isoformat() if record.updated_at else None,
    }
    return result
