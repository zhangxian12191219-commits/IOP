"""证书管理 API：监控、导入、托管和 ACME 免费证书申请。"""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models.certificate import ManagedCertificate
from ..models.database import get_db
from ..models.user import User
from ..services.auth import get_current_user
from ..services import settings as settings_service
from . import manager

router = APIRouter(prefix="/certificates", tags=["证书管理"])


def _get_certificate(db: Session, certificate_id: int) -> ManagedCertificate:
    record = db.query(ManagedCertificate).filter(ManagedCertificate.id == certificate_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="证书不存在")
    return record


def _is_admin(user: User) -> bool:
    return bool(user.is_superuser)


@router.get("")
def list_certificates(
    search: str = Query("", max_length=200),
    status: str = Query(""),
    source: str = Query(""),
    cert_type: str = Query(""),
    db: Session = Depends(get_db),
):
    query = db.query(ManagedCertificate)
    keyword = (search or "").strip()
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(or_(
            ManagedCertificate.name.ilike(like),
            ManagedCertificate.primary_host.ilike(like),
            ManagedCertificate.issuer.ilike(like),
        ))
    if status:
        query = query.filter(ManagedCertificate.status == status)
    if source:
        query = query.filter(ManagedCertificate.source == source)
    if cert_type:
        query = query.filter(ManagedCertificate.cert_type == cert_type)
    records = query.order_by(ManagedCertificate.created_at.desc(), ManagedCertificate.id.desc()).all()
    items = [manager.serialize_certificate(record) for record in records]
    summary = {
        "total": len(items),
        "valid": sum(1 for item in items if item["status"] == "valid"),
        "expiring": sum(1 for item in items if item["status"] == "expiring"),
        "expired": sum(1 for item in items if item["status"] == "expired"),
        "error": sum(1 for item in items if item["status"] == "error"),
        "auto_renew": sum(1 for item in items if item["auto_renew"]),
    }
    return {
        "items": items,
        "summary": summary,
        "certbot_available": manager.certbot_available(),
        "certbot_path": manager.certbot_path(),
        "certbot_live_dir": str(manager.CERTBOT_LIVE_DIR),
    }


@router.get("/config")
def certificate_config():
    return {
        "certbot_available": manager.certbot_available(),
        "certbot_path": manager.certbot_path(),
        "certbot_live_dir": str(manager.CERTBOT_LIVE_DIR),
        "acme_timeout_seconds": manager.ACME_TIMEOUT_SECONDS,
        "ip_note": "免费 ACME 证书通常只支持公网域名；IP 证书请使用导入/托管功能。",
        "runtime": manager.certbot_runtime_info(),
    }


@router.get("/certbot/status")
def certbot_status():
    """返回当前 Linux 发行版、包管理器与 certbot 状态。"""
    return manager.certbot_runtime_info()


@router.post("/certbot/install")
async def install_certbot(current: User = Depends(get_current_user)):
    """按当前 Linux 发行版自动安装 certbot（仅超级管理员）。"""
    if not current.is_superuser:
        raise HTTPException(status_code=403, detail="只有超级管理员可以安装系统软件包")
    try:
        result = await run_in_threadpool(manager.install_certbot)
    except manager.CertificateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "certbot 安装完成", **result}


@router.post("/import")
async def import_certificate(
    cert_file: UploadFile = File(...),
    key_file: Optional[UploadFile] = File(None),
    chain_file: Optional[UploadFile] = File(None),
    name: str = Form(""),
    monitor_host: str = Form(""),
    monitor_port: int = Form(443),
    warning_days: int = Form(30),
    notes: str = Form(""),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """导入证书和私钥；支持 IP SAN 证书，私钥可选（仅证书监控）。"""
    try:
        cert_data = await cert_file.read()
        key_data = await key_file.read() if key_file else None
        chain_data = await chain_file.read() if chain_file else None
    finally:
        await cert_file.close()
        if key_file:
            await key_file.close()
        if chain_file:
            await chain_file.close()
    if len(cert_data) > manager.MAX_CHAIN_BYTES:
        raise HTTPException(status_code=400, detail="证书文件过大")
    if key_data is not None and len(key_data) > manager.MAX_PEM_BYTES:
        raise HTTPException(status_code=400, detail="私钥文件过大")
    if chain_data is not None and len(chain_data) > manager.MAX_CHAIN_BYTES:
        raise HTTPException(status_code=400, detail="证书链文件过大")
    try:
        record = manager.import_certificate(
            db,
            cert_data=cert_data,
            key_data=key_data,
            chain_data=chain_data,
            name=name,
            monitor_host=monitor_host,
            monitor_port=monitor_port,
            warning_days=warning_days,
            notes=notes,
            created_by=current.username,
            source="import",
        )
    except manager.CertificateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "证书导入成功", "certificate": manager.serialize_certificate(record)}


@router.post("/generate")
def generate_certificate(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """自动生成自签名 PEM 证书（支持域名/IP SAN）并托管。"""
    common_name = str(payload.get("common_name") or "").strip()
    san = payload.get("san") or []
    if isinstance(san, str):
        san = [san]
    try:
        record = manager.generate_self_signed_certificate(
            db,
            name=str(payload.get("name") or "").strip(),
            common_name=common_name,
            san_values=san,
            valid_days=int(payload.get("valid_days") or 365),
            key_type=str(payload.get("key_type") or "rsa2048"),
            organization=str(payload.get("organization") or "").strip(),
            monitor_host=str(payload.get("monitor_host") or "").strip(),
            monitor_port=int(payload.get("monitor_port") or 443),
            warning_days=int(payload.get("warning_days") or 30),
            notes=str(payload.get("notes") or "").strip(),
            created_by=current.username,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=400, detail="证书参数格式不正确") from exc
    except manager.CertificateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "PEM 证书生成成功", "certificate": manager.serialize_certificate(record)}


