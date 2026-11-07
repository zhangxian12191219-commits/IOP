"""按设备厂商从公开 MIB 库补充 MIB 文件。

安全边界：
- 只访问固定的 GitHub API / raw 域名，不接受用户传入 URL；
- 限制单文件大小、单次下载数量和超时；
- 下载内容仍走现有 MIB 解析器，不执行任何代码；
- 仅在本地没有候选时由用户主动触发，失败不影响本地匹配。
"""
from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlparse

from sqlalchemy.orm import Session

from ..models.mib import MibFile, MibObject
from . import mib_parser, standard_mibs

SOURCE_REPO = "librenms/librenms"
SOURCE_BRANCH = "master"
SOURCE_LABEL = "LibreNMS 公共 MIB 库"
MAX_FILES = 6
MAX_DEPENDENCIES = 24
MAX_BYTES = 5 * 1024 * 1024
MAX_TOTAL_BYTES = 40 * 1024 * 1024
TIMEOUT = 10
MAX_OBJECTS = 8000

API_BASE = f"https://api.github.com/repos/{SOURCE_REPO}/contents/mibs"
RAW_BASE = f"https://raw.githubusercontent.com/{SOURCE_REPO}/{SOURCE_BRANCH}/mibs"
ALLOWED_HOSTS = {"api.github.com", "raw.githubusercontent.com", "github.com", "objects.githubusercontent.com"}

VENDOR_DIRS = {
    "huawei": "huawei", "h3c": "comware", "comware": "comware",
    "cisco": "cisco", "ruijie": "ruijie", "fortinet": "fortinet",
    "dell": "dell", "hpe": "hp", "hp": "hp", "juniper": "juniper",
    "aruba": "arubaos", "zte": "zte",
}
VENDOR_ALIASES = {
    "华为": "huawei", "华三": "h3c", "锐捷": "ruijie", "飞塔": "fortinet",
    "戴尔": "dell", "联想": "lenovo", "浪潮": "inspur", "中兴": "zte",
    "烽火": "fiberhome", "深信服": "sangfor", "天融信": "topsec",
    "山石": "hillstone", "神州数码": "digitalchina",
}
CATEGORY_WORDS = (
    "entity", "system", "cpu", "memory", "resource", "device", "health",
    "environment", "env", "power", "fan", "temperature", "interface",
)


def _vendor_key(vendor: str, sys_descr: str = "") -> str:
    text = f"{vendor} {sys_descr}".lower()
    for alias, key in VENDOR_ALIASES.items():
        if alias in text:
            return key
    return re.sub(r"[^a-z0-9]+", "", text.split()[0] if text.split() else "")


def _safe_get(url: str, *, accept: str = "application/vnd.github+json") -> bytes:
    parsed = urlparse(url)
    if parsed.scheme != "https" or parsed.hostname not in ALLOWED_HOSTS:
        raise ValueError("MIB 在线来源不在白名单")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "SNMP-NMS-MIB-Online/1.0", "Accept": accept},
    )
    last_error: Optional[Exception] = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                final = urlparse(response.geturl())
                if final.scheme != "https" or final.hostname not in ALLOWED_HOSTS:
                    raise ValueError("MIB 下载重定向到非白名单域名")
                data = response.read(MAX_BYTES + 1)
            if len(data) > MAX_BYTES:
                raise ValueError("MIB 文件超过 5MB")
            return data
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            if attempt < 2:
                time.sleep(0.5)
    raise last_error or RuntimeError("MIB 下载失败")


def _get_json(url: str) -> Any:
    return json.loads(_safe_get(url).decode("utf-8", errors="replace"))


