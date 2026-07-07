from pydantic import BaseModel


class RankItem(BaseModel):
    region_id: int
    region_name: str
    year_month: str | None = None
    supply_price: int | None = None
    attention_price: int | None = None
    value_price: int | None = None
    yoy_pct: float | None = None
    mom_pct: float | None = None


class RankResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[RankItem]


class ComparePoint(BaseModel):
    year_month: str
    price: int | None = None


class CompareRegion(BaseModel):
    region_id: int
    region_name: str
    data: list[ComparePoint]


class CompareResponse(BaseModel):
    price_type: str
    regions: list[CompareRegion]


class MapHeatItem(BaseModel):
    region_id: int
    region_name: str
    price: int | None = None


class MapHeatResponse(BaseModel):
    city_code: str
    region_type: str
    data: list[MapHeatItem]
