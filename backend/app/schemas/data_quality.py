"""数据质量审计报告 schema（GET /admin/data-quality/report）。"""

from pydantic import BaseModel


class RatioOutlier(BaseModel):
    """多源重叠比值离群项：比值 = 高优先级源价 / 低优先级源价。"""

    region_type: str
    region_id: int
    region_name: str | None = None
    year_month: str
    source_a: str
    price_a: float
    source_b: str
    price_b: float
    ratio: float


class OverlapRatioSection(BaseModel):
    pairs: int = 0
    outliers_total: int = 0
    # 按偏离程度降序，截断 OUTLIERS_CAP 条（总数看 outliers_total）
    outliers: list[RatioOutlier] = []
    ratio_median: float | None = None


class DirectionConsistencySection(BaseModel):
    """方向一致率小节；status: ok | no overlap | "no index data"（指数未导入降级）。"""

    status: str
    regions: int = 0
    compared: int = 0
    matches: int = 0
    agreement_rate: float | None = None  # 百分比；compared=0 时 None
    flat_excluded: int = 0
    skipped_missing_index: int = 0
    note: str | None = None


class SourceCoverageOut(BaseModel):
    source: str
    kind: str  # snapshot | index
    granularity: str | None = None
    basis: str | None = None
    regions: int
    rows: int
    latest_month: str
    months_behind: int


class ModelFreshnessOut(BaseModel):
    """模型新鲜度：库指纹 vs 活跃模型 meta.dataset.fingerprint。"""

    status: str  # fresh | stale | unknown
    model_name: str | None = None
    model_version: str | None = None
    trained_at: str | None = None
    model_fingerprint: str | None = None
    data_fingerprint: str | None = None
    note: str | None = None

    model_config = {"protected_namespaces": ()}


class DataQualityReport(BaseModel):
    generated_at: str
    overlap_ratio: OverlapRatioSection
    creprice_vs_index: DirectionConsistencySection
    annual_vs_index: DirectionConsistencySection
    coverage: list[SourceCoverageOut]
    model_freshness: ModelFreshnessOut

    model_config = {"protected_namespaces": ()}
