"""快照写入前校验：值域 / 环比跳变 / 格式（纯函数，无副作用）。

所有 price_snapshot 写入路径（creprice 管线、年度批量导入、未来新源）统一先过
``validate_snapshot_records``：

- 值域：¥/㎡ ∈ [PRICE_MIN, PRICE_MAX]。任一非空价格字段超界 → 整行 rejected
  （跳过写入并计数）。creprice 管线的 cleaners 已把 ≤0 / ≥200000 置 None，
  故该路径实际新增拦截的只有 (0, 500) 的脏值；年度导入无前置清洗，全靠这里。
- 跳变：同区域相邻自然月 supply_price 环比 |Δ| > JUMP_THRESHOLD → flagged
  （照常写入，计数透出到 job 结果 / 导入统计）。局限：只在**本批次内部**
  比较（两条写入路径均按区域分批传入，不查库）；跨批次/跨源的异常由
  data_quality 审计报告兜底。
- 格式：year_month 必须为 YYYY-MM（月 01~12）；region 存在性由各调用方既有
  逻辑保证（creprice 按 code 解析、批量导入按城市名匹配跳过）。

指数表（price_index_snapshot）不适用值域规则（float、100 基准），其格式与
区间校验在 index_import.parse_index_csv 内自带，不走本模块。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# 值域与跳变阈值（初始常量，集中定义可调）
PRICE_MIN = 500
PRICE_MAX = 200_000
JUMP_THRESHOLD = 0.4  # 相邻月环比 |Δ| > 40% 标记

_PRICE_FIELDS = ("supply_price", "attention_price", "value_price")
_YEAR_MONTH_RE = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


@dataclass
class ValidationResult:
    """校验结果：accepted 可写入（含 flagged 行），rejected 跳过写入。"""

    accepted: list[dict] = field(default_factory=list)
    # [{year_month, reason, field?, value?}]
    rejected: list[dict] = field(default_factory=list)
    # [{year_month, prev_month, pct_change}]（flagged 行同时在 accepted 里）
    flagged: list[dict] = field(default_factory=list)


def _out_of_range_field(row: dict) -> tuple[str, int] | None:
    """返回首个超界的价格字段 (field, value)；全部在域内（或 None）时返回 None。"""
    for f in _PRICE_FIELDS:
        value = row.get(f)
        if value is not None and not PRICE_MIN <= value <= PRICE_MAX:
            return f, value
    return None


def _is_adjacent_month(prev: str, cur: str) -> bool:
    py, pm = int(prev[:4]), int(prev[5:7])
    cy, cm = int(cur[:4]), int(cur[5:7])
    return (cy * 12 + cm) - (py * 12 + pm) == 1


def validate_snapshot_records(records: list[dict]) -> ValidationResult:
    """校验单区域的一批快照行，返回 (accepted, rejected, flagged)。

    records 假定同一区域（creprice 管线与年度导入均按区域分批调用）；
    跳变检测按 year_month 排序后只比较相邻自然月（年度点相隔 12 个月，
    天然不触发环比规则——年度间一致性走审计报告）。
    """
    result = ValidationResult()
    for row in records:
        ym = row.get("year_month")
        if not isinstance(ym, str) or not _YEAR_MONTH_RE.match(ym):
            result.rejected.append({"year_month": ym, "reason": "bad_year_month"})
            continue
        oor = _out_of_range_field(row)
        if oor is not None:
            result.rejected.append(
                {
                    "year_month": ym,
                    "reason": "price_out_of_range",
                    "field": oor[0],
                    "value": oor[1],
                }
            )
            continue
        result.accepted.append(row)

    # 跳变检测：批内相邻自然月 supply_price 环比（不拦截，只标记）
    dated = sorted(
        (r for r in result.accepted if r.get("supply_price") is not None),
        key=lambda r: r["year_month"],
    )
    for prev, cur in zip(dated, dated[1:]):
        if not _is_adjacent_month(prev["year_month"], cur["year_month"]):
            continue
        prev_price = prev["supply_price"]
        if prev_price <= 0:
            continue
        pct = (cur["supply_price"] - prev_price) / prev_price
        if abs(pct) > JUMP_THRESHOLD:
            result.flagged.append(
                {
                    "year_month": cur["year_month"],
                    "prev_month": prev["year_month"],
                    "pct_change": round(pct * 100, 1),
                }
            )
    return result
