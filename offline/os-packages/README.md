# 离线系统包目录

离线部署 PostgreSQL/Redis 时，把目标发行版及其架构对应的系统包放到：

```text
offline/os-packages/debian/*.deb   # Debian / Ubuntu
offline/os-packages/rhel/*.rpm     # RHEL / AlmaLinux / openEuler / Kylin
```

安装脚本会优先用 `dpkg -i` 或 `rpm -Uvh --replacepkgs` 安装这些本地包；如果目录为空，不会伪造 PostgreSQL/Redis 安装成功，而是明确警告并回退 SQLite / 进程内缓存。

## 生成系统包

在**与目标服务器相同发行版和架构**的联网机器上执行：

```bash
sudo bash deploy/prepare-offline-os-packages.sh --target debian
# 或
sudo bash deploy/prepare-offline-os-packages.sh --target rhel
```

脚本使用 apt 的下载缓存或 dnf download --resolve 收集依赖。必须在匹配的发行版上执行，不能把 Ubuntu 包放到 RHEL。

> 发布构建本身不包含这些系统包，以免把错误的发行版包发到其他服务器。部署前请按目标系统生成并放入目录。
