# 智能运维服务平台（IOP）

**IOP = Intelligent Operations Platform**

面向网络设备、安全设备、服务器、网站和虚拟化/容器环境的统一监控运维平台，覆盖资产管理、SNMP 采集、拓扑、大屏、告警、巡检、设备备份、机房、MIB、AI 运维、级联和系统管理。

- 当前版本：**v2.21.35**
- 授权签发平台：**License Studio v2.10.1**
- 后端：Python 3.12 / FastAPI / SQLAlchemy
- 前端：Vue 3 / Vite / Element Plus / ECharts / AntV X6
- 数据库：PostgreSQL（自动供给，失败回退 SQLite）/ MySQL / SQLite
- 缓存：Redis（自动供给，失败回退进程内缓存）
- 部署：Linux systemd / Docker Compose / Windows 本地运行
- 发布包：`IOP-v<版本>.zip`
- 英文说明：[README.en.md](README.en.md)
- 离线安装：[README-OFFLINE.md](README-OFFLINE.md) / [English](README-OFFLINE.en.md)
- 短信网关配置：[SMS-GATEWAY.md](SMS-GATEWAY.md)

> 发布包不包含运行数据、数据库、授权文件、私钥、上传文件和截图。详细安全要求见 [SECURITY.md](SECURITY.md)。

---

## 1. 核心能力

### 1.1 统一监控

- SNMP v1 / v2c / v3 设备采集；
- ICMP Ping、TCP 端口探测；
- CPU、内存、温度、磁盘、电源、接口流量、服务器传感器；
- 网站 HTTP/HTTPS 可用性、状态码、响应时间和证书；
- VMware、Proxmox、H3C CAS、KVM、Docker、Kubernetes 只读纳管；
- 设备、网站、虚拟化三类告警统一进入告警中心。

### 1.2 告警中心

告警来源：

```text
设备告警
网站告警
虚拟化 / 容器平台告警
```

告警生命周期：

```text
产生 → 未确认 → 确认/自动恢复 → 历史
```

特性：

- 左侧“告警中心”角标与告警中心使用同一套“未确认且未恢复”计数；
- 自动恢复后同步从当前告警和左侧角标移除；
- 角标最长 10 秒刷新，告警中心页面刷新时会触发即时更新；
- 平台级告警覆盖连接失败、认证失败、同步失败、同步超时；
- 支持告警级别调整、通知开关、批量确认和告警抑制；
- 外发邮件、Webhook 和上级平台告警携带设备位置、机房、机柜、楼层和详细位置。

### 1.3 资产与告警规则

- 设备增删改查、批量修改、复制、导入导出、二维码标签；
- 资产群组和数据权限；
- 资产来源：手工添加 / 自动发现；
- 机房、机柜、U 位、功率和楼层/位置；
- 自定义告警规则：
  - 仅展示用户创建的自定义告警规则，不再回退显示系统内置规则；
  - 规则阈值同步到仪表盘指标设置，仪表盘对应预警/告警值自动更新并锁定；
  - 支持指标、当前值、阈值和当前告警级别展示。

### 1.4 网站、虚拟化与 AI

- 网站监控：可用性、响应时间、状态码、证书有效期；
- 虚拟化：虚拟机、宿主机、平台告警；
- AI 运维：只读问答、告警研判、资产统计、报告；
- AI 不直接执行写操作，不绕过权限和授权。

### 1.5 级联与高可用

- 分支主动出站 WSS 连接总部；
- 业务帧使用令牌派生密钥二次加密；
- 支持公网中继、内网穿透或 WireGuard/Tailscale 等虚拟组网；
- 集群和级联按授权版本开放。

### 1.6 多语言

界面支持：

```text
简体中文 / 繁體中文 / English / 日本語 / 한국어
Deutsch / Français / Español / Português (Brasil)
Русский / العربية / हिन्दी
```

阿拉伯语自动启用 RTL，Element Plus 组件和日期格式同步切换。

