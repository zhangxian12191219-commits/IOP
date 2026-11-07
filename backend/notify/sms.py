"""短信发送模块

支持三类短信发送方式，方便对接后续采购的短信网关设备：

1. ``http``   —— 通用 HTTP 短信网关（多数硬件短信猫/网关、企业短信平台都提供 HTTP 接口）
2. ``smpp``   —— SMPP 3.4 标准协议（运营商级短信网关、短信中心常用的 TCP 协议）
3. ``serial`` —— 串口 GSM 模块 / 短信猫（AT 指令，需 pyserial）

统一入口::

    await send_sms(config, ["13800000000"], "告警内容")

配置示例见 README「告警渠道 → 短信通道」。
"""
import asyncio
import json
import urllib.parse
import logging
import re
import socket
import time
from typing import Any, Dict, List, Optional, Tuple

import aiohttp

logger = logging.getLogger(__name__)

try:
    import serial  # pyserial
    HAS_PYSERIAL = True
except ImportError:  # 串口方式为可选能力
    serial = None
    HAS_PYSERIAL = False


class SmsError(Exception):
    """短信发送异常"""


# ==================== 号码与文案工具 ====================
def normalize_phones(phones: Any) -> List[str]:
    """把手机号配置规整为列表

    支持: 列表、逗号/分号/换行分隔的字符串；号码内的空格、短横线会被清理。
    会过滤掉明显不合法的号码（长度不在 5~20 位之间）。
    """
    if not phones:
        return []
    if isinstance(phones, (list, tuple)):
        raw = [str(p) for p in phones]
    else:
        # 只按分隔符切分，避免把 "138 0000 0000" 这种带空格的号码拆成多个
        raw = re.split(r"[,;\n\r]+", str(phones))

    out: List[str] = []
    for item in raw:
        phone = re.sub(r"[^\d+]", "", item or "")
        if not phone:
            continue
        digits = phone.lstrip("+")
        if not digits.isdigit() or not (5 <= len(digits) <= 20):
            continue
        if phone not in out:
            out.append(phone)
    return out


def truncate_text(text: str, limit: int = 500) -> str:
    """SMS 网关通常限长，超长截断（默认 500 字符，约 1~2 条长短信）"""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


# ==================== 1) HTTP 网关 ====================
def _render(template: Any, variables: Dict[str, str]) -> Any:
    """把模板里的 {phones} / {text} 等占位符替换为实际值（递归处理 dict/list）"""
    if isinstance(template, dict):
        return {k: _render(v, variables) for k, v in template.items()}
    if isinstance(template, list):
        return [_render(v, variables) for v in template]
    if isinstance(template, str):
        value = template
        for key, val in variables.items():
            value = value.replace("{" + key + "}", val)
        return value
    return template


def _json_get(data: Any, path: str) -> Any:
    """按 a.b.c 路径取 JSON 值"""
    cur = data
    for part in (path or "").split("."):
        if not part:
            continue
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list) and part.isdigit():
            idx = int(part)
            cur = cur[idx] if idx < len(cur) else None
        else:
            return None
    return cur


