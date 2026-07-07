"""采集数据清洗：纯函数，无副作用。"""

from __future__ import annotations


def clean_price_timeline(records: list[dict]) -> list[dict]:
    """过滤全 None 行，将超范围价格置 None。"""
    cleaned = []
    for row in records:
        supply = _clamp_price(row.get("supply_price"))
        attention = _clamp_price(row.get("attention_price"))
        value = _clamp_price(row.get("value_price"))
        if supply is None and attention is None and value is None:
            continue
        cleaned.append(
            {
                "year_month": row["year_month"],
                "supply_price": supply,
                "attention_price": attention,
                "value_price": value,
                "sample_count": row.get("sample_count"),
            }
        )
    return cleaned


def clean_price_distribution(records: list[dict], year_month: str) -> list[dict]:
    """过滤 percentage==0 和 low>=high，补充 year_month。"""
    cleaned = []
    for row in records:
        low = row.get("price_range_low")
        high = row.get("price_range_high")
        pct = row.get("percentage")
        if low is None or high is None or low >= high:
            continue
        if pct is None or pct == 0:
            continue
        cleaned.append(
            {
                "year_month": year_month,
                "price_range_low": low,
                "price_range_high": high,
                "percentage": pct,
            }
        )
    return cleaned


def _clamp_price(value: int | None) -> int | None:
    if value is None:
        return None
    if value <= 0 or value >= 200000:
        return None
    return value