---

## 2. 功能模块

| 模块 | 路径 | 主要能力 |
|---|---|---|
| 监控总览 | `/dashboard` | 资产、告警、资源使用率和设备状态 |
| 设备指标工作台 | `/instrument` | 指标卡片、分组、指标选择、告警着色 |
| 大屏展示 | `/bigscreen` | 网站、AI 运维、资产、虚拟化大屏 |
| AI 智能运维 | `/ai` | 只读问答、告警分析、报告 |
| 资产管理 | `/devices` | 设备、批量修改、导入导出、告警规则 |
| 设备巡检 | `/inspection` | 定时/手动巡检、Word 报告 |
| 设备备份 | `/config-backups` | 网络设备配置备份和历史 |
| 设备凭据 | `/credentials` | 统一维护 SSH 凭据并分配给资产 |
| 自动发现 | `/discovery` | 网段扫描、SNMP 识别、批量入库 |
| 即时通信 | `/im` | 私聊、群聊、音视频、白板 |
| 系统工具 | `/tools` | Ping、路由追踪、SNMP Walk、端口、SSH、抓包 |
| MIB 管理 | `/mibs` | MIB 导入、厂商/型号匹配、在线 MIB、AI 辅助 |
| 机房管理 | `/rooms` | 机房、机柜、U 位、3D 数字孪生 |
| 网络拓扑 | `/topology` | 节点、链路、布局、LLDP 发现 |
| 级联管理 | `/cascade` | 总部/分支加密隧道和数据同步 |
| 虚拟化管理 | `/virtualization` | 虚拟机、宿主机、虚拟化/容器平台告警 |
| 网站监控 | `/website` | HTTP/HTTPS、响应时间、证书 |
| 告警中心 | `/alerts` | 设备/网站/虚拟化告警统一处理 |
| 告警渠道 | `/notifications` | 邮件、Webhook、短信、上级平台 |
| 用户权限 | `/users` | 用户、角色、群组、菜单权限 |
| 审计日志 | `/system/audit` | 登录和管理操作审计 |
| 系统配置 | `/system/settings` | 通用、安全、采集、备份、语言、网络 |
| 授权信息 | `/system/license` | 机器码、版本、价格、功能和激活 |

### 局域网音视频通话

即时通信默认面向局域网优化：

- 不再默认依赖公网 Google STUN；
- 同一网段优先使用浏览器 host candidate 直连；
- 页面必须通过 HTTPS 访问，HTTP 页面浏览器禁止调用麦克风/摄像头；
- 跨 VLAN、防火墙隔离或终端 NAT 环境，部署 coturn 或 TURN 服务后配置：

```env
WEBRTC_TURN_URLS=turn:192.168.1.10:3478,turns:192.168.1.10:5349
WEBRTC_TURN_USERNAME=nms
WEBRTC_TURN_CREDENTIAL=change-me
WEBRTC_FORCE_RELAY=0
```

TURN 需放通 3478 TCP/UDP 和 5349 TCP/TLS。配置后系统会通过 `/api/im/webrtc-config` 下发给所有用户，无需改前端。

---

## 3. 快速安装

### 3.1 离线和在线安装的选择

- **离线包**：内置独立 Python、全部 wheels、前端 dist，断网可安装；
- **在线安装**：使用系统 Python/pip，从软件源下载依赖；
- **数据库/缓存自动供给**：全新安装默认自动安装 PostgreSQL 和 Redis 并写入连接配置；失败自动回退 SQLite/内存缓存并警告。

离线包如需自动安装 PostgreSQL/Redis，请按目标发行版准备 `offline/os-packages/debian/*.deb` 或 `offline/os-packages/rhel/*.rpm`；发布包不携带跨发行版系统包。

Linux 默认安装目录：

```text
/opt/snmp-monitor
```

默认服务：

```text
snmp-nms.service
snmp-nms-healthcheck.timer
```

