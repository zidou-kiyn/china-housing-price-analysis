"""data_quality 纯函数计算单元测试：构造已知答案验证四节报告与模型新鲜度。"""

from datetime import datetime

from app.services.data_quality import (
    NO_INDEX_STATUS,
    compute_coverage,
    compute_mom_direction_consistency,
    compute_model_freshness,
    compute_overlap_outliers,
    compute_yoy_direction_consistency,
)


def _price(region_id: int, ym: str, price: float) -> dict:
    return {
        "region_type": "city",
        "region_id": region_id,
        "year_month": ym,
        "supply_price": price,
    }


def _idx(region_id: int, ym: str, value: float) -> dict:
    return {
        "region_type": "city",
        "region_id": region_id,
        "year_month": ym,
        "index_value": value,
        "source": "nbs_github_changao1",
    }


class TestOverlapOutliers:
    def test_ratio_outside_range_listed(self):
        rows = {
            "creprice": [_price(1, "2025-01", 25000), _price(1, "2025-02", 11000)],
            "listing_annual_58": [_price(1, "2025-01", 10000), _price(1, "2025-02", 10000)],
        }
        result = compute_overlap_outliers(rows)
        assert result["pairs"] == 2
        assert result["outliers_total"] == 1
        outlier = result["outliers"][0]
        # 比值 = 高优先级源(creprice) / 低优先级源
        assert outlier["year_month"] == "2025-01"
        assert outlier["source_a"] == "creprice"
        assert outlier["ratio"] == 2.5

    def test_no_overlap_no_pairs(self):
        rows = {
            "creprice": [_price(1, "2025-01", 10000)],
            "listing_annual_58": [_price(2, "2025-01", 10000)],
        }
        result = compute_overlap_outliers(rows)
        assert result["pairs"] == 0
        assert result["outliers"] == []
        assert result["ratio_median"] is None

    def test_none_price_skipped(self):
        rows = {
            "creprice": [_price(1, "2025-01", None)],
            "listing_annual_58": [_price(1, "2025-01", 10000)],
        }
        assert compute_overlap_outliers(rows)["pairs"] == 0


class TestMomDirectionConsistency:
    def test_known_answer(self):
        """4 个月：涨/跌/平各态齐全，手算一致率 1/2。"""
        prices = [
            _price(1, "2025-01", 10000),
            _price(1, "2025-02", 10200),  # +2% 涨
            _price(1, "2025-03", 10100),  # -0.98% 跌
            _price(1, "2025-04", 10100),  # 0% 平 → 剔除
        ]
        index = [
            _idx(1, "2025-02", 101.0),  # 涨 → 与价格一致
            _idx(1, "2025-03", 100.5),  # 涨 → 与价格不一致
            _idx(1, "2025-04", 100.0),  # 平
        ]
        result = compute_mom_direction_consistency(prices, index)
        assert result["status"] == "ok"
        assert result["regions"] == 1
        assert result["compared"] == 2
        assert result["matches"] == 1
        assert result["agreement_rate"] == 50.0
        assert result["flat_excluded"] == 1

    def test_index_flat_also_excluded(self):
        prices = [_price(1, "2025-01", 10000), _price(1, "2025-02", 10500)]
        index = [_idx(1, "2025-02", 100.05)]  # |Δ|<0.1 记平
        result = compute_mom_direction_consistency(prices, index)
        assert result["compared"] == 0
        assert result["flat_excluded"] == 1
        assert result["agreement_rate"] is None

    def test_no_index_data_degrades(self):
        result = compute_mom_direction_consistency([_price(1, "2025-01", 10000)], [])
        assert result["status"] == NO_INDEX_STATUS

    def test_no_overlap_region(self):
        prices = [_price(1, "2025-01", 10000), _price(1, "2025-02", 10500)]
        index = [_idx(2, "2025-02", 101.0)]  # 另一区域
        assert compute_mom_direction_consistency(prices, index)["status"] == "no overlap"

    def test_non_adjacent_months_skipped(self):
        prices = [_price(1, "2025-01", 10000), _price(1, "2025-05", 20000)]
        index = [_idx(1, "2025-05", 101.0)]
        assert compute_mom_direction_consistency(prices, index)["status"] == "no overlap"


