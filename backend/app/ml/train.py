"""模型训练、评估与版本化：RF + XGBoost（docs/06 §4~6、M3-1）。"""

import json
import os
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

    def _align_owner(self, *paths: Path) -> None:
        """写出文件属主对齐 base_dir 属主（治理 R5）。

        容器内以 root 训练时，宿主挂载目录下会产生 root 属主文件，宿主侧无法管理；
        写完后 chown 到挂载目录属主即可。非 root 运行或属主已一致时为空操作，
        失败静默（不影响训练主流程）。
        """
        try:
            stat = self.base_dir.stat()
        except OSError:
            return
        for path in paths:
            try:
                if path.stat().st_uid != stat.st_uid:
                    os.chown(path, stat.st_uid, stat.st_gid)
                path.chmod(0o775 if path.is_dir() else 0o664)
            except OSError:
                continue

    def save(self, model_name: str, version: str, model, meta: dict) -> Path:
        model_dir = self._model_dir(model_name)
        model_dir.mkdir(parents=True, exist_ok=True)
        path = model_dir / f"{version}.pkl"
        joblib.dump(model, path)
        meta_path = model_dir / f"{version}_meta.json"
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self._align_owner(model_dir, path, meta_path)
        return path

    def delete(self, model_name: str, version: str) -> None:
        """删除指定版本（pkl + meta 两个文件）；活跃版本拒绝删除（ValueError）。"""
        model_dir = self._model_dir(model_name)
        pkl = model_dir / f"{version}.pkl"
        meta_path = model_dir / f"{version}_meta.json"
        # 路径穿越防护（破坏性操作，纵深防御，API 层另有 pattern 校验）：
        # 解析后必须恰好位于 base_dir/<model_name>/ 一层内，".." 等一律拒绝
        base = self.base_dir.resolve()
        for target in (pkl, meta_path):
            if target.resolve().parent.parent != base:
                raise ValueError(f"非法模型版本路径: {model_name}/{version}")
        active = self.get_active()
        if (
            active is not None
            and active["model_name"] == model_name
            and active["version"] == version
        ):
            raise ValueError(f"活跃版本不可删除: {model_name}/{version}")
        if not pkl.exists() and not meta_path.exists():
            raise FileNotFoundError(f"模型版本不存在: {model_name}/{version}")
        pkl.unlink(missing_ok=True)
        meta_path.unlink(missing_ok=True)

    def cleanup(self, keep_last: int = 3) -> list[dict]:
        """每个模型保留最近 keep_last 个版本 + 活跃版本，删除其余，返回删除清单。"""
        active = self.get_active()
        deleted: list[dict] = []
        if not self.base_dir.exists():
            return deleted
        for model_dir in sorted(p for p in self.base_dir.iterdir() if p.is_dir()):
            model_name = model_dir.name
            versions = self.versions(model_name)
            keep = set(versions[-keep_last:]) if keep_last > 0 else set()
            if active is not None and active["model_name"] == model_name:
                keep.add(active["version"])
            for version in versions:
                if version not in keep:
                    self.delete(model_name, version)
                    deleted.append({"model_name": model_name, "version": version})
        return deleted

    def best_versions(self) -> dict[str, str]:
        """每个模型「诚实口径」MAPE 最低的版本 {model_name: version}。

        年度扩充数据训练后，全量验证集被平滑插值样本主导（headline MAPE 虚低，
        如 0.25% vs 真实月度层 2.71%），评"最佳"必须优先用
        metrics_real_monthly.mape；旧 meta 无该字段（多源构建器之前的版本，
        纯月度训练时 headline 即诚实口径）回退 metrics.mape。两项都缺则忽略。
        """
        best: dict[str, tuple[float, str]] = {}
        for meta in self.list_all():
            mape = (meta.get("metrics_real_monthly") or {}).get("mape")
            if mape is None:
                mape = (meta.get("metrics") or {}).get("mape")
            if mape is None:
                continue
            name = meta["model_name"]
            if name not in best or mape < best[name][0]:
                best[name] = (mape, meta["version"])
        return {name: version for name, (_, version) in best.items()}

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
        self._align_owner(self._active_path())

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

MIN_ES_SAMPLES = 6


