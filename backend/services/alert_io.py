"""告警导出（Excel / CSV）

导出列包含告警本身信息（时间/级别/类型/内容/值/阈值/确认状态）
以及设备上下文（设备名/IP/类型/厂商/型号/位置/机房/机柜/U位/功率）。
"""
import csv
import io
from datetime import datetime, timezone
from typing import Any, Dict, List, Tuple

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

# (表头, 字段名, 列宽)
COLUMNS: List[Tuple[str, str, int]] = [
    ("告警时间", "created_at_local", 20),
    ("告警级别", "level_text", 10),
    ("告警类型", "type_text", 10),
    ("告警来源", "source_text", 10),
    ("告警信息", "message", 46),
    ("当前值", "value", 10),
    ("阈值", "threshold", 10),
    ("确认状态", "ack_text", 10),
    ("设备名称", "device_name", 20),
    ("IP地址", "ip_address", 16),
    ("设备类型", "device_type_text", 10),
    ("厂商", "vendor", 12),
    ("型号", "model", 20),
    ("设备位置", "location", 18),
    ("机房", "room_name", 16),
    ("机柜", "cabinet_name", 20),
    ("起始U位", "u_position", 9),
    ("占用U数", "u_height", 9),
    ("设备功率(W)", "power_watts", 12),
]

LEVEL_TEXT = {"critical": "严重", "warning": "警告", "info": "提示"}
TYPE_TEXT = {
    "cpu": "CPU", "memory": "内存", "temperature": "温度",
    "power": "电源", "offline": "离线", "down": "不可达", "slow": "响应慢",
    "ssl_expired": "SSL证书异常",
}

HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
HEADER_FONT = Font(color="FFFFFF", bold=True)


def _local_time(iso_str: str) -> str:
    """把 UTC ISO 时间转换为服务器本地时间字符串"""
    if not iso_str:
        return ""
    try:
        dt = datetime.fromisoformat(iso_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return iso_str


def _rows(items: List[Dict[str, Any]]) -> List[List[Any]]:
    rows = []
    for a in items:
        level = (a.get("alert_level") or "").lower()
        rows.append([
            _local_time(a.get("created_at")),
            LEVEL_TEXT.get(level, level or ""),
            TYPE_TEXT.get(a.get("alert_type"), a.get("alert_type") or ""),
            a.get("source_text") or ("网站" if a.get("source") == "website" else "设备"),
            a.get("message") or "",
            a.get("value") if a.get("value") is not None else "",
            a.get("threshold") if a.get("threshold") is not None else "",
            "已确认" if a.get("is_acknowledged") else "未确认",
            a.get("device_name") or "",
            a.get("ip_address") or "",
            a.get("device_type_text") or "",
            a.get("vendor") or "",
            a.get("model") or "",
            a.get("location") or "",
            a.get("room_name") or "",
            a.get("cabinet_name") or "",
            a.get("u_position") if a.get("u_position") is not None else "",
            a.get("u_height") if a.get("u_height") is not None else "",
            a.get("power_watts") if a.get("power_watts") is not None else "",
        ])
    return rows


def _style_header(ws) -> None:
    for idx, (header, _key, width) in enumerate(COLUMNS, start=1):
        cell = ws.cell(row=1, column=idx, value=header)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        ws.column_dimensions[get_column_letter(idx)].width = width



def _safe_excel_cell(value):
    """阻止 CSV/Excel 公式注入：用户可控文本不能以公式前缀开头。"""
    if isinstance(value, str) and value and value[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value

def export_xlsx(items: List[Dict[str, Any]]) -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.title = "告警记录"
    _style_header(ws)

    for row_idx, row in enumerate(_rows(items), start=2):
        for col_idx, value in enumerate(row, start=1):
            ws.cell(row=row_idx, column=col_idx, value=_safe_excel_cell(value))
    ws.freeze_panes = "A2"
    if items:
        ws.auto_filter.ref = f"A1:{get_column_letter(len(COLUMNS))}{len(items) + 1}"

    info = wb.create_sheet("导出信息")
    info["A1"] = "导出时间"
    info["B1"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    info["A2"] = "告警数量"
    info["B2"] = len(items)
    info["A3"] = "说明"
    info["B3"] = (
        "告警时间已转换为服务器本地时间；设备位置/机房/机柜/U 位来自资产库快照，"
        "设备删除后将显示为空。"
    )
    info.column_dimensions["A"].width = 12
    info.column_dimensions["B"].width = 90

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def export_csv(items: List[Dict[str, Any]]) -> bytes:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([header for header, _key, _width in COLUMNS])
    for row in _rows(items):
        writer.writerow([_safe_excel_cell(value) for value in row])
    # 带 BOM，避免 Excel 打开中文乱码
    return buf.getvalue().encode("utf-8-sig")
