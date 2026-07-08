"""58/anjuke 全国城市年度房价数据集：下载 + 解析（GitHub raw，免登录直下）。

定位：**历史回填（广度）**，非实时源。数据来自 GitHub 仓库
changao1/70-China-cities-housing-index-data-by-national-bureau-of-statistics
的 supplementary/ 目录（MIT 许可），为 58.com / anjuke 各城市**年度二手房挂牌均价**（¥/㎡）：

- 58:     365 城 / 32 省，2010–2024
- anjuke: 349 城，2015–2024（交叉校验/补缺用）

口径注意：年度 + 挂牌价（非月度成交），挂牌略高于成交；落库用 source 列区隔并由前端标注。
数据集按城市**名**组织（无 creprice code），与按-code 的 PipelineRunner 阻抗不匹配，
故不注册为 BaseSource，由 services/nationwide_import.py 做 name→city_id 匹配后批量导入。

网络：GitHub raw 全球可达，requests 直连（不走采集代理）。下载后缓存 data/listing/。
"""

from __future__ import annotations

import csv
import io
import logging
from pathlib import Path

import requests

from app.collector.storage import DEFAULT_DATA_ROOT

logger = logging.getLogger(__name__)

_REPO_RAW = (
    "https://raw.githubusercontent.com/changao1/"
    "70-China-cities-housing-index-data-by-national-bureau-of-statistics/main"
)

# source_key → (下载地址, price_snapshot.source 溯源标记)
SOURCES: dict[str, tuple[str, str]] = {
    "58": (
        f"{_REPO_RAW}/supplementary/58tongcheng_city_avg_price_annual_2010-2024.csv",
        "listing_annual_58",
    ),
    "anjuke": (
        f"{_REPO_RAW}/supplementary/anjuke_city_avg_price_annual_2015-2024.csv",
        "listing_annual_anjuke",
    ),
}

# 价格合理区间（¥/㎡），区间外视为脏数据跳过
_PRICE_MIN = 500
_PRICE_MAX = 300_000

_DOWNLOAD_TIMEOUT = 60.0


def download_csv(source_key: str, cache_dir: Path | str | None = None) -> Path:
    """下载指定源的年度房价 CSV（已缓存则复用），返回本地路径。"""
    if source_key not in SOURCES:
        raise ValueError(f"未知年度房价源: {source_key}（可选: {sorted(SOURCES)}）")
    url, _ = SOURCES[source_key]
    root = Path(cache_dir) if cache_dir is not None else DEFAULT_DATA_ROOT / "listing"
    csv_path = root / url.rsplit("/", 1)[-1]
    if csv_path.exists() and csv_path.stat().st_size > 0:
        return csv_path
    root.mkdir(parents=True, exist_ok=True)
    logger.info("下载年度房价数据集 %s ...", url)
    resp = requests.get(url, timeout=_DOWNLOAD_TIMEOUT)
    resp.raise_for_status()
    csv_path.write_bytes(resp.content)
    logger.info("数据集已缓存: %s", csv_path)
    return csv_path


def parse_annual_csv(text: str) -> list[dict]:
    """解析年度房价 CSV，返回 {province, city, year:int, price:int} 记录列表。

    跳过省/市/年份/价格缺失、类型非法或价格超出合理区间的行；yoy_pct 列忽略。
    """
    records: list[dict] = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        province = (row.get("province") or "").strip()
        city = (row.get("city") or "").strip()
        year_str = (row.get("year") or "").strip()
        price_str = (row.get("price_yuan_per_sqm") or "").strip()
        if not (province and city and year_str and price_str):
            continue
        try:
            year = int(year_str)
            price = round(float(price_str))
        except ValueError:
            continue
        if not _PRICE_MIN <= price <= _PRICE_MAX:
            continue
        records.append(
            {"province": province, "city": city, "year": year, "price": price}
        )
    return records
