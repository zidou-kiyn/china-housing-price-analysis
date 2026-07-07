"""GovStatsSource 离线解析单测：用真实形状的 easyquery JSON，不打网络。

JSON 结构取自 research/govstats.md 实测录制片段（datanodes + wds + wdnodes）。
"""

import pytest

from app.collector.base import DataType
from app.collector.sources.gov_stats import (
    GovStatsBlockedError,
    GovStatsSource,
    easyquery,
    parse_index_response,
)

# 三维（zb + reg + sj）城市月度指数响应，含一条有数据 + 一条 hasdata=false 缺失月
_SAMPLE = {
    "returncode": 200,
    "returndata": {
        "datanodes": [
            {
                "code": "zb.A0901_reg.110000_sj.202405",
                "data": {"data": 100.2, "dotcount": 1, "hasdata": True, "strdata": "100.2"},
                "wds": [
                    {"valuecode": "A0901", "wdcode": "zb"},
                    {"valuecode": "110000", "wdcode": "reg"},
                    {"valuecode": "202405", "wdcode": "sj"},
                ],
            },
            {
                "code": "zb.A0901_reg.310000_sj.202405",
                "data": {"data": 0.0, "dotcount": 0, "hasdata": False, "strdata": ""},
                "wds": [
                    {"valuecode": "A0901", "wdcode": "zb"},
                    {"valuecode": "310000", "wdcode": "reg"},
                    {"valuecode": "202405", "wdcode": "sj"},
                ],
            },
        ],
        "wdnodes": [
            {"wdcode": "zb", "wdname": "指标", "nodes": [
                {"code": "A0901", "cname": "新建商品住宅销售价格指数(上月=100)", "unit": ""}]},
            {"wdcode": "reg", "wdname": "地区", "nodes": [
                {"code": "110000", "cname": "北京市"}, {"code": "310000", "cname": "上海市"}]},
            {"wdcode": "sj", "wdname": "时间", "nodes": [
                {"code": "202405", "name": "2024年5月"}]},
        ],
    },
}


def test_capabilities_index_only():
    assert GovStatsSource.supports(DataType.PRICE_INDEX)
    assert not GovStatsSource.supports(DataType.PRICE_TIMELINE)
    assert GovStatsSource.price_unit == "index"


def test_parse_normalizes_and_skips_missing():
    records = parse_index_response(_SAMPLE)
    # hasdata=false 的上海被跳过，只剩北京一条
    assert len(records) == 1
    rec = records[0]
    assert rec["region_code"] == "110000"
    assert rec["region_name"] == "北京市"
    assert rec["zb_code"] == "A0901"
    assert rec["zb_name"] == "新建商品住宅销售价格指数(上月=100)"
    assert rec["year_month"] == "2024-05"  # 202405 -> 2024-05
    assert rec["index_value"] == 100.2


def test_parse_empty_response():
    assert parse_index_response({}) == []
    assert parse_index_response({"returndata": {"datanodes": []}}) == []


def test_timeline_not_supported():
    with pytest.raises(NotImplementedError):
        GovStatsSource().fetch_price_timeline("bj")


def test_blocked_error_on_foreign_ip(monkeypatch):
    """easyquery 遇 403/UrlACL 抛 GovStatsBlockedError（提示需大陆 IP）。"""
    class _Resp:
        status_code = 403
        text = "reason:UrlACL Client IP: 54.37.83.196"

        def raise_for_status(self):  # pragma: no cover
            raise AssertionError("不应到达")

        def json(self):  # pragma: no cover
            return {}

    class _Session:
        trust_env = True

        def post(self, *a, **k):
            return _Resp()

    import app.collector.sources.gov_stats as mod

    monkeypatch.setattr(mod.requests, "Session", lambda: _Session())
    with pytest.raises(GovStatsBlockedError):
        easyquery(dbcode="csyd")
