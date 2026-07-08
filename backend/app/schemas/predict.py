from pydantic import BaseModel, Field


class PredictionPointOut(BaseModel):
    target_month: str
    predicted_price: int
    confidence_lower: int | None = None
    confidence_upper: int | None = None


class PredictionResponse(BaseModel):
    region_type: str
    region_id: int
    region_name: str
    model_name: str
    model_version: str
    predictions: list[PredictionPointOut]

    model_config = {"protected_namespaces": ()}


class TrainRequest(BaseModel):
    model_name: str = Field("random_forest", pattern="^(random_forest|xgboost)$")
    # 训练数据范围：城市 code 列表；空 = 全部已采集数据
    city_codes: list[str] = Field(default_factory=list)

    model_config = {"protected_namespaces": ()}


class ModelVersionOut(BaseModel):
    model_name: str
    version: str
    trained_at: str
    metrics: dict
    training_samples: int
    is_active: bool
    # naive 基线对比（train.py meta.baselines）；旧版本 meta 无该字段时为 None
    beats_baseline: bool | None = None
    baseline_mape: float | None = None

    model_config = {"protected_namespaces": ()}


class ActiveModelRequest(BaseModel):
    model_name: str = Field(..., pattern="^(random_forest|xgboost)$")
    version: str = Field(..., pattern=r"^v\d+\.\d+$")

    model_config = {"protected_namespaces": ()}
