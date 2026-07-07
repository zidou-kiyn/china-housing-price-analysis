"""清洗函数单元测试。"""

from app.pipeline.cleaners import clean_price_distribution, clean_price_timeline


class TestCleanPriceTimeline:
    def test_keeps_valid_rows(self):
        records = [
            {
                "year_month": "2025-01",
                "supply_price": 9000,
                "attention_price": 8500,
                "value_price": 9200,
                "sample_count": 100,
            }
        ]
        result = clean_price_timeline(records)
        assert len(result) == 1
        assert result[0]["supply_price"] == 9000

    def test_drops_all_none_row(self):
        records = [
            {
                "year_month": "2025-01",
                "supply_price": None,
                "attention_price": None,
                "value_price": None,
                "sample_count": 50,
            }
        ]
        assert clean_price_timeline(records) == []

    def test_clamps_out_of_range_price(self):
        records = [
            {
                "year_month": "2025-01",
                "supply_price": 250000,
                "attention_price": -10,
                "value_price": 9000,
                "sample_count": 10,
            }
        ]
        result = clean_price_timeline(records)
        assert len(result) == 1
        assert result[0]["supply_price"] is None
        assert result[0]["attention_price"] is None
        assert result[0]["value_price"] == 9000

    def test_keeps_partial_none_row(self):
        records = [
            {
                "year_month": "2025-06",
                "supply_price": 8000,
                "attention_price": None,
                "value_price": None,
            }
        ]
        result = clean_price_timeline(records)
        assert len(result) == 1
        assert result[0]["supply_price"] == 8000
        assert result[0]["attention_price"] is None

    def test_empty_input(self):
        assert clean_price_timeline([]) == []


class TestCleanPriceDistribution:
    def test_keeps_valid_rows(self):
        records = [
            {"price_range_low": 6000, "price_range_high": 7000, "percentage": 12.5}
        ]
        result = clean_price_distribution(records, "2025-07")
        assert len(result) == 1
        assert result[0]["year_month"] == "2025-07"
        assert result[0]["percentage"] == 12.5

    def test_drops_zero_percentage(self):
        records = [
            {"price_range_low": 6000, "price_range_high": 7000, "percentage": 0}
        ]
        assert clean_price_distribution(records, "2025-07") == []

    def test_drops_none_percentage(self):
        records = [
            {"price_range_low": 6000, "price_range_high": 7000, "percentage": None}
        ]
        assert clean_price_distribution(records, "2025-07") == []

    def test_drops_invalid_range(self):
        records = [
            {"price_range_low": 7000, "price_range_high": 6000, "percentage": 5.0},
            {"price_range_low": 8000, "price_range_high": 8000, "percentage": 3.0},
        ]
        assert clean_price_distribution(records, "2025-07") == []

    def test_empty_input(self):
        assert clean_price_distribution([], "2025-07") == []
