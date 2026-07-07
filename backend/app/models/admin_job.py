from datetime import datetime

from sqlalchemy import JSON, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class AdminJob(Base):
    """管理端后台任务（采集/地图爬取/模型训练），状态以 DB 为准供任一 worker 轮询。"""

    __tablename__ = "admin_job"

    id: Mapped[int] = mapped_column(primary_key=True)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)  # collect | geo_fetch | train
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="pending"
    )  # pending | running | success | failed
    payload: Mapped[dict | None] = mapped_column(JSON)
    progress_done: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    progress_total: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    result: Mapped[list | None] = mapped_column(JSON)  # 每单元结果摘要 [{city, ok, ...}]
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column()
    finished_at: Mapped[datetime | None] = mapped_column()

    __table_args__ = (
        # 同 kind 同时只允许一个活跃任务，兜底 submit 检查的并发竞态
        Index(
            "uq_admin_job_active_kind",
            "kind",
            unique=True,
            postgresql_where=text("status IN ('pending', 'running')"),
        ),
    )
