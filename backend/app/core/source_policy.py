"""数据源策略（creprice 单源）。"""

from __future__ import annotations

DEFAULT_SOURCE = "creprice"
REGISTERED_SOURCES: tuple[str, ...] = ("creprice",)
TRAINING_SOURCES: tuple[str, ...] = ("creprice",)

SOURCE_META: dict[str, dict[str, str]] = {
    "creprice": {"granularity": "monthly", "basis": "listing"},
}


def source_priority(source: str) -> int:
    return 0 if source == "creprice" else 9


def training_rows_only(rows_by_source: dict[str, list]) -> dict[str, list]:
    return {source: rows for source, rows in rows_by_source.items() if source in TRAINING_SOURCES}
