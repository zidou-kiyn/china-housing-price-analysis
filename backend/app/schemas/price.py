from decimal import Decimal

from pydantic import BaseModel


class TrendPoint(BaseModel):
    year_month: str
    supply_price: int | None = None
    attention_price: int | None = None
    value_price: int | None = None
    sample_count: int | None = None
    # 该点数据来源（price_snapshot.source），前端据此标注口径（如年度·挂牌）
    source: str | None = None

    model_config = {"from_attributes": True}


class DistributionItem(BaseModel):
    price_range_low: int
    price_range_high: int
    percentage: Decimal | None = None
    count: int | None = None

    model_config = {"from_attributes": True}


class DistrictOverviewItem(BaseModel):
    id: int
    name: str
    code: str
    supply_price: int | None = None
    attention_price: int | None = None
    value_price: int | None = None