def _train_exp_smoothing(
    series_list: list[RegionSeries],
    store: ModelStore,
    dataset_meta: dict | None = None,
) -> dict:
    """为每个区域独立拟合 ExponentialSmoothing，打包为 dict 存储。"""
    from statsmodels.tsa.holtwinters import ExponentialSmoothing as HoltWinters

    models: dict[tuple[str, int], object] = {}
    skipped: list[tuple[str, int]] = []
    eval_mae, eval_mape_vals = [], []
    worst_regions: list[dict] = []

    for rs in series_list:
        key = (rs.region_type, rs.region_id)
        if len(rs.prices) < MIN_ES_SAMPLES:
            skipped.append(key)
            continue

        prices = np.array(rs.prices, dtype=float)
        split = max(int(len(prices) * 0.8), 2)
        train_p, val_p = prices[:split], prices[split:]

        try:
            fitted = HoltWinters(
                train_p, trend="add", seasonal=None,
                initialization_method="estimated",
            ).fit(optimized=True)
        except Exception:
            skipped.append(key)
            continue

        models[key] = fitted

        if len(val_p) > 0:
            forecast = fitted.forecast(len(val_p))
            forecast = np.array(forecast, dtype=float)
            mae = float(np.mean(np.abs(val_p - forecast)))
            nonzero = val_p != 0
            mape = float(np.mean(np.abs((val_p[nonzero] - forecast[nonzero]) / val_p[nonzero])) * 100) if nonzero.any() else 0.0
            eval_mae.append(mae)
            eval_mape_vals.append(mape)
            worst_regions.append({
                "region_type": rs.region_type,
                "region_id": rs.region_id,
                "mape": round(mape, 2),
                "samples": len(rs.prices),
            })

    if not models:
        raise ValueError("没有足够数据的区域可供训练 ExponentialSmoothing")

    global_mae = round(float(np.mean(eval_mae)), 2) if eval_mae else 0.0
    global_mape = round(float(np.mean(eval_mape_vals)), 2) if eval_mape_vals else 0.0

    resid_std_pcts = []
    for rs in series_list:
        key = (rs.region_type, rs.region_id)
        if key not in models:
            continue
        fitted = models[key]
        fv = np.array(fitted.fittedvalues, dtype=float)
        tp = np.array(rs.prices[:len(fv)], dtype=float)
        nonzero = tp != 0
        if nonzero.any():
            resid_std_pcts.append(float(np.std((tp[nonzero] - fv[nonzero]) / tp[nonzero])))

    avg_resid_std_pct = round(float(np.mean(resid_std_pcts)), 4) if resid_std_pcts else None

    worst_regions.sort(key=lambda r: -r["mape"])

    version = store.next_version("exp_smoothing")
    meta = {
        "model_name": "exp_smoothing",
        "version": version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_lags": 0,
        "features": [],
        "metrics": {
            "mae": global_mae,
            "rmse": 0.0,
            "mape": global_mape,
            "r2": 0.0,
        },
        "training_samples": sum(len(rs.prices) for rs in series_list if (rs.region_type, rs.region_id) in models),
        "validation_samples": sum(max(len(rs.prices) - max(int(len(rs.prices) * 0.8), 2), 0) for rs in series_list if (rs.region_type, rs.region_id) in models),
        "ci_strategy": "residual",
        "resid_std": 0.0,
        "resid_std_pct": avg_resid_std_pct,
        "per_region_metrics": {
            "regions": len(models),
            "skipped": len(skipped),
            "median_mape": round(float(np.median(eval_mape_vals)), 2) if eval_mape_vals else 0.0,
            "worst": worst_regions[:WORST_REGIONS_LIMIT],
        },
        "dataset": dataset_meta,
    }
    store.save("exp_smoothing", version, models, meta)
    return meta


def train_model(
    algorithm: str,
    series_list: list[RegionSeries],
    store: ModelStore,
    n_lags: int | None = None,
    dataset_meta: dict | None = None,
) -> dict:
    """训练指定算法并版本化保存，返回 meta。

    n_lags 未指定时按 12→6→3 自适应选择首个样本数 ≥ MIN_SAMPLES 的窗口。
    数据不足以构成任何窗口时抛 ValueError。
    dataset_meta（多源构建器指纹）原样并入模型 meta["dataset"] 供追溯。
    """
    if algorithm == "exp_smoothing":
        return _train_exp_smoothing(series_list, store, dataset_meta)

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

    # 相对残差（residual 策略的置信区间随价位缩放）：与 _mape 同口径屏蔽零价样本，
    # 防止脏数据把 nan/inf 写进 meta 导致预测端 round() 崩溃；全零时置 None（预测
    # 端退回绝对 resid_std 算式）
    nonzero = y_val != 0
    resid_std_pct = (
        round(float(np.std((y_val[nonzero] - y_pred[nonzero]) / y_val[nonzero])), 4)
        if nonzero.any()
        else None
    )

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
        "ci_strategy": "per_tree" if algorithm == "random_forest" else "residual",
        "resid_std": round(float(np.std(y_val - y_pred)), 2),
        "resid_std_pct": resid_std_pct,
        "cv": cv_info,
        "dataset": dataset_meta,
    }
    store.save(algorithm, version, model, meta)
    return meta


def train_random_forest(
    series_list: list[RegionSeries],
    store: ModelStore,
    n_lags: int | None = None,
    dataset_meta: dict | None = None,
) -> dict:
    return train_model("random_forest", series_list, store, n_lags, dataset_meta)
