# 短信网关配置指南

本文档说明平台当前支持的短信通道，以及 **融智云 MFM-920E 智能告警服务模块** 的对接方式。

配置入口：

```text
告警渠道 → 新建通道 / 编辑通道 → 短信
```

保存后务必点击 **“发送测试”**，并到发送日志查看结果。

---

## 0. 短信正文与事件类型

平台发送的告警短信默认包含事件类型，例如：

```text
【告警】核心交换机-01
事件类型：告警；核心交换机-01 CPU使用率超过阈值 (11-11 22:12)
```

恢复短信包含：

```text
事件类型：恢复；...
```

短信和邮件保持纯文本，不使用 Webhook/Markdown 的红色/绿色标记；短信正文长度按运营商和网关限制截断。自定义短信模板支持 `{level}`、`{level_label}`、`{device_name}`、`{ip_address}`、`{alert_type}`、`{message}`、`{value}`、`{threshold}`、`{source}`、`{time}` 占位符。

## 1. MFM-920E 原生 HTTP 接口（推荐）

MFM-920E 资料中的标准通知接口：

```text
POST http://<设备IP>/cgi-bin/NoticePush
Content-Type: application/json; charset=utf-8
```

请求体：

```json
{
  "To": ["13800000000", "13900000000"],
  "Type": "SMS",
  "Encoding": "UTF-8",
  "Text": "告警正文"
}
```

成功响应示例：

```json
{"Reply":"OK"}
```

### 平台配置

| 字段 | 填写值 |
|---|---|
| 接收手机号 | 一个或多个手机号，用逗号分隔 |
| 网关方式 | `MFM-920E 智能告警模块` |
| 网关地址 | `http://192.168.0.100` |
| 通知类型 | `SMS` / `Call` / `All` |
| 超时 | 建议 10 秒 |

网关地址可以只填设备 IP：

```text
http://192.168.0.100
```

平台会自动补全：

```text
/cgi-bin/NoticePush
```

也可以直接填写完整地址：

```text
http://192.168.0.100/cgi-bin/NoticePush
```

### 成功判定

平台会同时检查：

1. HTTP 状态码不是失败状态；
2. 设备返回 JSON 中的 `Reply` 必须为 `OK`。

**HTTP 200 但 `Reply` 不是 `OK` 时，平台会判定失败**，不会把未提交成功的短信记录为成功。

### 设备侧检查

1. 在浏览器或 `curl` 中确认设备接口可达：
   ```bash
   curl -v -X POST "http://192.168.0.100/cgi-bin/NoticePush" \
     -H "Content-Type: application/json; charset=utf-8" \
     -d '{"To":["13800000000"],"Type":"SMS","Encoding":"UTF-8","Text":"平台测试"}'
   ```
2. 确认返回 `{"Reply":"OK"}`；
3. 确认设备已插卡、注册到运营商网络、短信余额/套餐正常；
4. 确认平台服务器到设备 `80/TCP` 网络可达；
5. 手机号不带空格、短横线，使用 `13800000000` 格式。

### 中文短信

MFM-920E 资料中 `Encoding` 支持 `UTF-8`。平台固定发送 UTF-8 中文正文。若现场设备固件只接受其他编码，请先升级设备固件，或使用平台通用 HTTP 模式并按设备要求配置参数模板。

---

## 2. 通用 HTTP 短信网关

适用于第三方短信平台或其他厂商的 HTTP 接口。

| 字段 | 说明 |
|---|---|
| 网关地址 | 完整 HTTP/HTTPS URL |
| 请求方法 | GET 或 POST |
| 消息格式 | JSON / 表单 / Query |
| 参数模板 | JSON 对象，支持 `{phones}`、`{text}`、`{message}` |
| 请求头 | 可选 JSON，例如鉴权 Token |
| 成功判定 | HTTP 状态码 / 响应关键字 / JSON 字段 |
| 超时 | 默认 10 秒 |

示例：某平台要求表单参数 `mobile` 和 `content`：

```json
{
  "mobile": "{phones}",
  "content": "{text}"
}
```

选择：

