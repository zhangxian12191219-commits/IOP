"""跨平台主机网络/服务/计划任务管理。

安全边界：
- 只接受严格校验过的网卡、IP、路由、服务名和计划任务名
- 所有命令使用参数数组或 PowerShell 环境变量，不拼接用户输入到 shell
- 写操作需要进程具备管理员/root 权限
- 所有变更由上层路由记录审计日志
"""
from __future__ import annotations

import ipaddress
import json
import os
import platform
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Optional, Tuple

IS_WINDOWS = os.name == "nt"
SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.@: /\\-]{1,160}$")
IFACE_RE = re.compile(r"^[^\"'`;|&$<>\r\n]{1,120}$")
PATH_FALLBACK_DIRS = ("/usr/sbin", "/sbin", "/usr/local/sbin")


def _effective_path() -> str:
    """systemd 精简 PATH 时补齐 ip/nmcli/firewall-cmd 等系统管理命令目录。"""
    path = os.environ.get("PATH", "") or ""
    parts = [item for item in path.split(os.pathsep) if item]
    for directory in PATH_FALLBACK_DIRS:
        if directory not in parts:
            parts.append(directory)
    return os.pathsep.join(parts)


class HostCommandError(RuntimeError):
    def __init__(self, message: str, output: str = ""):
        super().__init__(message)
        self.output = output[:2000]


def is_admin() -> bool:
    if IS_WINDOWS:
        try:
            import ctypes
            return bool(ctypes.windll.shell32.IsUserAnAdmin())
        except Exception:  # noqa: BLE001
            return False
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def capabilities() -> Dict[str, Any]:
    return {
        "platform": "windows" if IS_WINDOWS else "linux",
        "system": platform.system(),
        "release": platform.release(),
        "hostname": platform.node(),
        "admin": is_admin(),
        "supports": {
            "adapter_config": IS_WINDOWS or bool(which("nmcli")),
            "routes": True,
            "firewall": IS_WINDOWS or bool(which("ufw") or which("firewall-cmd")),
            "services": IS_WINDOWS or bool(which("systemctl")),
            "scheduled_tasks": IS_WINDOWS or bool(which("systemctl")),
            "network_restart": (not IS_WINDOWS) and bool(which("systemctl")),
        },
    }


def which(name: str) -> Optional[str]:
    import shutil
    return shutil.which(name, path=_effective_path())


