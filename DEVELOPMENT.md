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
