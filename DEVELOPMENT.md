# 跨平台开发与构建规范

本项目必须同时支持 **Linux** 和 **Windows** 的开发、调试与构建。

## 1. 路径

- Python 代码统一使用 `pathlib.Path`；
- 禁止硬编码 `/opt/...`、`C:\...` 等运行环境路径；
- URL 路径使用 `/`，文件系统路径使用 `Path`；
- 临时目录使用 `tempfile`，不要写死系统临时路径；
- 构建输出目录以项目根目录的父目录为基准。

## 2. 编码与换行

- 所有文本文件使用 UTF-8；
- Python 显式使用 `encoding="utf-8"`；
- Linux Shell 脚本必须使用 LF；
- Windows 批处理 `.bat` 使用 CRLF；
- PowerShell `.ps1` 允许 LF，但不得依赖 Unix 工具；
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

Linux：

```text
start.sh
deploy/install-systemd.sh
deploy/install-offline.sh
deploy/apply-permissions.sh
```

Windows：

```text
start-backend.ps1
start-frontend.ps1
```

- 不允许要求 Windows 用户安装 Bash 才能开发；
- 不允许要求 Linux 用户依赖 PowerShell 才能安装；
- 共用的构建逻辑写在 Python 中，不写在 Bash 或 PowerShell 中。

## 4. Python 依赖与虚拟环境

Linux 开发：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.txt
python run_backend.py 8000
```

Windows 开发：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r backend/requirements.txt
python run_backend.py 8000
```

离线包只针对 Linux x86_64；Windows 开发环境不要求使用离线 Python 压缩包。

## 5. 构建

Windows 和 Linux 都必须能执行：

```bash
cd frontend
npm ci
npm run build
cd ..
python tools/build_release.py --force

# 构建脚本会自动：
# 1. 编译检查后端
# 2. 执行安全门禁
# 3. 加密核心模块为 .pye
# 4. 校验无明文核心 .py 后才生成 ZIP
```

构建脚本要求：

- 使用 `pathlib` 处理路径；
- 不调用仅 Linux 可用的 `sed`、`chmod` 等命令完成必要逻辑；
- 可执行位只对 Linux 有意义，Windows 构建时忽略 `chmod` 失败；
- 复制到发布目录的 `.sh` 自动转 LF；
- 发布 ZIP 内 `.sh` 必须为 LF、`0755`；
- 不把 `data/`、数据库、密钥、虚拟环境、Node 依赖或截图打进发布包。

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

- 新功能必须在 Linux 和 Windows 至少各完成一次启动验证；
- 涉及文件上传、路径、临时文件、命令执行的代码必须同时考虑两个平台；
- 不得把 Linux 的 `/` 路径、权限模型或命令直接带入 Windows 逻辑；
- 不得把 Windows 的盘符、反斜杠或 CRLF 带入 Linux 脚本；
- 不能因为“开发机是 Windows”就把 Linux 发布包做坏；
- 不能因为“生产是 Linux”就忽略 Windows 本地开发体验。
