"""训练源白名单单测（creprice-first 方针）。"""

from app.core.source_policy import TRAINING_SOURCES, training_rows_only


def test_training_sources_is_creprice_only():
    assert TRAINING_SOURCES == ("creprice",)


def test_training_rows_only_keeps_whitelist_source():
    """构造含 58/kaggle 行的取数场景：过滤后只剩 creprice 行（R1 验收）。"""
    rows_by_source = {
        "creprice": [{"region_type": "city", "region_id": 1, "year_month": "2025-07", "supply_price": 9000}],
        "listing_annual_58": [{"region_type": "city", "region_id": 1, "year_month": "2020-12", "supply_price": 11000}],
        "kaggle_lianjia": [{"region_type": "city", "region_id": 2, "year_month": "2024-01", "supply_price": 8000}],
    }
    filtered = training_rows_only(rows_by_source)
    assert set(filtered) == {"creprice"}
    assert filtered["creprice"] == rows_by_source["creprice"]


def test_training_rows_only_empty_when_no_whitelist_source():
    """全部为非白名单源时训练集为空（源硬隔离，不回退）。"""
    assert training_rows_only({"listing_annual_58": [{"x": 1}], "kaggle_lianjia": [{"y": 2}]}) == {}


def test_training_rows_only_empty_input():
    assert training_rows_only({}) == {}
