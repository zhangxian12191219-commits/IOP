"""拓扑自动发现 - 基于 SNMP LLDP / CDP 邻居表

发现逻辑:
1. 遍历所有启用设备，读取其 LLDP（回退 CDP）邻居表
2. 把邻居的 chassisId / sysName 与已录入设备的 sysName、名称、IP 做匹配
3. 匹配成功则写入 device_connections（含两端接口名）
"""
import asyncio
import logging
from datetime import datetime
from typing import Dict, List, Optional, Set, Tuple

from sqlalchemy.orm import Session

from ..config import Config
from ..models.models import Device, DeviceConnection, DeviceInterface
from .snmp_client import SNMPClient

logger = logging.getLogger(__name__)


class TopologyDiscovery:
    def __init__(self, db: Session):
        self.db = db

    # ---------- 匹配 ----------
    @staticmethod
    def _norm(text: Optional[str]) -> str:
        return (text or "").strip().lower()

    def _build_lookup(self, devices: List[Device]) -> Dict[str, Device]:
        """构造 标识 -> 设备 的映射（sysName / 设备名 / IP / 名称中的短主机名）"""
        lookup: Dict[str, Device] = {}
        for dev in devices:
            for key in (dev.name, dev.ip_address, dev.model):
                k = self._norm(key)
                if k:
                    lookup.setdefault(k, dev)
            # 名称里的短主机名（去掉域名后缀）
            if dev.name and "." in dev.name:
                short = self._norm(dev.name.split(".")[0])
                if short:
                    lookup.setdefault(short, dev)
        return lookup

    # ---------- 采集邻居 ----------
    async def _neighbors_of(self, device: Device) -> List[Dict]:
        # 自动携带 SNMPv3 参数
        client = SNMPClient.from_device(
            device,
            # 发现流程对超时更敏感，避免整体接口被拖长
            timeout=min(Config.SNMP_TIMEOUT, 2),
            retries=0,
        )
        try:
            return await asyncio.wait_for(client.get_lldp_neighbors(), timeout=12)
        except asyncio.TimeoutError:
            logger.debug("读取 %s 邻居超时", device.ip_address)
            return []
        except Exception as exc:
            logger.debug("读取 %s 邻居失败: %s", device.ip_address, exc)
            return []

    def _local_if_name(self, device_id: int, local_port_num: str) -> str:
        """LLDP localPortNum 通常等于 ifIndex"""
        row = (
            self.db.query(DeviceInterface)
            .filter_by(device_id=device_id, if_index=str(local_port_num))
            .first()
        )
        if row and row.if_name:
            return row.if_name
        return f"ifIndex {local_port_num}" if local_port_num else ""

    # ---------- 主流程 ----------
    async def discover(self) -> int:
        devices = self.db.query(Device).filter(Device.is_enabled == True).all()
        # 演示设备不参与真实 SNMP 发现
        devices = [d for d in devices if not (d.tags and "demo" in d.tags)]
        if len(devices) < 2:
            return 0

        lookup = self._build_lookup(devices)
        results = await asyncio.gather(*[self._neighbors_of(d) for d in devices])

        existing: Set[Tuple[int, str, int, str]] = set()
        for conn in self.db.query(DeviceConnection).all():
            existing.add((conn.source_device_id, conn.source_interface or "",
                          conn.dest_device_id, conn.dest_interface or ""))

        added = 0
        for device, neighbours in zip(devices, results):
            for nb in neighbours:
                remote_keys = [
                    self._norm(nb.get("remote_sys_name")),
                    self._norm(nb.get("remote_chassis_id")),
                    self._norm(str(nb.get("remote_mgmt_ip") or "")),
                ]
                peer: Optional[Device] = None
                for key in remote_keys:
                    if key and key in lookup:
                        peer = lookup[key]
                        break
                if peer is None or peer.id == device.id:
                    continue

                src_if = self._local_if_name(device.id, str(nb.get("local_port_num") or ""))
                dst_if = nb.get("remote_port_id") or ""

                # 双向都记录一次，去重（A→B 与 B→A 视为同一条）
                forward = (device.id, src_if, peer.id, dst_if)
                backward = (peer.id, dst_if, device.id, src_if)
                if forward in existing or backward in existing:
                    continue

                self.db.add(DeviceConnection(
                    source_device_id=device.id,
                    source_interface=src_if,
                    dest_device_id=peer.id,
                    dest_interface=dst_if,
                    discovered_at=datetime.utcnow(),
                ))
                existing.add(forward)
                existing.add(backward)
                added += 1

        if added:
            self.db.commit()
        return added
