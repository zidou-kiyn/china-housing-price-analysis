"""KaggleLianjiaSource 离线解析/聚合单测：用小 fixture CSV，不下载、不打网络。"""

from pathlib import Path

import pytest

import app.collector.sources.kaggle_lianjia as mod
from app.collector.base import DataType
from app.collector.sources.kaggle_lianjia import KaggleLianjiaSource

_HEADER = "url,id,tradeTime,price,square,district\n"


def _write_csv(tmp_path: Path, rows: list[str]) -> None:
    csv_dir = tmp_path / "ruiqurm_lianjia"
    csv_dir.mkdir(parents=True)
    (csv_dir / "new.csv").write_text(_HEADER + "".join(rows), encoding="utf-8")


def _row(trade_time: str, price: str, district: str = "7") -> str:
    return f"http://x,1,{trade_time},{price},100.0,{district}\n"


@pytest.fixture
def low_threshold(monkeypatch):
    """把每月最小样本阈值降到 3，便于小 fixture 测试。"""
    monkeypatch.setattr(mod, "_MIN_SAMPLES_PER_MONTH", 3)


def test_capabilities_declared():
    assert KaggleLianjiaSource.supports(DataType.CITIES)
    assert KaggleLianjiaSource.supports(DataType.PRICE_TIMELINE)
    assert not KaggleLianjiaSource.supports(DataType.DISTRICTS)
    assert not KaggleLianjiaSource.supports(DataType.PRICE_DISTRIBUTION)


def test_fetch_cities_returns_beijing():
    cities = KaggleLianjiaSource().fetch_cities()
    assert len(cities) == 1
    assert cities[0].code == "bj"
    assert cities[0].name == "北京"


def test_aggregates_monthly_mean(tmp_path, low_threshold):
    rows = [_row("2016-05-01", "30000"), _row("2016-05-15", "40000"), _row("2016-05-20", "50000")]
    _write_csv(tmp_path, rows)
    raw = KaggleLianjiaSource(cache_dir=tmp_path).fetch_price_timeline("bj")
    assert len(raw.records) == 1
    rec = raw.records[0]
    assert rec["year_month"] == "2016-05"
    assert rec["supply_price"] == 40000  # (30000+40000+50000)/3
    assert rec["sample_count"] == 3
    assert rec["attention_price"] is None and rec["value_price"] is None
    assert raw.source == "kaggle_lianjia"


def test_filters_low_sample_and_bad_price(tmp_path, monkeypatch):
    monkeypatch.setattr(mod, "_MIN_SAMPLES_PER_MONTH", 5)
    rows = (
        [_row("2015-01-10", "45000")]  # 仅 1 笔 → 低于阈值滤除
        + [_row("2015-02-%02d" % d, "50000") for d in range(1, 6)]  # 5 有效笔 → 保留
        + [_row("2015-02-10", "abc"), _row("2015-02-11", "999999999")]  # 坏值/超范围 → 剔除
    )
    _write_csv(tmp_path, rows)
    raw = KaggleLianjiaSource(cache_dir=tmp_path).fetch_price_timeline("bj")
    assert [r["year_month"] for r in raw.records] == ["2015-02"]
    assert raw.records[0]["sample_count"] == 5


def test_rejects_non_beijing(tmp_path):
    with pytest.raises(ValueError):
        KaggleLianjiaSource(cache_dir=tmp_path).fetch_price_timeline("sh")