class TestYoyDirectionConsistency:
    def test_known_answer(self):
        """两个年度对：涨-涨一致 + 跌-涨不一致 → 一致率 50%。"""
        annual = [
            _price(1, "2019-12", 10000),
            _price(1, "2020-12", 11000),  # +10% 涨
            _price(1, "2021-12", 10500),  # -4.5% 跌
        ]
        index = [
            _idx(1, f"2020-{m:02d}", 101.0) for m in range(1, 13)  # 链乘 +12.7% 涨
        ] + [
            _idx(1, f"2021-{m:02d}", 100.5) for m in range(1, 13)  # 链乘 +6.2% 涨
        ]
        result = compute_yoy_direction_consistency(annual, index)
        assert result["status"] == "ok"
        assert result["compared"] == 2
        assert result["matches"] == 1
        assert result["agreement_rate"] == 50.0
        assert result["skipped_missing_index"] == 0

    def test_missing_month_skips_pair(self):
        annual = [_price(1, "2019-12", 10000), _price(1, "2020-12", 11000)]
        index = [_idx(1, f"2020-{m:02d}", 101.0) for m in range(1, 12)]  # 缺 12 月
        result = compute_yoy_direction_consistency(annual, index)
        assert result["compared"] == 0
        assert result["skipped_missing_index"] == 1

    def test_no_index_data_degrades(self):
        result = compute_yoy_direction_consistency([_price(1, "2019-12", 10000)], [])
        assert result["status"] == NO_INDEX_STATUS


class TestCoverage:
    def test_regions_latest_and_months_behind(self):
        rows = {
            "creprice": [_price(1, "2026-05", 10000), _price(2, "2026-06", 12000)],
            "listing_annual_58": [_price(3, "2024-12", 8000)],
        }
        index = [_idx(1, "2026-05", 100.2)]
        entries = compute_coverage(rows, index, datetime(2026, 7, 8))
        by_source = {e["source"]: e for e in entries}
        assert by_source["creprice"]["regions"] == 2
        assert by_source["creprice"]["latest_month"] == "2026-06"
        assert by_source["creprice"]["months_behind"] == 1
        assert by_source["listing_annual_58"]["months_behind"] == 19
        assert by_source["listing_annual_58"]["granularity"] == "annual"
        assert by_source["nbs_github_changao1"]["kind"] == "index"
        # 快照源按优先级排序，指数源殿后
        assert [e["kind"] for e in entries] == ["snapshot", "snapshot", "index"]

    def test_no_index_omitted(self):
        entries = compute_coverage(
            {"creprice": [_price(1, "2026-06", 10000)]}, [], datetime(2026, 7, 8)
        )
        assert [e["kind"] for e in entries] == ["snapshot"]


class TestModelFreshness:
    _META = {
        "model_name": "random_forest",
        "version": "v1.8",
        "trained_at": "2026-07-08T00:00:00+00:00",
        "dataset": {"fingerprint": "abc123"},
    }

    def test_fresh_when_fingerprints_match(self):
        result = compute_model_freshness(self._META, "abc123")
        assert result["status"] == "fresh"
        assert result["model_version"] == "v1.8"

    def test_stale_when_fingerprints_differ(self):
        result = compute_model_freshness(self._META, "def456")
        assert result["status"] == "stale"
        assert "重训" in result["note"]

    def test_unknown_without_active_model(self):
        assert compute_model_freshness(None, "abc123")["status"] == "unknown"

    def test_unknown_without_dataset_fingerprint(self):
        meta = {"model_name": "random_forest", "version": "v1.0", "metrics": {}}
        assert compute_model_freshness(meta, "abc123")["status"] == "unknown"
