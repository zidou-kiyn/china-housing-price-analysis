"""启动时种子数据加载：city 表为空则从 seed/cities.json 导入。"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from sqlalchemy import func, insert, select

from app.core.database import async_session_factory
from app.models.city import City

logger = logging.getLogger(__name__)

_SEED_FILE = Path(__file__).resolve().parent.parent.parent / "seed" / "cities.json"


async def seed_cities_if_empty() -> None:
    async with async_session_factory() as session:
        count = await session.scalar(select(func.count()).select_from(City))
        if count:
            return

        if not _SEED_FILE.exists():
            logger.warning("Seed file not found: %s", _SEED_FILE)
            return

        cities = json.loads(_SEED_FILE.read_text(encoding="utf-8"))
        await session.execute(
            insert(City),
            [
                {
                    "name": c["name"],
                    "code": c["code"],
                    "province": c.get("province"),
                    "adcode": c.get("adcode"),
                }
                for c in cities
            ],
        )
        await session.commit()
        logger.info("Seeded %d cities from %s", len(cities), _SEED_FILE.name)