async def send_http_gateway(cfg: Dict[str, Any], phones: List[str], text: str) -> Dict[str, Any]:
    """调用 HTTP 短信网关

    配置项:
      url                 网关地址（必填）
      method              GET / POST，默认 POST
      content_type        json / form / query，默认 json
      params              参数模板，支持 {phones} {text} {phone} 占位符
      headers             自定义请求头
      basic_auth          可选 {"username": "...", "password": "..."}
      success_mode        status / keyword / json，默认 status
      success_status      默认 200
      success_keyword     成功关键字
      success_json_path   如 "code"
      success_json_value  如 "0"
      timeout             默认 10 秒
    """
    url = (cfg.get("url") or "").strip()
    if not url:
        raise SmsError("HTTP 短信网关缺少 url")

    method = (cfg.get("method") or "POST").upper()
    content_type = (cfg.get("content_type") or "json").lower()
    timeout = int(cfg.get("timeout") or 10)

    phones_joined = ",".join(phones)
    variables = {"phones": phones_joined, "text": text, "message": text}

    params = _render(cfg.get("params") or {}, variables)
    if not params:
        params = {"phones": phones_joined, "content": text}

    headers = dict(cfg.get("headers") or {})
    auth = None
    basic = cfg.get("basic_auth") or {}
    if basic.get("username"):
        auth = aiohttp.BasicAuth(str(basic.get("username")), str(basic.get("password") or ""))

    request_kwargs: Dict[str, Any] = {
        "headers": headers,
        "timeout": aiohttp.ClientTimeout(total=timeout),
    }
    if auth:
        request_kwargs["auth"] = auth

    if method == "GET" or content_type == "query":
        request_kwargs["params"] = {k: str(v) for k, v in params.items()}
    elif content_type == "form":
        request_kwargs["data"] = {k: str(v) for k, v in params.items()}
    else:
        # 必须手动 ensure_ascii=False，否则中文会变成字面量 \uXXXX 发给网关。
        headers.setdefault("Content-Type", "application/json; charset=utf-8")
        request_kwargs["data"] = json.dumps(params, ensure_ascii=False).encode("utf-8")

    async with aiohttp.ClientSession() as session:
        async with session.request(method, url, **request_kwargs) as resp:
            body = (await resp.text())[:1000]
            status = resp.status

    mode = (cfg.get("success_mode") or "status").lower()
    success = False
    detail = ""

    if mode == "status":
        expect = int(cfg.get("success_status") or 200)
        success = status == expect
        detail = f"HTTP {status}"
    elif mode == "keyword":
        keyword = str(cfg.get("success_keyword") or "ok")
        success = keyword.lower() in body.lower()
        detail = f"HTTP {status} 关键字[{keyword}] {'命中' if success else '未命中'}"
    elif mode == "json":
        try:
            data = json.loads(body)
        except Exception:  # noqa: BLE001
            data = None
        path = str(cfg.get("success_json_path") or "code")
        expect = str(cfg.get("success_json_value") or "0")
        actual = _json_get(data, path) if data is not None else None
        success = str(actual) == expect
        detail = f"HTTP {status} {path}={actual} (期望 {expect})"
    else:
        success = 200 <= status < 300
        detail = f"HTTP {status}"

    if not success:
        raise SmsError(f"网关返回失败：{detail}；响应：{body[:300]}")

    return {"provider": "http", "http_status": status, "detail": detail, "response": body[:300]}


# ==================== 1b) MFM-920E HTTP 通知接口 ====================
def _mfm_endpoint(url: str) -> str:
    value = str(url or "").strip()
    if not value:
        raise SmsError("MFM-920E 缺少网关地址")
    if not value.startswith(("http://", "https://")):
        value = "http://" + value
    parsed = urllib.parse.urlparse(value)
    if not parsed.path or parsed.path == "/":
        value = value.rstrip("/") + "/cgi-bin/NoticePush"
    return value


async def send_mfm920e(cfg: Dict[str, Any], phones: List[str], text: str) -> Dict[str, Any]:
    """MFM-920E 智能告警服务模块 HTTP 接口。

    报文与设备例程一致：
      {"To":["手机号"],"Type":"SMS","Encoding":"UTF-8","Text":"告警正文"}
    设备成功响应通常为 {"Reply":"OK"}，不能仅凭 HTTP 200 判断成功。
    """
    url = _mfm_endpoint(cfg.get("url"))
    message_type = str(cfg.get("message_type") or "SMS").strip() or "SMS"
    if message_type.lower() not in ("sms", "call", "all", "broadcast"):
        raise SmsError("MFM-920E 消息类型仅支持 SMS/Call/All/Broadcast")
    payload = {
        "To": list(phones),
        "Type": message_type,
        "Encoding": "UTF-8",
        "Text": text,
    }
    timeout = int(cfg.get("timeout") or 10)
    body_bytes = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url,
            data=body_bytes,
            headers={"Content-Type": "application/json; charset=utf-8"},
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            body = (await resp.text())[:1000]
            status = resp.status
    reply = ""
    try:
        data = json.loads(body)
        reply = str((data or {}).get("Reply") or (data or {}).get("reply") or "")
    except Exception:  # noqa: BLE001
        reply = ""
    if status >= 300 or reply.strip().upper() != "OK":
        raise SmsError(f"MFM-920E 返回失败：HTTP {status}，Reply={reply or '-'}；响应：{body[:300]}")
    return {"provider": "mfm920e", "http_status": status, "reply": reply, "response": body[:300]}