### 3.2 离线安装（Linux x86_64）

要求：

- Linux x86_64；
- glibc 2.17+；
- systemd；
- 系统自带 `tar`、`bash`、`coreutils`、`sed`、`grep`、`awk`；
- 不需要系统 Python/pip/venv，不需要 apt/dnf 下载依赖。

```bash
unzip IOP-v2.21.35.zip -d /tmp
cd /tmp/IOP-v2.21.35
sudo bash deploy/apply-permissions.sh
sudo bash deploy/install-offline.sh
```

离线包包含：

```text
offline/python-linux-x86_64.tar.xz   CPython 3.12 独立运行时
offline/bin/busybox                  静态 xz 解压工具
offline/wheels/                      后端依赖 wheels
offline/os-packages/                 可选 PostgreSQL/Redis 系统包
README-OFFLINE.md                    中文离线安装说明
README-OFFLINE.en.md                 English offline guide
```

### 3.3 标准 systemd 安装

适用于可联网的 Linux 主机。

```bash
unzip IOP-v2.21.35.zip -d /tmp
cd /tmp/IOP-v2.21.35
bash deploy/apply-permissions.sh
sudo bash deploy/install-systemd.sh
```

脚本会自动检测 `apt-get` / `dnf` / `yum`，安装 PostgreSQL/Redis，创建 `snmp_nms` 库和 `nms` 用户，验证连接后写入 `DATABASE_URL` / `REDIS_URL`。安装失败只警告并回退 SQLite/内存缓存，不中断部署。

已有 `snmp-nms.env` 默认不自动切换数据库，避免已有 SQLite 数据“消失”。可选参数：

```bash
sudo bash deploy/install-systemd.sh --with-postgres --with-redis
sudo bash deploy/install-systemd.sh --no-postgres --no-redis
sudo bash deploy/install-systemd.sh --offline
```

离线包同样可以执行 `install-systemd.sh`，脚本会自动检测并使用内置 Python 和 wheels。

### 3.4 Docker Compose

```bash
cp .env.example .env
```

至少修改：

```text
POSTGRES_PASSWORD
DATABASE_URL
AUTH_SECRET
AUTH_DEFAULT_PASSWORD
```

启动：

```bash
docker compose up -d --build
```

默认入口：

```text
https://服务器IP/
HTTP 80：308 跳转到 HTTPS
```

可通过 `HTTPS_PORT` / `HTTP_PORT` 修改宿主机端口，默认 `443/80`。

