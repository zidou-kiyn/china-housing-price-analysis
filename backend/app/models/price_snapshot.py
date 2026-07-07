from datetime import datetime

from sqlalchemy import Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PriceSnapshot(Base):
    __tablename__ = "price_snapshot"
    __table_args__ = (
        UniqueConstraint("region_type", "region_id", "year_month", name="uq_price_snapshot_region_month"),
        Index("idx_price_snapshot_region", "region_type", "region_id"),
        Index("idx_price_snapshot_month", "year_month"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    region_type: Mapped[str] = mapped_column(String(10), nullable=False)
    region_id: Mapped[int] = mapped_column(nullable=False)
    year_month: Mapped[str] = mapped_column(String(7), nullable=False)
    supply_price: Mapped[int | None] = mapped_column()
    attention_price: Mapped[int | None] = mapped_column()
    value_price: Mapped[int | None] = mapped_column()
    sample_count: Mapped[int | None] = mapped_column()
    # 该行最后写入的数据源（多源溯源注记；不进唯一约束，latest-wins）
    source: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
