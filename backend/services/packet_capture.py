"""网络抓包与流量/异常分析。

只抓取并聚合报文头部信息，不保存或展示载荷内容。
运行时需要 Npcap（Windows）或 libpcap（Linux）。
"""
from __future__ import annotations

import io
import json
import logging
import struct
import threading
import time
import uuid
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)
from urllib.parse import quote

MAX_CAPTURE_SECONDS = 300
MAX_CAPTURE_PACKETS = 200000


class CaptureError(Exception):
    pass


_JOBS: Dict[str, CaptureJob] = {}
_JOBS_LOCK = threading.Lock()
_JOB_RETENTION_SECONDS = 3600


def capture_capability() -> Dict[str, Any]:
    try:
        import scapy  # noqa: F401
        from scapy.all import conf
        return {
            "available": True,
            "backend": "npcap" if getattr(conf, "use_npcap", False) else "libpcap",
            "message": "抓包引擎可用",
        }
    except Exception as exc:  # noqa: BLE001
        return {"available": False, "backend": "", "message": f"Scapy/Npcap 不可用：{exc}"}


def list_capture_interfaces() -> List[Dict[str, Any]]:
    try:
        from scapy.all import IFACES
    except Exception as exc:  # noqa: BLE001
        raise CaptureError(f"Scapy 不可用：{exc}") from exc
    result = []
    seen = set()
    windows_meta = {}
    try:
        from scapy.arch.windows import get_windows_if_list
        for item in get_windows_if_list():
            windows_meta[str(item.get("name") or "")] = item
    except Exception:
        windows_meta = {}
    for iface in IFACES.values():
        name = getattr(iface, "name", "") or ""
        network_name = getattr(iface, "network_name", "") or getattr(iface, "name", "")
        description = getattr(iface, "description", "") or ""
        meta = windows_meta.get(name, {})
        mac = getattr(iface, "mac", "") or meta.get("mac", "") or ""
        ips = meta.get("ips") or []
        if not ips:
            ips = [str(item) for item in (getattr(iface, "ips", None) or [])]
        # Windows IFACES.ips 有时只是地址族编号（4/6），不展示为 IP
        ips = [str(item) for item in ips if str(item).count(".") == 3 or ":" in str(item)]
        if not network_name or network_name in seen:
            continue
        seen.add(network_name)
        result.append({
            "id": network_name,
            "name": name,
            "description": description,
            "mac": mac,
            "ips": ips,
            "label": f"{name or description} {('· ' + description) if name and description else ''}".strip(),
        })
    return sorted(result, key=lambda item: (not bool(item["ips"]), item["label"].lower()))


def start_capture(interface: str, interface_label: str, duration: int, max_packets: int, bpf_filter: str = "") -> CaptureJob:
    if not interface:
        raise CaptureError("请选择抓包网卡")
    if duration < 1 or duration > MAX_CAPTURE_SECONDS:
        raise CaptureError(f"抓包时长必须在 1~{MAX_CAPTURE_SECONDS} 秒之间")
    if max_packets < 10 or max_packets > MAX_CAPTURE_PACKETS:
        raise CaptureError(f"最大报文数必须在 10~{MAX_CAPTURE_PACKETS} 之间")
    if any(ch in bpf_filter for ch in ("\r", "\n", "\x00")) or len(bpf_filter) > 200:
        raise CaptureError("BPF 过滤表达式不合法")
    job = CaptureJob(interface, interface_label or interface, duration, max_packets, bpf_filter)
    with _JOBS_LOCK:
        cutoff = time.monotonic() - _JOB_RETENTION_SECONDS
        for job_id in [key for key, item in _JOBS.items() if (item.ended_at or item.started_at) < cutoff]:
            _JOBS.pop(job_id, None)
        _JOBS[job.id] = job
    job.start()
    return job


def get_capture_job(job_id: str) -> Optional[CaptureJob]:
    with _JOBS_LOCK:
        return _JOBS.get(job_id)


def stop_capture_job(job_id: str) -> Optional[CaptureJob]:
    job = get_capture_job(job_id)
    if job:
        job.stop()
    return job