# ==================== 2) SMPP 3.4 ====================
class _Pdu:
    """极简 SMPP PDU 编码/解码"""

    BIND_TRANSCEIVER = 0x00000009
    BIND_TRANSCEIVER_RESP = 0x80000009
    SUBMIT_SM = 0x00000004
    SUBMIT_SM_RESP = 0x80000004
    UNBIND = 0x00000006
    UNBIND_RESP = 0x80000006
    ENQUIRE_LINK = 0x00000015
    ENQUIRE_LINK_RESP = 0x80000015
    DELIVER_SM = 0x00000005

    @staticmethod
    def c_octet(text: str) -> bytes:
        return (text or "").encode("utf-8") + b"\x00"

    @staticmethod
    def build(command_id: int, sequence: int, body: bytes,
              command_status: int = 0) -> bytes:
        length = 16 + len(body)
        return (
            length.to_bytes(4, "big")
            + command_id.to_bytes(4, "big")
            + command_status.to_bytes(4, "big")
            + sequence.to_bytes(4, "big")
            + body
        )

    @staticmethod
    def header(data: bytes) -> Tuple[int, int, int, int]:
        length = int.from_bytes(data[0:4], "big")
        command_id = int.from_bytes(data[4:8], "big")
        status = int.from_bytes(data[8:12], "big")
        sequence = int.from_bytes(data[12:16], "big")
        return length, command_id, status, sequence

    @staticmethod
    def read_c_octet(data: bytes, offset: int) -> Tuple[str, int]:
        end = data.find(b"\x00", offset)
        if end < 0:
            end = len(data)
        return data[offset:end].decode("utf-8", errors="ignore"), end + 1


async def _smpp_recv(reader: asyncio.StreamReader, timeout: float) -> bytes:
    head = await asyncio.wait_for(reader.readexactly(4), timeout=timeout)
    length = int.from_bytes(head, "big")
    if length < 16 or length > 20000:
        raise SmsError(f"SMPP 报文长度异常: {length}")
    rest = await asyncio.wait_for(reader.readexactly(length - 4), timeout=timeout)
    return head + rest


def _encode_sms_text(text: str) -> Tuple[bytes, int]:
    """编码短信内容：纯 ASCII 用 GSM 默认编码(0)，含中文用 UCS2(8)"""
    try:
        text.encode("ascii")
        return text.encode("ascii"), 0
    except UnicodeEncodeError:
        return text.encode("utf-16-be"), 8


