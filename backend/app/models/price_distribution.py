from datetime import datetime
from decimal import Decimal

from sqlalchemy import Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class PriceDistribution(Base):
    __tablename__ = "price_distribution"
    __table_args__ = (
        UniqueConstraint(
            "region_type", "region_id", "year_month", "price_range_low",
            name="uq_price_distribution_region_range",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    region_type: Mapped[str] = mapped_column(String(10), nullable=False)
    region_id: Mapped[int] = mapped_column(nullable=False)
    year_month: Mapped[str] = mapped_column(String(7), nullable=False)
    price_range_low: Mapped[int] = mapped_column(nullable=False)
    price_range_high: Mapped[int] = mapped_column(nullable=False)
    percentage: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    count: Mapped[int | None] = mapped_column()
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
