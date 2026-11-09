# IOP 离线安装依赖包

本目录用于 Linux x86_64（glibc）断网安装，包含：

- `python-linux-x86_64.tar.xz`：CPython 3.12.16 独立运行时（xz 极限压缩）；
- `bin/busybox`：静态 x86_64 解压工具，安装时解压 xz，不依赖系统 xz；
- `wheels/`：后端全部 Python 依赖的 manylinux2014 x86_64 wheels；
- `manifest.json`：平台、版本和校验信息；
- `SHA256SUMS`：全部文件 SHA256。

安装时不需要联网，也不需要系统预装 Python、pip、venv，不需要 apt/dnf 下载依赖。

## 安装

```bash
unzip IOP-v<版本>.zip -d /tmp
cd /tmp/IOP-v<版本>
sudo bash deploy/apply-permissions.sh
sudo bash deploy/install-offline.sh
```

安装脚本会：

1. 把程序和 `offline/` 同步到 `/opt/snmp-monitor`；
2. 使用随包 busybox 解压内置 Python 到 `offline/python`；
3. 使用内置 Python 创建虚拟环境；
4. 使用 `pip --no-index --find-links offline/wheels` 安装依赖；
5. 安装 systemd 服务和健康检查定时器。

## 系统要求

- Linux x86_64；
- glibc 2.17 及以上（Ubuntu 20.04+、Debian 11+、RHEL/AlmaLinux 8+ 等）；
- systemd；
- `bash`、`coreutils`、`sed`、`grep`、`awk`；
- 没有系统 `tar` 时使用本目录的 `bin/busybox tar`；
- 不使用 Alpine/musl 系统；
- 精简 openEuler 已实测通过。

如需 IPMI，请把 `ipmitool` 的 RPM 放入 `os-packages/rhel/`，或从 openEuler ISO 手工安装。

## 校验

```bash
cd offline
sha256sum -c SHA256SUMS
```

> `offline/` 中的 Python 运行时和 wheels 只用于目标架构 Linux x86_64，不要复制到 ARM 服务器使用。
