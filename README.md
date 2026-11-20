# 综合运维管理平台（IOP）

> 面向网络设备、安全设备、服务器、数据库、网站与虚拟化环境的统一监控运维平台。
>
> **项目已闭源。** 因国内某大型厂商已完成对该项目的收购，项目需遵守商业合作与授权规则，源代码不再公开发布。本文档仅用于产品介绍与商务沟通。

## 为什么闭源

本项目早期以公开方式迭代。随着产品能力完善，国内某大型厂商已完成对该项目的收购。为遵守收购协议、商业授权和客户交付规则，项目不再公开源代码，也不再通过公开仓库分发安装包。

这不影响已有客户的私有化部署与授权使用。需要源码级合作、私有化交付、二次开发或商业授权的单位，可通过下方联系方式进行商务沟通。

## 产品简介

IOP 是一套可私有化部署的综合运维平台，面向内网、机房和混合环境，覆盖“资产—监控—告警—巡检—备份—可视化—协作”的完整闭环。

- 统一纳管网络设备、安全设备、服务器、数据库、网站、虚拟化和容器环境。
- 无代理采集主机与数据库指标，不要求在业务服务器安装额外 Agent。
- 提供 SNMP、SSH、WinRM 和数据库原生协议采集。
- 支持主备高可用、离线部署、商业授权和独立升级服务器。

## 核心功能

### 1. 网络与资产监控

- SNMP v1/v2c/v3：CPU、内存、磁盘、温度、电源、风扇、接口流量、端口状态。
- 资产分组、机房/机柜/U 位、厂商型号、维保和自定义字段。
- Ping、TCP 端口、网站可用性、HTTPS 证书到期监控。
- LLDP 邻居发现、网络拓扑编辑、链路流量与设备状态联动。
- 设备重启误报抑制：容忍采集周期内的 uptime 抖动，同时识别真实重启和计数器回绕。

<p align="center">
<img width="1595" height="899" alt="assets" src="https://github.com/user-attachments/assets/666fd22b-6b93-4977-bf0e-67303f884889" />
</p>

### 2. 主机与数据库无代理监控

- **Linux**：SSH 采集 CPU、内存、磁盘、负载、网卡、进程、服务、运行时长。
- **Windows Server**：WinRM 采集 CPU、内存、磁盘、网卡、进程、自动启动服务、事件日志、启动时间。
- **数据库**：MySQL/MariaDB、PostgreSQL、人大金仓、SQL Server、Oracle、MongoDB、Redis/Valkey、达梦。
- 指标覆盖连接数、活跃会话、QPS/TPS、慢查询、锁、复制延迟、数据库容量。
- 服务异常告警显示**服务名、退出码和 journal 原因**，例如：
  `mcelog.service：进程退出码 1；日志：CPU is unsupported`
- 采集凭据加密存储；支持连接测试、批量新增、批量启停、批量采集、阈值模板、趋势和容量预测。
- 跨网段场景可部署采集中继。

<p align="center">
<img width="1600" height="900" alt="hostdb-3d" src="https://github.com/user-attachments/assets/d5511335-c84c-4bd7-ac74-d6e9e32b5839" />
</p>

### 3. 告警、巡检与可视化

- 告警去重、分级、确认、恢复、通知渠道和 Webhook。
- 巡检计划、巡检报告、配置备份、版本回退、诊断包。
- 资产大屏、虚拟化大屏、网站大屏、主机数据库 3D 大屏、AIOps 大屏。
- 3D 场景按内容包围盒和视口比例自动居中/拉远，适配 1366×768、1600×900、1920×1080 等分辨率。
- 明亮/暗色主题切换。

### 4. 平台与协作

- RBAC、资产组、审计日志、登录策略、验证码、双因素认证、登录锁定。
- 即时通信、群组、音视频、白板、屏幕共享、悬浮助手。
- 主备高可用：PostgreSQL 共享/流复制、keepalived VIP、强制一致性校验、TURN 中继随 VIP 漂移。
- 级联管理、MIB 管理、AI 运维（只读问答/分析/报告）。
- 升级包上传或手动升级服务器（`latest.json`）；支持备份、回滚和健康检查。

<p align="center">
 <img width="1591" height="900" alt="dark-theme" src="https://github.com/user-attachments/assets/2ed77159-2a5f-4683-b39f-840550f19735" />

</p>

## 技术架构

| 层次 | 技术 |
|---|---|
| 前端 | Vue 3、Vite、Element Plus、ECharts、AntV X6、Three.js |
| 后端 | Python 3.12、FastAPI、SQLAlchemy |
| 数据库 | PostgreSQL（自动供给，失败回退 SQLite）、MySQL、SQLite |
| 缓存 | Redis（自动供给，失败回退进程内缓存） |
| 采集 | SNMP、SSH/Paramiko、WinRM、数据库原生协议 |
| 部署 | Linux systemd、Docker Compose、Linux 离线包 |
| 高可用 | PostgreSQL 流复制、keepalived VIP、coturn/TURN |

## 部署方式

- **在线安装**：解压发布包后执行 `deploy/install-systemd.sh`。
- **离线安装**：发布包内置 Python 运行时、Python wheels、coturn、ipmitool 和常用 OS 包，执行 `deploy/install-offline.sh`。
- **高可用**：两台节点分别导入商业授权；共享或流复制 PostgreSQL；keepalived 管理 VIP。
- **端口**：Web 80/443；内部 API 8000 仅监听本机；TURN 3478 和中继 49160–49200（启用音视频时）。

## 授权模式

| 版本 | 资产额度 | 有效期 | HA 节点 | 功能 |
|---|---:|---|---:|---|
| 试用版 | 50 台 | 30 天 | 50 个 | 全部功能 |
| 商业版 | 按合同 | 按合同/永久 | 每节点独立授权 | 全部功能 |

- 未导入商业授权时自动进入试用版。
- 授权使用 Ed25519 签名，绑定机器码，不绑定产品发布版本。
- 商业高可用每台节点分别导入自己的授权文件，不共享授权。

<p align="center">
 <img width="1600" height="900" alt="login" src="https://github.com/user-attachments/assets/e25e6de2-d226-4c7a-b1ce-2ae205afbcf9" />

</p>

## 商务与授权联系

如需私有化部署、商业授权、源码级合作、二次开发或渠道合作，请联系：

- **联系人**：张总
- **邮箱**：ykzhangxian@163.com
- **电话**：13057649527

> 本项目已闭源，不提供公开源代码下载。未经授权，请勿复制、分发或用于商业交付。
