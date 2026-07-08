"""数据源口径元数据与登记表（唯一定义处）。

存储层各源独立（price_snapshot 唯一键含 source），同一 (region, month) 可能有多行。
creprice-first 方针（2026-07-08）后**读取层不再跨源合并**：视图按全局 `source`
单源直读，各源硬隔离。SOURCE_PRIORITY 保留，仅用于「切换器选项排序」与
`/prices/trend/series` 多源分线的稳定排序（不再驱动合并取值）。
"""

from __future__ import annotations

# 排序值小者优先。新增数据源时必须同步登记，否则落到兜底优先级 9。
SOURCE_PRIORITY: dict[str, int] = {
    "creprice": 0,
    "kaggle_lianjia": 1,
    "listing_annual_58": 2,
    "listing_annual_anjuke": 3,
}

_FALLBACK_PRIORITY = 9

# 已登记的 price_snapshot 源（按优先级排序），供读取层 `source` 查询参数校验。
# NBS 指数不在此列——它是 price_index_snapshot 源，走独立端点，不进 ¥/㎡ 端点。
REGISTERED_SOURCES: tuple[str, ...] = tuple(
    sorted(SOURCE_PRIORITY, key=lambda s: SOURCE_PRIORITY[s])
)
DEFAULT_SOURCE = "creprice"

# granularity: monthly|annual；basis: listing(挂牌)|transaction(成交)。前端标签/口径透出用。
SOURCE_META: dict[str, dict[str, str]] = {
    "creprice": {"granularity": "monthly", "basis": "listing"},
    "kaggle_lianjia": {"granularity": "monthly", "basis": "transaction"},
    "listing_annual_58": {"granularity": "annual", "basis": "listing"},
    "listing_annual_anjuke": {"granularity": "annual", "basis": "listing"},
}


def source_priority(source: str) -> int:
    return SOURCE_PRIORITY.get(source, _FALLBACK_PRIORITY)