@router.post("/apply")
async def apply_certificate(
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """使用 Let's Encrypt / certbot 申请免费证书（HTTP-01）。"""
    domains = payload.get("domains")
    if isinstance(domains, str):
        domains = [domains]
    if not isinstance(domains, list) or not domains:
        raise HTTPException(status_code=400, detail="请填写需要申请的域名")
    email = str(payload.get("email") or "").strip()
    method = str(payload.get("method") or "webroot").strip().lower()
    webroot = str(payload.get("webroot") or "").strip()
    staging = bool(payload.get("staging"))
    auto_renew = bool(payload.get("auto_renew", True))
    notes = str(payload.get("notes") or "").strip()[:2000]
    try:
        record = await run_in_threadpool(
            manager.apply_acme_certificate,
            db,
            domains=[str(item) for item in domains],
            email=email,
            method=method,
            webroot=webroot,
            staging=staging,
            auto_renew=auto_renew,
            notes=notes,
            created_by=current.username,
        )
    except manager.CertificateError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "免费证书申请成功", "certificate": manager.serialize_certificate(record)}


@router.get("/{certificate_id}")
def get_certificate(certificate_id: int, db: Session = Depends(get_db)):
    return manager.serialize_certificate(_get_certificate(db, certificate_id))


@router.put("/{certificate_id}")
def update_certificate(
    certificate_id: int,
    payload: Dict[str, Any],
    db: Session = Depends(get_db),
):
    record = _get_certificate(db, certificate_id)
    if "name" in payload:
        name = str(payload.get("name") or "").strip()
        if not name:
            raise HTTPException(status_code=400, detail="证书名称不能为空")
        record.name = name[:255]
    if "monitor_enabled" in payload:
        record.monitor_enabled = bool(payload.get("monitor_enabled"))
    if "monitor_host" in payload:
        record.monitor_host = str(payload.get("monitor_host") or "").strip()[:255]
    if "monitor_port" in payload:
        try:
            port = int(payload.get("monitor_port") or 443)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="监控端口必须是整数") from None
        if not 1 <= port <= 65535:
            raise HTTPException(status_code=400, detail="监控端口必须在 1~65535 之间")
        record.monitor_port = port
    if "warning_days" in payload:
        try:
            days = int(payload.get("warning_days") or 30)
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="提前告警天数必须是整数") from None
        if not 1 <= days <= 3650:
            raise HTTPException(status_code=400, detail="提前告警天数必须在 1~3650 之间")
        record.warning_days = days
    if "auto_renew" in payload:
        if record.source != "acme" and payload.get("auto_renew"):
            raise HTTPException(status_code=400, detail="只有 ACME 证书支持自动续期")
        record.auto_renew = bool(payload.get("auto_renew"))
    if "notes" in payload:
        record.notes = str(payload.get("notes") or "")[:2000]
    db.commit()
    db.refresh(record)
    return {"message": "证书设置已保存", "certificate": manager.serialize_certificate(record)}


@router.post("/{certificate_id}/refresh")
async def refresh_certificate(certificate_id: int, db: Session = Depends(get_db)):
    record = _get_certificate(db, certificate_id)
    try:
        record = await manager.refresh_certificate(db, record)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"证书监控失败: {exc}") from exc
    return {"message": "证书状态已刷新", "certificate": manager.serialize_certificate(record)}


@router.post("/refresh")
async def refresh_all_certificates(db: Session = Depends(get_db)):
    result = await manager.refresh_all(db)
    return {"message": "证书监控已刷新", **result}


@router.post("/{certificate_id}/renew")
async def renew_certificate(certificate_id: int, db: Session = Depends(get_db)):
    record = _get_certificate(db, certificate_id)
    try:
        record = await run_in_threadpool(manager.renew_acme_certificate, db, record)
    except manager.CertificateError as exc:
        record.last_renew_error = str(exc)[:2000]
        db.commit()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {"message": "证书续期成功", "certificate": manager.serialize_certificate(record)}


@router.get("/{certificate_id}/download")
def download_certificate(
    certificate_id: int,
    kind: str = Query("cert", pattern="^(cert|key|chain|fullchain)$"),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    record = _get_certificate(db, certificate_id)
    if kind == "key" and not _is_admin(current):
        raise HTTPException(status_code=403, detail="只有超级管理员可以下载私钥")
    if kind == "fullchain":
        content = manager.fullchain_text(record)
        if not content:
            raise HTTPException(status_code=404, detail="证书文件不存在")
        return Response(
            content=content,
            media_type="application/x-pem-file",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(record.name)}-fullchain.pem"},
        )
    path = manager.file_for_download(record, kind)
    if not path or not path.is_file():
        raise HTTPException(status_code=404, detail="证书文件不存在")
    suffix = {"cert": "cert.pem", "key": "privkey.pem", "chain": "chain.pem"}[kind]
    content = path.read_bytes()
    return Response(
        content=content,
        media_type="application/x-pem-file",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{quote(record.name)}-{suffix}"},
    )


@router.delete("/{certificate_id}")
def delete_certificate(certificate_id: int, db: Session = Depends(get_db)):
    record = _get_certificate(db, certificate_id)
    directory = manager.CERT_ROOT / str(record.id)
    try:
        if int(settings_service.get_value(db, "web_ssl_certificate_id") or 0) == record.id:
            settings_service.save(db, {"web_ssl_certificate_id": 0})
    except Exception:  # noqa: BLE001
        pass
    db.delete(record)
    db.commit()
    try:
        shutil.rmtree(directory, ignore_errors=True)
    except OSError:
        pass
    return {"message": "证书已删除"}
