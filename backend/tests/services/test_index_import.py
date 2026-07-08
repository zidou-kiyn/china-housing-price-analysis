"""index_import 指数导入单测：真实 DB + 小 fixture CSV（monkeypatch 下载与 crosswalk）。"""

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

import app.services.index_import as mod
from app.core.database import async_session_factory
from app.models.city import City
from app.models.price_index_snapshot import PriceIndexSnapshot
from app.services.index_import import import_index, parse_index_csv

pytestmark = pytest.mark.asyncio(loop_scope="session")

_CITY = {"name": "单测指数城", "code": "t_idx1", "province": "单测省"}

# Testville → 单测指数城（可匹配）；Ghostville 在 crosswalk 但 city 表无同名行；
# Nowhere 不在 crosswalk —— 两类未匹配都应跳过并报告
_FIXTURE_MAP = {"Testville": "单测指数城", "Ghostville": "单测幽灵城"}

_FIXTURE_CSV = (
    "city,year,month,new_home_price_index,existing_home_price_index,"
    "new_small_home_index,new_medium_home_index,new_large_home_index,"
    "existing_small_home_index,existing_medium_home_index,existing_large_home_index\n"
    "Testville,2021,1,101.1,100.5,102.1,101.4,100.4,100.7,100.2,100.4\n"
    "Testville,2021,2,99.8,,100.0,99.9,99.7,99.8,99.9,\n"  # 二手缺值：只导新建
    "Ghostville,2021,1,100.6,100.3,101.3,100.3,99.6,100.5,100.0,100.1\n"
    "Nowhere,2021,1,100.2,100.1,100.2,100.2,100.7,100.2,101.0,101.0\n"
    "Testville,2021,13,100.0,100.0,,,,,,\n"  # 非法月份：跳过
    "Testville,2021,3,999.0,100.9,,,,,,\n"  # 新建超合理区间：只导二手
)


@pytest_asyncio.fixture(loop_scope="session")
async def seeded_city():
    """seed 一个测试城市，结束后清掉城市与其指数行。"""
    async with async_session_factory() as s:
        city = City(**_CITY)
        s.add(city)
        await s.commit()
        city_id = city.id
    yield city_id
    async with async_session_factory() as s:
        await s.execute(
            delete(PriceIndexSnapshot).where(
                PriceIndexSnapshot.region_type == "city",
                PriceIndexSnapshot.region_id == city_id,
            )
        )
        await s.execute(delete(City).where(City.id == city_id))
        await s.commit()


@pytest.fixture
def fake_download(tmp_path, monkeypatch):
    csv_path = tmp_path / "nbs_index.csv"
    csv_path.write_text(_FIXTURE_CSV, encoding="utf-8")
    monkeypatch.setattr(mod, "download_csv", lambda cache_dir=None: csv_path)
    monkeypatch.setattr(mod, "NBS_CITY_NAME_MAP", _FIXTURE_MAP)


async def _index_rows(city_id: int) -> list[PriceIndexSnapshot]:
    async with async_session_factory() as s:
        return list(
            (
                await s.execute(
                    select(PriceIndexSnapshot)
                    .where(
                        PriceIndexSnapshot.region_type == "city",
                        PriceIndexSnapshot.region_id == city_id,
                    )
                    .order_by(
                        PriceIndexSnapshot.year_month, PriceIndexSnapshot.dwelling_type
                    )
                )
            ).scalars()
        )


async def test_parse_splits_dwelling_types_and_skips_bad_rows():
    records = parse_index_csv(_FIXTURE_CSV)

    keys = {(r["city_en"], r["year_month"], r["dwelling_type"]) for r in records}
    # Testville 2021-01 两口径；2021-02 只有新建；2021-03 只有二手（新建 999 出界）
    assert ("Testville", "2021-01", "new") in keys
    assert ("Testville", "2021-01", "second") in keys
    assert ("Testville", "2021-02", "new") in keys
    assert ("Testville", "2021-02", "second") not in keys
    assert ("Testville", "2021-03", "new") not in keys
    assert ("Testville", "2021-03", "second") in keys
    assert not any(r["year_month"] == "2021-13" for r in records)  # 非法月份

    by_key = {(r["city_en"], r["year_month"], r["dwelling_type"]): r for r in records}
    assert by_key[("Testville", "2021-01", "new")]["index_value"] == pytest.approx(101.1)
    assert by_key[("Testville", "2021-01", "second")]["index_value"] == pytest.approx(100.5)


async def test_import_matches_and_skips(seeded_city, fake_download):
    async with async_session_factory() as s:
        stats = await import_index(s)

    assert stats["source"] == "nbs_github_changao1"
    assert stats["matched"] == 1
    # Ghostville（crosswalk 有、city 表无）与 Nowhere（crosswalk 无）都跳过
    assert stats["skipped"] == ["Ghostville", "Nowhere"]
    assert stats["rows"] == 4  # 2021-01 双口径 + 2021-02 new + 2021-03 second
    assert stats["months_range"] == ["2021-01", "2021-03"]

    rows = await _index_rows(seeded_city)
    assert [(r.year_month, r.dwelling_type, r.index_value) for r in rows] == [
        ("2021-01", "new", 101.1),
        ("2021-01", "second", 100.5),
        ("2021-02", "new", 99.8),
        ("2021-03", "second", 100.9),
    ]
    assert all(
        r.base_type == "mom" and r.source == "nbs_github_changao1" for r in rows
    )


async def test_import_idempotent(seeded_city, fake_download):
    async with async_session_factory() as s:
        await import_index(s)
    async with async_session_factory() as s:
        stats2 = await import_index(s)

    assert stats2["rows"] == 4
    rows = await _index_rows(seeded_city)
    assert len(rows) == 4  # 重跑覆盖同值，不产生重复行


async def test_import_empty_csv_raises(seeded_city, tmp_path, monkeypatch):
    """解析结果为空（源格式变更/空文件）→ 显式报错，不静默空导入。"""
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("city,year,month\n", encoding="utf-8")
    monkeypatch.setattr(mod, "download_csv", lambda cache_dir=None: csv_path)

    async with async_session_factory() as s:
        with pytest.raises(RuntimeError, match="解析结果为空"):
            await import_index(s)
