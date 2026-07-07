"""预测查询与模型训练端点（docs/05 §3.6）。"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_admin, require_user
from app.core.config import settings
from app.core.errors import ApiError
from app.ml.features import build_region_series
from app.ml.predict import rolling_predict
from app.ml.train import ModelStore
from app.ml.train import train_model as run_training
from app.models.city import City
from app.models.district import District
from app.models.prediction import Prediction
from app.models.price_snapshot import PriceSnapshot
from app.models.user import UserAccount
from app.schemas.predict import (
    ActiveModelRequest,
    ModelVersionOut,
    PredictionPointOut,
    PredictionResponse,
    TrainRequest,
    TrainResponse,
)

router = APIRouter(tags=["predictions"])


def _store() -> ModelStore:
    return ModelStore(settings.ml_model_dir)


async def _load_snapshot_rows(
    db: AsyncSession, region_type: str | None = None, region_ids: list[int] | None = None
) -> list[dict]:
    stmt = select(PriceSnapshot)
    if region_type:
        stmt = stmt.where(PriceSnapshot.region_type == region_type)
    if region_ids:
        stmt = stmt.where(PriceSnapshot.region_id.in_(region_ids))
    result = await db.execute(stmt)
    return [
        {
            "region_type": s.region_type,
            "region_id": s.region_id,
            "year_month": s.year_month,
            "supply_price": s.supply_price,
        }
        for s in result.scalars()
    ]


@router.get("/predict/{region_id}", response_model=PredictionResponse)
async def get_prediction(
    region_id: int,
    region_type: str = Query(..., pattern="^(city|district)$"),
    months_ahead: int = Query(3, ge=1, le=12),
    db: AsyncSession = Depends(get_session),
    _user: UserAccount = Depends(require_user),
):
    region_model = City if region_type == "city" else District
    region = await db.get(region_model, region_id)
    if region is None:
        raise ApiError(404, "区域不存在", "REGION_NOT_FOUND")

    loaded = _store().load_active()
    if loaded is None:
        raise ApiError(404, "模型尚未训练，请先训练模型", "PREDICTION_NOT_FOUND")
    model, meta = loaded

    rows = await _load_snapshot_rows(db, region_type, [region_id])
    series_list = build_region_series(rows)
    if not series_list:
        raise ApiError(404, "该区域暂无可用历史数据", "PREDICTION_NOT_FOUND")

    try:
        points = rolling_predict(model, meta, series_list[0], months_ahead)
    except ValueError as exc:
        raise ApiError(404, str(exc), "PREDICTION_NOT_FOUND")

    for p in points:
        stmt = pg_insert(Prediction).values(
            region_type=region_type,
            region_id=region_id,
            target_month=p.target_month,
            predicted_price=p.predicted_price,
            confidence_lower=p.confidence_lower,
            confidence_upper=p.confidence_upper,
            model_name=meta["model_name"],
            model_version=meta["version"],
        )
        stmt = stmt.on_conflict_do_update(
            constraint="uq_prediction_region_model",
            set_={
                "predicted_price": stmt.excluded.predicted_price,
                "confidence_lower": stmt.excluded.confidence_lower,
                "confidence_upper": stmt.excluded.confidence_upper,
            },
        )
        await db.execute(stmt)
    await db.commit()

    return PredictionResponse(
        region_type=region_type,
        region_id=region_id,
        region_name=region.name,
        model_name=meta["model_name"],
        model_version=meta["version"],
        predictions=[
            PredictionPointOut(
                target_month=p.target_month,
                predicted_price=p.predicted_price,
                confidence_lower=p.confidence_lower,
                confidence_upper=p.confidence_upper,
            )
            for p in points
        ],
    )


@router.post("/admin/predict/train", response_model=TrainResponse, status_code=202)
async def train_model(
    payload: TrainRequest,
    db: AsyncSession = Depends(get_session),
    _admin: UserAccount = Depends(require_admin),
):
    city_codes: list[str] = []
    region_ids: list[int] | None = None
    region_type: str | None = None

    if payload.city_code:
        city = (
            await db.execute(select(City).where(City.code == payload.city_code))
        ).scalar_one_or_none()
        if city is None:
            raise ApiError(404, "城市不存在", "CITY_NOT_FOUND")
        districts = (
            (await db.execute(select(District.id).where(District.city_id == city.id)))
            .scalars()
            .all()
        )
        region_type = "district"
        region_ids = list(districts)
        city_codes = [payload.city_code]

    rows = await _load_snapshot_rows(db, region_type, region_ids)
    series_list = build_region_series(rows)

    try:
        meta = run_training(payload.model_name, series_list, _store(), city_codes=city_codes)
    except ValueError as exc:
        raise ApiError(400, str(exc), "VALIDATION_ERROR")

    return TrainResponse(
        message="训练完成",
        model_name=meta["model_name"],
        model_version=meta["version"],
        metrics=meta["metrics"],
        training_samples=meta["training_samples"],
    )


@router.get("/admin/predict/models", response_model=list[ModelVersionOut])
async def list_models(_admin: UserAccount = Depends(require_admin)):
    store = _store()
    active = store.get_active()
    return [
        ModelVersionOut(
            model_name=meta["model_name"],
            version=meta["version"],
            trained_at=meta["trained_at"],
            metrics=meta["metrics"],
            training_samples=meta["training_samples"],
            is_active=active is not None
            and active["model_name"] == meta["model_name"]
            and active["version"] == meta["version"],
        )
        for meta in store.list_all()
    ]


@router.put("/admin/predict/models/active", response_model=list[ModelVersionOut])
async def set_active_model(
    payload: ActiveModelRequest,
    _admin: UserAccount = Depends(require_admin),
):
    try:
        _store().set_active(payload.model_name, payload.version)
    except ValueError as exc:
        raise ApiError(404, str(exc), "MODEL_NOT_FOUND")
    return await list_models(_admin)
