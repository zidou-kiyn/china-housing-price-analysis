import datetime as dt
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Date, ForeignKey, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Listing(Base):
    __tablename__ = "listing"
    __table_args__ = (UniqueConstraint("source", "source_id", name="uq_listing_source"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    community_id: Mapped[int] = mapped_column(ForeignKey("community.id"), nullable=False)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    source_id: Mapped[str | None] = mapped_column(String(50))
    title: Mapped[str | None] = mapped_column(String(200))
    total_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    unit_price: Mapped[int | None] = mapped_column()
    area_sqm: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    layout: Mapped[str | None] = mapped_column(String(30))
    floor: Mapped[str | None] = mapped_column(String(30))
    orientation: Mapped[str | None] = mapped_column(String(30))
    listed_at: Mapped[dt.date | None] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    community: Mapped["Community"] = relationship(back_populates="listings")  # noqa: F821
