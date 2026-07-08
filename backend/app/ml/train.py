"""模型训练、评估与版本化：RF + XGBoost（docs/06 §4~6、M3-1）。"""

import json
from datetime import datetime, timezone
from itertools import product
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import TimeSeriesSplit
from xgboost import XGBRegressor

from app.ml.features import REGION_TYPE_ENC, RegionSeries, build_training_frame, feature_columns

LAG_CANDIDATES = (12, 6, 3)
MIN_SAMPLES = 20
MIN_CV_SAMPLES = 30
CV_FOLDS = 3
WORST_REGIONS_LIMIT = 5  # per_region_metrics 只留最差 N 个，避免 330 城时 meta 膨胀
RF_PARAMS = {
    "n_estimators": 100,
    "max_depth": 10,
    "min_samples_split": 5,
    "random_state": 42,
}
RF_GRID = {
    "n_estimators": (100, 300),
    "max_depth": (10, None),
}
RF_FIXED_PARAMS = {"min_samples_split": 5}  # 网格外固定项（与 RF_PARAMS 一致）
XGB_DEFAULT_PARAMS = {
    "n_estimators": 300,
    "max_depth": 3,
    "learning_rate": 0.05,
    "random_state": 42,
}
XGB_GRID = {
    "n_estimators": (100, 300),
    "max_depth": (3, 5),
    "learning_rate": (0.05, 0.1),
}


class ModelStore:
    """models/{model_name}/v{x}.pkl + v{x}_meta.json 的读写、版本与活跃指针管理。"""

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)

    def _model_dir(self, model_name: str) -> Path:
        return self.base_dir / model_name

    def _active_path(self) -> Path:
        return self.base_dir / "active.json"

    def versions(self, model_name: str) -> list[str]:
        model_dir = self._model_dir(model_name)
        if not model_dir.exists():
            return []
        versions = [p.stem for p in model_dir.glob("v*.pkl")]
        return sorted(versions, key=lambda v: [int(x) for x in v[1:].split(".")])

    def next_version(self, model_name: str) -> str:
        versions = self.versions(model_name)
        if not versions:
            return "v1.0"
        major, minor = (int(x) for x in versions[-1][1:].split("."))
        return f"v{major}.{minor + 1}"

    def save(self, model_name: str, version: str, model, meta: dict) -> Path:
        model_dir = self._model_dir(model_name)
        model_dir.mkdir(parents=True, exist_ok=True)
        path = model_dir / f"{version}.pkl"
        joblib.dump(model, path)
        (model_dir / f"{version}_meta.json").write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return path

    def load(self, model_name: str, version: str) -> tuple[object, dict] | None:
        model_dir = self._model_dir(model_name)
        pkl = model_dir / f"{version}.pkl"
        meta_path = model_dir / f"{version}_meta.json"
        if not pkl.exists() or not meta_path.exists():
            return None
        model = joblib.load(pkl)
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        return model, meta

    def load_latest(self, model_name: str) -> tuple[object, dict] | None:
        versions = self.versions(model_name)
        if not versions:
            return None
        return self.load(model_name, versions[-1])

    def list_all(self) -> list[dict]:
        """全部模型全部版本的 meta，按 (model_name, 版本号) 排序。"""
        metas = []
        if not self.base_dir.exists():
            return metas
        for model_dir in sorted(p for p in self.base_dir.iterdir() if p.is_dir()):
            for version in self.versions(model_dir.name):
                meta_path = model_dir / f"{version}_meta.json"
                if meta_path.exists():
                    metas.append(json.loads(meta_path.read_text(encoding="utf-8")))
        return metas

    def get_active(self) -> dict | None:
        path = self._active_path()
        if not path.exists():
            return None
        try:
            pointer = json.loads(path.read_text(encoding="utf-8"))
            return {"model_name": pointer["model_name"], "version": pointer["version"]}
        except (ValueError, KeyError):
            return None

    def set_active(self, model_name: str, version: str) -> None:
        if version not in self.versions(model_name):
            raise ValueError(f"模型版本不存在: {model_name}/{version}")
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._active_path().write_text(
            json.dumps({"model_name": model_name, "version": version}, ensure_ascii=False),
            encoding="utf-8",
        )

    def load_active(self) -> tuple[object, dict] | None:
        """加载活跃模型；指针缺失或失效时回退 random_forest 最新版（M2-5 兼容）。"""
        pointer = self.get_active()
        if pointer is not None:
            loaded = self.load(pointer["model_name"], pointer["version"])
            if loaded is not None:
                return loaded
        return self.load_latest("random_forest")


