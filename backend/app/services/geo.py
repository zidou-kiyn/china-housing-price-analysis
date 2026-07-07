"""GeoJSON 存储与读取（Part 3 扩展下载能力，本模块先提供目录与存在性查询）。"""

from __future__ import annotations

from pathlib import Path

from app.collector.storage import DEFAULT_DATA_ROOT
from app.core.config import settings


def geo_root() -> Path:
    """GeoJSON 落盘目录：默认仓库根 data/geo/（容器内 /data/geo），可经配置覆盖。"""
    root = Path(settings.geo_dir) if settings.geo_dir else DEFAULT_DATA_ROOT / "geo"
    root.mkdir(parents=True, exist_ok=True)
    return root


def geo_path(city_code: str) -> Path:
    return geo_root() / f"{city_code}.json"


def list_available() -> set[str]:
    """扫描 geo 目录，返回已有地图的城市 code 集合。"""
    return {p.stem for p in geo_root().glob("*.json")}
