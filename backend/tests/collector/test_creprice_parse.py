"""creprice 解析逻辑单元测试：用真实 API 响应 / HTML 片段作为 fixture，不触网。"""

from __future__ import annotations

import json
from pathlib import Path

from app.collector.sources.creprice import CrepriceSource
from app.collector.storage import save_raw

FIXTURES = Path(__file__).parent / "fixtures"


def _load_json(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _load_text(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# -- 均价时序 --------------------------------------------------------------------


def test_parse_price_timeline_shape():
    records = CrepriceSource._parse_price_timeline(_load_json("api_price_line.json"))

    assert len(records) == 13
    expected_keys = {
        "year_month",
        "supply_price",
        "attention_price",
        "value_price",
        "sample_count",
    }
    for row in records:
        assert set(row) == expected_keys


def test_parse_price_timeline_first_row_values():
    records = CrepriceSource._parse_price_timeline(_load_json("api_price_line.json"))
    first = records[0]

    # month "2025-7" 归一化为 "2025-07"
    assert first["year_month"] == "2025-07"
    assert first["supply_price"] == 9373
    assert first["sample_count"] == 486
    assert first["value_price"] == 9373


def test_parse_price_timeline_missing_attention_is_none():
    records = CrepriceSource._parse_price_timeline(_load_json("api_price_line.json"))
    by_month = {r["year_month"]: r for r in records}

    # 关注 series 首行 {"month":"2025-7"} 无 data → None
    assert by_month["2025-07"]["attention_price"] is None
    # 有 data 的月份正常取值
    assert by_month["2025-08"]["attention_price"] == 11471
    assert by_month["2026-01"]["attention_price"] == 16234


def test_parse_price_timeline_chronological_order():
    records = CrepriceSource._parse_price_timeline(_load_json("api_price_line.json"))
    months = [r["year_month"] for r in records]

    assert months == sorted(months)
    assert months[0] == "2025-07"
    assert months[-1] == "2026-07"


# -- 价格分布 --------------------------------------------------------------------


def test_parse_price_distribution_shape():
    records = CrepriceSource._parse_price_distribution(_load_json("api_price_bar.json"))

    assert len(records) == 21
    for row in records:
        assert set(row) == {"price_range_low", "price_range_high", "percentage"}


def test_parse_price_distribution_values():
    records = CrepriceSource._parse_price_distribution(_load_json("api_price_bar.json"))

    assert records[0] == {
        "price_range_low": 6000,
        "price_range_high": 7000,
        "percentage": 0.54,
    }
    by_low = {r["price_range_low"]: r for r in records}
    assert by_low[13000]["price_range_high"] == 14000
    assert by_low[13000]["percentage"] == 15.57
    assert records[-1]["price_range_low"] == 26000
    assert records[-1]["price_range_high"] == 27000


# -- 城市 / 区县列表 HTML 解析 + 去重 ---------------------------------------------


def test_parse_cities_dedup():
    cities = CrepriceSource._parse_cities(_load_text("citySel_snippet.html"))

    # aq / hf 在两个视图块各出现一次，qz 出现一次 → 去重后 3 个
    assert len(cities) == 3
    assert {c.code for c in cities} == {"aq", "hf", "qz"}
    by_code = {c.code: c.name for c in cities}
    assert by_code["aq"] == "安庆"
    assert by_code["hf"] == "合肥"
    assert by_code["qz"] == "泉州"


def test_parse_districts_composite_key():
    districts = CrepriceSource._parse_districts(_load_text("citySel_snippet.html"))

    assert len(districts) == 3
    pairs = {(d.city_code, d.code) for d in districts}
    assert pairs == {("aq", "QS"), ("aq", "TC"), ("hf", "CH")}
    by_code = {d.code: d.name for d in districts}
    assert by_code["QS"] == "潜山市"
    assert by_code["TC"] == "桐城市"
    assert by_code["CH"] == "巢湖市"


# -- 原始数据落地 ----------------------------------------------------------------


def test_save_raw_roundtrip(tmp_path):
    payload = [{"year_month": "2025-07", "supply_price": 9373}]
    path = save_raw("creprice", "qz", payload, "price_timeline", base_dir=tmp_path)

    saved = Path(path)
    assert saved.exists()
    assert saved.parent == tmp_path / "raw" / "creprice" / "qz"
    assert saved.name.endswith("_price_timeline.json")
    assert json.loads(saved.read_text(encoding="utf-8")) == payload
