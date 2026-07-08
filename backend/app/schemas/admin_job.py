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
    city_codes: list[str] = Field(default_factory=list)


class RefreshCitiesResponse(BaseModel):
    total: int


class CityCoverageOut(BaseModel):
    id: int
    name: str
    code: str
    province: str | None
    tier: int | None
    district_count: int
    latest_month: str | None


class CityCoverageListResponse(BaseModel):
    total: int
    items: list[CityCoverageOut]
