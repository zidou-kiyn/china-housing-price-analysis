"""NBS 70 城房价指数导入：GitHub 直链 CSV → price_index_snapshot。

数据源 changao1/70-China-cities-housing-index-data-by-national-bureau-of-statistics
的 `merged_housing_data_eng.csv`（MIT，GitHub Action 每月自动更新）：70 城 × 月度
（2011-01 起），new_home_price_index / existing_home_price_index 均为**环比指数
（上月=100，float）**。指数禁止塞 PriceSnapshot（govstats.md §8.1）——独立表、
唯一键含全部口径维度；也不登记 SOURCE_PRIORITY/SOURCE_META（不是 ¥/㎡ 快照源）。

CSV 按城市**英文名**组织，用静态 crosswalk 对齐 city.name（中文）；未匹配城市
跳过并报告（同 nationwide_import 约定，不新建脏城市行）。
"""

from __future__ import annotations

import asyncio
import csv
import io
import logging
from pathlib import Path

import requests
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.collector.storage import DEFAULT_DATA_ROOT
from app.models.city import City
from app.models.price_index_snapshot import PriceIndexSnapshot

logger = logging.getLogger(__name__)

INDEX_SOURCE_TAG = "nbs_github_changao1"

INDEX_CSV_URL = (
    "https://raw.githubusercontent.com/changao1/"
    "70-China-cities-housing-index-data-by-national-bureau-of-statistics/main/"
    "merged_housing_data_eng.csv"
)

# CSV 列名 → dwelling_type（本轮只导新建/二手两个总指数，分面积段列忽略）
_DWELLING_COLUMNS = {
    "new_home_price_index": "new",
    "existing_home_price_index": "second",
}

# 环比指数合理区间（上月=100；2011~2026 实测全部落在 96~110 内），区间外视为脏数据跳过
_INDEX_MIN = 50.0
_INDEX_MAX = 200.0

_DOWNLOAD_TIMEOUT = 60.0

# asyncpg 单语句参数上限 32767，7 列/行 → 每批 2000 行留足余量
_UPSERT_CHUNK = 2000

# CSV 城市英文名 → city.name（中文）静态 crosswalk。
# 70 项与 2026-07 实测 CSV 的 distinct 城市一一对应，全部在 368 城 city 表中有同名行
# （已 SQL 实测验证）。静态映射而非模糊匹配：一次写死、可审计、无误配风险。
NBS_CITY_NAME_MAP: dict[str, str] = {
    "Anqing": "安庆",
    "Baotou": "包头",
    "Beihai": "北海",
    "Beijing": "北京",
    "Bengbu": "蚌埠",
    "Changchun": "长春",
    "Changde": "常德",
    "Changsha": "长沙",
    "Chengdu": "成都",
    "Chongqing": "重庆",
    "Dali": "大理",
    "Dalian": "大连",
    "Dandong": "丹东",
    "Fuzhou": "福州",
    "Ganzhou": "赣州",
    "Guangzhou": "广州",
    "Guilin": "桂林",
    "Guiyang": "贵阳",
    "Haikou": "海口",
    "Hangzhou": "杭州",
    "Harbin": "哈尔滨",
    "Hefei": "合肥",
    "Hohhot": "呼和浩特",
    "Huizhou": "惠州",
    "Jilin": "吉林",
    "Jinan": "济南",
    "Jinhua": "金华",
    "Jining": "济宁",
    "Jinzhou": "锦州",
    "Jiujiang": "九江",
    "Kunming": "昆明",
    "Lanzhou": "兰州",
    "Luoyang": "洛阳",
    "Luzhou": "泸州",
    "Mudanjiang": "牡丹江",
    "Nanchang": "南昌",
    "Nanchong": "南充",
    "Nanjing": "南京",
    "Nanning": "南宁",
    "Ningbo": "宁波",
    "Pingdingshan": "平顶山",
    "Qingdao": "青岛",
    "Qinhuangdao": "秦皇岛",
    "Quanzhou": "泉州",
    "Sanya": "三亚",
    "Shanghai": "上海",
    "Shaoguan": "韶关",
    "Shenyang": "沈阳",
    "Shenzhen": "深圳",
    "Shijiazhuang": "石家庄",
    "Taiyuan": "太原",
    "Tangshan": "唐山",
    "Tianjin": "天津",
    "Urumqi": "乌鲁木齐",
    "Wenzhou": "温州",
    "Wuhan": "武汉",
    "Wuxi": "无锡",
    "Xiamen": "厦门",
    "Xi'an": "西安",
    "Xiangyang": "襄阳",
    "Xining": "西宁",
    "Xuzhou": "徐州",
    "Yangzhou": "扬州",
    "Yantai": "烟台",
    "Yichang": "宜昌",
    "Yinchuan": "银川",
    "Yueyang": "岳阳",
    "Zhanjiang": "湛江",
    "Zhengzhou": "郑州",
    "Zunyi": "遵义",
}