def list_capture_jobs() -> List[Dict[str, Any]]:
    with _JOBS_LOCK:
        jobs = list(_JOBS.values())
    jobs.sort(key=lambda item: item.started_at, reverse=True)
    return [
        {
            "id": item.id,
            "status": item.status,
            "interface": item.interface,
            "interface_label": item.interface_label,
            "started_at": item.started_time,
            "packets": item.packets,
            "error": item.error,
            "record_id": item.record_id,
            "capture_filename": item.capture_filename,
            "report_filename": item.report_filename,
        }
        for item in jobs
    ]


def capture_record_path(filename: str) -> Path:
    """返回报告文件路径，禁止目录穿越。"""
    from ..config import PROJECT_ROOT
    safe = Path(filename).name
    return Path(PROJECT_ROOT) / "data" / "captures" / safe


def list_capture_records(db, limit: int = 200) -> List[Dict[str, Any]]:
    from ..models.capture import CaptureRecord
    rows = db.query(CaptureRecord).order_by(CaptureRecord.created_at.desc()).limit(limit).all()
    return [row.to_dict() for row in rows]


def get_capture_record(db, record_id: int):
    from ..models.capture import CaptureRecord
    return db.query(CaptureRecord).filter(CaptureRecord.id == record_id).first()


def delete_capture_records(db, ids: List[int]) -> Dict[str, int]:
    from ..models.capture import CaptureRecord
    clean_ids = sorted({int(item) for item in ids if str(item).isdigit()})
    if not clean_ids:
        return {"deleted": 0, "files": 0}
    records = db.query(CaptureRecord).filter(CaptureRecord.id.in_(clean_ids)).all()
    deleted_files = 0
    for record in records:
        names = [record.filename]
        if getattr(record, "report_filename", None):
            names.append(record.report_filename)
        for name in {item for item in names if item}:
            path = capture_record_path(name)
            try:
                if path.is_file():
                    path.unlink()
                    deleted_files += 1
            except Exception as exc:  # noqa: BLE001
                logger.warning("删除抓包文件失败 %s: %s", path, exc)
    for record in records:
        db.delete(record)
    db.commit()
    return {"deleted": len(records), "files": deleted_files}


def build_capture_records_zip(db, ids: List[int]) -> tuple[bytes, str]:
    """把选中的 .cap 抓包文件打包为 ZIP，返回内容和下载文件名。"""
    from ..models.capture import CaptureRecord
    clean_ids = sorted({int(item) for item in ids if str(item).isdigit()})
    records = db.query(CaptureRecord).filter(CaptureRecord.id.in_(clean_ids)).all() if clean_ids else []
    if not records:
        raise CaptureError("没有可保存的抓包记录")
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for record in records:
            path = capture_record_path(record.filename)
            if path.is_file():
                archive.write(path, arcname=record.filename)
            elif getattr(record, "report_filename", None):
                # 兼容旧记录：此前只保存 JSON 分析报告
                legacy = capture_record_path(record.report_filename)
                if legacy.is_file():
                    archive.write(legacy, arcname=record.report_filename)
    content = buffer.getvalue()
    if not content:
        raise CaptureError("抓包文件不存在")
    return content, f"capture-reports-{datetime.now():%Y%m%d_%H%M%S}.zip"




def _now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _mac(value: Any) -> str:
    return str(value or "").lower()


