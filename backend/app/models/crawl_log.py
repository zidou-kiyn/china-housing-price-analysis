from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Index, SmallInteger, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class CrawlLog(Base):
    __tablename__ = "crawl_log"
    __table_args__ = (Index("idx_crawl_log_job", "job_id"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    job_id: Mapped[int] = mapped_column(ForeignKey("crawl_job.id"), nullable=False)
    url: Mapped[str] = mapped_column(String(500), nullable=False)
    status_code: Mapped[int | None] = mapped_column(SmallInteger)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text)
    raw_path: Mapped[str | None] = mapped_column(String(300))
    record_count: Mapped[int | None] = mapped_column(server_default="0")
    elapsed_ms: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    job: Mapped["CrawlJob"] = relationship(back_populates="logs")  # noqa: F821
