"""nationwide_import 批量导入单测：真实 DB + 小 fixture CSV（monkeypatch 下载，不打网络）。"""

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

import app.services.nationwide_import as mod
from app.core.database import async_session_factory
from app.models.city import City
from app.models.price_snapshot import PriceSnapshot
from app.services.nationwide_import import import_annual

pytestmark = pytest.mark.asyncio(loop_scope="session")

_CITY_A = {"name": "单测导入城甲", "code": "t_na1", "province": "单测省"}
_CITY_B = {"name": "单测导入城乙", "code": "t_na2", "province": "单测省"}

_FIXTURE_CSV = (
    "province,city,year,price_yuan_per_sqm,yoy_pct\n"
    "单测省,单测导入城甲,2019,8000,\n"
    "单测省,单测导入城甲,2020,8800,10.0\n"
    "单测省,单测导入城乙,2020,12000,\n"
    "单测省,单测不存在城,2020,5000,\n"
)


@pytest_asyncio.fixture(loop_scope="session")
async def seeded_cities():
    """seed 两个测试城市，结束后清掉城市与其快照。"""
    async with async_session_factory() as s:
        cities = [City(**_CITY_A), City(**_CITY_B)]
        s.add_all(cities)
        await s.commit()
        ids = [c.id for c in cities]
    yield dict(zip([_CITY_A["name"], _CITY_B["name"]], ids))
    async with async_session_factory() as s:
        await s.execute(
            delete(PriceSnapshot).where(
                PriceSnapshot.region_type == "city",
                PriceSnapshot.region_id.in_(ids),
            )
        )
        await s.execute(delete(City).where(City.id.in_(ids)))
        await s.commit()


@pytest.fixture
def fake_download(tmp_path, monkeypatch):
    csv_path = tmp_path / "annual.csv"
    csv_path.write_text(_FIXTURE_CSV, encoding="utf-8")
    monkeypatch.setattr(mod, "download_csv", lambda source_key: csv_path)


async def _snapshot_rows(city_ids: list[int]) -> list[PriceSnapshot]:
    async with async_session_factory() as s:
        return list(
            (
                await s.execute(
                    select(PriceSnapshot)
                    .where(
                        PriceSnapshot.region_type == "city",
                        PriceSnapshot.region_id.in_(city_ids),
                    )
                    .order_by(PriceSnapshot.region_id, PriceSnapshot.year_month)
                )
            ).scalars()
        )


async def test_import_matches_and_skips(seeded_cities, fake_download):
    async with async_session_factory() as s:
        stats = await import_annual(s, "58")

    assert stats["source"] == "listing_annual_58"
    assert stats["matched"] == 2
    assert stats["skipped"] == ["单测不存在城"]
    assert stats["snapshots"] == 3

    rows = await _snapshot_rows(list(seeded_cities.values()))
    assert len(rows) == 3
    a_rows = [r for r in rows if r.region_id == seeded_cities[_CITY_A["name"]]]
    assert [(r.year_month, int(r.supply_price)) for r in a_rows] == [
        ("2019-12", 8000),
        ("2020-12", 8800),
    ]
    assert all(r.source == "listing_annual_58" and r.sample_count is None for r in rows)


async def test_import_idempotent(seeded_cities, fake_download):
    async with async_session_factory() as s:
        await import_annual(s, "58")
    async with async_session_factory() as s:
        stats2 = await import_annual(s, "58")

    assert stats2["matched"] == 2
    rows = await _snapshot_rows(list(seeded_cities.values()))
    assert len(rows) == 3  # 重跑覆盖同值，不产生重复行


async def test_import_unknown_source_raises(fake_download):
    async with async_session_factory() as s:
        with pytest.raises(ValueError, match="未知年度房价源"):
            await import_annual(s, "nope")