```text
消息格式：表单
方法：POST
成功判定：JSON 字段
字段路径：code
期望值：0
```

注意：通用 HTTP 的 `{phones}` 是逗号拼接的字符串。MFM-920E 要求 `To` 是数组，请使用第 1 节的 **MFM-920E 原生模式**，不要用通用模式拼接数组。

---

## 3. SMPP 3.4 网关

适用于运营商级短信中心或 SMPP 短信平台。

| 字段 | 说明 |
|---|---|
| SMSC 地址 | 网关 IP 或域名 |
| 端口 | 默认 2775，以运营商提供为准 |
| system_id | 账号 |
| password | 密码 |
| 主叫号码 | 短信端口号/主叫号，按运营商要求 |
| source TON / dest TON | 按运营商要求，通常 5 / 1 |
| 长短信 | 建议开启，使用 message_payload |

要求：

- 平台服务器到 SMSC 的 TCP 端口可达；
- system_id/password 已在运营商侧开通；
- 短信签名、模板和发送时段符合运营商要求。

SMPP 不使用 MFM-920E 的 `/cgi-bin/NoticePush` 接口。

---

## 4. 串口 GSM 模块（AT 指令）

适用于标准 AT 指令串口短信猫，不是 MFM-920E 的 JSON 串口协议。

| 字段 | 说明 |
|---|---|
| 串口设备 | Linux：`/dev/ttyUSB0` |
| 波特率 | 按模块要求，常见 115200 |
| 服务器依赖 | `pyserial` |

Linux 检查：

```bash
ls -l /dev/ttyUSB0
sudo usermod -aG dialout <运行平台服务的用户>
```

修改用户组后需要重启服务。

---

## 5. MFM-920E 的其他设备接口

MFM-920E 资料还提供：

- **TCP Client API**：设备 `8000/TCP`，发送同样的 JSON 字符串；
- **串口 JSON**：`9600, 8N1`，直接发送 JSON 字符串，不是 AT 指令；
- 电话语音：`Type=Call`；
- 短信 + 电话：`Type=All`；
- 广播：`Type=Broadcast`。

平台当前推荐使用 **MFM-920E 原生 HTTP** 完成告警短信/电话报送。TCP 和串口 JSON 需要平台增加对应传输实现；在没有实现前，不要用平台“串口 GSM 模块（AT）”模式连接 MFM-920E，因为两者协议不同。

MFM-920E 的 HTTP 和 TCP 请求体格式一致，现场调试时可先用 HTTP 验证号码、卡片和内容，再切换传输方式。

---

## 6. 测试与排查

### 平台测试

1. 保存短信通道；
2. 点击“发送测试”；
3. 查看弹窗结果；
4. 进入“发送日志”，确认状态和正文。

### 常见问题

| 现象 | 检查 |
|---|---|
| HTTP 200 但发送失败 | 响应是否 `{"Reply":"OK"}` |
| 连接超时 | 平台到设备 IP/端口、防火墙、设备是否在线 |
| 401/403 | 通用 HTTP 的 Token/账号配置 |
| 中文乱码 | 设备编码设置，MFM 使用 UTF-8 |
| 号码格式错误 | 使用纯 11 位手机号，逗号分隔 |
| 短信提交成功但未收到 | 设备 SIM 卡、运营商网络、欠费、短信中心配置 |
| 电话语音失败 | `Type=Call`、设备语音通道和号码白名单 |
| SMPP 绑定失败 | system_id/password、TON/NPI、SMSC 端口 |
| 串口打不开 | 设备路径、权限、波特率、是否被其他程序占用 |

### 命令检查

```bash
# MFM-920E HTTP 连通性
curl -v http://192.168.0.100/cgi-bin/NoticePush

# 查看平台日志
journalctl -u snmp-nms -n 100 --no-pager
tail -f /opt/snmp-monitor/data/logs/backend.log
```

---

## 7. 安全建议

- 短信网关只开放在受控管理网，不要直接暴露公网；
- 不要把短信平台 Token、设备密码写入 README 或代码；
- 短信正文可能包含设备名、IP、告警内容，注意接收人范围；
- 生产环境建议为短信网关设置独立账号和最小权限。
