"""Zabbix 在线模板同步：通过 API 拉取模板并转换为现有 YAML 导入模型。

默认只拉取模板摘要，用户筛选并勾选后再拉取监控项详情，避免几千个模板和
海量监控项一次性进入内存。
"""
from __future__ import annotations

import ipaddress
import re
from urllib.parse import urlparse
from typing import Any, Dict, Iterable, List, Optional

import requests
import yaml

ITEM_TYPE_MAP = {
    "0": "ZABBIX_PASSIVE",
    "2": "TRAP",
    "3": "SIMPLE",
    "4": "SNMP_AGENT",
    "5": "INTERNAL",
    "7": "ZABBIX_ACTIVE",
    "9": "HTTP_AGENT",
    "10": "EXTERNAL",
    "11": "DATABASE_MONITOR",
    "12": "IPMI_AGENT",
    "13": "SSH_AGENT",
    "14": "TELNET_AGENT",
    "15": "CALCULATED",
    "16": "JMX_AGENT",
    "17": "SNMP_TRAP",
    "18": "DEPENDENT",
    "19": "HTTP_AGENT",
    "20": "SCRIPT",
    "21": "BROWSER",
}
VALUE_TYPE_MAP = {
    "0": "FLOAT",
    "1": "CHAR",
    "2": "LOG",
    "3": "UNSIGNED",
    "4": "TEXT",
}
PREPROCESSING_TYPE_MAP = {
    "1": "MULTIPLIER",
    "2": "RIGHT_TRIM",
    "3": "LEFT_TRIM",
    "4": "TRIM",
    "5": "REGEX",
    "6": "BOOL_TO_DECIMAL",
    "7": "OCTAL_TO_DECIMAL",
    "8": "HEX_TO_DECIMAL",
    "9": "JAVASCRIPT",
    "10": "DISCARD_UNCHANGED",
    "11": "XMLPATH",
    "12": "JSONPATH",
    "13": "IN_RANGE",
    "14": "MATCHES_REGEX",
    "15": "NOT_MATCHES_REGEX",
    "16": "CHECK_JSON_ERROR",
    "17": "CHECK_XML_ERROR",
    "18": "CHECK_REGEX_ERROR",
    "19": "DISCARD_UNCHANGED_HEARTBEAT",
    "20": "JAVASCRIPT",
    "21": "JAVASCRIPT",
    "22": "PROMETHEUS_PATTERN",
    "23": "PROMETHEUS_TO_JSON",
    "24": "CSV_TO_JSON",
    "25": "STR_REPLACE",
    "26": "CHECK_NOT_SUPPORTED",
}
VENDOR_PATTERNS = [
    ("Huawei", "Huawei"), ("华为", "Huawei"),
    ("Cisco", "Cisco"), ("思科", "Cisco"),
    ("H3C", "H3C"), ("华三", "H3C"),
    ("Ruijie", "Ruijie"), ("锐捷", "Ruijie"),
    ("Fortinet", "Fortinet"), ("FortiGate", "Fortinet"),
    ("Sangfor", "Sangfor"), ("深信服", "Sangfor"),
    ("Topsec", "Topsec"), ("天融信", "Topsec"),
    ("Hikvision", "Hikvision"), ("海康", "Hikvision"),
    ("Dahua", "Dahua"), ("大华", "Dahua"),
    ("Juniper", "Juniper"), ("Arista", "Arista"),
    ("MikroTik", "MikroTik"), ("Ubiquiti", "Ubiquiti"),
    ("TP-Link", "TP-Link"), ("Dell", "Dell"), ("HPE", "HPE"),
    ("HP ", "HP"), ("Lenovo", "Lenovo"), ("联想", "Lenovo"),
    ("Inspur", "Inspur"), ("浪潮", "Inspur"),
]


class ZabbixError(Exception):
    pass


def _text(value: Any) -> str:
    return str(value or "").strip()


def _group_names(template: Dict[str, Any]) -> List[str]:
    names = []
    for group in template.get("groups") or []:
        if isinstance(group, dict):
            name = _text(group.get("name"))
        else:
            name = _text(group)
        if name and name not in names:
            names.append(name)
    return names


