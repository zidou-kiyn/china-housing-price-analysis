"""snapshot_validator 纯函数单元测试：值域边界、跳变阈值、格式校验。"""

from app.pipeline.snapshot_validator import (
    JUMP_THRESHOLD,
    PRICE_MAX,
    PRICE_MIN,
    validate_snapshot_records,
)


def _row(year_month: str, supply: int | None, **extra) -> dict:
    return {"year_month": year_month, "supply_price": supply, **extra}


class TestPriceRange:
    def test_boundary_values(self):
        """499 拒 / 500 收 / 200000 收 / 200001 拒。"""
        vr = validate_snapshot_records(
            [
                _row("2025-01", PRICE_MIN - 1),
                _row("2025-02", PRICE_MIN),
                _row("2025-03", PRICE_MAX),
                _row("2025-04", PRICE_MAX + 1),
            ]
        )
        assert [r["year_month"] for r in vr.accepted] == ["2025-02", "2025-03"]
        assert [r["year_month"] for r in vr.rejected] == ["2025-01", "2025-04"]
        assert all(r["reason"] == "price_out_of_range" for r in vr.rejected)
        assert vr.rejected[0]["value"] == 499
        assert vr.rejected[1]["value"] == 200001

    def test_secondary_price_field_out_of_range_rejects_row(self):
        vr = validate_snapshot_records(
            [_row("2025-01", 9000, attention_price=300)]
        )
        assert vr.accepted == []
        assert vr.rejected[0]["field"] == "attention_price"

    def test_none_prices_pass_range_check(self):
        """None 字段不参与值域判断（creprice 清洗后常见部分 None）。"""
        vr = validate_snapshot_records(
            [_row("2025-01", 9000, attention_price=None, value_price=None)]
        )
        assert len(vr.accepted) == 1
        assert vr.rejected == []


class TestYearMonthFormat:
    def test_bad_formats_rejected(self):
        vr = validate_snapshot_records(
            [
                _row("2025-13", 9000),
                _row("2025-00", 9000),
                _row("202501", 9000),
                _row(None, 9000),
                _row("2025-01", 9000),
            ]
        )
        assert len(vr.accepted) == 1
        assert len(vr.rejected) == 4
        assert all(r["reason"] == "bad_year_month" for r in vr.rejected)


class TestJumpDetection:
    def test_39_pct_not_flagged_41_pct_flagged(self):
        base = 10000
        below = int(base * (1 + JUMP_THRESHOLD - 0.01))  # +39%
        vr = validate_snapshot_records([_row("2025-01", base), _row("2025-02", below)])
        assert vr.flagged == []

        above = int(base * (1 + JUMP_THRESHOLD + 0.01))  # +41%
        vr = validate_snapshot_records([_row("2025-01", base), _row("2025-02", above)])
        assert len(vr.flagged) == 1
        assert vr.flagged[0]["year_month"] == "2025-02"
        assert vr.flagged[0]["prev_month"] == "2025-01"
        assert vr.flagged[0]["pct_change"] == 41.0

    def test_downward_jump_flagged(self):
        vr = validate_snapshot_records([_row("2025-01", 10000), _row("2025-02", 5000)])
        assert len(vr.flagged) == 1
        assert vr.flagged[0]["pct_change"] == -50.0

    def test_flagged_rows_still_accepted(self):
        """跳变只标记不拦截：行仍在 accepted 里照常写入。"""
        vr = validate_snapshot_records([_row("2025-01", 10000), _row("2025-02", 20000)])
        assert len(vr.accepted) == 2
        assert len(vr.flagged) == 1

    def test_annual_points_not_flagged(self):
        """年度点相隔 12 个月，非相邻自然月不做环比跳变检测。"""
        vr = validate_snapshot_records(
            [_row("2019-12", 8000), _row("2020-12", 16000)]
        )
        assert vr.flagged == []
        assert len(vr.accepted) == 2

    def test_unsorted_input_compared_in_month_order(self):
        vr = validate_snapshot_records(
            [_row("2025-02", 20000), _row("2025-01", 10000)]
        )
        assert len(vr.flagged) == 1
        assert vr.flagged[0]["year_month"] == "2025-02"

    def test_rejected_rows_excluded_from_jump_pairs(self):
        """被值域拒绝的行不参与跳变对比。"""
        vr = validate_snapshot_records(
            [_row("2025-01", 10000), _row("2025-02", 300), _row("2025-03", 10100)]
        )
        assert len(vr.rejected) == 1
        assert vr.flagged == []  # 01 与 03 不相邻，不比较


class TestEmptyAndPassthrough:
    def test_empty_input(self):
        vr = validate_snapshot_records([])
        assert vr.accepted == [] and vr.rejected == [] and vr.flagged == []

    def test_valid_rows_pass_through_unchanged(self):
        """合法数据原样通过（回归保证：不改变既有导入行为）。"""
        rows = [
            _row("2025-01", 9000, attention_price=8500, value_price=9100, sample_count=3),
            _row("2025-02", 9100, attention_price=8600, value_price=9200, sample_count=4),
        ]
        vr = validate_snapshot_records(rows)
        assert vr.accepted == rows
        assert vr.rejected == [] and vr.flagged == []
