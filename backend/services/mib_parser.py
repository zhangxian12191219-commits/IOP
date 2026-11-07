"""MIB 文件解析（纯 Python，ASN.1 MIB 子集）

支持常见的 SNMP MIB：
- 模块名：XXX DEFINITIONS ::= BEGIN
- OID 赋值：name OBJECT IDENTIFIER ::= { parent 1 }
- 对象定义：name OBJECT-TYPE SYNTAX ... ACCESS ... STATUS ... DESCRIPTION "..." ::= { parent 1 }
- IMPORTS 引用的标准根节点（iso/org/dod/internet/mgmt/mib-2/enterprises 等）内置解析

解析结果：对象名、数字 OID、语法、访问权限、状态、描述、推荐类别。
"""
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

# 标准根节点（SNMPv2-SMI 等基础定义），用于解析 IMPORTS 引用
COMMON_OIDS: Dict[str, str] = {
    "iso": "1",
    "org": "1.3",
    "dod": "1.3.6",
    "internet": "1.3.6.1",
    "directory": "1.3.6.1.1",
    "mgmt": "1.3.6.1.2",
    "mib-2": "1.3.6.1.2.1",
    "mib_2": "1.3.6.1.2.1",
    "transmission": "1.3.6.1.2.1.10",
    "experimental": "1.3.6.1.3",
    "private": "1.3.6.1.4",
    "enterprises": "1.3.6.1.4.1",
    "security": "1.3.6.1.5",
    "snmpV2": "1.3.6.1.6",
    "snmpDomains": "1.3.6.1.6.1",
    "snmpProxys": "1.3.6.1.6.2",
    "snmpModules": "1.3.6.1.6.3",
    "zeroDotZero": "0.0",
    "snmpMIB": "1.3.6.1.6.3.1",
    "ifMIB": "1.3.6.1.2.1.31",
    "ifMIBObjects": "1.3.6.1.2.1.31.1",
}

# 推荐类别关键词：名称命中权重高，描述命中权重低
CATEGORY_KEYWORDS: Dict[str, List[str]] = {
    "cpu": ["cpu", "processor", "load", "utilization", "util", "busy", "usage"],
    "memory": ["memory", "mem", "ram", "buffer", "swap", "heap"],
    "storage": ["storage", "disk", "volume", "filesystem", "capacity", "pool"],
    "temperature": ["temperature", "temp", "thermal", "celsius", "degrees"],
    "power": ["power", "psu", "supply", "voltage", "watt", "battery", "redundancy"],
    "optical": [
        "optical", "light", "rxpower", "txpower", "rx_power", "tx_power",
        "receivepower", "transmitpower", "dbm", "lux", "luminance",
    ],
    "fan": ["fan", "rpm", "rotations", "rotspeed", "fan_speed", "fanspeed", "cooling"],
    "session": ["session", "connection", "concurrent", "connections", "sessions"],
    "interface": ["interface", "if", "port", "oper", "admin", "link", "speed", "octets"],
}

CATEGORY_LABELS = {
    "cpu": "CPU 使用率",
    "memory": "内存使用率",
    "storage": "存储容量",
    "temperature": "温度",
    "power": "电源状态",
    "optical": "光功率",
    "fan": "风扇转速",
    "session": "会话数",
    "interface": "接口",
}

_NUMBER_RE = re.compile(r"\d+")
_QUOTED_RE = re.compile(r'"((?:[^"\\]|\\.)*)"', re.S)


def _strip_comments(text: str) -> str:
    """去掉 -- 注释（保留字符串内的 --）"""
    out: List[str] = []
    i, n = 0, len(text)
    in_string = False
    while i < n:
        ch = text[i]
        if in_string:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_string = False
            i += 1
            continue
        if ch == '"':
            in_string = True
            out.append(ch)
            i += 1
            continue
        if ch == "-" and i + 1 < n and text[i + 1] == "-":
            while i < n and text[i] not in "\r\n":
                i += 1
            out.append(" ")
            continue
        out.append(ch)
        i += 1
    return "".join(out)


def _clean_description(text: str) -> str:
    """规范化 DESCRIPTION 文本（保留原样，仅压缩空白与转义）"""
    text = text.replace('\\"', '"').replace('\\n', " ").replace('\\t', " ")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:800]


