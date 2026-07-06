from datetime import datetime
from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, SmallInteger, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Community(Base):
    __tablename__ = "community"

    id: Mapped[int] = mapped_column(primary_key=True)
    area_id: Mapped[int] = mapped_column(ForeignKey("area.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[str | None] = mapped_column(String(200))
    year_built: Mapped[int | None] = mapped_column(SmallInteger)
    building_type: Mapped[str | None] = mapped_column(String(30))
    total_units: Mapped[int | None] = mapped_column()
    lat: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    lng: Mapped[Decimal | None] = mapped_column(Numeric(10, 7))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    area: Mapped["Area"] = relationship(back_populates="communities")  # noqa: F821
    listings: Mapped[list["Listing"]] = relationship(back_populates="community")  # noqa: F821