def detect_vendor(name: str) -> str:
    text = _text(name)
    for pattern, vendor in VENDOR_PATTERNS:
        if pattern.lower() in text.lower():
            return vendor
    return "其他"


class ZabbixClient:
    def __init__(
        self,
        url: str,
        token: str = "",
        username: str = "",
        password: str = "",
        verify_tls: bool = True,
        timeout: int = 20,
    ):
        base = _text(url).rstrip("/")
        if not re.match(r"^https?://", base, re.IGNORECASE):
            raise ZabbixError("Zabbix 地址必须以 http:// 或 https:// 开头")
        parsed = urlparse(base)
        if parsed.username or parsed.password:
            raise ZabbixError("Zabbix 地址不能包含内嵌用户名或密码")
        host = (parsed.hostname or "").strip().lower()
        blocked_names = {"metadata.google.internal", "metadata", "instance-data"}
        if host in blocked_names:
            raise ZabbixError("不允许访问云元数据地址")
        try:
            ip = ipaddress.ip_address(host)
            if ip.is_link_local or ip.is_loopback or ip.is_unspecified:
                raise ZabbixError("不允许访问回环、链路本地或未指定地址")
        except ValueError:
            pass
        if base.endswith("/api_jsonrpc.php"):
            self.endpoint = base
        else:
            self.endpoint = f"{base}/api_jsonrpc.php"
        self.token = _text(token)
        self.username = _text(username)
        self.password = str(password or "")
        self.verify_tls = bool(verify_tls)
        self.timeout = timeout
        self.session = requests.Session()
        self.session.verify = self.verify_tls
        self._id = 0
        self._logged_in = bool(self.token)
        if not self.token and (not self.username or not self.password):
            raise ZabbixError("请填写 Zabbix API Token，或填写用户名和密码")

    def _call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        self._id += 1
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params or {},
            "id": self._id,
        }
        headers = {"Content-Type": "application/json-rpc"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        try:
            response = self.session.post(
                self.endpoint,
                json=payload,
                headers=headers,
                timeout=self.timeout,
                allow_redirects=False,
            )
        except requests.RequestException as exc:
            raise ZabbixError(f"连接 Zabbix 失败：{exc}") from exc
        if response.status_code >= 400:
            raise ZabbixError(f"Zabbix HTTP {response.status_code}：{response.text[:200]}")
        try:
            data = response.json()
        except ValueError as exc:
            raise ZabbixError("Zabbix 返回内容不是 JSON，请检查 API 地址") from exc
        if data.get("error"):
            error = data["error"]
            message = error.get("data") or error.get("message") or "Zabbix API 错误"
            raise ZabbixError(str(message))
        return data.get("result")

    def version(self) -> str:
        result = self._call("apiinfo.version")
        return _text(result) or "unknown"

    def call(self, method: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """执行已认证的 Zabbix API 调用，供大屏等查询复用。"""
        if not self._logged_in:
            self.login()
            self._logged_in = True
        return self._call(method, params)

    def login(self) -> None:
        if self.token:
            return
        result = self._call("user.login", {
            "username": self.username,
            "password": self.password,
        })
        token = _text(result)
        if not token:
            raise ZabbixError("Zabbix 登录未返回 API Token")
        self.token = token

    def list_templates(self, keyword: str = "", limit: int = 300) -> List[Dict[str, Any]]:
        if not self._logged_in:
            self.login()
            self._logged_in = True
        params: Dict[str, Any] = {
            "output": ["templateid", "host", "name", "description"],
            "selectGroups": ["groupid", "name"],
            "sortfield": "host",
            "limit": max(1, min(int(limit or 300), 1000)),
        }
        if _text(keyword):
            params["search"] = {"host": _text(keyword), "name": _text(keyword)}
            params["searchByAny"] = True
        result = self._call("template.get", params) or []
        templates = []
        for item in result:
            if not isinstance(item, dict):
                continue
            groups = _group_names(item)
            templates.append({
                "templateid": _text(item.get("templateid")),
                "host": _text(item.get("host")),
                "name": _text(item.get("name")) or _text(item.get("host")),
                "description": _text(item.get("description")),
                "groups": groups,
            })
        return templates
