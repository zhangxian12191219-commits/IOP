"""即时通信群组的纯逻辑辅助：输入清洗、群通话内存登记表。

这里不访问数据库，方便单测；访问控制与广播由 routes/im.py 完成。
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

GROUP_NAME_MAX_LENGTH = 60
GROUP_MAX_MEMBERS = 30
MAX_MESSAGE_LENGTH = 4000
MAX_CALL_ID_LENGTH = 100
MAX_BOARD_ID_LENGTH = 40
MAX_STROKE_POINTS = 2000
MAX_STROKE_CONTENT_CHARS = 200_000

_HEX_COLOR_RE = re.compile(r"^#(?:[0-9a-fA-F]{6})$")
_PEN_TOOLS = ("pen", "eraser")


def normalize_group_name(raw: Any) -> str:
    """群名：去首尾空白、压缩空白，1~60 字符。"""
    name = re.sub(r"\s+", " ", str(raw or "")).strip()
    return name[:GROUP_NAME_MAX_LENGTH]


def normalize_user_ids(raw: Any) -> List[int]:
    """成员 ID 列表：去重、保持顺序、只接受正整数。"""
    if not isinstance(raw, (list, tuple, set)):
        return []
    result: List[int] = []
    seen: set[int] = set()
    for item in raw:
        try:
            value = int(item)
        except (TypeError, ValueError):
            continue
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def normalize_call_id(raw: Any) -> str:
    return str(raw or "").strip()[:MAX_CALL_ID_LENGTH]


def normalize_board_id(raw: Any) -> str:
    board_id = re.sub(r"[^0-9A-Za-z_-]", "", str(raw or ""))[:MAX_BOARD_ID_LENGTH]
    return board_id or "main"


def _clamp_coord(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return round(max(0.0, min(1.0, number)), 4)


def sanitize_stroke(raw: Any) -> Optional[dict]:
    """清洗一笔白板笔画；非法数据返回 None。坐标归一化到 0~1。"""
    if not isinstance(raw, dict):
        return None
    tool = str(raw.get("tool") or "pen").lower()
    if tool not in _PEN_TOOLS:
        tool = "pen"
    color = str(raw.get("color") or "").strip()
    if not _HEX_COLOR_RE.match(color):
        color = "#38bdf8"
    try:
        width = int(float(raw.get("width") or 3))
    except (TypeError, ValueError):
        width = 3
    width = max(1, min(64, width))
    raw_points = raw.get("points")
    if not isinstance(raw_points, (list, tuple)) or len(raw_points) < 2:
        return None
    points: List[List[float]] = []
    for item in raw_points[:MAX_STROKE_POINTS]:
        if not isinstance(item, (list, tuple)) or len(item) < 2:
            continue
        x = _clamp_coord(item[0])
        y = _clamp_coord(item[1])
        if x is None or y is None:
            continue
        points.append([x, y])
    if len(points) < 2:
        return None
    return {"tool": tool, "color": color, "width": width, "points": points}


def sanitize_pointer(raw: Any) -> Optional[dict]:
    """清洗激光笔 / 指针坐标。"""
    if not isinstance(raw, dict):
        return None
    x = _clamp_coord(raw.get("x"))
    y = _clamp_coord(raw.get("y"))
    if x is None or y is None:
        return None
    return {"x": x, "y": y, "visible": bool(raw.get("visible", True))}


class GroupCallRegistry:
    """群通话登记表（单进程内存）。

    mesh WebRTC 的信令只在这里登记参与者与媒体状态，不保存 SDP；
    SDP / ICE 由服务端按 call_id + from + to + group_id 点对点转发。
    """

    def __init__(self) -> None:
        self._calls: Dict[str, dict] = {}

    def get(self, call_id: Any) -> Optional[dict]:
        return self._calls.get(normalize_call_id(call_id))

    def start(
        self,
        call_id: Any,
        group_id: int,
        call_type: str,
        owner_id: int,
        participant_ids: Iterable[int],
    ) -> Optional[dict]:
        key = normalize_call_id(call_id)
        if not key or key in self._calls:
            return None
        call_type = "video" if call_type == "video" else "audio"
        participants: Dict[int, dict] = {}
        for raw_id in participant_ids:
            try:
                user_id = int(raw_id)
            except (TypeError, ValueError):
                continue
            participants[user_id] = {
                "muted": False,
                "camera": call_type == "video",
                "joined": user_id == int(owner_id),
                "joined_at": datetime.utcnow(),
            }
        call = {
            "call_id": key,
            "group_id": int(group_id),
            "call_type": call_type,
            "owner_id": int(owner_id),
            "participants": participants,
            "started_at": datetime.utcnow(),
        }
        self._calls[key] = call
        return call

    def join(self, call_id: Any, user_id: int, call_type: Optional[str] = None) -> Optional[dict]:
        call = self.get(call_id)
        if not call:
            return None
        state = call["participants"].get(int(user_id))
        if state is None:
            state = {
                "muted": False,
                "camera": (call_type or call["call_type"]) == "video",
                "joined_at": datetime.utcnow(),
            }
            call["participants"][int(user_id)] = state
        state["joined"] = True
        return call

    def leave(self, call_id: Any, user_id: int) -> Tuple[Optional[dict], int]:
        call = self.get(call_id)
        if not call:
            return None, 0
        call["participants"].pop(int(user_id), None)
        remaining = len(call["participants"])
        if remaining <= 0:
            self._calls.pop(call["call_id"], None)
        return call, remaining

    def end(self, call_id: Any) -> Optional[dict]:
        return self._calls.pop(normalize_call_id(call_id), None)

    def set_media(self, call_id: Any, user_id: int, muted: bool, camera: bool) -> Optional[dict]:
        call = self.get(call_id)
        if not call:
            return None
        state = call["participants"].get(int(user_id))
        if state is None:
            return None
        state["muted"] = bool(muted)
        state["camera"] = bool(camera)
        return call

    def is_participant(self, call_id: Any, user_id: int) -> bool:
        call = self.get(call_id)
        return bool(call and int(user_id) in call["participants"])

    def participant_ids(self, call_id: Any) -> List[int]:
        call = self.get(call_id)
        return sorted(call["participants"].keys()) if call else []

    def participant_state(self, call_id: Any, user_id: int) -> Optional[dict]:
        call = self.get(call_id)
        if not call:
            return None
        return call["participants"].get(int(user_id))

    def remove_user(self, user_id: int) -> List[dict]:
        """断开连接时把用户从所有群通话移除，返回仍有意义的通话列表。"""
        touched: List[dict] = []
        for call_id in list(self._calls.keys()):
            call = self._calls.get(call_id)
            if not call or int(user_id) not in call["participants"]:
                continue
            call["participants"].pop(int(user_id), None)
            touched.append(call)
            if not call["participants"]:
                self._calls.pop(call_id, None)
        return touched

    def calls_for_user(self, user_id: int) -> List[dict]:
        return [
            call for call in self._calls.values()
            if int(user_id) in call["participants"]
        ]

    def __len__(self) -> int:
        return len(self._calls)


registry = GroupCallRegistry()

__all__ = [
    "GROUP_NAME_MAX_LENGTH",
    "GROUP_MAX_MEMBERS",
    "MAX_MESSAGE_LENGTH",
    "MAX_STROKE_POINTS",
    "MAX_STROKE_CONTENT_CHARS",
    "registry",
    "GroupCallRegistry",
    "normalize_group_name",
    "normalize_user_ids",
    "normalize_call_id",
    "normalize_board_id",
    "sanitize_stroke",
    "sanitize_pointer",
]
