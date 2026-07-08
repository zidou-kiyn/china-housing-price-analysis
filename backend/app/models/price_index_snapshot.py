from datetime import datetime

from sqlalchemy import Index, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PriceIndexSnapshot(Base):
    """房价指数快照（NBS 70 城等，100 基准 float）。

    指数是 float 且一城一月可有多口径（新建/二手 × 环比/同比/定基），与
    PriceSnapshot 的「元/㎡ 整数」语义不同，禁止混表（govstats.md §8.1）。
    唯一键含全部口径维度 + source，各源各口径序列独立共存。
    """

    __tablename__ = "price_index_snapshot"
    __table_args__ = (
        UniqueConstraint(
            "region_type", "region_id", "year_month",
            "dwelling_type", "base_type", "source",
            name="uq_price_index_region_month_kind_source",
        ),
        Index("idx_price_index_region", "region_type", "region_id"),
        Index("idx_price_index_month", "year_month"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    region_type: Mapped[str] = mapped_column(String(10), nullable=False)
    region_id: Mapped[int] = mapped_column(nullable=False)
    year_month: Mapped[str] = mapped_column(String(7), nullable=False)
    # 'new'(新建商品住宅) | 'second'(二手住宅)
    dwelling_type: Mapped[str] = mapped_column(String(10), nullable=False)
    # 'mom'(上月=100)；表结构预留 'yoy'(上年同月=100) / 'fixed'(定基)
    base_type: Mapped[str] = mapped_column(String(10), nullable=False)
    index_value: Mapped[float] = mapped_column(nullable=False)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
