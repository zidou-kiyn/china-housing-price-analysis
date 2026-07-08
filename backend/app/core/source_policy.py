"""数据源合并策略：多源快照读取时的优先级与口径元数据（唯一定义处）。

存储层各源独立（price_snapshot 唯一键含 source），同一 (region, month) 可能有
多行；需要"单值"的读取方（排行/对比/预测/默认走势）按此处优先级取一行：
月度源优于年度挂牌源——月度成交/评估价才是行情基准，年度挂牌只作历史底图。
"""

from __future__ import annotations

from sqlalchemy import case
from sqlalchemy.sql.elements import Case

from app.models.price_snapshot import PriceSnapshot

# 排序值小者优先。新增数据源时必须同步登记，否则落到兜底优先级 9。
SOURCE_PRIORITY: dict[str, int] = {
    "creprice": 0,
    "kaggle_lianjia": 1,
    "listing_annual_58": 2,
    "listing_annual_anjuke": 3,
}

_FALLBACK_PRIORITY = 9

# granularity: monthly|annual；basis: listing(挂牌)|transaction(成交)。前端标签/口径透出用。
SOURCE_META: dict[str, dict[str, str]] = {
    "creprice": {"granularity": "monthly", "basis": "listing"},
    "kaggle_lianjia": {"granularity": "monthly", "basis": "transaction"},
    "listing_annual_58": {"granularity": "annual", "basis": "listing"},
    "listing_annual_anjuke": {"granularity": "annual", "basis": "listing"},
}


def source_priority(source: str) -> int:
    return SOURCE_PRIORITY.get(source, _FALLBACK_PRIORITY)


def priority_case() -> Case:
    """PriceSnapshot.source → 优先级排序值的 SQL CASE（DISTINCT ON 排序用）。"""
    return case(SOURCE_PRIORITY, value=PriceSnapshot.source, else_=_FALLBACK_PRIORITY)
