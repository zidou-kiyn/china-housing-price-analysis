"""预测查询与模型训练端点（docs/05 §3.6）。"""

import asyncio

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_admin, require_user
from app.core.config import settings
from app.core.database import async_session_factory
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
from app.schemas.admin_job import AdminJobOut
from app.schemas.predict import (
    ActiveModelRequest,
    ModelVersionOut,
    PredictionPointOut,
    PredictionResponse,
    TrainRequest,
)
from app.services import job_runner

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


async def _run_train(
    job_id: int,
    model_name: str,
    city_codes: list[str],
    region_type: str | None,
    region_ids: list[int] | None,
) -> None:
    """训练任务体：读数在独立 session，训练（同步 CPU 密集）放线程池避免阻塞事件循环。"""
    async with async_session_factory() as db:
        rows = await _load_snapshot_rows(db, region_type, region_ids)
    series_list = build_region_series(rows)

    meta = await asyncio.to_thread(
        run_training, model_name, series_list, _store(), city_codes=city_codes
    )
    await job_runner.report_progress(
        job_id,
        1,
        total=1,
        result=[
            {
                "ok": True,
                "model_name": meta["model_name"],
                "version": meta["version"],
                "metrics": meta["metrics"],
                "training_samples": meta["training_samples"],
            }
        ],
    )


@router.post("/admin/predict/train", response_model=AdminJobOut, status_code=202)
async def train_model(
    payload: TrainRequest,
    db: AsyncSession = Depends(get_session),
    _admin: UserAccount = Depends(require_admin),
):
    """提交异步训练任务，返回 job；训练完成后新版本不自动激活。"""
    region_ids: list[int] | None = None
    region_type: str | None = None

    if payload.city_codes:
        cities = (
            (await db.execute(select(City).where(City.code.in_(payload.city_codes))))
            .scalars()
            .all()
        )
        found = {c.code for c in cities}
        missing = [c for c in payload.city_codes if c not in found]
        if missing:
            raise ApiError(404, f"城市不存在: {', '.join(missing[:10])}", "CITY_NOT_FOUND")
        region_ids = list(
            (
                await db.execute(
                    select(District.id).where(
                        District.city_id.in_([c.id for c in cities])
                    )
                )
            ).scalars()
        )
        region_type = "district"
        if not region_ids:
            raise ApiError(400, "所选城市暂无区县数据，请先采集", "VALIDATION_ERROR")

    job = await job_runner.submit(
        "train",
        {"model_name": payload.model_name, "city_codes": payload.city_codes},
        lambda job_id: _run_train(
            job_id, payload.model_name, payload.city_codes, region_type, region_ids
        ),
        progress_total=1,
    )
    return job


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
