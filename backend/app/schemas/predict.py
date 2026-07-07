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
    city_code: str | None = None

    model_config = {"protected_namespaces": ()}


class ModelVersionOut(BaseModel):
    model_name: str
    version: str
    trained_at: str
    metrics: dict
    training_samples: int
    is_active: bool

    model_config = {"protected_namespaces": ()}


class ActiveModelRequest(BaseModel):
    model_name: str = Field(..., pattern="^(random_forest|xgboost)$")
    version: str = Field(..., pattern=r"^v\d+\.\d+$")

    model_config = {"protected_namespaces": ()}


class TrainResponse(BaseModel):
    message: str
    model_name: str
    model_version: str
    metrics: dict
    training_samples: int

    model_config = {"protected_namespaces": ()}
