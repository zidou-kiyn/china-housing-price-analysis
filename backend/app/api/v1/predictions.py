"""预测查询与模型训练端点（docs/05 §3.6）。"""

import asyncio

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_admin, require_user
from app.core.config import settings
from app.core.database import async_session_factory
from app.core.errors import ApiError
from app.ml.dataset import build_multi_source_series
from app.ml.predict import rolling_predict
from app.ml.train import ModelStore
from app.ml.train import train_model as run_training
from app.models.city import City
from app.models.district import District
from app.models.prediction import Prediction
from app.models.user import UserAccount
from app.schemas.admin_job import AdminJobOut
from app.schemas.predict import (
    ActiveModelRequest,
    ModelCleanupOut,
    ModelVersionOut,
    ModelVersionRef,
    PredictionPointOut,
    PredictionResponse,
    TrainRequest,
)
from app.core.source_policy import training_rows_only
from app.services import job_runner
from app.services.price_select import select_source_snapshots

router = APIRouter(tags=["predictions"])


def _store() -> ModelStore:
    return ModelStore(settings.ml_model_dir)


async def _load_source_rows(
    db: AsyncSession, region_type: str | None = None, region_ids: list[int] | None = None
) -> dict[str, list[dict]]:
    # 分源取数（不合并）：训练集构建器需要各源完整序列做口径校准与年度扩充。
    # creprice-first 白名单在此装载入口过滤：训练与预测只认 TRAINING_SOURCES 的源，
    # 非白名单源（58/kaggle/anjuke）的行进不了训练/预测集（构建器多源路径保留但走不到）。
    by_source = training_rows_only(await select_source_snapshots(db, region_type, region_ids))
    return {
        source: [
            {
                "region_type": s.region_type,
                "region_id": s.region_id,
                "year_month": s.year_month,
                "supply_price": s.supply_price,
            }
            for s in snaps
        ]
        for source, snaps in by_source.items()
    }


async def _load_index_rows(
    db: AsyncSession, region_type: str | None = None, region_ids: list[int] | None = None
) -> list[dict]:
    # NBS 指数表已删除（migration 007），返回空列表；build_multi_source_series
    # 在 index_rows 为空时自动回退到线性插值。
    return []


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
        # creprice-first 空窗期：旧多源模型已全删，等全量采集完成后重训 v1.8
        raise ApiError(
            404,
            "预测功能数据积累中，暂无可用模型（等 creprice 全量采集完成后重新训练）",
            "NO_ACTIVE_MODEL",
        )
    model, meta = loaded

    # 预测取数与训练同路径：分源取数 → 多源构建（年度城市校准+插值后亦可预测）。
    # 校准一致性强约束：ratio_curve 必须复用训练时曲线（meta["dataset"]），禁止
    # 用单区域数据重估；旧模型 meta 无 dataset 字段时现场估计（override=None），
    # 与其训练时未做校准的行为一致（单区域通常无重叠对，即不校准）。
    rows_by_source = await _load_source_rows(db, region_type, [region_id])
    index_rows = await _load_index_rows(db, region_type, [region_id])
    ratio_curve = (meta.get("dataset") or {}).get("ratio_curve")
    series_list, _ = build_multi_source_series(
        rows_by_source, ratio_curve_override=ratio_curve, index_rows=index_rows
    )
    if not series_list:
        raise ApiError(404, "该区域暂无可用历史数据", "PREDICTION_NOT_FOUND")

    try:
        points, data_quality = rolling_predict(model, meta, series_list[0], months_ahead)
    except ValueError as exc:
        raise ApiError(404, str(exc), "PREDICTION_NOT_FOUND")

    # 预测表治理：同 (region, model_name) 只保留当前版本，旧版本行同事务先删后插
    await db.execute(
        delete(Prediction).where(
            Prediction.region_type == region_type,
            Prediction.region_id == region_id,
            Prediction.model_name == meta["model_name"],
            Prediction.model_version != meta["version"],
        )
    )
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
        data_quality=data_quality,
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
        rows_by_source = await _load_source_rows(db, region_type, region_ids)
        index_rows = await _load_index_rows(db, region_type, region_ids)
    # 多源构建：口径校准 + 年度扩充（指数赋形/线性）+ 真实月度优先去重
    series_list, dataset_meta = build_multi_source_series(rows_by_source, index_rows=index_rows)

    meta = await asyncio.to_thread(
        run_training,
        model_name,
        series_list,
        _store(),
        city_codes=city_codes,
        dataset_meta=dataset_meta.to_dict(),
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
    best = store.best_versions()
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
            is_best=best.get(meta["model_name"]) == meta["version"],
            # 旧版本 meta 无 baselines/beats_baseline 字段 → None（兼容）
            beats_baseline=meta.get("beats_baseline"),
            baseline_mape=((meta.get("baselines") or {}).get("last_value") or {}).get("mape"),
        )
        for meta in store.list_all()
    ]


@router.delete("/admin/predict/models/{model_name}/{version}", status_code=204)
async def delete_model_version(
    # pattern 校验兼作路径穿越防护：拒绝 ".."、"." 及任何含点/斜杠的段（破坏性操作）
    model_name: str = Path(..., pattern=r"^[a-z][a-z0-9_]{0,63}$"),
    version: str = Path(..., pattern=r"^v\d+\.\d+$"),
    _admin: UserAccount = Depends(require_admin),
):
    """删除指定模型版本（pkl + meta）；活跃版本拒绝删除（409）。"""
    try:
        _store().delete(model_name, version)
    except ValueError as exc:
        raise ApiError(409, str(exc), "MODEL_ACTIVE")
    except FileNotFoundError as exc:
        raise ApiError(404, str(exc), "MODEL_NOT_FOUND")


@router.post("/admin/predict/models/cleanup", response_model=ModelCleanupOut)
async def cleanup_model_versions(
    keep_last: int = Query(3, ge=1, le=20),
    _admin: UserAccount = Depends(require_admin),
):
    """批量清理旧版本：每个模型保留最近 keep_last 个版本 + 活跃版本，返回删除清单。"""
    deleted = _store().cleanup(keep_last)
    return ModelCleanupOut(keep_last=keep_last, deleted=[ModelVersionRef(**d) for d in deleted])


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
