"""按需安装系统工具依赖（目前用于 Linux traceroute）。

服务器以 root 运行但 systemd 单元有 ProtectSystem=full/NoNewPrivileges，
直接由服务进程写 /usr 会被沙箱拦截。因此优先通过 systemd-run 启动一个
独立的瞬时 root 单元安装固定包名，进程本身只负责收集输出和进度。
"""
from __future__ import annotations

import asyncio
import os
import shutil
import time
from typing import Any, Awaitable, Callable, Dict, Optional

ProgressCallback = Callable[[Dict[str, Any]], Awaitable[None]]
_JOB: Optional[Dict[str, Any]] = None
_LOCK = asyncio.Lock()


def traceroute_installed() -> bool:
    return bool(shutil.which("traceroute"))


def current_job() -> Dict[str, Any]:
    return dict(_JOB or {"status": "idle", "progress": 0, "message": "未开始"})


async def _emit(callback: Optional[ProgressCallback], job: Dict[str, Any]) -> None:
    if callback is not None:
        try:
            await callback(dict(job))
        except Exception:  # noqa: BLE001
            pass


def _package_manager() -> Optional[list[str]]:
    if shutil.which("dnf"):
        return ["dnf", "install", "-y", "--setopt=tsflags=noscripts", "traceroute"]
    if shutil.which("yum"):
        return ["yum", "install", "-y", "--setopt=tsflags=noscripts", "traceroute"]
    if shutil.which("apt-get"):
        return ["apt-get", "install", "-y", "traceroute"]
    if shutil.which("apk"):
        return ["apk", "add", "--no-cache", "traceroute"]
    return None


def _decode(data: bytes) -> str:
    for encoding in ("utf-8", "gb18030", "latin-1"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


async def ensure_traceroute(progress_cb: Optional[ProgressCallback] = None) -> Dict[str, Any]:
    """确保 traceroute 可用；已经安装时直接返回。"""
    global _JOB
    if traceroute_installed():
        job = {"status": "success", "progress": 100, "message": "traceroute 已安装",
               "installed": True, "log": ""}
        _JOB = job
        return job

    async with _LOCK:
        if traceroute_installed():
            job = {"status": "success", "progress": 100, "message": "traceroute 已安装",
                   "installed": True, "log": ""}
            _JOB = job
            return job

        job: Dict[str, Any] = {
            "status": "running", "progress": 5, "stage": "detect",
            "message": "正在检测系统包管理器...", "installed": False,
            "log": "", "started_at": time.time(),
        }
        _JOB = job
        await _emit(progress_cb, job)

        if os.name == "nt":
            job.update(status="failed", message="Windows 自带 tracert，不需要安装 traceroute")
            await _emit(progress_cb, job)
            return dict(job)

        pm = _package_manager()
        if not pm:
            job.update(status="failed", message="未找到 dnf/yum/apt-get/apk 包管理器，无法自动安装")
            await _emit(progress_cb, job)
            return dict(job)

        if hasattr(os, "geteuid") and os.geteuid() != 0:
            job.update(status="failed", message="自动安装 traceroute 需要后端服务以 root 权限运行")
            await _emit(progress_cb, job)
            return dict(job)

        # 安装固定包名需要写 /usr；systemd 单元通过 ReadWritePaths 放行 /usr。
        # 直接执行包管理器，便于逐行采集安装进度。
        cmd = pm
        job.update(progress=12, stage="install", message="正在下载并安装 traceroute...",
                   command=" ".join(cmd))
        await _emit(progress_cb, job)

        env = os.environ.copy()
        env.update({"DEBIAN_FRONTEND": "noninteractive", "LC_ALL": "C", "LANG": "C"})
        proc = None
        output_lines: list[str] = []
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                env=env,
            )
            deadline = time.monotonic() + 300
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    proc.kill()
                    await proc.wait()
                    job.update(status="failed", message="安装超时（300 秒）")
                    await _emit(progress_cb, job)
                    return dict(job)
                try:
                    raw = await asyncio.wait_for(proc.stdout.readline(), timeout=remaining)
                except asyncio.TimeoutError:
                    proc.kill()
                    await proc.wait()
                    job.update(status="failed", message="安装超时（300 秒）")
                    await _emit(progress_cb, job)
                    return dict(job)
                if not raw:
                    break
                line = _decode(raw).strip()
                if not line:
                    continue
                output_lines.append(line)
                job["log"] = "\n".join(output_lines[-30:])
                lowered = line.lower()
                if "running as unit" in lowered:
                    progress = 20
                elif "dependencies resolved" in lowered or "reading package lists" in lowered:
                    progress = 35
                elif "downloading" in lowered or "downloaded" in lowered:
                    progress = 50
                elif "installing" in lowered or "transaction" in lowered or "updating" in lowered:
                    progress = 65
                elif "complete" in lowered or "installed" in lowered or "verifying" in lowered:
                    progress = 82
                else:
                    progress = max(int(job.get("progress") or 12), 12)
                job.update(progress=max(int(job.get("progress") or 12), progress),
                           message=line[:240])
                await _emit(progress_cb, job)
            code = await proc.wait()
        except asyncio.CancelledError:
            if proc and proc.returncode is None:
                proc.kill()
                await proc.wait()
            raise
        except Exception as exc:  # noqa: BLE001
            if proc and proc.returncode is None:
                proc.kill()
                await proc.wait()
            job.update(status="failed", message=f"安装命令执行失败：{exc}",
                       log="\n".join(output_lines[-30:]))
            await _emit(progress_cb, job)
            return dict(job)

        job.update(progress=90, stage="verify", message="正在验证 traceroute 安装结果...")
        await _emit(progress_cb, job)
        ok = code == 0 and traceroute_installed()
        if ok:
            job.update(status="success", progress=100, stage="done",
                       message="traceroute 安装完成，正在重新开始路由追踪", installed=True)
        else:
            detail = "\n".join(output_lines[-5:])[-800:]
            job.update(
                status="failed", progress=0, stage="failed",
                message=f"traceroute 安装失败（退出码 {code}）" + (f"：{detail}" if detail else ""),
                installed=False,
            )
        await _emit(progress_cb, job)
        return dict(job)
