"""大屏展示外部数据源：Zabbix API 指标查询。"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from ..services.zabbix_templates import ZabbixClient, ZabbixError

router = APIRouter(prefix="/api/bigscreen", tags=["大屏展示"])


class ZabbixQuery(BaseModel):
    id: str = Field(..., max_length=100)
    host: str = Field(..., max_length=200)
    item: str = Field(..., max_length=500)
    aggregation: str = Field("last", max_length=20)
    minutes: int = Field(60, ge=1, le=10080)
    unit: str = Field("", max_length=30)
    precision: int = Field(1, ge=0, le=4)


class ZabbixQueryPayload(BaseModel):
    url: str = Field(..., min_length=8, max_length=500)
    token: str = Field("", max_length=500)
    username: str = Field("", max_length=100)
    password: str = Field("", max_length=255)
    verify_tls: bool = True
    queries: List[ZabbixQuery] = Field(default_factory=list, max_length=50)


def _number(value) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:
        return None
    return number


def _resolve_host(client: ZabbixClient, name: str) -> Optional[dict]:
    hosts = client.call("host.get", {
        "output": ["hostid", "host", "name"],
        "search": {"host": name, "name": name},
        "searchByAny": True,
        "limit": 2,
    }) or []
    return hosts[0] if hosts else None


def _query_one(client: ZabbixClient, query: ZabbixQuery) -> dict:
    host = _resolve_host(client, query.host)
    if not host:
        return {"id": query.id, "error": f"未找到 Zabbix 主机：{query.host}"}
    items = client.call("item.get", {
        "output": ["itemid", "name", "key_", "lastvalue", "lastclock", "units", "value_type"],
        "hostids": [host["hostid"]],
        "filter": {"key_": query.item},
        "limit": 5,
    }) or []
    if not items:
        items = client.call("item.get", {
            "output": ["itemid", "name", "key_", "lastvalue", "lastclock", "units", "value_type"],
            "hostids": [host["hostid"]],
            "search": {"key_": query.item},
            "limit": 5,
        }) or []
    if not items:
        return {
            "id": query.id,
            "error": f"主机 {query.host} 未找到指标 {query.item}",
        }
    item = items[0]
    value = _number(item.get("lastvalue"))
    aggregation = (query.aggregation or "last").lower()
    if aggregation not in ("last", "avg", "min", "max"):
        aggregation = "last"
    if aggregation != "last":
        history_type = int(item.get("value_type") or 3)
        if history_type not in (0, 3):
            return {
                "id": query.id,
                "host": host.get("host"),
                "host_name": host.get("name"),
                "item": item.get("key_"),
                "item_name": item.get("name"),
                "unit": query.unit or item.get("units") or "",
                "error": "文本指标不支持时间范围聚合",
            }
        now = int(datetime.now(timezone.utc).timestamp())
        values = client.call("history.get", {
            "output": ["value", "clock"],
            "history": history_type,
            "itemids": [item["itemid"]],
            "time_from": now - query.minutes * 60,
            "sortfield": "clock",
            "sortorder": "DESC",
            "limit": 5000,
        }) or []
        numbers = [number for number in (_number(row.get("value")) for row in values) if number is not None]
        if not numbers:
            return {"id": query.id, "host": host.get("host"), "item": item.get("key_"), "item_name": item.get("name"), "error": "所选时间范围没有历史数据"}
        if aggregation == "avg":
            value = sum(numbers) / len(numbers)
        elif aggregation == "min":
            value = min(numbers)
        else:
            value = max(numbers)
    return {
        "id": query.id,
        "host": host.get("host"),
        "host_name": host.get("name"),
        "item": item.get("key_"),
        "item_name": item.get("name"),
        "value": value,
        "unit": query.unit or item.get("units") or "",
        "aggregation": aggregation,
        "minutes": query.minutes,
        "clock": item.get("lastclock"),
        "error": "",
    }


@router.post("/zabbix/query")
def query_zabbix(payload: ZabbixQueryPayload):
    """查询大屏上的 Zabbix 指标；凭据只用于本次请求，不写入数据库。"""
    if not payload.queries:
        raise HTTPException(status_code=400, detail="至少配置一个 Zabbix 指标")
    if len(payload.queries) > 50:
        raise HTTPException(status_code=400, detail="单次最多查询 50 个指标")
    try:
        client = ZabbixClient(
            url=payload.url,
            token=payload.token,
            username=payload.username,
            password=payload.password,
            verify_tls=payload.verify_tls,
        )
        version = client.version()
    except ZabbixError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    results = []
    for query in payload.queries:
        try:
            results.append(_query_one(client, query))
        except ZabbixError as exc:
            results.append({"id": query.id, "error": str(exc)})
        except Exception as exc:  # noqa: BLE001
            results.append({"id": query.id, "error": f"查询失败：{exc}"})
    return {"zabbix_version": version, "results": results}
