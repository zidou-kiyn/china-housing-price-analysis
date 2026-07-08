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
    """采集目标：显式 code 列表，或 all=true 全部城市，或 all_missing=true 仅缺数据城市。

    source 可选：覆盖本次采集使用的数据源；None 时用当前默认源（KV）。
    """

    city_codes: list[str] = Field(default_factory=list)
    all: bool = False
    all_missing: bool = False
    source: str | None = None


class GeoFetchRequest(BaseModel):
    """地图爬取目标：显式 code 列表，或 all_missing=true 补齐全部缺图城市。"""

    city_codes: list[str] = Field(default_factory=list)
    all_missing: bool = False


class RefreshCitiesResponse(BaseModel):
    total: int


class CollectSourceOut(BaseModel):
    """单个已注册数据源的能力描述。"""

    name: str
    capabilities: list[str]
    price_unit: str


class CollectSourcesResponse(BaseModel):
    """可用数据源列表 + 当前默认源。"""

    current: str
    items: list[CollectSourceOut]


class CollectSourceUpdate(BaseModel):
    """切换当前默认采集源。"""

    source: str


class AnnualImportRequest(BaseModel):
    """全国年度房价导入：source 为 listing_annual 的 source_key（58 / anjuke）。"""

    source: str = "58"


class AnnualImportResult(BaseModel):
    """全国年度房价导入覆盖统计。"""

    source: str
    matched: int
    skipped_count: int
    skipped_cities: list[str]
    snapshots: int
    # snapshot_validator 计数：值域/格式拦截、批内跳变标记（只增字段）
    rejected: int = 0
    flagged: int = 0


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
