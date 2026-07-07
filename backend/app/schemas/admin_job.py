"""管理端后台任务与数据采集相关 schema。"""

from datetime import datetime

from pydantic import BaseModel, Field


class AdminJobOut(BaseModel):
    id: int
    kind: str
    status: str
    payload: dict | None
    progress_done: int
    progress_total: int
    result: list | None
    error: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None

    model_config = {"from_attributes": True}


class AdminJobListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[AdminJobOut]


class CollectRequest(BaseModel):
    """采集目标：显式 code 列表，或 all=true 全部城市，或 all_missing=true 仅缺数据城市。"""

    city_codes: list[str] = Field(default_factory=list)
    all: bool = False
    all_missing: bool = False


class GeoFetchRequest(BaseModel):
    """地图爬取目标：显式 code 列表，或 all_missing=true 补齐全部缺图城市。"""

    city_codes: list[str] = Field(default_factory=list)
    all_missing: bool = False


class RefreshCitiesResponse(BaseModel):
    total: int


class CityCoverageOut(BaseModel):
    id: int
    name: str
    code: str
    province: str | None
    district_count: int
    latest_month: str | None
    has_geo: bool


class CityCoverageListResponse(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[CityCoverageOut]
