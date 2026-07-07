"""creprice 网络集成冒烟测试：实际抓取一个城市，验证结构与合理性。

默认被 -m "not slow" 排除。运行：`uv run pytest tests/collector/test_creprice_live.py -v -m slow`。
连接失败（网络/DNS/TLS）时跳过而非硬失败，但结构断言失败会正常暴露。
"""

from __future__ import annotations

import re

import pytest
import requests

from app.collector.sources.creprice import CrepriceSource

pytestmark = pytest.mark.slow

_YEAR_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


@pytest.fixture(scope="module")
def source() -> CrepriceSource:
    return CrepriceSource()


def test_live_price_timeline(source: CrepriceSource):
    try:
        record = source.fetch_price_timeline("qz")
    except requests.RequestException as exc:
        pytest.skip(f"creprice 不可达，跳过冒烟测试: {exc}")

    assert record.source == "creprice"
    assert record.city_code == "qz"
    assert record.data_type == "price_timeline"
    assert "chartsdatanew" in record.raw_url
    assert record.records, "均价时序不应为空"

    for row in record.records:
        assert set(row) == {
            "year_month",
            "supply_price",
            "attention_price",
            "value_price",
            "sample_count",
        }
        assert _YEAR_MONTH_RE.match(row["year_month"]), row["year_month"]

    prices = [r["supply_price"] for r in record.records if r["supply_price"] is not None]
    assert prices, "至少应有一个月份含均价"
    # 泉州二手房均价应在合理区间（元/㎡）
    assert all(1000 < p < 200000 for p in prices), prices


def test_live_fetch_cities(source: CrepriceSource):
    try:
        cities = source.fetch_cities()
    except requests.RequestException as exc:
        pytest.skip(f"creprice 不可达，跳过冒烟测试: {exc}")

    codes = [c.code for c in cities]
    assert len(codes) == len(set(codes)), "城市列表应已去重"
    assert len(cities) > 100, "全国城市数应较多"
    assert "qz" in set(codes)
