"""RandomForest 训练、评估与模型版本化（docs/06 §4~6、§8）。"""

import json
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import RandomForestRegressor

from app.ml.features import RegionSeries, build_training_frame, feature_columns

LAG_CANDIDATES = (12, 6, 3)
MIN_SAMPLES = 20
RF_PARAMS = {
    "n_estimators": 100,
    "max_depth": 10,
    "min_samples_split": 5,
    "random_state": 42,
}


class ModelStore:
    """models/{model_name}/v{x}.pkl + v{x}_meta.json 的读写与版本管理。"""

    def __init__(self, base_dir: str | Path) -> None:
        self.base_dir = Path(base_dir)

    def _model_dir(self, model_name: str) -> Path:
        return self.base_dir / model_name

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

    def load_latest(self, model_name: str) -> tuple[object, dict] | None:
        versions = self.versions(model_name)
        if not versions:
            return None
        version = versions[-1]
        model_dir = self._model_dir(model_name)
        model = joblib.load(model_dir / f"{version}.pkl")
        meta = json.loads((model_dir / f"{version}_meta.json").read_text(encoding="utf-8"))
        return model, meta


def _evaluate(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    mae = float(np.mean(np.abs(y_true - y_pred)))
    rmse = float(np.sqrt(np.mean((y_true - y_pred) ** 2)))
    nonzero = y_true != 0
    mape = float(np.mean(np.abs((y_true[nonzero] - y_pred[nonzero]) / y_true[nonzero])) * 100)
    ss_res = float(np.sum((y_true - y_pred) ** 2))
    ss_tot = float(np.sum((y_true - np.mean(y_true)) ** 2))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return {"mae": round(mae, 2), "rmse": round(rmse, 2), "mape": round(mape, 2), "r2": round(r2, 4)}


def train_random_forest(
    series_list: list[RegionSeries],
    store: ModelStore,
    n_lags: int | None = None,
    city_codes: list[str] | None = None,
) -> dict:
    """训练 RF 并版本化保存，返回 meta。

    n_lags 未指定时按 12→6→3 自适应选择首个样本数 ≥ MIN_SAMPLES 的窗口。
    数据不足以构成任何窗口时抛 ValueError。
    """
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

    # 时序切分：后 20% 验证（已按 year_month 排序）
    split = max(int(len(frame) * 0.8), 1)
    if split >= len(frame):
        split = len(frame) - 1
    x_train, x_val = x[:split], x[split:]
    y_train, y_val = y[:split], y[split:]

    model = RandomForestRegressor(**RF_PARAMS)
    model.fit(x_train, y_train)
    metrics = _evaluate(y_val, model.predict(x_val))

    model_name = "random_forest"
    version = store.next_version(model_name)
    meta = {
        "model_name": model_name,
        "version": version,
        "trained_at": datetime.now(timezone.utc).isoformat(),
        "n_lags": chosen_lags,
        "features": cols,
        "metrics": metrics,
        "training_samples": int(len(frame)),
        "validation_samples": int(len(x_val)),
        "city_codes": city_codes or [],
    }
    store.save(model_name, version, model, meta)
    return meta