def download_csv(cache_dir: Path | str | None = None) -> Path:
    """下载 NBS 指数 CSV，返回本地路径。

    源仓库每月自动更新，故**每次重新下载并覆盖缓存**（与静态年度数据集的
    「已缓存则复用」不同）；下载失败直接抛错给调用方（job 显式失败，不静默空导入）。
    """
    root = Path(cache_dir) if cache_dir is not None else DEFAULT_DATA_ROOT / "index"
    csv_path = root / INDEX_CSV_URL.rsplit("/", 1)[-1]
    root.mkdir(parents=True, exist_ok=True)
    logger.info("下载 NBS 70 城指数数据集 %s ...", INDEX_CSV_URL)
    resp = requests.get(INDEX_CSV_URL, timeout=_DOWNLOAD_TIMEOUT)
    resp.raise_for_status()
    if not resp.content:
        raise RuntimeError(f"NBS 指数 CSV 下载内容为空: {INDEX_CSV_URL}")
    csv_path.write_bytes(resp.content)
    logger.info("指数数据集已缓存: %s", csv_path)
    return csv_path


def parse_index_csv(text: str) -> list[dict]:
    """解析指数 CSV，返回 {city_en, year_month, dwelling_type, index_value} 记录列表。

    每行 CSV 拆出新建/二手两条记录；城市/年/月缺失、类型非法或指数超出合理
    区间的值跳过。分面积段的 6 列忽略（本轮只导两个总指数）。

    校验说明（snapshot_validator 约定的第三条写入路径）：指数是 float、100
    基准，不适用 ¥/㎡ 值域与环比跳变规则；格式校验（年/月合法、month 1~12、
    指数区间 _INDEX_MIN~_INDEX_MAX）在此函数内完成，year_month 由校验后的
    整数构造，格式必然合法。
    """
    records: list[dict] = []
    reader = csv.DictReader(io.StringIO(text))
    for row in reader:
        city_en = (row.get("city") or "").strip()
        year_str = (row.get("year") or "").strip()
        month_str = (row.get("month") or "").strip()
        if not (city_en and year_str and month_str):
            continue
        try:
            year, month = int(year_str), int(month_str)
        except ValueError:
            continue
        if not 1 <= month <= 12:
            continue
        year_month = f"{year:04d}-{month:02d}"
        for column, dwelling_type in _DWELLING_COLUMNS.items():
            value_str = (row.get(column) or "").strip()
            if not value_str:
                continue
            try:
                value = float(value_str)
            except ValueError:
                continue
            if not _INDEX_MIN <= value <= _INDEX_MAX:
                continue
            records.append(
                {
                    "city_en": city_en,
                    "year_month": year_month,
                    "dwelling_type": dwelling_type,
                    "index_value": value,
                }
            )
    return records


async def import_index(session: AsyncSession) -> dict:
    """下载并导入 NBS 70 城月度环比指数到 price_index_snapshot，返回覆盖统计。

    幂等：upsert on 唯一键（region+month+口径+source），重跑覆盖同值不产生重复行。
    未匹配城市（不在 crosswalk 或 city 表无同名行）跳过并计入 skipped。
    """
    csv_path = await asyncio.to_thread(download_csv)
    records = parse_index_csv(csv_path.read_text(encoding="utf-8"))
    if not records:
        raise RuntimeError("NBS 指数 CSV 解析结果为空（源文件格式可能已变更）")

    name_to_id: dict[str, int] = dict(
        (await session.execute(select(City.name, City.id))).all()
    )

    # 唯一键内去重（防御源内重复行，后出现者为准），同时做城市名两级匹配
    rows_by_key: dict[tuple, dict] = {}
    matched_cities: set[str] = set()
    skipped: set[str] = set()
    for r in records:
        cn_name = NBS_CITY_NAME_MAP.get(r["city_en"])
        city_id = name_to_id.get(cn_name) if cn_name else None
        if city_id is None:
            skipped.add(r["city_en"])
            continue
        matched_cities.add(r["city_en"])
        key = ("city", city_id, r["year_month"], r["dwelling_type"], "mom")
        rows_by_key[key] = {
            "region_type": "city",
            "region_id": city_id,
            "year_month": r["year_month"],
            "dwelling_type": r["dwelling_type"],
            "base_type": "mom",
            "index_value": r["index_value"],
            "source": INDEX_SOURCE_TAG,
        }

    rows = list(rows_by_key.values())
    for start in range(0, len(rows), _UPSERT_CHUNK):
        chunk = rows[start : start + _UPSERT_CHUNK]
        stmt = insert(PriceIndexSnapshot).values(chunk)
        stmt = stmt.on_conflict_do_update(
            constraint="uq_price_index_region_month_kind_source",
            set_={"index_value": stmt.excluded.index_value},
        )
        await session.execute(stmt)
    await session.commit()

    if skipped:
        logger.info(
            "NBS 指数导入：%d 城名未匹配跳过: %s", len(skipped), "、".join(sorted(skipped))
        )

    months = [r["year_month"] for r in rows]
    return {
        "source": INDEX_SOURCE_TAG,
        "matched": len(matched_cities),
        "skipped": sorted(skipped),
        "rows": len(rows),
        "months_range": [min(months), max(months)] if months else None,
    }
