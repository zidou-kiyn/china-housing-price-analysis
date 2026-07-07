"""原始采集数据落地：写入 data/raw/{source}/{city}/{date}_{data_type}.json。"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

# 仓库根目录下的 data/ 目录：storage.py 位于 backend/app/collector/ 下，向上 3 级到仓库根。
DEFAULT_DATA_ROOT = Path(__file__).resolve().parents[3] / "data"


def save_raw(
    source: str,
    city_code: str,
    data: dict | list,
    data_type: str,
    base_dir: Path | str | None = None,
    district_code: str | None = None,
) -> str:
    """将一次采集的数据以 JSON 落盘，返回文件绝对路径。目录不存在时自动创建。"""
    root = Path(base_dir) if base_dir is not None else DEFAULT_DATA_ROOT
    date_str = datetime.now().strftime("%Y-%m-%d")
    target_dir = root / "raw" / source / city_code
    target_dir.mkdir(parents=True, exist_ok=True)

    suffix = f"_{district_code}" if district_code else ""
    file_path = target_dir / f"{date_str}_{data_type}{suffix}.json"
    file_path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return str(file_path)
