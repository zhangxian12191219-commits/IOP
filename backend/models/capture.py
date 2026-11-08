"""网络抓包文件与分析报告记录。"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String, BigInteger

from .database import Base


class CaptureRecord(Base):
    """一次抓包任务保存的 .cap 文件与分析报告记录。"""
    __tablename__ = "capture_records"

    id = Column(Integer, primary_key=True, index=True)
    capture_id = Column(String(32), nullable=False, index=True, comment="抓包任务ID")
    filename = Column(String(255), nullable=False, unique=True, comment="Wireshark 兼容 .cap 文件名")
    report_filename = Column(String(255), comment="JSON 分析报告文件名")
    report_size = Column(Integer, default=0, comment="分析报告大小(字节)")
    interface_label = Column(String(255), comment="抓包网卡")
    bpf_filter = Column(String(200), comment="BPF过滤条件")
    status = Column(String(20), comment="完成/停止")
    started_at = Column(DateTime, comment="开始时间")
    ended_at = Column(DateTime, comment="结束时间")
    duration_seconds = Column(Float, default=0, comment="抓包时长(秒)")
    packets = Column(Integer, default=0, comment="报文数")
    bytes = Column(BigInteger, default=0, comment="字节数")
    throughput_mbps = Column(Float, default=0, comment="吞吐Mbps")
    findings_count = Column(Integer, default=0, comment="异常特征数量")
    file_size = Column(Integer, default=0, comment=".cap 文件大小(字节)")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "capture_id": self.capture_id,
            "filename": self.filename,
            "report_filename": self.report_filename or "",
            "report_size": self.report_size or 0,
            "interface_label": self.interface_label or "",
            "bpf_filter": self.bpf_filter or "",
            "status": self.status or "",
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "duration_seconds": self.duration_seconds or 0,
            "packets": self.packets or 0,
            "bytes": self.bytes or 0,
            "throughput_mbps": self.throughput_mbps or 0,
            "findings_count": self.findings_count or 0,
            "file_size": self.file_size or 0,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }
