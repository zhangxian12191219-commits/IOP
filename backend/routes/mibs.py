"""MIB 文件导入、解析、对象查询与采集 OID 推荐"""
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, UploadFile
from sqlalchemy import or_
from sqlalchemy.orm import Session

from ..models.database import get_db
from ..models.mib import MibFile, MibObject
from ..models.models import Device
from ..models.user import User
from ..services import audit, asset_scope
from ..services.auth import get_current_user, has_permission
from ..services import mib_parser, mib_templates, standard_mibs, builtin_mibs, mib_auto, mib_online, ai_ops
from ..services import license_manager
from ..services.cache import invalidate_all

router = APIRouter(prefix="/api/mibs", tags=["MIB 管理"])

logger = logging.getLogger(__name__)

MAX_FILE_MB = 5
MAX_OBJECTS = 8000

# 内置/标准库不是针对特定型号的厂商私有库，统一标注为「通用」
STANDARD_MIB_VENDOR = "标准库"
GENERIC_DEVICE_MODEL = "通用"


def _decode(content: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


def _mib_to_dict(mib: MibFile) -> dict:
    return {
        "id": mib.id,
        "filename": mib.filename,
        "module_name": mib.module_name,
        "size": mib.size,
        "object_count": mib.object_count,
        "readable_count": mib.readable_count,
        "unresolved_count": mib.unresolved_count,
        "categories": mib.categories or [],
        "imports": mib.imports or [],
        "note": mib.note,
        "is_builtin": bool(mib.is_builtin),
        "builtin_key": mib.builtin_key,
        "device_category": mib.device_category,
        "vendor": mib.vendor,
        "device_model": mib.device_model,
        "created_at": mib.created_at.isoformat() if mib.created_at else None,
    }


def _object_to_dict(obj: MibObject) -> dict:
    return {
        "id": obj.id,
        "name": obj.name,
        "oid": obj.oid,
        "syntax": obj.syntax,
        "access": obj.access,
        "status": obj.status,
        "description": obj.description,
        "category": obj.category,
        "score": obj.score,
    }


@router.post("/upload")
async def upload_mibs(
    files: List[UploadFile] = File(..., description="一个或多个 MIB 文件"),
    vendor: str = Form(..., description="厂商"),
    device_model: str = Form(..., description="设备型号"),
    db: Session = Depends(get_db),
):
    """上传并解析 MIB 文件（支持一次多个，自动解析标准依赖）

    同厂商不同型号的 MIB 可能不同，因此每个文件都必须归属到厂商 + 设备型号；
    一次上传多个文件时，该厂商/型号会应用到本批全部文件。
    """
    vendor = (vendor or "").strip()
    device_model = (device_model or "").strip()
    if not vendor:
        raise HTTPException(status_code=400, detail="请填写厂商，MIB 需按厂商 + 设备型号归档")
    if not device_model:
        raise HTTPException(status_code=400, detail="请填写设备型号，同一厂商不同型号的 MIB 可能不同")
    if len(vendor) > 60:
        raise HTTPException(status_code=400, detail="厂商名称过长（最多 60 个字符）")
    if len(device_model) > 120:
        raise HTTPException(status_code=400, detail="设备型号过长（最多 120 个字符）")

    if not files:
        raise HTTPException(status_code=400, detail="请选择 MIB 文件")
    if len(files) > 10:
        raise HTTPException(status_code=400, detail="一次最多上传 10 个文件")

    errors = []
    contents = []
    for upload in files:
        filename = (upload.filename or "unknown.mib").strip()
        try:
            content = await upload.read()
            if len(content) > MAX_FILE_MB * 1024 * 1024:
                raise ValueError(f"文件超过 {MAX_FILE_MB}MB")
            text = _decode(content)
            if "DEFINITIONS" not in text.upper():
                raise ValueError("不是有效的 MIB 文件（缺少 DEFINITIONS）")
            contents.append({"filename": filename, "text": text, "size": len(content)})
        except Exception as exc:  # noqa: BLE001
            errors.append({"filename": filename, "error": str(exc)})

    if not contents:
        raise HTTPException(
            status_code=400,
            detail="；".join(f"{e['filename']}: {e['error']}" for e in errors),
        )

    # ---- 已知符号：标准库 + mibs/standard 目录 + 数据库已导入对象 ----
    known = dict(standard_mibs.symbol_map())
    try:
        known.update(standard_mibs.load_standard_dir_symbols())
    except Exception as exc:  # noqa: BLE001
        logger.warning("加载标准 MIB 目录失败: %s", exc)
    for obj in db.query(MibObject).all():
        if obj.name and obj.oid:
            known.setdefault(obj.name, obj.oid)

    # ---- 第一轮解析：收集同批文件的符号 ----
    records = []
    batch_symbols: dict = {}
    for item in contents:
        try:
            parsed = mib_parser.parse_mib(
                item["text"], item["filename"], known_oids=known
            )
        except Exception as exc:  # noqa: BLE001
            errors.append({"filename": item["filename"], "error": str(exc)})
            continue
        for obj in parsed.get("objects", []):
            if obj.get("name") and obj.get("oid"):
                batch_symbols.setdefault(obj["name"], obj["oid"])
        records.append({**item, "parsed": parsed})

    # ---- 第二轮：用「标准库 + 同批符号」重新解析仍有未解析引用的文件 ----
    merged = dict(known)
    merged.update(batch_symbols)
    for record in records:
        if record["parsed"].get("unresolved", 0) > 0:
            try:
                better = mib_parser.parse_mib(
                    record["text"], record["filename"], known_oids=merged
                )
                if better["unresolved"] < record["parsed"]["unresolved"]:
                    record["parsed"] = better
            except Exception:  # noqa: BLE001
                pass

    existing_modules = {
        (m.module_name or "").lower()
        for m in db.query(MibFile).all()
    }
    batch_modules = {
        (record["parsed"].get("module") or "").lower() for record in records
    }
    known_module_names = {m.lower() for m in standard_mibs.known_modules()}

    results = []
    for record in records:
        filename = record["filename"]
        parsed = record["parsed"]
        try:
            imports = parsed.get("imports") or []
            missing_imports = [
                module for module in imports
                if module.lower() not in existing_modules
                and module.lower() not in batch_modules
                and module.lower() not in known_module_names
            ]
            resolved_imports = [m for m in imports if m not in missing_imports]

            mib = MibFile(
                filename=filename[:255],
                module_name=(parsed["module"] or filename)[:120],
                size=record["size"],
                object_count=parsed["total"],
                readable_count=parsed["readable"],
                unresolved_count=parsed["unresolved"],
                categories=parsed["categories"],
                imports=imports,
                vendor=vendor,
                device_model=device_model,
                note=(
                    f"依赖自动解析：{len(resolved_imports)}/{len(imports)}"
                    + (f"；缺少依赖：{', '.join(missing_imports[:8])}" if missing_imports else "")
                ),
            )
            db.add(mib)
            db.flush()

            for item in parsed["objects"][:MAX_OBJECTS]:
                db.add(MibObject(
                    mib_id=mib.id,
                    name=(item["name"] or "")[:160],
                    oid=(item["oid"] or "")[:200],
                    syntax=(item["syntax"] or "")[:160],
                    access=(item["access"] or "")[:40],
                    status=(item["status"] or "")[:40],
                    description=item["description"] or "",
                    category=(item["category"] or "")[:30],
                    score=item["score"] or 0,
                ))
            db.commit()
            db.refresh(mib)

            results.append({
                **_mib_to_dict(mib),
                "recommendations": mib_parser.recommend(parsed["objects"]),
                "auto_map": mib_parser.guess_metric_map(parsed["objects"]),
                "missing_imports": missing_imports,
                "resolved_imports": resolved_imports,
                "dependencies_resolved": len(resolved_imports),
            })
            logger.info(
                "MIB 解析成功 %s / %s：%s 个对象，未解析 %s，缺少依赖 %s",
                filename, mib.module_name, mib.object_count,
                mib.unresolved_count, missing_imports,
            )
        except Exception as exc:  # noqa: BLE001
            db.rollback()
            logger.warning("MIB 解析失败 %s: %s", filename, exc)
            errors.append({"filename": filename, "error": str(exc)})

    if not results and errors:
        raise HTTPException(
            status_code=400,
            detail="；".join(f"{e['filename']}: {e['error']}" for e in errors),
        )

    return {
        "imported": results,
        "errors": errors,
        "total": len(results),
        "standard_modules_loaded": len(known_module_names),
    }


@router.post("/import-standard")
def import_standard_library(db: Session = Depends(get_db)):
    """导入内置标准 MIB 符号库（可浏览、可复制 OID、用于依赖解析）"""
    existing = (
        db.query(MibFile)
        .filter(MibFile.filename == "STANDARD-MIB-LIBRARY")
        .first()
    )
    if existing:
        # 兼容旧数据：标准库统一标注「标准库 / 通用」，便于列表按厂商+型号筛选
        if not existing.vendor or not existing.device_model:
            existing.vendor = existing.vendor or STANDARD_MIB_VENDOR
            existing.device_model = existing.device_model or GENERIC_DEVICE_MODEL
            db.commit()
        return {
            "imported": False,
            "mib_id": existing.id,
            "module_name": existing.module_name,
            "object_count": existing.object_count,
            "vendor": existing.vendor,
            "device_model": existing.device_model,
            "message": "标准 MIB 库已导入",
        }

    objects = standard_mibs.library_objects()
    # 同名对象去重（标准库中个别名称跨模块重复）
    seen = set()
    unique = []
    for item in objects:
        if item["name"] in seen:
            continue
        seen.add(item["name"])
        unique.append(item)

    mib = MibFile(
        filename="STANDARD-MIB-LIBRARY",
        module_name="STANDARD-MIB-LIBRARY",
        size=0,
        object_count=len(unique),
        readable_count=len(unique),
        unresolved_count=0,
        categories=[],
        imports=[],
        vendor=STANDARD_MIB_VENDOR,
        device_model=GENERIC_DEVICE_MODEL,
        note="内置标准 MIB 符号库（SNMPv2-MIB / IF-MIB / HOST-RESOURCES-MIB / ENTITY-MIB / ENTITY-SENSORS-MIB 等）",
    )
    db.add(mib)
    db.flush()
    for item in unique:
        db.add(MibObject(
            mib_id=mib.id,
            name=item["name"][:160],
            oid=item["oid"][:200],
            syntax=item["syntax"],
            access=item["access"],
            status=item["status"],
            description=item["description"],
            category=item["category"],
            score=0,
        ))
    db.commit()
    db.refresh(mib)
    logger.info("已导入内置标准 MIB 库：%s 个对象", len(unique))
    return {
        "imported": True,
        "mib_id": mib.id,
        "module_name": mib.module_name,
        "object_count": mib.object_count,
        "vendor": mib.vendor,
        "device_model": mib.device_model,
        "message": f"标准 MIB 库导入成功（{mib.object_count} 个对象）",
    }


@router.get("/builtin/catalog")
def builtin_catalog(db: Session = Depends(get_db)):
    """内置厂商 MIB 对象库目录（按交换机/服务器/存储分类）。"""
    imported = {
        row.builtin_key: row.id
        for row in db.query(MibFile).filter(MibFile.is_builtin == True).all()
        if row.builtin_key
    }
    items = []
    for item in builtin_mibs.catalog():
        items.append({**item, "imported": item["key"] in imported,
                      "mib_id": imported.get(item["key"])})
    return {
        "items": items,
        "total": len(items),
        "imported": len(imported),
        "categories": [
            {"value": "switch", "label": "交换机"},
            {"value": "server", "label": "服务器"},
            {"value": "storage", "label": "存储"},
        ],
    }


def _sync_builtin_mib_metadata(db: Session) -> int:
    """为内置厂商库补齐厂商/型号命名。

    内置库是厂商通用对象库（非特定型号），统一标注设备型号为「通用」，
    厂商优先取内置目录；只补空值，不覆盖用户已填写的厂商/型号。
    """
    catalog = {item["key"]: item for item in builtin_mibs.catalog()}
    updated = 0
    for mib in db.query(MibFile).filter(MibFile.is_builtin == True).all():  # noqa: E712
        meta = catalog.get(mib.builtin_key or "")
        changed = False
        if not (mib.vendor or "").strip() and meta and meta.get("vendor"):
            mib.vendor = str(meta["vendor"])[:60]
            changed = True
        desired_model = str((meta or {}).get("device_model") or "").strip()
        if desired_model and mib.device_model != desired_model:
            mib.device_model = desired_model[:120]
            changed = True
        elif not (mib.device_model or "").strip():
            mib.device_model = GENERIC_DEVICE_MODEL
            changed = True
        if changed:
            updated += 1
    if updated:
        db.commit()
    return updated


@router.post("/builtin/import")
def import_builtin_library(
    payload: Optional[dict] = Body(default=None),
    db: Session = Depends(get_db),
):
    """补齐内置厂商 MIB 库；payload 可传 {"keys": [...]} 或 {"all": true}。"""
    payload = payload or {}
    keys = payload.get("keys")
    if payload.get("all") or not keys:
        keys = None
    elif not isinstance(keys, list):
        raise HTTPException(status_code=400, detail="keys 必须是数组")
    result = builtin_mibs.ensure_builtin_mibs(
        db, only_keys=[str(k) for k in keys] if keys else None
    )
    metadata_synced = _sync_builtin_mib_metadata(db)
    return {
        **result,
        "metadata_synced": metadata_synced,
        "message": f"已导入 {result['total']} 个内置 MIB 库",
    }


@router.post("/builtin/cleanup")
def cleanup_builtin_library(db: Session = Depends(get_db)):
    """删除当前内置目录之外、无法完整采集的旧内置 MIB 库。"""
    result = builtin_mibs.cleanup_obsolete_builtins(db)
    return {
        **result,
        "message": f"已清理 {result['deleted']} 个无用内置 MIB 库",
    }


@router.get("/templates")
def list_templates(
    vendor: str = "",
    model: str = "",
    device_type: str = "",
    device_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """MIB 模板列表；传 vendor/model 时返回匹配模板与解析预览"""
    device = None
    if device_id:
        device = db.query(Device).filter(Device.id == device_id).first()
        if device:
            vendor = vendor or device.vendor or ""
            model = model or device.model or ""
            device_type = device_type or device.device_type or ""

    matched = mib_templates.match_template(vendor, model, device_type)
    preview = None
    if matched:
        preview = mib_templates.resolve_template(db, matched, device=device)

    templates = []
    for template in mib_templates.list_templates():
        templates.append({
            "id": template["id"],
            "name": template["name"],
            "vendor_keys": template.get("vendor_keys") or [],
            "device_types": template.get("device_types") or [],
            "mib_modules": template.get("mib_modules") or [],
            "matched": bool(matched and template["id"] == matched["id"]),
        })
    return {
        "templates": templates,
        "match": preview,
        "matched_template_id": matched["id"] if matched else None,
    }


@router.get("/templates/match")
def match_template(
    vendor: str = "",
    model: str = "",
    device_type: str = "",
    device_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """按厂商/型号匹配模板并返回可套用的 OID 预览"""
    device = None
    if device_id:
        device = db.query(Device).filter(Device.id == device_id).first()
        if not device:
            raise HTTPException(status_code=404, detail="设备不存在")
        vendor = vendor or device.vendor or ""
        model = model or device.model or ""
        device_type = device_type or device.device_type or ""

    matched = mib_templates.match_template(vendor, model, device_type)
    if not matched:
        return {"matched": False, "template": None, "preview": None}
    preview = mib_templates.resolve_template(db, matched, device=device)
    return {
        "matched": True,
        "template": {
            "id": matched["id"],
            "name": matched["name"],
            "mib_modules": matched.get("mib_modules") or [],
        },
        "preview": preview,
    }


@router.post("/templates/apply")
def apply_template(payload: dict = Body(...), db: Session = Depends(get_db)):
    """按厂商型号自动套用 MIB 模板到设备

    请求体：
      {"device_id": 1}                                  # 自动匹配
      {"device_ids": [1,2,3], "template_id": "huawei-vrp", "overwrite": false}
    """
    device_ids = payload.get("device_ids") or []
    if payload.get("device_id"):
        device_ids = [payload["device_id"]]
    try:
        device_ids = [int(i) for i in device_ids]
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="设备 ID 不合法") from None
    if not device_ids:
        raise HTTPException(status_code=400, detail="请选择设备")

    overwrite = bool(payload.get("overwrite"))
    template_id = payload.get("template_id")
    explicit_template = None
    if template_id:
        explicit_template = next(
            (t for t in mib_templates.list_templates() if t["id"] == template_id),
            None,
        )
        if not explicit_template:
            raise HTTPException(status_code=400, detail="模板不存在")

    devices = db.query(Device).filter(Device.id.in_(device_ids)).all()
    applied = []
    skipped = []
    for device in devices:
        template = explicit_template or mib_templates.match_template(
            device.vendor or "", device.model or "", device.device_type or ""
        )
        if not template:
            skipped.append({"device_id": device.id, "device_name": device.name,
                            "reason": "未匹配到厂商/型号模板"})
            continue

        preview = mib_templates.resolve_template(db, template, device=device)
        changed = []
        if preview.get("mib_id") and (overwrite or not device.mib_id):
            device.mib_id = preview["mib_id"]
            changed.append("mib_id")

        custom_oids = dict(device.custom_oids or {})
        for metric, info in (preview.get("matched_metrics") or {}).items():
            if overwrite or not custom_oids.get(metric):
                custom_oids[metric] = info["oid"]
                changed.append(f"custom_oids.{metric}")
        device.custom_oids = custom_oids

        custom_metrics = list(device.custom_metrics or [])
        existing = {item.get("key"): item for item in custom_metrics if isinstance(item, dict)}
        for item in preview.get("custom_metrics") or []:
            key = item.get("key")
            if not key:
                continue
            if key in existing and not overwrite:
                continue
            existing[key] = {
                "key": key, "name": item.get("name") or key, "oid": item["oid"],
                "unit": item.get("unit") or "", "scale": item.get("scale") or 1,
                "aggregate": item.get("aggregate") or "max",
            }
            changed.append(f"custom_metrics.{key}")
        device.custom_metrics = list(existing.values())

        device.updated_at = datetime.utcnow()
        applied.append({
            "device_id": device.id,
            "device_name": device.name,
            "template_id": template["id"],
            "template_name": template["name"],
            "changed": changed,
            "missing_metrics": preview.get("missing_metrics") or [],
            "missing_custom_metrics": preview.get("missing_custom_metrics") or [],
            "missing_mibs": preview.get("missing_mibs") or [],
        })

    db.commit()
    invalidate_all()
    return {"applied": applied, "skipped": skipped, "total": len(applied)}


@router.get("")
def list_mibs(db: Session = Depends(get_db)):
    """MIB 文件列表（内置库如缺少型号命名会自动补齐）"""
    items = db.query(MibFile).order_by(MibFile.created_at.desc()).all()
    # 启动时自动创建/历史遗留的内置库可能没有 device_model：首次列表加载时补齐
    if any(m.is_builtin and not (m.device_model or "").strip() for m in items):
        if _sync_builtin_mib_metadata(db):
            items = db.query(MibFile).order_by(MibFile.created_at.desc()).all()
    return {"total": len(items), "items": [_mib_to_dict(m) for m in items]}


@router.post("/auto-match")
async def auto_match(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    """设备 MIB 自动识别：SNMP 指纹 + 候选库 + OID 实测校验。

    请求：{"device_id": 1, "apply": false}
    apply=true 时自动绑定最佳且至少有一个指标通过校验的候选。
    """
    try:
        device_id = int(payload.get("device_id") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="设备 ID 不合法") from None
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    asset_scope.require_device_access(db, request, device)
    result = await mib_auto.analyze_device(db, device)
    online_meta = None
    if payload.get("online") and not result.get("candidates"):
        # 只在本地没有候选时联网补充，避免每次匹配都访问外网。
        online_meta = mib_online.fetch_and_import(
            db,
            result.get("device", {}).get("vendor") or device.vendor or "",
            result.get("device", {}).get("model") or device.model or "",
            result.get("snmp", {}).get("sys_descr") or device.description or "",
        )
        if online_meta.get("imported"):
            try:
                db.commit()
                result = await mib_auto.analyze_device(db, device)
                audit.record(
                    db, request, module="assets", action="create",
                    target_type="mib_online", target_id=device.id, target_name=device.name,
                    after={"source": online_meta.get("source"), "imported": online_meta.get("imported")},
                    message=f"设备 {device.name} 联网获取并导入 MIB",
                )
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                online_meta["errors"] = list(online_meta.get("errors") or []) + [str(exc)[:240]]
        result["online"] = online_meta
        if online_meta.get("imported"):
            result["message"] = "已联网获取 MIB 并完成重新匹配，请查看候选和验证结果"
        elif online_meta.get("errors"):
            result["message"] = f"本地无候选，联网获取未成功：{online_meta['errors'][0]}"
    if payload.get("ai"):
        ai_info: Dict[str, Any] = {"configured": False}
        try:
            public_ai = ai_ops.public_config(ai_ops.get_config(db))
            ai_info["configured"] = bool(public_ai.get("configured"))
            if not public_ai.get("configured"):
                ai_info["error"] = "外部 AI 模型未配置，已跳过 AI 辅助匹配"
            elif not license_manager.has_feature("ai"):
                ai_info["error"] = "当前授权未包含 AI 运维功能，已跳过 AI 辅助匹配"
            elif not result.get("candidates"):
                ai_info["error"] = "没有候选 MIB，AI 无法进行候选排序"
            else:
                recommendation = ai_ops.recommend_mib(
                    db,
                    result.get("device") or {},
                    result.get("candidates") or [],
                )
                ai_info.update(recommendation)
                ai_mib_id = int(recommendation.get("recommended_mib_id"))
                recommended = next(
                    (item for item in result.get("candidates") or [] if int(item.get("mib_id")) == ai_mib_id),
                    None,
                )
                if recommended:
                    recommended["ai_recommended"] = True
                    result["candidates"] = [recommended] + [
                        item for item in result.get("candidates") or [] if item is not recommended
                    ]
                    result["best"] = recommended
                    result["message"] = "AI 已完成候选排序；绑定仍需通过 SNMP OID 验证"
        except Exception as exc:  # noqa: BLE001
            ai_info["error"] = str(exc)[:300]
        result["ai"] = ai_info
    applied = None
    if payload.get("apply"):
        best = result.get("best")
        if best and best.get("valid_count", 0) > 0 and best.get("confidence", 0) >= 45:
            try:
                applied = mib_auto.bind_device(
                    db, device, int(best["mib_id"]), best.get("metrics") or [],
                    fingerprint=result.get("fingerprint") or "",
                )
                db.commit()
                audit.record(
                    db, request, module="assets", action="update",
                    target_type="mib_auto", target_id=device.id, target_name=device.name,
                    after={"mib_id": best["mib_id"], "valid_count": best["valid_count"]},
                    message=f"设备 {device.name} 自动匹配并归类 MIB",
                )
            except ValueError as exc:
                db.rollback()
                result["apply_error"] = str(exc)
        else:
            result["apply_error"] = "最佳候选没有通过验证的指标，未自动绑定"
    result["applied"] = applied
    return result


@router.post("/auto-bind")
def auto_bind(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
    current: User = Depends(get_current_user),
):
    """确认自动识别的 MIB，并将通过验证的 OID 写入设备指标映射。"""
    try:
        device_id = int(payload.get("device_id") or 0)
        mib_id = int(payload.get("mib_id") or 0)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="设备或 MIB ID 不合法") from None
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail="设备不存在")
    if not current.is_superuser and not has_permission(current, "mib:edit"):
        raise HTTPException(status_code=403, detail="需要资产编辑权限才能应用 MIB")
    asset_scope.require_device_access(db, request, device)
    metrics = payload.get("metrics") if isinstance(payload.get("metrics"), list) else []
    try:
        result = mib_auto.bind_device(
            db, device, mib_id, metrics,
            fingerprint=str(payload.get("fingerprint") or ""),
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    db.commit()
    audit.record(
        db, request, module="assets", action="update",
        target_type="mib_auto", target_id=device.id, target_name=device.name,
        after={"mib_id": mib_id, "metrics": result["metrics"]},
        message=f"设备 {device.name} 应用自动匹配 MIB 并归类",
    )
    return result


@router.get("/{mib_id}")
def get_mib(mib_id: int, db: Session = Depends(get_db)):
    """MIB 详情（含推荐 OID）"""
    mib = db.query(MibFile).filter(MibFile.id == mib_id).first()
    if not mib:
        raise HTTPException(status_code=404, detail="MIB 不存在")

    objects = (
        db.query(MibObject)
        .filter(MibObject.mib_id == mib_id)
        .order_by(MibObject.score.desc(), MibObject.name)
        .all()
    )
    object_dicts = [_object_to_dict(o) for o in objects]
    return {
        **_mib_to_dict(mib),
        "recommendations": mib_parser.recommend(object_dicts),
        "auto_map": mib_parser.guess_metric_map(object_dicts),
    }


@router.get("/{mib_id}/objects")
def list_mib_objects(
    mib_id: int,
    category: Optional[str] = None,
    keyword: Optional[str] = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """分页查询 MIB 对象，可按类别/关键字过滤"""
    if not db.query(MibFile).filter(MibFile.id == mib_id).first():
        raise HTTPException(status_code=404, detail="MIB 不存在")

    query = db.query(MibObject).filter(MibObject.mib_id == mib_id)
    if category:
        query = query.filter(MibObject.category == category)
    if keyword:
        like = f"%{keyword}%"
        query = query.filter(or_(
            MibObject.name.like(like),
            MibObject.oid.like(like),
            MibObject.description.like(like),
        ))

    total = query.count()
    items = (
        query.order_by(MibObject.score.desc(), MibObject.oid)
        .offset((page - 1) * size)
        .limit(size)
        .all()
    )
    return {
        "total": total,
        "page": page,
        "size": size,
        "items": [_object_to_dict(o) for o in items],
    }


@router.get("/{mib_id}/recommendations")
def get_recommendations(mib_id: int, db: Session = Depends(get_db)):
    """按指标类别返回推荐 OID（cpu/memory/temperature/power/interface）"""
    mib = db.query(MibFile).filter(MibFile.id == mib_id).first()
    if not mib:
        raise HTTPException(status_code=404, detail="MIB 不存在")

    objects = (
        db.query(MibObject)
        .filter(MibObject.mib_id == mib_id)
        .order_by(MibObject.score.desc())
        .all()
    )
    object_dicts = [_object_to_dict(o) for o in objects]
    return {
        "mib_id": mib_id,
        "module_name": mib.module_name,
        "recommendations": mib_parser.recommend(object_dicts),
        "auto_map": mib_parser.guess_metric_map(object_dicts),
        "labels": mib_parser.CATEGORY_LABELS,
    }


@router.delete("/batch/delete")
def batch_delete_mibs(
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    """批量删除 MIB，并解除设备上的引用。"""
    raw_ids = payload.get("ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        raise HTTPException(status_code=400, detail="请选择 MIB")
    try:
        ids = list(dict.fromkeys(int(item) for item in raw_ids if int(item) > 0))[:500]
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="MIB ID 不合法") from None
    if not ids:
        raise HTTPException(status_code=400, detail="请选择 MIB")
    mibs = db.query(MibFile).filter(MibFile.id.in_(ids)).all()
    found = {item.id for item in mibs}
    if not found:
        raise HTTPException(status_code=404, detail="MIB 不存在")
    affected = db.query(Device).filter(Device.mib_id.in_(ids)).all()
    for device in affected:
        device.mib_id = None
    for mib in mibs:
        db.delete(mib)
    audit.record(
        db, request, module="assets", action="delete",
        target_type="mib", target_name="批量删除 MIB",
        after={"mib_ids": sorted(found), "devices_unbound": len(affected)},
        message=f"批量删除 {len(mibs)} 个 MIB，解除 {len(affected)} 台设备引用",
    )
    db.commit()
    invalidate_all()
    return {
        "deleted": len(mibs),
        "devices_unbound": len(affected),
        "message": f"已删除 {len(mibs)} 个 MIB，解除 {len(affected)} 台设备引用",
    }


@router.post("/{mib_id}/devices/assign")
def assign_mib_devices(
    mib_id: int,
    request: Request,
    payload: Dict[str, Any] = Body(...),
    db: Session = Depends(get_db),
):
    """把 MIB 批量引用到资产设备（设置 Device.mib_id）。"""
    mib = db.query(MibFile).filter(MibFile.id == mib_id).first()
    if not mib:
        raise HTTPException(status_code=404, detail="MIB 不存在")
    raw_ids = payload.get("device_ids")
    if not isinstance(raw_ids, list) or not raw_ids:
        raise HTTPException(status_code=400, detail="请选择要引用的设备")
    try:
        device_ids = list(dict.fromkeys(int(item) for item in raw_ids))[:500]
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="设备 ID 不合法") from None
    devices = (
        asset_scope.scope_device_query(db, request, db.query(Device))
        .filter(Device.id.in_(device_ids))
        .all()
    )
    found = {item.id for item in devices}
    missing = [item for item in device_ids if item not in found]
    if missing:
        raise HTTPException(status_code=403, detail="部分设备不存在或无权访问")
    for device in devices:
        device.mib_id = mib.id
        device.updated_at = datetime.utcnow()
        # 批量引用时同步套用厂商采集模板，避免只绑定 MIB 名称却没有任何采集 OID
        template = mib_templates.match_template(
            device.vendor or "", device.model or "", device.device_type or ""
        )
        if template:
            preview = mib_templates.resolve_template(db, template, device=device)
            custom_oids = dict(device.custom_oids or {})
            for metric, info in (preview.get("matched_metrics") or {}).items():
                if not custom_oids.get(metric):
                    custom_oids[metric] = info["oid"]
            device.custom_oids = custom_oids
            custom_metrics = list(device.custom_metrics or [])
            existing = {item.get("key"): item for item in custom_metrics if isinstance(item, dict)}
            for item in preview.get("custom_metrics") or []:
                key = item.get("key")
                if not key or key in existing:
                    continue
                existing[key] = {
                    "key": key, "name": item.get("name") or key, "oid": item["oid"],
                    "unit": item.get("unit") or "", "scale": item.get("scale") or 1,
                    "aggregate": item.get("aggregate") or "max",
                }
            device.custom_metrics = list(existing.values())
    audit.record(
        db, request, module="assets", action="update",
        target_type="mib", target_id=mib.id, target_name=mib.module_name or mib.filename,
        after={"assigned_device_ids": device_ids},
        message=f"MIB {mib.module_name or mib.filename} 批量引用设备 {len(devices)} 台",
    )
    db.commit()
    invalidate_all()
    return {
        "message": f"已将 MIB 引用到 {len(devices)} 台设备",
        "assigned": len(devices),
        "mib_id": mib.id,
    }


@router.delete("/{mib_id}")
def delete_mib(mib_id: int, db: Session = Depends(get_db)):
    """删除 MIB（同时解除设备上的引用，自定义 OID 保留）"""
    mib = db.query(MibFile).filter(MibFile.id == mib_id).first()
    if not mib:
        raise HTTPException(status_code=404, detail="MIB 不存在")

    affected = (
        db.query(Device)
        .filter(Device.mib_id == mib_id)
        .all()
    )
    for device in affected:
        device.mib_id = None

    db.delete(mib)
    db.commit()
    return {"message": "MIB 已删除", "devices_unbound": len(affected)}