class CaptureJob:
    def __init__(self, interface: str, interface_label: str, duration: int, max_packets: int, bpf_filter: str):
        self.id = uuid.uuid4().hex[:12]
        self.interface = interface
        self.interface_label = interface_label
        self.duration = max(1, min(MAX_CAPTURE_SECONDS, int(duration)))
        self.max_packets = max(10, min(MAX_CAPTURE_PACKETS, int(max_packets)))
        self.bpf_filter = (bpf_filter or "").strip()
        self.status = "starting"
        self.error = ""
        self.started_at = time.monotonic()
        self.ended_at: Optional[float] = None
        self.started_time = _now_iso()
        self.stop_requested = False
        self.sniffer = None
        self.thread: Optional[threading.Thread] = None
        self.record_id: Optional[int] = None
        self.capture_filename = ""
        self.report_filename = ""
        self.pcap_writer = None
        self.pcap_path: Optional[Path] = None
        self.pcap_error = ""
        self.save_error = ""
        self.lock = threading.Lock()
        self._reset_stats()

    def _reset_stats(self):
        self.packets = 0
        self.bytes = 0
        self.protocols = Counter()
        self.tcp_packets = 0
        self.udp_packets = 0
        self.icmp_packets = 0
        self.arp_packets = 0
        self.tcp_flags = Counter()
        self.syn_only = 0
        self.rst_packets = 0
        self.errors = 0
        self.small_packets = 0
        self.broadcast_packets = 0
        self.unique_ips = set()
        self.unique_macs = set()
        self.src_stats: Dict[str, Dict[str, Any]] = {}
        self.dst_stats: Dict[str, Dict[str, Any]] = {}
        self.mac_stats: Dict[str, Dict[str, Any]] = {}
        self.syn_sources: Counter = Counter()
        self.rst_sources: Counter = Counter()
        self.icmp_sources: Counter = Counter()
        self.ip_macs: Dict[str, Counter] = defaultdict(Counter)
        self.arp_claims: Dict[str, Counter] = defaultdict(Counter)
        self.port_stats: Counter = Counter()
        self.flow_stats: Dict[str, Dict[str, Any]] = {}

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True, name=f"capture-{self.id}")
        self.thread.start()

    def stop(self):
        self.stop_requested = True
        if self.status in ("starting", "running"):
            self.status = "stopping"

    def wait_finished(self, timeout: float = 5.0) -> bool:
        """等待抓包线程结束并完成 .cap 文件落盘/记录写入。"""
        thread = self.thread
        if thread and thread.is_alive():
            thread.join(timeout)
        return not (thread and thread.is_alive())

    def _open_capture(self):
        """创建 Wireshark 兼容的 .cap 文件并建立流式写入器。"""
        from scapy.utils import PcapWriter
        from ..config import PROJECT_ROOT

        capture_dir = Path(PROJECT_ROOT) / "data" / "captures"
        capture_dir.mkdir(parents=True, exist_ok=True)
        self.capture_filename = f"capture_{datetime.now():%Y%m%d_%H%M%S}_{self.id}.cap"
        self.pcap_path = capture_dir / self.capture_filename
        self.pcap_writer = PcapWriter(str(self.pcap_path), append=False, sync=False)
        logger.info("抓包文件: %s", self.pcap_path)

    def _close_capture(self):
        try:
            if self.pcap_writer is not None:
                self.pcap_writer.close()
        except Exception as exc:  # noqa: BLE001
            logger.warning("关闭抓包文件失败 %s: %s", self.pcap_path, exc)
            self.pcap_error = str(exc)[:200]
        finally:
            self.pcap_writer = None
        if self.pcap_path and self.pcap_path.exists() and self.pcap_path.stat().st_size == 0 and self.packets == 0:
            # 即使没有抓到报文，也生成一个合法的空 pcap 文件，保证“停止即产生文件记录”
            try:
                with open(self.pcap_path, "wb") as handle:
                    handle.write(struct.pack("<IHHIIII", 0xA1B2C3D4, 2, 4, 0, 0, 65535, 1))
            except OSError as exc:
                logger.warning("生成空 .cap 文件失败 %s: %s", self.pcap_path, exc)
                self.pcap_error = str(exc)[:200]

    def _run(self):
        from scapy.sendrecv import AsyncSniffer

        try:
            self._open_capture()
            self.status = "running"
            self.sniffer = AsyncSniffer(
                iface=self.interface,
                filter=self.bpf_filter or None,
                prn=self._handle,
                store=False,
            )
            self.sniffer.start()
            deadline = self.started_at + self.duration
            while time.monotonic() < deadline:
                if self.stop_requested or self.packets >= self.max_packets:
                    break
                time.sleep(0.12)
            if self.sniffer and self.sniffer.running:
                self.sniffer.stop()
            with self.lock:
                if not self.stop_requested:
                    self.status = "completed"
                else:
                    self.status = "stopped"
                self.ended_at = time.monotonic()
        except Exception as exc:  # noqa: BLE001
            with self.lock:
                self.status = "error"
                self.error = str(exc)
                self.ended_at = time.monotonic()
        finally:
            self._close_capture()
        if self.status in ("completed", "stopped"):
            self._persist_report()

    def _persist_report(self):
        """保存 Wireshark 兼容 .cap 文件，并附带 JSON 分析报告记录。"""
        try:
            from ..config import PROJECT_ROOT
            from ..models.capture import CaptureRecord
            from ..models.database import SessionLocal

            if not self.pcap_path or not self.pcap_path.exists() or self.pcap_path.stat().st_size < 24:
                raise RuntimeError(self.pcap_error or "未生成有效的 .cap 抓包文件")
            snapshot = self.snapshot(None)
            report = {
                "type": "snmp-monitor-capture-report",
                "version": 1,
                "saved_at": datetime.now().isoformat(timespec="seconds"),
                "capture_file": self.capture_filename,
                "summary": snapshot,
            }
            report_dir = Path(PROJECT_ROOT) / "data" / "captures"
            report_dir.mkdir(parents=True, exist_ok=True)
            report_filename = f"capture_{datetime.now():%Y%m%d_%H%M%S}_{self.id}.json"
            report_path = report_dir / report_filename
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
            db = SessionLocal()
            try:
                record = CaptureRecord(
                    capture_id=self.id,
                    filename=self.capture_filename,
                    report_filename=report_filename,
                    report_size=report_path.stat().st_size,
                    interface_label=self.interface_label,
                    bpf_filter=self.bpf_filter,
                    status=self.status,
                    started_at=datetime.fromisoformat(self.started_time),
                    ended_at=datetime.now(),
                    duration_seconds=snapshot.get("elapsed_seconds") or 0,
                    packets=snapshot.get("packets") or 0,
                    bytes=snapshot.get("bytes") or 0,
                    throughput_mbps=snapshot.get("throughput_mbps") or 0,
                    findings_count=len(snapshot.get("findings") or []),
                    file_size=self.pcap_path.stat().st_size,
                )
                db.add(record)
                db.commit()
                db.refresh(record)
                with self.lock:
                    self.record_id = record.id
                    self.report_filename = report_filename
            finally:
                db.close()
        except Exception as exc:  # noqa: BLE001
            logger.exception("保存抓包文件失败: %s", exc)
            with self.lock:
                self.save_error = str(exc)[:300]

    def _bump(self, table: Dict[str, Dict[str, Any]], key: str, size: int):
        if not key:
            return
        item = table.get(key)
        if item is None:
            table[key] = {"packets": 1, "bytes": size, "last": time.monotonic()}
        else:
            item["packets"] += 1
            item["bytes"] += size
            item["last"] = time.monotonic()

    def _handle(self, packet):
        try:
            from scapy.layers.inet import ICMP, IP, TCP, UDP
            from scapy.layers.l2 import ARP, Ether

            size = len(packet)
            with self.lock:
                if self.packets >= self.max_packets:
                    self.stop_requested = True
                    return
                self.packets += 1
                self.bytes += size
                if self.pcap_writer is not None:
                    try:
                        self.pcap_writer.write(packet)
                    except Exception as exc:  # noqa: BLE001
                        logger.warning("写入 .cap 抓包文件失败: %s", exc)
                        self.pcap_error = str(exc)[:200]
                        try:
                            self.pcap_writer.close()
                        except Exception:
                            pass
                        self.pcap_writer = None
                if size < 60:
                    self.small_packets += 1
                eth = packet.getlayer(Ether)
                src_mac = _mac(eth.src) if eth else ""
                dst_mac = _mac(eth.dst) if eth else ""
                if src_mac:
                    self.unique_macs.add(src_mac)
                    self._bump(self.mac_stats, src_mac, size)
                if dst_mac and (dst_mac == "ff:ff:ff:ff:ff:ff" or (int(dst_mac.split(":")[0], 16) & 1)):
                    self.broadcast_packets += 1
                arp = packet.getlayer(ARP)
                if arp and arp.psrc:
                    self.arp_packets += 1
                    self.arp_claims[str(arp.psrc)][_mac(arp.hwsrc)] += 1
                ip = packet.getlayer(IP)
                if ip is None:
                    if eth:
                        self.protocols["OTHER"] += 1
                    return
                src, dst = str(ip.src), str(ip.dst)
                self.unique_ips.add(src)
                self.unique_ips.add(dst)
                self._bump(self.src_stats, src, size)
                self._bump(self.dst_stats, dst, size)
                if src_mac:
                    self.ip_macs[src][src_mac] += 1
                tcp = packet.getlayer(TCP)
                udp = packet.getlayer(UDP)
                icmp = packet.getlayer(ICMP)
                proto = "OTHER"
                dst_port = None
                if tcp is not None:
                    proto = "TCP"
                    self.tcp_packets += 1
                    dst_port = int(tcp.dport or 0)
                    flags = int(tcp.flags)
                    for name, mask in (("FIN", 0x01), ("SYN", 0x02), ("RST", 0x04), ("PSH", 0x08), ("ACK", 0x10), ("URG", 0x20)):
                        if flags & mask:
                            self.tcp_flags[name] += 1
                    if (flags & 0x02) and not (flags & 0x10):
                        self.syn_only += 1
                        self.syn_sources[src] += 1
                    if flags & 0x04:
                        self.rst_packets += 1
                        self.rst_sources[src] += 1
                    if flags & 0x04:
                        self.errors += 1
                elif udp is not None:
                    proto = "UDP"
                    self.udp_packets += 1
                    dst_port = int(udp.dport or 0)
                elif icmp is not None:
                    proto = "ICMP"
                    self.icmp_packets += 1
                    self.icmp_sources[src] += 1
                    if int(getattr(icmp, "type", 0) or 0) == 3:
                        self.errors += 1
                self.protocols[proto] += 1
                if dst_port is not None:
                    self.port_stats[f"{proto}/{dst_port}"] += 1
                flow_key = f"{src}|{dst}|{proto}|{dst_port or '-'}"
                flow = self.flow_stats.get(flow_key)
                if flow is None:
                    self.flow_stats[flow_key] = {
                        "src": src, "dst": dst, "proto": proto, "dst_port": dst_port,
                        "packets": 1, "bytes": size, "mac": src_mac,
                    }
                else:
                    flow["packets"] += 1
                    flow["bytes"] += size
        except Exception:
            # 单个异常报文不影响整个抓包任务
            return

    def snapshot(self, db=None) -> Dict[str, Any]:
        with self.lock:
            now = time.monotonic()
            elapsed = max(0.05, (self.ended_at or now) - self.started_at)
            total = self.packets
            protocols = dict(self.protocols)
            src_items = sorted(self.src_stats.items(), key=lambda item: item[1]["bytes"], reverse=True)
            dst_items = sorted(self.dst_stats.items(), key=lambda item: item[1]["bytes"], reverse=True)
            mac_items = sorted(self.mac_stats.items(), key=lambda item: item[1]["bytes"], reverse=True)
            flows = sorted(self.flow_stats.values(), key=lambda item: item["bytes"], reverse=True)
            port_items = self.port_stats.most_common(15)
            arp_conflicts = []
            for ip, macs in self.arp_claims.items():
                if len(macs) > 1:
                    arp_conflicts.append({"ip": ip, "macs": list(macs.keys()), "counts": dict(macs)})
            ip_conflicts = []
            for ip, macs in self.ip_macs.items():
                if len(macs) > 1:
                    ip_conflicts.append({"ip": ip, "macs": list(macs.keys()), "counts": dict(macs)})

            def host_rows(items, limit=12):
                rows = []
                for ip, info in items[:limit]:
                    macs = self.ip_macs.get(ip)
                    mac = macs.most_common(1)[0][0] if macs else ""
                    rows.append({
                        "ip": ip, "mac": mac, "packets": info["packets"], "bytes": info["bytes"],
                        "share": round(info["bytes"] / self.bytes * 100, 1) if self.bytes else 0,
                    })
                return rows

            findings = self._findings(total, src_items, arp_conflicts + ip_conflicts)
            result = {
                "id": self.id,
                "status": self.status,
                "error": self.error,
                "interface": self.interface,
                "interface_label": self.interface_label,
                "filter": self.bpf_filter,
                "started_at": self.started_time,
                "elapsed_seconds": round(elapsed, 1),
                "duration": self.duration,
                "max_packets": self.max_packets,
                "packets": total,
                "bytes": self.bytes,
                "packets_per_second": round(total / elapsed, 1),
                "bytes_per_second": round(self.bytes / elapsed, 1),
                "throughput_mbps": round(self.bytes * 8 / elapsed / 1_000_000, 2),
                "unique_ips": len(self.unique_ips),
                "unique_macs": len(self.unique_macs),
                "protocols": protocols,
                "tcp_flags": dict(self.tcp_flags),
                "tcp_packets": self.tcp_packets,
                "udp_packets": self.udp_packets,
                "icmp_packets": self.icmp_packets,
                "arp_packets": self.arp_packets,
                "syn_only": self.syn_only,
                "rst_packets": self.rst_packets,
                "errors": self.errors,
                "small_packets": self.small_packets,
                "broadcast_packets": self.broadcast_packets,
                "error_percent": round(self.errors / total * 100, 2) if total else 0,
                "broadcast_percent": round(self.broadcast_packets / total * 100, 2) if total else 0,
                "top_sources": host_rows(src_items),
                "top_destinations": host_rows(dst_items),
                "top_macs": [
                    {"mac": mac, "packets": info["packets"], "bytes": info["bytes"]}
                    for mac, info in mac_items[:10]
                ],
                "top_flows": flows[:12],
                "top_ports": [{"port": port, "packets": count} for port, count in port_items],
                "arp_ip_conflicts": arp_conflicts,
                "ip_mac_conflicts": ip_conflicts,
                "findings": findings,
                "record_id": self.record_id,
                "capture_filename": self.capture_filename,
                "report_filename": self.report_filename,
                "pcap_error": self.pcap_error,
                "save_error": self.save_error,
            }
        if db is not None:
            self._enrich(db, result)
        return result

    def _findings(self, total: int, src_items, mac_conflicts):
        findings = []
        top_source = src_items[0] if src_items else None
        if self.syn_only >= 80 and self.syn_only / max(self.tcp_packets, 1) >= 0.5:
            src = self.syn_sources.most_common(1)[0][0] if self.syn_sources else ""
            findings.append({
                "type": "syn_flood", "severity": "critical", "title": "疑似 SYN Flood 攻击",
                "description": f"SYN-only 报文 {self.syn_only} 个，占 TCP 报文 {round(self.syn_only / max(self.tcp_packets, 1) * 100, 1)}%，存在半连接洪泛特征。",
                "ip": src, "evidence": f"SYN-only {self.syn_only} / TCP {self.tcp_packets}",
            })
        if self.rst_packets >= 50 and self.rst_packets / max(self.tcp_packets, 1) >= 0.25:
            src = self.rst_sources.most_common(1)[0][0] if self.rst_sources else ""
            findings.append({
                "type": "rst_storm", "severity": "warning", "title": "TCP RST 异常激增",
                "description": f"RST 报文 {self.rst_packets} 个，可能存在扫描、连接拒绝或异常中断。",
                "ip": src, "evidence": f"RST {self.rst_packets} / TCP {self.tcp_packets}",
            })
        if self.icmp_packets >= 100 and self.icmp_packets / max(total, 1) >= 0.25:
            src = self.icmp_sources.most_common(1)[0][0] if self.icmp_sources else ""
            findings.append({
                "type": "icmp_flood", "severity": "warning", "title": "ICMP 流量异常",
                "description": f"ICMP 报文 {self.icmp_packets} 个，占总流量 {round(self.icmp_packets / max(total, 1) * 100, 1)}%，可能存在 Ping Flood 或探测扫描。",
                "ip": src, "evidence": f"ICMP {self.icmp_packets} / total {total}",
            })
        if self.arp_packets >= 100 and self.arp_packets / max(total, 1) >= 0.25:
            findings.append({
                "type": "arp_storm", "severity": "warning", "title": "ARP 广播/欺骗风险",
                "description": f"ARP 报文 {self.arp_packets} 个，占总流量 {round(self.arp_packets / max(total, 1) * 100, 1)}%。",
                "ip": "", "evidence": f"ARP {self.arp_packets} / total {total}",
            })
        if self.broadcast_packets >= 150 and self.broadcast_packets / max(total, 1) >= 0.25:
            findings.append({
                "type": "broadcast_storm", "severity": "warning", "title": "广播风暴风险",
                "description": f"广播/组播报文 {self.broadcast_packets} 个，占总流量 {round(self.broadcast_packets / max(total, 1) * 100, 1)}%。",
                "ip": "", "evidence": f"broadcast/multicast {self.broadcast_packets} / total {total}",
            })
        if self.errors >= 50 and self.errors / max(total, 1) >= 0.08:
            findings.append({
                "type": "error_storm", "severity": "warning", "title": "错误包比例偏高",
                "description": f"RST/ICMP 不可达等错误报文 {self.errors} 个，占比 {round(self.errors / max(total, 1) * 100, 1)}%，可能存在链路或攻击异常。",
                "ip": "", "evidence": f"errors {self.errors} / total {total}",
            })
        if top_source and self.bytes > 8_000_000 and top_source[1]["bytes"] / max(self.bytes, 1) >= 0.5:
            findings.append({
                "type": "heavy_source", "severity": "info", "title": "单 IP 大流量",
                "description": f"源 IP {top_source[0]} 占用总字节数 {round(top_source[1]['bytes'] / self.bytes * 100, 1)}%，建议核查是否为大流量传输或异常外联。",
                "ip": top_source[0], "evidence": f"bytes {top_source[1]['bytes']} / total {self.bytes}",
            })
        for conflict in mac_conflicts[:8]:
            findings.append({
                "type": "mac_conflict", "severity": "critical", "title": "IP / MAC 冲突或 ARP 欺骗",
                "description": f"IP {conflict['ip']} 对应多个 MAC：{', '.join(conflict['macs'])}，可能存在 ARP 欺骗、IP 冲突或虚拟化漂移。",
                "ip": conflict["ip"], "mac": ",".join(conflict["macs"]),
                "evidence": f"conflict MACs {len(conflict['macs'])}",
            })
        if self.small_packets >= 80 and self.small_packets / max(total, 1) >= 0.3:
            findings.append({
                "type": "small_packet_storm", "severity": "info", "title": "小包比例偏高",
                "description": f"小于 60 字节的报文 {self.small_packets} 个，占 {round(self.small_packets / max(total, 1) * 100, 1)}%，可能为扫描、控制流量或链路异常。",
                "ip": "", "evidence": f"small {self.small_packets} / total {total}",
            })
        if not findings and total > 0:
            findings.append({
                "type": "normal", "severity": "info", "title": "暂未发现明显攻击特征",
                "description": "当前抓包窗口未达到常见攻击/错误阈值，请结合业务流量与接口错误计数继续观察。",
                "ip": "", "evidence": f"sampled {total} packets",
            })
        return findings[:20]

    def _enrich(self, db, result: Dict[str, Any]):
        from ..models.models import Device, DeviceInterface

        ips = set()
        macs = set()
        for key in ("top_sources", "top_destinations"):
            for item in result.get(key, []):
                ips.add(item.get("ip"))
                if item.get("mac"):
                    macs.add(item["mac"])
        for finding in result.get("findings", []):
            if finding.get("ip"):
                ips.add(finding["ip"])
            for mac in str(finding.get("mac") or "").split(","):
                if ":" in mac:
                    macs.add(mac)
        ips = {ip for ip in ips if ip}
        macs = {mac for mac in macs if mac}
        devices = db.query(Device).filter(Device.ip_address.in_(ips)).all() if ips else []
        ifaces = db.query(DeviceInterface).filter(DeviceInterface.if_mac.in_(macs)).all() if macs else []
        by_ip = {item.ip_address: item for item in devices}
        by_mac = {item.if_mac.lower(): item for item in ifaces if item.if_mac}

        def host(ip: str, mac: str = ""):
            device = by_ip.get(ip)
            iface = by_mac.get((mac or "").lower())
            if iface and not device:
                device = db.query(Device).filter(Device.id == iface.device_id).first()
            return {
                "device_id": device.id if device else None,
                "device_name": device.name if device else "",
                "device_type": device.device_type if device else "",
                "device_ip": device.ip_address if device else "",
                "interface_name": iface.if_name if iface else "",
                "interface_description": iface.if_description if iface else "",
                "capture_interface": self.interface_label,
            }

        for key in ("top_sources", "top_destinations"):
            for item in result.get(key, []):
                item.update(host(item.get("ip", ""), item.get("mac", "")))
        for finding in result.get("findings", []):
            finding.update(host(finding.get("ip", ""), str(finding.get("mac") or "").split(",")[0]))
        for flow in result.get("top_flows", []):
            flow.update(host(flow.get("src", ""), flow.get("mac", "")))
        result["capture"] = {"interface": self.interface, "interface_label": self.interface_label}