async def send_smpp(cfg: Dict[str, Any], phones: List[str], text: str) -> Dict[str, Any]:
    """通过 SMPP 3.4 发送短信（bind_transceiver → submit_sm → unbind）

    配置项:
      host / port           SMSC 地址端口，默认 2775
      system_id / password  账号密码
      system_type           通常空字符串
      source_addr           主叫号码/短信端口号
      source_ton/npi        默认 5/0（Alphanumeric）
      dest_ton/npi          默认 1/1（International/ISDN）
      use_message_payload   true 时用 TLV(0x0424) 发送长短信，默认 true
      timeout               连接与响应超时，默认 10 秒
    """
    host = (cfg.get("host") or "").strip()
    if not host:
        raise SmsError("SMPP 缺少 host")
    port = int(cfg.get("port") or 2775)
    timeout = float(cfg.get("timeout") or 10)
    system_id = str(cfg.get("system_id") or "")
    password = str(cfg.get("password") or "")
    if not system_id:
        raise SmsError("SMPP 缺少 system_id")

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port), timeout=timeout
        )
    except Exception as exc:  # noqa: BLE001
        raise SmsError(f"SMPP 连接 {host}:{port} 失败: {exc}") from exc

    seq = 0
    try:
        # ---- bind_transceiver ----
        seq += 1
        body = (
            _Pdu.c_octet(system_id)
            + _Pdu.c_octet(password)
            + _Pdu.c_octet(str(cfg.get("system_type") or ""))
            + bytes([0x34])                       # interface_version 3.4
            + bytes([int(cfg.get("source_ton") or 5)])
            + bytes([int(cfg.get("source_npi") or 0)])
            + _Pdu.c_octet("")                    # address_range
        )
        writer.write(_Pdu.build(_Pdu.BIND_TRANSCEIVER, seq, body))
        await writer.drain()

        resp = await _smpp_recv(reader, timeout)
        _, cmd_id, status, resp_seq = _Pdu.header(resp)
        if cmd_id != _Pdu.BIND_TRANSCEIVER_RESP:
            raise SmsError(f"SMPP 绑定响应异常: cmd=0x{cmd_id:08X}")
        if status != 0:
            raise SmsError(f"SMPP 绑定被拒绝: command_status=0x{status:08X}")

        # ---- 逐个号码 submit_sm ----
        results = []
        for phone in phones:
            seq += 1
            payload, data_coding = _encode_sms_text(text)
            use_tlv = bool(cfg.get("use_message_payload", True)) and len(payload) > 160

            body = (
                _Pdu.c_octet(str(cfg.get("service_type") or ""))
                + bytes([int(cfg.get("source_ton") or 5)])
                + bytes([int(cfg.get("source_npi") or 0)])
                + _Pdu.c_octet(str(cfg.get("source_addr") or ""))
                + bytes([int(cfg.get("dest_ton") or 1)])
                + bytes([int(cfg.get("dest_npi") or 1)])
                + _Pdu.c_octet(phone)
                + bytes([0x00])                   # esm_class
                + bytes([0x00])                   # protocol_id
                + bytes([0x00])                   # priority_flag
                + _Pdu.c_octet("")                # schedule_delivery_time
                + _Pdu.c_octet("")                # validity_period
                + bytes([0x00])                   # registered_delivery
                + bytes([0x00])                   # replace_if_present_flag
                + bytes([data_coding])
                + bytes([0x00])                   # sm_default_msg_id
            )

            if use_tlv:
                body += bytes([0x00])             # sm_length = 0（内容走 TLV）
                body += (0x0424).to_bytes(2, "big") + len(payload).to_bytes(2, "big") + payload
            else:
                # 单条最大 254 字节，超出截断
                payload = payload[:254]
                body += bytes([len(payload)]) + payload

            writer.write(_Pdu.build(_Pdu.SUBMIT_SM, seq, body))
            await writer.drain()

            while True:
                resp = await _smpp_recv(reader, timeout)
                _, cmd_id, status, resp_seq = _Pdu.header(resp)
                if cmd_id == _Pdu.ENQUIRE_LINK:
                    seq += 1
                    writer.write(_Pdu.build(_Pdu.ENQUIRE_LINK_RESP, seq, b"", 0))
                    await writer.drain()
                    continue
                break

            if cmd_id != _Pdu.SUBMIT_SM_RESP:
                raise SmsError(f"SMPP submit_sm 响应异常: cmd=0x{cmd_id:08X}")
            if status != 0:
                raise SmsError(f"号码 {phone} 提交失败: command_status=0x{status:08X}")
            message_id = resp[16:].split(b"\x00", 1)[0].decode("utf-8", "ignore")
            results.append({"phone": phone, "message_id": message_id})

        # ---- unbind ----
        seq += 1
        writer.write(_Pdu.build(_Pdu.UNBIND, seq, b""))
        await writer.drain()
        try:
            await _smpp_recv(reader, 3)
        except Exception:  # noqa: BLE001
            pass

        return {"provider": "smpp", "submitted": len(results), "messages": results}
    finally:
        try:
            writer.close()
            await writer.wait_closed()
        except Exception:  # noqa: BLE001
            pass


