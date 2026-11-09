# IOP 离线安装说明

本发布包包含完整离线运行环境：

- Linux x86_64 独立 CPython 3.12 运行时（xz 压缩）；
- 静态 busybox 解压工具；
- 后端全部 Python 依赖 wheels；
- 已构建前端 `frontend/dist`；
- systemd 安装脚本和依赖校验文件。

安装过程不需要联网，不需要系统预装 Python/pip/venv，也不需要 apt/dnf 下载依赖。

## 安装命令

```bash
unzip IOP-v2.22.24.zip -d /tmp
cd /tmp/IOP-v2.22.24
sudo bash deploy/apply-permissions.sh
sudo bash deploy/install-offline.sh
```

安装完成后访问：

```text
https://服务器IP/
```

初始管理员密码文件：

```text
/opt/snmp-monitor/data/initial_admin_password.txt
```

直接查看：

```bash
sudo cat /opt/snmp-monitor/data/initial_admin_password.txt
```

## PostgreSQL / Redis 自动安装

全新安装默认自动安装 PostgreSQL 和 Redis 并写入平台配置；失败会回退 SQLite/内存缓存并警告。

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

## 系统要求

- Linux x86_64；
- glibc 2.17 及以上；
- systemd；
- 系统自带 `tar`、`bash`、`coreutils`、`sed`、`grep`、`awk`；
- 不适用于 Alpine/musl 或 ARM 架构。

## 校验离线依赖

```bash
cd /tmp/IOP-v2.22.24/offline
sha256sum -c SHA256SUMS
```

详细说明见 `offline/README.md`。

> 内网离线环境无法使用在线 MIB 下载、在线 AI 模型和在线更新服务；这些功能需要在能够访问对应服务时使用。