def _decode(content: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")


COMMON_WORDS = {
    "entity": 22, "environment": 22, "system": 16, "cpu": 12,
    "memory": 12, "resource": 12, "health": 12, "device": 8,
    "power": 8, "fan": 8, "temperature": 8, "interface": 5,
}
NOISE_WORDS = (
    "bras", "srvcfg", "mpls", "bgp", "ospf", "isis", "l2vpn", "l3vpn",
    "multicast", "ipv6", "acl", "aaa", "qos", "vlan", "stp", "trap",
    "notification", "alarm", "firewall", "srpolicy", "segment-routing",
)


def _candidate_score(name: str, model: str) -> int:
    lowered = name.lower()
    score = 0
    model_tokens = [token.lower() for token in re.findall(r"[A-Za-z0-9]{2,}", model or "")]
    for token in model_tokens:
        if token and token in lowered:
            score += 60
    for word, weight in COMMON_WORDS.items():
        if word in lowered:
            score += weight
    for word in NOISE_WORDS:
        if word in lowered:
            score -= 14
    return score


def _vendor_dir(vendor: str, sys_descr: str = "") -> str:
    key = _vendor_key(vendor, sys_descr)
    return VENDOR_DIRS.get(key, "")


def _list_directory(directory: str) -> List[Dict[str, Any]]:
    suffix = f"{API_BASE}/{quote(directory)}?ref={SOURCE_BRANCH}&per_page=1000" if directory else f"{API_BASE}?ref={SOURCE_BRANCH}&per_page=1000"
    try:
        data = _get_json(suffix)
    except Exception:
        return []
    return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []


def _find_file(entries: List[Dict[str, Any]], module: str) -> Optional[Dict[str, Any]]:
    target = module.lower().strip()
    names = {target, f"{target}.mib", f"{target}.txt"}
    for item in entries:
        if str(item.get("type") or "") != "file":
            continue
        name = str(item.get("name") or "")
        if name.lower() in names:
            return item
    return None


def _download_entry(entry: Dict[str, Any], directory: str) -> Dict[str, Any]:
    name = str(entry.get("name") or "").strip()
    download_url = str(entry.get("download_url") or "").strip()
    if not download_url:
        prefix = f"{RAW_BASE}/{quote(directory)}" if directory else RAW_BASE
        download_url = f"{prefix}/{quote(name)}"
    data = _safe_get(download_url, accept="text/plain")
    text = _decode(data)
    if "DEFINITIONS" not in text.upper():
        raise ValueError("不是 MIB 文件")
    return {"filename": name, "text": text, "size": len(data), "source": download_url}


def fetch_texts(vendor: str, model: str = "", sys_descr: str = "") -> Dict[str, Any]:
    """下载候选 MIB 及其直接依赖；只返回文本，不写数据库。"""
    directory = _vendor_dir(vendor, sys_descr)
    if not directory:
        return {"vendor": vendor, "directory": "", "files": [], "errors": [f"暂不支持厂商 {vendor or '未知'} 的在线 MIB 来源"]}
    entries = _list_directory(directory)
    if not entries:
        return {"vendor": vendor, "directory": directory, "files": [], "errors": ["读取在线 MIB 目录失败或目录为空"]}
    initial = [item for item in entries if isinstance(item, dict) and item.get("type") == "file"]
    initial.sort(key=lambda item: _candidate_score(str(item.get("name") or ""), model), reverse=True)
    files: List[Dict[str, Any]] = []
    errors: List[str] = []
    downloaded = set()
    total_bytes = 0
    for item in initial[:MAX_FILES]:
        name = str(item.get("name") or "")
        try:
            record = _download_entry(item, directory)
            if total_bytes + record["size"] > MAX_TOTAL_BYTES:
                errors.append(f"{name}：本次在线下载总量超过限制")
                continue
            total_bytes += record["size"]
            files.append(record)
            downloaded.add(name.lower())
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}：{str(exc)[:200]}")

    # 解析 IMPORTS，补齐直接依赖（标准模块已内置，不再下载）。
    known_modules = {str(item).lower() for item in standard_mibs.known_modules()}
    queue: List[str] = []
    for record in files:
        try:
            parsed = mib_parser.parse_mib(record["text"], record["filename"], known_oids=standard_mibs.symbol_map())
            queue.extend(str(item) for item in (parsed.get("imports") or []) if str(item).strip())
        except Exception:
            continue
    root_entries: Optional[List[Dict[str, Any]]] = None
    dependency_count = 0
    while queue and dependency_count < MAX_DEPENDENCIES:
        module = queue.pop(0).strip()
        if not module or module.lower() in known_modules or module.lower() in downloaded:
            continue
        entry = _find_file(entries, module)
        source_dir = directory
        if not entry:
            if root_entries is None:
                root_entries = _list_directory("")
            entry = _find_file(root_entries, module)
            source_dir = ""
        if not entry:
            errors.append(f"缺少依赖：{module}")
            continue
        try:
            record = _download_entry(entry, source_dir)
            if record["filename"].lower() in downloaded:
                continue
            if total_bytes + record["size"] > MAX_TOTAL_BYTES:
                errors.append(f"{module}：本次在线下载总量超过限制")
                continue
            total_bytes += record["size"]
            files.append(record)
            downloaded.add(record["filename"].lower())
            dependency_count += 1
            parsed = mib_parser.parse_mib(record["text"], record["filename"], known_oids=standard_mibs.symbol_map())
            queue.extend(str(item) for item in (parsed.get("imports") or []) if str(item).strip())
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{module}：{str(exc)[:200]}")
    return {"vendor": vendor, "directory": directory, "files": files, "errors": errors}