def _evaluate(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    mae = float(np.mean(np.abs(y_true - y_pred)))
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    mape = _mape(y_true, y_pred)
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return {"mae": round(mae, 2), "rmse": round(rmse, 2), "mape": round(mape, 2), "r2": round(r2, 4)}


def _mape(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    nonzero = y_true != 0
    return float(np.mean(np.abs((y_true[nonzero] - y_pred[nonzero]) / y_true[nonzero])) * 100)


def _baseline_metrics(frame_val: pd.DataFrame, n_lags: int) -> dict:
    """naive 基线（同一验证集）：last_value=lag_1、seasonal=lag_12（窗口不足时 None）。

    基线只作评估参照，不落盘为模型；模型 MAPE 应与其直接对比（beats_baseline）。
    """
    y_val = frame_val["y"].to_numpy()

    def entry(y_hat: np.ndarray) -> dict:
        return {
            "mae": round(float(np.mean(np.abs(y_val - y_hat))), 2),
            "mape": round(_mape(y_val, y_hat), 2),
        }

    return {
        "last_value": entry(frame_val["lag_1"].to_numpy()),
        "seasonal": entry(frame_val["lag_12"].to_numpy()) if n_lags >= 12 else None,
    }


def _per_region_metrics(frame_val: pd.DataFrame, y_pred: np.ndarray) -> dict:
    """验证集按区域分组 MAPE：区域数、中位数、最差 WORST_REGIONS_LIMIT 个。"""
    enc_to_type = {v: k for k, v in REGION_TYPE_ENC.items()}
    df = frame_val[["region_type_enc", "region_id", "y"]].copy()
    df["y_pred"] = y_pred
    groups = [
        {
            "region_type": enc_to_type.get(int(type_enc), "unknown"),
            "region_id": int(region_id),
            "mape": round(_mape(g["y"].to_numpy(), g["y_pred"].to_numpy()), 2),
            "samples": int(len(g)),
        }
        for (type_enc, region_id), g in df.groupby(["region_type_enc", "region_id"])
    ]
    return {
        "regions": len(groups),
        "median_mape": round(float(np.median([g["mape"] for g in groups])), 2),
        "worst": sorted(groups, key=lambda g: -g["mape"])[:WORST_REGIONS_LIMIT],
    }


def _stratified_metrics(
    frame_val: pd.DataFrame, y_pred: np.ndarray
) -> tuple[dict | None, dict]:
    """按 is_annual_interp 分层：真实月度层指标 + 两层样本数。

    年度插值样本被线性平滑、指标必然偏乐观；真实月度层是更诚实的口径。
    验证集无真实月度样本时指标为 None。
    """
    real_mask = frame_val["is_annual_interp"].to_numpy() == 0
    strata = {
        "real_monthly": int(real_mask.sum()),
        "annual_interp": int(len(real_mask) - real_mask.sum()),
    }
    if not real_mask.any():
        return None, strata
    return _evaluate(frame_val["y"].to_numpy()[real_mask], y_pred[real_mask]), strata


def _grid_search_cv(
    estimator_cls,
    grid: dict[str, tuple],
    x_train: np.ndarray,
    y_train: np.ndarray,
    w_train: np.ndarray | None = None,
    fixed_params: dict | None = None,
) -> tuple[dict, dict]:
    """小网格 × TimeSeriesSplit 选参骨架（RF/XGB 共用），sample_weight 折内切片。

    返回 (最优参数含 random_state, cv_info)；cv_info.best_params 只含网格键。
    """
    splitter = TimeSeriesSplit(n_splits=CV_FOLDS)
    best = None
    for combo in product(*grid.values()):
        candidate = dict(fixed_params or {})
        candidate.update(zip(grid.keys(), combo))
        candidate["random_state"] = 42
        fold_mapes = []
        for train_idx, val_idx in splitter.split(x_train):
            m = estimator_cls(**candidate)
            m.fit(
                x_train[train_idx],
                y_train[train_idx],
                sample_weight=None if w_train is None else w_train[train_idx],
            )
            fold_mapes.append(_mape(y_train[val_idx], m.predict(x_train[val_idx])))
        mean_mape = float(np.mean(fold_mapes))
        if best is None or mean_mape < best[0]:
            best = (mean_mape, candidate, fold_mapes)
    params = best[1]
    cv_info = {
        "folds": CV_FOLDS,
        "best_params": {k: params[k] for k in grid},
        "fold_mapes": [round(m, 2) for m in best[2]],
        "mean_mape": round(best[0], 2),
    }
    return params, cv_info


def _fit_random_forest(
    x_train: np.ndarray, y_train: np.ndarray, w_train: np.ndarray | None = None
):
    """小网格 × 时序 CV 选参；样本不足时用默认参数（cv=None）。"""
    params = dict(RF_PARAMS)
    cv_info = None
    if len(x_train) >= MIN_CV_SAMPLES:
        params, cv_info = _grid_search_cv(
            RandomForestRegressor, RF_GRID, x_train, y_train, w_train, RF_FIXED_PARAMS
        )
    model = RandomForestRegressor(**params)
    model.fit(x_train, y_train, sample_weight=w_train)
    return model, cv_info


def _fit_xgboost(
    x_train: np.ndarray, y_train: np.ndarray, w_train: np.ndarray | None = None
):
    """小网格 × 时序 CV 选参；样本不足时用默认参数（cv=None）。"""
    params = dict(XGB_DEFAULT_PARAMS)
    cv_info = None
    if len(x_train) >= MIN_CV_SAMPLES:
        params, cv_info = _grid_search_cv(XGBRegressor, XGB_GRID, x_train, y_train, w_train)
    model = XGBRegressor(**params)
    model.fit(x_train, y_train, sample_weight=w_train)
    return model, cv_info


ALGORITHMS = {
    "random_forest": _fit_random_forest,
    "xgboost": _fit_xgboost,
}


def train_model(
    algorithm: str,
    series_list: list[RegionSeries],
    store: ModelStore,
    n_lags: int | None = None,
    city_codes: list[str] | None = None,
    dataset_meta: dict | None = None,
) -> dict:
    """训练指定算法并版本化保存，返回 meta。

    n_lags 未指定时按 12→6→3 自适应选择首个样本数 ≥ MIN_SAMPLES 的窗口。
    数据不足以构成任何窗口时抛 ValueError。
    dataset_meta（多源构建器指纹）原样并入模型 meta["dataset"] 供追溯。
    """
    if algorithm not in ALGORITHMS:
        raise ValueError(f"未知模型算法: {algorithm}")

    candidates = (n_lags,) if n_lags else LAG_CANDIDATES
    frame = None
    chosen_lags = None
    for candidate in candidates:
        frame = build_training_frame(series_list, candidate)
        if len(frame) >= MIN_SAMPLES:
            chosen_lags = candidate
            break
    if chosen_lags is None:
        if n_lags or frame is None or frame.empty:
            raise ValueError(f"训练样本不足（最少需要 {MIN_SAMPLES} 条）")
        chosen_lags = candidates[-1]  # 全部窗口都不足时用最小窗口尽量训练
        frame = build_training_frame(series_list, chosen_lags)
        if len(frame) < 2:
            raise ValueError(f"训练样本不足（最少需要 {MIN_SAMPLES} 条）")

    cols = feature_columns(chosen_lags)
    x = frame[cols].to_numpy()
    y = frame["y"].to_numpy()
    w = (
        frame["weight"].to_numpy(dtype=float)
        if "weight" in frame.columns
        else np.ones(len(frame))
    )

    # 时序切分：后 20% 验证（已按 year_month 排序）
    split = max(int(len(frame) * 0.8), 1)
    if split >= len(frame):
        split = len(frame) - 1
    x_train, x_val = x[:split], x[split:]
    y_train, y_val = y[:split], y[split:]

    model, cv_info = ALGORITHMS[algorithm](x_train, y_train, w[:split])
    y_pred = model.predict(x_val)
    metrics = _evaluate(y_val, y_pred)

    # 同一验证集上的评估扩展：naive 基线、分区域、按插值分层（R1/R3/R6）
    frame_val = frame.iloc[split:]
    baselines = _baseline_metrics(frame_val, chosen_lags)
    metrics_real_monthly, validation_strata = _stratified_metrics(frame_val, y_pred)

    version = store.next_version(algorithm)
    meta = {
        "model_name": algorithm,
        "version": version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_lags": chosen_lags,
        "features": cols,
        "metrics": metrics,
        "metrics_real_monthly": metrics_real_monthly,
        "validation_strata": validation_strata,
        "baselines": baselines,
        "beats_baseline": bool(metrics["mape"] < baselines["last_value"]["mape"]),
        "per_region_metrics": _per_region_metrics(frame_val, y_pred),
        "training_samples": int(len(frame)),
        "validation_samples": int(len(x_val)),
        "city_codes": city_codes or [],
        "ci_strategy": "per_tree" if algorithm == "random_forest" else "residual",
        "resid_std": round(float(np.std(y_val - y_pred)), 2),
        "cv": cv_info,
        "dataset": dataset_meta,
    }
    store.save(algorithm, version, model, meta)
    return meta


def train_random_forest(
    series_list: list[RegionSeries],
    store: ModelStore,
    n_lags: int | None = None,
    city_codes: list[str] | None = None,
    dataset_meta: dict | None = None,
) -> dict:
    return train_model("random_forest", series_list, store, n_lags, city_codes, dataset_meta)
