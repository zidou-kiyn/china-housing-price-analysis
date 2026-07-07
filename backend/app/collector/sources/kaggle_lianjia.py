"""Kaggle 公开数据集采集源：北京链家历史成交（ruiqurm/lianjia）。

定位：**历史回填 + 交叉校验**，非实时源。数据是 2011–2017 北京二手房**成交**明细，
按月聚合为城市级成交均价（元/㎡），复用现有 pipeline 落入 price_snapshot（source 标记）。

与 creprice 的语义差异：creprice 是挂牌/供给价，本源是成交价；写入 supply_price 以便在
前端主均价线连续展示，来源差异由 price_snapshot.source 溯源。许可：数据集 CC BY-NC-SA 4.0
（非商业），仅用于本系统分析展示。

网络：Kaggle 公开数据集无需登录即可下载（302 → 签名 GCS 直链），全球可达，默认直连
（不走采集代理，因所给美国代理对多数站点更差）。下载后本地缓存，重复采集不重复下载。
"""

from __future__ import annotations

import csv
import io
import logging
import zipfile
from datetime import datetime
from pathlib import Path

import requests

from app.collector.base import (
    BaseSource,
    CityInfo,
    DataType,
    RawRecord,
    SourceRegistry,
)
from app.collector.storage import DEFAULT_DATA_ROOT

logger = logging.getLogger(__name__)

# 数据集标识与下载地址（Kaggle 公开数据集直链，无需 token）
_DATASET = "ruiqurm/lianjia"
_DOWNLOAD_URL = f"https://www.kaggle.com/api/v1/datasets/download/{_DATASET}"
_CSV_NAME = "new.csv"

# 该数据集仅覆盖北京；城市 code 对齐库内既有 'bj'，使快照落到同一城市。
_CITY_CODE = "bj"
_CITY_NAME = "北京"
_CITY_PROVINCE = "北京"

# 过滤：单价合理区间 + 每月最小成交样本数（滤除早期 1~2 笔的噪声月份）
_PRICE_MIN = 1000
_PRICE_MAX = 200000
_MIN_SAMPLES_PER_MONTH = 30

_DOWNLOAD_TIMEOUT = 120.0


class KaggleLianjiaSource(BaseSource):
    source_name = "kaggle_lianjia"
    base_url = "https://www.kaggle.com/datasets/ruiqurm/lianjia"
    # 城市级历史时序，无区县 / 无价格分布
    capabilities = frozenset({DataType.CITIES, DataType.PRICE_TIMELINE})
    price_unit = "cny_per_sqm"

    def __init__(self, cache_dir: Path | str | None = None) -> None:
        root = Path(cache_dir) if cache_dir is not None else DEFAULT_DATA_ROOT / "kaggle"
        self.cache_dir = root / "ruiqurm_lianjia"
        # 解析结果按实例缓存，避免同一采集任务内重复读 58MB CSV
        self._timeline: list[dict] | None = None

    # -- 城市列表 ----------------------------------------------------------------

    def fetch_cities(self) -> list[CityInfo]:
        return [CityInfo(name=_CITY_NAME, code=_CITY_CODE, province=_CITY_PROVINCE)]

    # -- 均价时序 ----------------------------------------------------------------

    def fetch_price_timeline(self, city_code: str, district_code: str = "allsq1") -> RawRecord:
        if city_code != _CITY_CODE:
            raise ValueError(
                f"kaggle_lianjia 仅覆盖北京(bj)，不支持城市 {city_code}"
            )
        records = self._city_timeline()
        return RawRecord(
            source=self.source_name,
            city_code=city_code,
            data_type="price_timeline",
            records=records,
            fetched_at=datetime.now().isoformat(),
            raw_url=_DOWNLOAD_URL,
        )

    # -- 数据集下载与聚合 --------------------------------------------------------

    def _csv_path(self) -> Path:
        """确保数据集已下载解压，返回 CSV 路径（已缓存则直接复用）。"""
        csv_path = self.cache_dir / _CSV_NAME
        if csv_path.exists() and csv_path.stat().st_size > 0:
            return csv_path
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        logger.info("下载 Kaggle 数据集 %s ...", _DATASET)
        resp = requests.get(_DOWNLOAD_URL, timeout=_DOWNLOAD_TIMEOUT, stream=True)
        resp.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(resp.content)) as zf:
            name = next((n for n in zf.namelist() if n.endswith(".csv")), None)
            if name is None:
                raise ValueError(f"{_DATASET} 压缩包内未找到 CSV")
            with zf.open(name) as src, open(csv_path, "wb") as dst:
                dst.write(src.read())
        logger.info("数据集已缓存: %s", csv_path)
        return csv_path

    def _city_timeline(self) -> list[dict]:
        """解析成交明细并按月聚合为城市级成交均价记录。"""
        if self._timeline is not None:
            return self._timeline
        self._timeline = self._aggregate(self._csv_path())
        return self._timeline

    @staticmethod
    def _aggregate(csv_path: Path) -> list[dict]:
        """按 tradeTime 的 YYYY-MM 分组，输出 supply_price=均价、sample_count=成交笔数。"""
        totals: dict[str, list] = {}  # ym -> [count, sum_price]
        # 数据集含中文列（floor 的 高/中/低）以 GBK 编码；目标列均为 ASCII，用 latin-1 容错读取。
        with open(csv_path, encoding="latin-1", newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                trade_time = (row.get("tradeTime") or "").strip()
                price_str = (row.get("price") or "").strip()
                if len(trade_time) < 7 or not price_str:
                    continue
                try:
                    price = float(price_str)
                except ValueError:
                    continue
                if price < _PRICE_MIN or price > _PRICE_MAX:
                    continue
                ym = trade_time[:7]
                slot = totals.setdefault(ym, [0, 0.0])
                slot[0] += 1
                slot[1] += price

        records: list[dict] = []
        for ym in sorted(totals):
            count, total = totals[ym]
            if count < _MIN_SAMPLES_PER_MONTH:
                continue
            records.append(
                {
                    "year_month": ym,
                    "supply_price": round(total / count),
                    "attention_price": None,
                    "value_price": None,
                    "sample_count": count,
                }
            )
        return records


SourceRegistry.register(KaggleLianjiaSource.source_name, KaggleLianjiaSource)
