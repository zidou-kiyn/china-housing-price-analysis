"""国家统计局（data.stats.gov.cn）房价指数采集源。

**数据形态**：70 个大中城市商品住宅销售价格**指数**（100 基准 float，非 ¥/㎡），月度、无区县。
因此声明 `price_unit="index"` + 能力 `{PRICE_INDEX}`，**不进** ¥/㎡ 时序管线（PipelineRunner 会
以守卫拒绝，避免指数污染 supply_price）。指数入库表 / 前端展示为后续集成（见 govstats 任务）。

**网络前置（重要）**：`easyquery.htm` 被 WAF 按 IP 地理围栏（`reason:UrlACL`）硬拦，**境外 IP 一律
403，与 Header/Cookie 无关**。接入唯一前置是「中国大陆出口 IP」（境内机器或国内代理）。所给美国
代理对该站 TLS 直接 RST，不可用。本适配器的 easyquery 客户端与解析器已按官方前端参数实现并**离线
单测**；一旦提供大陆 IP（填入管理端「采集代理」为国内代理）即可 live 抓取。

无验证码 / 无滑块 / 无签名 / 无需登录；唯一参数 k1 是毫秒时间戳缓存穿透。
"""

from __future__ import annotations

import json
import logging
import time

import requests

from app.collector.base import BaseSource, CityInfo, DataType, RawRecord, SourceRegistry

logger = logging.getLogger(__name__)

_BASE_URL = "https://data.stats.gov.cn"
_EASYQUERY_URL = f"{_BASE_URL}/easyquery.htm"

# 与官方前端一致的请求头（无需 Cookie / 登录）
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36 Edg/99.0.1150.36"
    ),
    "Referer": "https://data.stats.gov.cn/easyquery.htm?cn=A01",
    "X-Requested-With": "XMLHttpRequest",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Host": "data.stats.gov.cn",
}

# 城市月度数据库（70 大中城市房价指数所在库）
_DBCODE_CITY_MONTH = "csyd"


class GovStatsBlockedError(RuntimeError):
    """easyquery 被 WAF 地理围栏拦截（境外 IP 403）。提示需中国大陆出口 IP。"""


def easyquery(
    *,
    m: str = "QueryData",
    dbcode: str = "hgyd",
    rowcode: str = "zb",
    colcode: str = "sj",
    wds: list[dict] | None = None,
    dfwds: list[dict] | None = None,
    node_id: str | None = None,
    wdcode: str | None = None,
    proxy: str | None = None,
    timeout: float = 30.0,
) -> dict:
    """调用 easyquery.htm 返回解析后的 JSON。境外 IP 会 403 → 抛 GovStatsBlockedError。

    wds=筛选维（地区 reg 放这里）；dfwds=主查询维（指标 zb + 时间 sj）。
    proxy 建议填**国内**代理；k1 毫秒时间戳仅作缓存穿透。
    """
    payload = {
        "m": m,
        "dbcode": dbcode,
        "rowcode": rowcode,
        "colcode": colcode,
        "wds": json.dumps(wds or [], ensure_ascii=False),
        "dfwds": json.dumps(dfwds or [], ensure_ascii=False),
        "k1": str(int(time.time() * 1000)),
    }
    if node_id:
        payload["id"] = node_id
    if wdcode:
        payload["wdcode"] = wdcode

    session = requests.Session()
    session.trust_env = False  # 不吃环境里的 http_proxy，代理只由 proxy 参数显式控制
    proxies = {"http": proxy, "https": proxy} if proxy else None
    resp = session.post(
        _EASYQUERY_URL, data=payload, headers=_HEADERS, proxies=proxies,
        verify=False, timeout=timeout,
    )
    if resp.status_code == 403 or "UrlACL" in resp.text[:500]:
        raise GovStatsBlockedError(
            "国家统计局 easyquery 返回 403（WAF 地理围栏）。需中国大陆出口 IP："
            "在管理端「采集代理」填入国内代理，或部署于境内。所给美国代理不可用。"
        )
    resp.raise_for_status()
    return resp.json()


def _period_to_year_month(sj: str) -> str:
    """时间维 valuecode 归一化：'202312' -> '2023-12'；年度 '2023' 原样返回。"""
    sj = sj.strip()
    if len(sj) == 6 and sj.isdigit():
        return f"{sj[:4]}-{sj[4:]}"
    return sj


