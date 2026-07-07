"""补齐城市地图 GeoJSON（薄 CLI，核心逻辑在 app.services.geo）。

用法：
    uv run python scripts/fetch_geo.py              # 补齐所有已采集城市（有 district 数据）的缺图
    uv run python scripts/fetch_geo.py fz xm        # 指定城市（creprice 代码）
    uv run python scripts/fetch_geo.py nn=450100    # 显式指定国标 adcode（写入 city.adcode 后下载）

文件落盘到仓库根 data/geo/（容器内 /data/geo），经 GET /api/v1/geo/{code} 提供给前端，
无需重新构建前端镜像。日常操作建议直接使用管理端「数据管理」页触发。
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.models.city import City
from app.models.district import District
from app.services import geo


async def main() -> int:
    if any(arg.startswith("-") for arg in sys.argv[1:]):
        print(__doc__)
        return 0

    explicit_adcodes: dict[str, str] = {}
    targets: list[str] = []
    for arg in sys.argv[1:]:
        code, _, adcode = arg.partition("=")
        targets.append(code)
        if adcode:
            explicit_adcodes[code] = adcode

    engine = create_async_engine(settings.database_url)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    failed: list[str] = []
    try:
        async with session_factory() as session, httpx.AsyncClient(timeout=30) as client:
            if not targets:
                collected = select(District.city_id).distinct()
                rows = await session.scalars(
                    select(City.code).where(City.id.in_(collected)).order_by(City.id)
                )
                available = geo.list_available()
                targets = [c for c in rows.all() if c not in available]
                if not targets:
                    print("所有已采集城市均已有地图文件，无需补图")
                    return 0

            cities = {
                c.code: c
                for c in (
                    await session.scalars(select(City).where(City.code.in_(targets)))
                ).all()
            }

            # 显式 adcode 先写库
            for code, adcode in explicit_adcodes.items():
                if code in cities:
                    cities[code].adcode = adcode
            if explicit_adcodes:
                await session.commit()

            if any(c in cities and cities[c].adcode is None for c in targets):
                print("存在缺 adcode 的城市，构建全国索引回填（约 35 次请求）…")
                await geo.backfill_adcodes(session, client)
                cities = {
                    c.code: c
                    for c in (
                        await session.scalars(select(City).where(City.code.in_(targets)))
                    ).all()
                }

            for code in targets:
                city = cities.get(code)
                label = f"{city.name}({code})" if city else code
                print(f"== 补图 {label} ==")
                try:
                    if city is None:
                        raise ValueError(f"city 表中无代码 {code}")
                    summary = await geo.fetch_city_geo(client, city)
                    print(f"已写入 {geo.geo_path(code)}（{summary['districts']} 个区县）")
                except Exception as exc:
                    print(f"失败: {exc}")
                    failed.append(code)
                await asyncio.sleep(geo.REQUEST_INTERVAL)
    finally:
        await engine.dispose()

    if failed:
        print(f"\n失败城市: {', '.join(failed)}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
