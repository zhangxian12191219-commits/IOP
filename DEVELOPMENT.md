# Linux 开发与构建规范

本项目部署、安装、运行和构建统一使用 **Linux**。发布包只提供 Linux 部署路径。

## 1. 路径

- Python 代码统一使用 `pathlib.Path`；
- 运行环境路径以 `/opt/snmp-monitor` 为准；
- URL 路径使用 `/`，文件系统路径使用 `Path`；
- 临时目录使用 `tempfile`；
- 构建输出目录以项目根目录的父目录为基准。

## 2. 编码与换行

- 所有文本文件使用 UTF-8；
- Python 显式使用 `encoding="utf-8"`；
- 所有 Shell 脚本使用 LF；
- 新增或修改 `.sh` 后必须检查：

```bash
python - <<'PY'
from pathlib import Path
for p in Path(".").rglob("*.sh"):
    if b"\r\n" in p.read_bytes():
        raise SystemExit(f"CRLF shell: {p}")
PY
```

构建脚本会在复制阶段自动规范化 `.sh` 为 LF。

## 3. 脚本入口

只允许以下 Linux 入口：

```text
start.sh
deploy/install-systemd.sh
deploy/install-offline.sh
deploy/apply-permissions.sh
```

不再提供非 Linux 启动脚本。

## 4. Python 依赖与虚拟环境

Linux 开发：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
python run_backend.py 8000
```

离线部署使用包内独立 Python 和 wheels，不依赖系统 Python。

## 5. 构建

```bash
cd frontend
npm ci
npm run build
cd ..
python tools/build_release.py --force
```

构建脚本会自动：

1. 编译检查后端；
2. 执行安全门禁；
3. 扫描敏感信息；
4. 加密核心模块为 `.pye`；
5. 校验无明文核心 `.py` 后才生成 ZIP；
6. 检查 `LICENSE` 是否进入发布包。

构建要求：

- 使用 `pathlib` 处理路径；
- 发布 ZIP 内 `.sh` 必须为 LF、`0755`；
- 不把 `data/`、数据库、密钥、虚拟环境、Node 依赖或截图打进发布包；
- 只生成 Linux 发布包。

## 6. 提交前检查

```bash
python tools/security_check.py
python -m compileall -q backend
cd frontend && npm run build
cd ..
python tools/build_release.py --force
```

如果修改了 Shell 脚本，额外检查：

```bash
file deploy/*.sh start.sh uninstall.sh
```

不能出现 `CRLF line terminators`。

## 7. 兼容性原则

- 新功能在 Linux 上完成启动和部署验证；
- 文件上传、路径、临时文件、命令执行按 Linux 环境考虑；
- Shell 脚本不得使用非 Linux 命令、盘符或 CRLF；
- 发布包只包含 Linux 部署文件；
- 文档中的命令只保留 Linux/bash 形式。

## 8. 拓扑前端约定

- 设备连接偏移保存为 `edge_offset` JSON；双控制点使用 `points: [{x, y}, {x, y}]`，坐标相对两端设备中心连线的中点；
- 前端保存时同时提交 `offset_x`、`offset_y` 和 `offset_points`；后端校验偏移是否为空时必须把非空 `points` 视为有效，不能只判断 `x/y/color`；
- 云链路使用 `cloud_links` 保存 `edge_offset`、`edge_label_offset`、`source_anchor`、`dest_anchor`，新增云链路只增量添加单元，不得整图重绘；
- 拓扑编辑采用手动保存；添加连接前保存布局失败不应阻断添加；
- 双击连线用于修改连接参数，删除只能通过链路详情按钮二次确认；
- 框选为长按左键 1.5 秒后进入准备状态，提前移动取消；
- 画布不使用 X6 Scroller；滚动条为独立覆盖层，通过 `graph.translate` 平移，避免影响 `zoomToFit/centerContent`；
- 编辑模式滚轮缩放调用 `graph.zoomTo`，缩放和适应画布后必须重新计算滚动条位置；
- 交叉桥接节点仅用于显示，数据标记 `isCrossing: true`，不得参与设备选择、框选、保存和设备统计。

## 9. 权限与即时通信约定

- 功能权限存于角色 permissions，使用 view/edit 权限点表示只读/可编辑；不包含 view 即不可见，前端菜单和路由必须按角色原始权限判断；
- 资产可见范围由用户所属资产组决定，资产接口必须调用统一 scope 校验；新建用户必须至少绑定一个角色和一个资产组；
- 超级管理员绕过功能权限和资产组范围；多个角色权限取并集；
- 左侧菜单权限点使用 im:view 控制即时通信；单聊白板消息使用 group_id=NULL、recipient_id=对方用户，群白板使用 group_id；白板消息不得进入普通聊天列表、未读统计或会话最后一条消息；
- 打开白板发送 whiteboard-active 协作事件：单聊只通知对方，群聊只通知在线群成员；前端收到后显示可点击通知和“加入白板”提示；
- 白板清空必须在白板内部确认，确认文案需区分单聊双方和群聊成员；
- 白板保留期与聊天记录一致（15 天），清理任务必须同时清理单聊和群聊白板。