# ==================== 3) 串口 GSM 模块 ====================
def _send_serial_sync(cfg: Dict[str, Any], phones: List[str], text: str) -> Dict[str, Any]:
    if not HAS_PYSERIAL:
        raise SmsError("串口短信需要 pyserial，请执行: pip install pyserial")

    port = cfg.get("port")
    if not port:
        raise SmsError("串口短信缺少 port（如 /dev/ttyUSB0 或 COM3）")
    baudrate = int(cfg.get("baudrate") or 115200)
    timeout = float(cfg.get("timeout") or 5)
    # 中文短信需要 UCS2 编码模式
    is_ascii = text.isascii()

    try:
        ser = serial.Serial(port, baudrate, timeout=timeout)
    except Exception as exc:  # noqa: BLE001
        raise SmsError(f"打开串口 {port} 失败: {exc}") from exc

    def at(cmd: str, wait: float = 1.0) -> str:
        ser.write((cmd + "\r").encode("ascii"))
        time.sleep(wait)
        data = ser.read(ser.in_waiting or 64)
        return data.decode("utf-8", errors="ignore")

    sent = []
    try:
        at("AT")
        # 文本模式
        at("AT+CMGF=1")
        if not is_ascii:
            at('AT+CSCS="UCS2"')
            at("AT+CSMP=17,167,0,8")
        else:
            at('AT+CSCS="GSM"')
            at("AT+CSMP=17,167,0,0")

        for phone in phones:
            ser.write(f'AT+CMGS="{phone}"\r'.encode("ascii"))
            time.sleep(0.5)
            body = text if is_ascii else text.encode("utf-16-be").hex().upper()
            ser.write(body.encode("ascii") + bytes([0x1A]))  # Ctrl+Z 结束
            time.sleep(2.0)
            resp = ser.read(ser.in_waiting or 128).decode("utf-8", errors="ignore")
            if "OK" not in resp.upper():
                raise SmsError(f"号码 {phone} 发送失败: {resp.strip()[:120]}")
            sent.append({"phone": phone})
    finally:
        try:
            ser.close()
        except Exception:  # noqa: BLE001
            pass

    return {"provider": "serial", "submitted": len(sent), "messages": sent}


async def send_serial(cfg: Dict[str, Any], phones: List[str], text: str) -> Dict[str, Any]:
    """串口发送（阻塞调用放入线程池，避免卡住事件循环）"""
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, _send_serial_sync, cfg, phones, text)


# ==================== 统一入口 ====================
async def send_sms(cfg: Dict[str, Any], phones: Any, text: str) -> Dict[str, Any]:
    """按 provider 发送短信

    :param cfg: 通道 config
    :param phones: 手机号（字符串或列表）
    :param text: 短信正文
    """
    phone_list = normalize_phones(phones if phones else cfg.get("phones"))
    if not phone_list:
        raise SmsError("未配置接收手机号")

    body = truncate_text(text, int(cfg.get("max_length") or 500))
    provider = (cfg.get("provider") or "http").lower()

    if provider == "mfm920e":
        result = await send_mfm920e(cfg, phone_list, body)
    elif provider == "http":
        result = await send_http_gateway(cfg, phone_list, body)
    elif provider == "smpp":
        result = await send_smpp(cfg, phone_list, body)
    elif provider == "serial":
        result = await send_serial(cfg, phone_list, body)
    else:
        raise SmsError(f"不支持的短信 provider: {provider}（可选 mfm920e/http/smpp/serial）")

    result["phones"] = phone_list
    result["text_length"] = len(body)
    return result