def _resolve_tokens(
    tokens: List[str],
    name_map: Dict[str, str],
    known_oids: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """把 OID 定义体（如 { enterprises 9 1 2 }）解析成数字 OID

    known_oids：外部标准库/已导入 MIB 的符号，仅用于解析引用，不导出为对象
    """
    parts: List[str] = []
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        named = re.fullmatch(r"([A-Za-z][\w-]*)\((\d+)\)", token)
        if named:
            parts.append(named.group(2))
            continue
        if re.fullmatch(r"\d+", token):
            parts.append(token)
            continue
        if re.fullmatch(r"[A-Za-z][\w-]*", token):
            oid = (
                name_map.get(token)
                or (known_oids or {}).get(token)
                or COMMON_OIDS.get(token)
            )
            if not oid:
                return None
            parts.extend(oid.split("."))
            continue
        # 其它形式（如 "0"）无法解析
        return None
    if not parts:
        return None
    return ".".join(parts)


def _find_module_name(text: str, filename: str) -> str:
    match = re.search(r"^\s*([A-Za-z][\w-]*)\s+DEFINITIONS\b", text, re.M)
    if match:
        return match.group(1)
    return filename.rsplit(".", 1)[0][:80] or "UNKNOWN-MIB"


def _extract_imports(text: str) -> List[str]:
    modules: List[str] = []
    for block in re.finditer(r"IMPORTS\b(.*?);", text, re.S):
        for match in re.finditer(r"FROM\s+([A-Za-z][\w-]*)", block.group(1)):
            name = match.group(1)
            if name not in modules:
                modules.append(name)
    return modules


# 定义名必须位于行首（允许缩进），避免把 IMPORTS 列表中的关键字当成对象名
_IDENT_RE = re.compile(
    r"(?m)^[ \t]*([A-Za-z][\w-]*)[ \t]+OBJECT[ \t]+IDENTIFIER[ \t]*::=[ \t]*\{([^{}]*)\}",
    re.S,
)
# 模块根节点 / 对象标识节点
_MODULE_IDENT_RE = re.compile(
    r"(?m)^[ \t]*([A-Za-z][\w-]*)[ \t]+(?:MODULE-IDENTITY|OBJECT-IDENTITY)\b"
    r"(?:(?!::=).)*?::=[ \t]*\{([^{}]*)\}",
    re.S,
)
_TYPE_RE = re.compile(
    r"(?m)^[ \t]*([A-Za-z][\w-]*)[ \t]+OBJECT-TYPE\b(?:(?!::=).)*?::=[ \t]*\{([^{}]*)\}",
    re.S,
)

_RESERVED_NAMES = {"IMPORTS", "EXPORTS", "OBJECT-TYPE", "OBJECT-IDENTITY",
                   "MODULE-IDENTITY", "DEFINITIONS", "BEGIN", "END"}
_SYNTAX_RE = re.compile(
    r"\bSYNTAX\s+(.+?)(?=\b(?:MAX-ACCESS|ACCESS|STATUS|DESCRIPTION|REFERENCE|INDEX|"
    r"DEFVAL|UNITS|::=)\b)",
    re.S,
)
_ACCESS_RE = re.compile(r"\b(?:MAX-ACCESS|ACCESS)\s+([\w-]+)")
_STATUS_RE = re.compile(r"\bSTATUS\s+([\w-]+)")
_DESCRIPTION_RE = re.compile(r"\bDESCRIPTION\s*\"((?:[^\"\\]|\\.)*)\"", re.S)


# 名称偏好/负向词：帮助在同类候选中挑出「使用率」而非「总量/描述/阈值」
PREFER_WORDS: Dict[str, List[str]] = {
    "cpu": ["usage", "util", "load", "percent", "avg", "rate"],
    "memory": ["usage", "used", "util", "percent", "available", "free"],
    "temperature": ["current", "celsius", "value", "temp"],
    "power": ["status", "state", "present"],
}
PENALIZE_WORDS: Dict[str, List[str]] = {
    "cpu": ["count", "index", "descr", "name", "id"],
    "memory": ["total", "size", "capacity", "descr", "index", "max", "alloc"],
    "temperature": ["threshold", "alarm", "trap", "limit", "high", "low"],
    "power": ["threshold", "alarm", "trap", "limit", "count"],
}


def _score_category(name: str, description: str, syntax: str, access: str) -> Tuple[Optional[str], int]:
    """根据名称/描述推断对象所属类别及置信度"""
    lname = name.lower()
    ldesc = (description or "").lower()

    # 表/行对象不适合直接 GET
    if lname.endswith(("table", "entry", "index")) or lname.endswith("table"):
        return None, 0
    if syntax.upper().startswith("SEQUENCE") or "SEQUENCE OF" in syntax.upper():
        return None, 0
    if access in ("not-accessible", "accessible-for-notify"):
        return None, 0

    best: Optional[str] = None
    best_score = 0
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = 0
        for kw in keywords:
            if kw in lname:
                score += 3
            if ldesc and kw in ldesc:
                score += 1
        if score <= 0:
            continue
        for word in PREFER_WORDS.get(category, []):
            if word in lname:
                score += 4
        for word in PENALIZE_WORDS.get(category, []):
            if word in lname:
                score -= 3
        if score > best_score:
            best_score = score
            best = category
    return best, best_score


def parse_mib(
    text: str,
    filename: str = "",
    known_oids: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """解析单个 MIB 文本

    known_oids: 外部已知对象名→OID（标准库/已导入 MIB），用于解析依赖引用
    返回: {module, imports, objects: [...], unresolved: int, total: int}
    """
    raw = _strip_comments(text)
    module = _find_module_name(raw, filename)
    imports = _extract_imports(raw)

    # 1) 先解析 OBJECT IDENTIFIER 赋值，构建名称 -> OID 映射
    external = dict(known_oids or {})
    name_map: Dict[str, str] = {}
    pending: List[Tuple[str, List[str]]] = []
    for match in _IDENT_RE.finditer(raw):
        name, body = match.group(1), match.group(2)
        if name in _RESERVED_NAMES:
            continue
        pending.append((name, body.split()))
    for match in _MODULE_IDENT_RE.finditer(raw):
        name, body = match.group(1), match.group(2)
        if name in _RESERVED_NAMES:
            continue
        pending.append((name, body.split()))

    unresolved = 0
    # 多轮解析，处理定义顺序依赖
    for _round in range(6):
        remaining: List[Tuple[str, List[str]]] = []
        progress = False
        for name, tokens in pending:
            oid = _resolve_tokens(tokens, name_map, external)
            if oid:
                name_map[name] = oid
                progress = True
            else:
                remaining.append((name, tokens))
        pending = remaining
        if not progress:
            break
    unresolved += len(pending)

    objects: List[Dict[str, Any]] = []
    seen_oids = set()

    # 2) 解析 OBJECT-TYPE 定义
    #    OBJECT-TYPE 的 OID 也可能是其它对象的父节点（如表 → 行 → 列），
    #    因此需要多轮解析：先解析父节点已确定的，再把结果加入 name_map 供后续使用。
    entries: List[Dict[str, Any]] = []
    for match in _TYPE_RE.finditer(raw):
        name = match.group(1)
        if name in _RESERVED_NAMES:
            continue
        body = match.group(0)
        entries.append({
            "name": name,
            "tokens": match.group(2).split(),
            "body": body,
        })

    pending_entries = entries
    resolved_objects: List[Dict[str, Any]] = []
    for _round in range(8):
        remaining: List[Dict[str, Any]] = []
        progress = False
        for entry in pending_entries:
            oid = _resolve_tokens(entry["tokens"], name_map, external)
            if not oid:
                remaining.append(entry)
                continue
            name_map[entry["name"]] = oid
            progress = True

            body = entry["body"]
            syntax_match = _SYNTAX_RE.search(body)
            syntax = ""
            if syntax_match:
                syntax = re.sub(r"\s+", " ", syntax_match.group(1)).strip()[:120]
            access_match = _ACCESS_RE.search(body)
            access = access_match.group(1) if access_match else ""
            status_match = _STATUS_RE.search(body)
            status = status_match.group(1) if status_match else ""
            desc_match = _DESCRIPTION_RE.search(body)
            description = _clean_description(desc_match.group(1)) if desc_match else ""

            category, score = _score_category(
                entry["name"], description, syntax, access
            )
            resolved_objects.append({
                "name": entry["name"],
                "oid": oid,
                "syntax": syntax,
                "access": access,
                "status": status,
                "description": description,
                "category": category or "",
                "score": score,
            })
        pending_entries = remaining
        if not progress:
            break
    unresolved += len(pending_entries)

    for obj in resolved_objects:
        if obj["oid"] in seen_oids:
            continue
        seen_oids.add(obj["oid"])
        objects.append(obj)

    # 3) 纯 OID 节点也收录（便于在 MIB 树中查看），但低优先级
    for name, oid in name_map.items():
        if oid in seen_oids:
            continue
        seen_oids.add(oid)
        objects.append({
            "name": name,
            "oid": oid,
            "syntax": "",
            "access": "",
            "status": "",
            "description": "",
            "category": "",
            "score": 0,
        })

    # 限制数量，避免超大 MIB 撑爆数据库
    objects.sort(key=lambda item: (item["score"] == 0, item["name"]))
    objects = objects[:8000]

    categories = sorted({o["category"] for o in objects if o["category"]})
    readable = [o for o in objects if o["access"] not in ("not-accessible", "")]
    return {
        "module": module,
        "imports": imports,
        "objects": objects,
        "total": len(objects),
        "readable": len(readable),
        "unresolved": unresolved,
        "categories": categories,
    }


def recommend(objects: Iterable[Dict[str, Any]], per_category: int = 8) -> Dict[str, List[Dict[str, Any]]]:
    """按类别给出推荐 OID（供设备采集优化）"""
    result: Dict[str, List[Dict[str, Any]]] = {key: [] for key in CATEGORY_LABELS}
    for obj in objects:
        category = obj.get("category") or ""
        if category not in result:
            continue
        result[category].append(obj)

    for category, items in result.items():
        items.sort(key=lambda o: (-(o.get("score") or 0), o.get("name") or ""))
        result[category] = items[:per_category]
    return result


def guess_metric_map(objects: Iterable[Dict[str, Any]]) -> Dict[str, Optional[Dict[str, Any]]]:
    """自动识别设备采集映射：每个指标取置信度最高的一个对象"""
    best: Dict[str, Optional[Dict[str, Any]]] = {
        "cpu": None, "memory": None, "temperature": None, "power": None,
    }
    for obj in objects:
        category = obj.get("category") or ""
        if category not in best:
            continue
        current = best[category]
        if current is None or (obj.get("score") or 0) > (current.get("score") or 0):
            best[category] = obj
    return best