### 3.5 Windows 本地运行

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements.txt
python run_backend.py 8000
```

打开：

```text
http://127.0.0.1:8000/
```

Windows 本地运行用于开发；生产环境优先使用 Linux systemd 或 Docker。

---

## 4. 首次登录与 HTTPS

默认登录：

```text
https://服务器IP/
```

HTTP 80 仅做 308 跳转，`8000` 是内部应用端口，不应对公网直接开放。

首次启动会自动签发 10 年设备自签证书。浏览器首次访问需要手动信任，或在「系统配置 → 登录与安全」上传企业证书。

初始管理员密码文件：

```text
/opt/snmp-monitor/data/initial_admin_password.txt
```

直接查看：

```bash
sudo cat /opt/snmp-monitor/data/initial_admin_password.txt
```

首次登录必须修改初始密码。

如 HTTPS 443 启动失败，系统会临时回退 HTTP 80，管理员登录后可在系统配置中修复。应急强制 HTTP：

```text
WEB_FORCE_HTTP=1
```

不要长期开启。

---

## 5. 授权版本

全新安装不包含商业授权文件，默认进入**开源版**。

| 版本 | 资产上限 | 集群节点 | 有效期 | 默认价格 | 功能 |
|---|---:|---:|---|---:|---|
| 开源版 | 50 | 1 | 永久（可自定义） | 免费 | 全部功能 |
| 商业版 | 100 | 3 | 永久（可自定义） | 100 元/资产自动计算 | 全部功能 |

- 授权文件：`/opt/snmp-monitor/data/license.key`
- 授权绑定机器码；
- 升级安装保留已有授权文件；
- 价格、资产上限、节点数和有效期可在 License Studio 自定义。

---

## 6. 配置与环境变量

systemd 环境文件：

```text
/opt/snmp-monitor/deploy/snmp-nms.env
```

常用变量：

| 变量 | 默认值 | 说明 |
|---|---|---|
| `API_HOST` | `0.0.0.0` | 内部监听地址 |
| `API_PORT` | `8000` | 内部应用端口 |
| `DATABASE_URL` | SQLite | 数据库连接 |
| `AUTH_SECRET` | 自动生成 | 令牌签名密钥，多实例必须一致 |
| `AUTH_DEFAULT_ADMIN` | `admin` | 初始管理员账号 |
| `AUTH_DEFAULT_PASSWORD` | 空 | 为空时随机生成并写入初始密码文件 |
| `CORS_ORIGINS` | 空 | 默认同源；不支持 `*` |
| `REDIS_URL` | 空 | 为空时使用内存缓存 |
| `UPLOAD_DIR` | `data/uploads` | 上传目录 |
| `LOG_DIR` | `data/logs` | 日志目录 |
| `LICENSE_FILE` | `data/license.key` | 授权文件 |
| `COLLECTION_INTERVAL` | `60` | 采集间隔（秒） |
| `CPU_THRESHOLD` | `80` | CPU 内置告警阈值 |
| `MEMORY_THRESHOLD` | `85` | 内存内置告警阈值 |
| `TEMPERATURE_THRESHOLD` | `80` | 温度内置告警阈值 |
| `TEMPERATURE_CRITICAL_THRESHOLD` | `90` | 温度严重阈值 |
| `SQLITE_BUSY_TIMEOUT_MS` | `30000` | SQLite 锁等待 |
| `RUN_BACKGROUND_TASKS` | `1` | 多实例仅主节点设为 1 |
| `METRICS_TOKEN` | 空 | Prometheus 抓取鉴权 |
| `WEB_FORCE_HTTP` | `0` | 应急强制 HTTP，不建议长期开启 |

Web 登录协议、端口和证书保存在数据库系统配置中，默认：

```text
HTTPS 登录：开启
HTTPS 端口：443
HTTP 登录：关闭
HTTP 80：308 跳转
证书：首次启动自动签发 10 年设备自签证书
```

---

## 7. 数据库与 Redis

全新安装默认尝试自动安装 PostgreSQL 和 Redis，并在「系统配置 → 数据库与缓存」显示实际连接状态、延迟、版本和失败原因。安装失败时回退 SQLite/进程内缓存，不会中断部署。

离线自动安装需要把与目标发行版一致的系统包放入：

```text
offline/os-packages/debian/*.deb
offline/os-packages/rhel/*.rpm
```

在联网的同发行版机器生成：

```bash
sudo bash deploy/prepare-offline-os-packages.sh --target debian
sudo bash deploy/prepare-offline-os-packages.sh --target rhel
```

没有系统包时仍可安装平台，但数据库/缓存使用 SQLite/进程内缓存。

### SQLite

默认无需额外数据库：

```text
/opt/snmp-monitor/data/snmp_monitor.db
```

### MySQL

```text
DATABASE_URL=mysql+pymysql://nms:password@127.0.0.1:3306/snmp_nms?charset=utf8mb4
```

### PostgreSQL

```text
DATABASE_URL=postgresql+psycopg2://nms:password@127.0.0.1:5432/snmp_nms
```

### Redis

```text
REDIS_URL=redis://127.0.0.1:6379/0
```

---

## 8. 常见运维命令

```bash
systemctl status snmp-nms
systemctl restart snmp-nms
systemctl stop snmp-nms
journalctl -u snmp-nms -n 200 --no-pager
journalctl -u snmp-nms -f
tail -f /opt/snmp-monitor/data/logs/backend.log
curl -k https://127.0.0.1/api/health
curl http://127.0.0.1:8000/api/health
```

健康检查和指标：

```text
HTTPS 登录：https://服务器IP/
内部健康检查：http://127.0.0.1:8000/api/health
Prometheus：http://127.0.0.1:8000/metrics
API 文档：http://127.0.0.1:8000/docs
```

`8000` 只用于内部应用和本机检查。

---

## 9. 备份、恢复与升级

### 备份

```bash
sudo systemctl stop snmp-nms
sudo tar -czf /root/iop-backup-$(date +%F).tar.gz \
  -C /opt snmp-monitor/data snmp-monitor/deploy/snmp-nms.env
sudo systemctl start snmp-nms
```

SQLite 部署重点是 `data/`。MySQL/PostgreSQL 使用数据库备份工具，同时备份上传文件和授权文件。

### 恢复

```bash
sudo systemctl stop snmp-nms
# 恢复 data/ 和数据库
sudo systemctl start snmp-nms
curl -k https://127.0.0.1/api/health
```

### 升级

升级包保留 `data/`，不要用发布包覆盖运行数据：

```bash
unzip IOP-v<版本>.zip -d /tmp
cd /tmp/IOP-v<版本>
sudo bash deploy/apply-permissions.sh
sudo bash deploy/install-systemd.sh
```

在线更新入口位于系统配置 → 更新。

---

## 10. 跨平台开发与构建规范

本项目开发和构建必须同时兼容 **Linux** 和 **Windows**。

- Python 路径统一使用 `pathlib`，不硬编码盘符或 `/opt`；
- 文本文件统一 UTF-8；
- Linux Shell 脚本使用 LF，Windows 批处理使用 CRLF；
- Linux 入口：`start.sh`、`deploy/install-systemd.sh`、`deploy/install-offline.sh`；
- Windows 入口：`start-backend.ps1`、`start-frontend.ps1`；
- 构建核心统一使用 Python，不把必要逻辑写在 Bash/PowerShell 中；
- 发布构建自动将 `.sh` 规范为 LF，并检查 CRLF；
- 详细规范见 [DEVELOPMENT.md](DEVELOPMENT.md)。

## 11. 构建与发布

前端：

```bash
cd frontend
npm ci
npm run build
```

后端安全门禁：

```bash
python tools/security_check.py
python -m compileall -q backend
```

离线发布包需要准备：

```text
offline/python-linux-x86_64.tar.xz
offline/bin/busybox
offline/wheels/*.whl
offline/manifest.json
offline/SHA256SUMS
```

生成发布目录和 ZIP：

```bash
python tools/build_release.py --force
```

输出：

```text
IOP-v<版本>/
IOP-v<版本>.zip
```

发布包同时包含：

```text
README.md       中文
README.en.md    English
```

版本使用递增构建号，ZIP 根目录为单层 `IOP-v<版本>`，在线更新器可直接识别。

---

## 12. 目录结构

```text
snmp-monitor/
├── backend/                  FastAPI 后端
├── frontend/                 Vue 3 前端
├── deploy/                   systemd / 离线 / 部署脚本
├── tools/                    构建、安全检查、授权、迁移工具
├── mibs/                     内置 MIB
├── offline/                  独立 Python、wheels 和校验文件
├── data/                     运行数据，不进入发布包
├── docker-compose.yml
├── Dockerfile
├── README.md                 中文说明
├── README.en.md              英文说明
├── README-OFFLINE.md         离线安装说明
├── start.sh
└── uninstall.sh
```

---

## 13. 安全要求

发布前必须执行：

```bash
python tools/security_check.py
python -m compileall -q backend
cd frontend && npm run build
```

要求：

- 生产环境必须修改 `AUTH_SECRET`；
- 首次登录必须修改初始密码；
- 不提交 `.env`、`data/`、数据库、`data/license.key`、`data/.auth_secret`、初始密码文件或授权私钥；
- 公网只开放 443；HTTP 80 仅跳转；
- 不要将 `8000` 暴露到公网；
- 级联中继必须使用 TLS 和有效令牌；
- 第三方 API Key、SMTP 密码、SSH 密码不得写入代码或 README；
- 详细安全基线和 OWASP 检查见 [SECURITY.md](SECURITY.md)。

---

## 14. 常见问题

### 访问 `https://IP/` 提示证书不受信任

首次安装使用自签证书，浏览器手动信任即可；生产环境建议上传企业证书。

### 访问 `IP:8000` 返回 `web_gateway_required`

正常保护。请通过 `https://服务器IP/` 访问，`8000` 仅用于本机健康检查。

### 443 端口被占用

停止占用 443 的服务，或修改系统配置中的 HTTPS 端口后重启 `snmp-nms`。HTTPS 启动失败时会临时回退 HTTP 80。

### 左侧告警数量与告警中心不一致

两侧统一统计“未确认且未恢复”的当前告警。已恢复告警保留在告警历史中，不再计入左侧角标。

### 登录报 `database is locked`

确认 SQLite 目录可写并避免多个进程共享同一 SQLite；高并发场景迁移到 MySQL/PostgreSQL。

### 登录后页面空白

确认 `frontend/dist/index.html` 存在，重新构建前端并重启后端。

### 修改前端后不生效

```bash
cd frontend
npm run build
sudo systemctl restart snmp-nms
```

### 离线安装提示缺少依赖

确认使用完整 `IOP-v<版本>.zip`，并校验：

```bash
cd offline
sha256sum -c SHA256SUMS
```

---

## 15. 版本

### v2.21.35

- 机房新增/编辑弹窗移除长、宽、层高输入并统一表单对齐；
- 设备详情按 SNMP 版本显示 v2c 团体名或 v3 用户名、认证/加密协议、密码状态和 Context；
- 资产编辑增加可编辑“维保开始时间”，图标操作行和返回/保存按钮对齐；
- AI 智能运维/语音对话增加多轮会话、真实数据上下文和重置会话；
- 大屏列表满时改为自动滚动，悬停暂停并尊重 reduced-motion；
- 拓扑新增云/互联网出口显示；v2.21.35 已修正为虚拟节点。
- 虚拟化平台增加平台存储、认证失败等告警；
- 告警发送日志显示完整正文；外发正文移除“设备位置”，保留机房/机柜/楼层/位置；
- 在线/离线安装自动供给 PostgreSQL/Redis，失败回退 SQLite/内存缓存；
- 系统配置显示数据库/缓存实际连接状态；
- 新增英文离线部署手册 README-OFFLINE.en.md；
- 离线系统包通过 prepare-offline-os-packages.sh 按目标发行版生成。

### v2.18.25

- 新增 Linux/Windows 双平台开发与构建规范；
- 新增 `.gitattributes` 固定 `.sh`/`.py`/前端文件 LF，`.bat`/`.ps1` CRLF；
- 构建流程强制校验发布包内 `.sh` 不含 CR 换行；
- 新增 `DEVELOPMENT.md`，明确路径、编码、脚本入口和提交检查。

### v2.18.24

- 修复离线安装入口 `install-offline.sh` 的 CRLF 换行导致的 `set: -` 和语法错误；
- 修复离线入口仍检查旧 `.tar.gz` 文件名的问题，统一使用 `python-linux-x86_64.tar.xz`；
- 发布构建自动将复制到发布目录的 `.sh` 脚本规范为 LF。



本 README 对应 **IOP v2.21.35**。

- 中文说明：`README.md`
- 英文说明：`README.en.md`
- 离线安装：`README-OFFLINE.md`
- 安全基线：`SECURITY.md`