def _run(cmd: List[str], timeout: int = 30, env: Optional[Dict[str, str]] = None) -> str:
    try:
        child_env = dict(env or os.environ)
        child_env["PATH"] = _effective_path()
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=child_env,
        )
    except FileNotFoundError as exc:
        raise HostCommandError(f"命令不存在：{cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise HostCommandError(f"命令执行超时（{timeout}s）", str(exc)) from exc
    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        detail = " ".join(output.strip().splitlines()[:3])[:500]
        message = f"命令执行失败（退出码 {proc.returncode}）"
        if detail:
            message += f"：{detail}"
        raise HostCommandError(message, output)
    return (proc.stdout or "").strip()


def _ps(script: str, timeout: int = 30, env: Optional[Dict[str, str]] = None) -> str:
    if not IS_WINDOWS:
        raise HostCommandError("当前系统不是 Windows")
    preamble = (
        "$ErrorActionPreference='Stop'; "
        "[Console]::OutputEncoding=[System.Text.Encoding]::UTF8; "
        "$OutputEncoding=[System.Text.Encoding]::UTF8; "
    )
    return _run(
        ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", preamble + script],
        timeout=timeout,
        env=env,
    )


def _json(value: str) -> Any:
    text = (value or "").strip()
    if not text:
        return []
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise HostCommandError("系统返回格式无法解析", text[:1000]) from exc


def _as_list(value: Any) -> List[Any]:
    if value is None or value == "":
        return []
    return value if isinstance(value, list) else [value]


def _check_iface(name: str) -> str:
    name = str(name or "").strip()
    if not name or not IFACE_RE.match(name):
        raise HostCommandError("网卡名称不合法")
    return name


def _check_name(name: str) -> str:
    name = str(name or "").strip()
    if not name or not SAFE_NAME_RE.match(name):
        raise HostCommandError("名称包含不允许的字符")
    return name


def _ip(value: str, label: str) -> str:
    try:
        return str(ipaddress.ip_address(str(value).strip()))
    except ValueError as exc:
        raise HostCommandError(f"{label}格式不正确") from exc


def _network(value: str) -> str:
    try:
        return str(ipaddress.ip_network(str(value).strip(), strict=False))
    except ValueError as exc:
        raise HostCommandError("目标网段格式不正确，应为 CIDR（如 10.0.0.0/24）") from exc


def _prefix(value: Any) -> int:
    try:
        prefix = int(value)
    except (TypeError, ValueError) as exc:
        raise HostCommandError("子网前缀不正确") from exc
    if prefix < 1 or prefix > 32:
        raise HostCommandError("IPv4 子网前缀应为 1~32")
    return prefix


def _prefix_to_mask(prefix: int) -> str:
    return str(ipaddress.IPv4Network(f"0.0.0.0/{prefix}").netmask)


# ---------------- Windows 读取 ----------------
def _windows_overview() -> Dict[str, Any]:
    script = r"""
$dhcp = @{}
Get-NetIPInterface -AddressFamily IPv4 -ErrorAction SilentlyContinue | ForEach-Object { $dhcp[$_.InterfaceIndex] = $_.Dhcp }
$items = @(Get-NetIPConfiguration -ErrorAction SilentlyContinue | Where-Object { $_.NetAdapter.Status -ne 'NotPresent' } | ForEach-Object {
  $ip = @($_.IPv4Address | Select-Object -First 1)
  $gw = @($_.IPv4DefaultGateway | Select-Object -First 1)
  $dns = @()
  foreach ($server in @($_.DNSServer)) { foreach ($address in @($server.ServerAddresses)) { $dns += $address } }
  [pscustomobject]@{
    name=$_.InterfaceAlias; description=$_.InterfaceDescription; index=[int]$_.InterfaceIndex;
    status=[string]$_.NetAdapter.Status; mac=[string]$_.NetAdapter.MacAddress;
    ip=if($ip.Count){[string]$ip[0].IPAddress}else{''}; prefix=if($ip.Count){[int]$ip[0].PrefixLength}else{0};
    gateway=if($gw.Count){[string]$gw[0].NextHop}else{''}; dns=$dns;
    dhcp=if($dhcp.ContainsKey([int]$_.InterfaceIndex)){[bool]$dhcp[[int]$_.InterfaceIndex]}else{$false}
  }
})
$items | ConvertTo-Json -Compress -Depth 6
"""
    raw_routes_script = r"""
$items = @(Get-NetRoute -ErrorAction SilentlyContinue | Where-Object {
  $_.DestinationPrefix -notmatch '^(ff00|fe80|224\.|239\.|255\.255\.255\.255)'
} | Select-Object -First 500 | ForEach-Object {
  [pscustomobject]@{
    destination=[string]$_.DestinationPrefix; gateway=[string]$_.NextHop;
    interface_index=[int]$_.InterfaceIndex; metric=[int]$_.RouteMetric; store=[string]$_.PolicyStore
  }
})
$items | ConvertTo-Json -Compress -Depth 5
"""
    firewall_script = r"""
@(Get-NetFirewallProfile -ErrorAction SilentlyContinue | ForEach-Object {
  [pscustomobject]@{name=[string]$_.Name; enabled=[bool]$_.Enabled}
}) | ConvertTo-Json -Compress -Depth 4
"""
    # 三个 PowerShell 查询互不依赖，并行执行，避免串行等待十几秒
    with ThreadPoolExecutor(max_workers=3) as pool:
        adapter_future = pool.submit(_ps, script, 25)
        route_future = pool.submit(_ps, raw_routes_script, 25)
        firewall_future = pool.submit(_ps, firewall_script, 20)
        adapters = _as_list(_json(adapter_future.result()))
        raw_routes = _as_list(_json(route_future.result()))
        profiles = _as_list(_json(firewall_future.result()))
    names = {int(item.get("index") or 0): item.get("name") for item in adapters}
    routes = []
    for item in raw_routes:
        idx = int(item.get("interface_index") or 0)
        routes.append({
            "destination": item.get("destination") or "",
            "gateway": item.get("gateway") or "",
            "interface": names.get(idx, f"if{idx}"),
            "metric": item.get("metric") or 0,
            "store": item.get("store") or "",
        })
    enabled = any(bool(item.get("enabled")) for item in profiles)
    return {
        "adapters": adapters,
        "routes": routes,
        "firewall": {
            "backend": "Windows Defender Firewall",
            "enabled": enabled,
            "profiles": profiles,
            "available": True,
        },
    }


# ---------------- Linux 读取 ----------------
def _linux_adapters(routes_raw: Optional[List[Any]] = None) -> List[Dict[str, Any]]:
    raw = _json(_run(["ip", "-j", "addr", "show"], timeout=10))
    if routes_raw is None:
        routes_raw = _json(_run(["ip", "-j", "route", "show"], timeout=10))
    defaults = {}
    for route in routes_raw:
        if route.get("dst") == "default" and route.get("dev"):
            defaults[route["dev"]] = route.get("gateway") or ""
    dns = []
    try:
        resolver = _run(["resolvectl", "dns"], timeout=3)
        for line in resolver.splitlines():
            if ":" in line:
                dns.extend(line.split(":", 1)[1].split())
    except HostCommandError:
        try:
            with open("/etc/resolv.conf", encoding="utf-8") as handle:
                dns = [line.split()[1] for line in handle if line.startswith("nameserver ") and len(line.split()) > 1]
        except OSError:
            dns = []
    adapters = []
    for item in raw if isinstance(raw, list) else []:
        name = item.get("ifname") or ""
        if not name or name == "lo":
            continue
        ipv4 = [a for a in item.get("addr_info") or [] if a.get("family") == "inet"]
        first = ipv4[0] if ipv4 else {}
        adapters.append({
            "name": name,
            "description": (item.get("linkinfo") or {}).get("info_kind") or item.get("link_type") or "",
            "index": item.get("ifindex") or 0,
            "status": item.get("operstate") or "UNKNOWN",
            "mac": item.get("address") or "",
            "ip": first.get("local") or "",
            "prefix": first.get("prefixlen") or 0,
            "gateway": defaults.get(name, ""),
            "dns": dns,
            "dhcp": None,
        })
    return adapters


def _linux_routes() -> List[Dict[str, Any]]:
    raw = _json(_run(["ip", "-j", "route", "show"], timeout=10))
    routes = []
    for item in raw if isinstance(raw, list) else []:
        routes.append({
            "destination": "default" if item.get("dst") == "default" else (item.get("dst") or ""),
            "gateway": item.get("gateway") or "",
            "interface": item.get("dev") or "",
            "metric": int(item.get("metric") or 0),
            "store": item.get("protocol") or "",
        })
    return routes[:500]


def _linux_firewall() -> Dict[str, Any]:
    if which("ufw"):
        try:
            output = _run(["ufw", "status"], timeout=5)
            return {
                "backend": "ufw",
                "enabled": "Status: active" in output,
                "profiles": [],
                "available": True,
            }
        except HostCommandError:
            pass
    if which("firewall-cmd"):
        try:
            output = _run(["firewall-cmd", "--state"], timeout=5)
            return {
                "backend": "firewalld",
                "enabled": output.strip() == "running",
                "profiles": [],
                "available": True,
            }
        except HostCommandError as exc:
            return {
                "backend": "firewalld",
                "enabled": "running" in str(exc).lower(),
                "profiles": [],
                "available": True,
            }
    return {"backend": "none", "enabled": False, "profiles": [], "available": False}


def get_overview() -> Dict[str, Any]:
    caps = capabilities()
    if IS_WINDOWS:
        data = _windows_overview()
    else:
        with ThreadPoolExecutor(max_workers=2) as pool:
            route_future = pool.submit(_linux_routes)
            firewall_future = pool.submit(_linux_firewall)
            routes = route_future.result()
            adapters = _linux_adapters(routes)
            firewall = firewall_future.result()
        data = {
            "adapters": adapters,
            "routes": routes,
            "firewall": firewall,
        }
    return {**caps, **data}


# ---------------- 网卡配置 ----------------
def _windows_active_connection(name: str) -> None:
    # 名称必须来自当前网卡，避免对任意接口执行命令
    data = _windows_overview()
    if name not in {item.get("name") for item in data["adapters"]}:
        raise HostCommandError("网卡不存在或当前不可用")


def configure_adapter(
    name: str,
    mode: str,
    ip: str = "",
    prefix: int = 24,
    gateway: str = "",
    dns: Optional[List[str]] = None,
) -> Dict[str, Any]:
    name = _check_iface(name)
    mode = str(mode or "").lower()
    if mode not in ("static", "dhcp"):
        raise HostCommandError("模式只支持 static 或 dhcp")
    if not is_admin():
        raise HostCommandError("修改网卡需要管理员/root 权限")
    dns_list = [str(item).strip() for item in (dns or []) if str(item).strip()]
    for item in dns_list:
        _ip(item, "DNS 地址")
    if mode == "static":
        ip = _ip(ip, "IP 地址")
        prefix = _prefix(prefix)
        if gateway:
            gateway = _ip(gateway, "网关地址")
    if IS_WINDOWS:
        _windows_active_connection(name)
        if mode == "static":
            cmd = [
                "netsh", "interface", "ipv4", "set", "address",
                f"name={name}", "source=static", f"address={ip}",
                f"mask={_prefix_to_mask(prefix)}",
            ]
            if gateway:
                cmd.append(f"gateway={gateway}")
            _run(cmd, timeout=45)
            if dns_list:
                _run([
                    "netsh", "interface", "ipv4", "set", "dnsservers",
                    f"name={name}", "source=static", f"address={dns_list[0]}",
                    "register=primary", "validate=no",
                ], timeout=30)
                for index, server in enumerate(dns_list[1:], start=2):
                    _run([
                        "netsh", "interface", "ipv4", "add", "dnsservers",
                        f"name={name}", f"address={server}", f"index={index}",
                        "validate=no",
                    ], timeout=30)
        else:
            _run(["netsh", "interface", "ipv4", "set", "address", f"name={name}", "source=dhcp"], timeout=45)
            _run(["netsh", "interface", "ipv4", "set", "dnsservers", f"name={name}", "source=dhcp"], timeout=30)
        namespace = "Windows netsh"
    else:
        if not which("nmcli"):
            raise HostCommandError("当前 Linux 未安装 NetworkManager（nmcli），第一版不直接改写 /etc/network/interfaces")
        active = _run(["nmcli", "-t", "-f", "NAME,DEVICE", "connection", "show", "--active"], timeout=15)
        connection = ""
        for line in active.splitlines():
            parts = line.rsplit(":", 1)
            if len(parts) == 2 and parts[1] == name:
                connection = parts[0]
                break
        if not connection:
            raise HostCommandError(f"网卡 {name} 没有活动的 NetworkManager 连接")
        if mode == "static":
            args = [
                "nmcli", "connection", "modify", connection,
                "ipv4.method", "manual", "ipv4.addresses", f"{ip}/{prefix}",
            ]
            if gateway:
                args += ["ipv4.gateway", gateway]
            if dns_list:
                args += ["ipv4.dns", ",".join(dns_list)]
            else:
                args += ["ipv4.dns", ""]
            _run(args, timeout=30)
        else:
            _run([
                "nmcli", "connection", "modify", connection,
                "ipv4.method", "auto", "ipv4.addresses", "",
                "ipv4.gateway", "", "ipv4.dns", "",
            ], timeout=30)
        _run(["nmcli", "connection", "up", connection], timeout=60)
        namespace = f"NetworkManager ({connection})"
    return {
        "message": "网卡配置已提交，连接可能短暂中断",
        "adapter": name,
        "mode": mode,
        "backend": namespace,
    }


# ---------------- 路由 ----------------
def _windows_route_script(action: str, destination: str, gateway: str, interface: str = "", metric: int = 10) -> str:
    env_key = "NMS_ROUTE_ACTION"
    env = {
        **os.environ,
        env_key: action,
        "NMS_DST": destination,
        "NMS_GW": gateway,
        "NMS_IF": interface,
        "NMS_METRIC": str(max(1, int(metric or 10))),
    }
    if action == "add":
        script = (
            "if(-not $env:NMS_GW -and -not $env:NMS_IF){"
            "$default=(Get-NetRoute -DestinationPrefix '0.0.0.0/0' -ErrorAction SilentlyContinue | Sort-Object RouteMetric | Select-Object -First 1);"
            "if($default){$env:NMS_IF=$default.InterfaceAlias}"
            "};"
            "$params=@{DestinationPrefix=$env:NMS_DST; PolicyStore='PersistentStore'; RouteMetric=[int]$env:NMS_METRIC; ErrorAction='Stop'};"
            "if($env:NMS_GW){$params.NextHop=$env:NMS_GW};"
            "if($env:NMS_IF){$params.InterfaceAlias=$env:NMS_IF};"
            "New-NetRoute @params | Out-String"
        )
    else:
        script = (
            "$params=@{DestinationPrefix=$env:NMS_DST; ErrorAction='SilentlyContinue'};"
            "if($env:NMS_GW){$params.NextHop=$env:NMS_GW};"
            "if($env:NMS_IF){$params.InterfaceAlias=$env:NMS_IF};"
            "Remove-NetRoute @params -PolicyStore ActiveStore -Confirm:$false;"
            "Remove-NetRoute @params -PolicyStore PersistentStore -Confirm:$false;"
            "'ok'"
        )
    return _ps(script, timeout=30, env=env)


def add_route(destination: str, gateway: str = "", interface: str = "", metric: int = 10) -> Dict[str, Any]:
    if not is_admin():
        raise HostCommandError("添加路由需要管理员/root 权限")
    destination = _network(destination)
    gateway = _ip(gateway, "网关地址") if gateway else ""
    interface = _check_iface(interface) if interface else ""
    try:
        metric = int(metric)
    except (TypeError, ValueError) as exc:
        raise HostCommandError("Metric 必须是整数") from exc
    if not 1 <= metric <= 9999:
        raise HostCommandError("Metric 必须在 1~9999 之间")

    if IS_WINDOWS:
        _windows_route_script("add", destination, gateway, interface, metric)
        backend = "New-NetRoute PersistentStore"
    else:
        if not which("ip"):
            raise HostCommandError("系统缺少 ip 命令")
        if not interface:
            # 未指定出口网卡时优先补默认路由出口，避免 ip route 退出码 2
            try:
                default_route = _run(["ip", "route", "show", "default"], timeout=8)
            except HostCommandError as exc:
                if not gateway:
                    raise HostCommandError(
                        "未填写下一跳或出口网卡，且无法读取默认路由，请手动选择出口网卡",
                        exc.output,
                    ) from exc
                default_route = ""
            match = re.search(r"\bdev\s+(\S+)", default_route)
            if match:
                interface = match.group(1)
            elif not gateway:
                raise HostCommandError("未填写下一跳或出口网卡，且未找到默认出口网卡，请手动选择出口网卡")
        cmd = ["ip", "route", "replace", destination]
        if gateway:
            cmd += ["via", gateway]
        if interface:
            cmd += ["dev", interface]
        cmd += ["metric", str(metric)]
        try:
            _run(cmd, timeout=20)
        except HostCommandError as exc:
            # 下一跳不在出口网段时，内核会拒绝；明确提示后使用 onlink 重试
            if gateway and any(token in str(exc).lower() for token in (
                "invalid gateway", "network is unreachable", "nexthop", "no route",
            )):
                retry = ["ip", "route", "replace", destination, "via", gateway]
                if interface:
                    retry += ["dev", interface]
                retry += ["metric", str(metric), "onlink"]
                _run(retry, timeout=20)
            else:
                raise
        if interface and which("nmcli"):
            try:
                active = _run(["nmcli", "-t", "-f", "NAME,DEVICE", "connection", "show", "--active"], timeout=12)
                for line in active.splitlines():
                    parts = line.rsplit(":", 1)
                    if len(parts) == 2 and parts[1] == interface:
                        route = f"{destination} {gateway}".strip()
                        _run(["nmcli", "connection", "modify", parts[0], "+ipv4.routes", route], timeout=20)
                        break
            except HostCommandError:
                pass
        backend = "ip route replace（NetworkManager 可用时同步持久化）"
    return {"message": "路由已添加", "destination": destination, "backend": backend}


def delete_route(destination: str, gateway: str = "", interface: str = "") -> Dict[str, Any]:
    if not is_admin():
        raise HostCommandError("删除路由需要管理员/root 权限")
    destination = _network(destination)
    gateway = _ip(gateway, "网关地址") if gateway else ""
    interface = _check_iface(interface) if interface else ""
    if IS_WINDOWS:
        _windows_route_script("delete", destination, gateway, interface)
    else:
        cmd = ["ip", "route", "del", destination]
        if gateway:
            cmd += ["via", gateway]
        if interface:
            cmd += ["dev", interface]
        _run(cmd, timeout=20)
    return {"message": "路由已删除", "destination": destination}


# ---------------- 防火墙 ----------------
def set_firewall(enabled: bool) -> Dict[str, Any]:
    if not is_admin():
        raise HostCommandError("修改防火墙需要管理员/root 权限")
    if IS_WINDOWS:
        env = {**os.environ, "NMS_ENABLED": "true" if enabled else "false"}
        _ps(
            "$v = $env:NMS_ENABLED -eq 'true'; Set-NetFirewallProfile -Profile Domain,Private,Public -Enabled $v | Out-Null",
            timeout=30, env=env,
        )
        backend = "Windows Defender Firewall"
    else:
        if which("ufw"):
            _run(["ufw", "--force", "enable" if enabled else "disable"], timeout=30)
            backend = "ufw"
        elif which("firewall-cmd"):
            if enabled:
                _run(["systemctl", "enable", "--now", "firewalld"], timeout=45)
            else:
                _run(["systemctl", "disable", "--now", "firewalld"], timeout=45)
            backend = "firewalld"
        else:
            raise HostCommandError("未检测到 ufw 或 firewalld，无法通过网页切换防火墙")
    return {"message": "防火墙状态已更新", "enabled": enabled, "backend": backend}


# ---------------- 服务 ----------------
def list_services(query: str = "", limit: int = 300) -> List[Dict[str, Any]]:
    limit = max(1, min(1000, int(limit or 300)))
    if IS_WINDOWS:
        rows = _as_list(_json(_ps(
            "Get-Service | Select-Object Name,DisplayName,"
            "@{n='Status';e={[string]$_.Status}},@{n='Startup';e={[string]$_.StartType}} "
            "| ConvertTo-Json -Compress -Depth 4",
            timeout=30,
        )))
        result = [{
            "name": item.get("Name") or "",
            "display_name": item.get("DisplayName") or "",
            "status": str(item.get("Status") or ""),
            "startup": str(item.get("StartType") or ""),
        } for item in rows]
    else:
        units = _run([
            "systemctl", "list-units", "--type=service", "--all",
            "--no-pager", "--no-legend", "--plain",
        ], timeout=30)
        enabled_map = {}
        try:
            files = _run([
                "systemctl", "list-unit-files", "--type=service",
                "--no-pager", "--no-legend",
            ], timeout=30)
            for line in files.splitlines():
                parts = line.split()
                if len(parts) >= 2:
                    enabled_map[parts[0]] = parts[1]
        except HostCommandError:
            pass
        result = []
        for line in units.splitlines():
            parts = line.split(None, 4)
            if len(parts) < 4:
                continue
            unit = parts[0]
            result.append({
                "name": unit,
                "display_name": parts[4] if len(parts) > 4 else unit,
                "status": parts[3],
                "startup": enabled_map.get(unit, ""),
            })
    needle = str(query or "").strip().lower()
    if needle:
        result = [
            item for item in result
            if needle in item["name"].lower() or needle in item["display_name"].lower()
        ]
    return result[:limit]


def restart_network_service() -> Dict[str, Any]:
    """重启 Linux 网络管理服务，使网卡配置立即重新加载。

    仅 Linux 支持；该操作可能短暂断开管理连接，调用方必须先二次确认。
    """
    if IS_WINDOWS:
        raise HostCommandError("当前为 Windows，未启用 Linux 网络服务重启")
    if not is_admin():
        raise HostCommandError("重启网络服务需要管理员/root 权限")
    if not which("systemctl"):
        raise HostCommandError("当前系统未使用 systemd，无法重启网络服务")

    candidates = []
    if which("nmcli"):
        candidates.append("NetworkManager")
    candidates.extend(["networking", "network"])
    unit = ""
    for candidate in candidates:
        try:
            _run(["systemctl", "cat", candidate], timeout=5)
            unit = candidate
            break
        except HostCommandError:
            continue
    if not unit:
        raise HostCommandError("未找到 NetworkManager/networking 网络服务")
    _run(["systemctl", "restart", unit], timeout=60)
    return {
        "message": f"网络服务 {unit} 已重启",
        "service": unit,
        "action": "restart",
    }


def service_action(name: str, action: str) -> Dict[str, Any]:
    name = _check_name(name)
    action = str(action or "").lower()
    if action not in ("start", "stop", "restart", "enable", "disable"):
        raise HostCommandError("服务操作不支持")
    if not is_admin():
        raise HostCommandError("管理服务需要管理员/root 权限")
    if IS_WINDOWS:
        env = {**os.environ, "NMS_SERVICE": name, "NMS_ACTION": action}
        script = {
            "start": "Start-Service -Name $env:NMS_SERVICE",
            "stop": "Stop-Service -Name $env:NMS_SERVICE -Force",
            "restart": "Restart-Service -Name $env:NMS_SERVICE -Force",
            "enable": "Set-Service -Name $env:NMS_SERVICE -StartupType Automatic",
            "disable": "Set-Service -Name $env:NMS_SERVICE -StartupType Disabled",
        }[action]
        _ps(script + "; 'ok'", timeout=60, env=env)
    else:
        _run(["systemctl", action, name], timeout=60)
    return {"message": "服务操作完成", "name": name, "action": action}


# ---------------- 计划任务 ----------------
def list_scheduled_tasks() -> List[Dict[str, Any]]:
    if IS_WINDOWS:
        rows = _as_list(_json(_ps(
            "Get-ScheduledTask | Select-Object TaskName,TaskPath,"
            "@{n='State';e={[string]$_.State}} | ConvertTo-Json -Compress -Depth 4",
            timeout=30,
        )))
        return [{
            "name": item.get("TaskName") or "",
            "path": item.get("TaskPath") or "",
            "status": item.get("State") or "",
        } for item in rows]
    if not which("systemctl"):
        return []
    output = _run([
        "systemctl", "list-timers", "--all",
        "--no-pager", "--no-legend", "--plain",
    ], timeout=30)
    result = []
    for line in output.splitlines():
        parts = line.split()
        if not parts:
            continue
        unit = parts[0]
        if not unit.endswith(".timer"):
            continue
        result.append({
            "name": unit,
            "path": "systemd timer",
            "status": "active" if len(parts) > 1 and ":" in parts[1] or "left" in line else "listed",
            "next": parts[1] if len(parts) > 1 else "",
        })
    return result[:300]


def scheduled_task_action(name: str, action: str) -> Dict[str, Any]:
    name = _check_name(name)
    action = str(action or "").lower()
    if action not in ("start", "stop", "enable", "disable"):
        raise HostCommandError("计划任务操作不支持")
    if not is_admin():
        raise HostCommandError("管理计划任务需要管理员/root 权限")
    if IS_WINDOWS:
        env = {**os.environ, "NMS_TASK": name, "NMS_ACTION": action}
        mapping = {
            "start": "Start-ScheduledTask -TaskName $env:NMS_TASK",
            "stop": "Stop-ScheduledTask -TaskName $env:NMS_TASK",
            "enable": "Enable-ScheduledTask -TaskName $env:NMS_TASK | Out-Null",
            "disable": "Disable-ScheduledTask -TaskName $env:NMS_TASK | Out-Null",
        }
        _ps(mapping[action] + "; 'ok'", timeout=45, env=env)
    else:
        _run(["systemctl", action, name], timeout=45)
    return {"message": "计划任务操作完成", "name": name, "action": action}
