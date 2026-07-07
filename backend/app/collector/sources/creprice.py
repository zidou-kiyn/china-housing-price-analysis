"""creprice.cn 采集适配器。

核心：均价与价格分布均来自同源 JSON API（非 HTML 表格），仅城市列表页 `/rank/citySel.html`
需要 HTML 解析。缺失数据在 JSON 中表现为 key 不存在（非 null / "--"），一律用 .get() 处理。
"""

from __future__ import annotations

import re
from datetime import datetime

from app.collector.base import (
    BaseSource,
    CityInfo,
    DistrictInfo,
    RawRecord,
    SourceRegistry,
)
from app.collector.http_client import CrawlerHttpClient

# 城市列表页每个城市/区县链接均在静态 HTML 中，用正则直接提取。
_CITY_RE = re.compile(r'<a class="city[^"]*"[^>]*href="/city/([^"]+)\.html">([^<]+)</a>')
_DIST_RE = re.compile(
    r'<a class="dist"[^>]*href="/district/([^"]+)\.html\?city=([^"]+)">([^<]+)</a>'
)

# 均价时序 JSON 的三条 series 名称。
_SERIES_SUPPLY = "供给"
_SERIES_ATTENTION = "关注"
_SERIES_VALUE = "价值"


def _normalize_month(month: str) -> str:
    """将 "2025-7" 归一化为 "2025-07"（对齐 PriceSnapshot.year_month 的 YYYY-MM 格式）。"""
    year, _, mon = month.partition("-")
    return f"{int(year):04d}-{int(mon):02d}"


class CrepriceSource(BaseSource):
    source_name = "creprice"
    BASE_URL = "https://creprice.cn"

    def __init__(self, http_client: CrawlerHttpClient | None = None) -> None:
        self.http = http_client or CrawlerHttpClient()

    # -- 城市 / 区县列表（唯一需要 HTML 解析的页面） --------------------------------

    def fetch_cities(self) -> list[CityInfo]:
        response = self.http.get(f"{self.BASE_URL}/rank/citySel.html")
        return self._parse_cities(response.text)

    def fetch_districts(self) -> list[DistrictInfo]:
        response = self.http.get(f"{self.BASE_URL}/rank/citySel.html")
        return self._parse_districts(response.text)

    @staticmethod
    def _parse_cities(html: str) -> list[CityInfo]:
        """提取城市并按 code 去重（每个城市在两个视图块中各出现一次）。"""
        seen: dict[str, CityInfo] = {}
        for code, name in _CITY_RE.findall(html):
            if code not in seen:
                seen[code] = CityInfo(name=name.strip(), code=code)
        return list(seen.values())

    @staticmethod
    def _parse_districts(html: str) -> list[DistrictInfo]:
        """提取区县并按 (city_code, dist_code) 联合键去重（dist code 跨城市复用）。"""
        seen: dict[tuple[str, str], DistrictInfo] = {}
        for dist_code, city_code, name in _DIST_RE.findall(html):
            key = (city_code, dist_code)
            if key not in seen:
                seen[key] = DistrictInfo(name=name.strip(), code=dist_code, city_code=city_code)
        return list(seen.values())

    # -- 均价时序 ----------------------------------------------------------------

    def fetch_price_timeline(self, city_code: str, district_code: str = "allsq1") -> RawRecord:
        params = {
            "city": city_code,
            "district": district_code,
            "proptype": "11",
            "flag": "1",
            "type": "forsale",
            "based": "price",
            "dtype": "line",
            "sinceyear": "1",
            "timeType": "month",
        }
        response = self.http.get(f"{self.BASE_URL}/market/chartsdatanew.html", params=params)
        records = self._parse_price_timeline(response.json())
        return RawRecord(
            source=self.source_name,
            city_code=city_code,
            data_type="price_timeline",
            records=records,
            fetched_at=datetime.now().isoformat(),
            raw_url=response.url,
        )

    @staticmethod
    def _parse_price_timeline(json_data: dict) -> list[dict]:
        """合并三条 series，按月对齐输出。

        供给 series: value=均价, count=样本套数；关注 series: data=关注价；价值 series: data=价值价。
        缺失月份的 key 不存在，用 .get() 返回 None。
        """
        series_by_name = {
            series.get("chartsName"): series.get("rows", [])
            for series in json_data.get("data", [])
        }
        supply_rows = series_by_name.get(_SERIES_SUPPLY, [])
        attention_rows = series_by_name.get(_SERIES_ATTENTION, [])
        value_rows = series_by_name.get(_SERIES_VALUE, [])

        merged: dict[str, dict] = {}

        def _slot(month: str) -> dict:
            if month not in merged:
                merged[month] = {
                    "year_month": _normalize_month(month),
                    "supply_price": None,
                    "attention_price": None,
                    "value_price": None,
                    "sample_count": None,
                }
            return merged[month]

        for row in supply_rows:
            month = row.get("month")
            if month is None:
                continue
            slot = _slot(month)
            slot["supply_price"] = row.get("value")
            slot["sample_count"] = row.get("count")

        for row in attention_rows:
            month = row.get("month")
            if month is None:
                continue
            _slot(month)["attention_price"] = row.get("data")

        for row in value_rows:
            month = row.get("month")
            if month is None:
                continue
            _slot(month)["value_price"] = row.get("data")

        return [merged[m] for m in sorted(merged, key=_normalize_month)]

    # -- 价格分布 ----------------------------------------------------------------

    def fetch_price_distribution(
        self, city_code: str, district_code: str = "allsq1"
    ) -> RawRecord:
        params = {
            "city": city_code,
            "district": district_code,
            "proptype": "11",
            "flag": "1",
            "type": "forsale",
            "based": "price",
            "dtype": "bar",
        }
        response = self.http.get(f"{self.BASE_URL}/market/chartsdatanew.html", params=params)
        records = self._parse_price_distribution(response.json())
        return RawRecord(
            source=self.source_name,
            city_code=city_code,
            data_type="price_distribution",
            records=records,
            fetched_at=datetime.now().isoformat(),
            raw_url=response.url,
        )

    @staticmethod
    def _parse_price_distribution(json_data: dict) -> list[dict]:
        """解析价格区间分布：section "6000-7000" → low/high，data 为占比(%)。"""
        series_list = json_data.get("data", [])
        supply_series = next(
            (s for s in series_list if s.get("chartsName") == _SERIES_SUPPLY),
            series_list[0] if series_list else {},
        )

        records: list[dict] = []
        for row in supply_series.get("rows", []):
            section = row.get("section")
            if not section:
                continue
            low_str, _, high_str = section.partition("-")
            records.append(
                {
                    "price_range_low": int(low_str),
                    "price_range_high": int(high_str),
                    "percentage": row.get("data"),
                }
            )
        return records


SourceRegistry.register(CrepriceSource.source_name, CrepriceSource)