def import_texts(db: Session, vendor: str, model: str, files: List[Dict[str, Any]]) -> Dict[str, Any]:
    """解析并入库在线 MIB；按依赖顺序多轮解析后只写入有效对象。"""
    known = dict(standard_mibs.symbol_map())
    try:
        known.update(standard_mibs.load_standard_dir_symbols())
    except Exception:
        pass
    for obj in db.query(MibObject).all():
        if obj.name and obj.oid:
            known.setdefault(obj.name, obj.oid)
    existing_modules = {str(item.module_name or "").lower() for item in db.query(MibFile).all()}
    parsed_records: List[Dict[str, Any]] = []
    pending = list(files)
    # 依赖可能后于主 MIB 下载，多轮解析直到 OID 符号不再增加。
    for _ in range(5):
        next_pending = []
        progressed = False
        for item in pending:
            try:
                parsed = mib_parser.parse_mib(item["text"], item["filename"], known_oids=known)
                record = {**item, "parsed": parsed}
                parsed_records.append(record)
                for obj in parsed.get("objects") or []:
                    name = str(obj.get("name") or "").strip()
                    oid = str(obj.get("oid") or "").strip()
                    if name and oid and name not in known:
                        known[name] = oid
                        progressed = True
                if parsed.get("unresolved", 0) > 0:
                    next_pending.append(item)
            except Exception:
                next_pending.append(item)
        pending = next_pending
        if not pending or not progressed:
            break
    # 取每份 MIB 解析对象最多的一次结果
    best_by_file: Dict[str, Dict[str, Any]] = {}
    for record in parsed_records:
        key = record["filename"]
        old = best_by_file.get(key)
        if old is None or int(record["parsed"].get("total") or 0) >= int(old["parsed"].get("total") or 0):
            best_by_file[key] = record
    imported = []
    errors = []
    for record in best_by_file.values():
        try:
            parsed = record["parsed"]
            module = str(parsed.get("module") or record["filename"]).strip()
            if module.lower() in existing_modules:
                errors.append(f"{record['filename']}：模块 {module} 已存在")
                continue
            if not parsed.get("objects"):
                errors.append(f"{record['filename']}：依赖未完整解析，暂无可导入对象")
                continue
            mib = MibFile(
                filename=str(record["filename"])[:255],
                module_name=module[:120],
                size=int(record.get("size") or 0),
                object_count=int(parsed.get("total") or 0),
                readable_count=int(parsed.get("readable") or 0),
                unresolved_count=int(parsed.get("unresolved") or 0),
                categories=parsed.get("categories") or [],
                imports=parsed.get("imports") or [],
                vendor=vendor[:60],
                device_model=(model or "")[:120],
                note=f"在线获取：{SOURCE_LABEL}；来源 {str(record.get('source') or '')[:300]}",
            )
            db.add(mib)
            db.flush()
            for obj in (parsed.get("objects") or [])[:MAX_OBJECTS]:
                db.add(MibObject(
                    mib_id=mib.id,
                    name=(obj.get("name") or "")[:160],
                    oid=(obj.get("oid") or "")[:200],
                    syntax=(obj.get("syntax") or "")[:160],
                    access=(obj.get("access") or "")[:40],
                    status=(obj.get("status") or "")[:40],
                    description=obj.get("description") or "",
                    category=(obj.get("category") or "")[:30],
                    score=obj.get("score") or 0,
                ))
            db.flush()
            imported.append({"id": mib.id, "filename": mib.filename, "module_name": mib.module_name, "object_count": mib.object_count})
            existing_modules.add(module.lower())
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{record.get('filename') or 'MIB'}：{str(exc)[:240]}")
    return {"imported": imported, "errors": errors}

def fetch_and_import(db: Session, vendor: str, model: str = "", sys_descr: str = "") -> Dict[str, Any]:
    fetched = fetch_texts(vendor, model, sys_descr)
    result = import_texts(db, vendor, model, fetched.get("files") or [])
    return {
        "source": SOURCE_LABEL,
        "directory": fetched.get("directory") or "",
        "fetched": len(fetched.get("files") or []),
        "imported": result["imported"],
        "errors": (fetched.get("errors") or []) + (result["errors"] or []),
    }
