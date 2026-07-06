from datetime import datetime

from sqlalchemy import String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Prediction(Base):
    __tablename__ = "prediction"
    __table_args__ = (
        UniqueConstraint(
            "region_type", "region_id", "target_month", "model_name", "model_version",
            name="uq_prediction_region_model",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    region_type: Mapped[str] = mapped_column(String(10), nullable=False)
    region_id: Mapped[int] = mapped_column(nullable=False)
    target_month: Mapped[str] = mapped_column(String(7), nullable=False)
    predicted_price: Mapped[int] = mapped_column(nullable=False)
    confidence_lower: Mapped[int | None] = mapped_column()
    confidence_upper: Mapped[int | None] = mapped_column()
    model_name: Mapped[str] = mapped_column(String(50), nullable=False)
    model_version: Mapped[str] = mapped_column(String(20), nullable=False)
    features_json: Mapped[dict | None] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
