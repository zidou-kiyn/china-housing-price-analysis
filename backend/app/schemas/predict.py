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
    # 依据序列的口径：monthly=真实月度 | annual_interp=年度挂牌插值 | mixed=混合
    data_quality: str
    predictions: list[PredictionPointOut]

    model_config = {"protected_namespaces": ()}


class TrainRequest(BaseModel):
    model_name: str = Field("random_forest", pattern="^(random_forest|xgboost|exp_smoothing)$")

    model_config = {"protected_namespaces": ()}


class ModelVersionOut(BaseModel):
    model_name: str
    version: str
    trained_at: str
    metrics: dict
    training_samples: int
    is_active: bool
    # 同模型下 MAPE 最低的版本（治理 R3）
    is_best: bool = False
    # naive 基线对比（train.py meta.baselines）；旧版本 meta 无该字段时为 None
    beats_baseline: bool | None = None
    baseline_mape: float | None = None

    model_config = {"protected_namespaces": ()}


class ModelVersionRef(BaseModel):
    model_name: str
    version: str

    model_config = {"protected_namespaces": ()}


class ModelCleanupOut(BaseModel):
    keep_last: int
    deleted: list[ModelVersionRef]


class ActiveModelRequest(BaseModel):
    model_name: str = Field(..., pattern="^(random_forest|xgboost)$")
    version: str = Field(..., pattern=r"^v\d+\.\d+$")

    model_config = {"protected_namespaces": ()}
