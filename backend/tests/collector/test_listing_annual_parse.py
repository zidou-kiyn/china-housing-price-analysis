"""listing_annual 离线解析单测：小 fixture CSV 文本，不下载、不打网络。"""

import pytest

import app.collector.sources.listing_annual as mod
from app.collector.sources.listing_annual import SOURCES, download_csv, parse_annual_csv

_HEADER = "province,city,year,price_yuan_per_sqm,yoy_pct\n"


def test_sources_declares_58_and_anjuke():
    assert set(SOURCES) == {"58", "anjuke"}
    for url, source_tag in SOURCES.values():
        assert url.startswith("https://raw.githubusercontent.com/")
        assert source_tag.startswith("listing_annual_")


def test_parse_basic_rows():
    text = _HEADER + "河南,洛阳,2019,8556,11.51\n新疆,克拉玛依,2024,5278,0.30\n"
    assert parse_annual_csv(text) == [
        {"province": "河南", "city": "洛阳", "year": 2019, "price": 8556},
        {"province": "新疆", "city": "克拉玛依", "year": 2024, "price": 5278},
    ]


def test_parse_skips_missing_and_invalid():
    text = _HEADER + (
        "上海,上海,2010,22311,\n"  # yoy 空（每城首年）→ 保留
        "河南,,2019,8556,1.0\n"  # city 空 → 跳过
        ",洛阳,2019,8556,1.0\n"  # province 空 → 跳过
        "河南,洛阳,,8556,1.0\n"  # year 空 → 跳过
        "河南,洛阳,2019,,1.0\n"  # price 空 → 跳过
        "河南,洛阳,abcd,8556,1.0\n"  # year 非法 → 跳过
        "河南,洛阳,2019,abc,1.0\n"  # price 非法 → 跳过
    )
    assert parse_annual_csv(text) == [
        {"province": "上海", "city": "上海", "year": 2010, "price": 22311}
    ]


def test_parse_filters_price_out_of_range():
    text = _HEADER + (
        "甘肃,某城,2020,499,\n"  # 低于下限
        "香港,香港,2020,300001,\n"  # 高于上限
        "北京,北京,2024,58950,3.2\n"
    )
    records = parse_annual_csv(text)
    assert [r["city"] for r in records] == ["北京"]


def test_parse_rounds_float_price():
    text = _HEADER + "海南,三亚,2024,29787.6,\n"
    assert parse_annual_csv(text)[0]["price"] == 29788


def test_download_uses_cache(tmp_path, monkeypatch):
    cached = tmp_path / "58tongcheng_city_avg_price_annual_2010-2024.csv"
    cached.write_text(_HEADER, encoding="utf-8")

    def _no_network(*args, **kwargs):
        raise AssertionError("已有缓存时不应发起下载")

    monkeypatch.setattr(mod.requests, "get", _no_network)
    assert download_csv("58", cache_dir=tmp_path) == cached


def test_download_unknown_source_raises():
    with pytest.raises(ValueError, match="未知年度房价源"):
        download_csv("unknown")