def parse_index_response(json_data: dict) -> list[dict]:
    """解析 easyquery 指数响应为归一化记录。

    每条 datanode 用 wds（[{wdcode,valuecode}]）取指标(zb)/地区(reg)/时间(sj)；值取 data.data，
    hasdata=false 的缺失月份跳过。返回 [{region_code, region_name, zb_code, zb_name,
    year_month, index_value}]。
    """
    returndata = json_data.get("returndata") or {}
    datanodes = returndata.get("datanodes") or []
    wdnodes = returndata.get("wdnodes") or []

    # 维度字典：wdcode -> {valuecode -> 中文名}
    name_map: dict[str, dict[str, str]] = {}
    for wd in wdnodes:
        code = wd.get("wdcode")
        if not code:
            continue
        name_map[code] = {
            n.get("code"): (n.get("cname") or n.get("name") or "")
            for n in wd.get("nodes", [])
            if n.get("code")
        }

    records: list[dict] = []
    for node in datanodes:
        data = node.get("data") or {}
        if not data.get("hasdata"):
            continue
        dims = {w.get("wdcode"): w.get("valuecode") for w in node.get("wds", [])}
        zb = dims.get("zb")
        sj = dims.get("sj")
        reg = dims.get("reg")
        if zb is None or sj is None:
            continue
        records.append(
            {
                "region_code": reg,
                "region_name": name_map.get("reg", {}).get(reg) if reg else None,
                "zb_code": zb,
                "zb_name": name_map.get("zb", {}).get(zb),
                "year_month": _period_to_year_month(sj),
                "index_value": data.get("data"),
            }
        )
    return records


class GovStatsSource(BaseSource):
    source_name = "govstats"
    base_url = _BASE_URL
    # 指数源：不参与 ¥/㎡ 时序 / 区县 / 分布管线
    capabilities = frozenset({DataType.PRICE_INDEX})
    price_unit = "index"

    def __init__(self, proxy: str | None = None) -> None:
        # 默认读管理端「采集代理」（应配国内代理）；None 时直连（境外必 403）。
        if proxy is None:
            try:
                from app.services.app_settings import get_proxy_url_sync

                proxy = get_proxy_url_sync()
            except Exception:  # pragma: no cover - 配置不可用时退化直连
                proxy = None
        self.proxy = proxy

    # -- BaseSource 抽象方法（指数源不走 ¥/㎡ 管线，这里满足接口/供适配器自用）----------

    def fetch_cities(self) -> list[CityInfo]:
        """从 csyd 地区维取 70 大中城市列表（reg=6 位 GB 码）。境外 IP 会 403。"""
        tree = easyquery(
            m="getTree", dbcode=_DBCODE_CITY_MONTH, node_id="reg", wdcode="reg",
            proxy=self.proxy,
        )
        cities: list[CityInfo] = []
        for node in tree if isinstance(tree, list) else []:
            code = node.get("id") or node.get("code")
            name = node.get("name")
            if code and name:
                cities.append(CityInfo(name=name.strip(), code=code, province=None))
        return cities

    def fetch_price_timeline(self, city_code: str, district_code: str = "allsq1") -> RawRecord:
        raise NotImplementedError(
            "govstats 为价格指数源（非 ¥/㎡），不支持 fetch_price_timeline；"
            "请用 fetch_price_index（指数入库管线为后续集成）"
        )

    # -- 指数采集 ----------------------------------------------------------------

    def fetch_price_index(
        self, reg_codes: list[str], zb_code: str, sj: str = "LAST13"
    ) -> RawRecord:
        """抓取指定城市(reg 6 位 GB 码)、指定房价指标(zb)、时间段(sj)的价格指数。

        sj 支持 '202312' / '202301-202312' / 'LAST13' 等。需中国大陆 IP。
        """
        result = easyquery(
            dbcode=_DBCODE_CITY_MONTH,
            wds=[{"wdcode": "reg", "valuecode": ",".join(reg_codes)}] if reg_codes else [],
            dfwds=[
                {"wdcode": "zb", "valuecode": zb_code},
                {"wdcode": "sj", "valuecode": sj},
            ],
            proxy=self.proxy,
        )
        records = parse_index_response(result)
        return RawRecord(
            source=self.source_name,
            city_code=",".join(reg_codes),
            data_type="price_index",
            records=records,
            raw_url=_EASYQUERY_URL,
        )


SourceRegistry.register(GovStatsSource.source_name, GovStatsSource)
