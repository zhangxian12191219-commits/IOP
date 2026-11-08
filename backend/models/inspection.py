"""设备巡检任务与巡检报告

- InspectionTask：定时/手动巡检任务，巡检对象可以是资产库设备或自定义设备
- InspectionReport：内置巡检报告（python-docx 生成的 .docx）或上传的自定义 Word 报告
"""
from datetime import datetime

from sqlalchemy import JSON, Boolean, Column, DateTime, Integer, String, Text

from .database import Base


class InspectionTask(Base):
    """设备巡检任务"""

    __tablename__ = "inspection_tasks"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, comment="任务名称")
    enabled = Column(Boolean, default=True, index=True, comment="是否启用定时巡检")
    # 巡检对象：assets=资产库设备；custom=自定义设备（也可同时存在）
    target_mode = Column(
        String(20), default="assets", comment="assets / custom / mixed"
    )
    asset_ids = Column(JSON, default=list, comment="资产库设备 ID 列表")
    custom_devices = Column(
        JSON, default=list, comment="自定义设备 [{name,ip_address,device_type,note}]"
    )
    include_virtualization = Column(
        Boolean, default=False, comment="是否同时巡检虚拟化平台并写入报告"
    )
    run_commands = Column(
        Boolean, default=False, comment="是否使用设备备份 SSH 凭据执行厂商巡检命令"
    )

    # 调度：interval=每 N 小时；daily=每天 HH:mm（按系统配置时区）
    schedule_type = Column(String(20), default="interval", comment="interval / daily")
    interval_hours = Column(Integer, default=24, comment="间隔小时数（1~8760）")
    daily_time = Column(String(5), default="02:00", comment="每天执行时间 HH:mm")

    next_run_at = Column(DateTime, index=True, comment="下次执行时间（UTC）")
    last_run_at = Column(DateTime, comment="上次执行时间（UTC）")
    last_status = Column(
        String(20), default="idle", comment="idle/running/success/failed"
    )
    last_message = Column(Text, default="", comment="上次执行结果说明")
    last_report_id = Column(Integer, comment="上次生成的巡检报告 ID")

    created_by = Column(String(100), default="", comment="创建人")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class InspectionReport(Base):
    """巡检报告（内置生成或上传的 Word 文档）"""

    __tablename__ = "inspection_reports"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, index=True, comment="所属巡检任务 ID（上传报告可为空）")
    task_name = Column(String(200), default="", comment="任务名称快照")
    title = Column(String(300), nullable=False, comment="报告标题")
    source = Column(
        String(20), default="builtin", comment="builtin=系统生成 / upload=上传"
    )
    trigger = Column(
        String(20), default="manual", comment="manual / scheduled / upload"
    )
    status = Column(String(20), default="success", comment="success / failed")

    device_count = Column(Integer, default=0, comment="巡检设备总数")
    online_count = Column(Integer, default=0, comment="在线设备数")
    alert_count = Column(Integer, default=0, comment="未确认告警数")

    summary = Column(Text, default="", comment="摘要")
    conclusion = Column(Text, default="", comment="巡检结论")
    recommendations = Column(JSON, default=list, comment="整改建议列表")
    payload = Column(JSON, default=dict, comment="结构化巡检明细")

    # 落盘文件名（data/inspection_reports 下的纯文件名，禁止包含路径）
    filename = Column(String(255), comment="存储文件名")
    original_filename = Column(String(255), comment="原始文件名")
    file_size = Column(Integer, default=0, comment="文件大小（字节）")
    content_type = Column(
        String(120),
        default="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        comment="MIME 类型（统一 Word .docx）",
    )

    created_by = Column(String(100), default="", comment="生成/上传人")
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
