"""管线编排器：串联采集→清洗→入库→日志全流程。"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.collector.base import BaseSource, RawRecord, SourceRegistry
from app.collector.storage import save_raw
from app.pipeline.cleaners import clean_price_distribution, clean_price_timeline
from app.pipeline.loaders import (
    create_crawl_job,
    create_crawl_log,
    finish_crawl_job,
    upsert_cities,
    upsert_districts,
    upsert_price_distributions,
    upsert_price_snapshots,
)

logger = logging.getLogger(__name__)


class PipelineRunner:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis=None,
    ) -> None:
        self.session_factory = session_factory
        self.redis = redis

    async def run(self, source_name: str, city_code: str) -> dict:
        """端到端执行单城市采集入库，返回统计摘要。"""
        source = SourceRegistry.get(source_name)
        stats = {"snapshots": 0, "distributions": 0, "logs": 0, "errors": []}

        async with self.session_factory() as session:
            async with session.begin():
                job = await create_crawl_job(session, source_name, city_code)

                try:
                    city_map, dist_map, dist_list = await self._load_dimensions(
                        session, source, city_code, job.id
                    )
                    stats["logs"] += 1

                    city_id = city_map.get(city_code)
                    if city_id is None:
                        raise ValueError(f"城市 {city_code} 不在数据源城市列表中")

                    n = await self._load_city_timeline(
                        session, source, city_code, city_id, job.id
                    )
                    stats["snapshots"] += n
                    stats["logs"] += 1

                    for dist in dist_list:
                        dist_id = dist_map.get(dist.code)
                        if dist_id is None:
                            continue
                        n = await self._load_district_timeline(
                            session, source, city_code, dist.code, dist_id, job.id
                        )
                        stats["snapshots"] += n
                        stats["logs"] += 1

                    n = await self._load_city_distribution(
                        session, source, city_code, city_id, job.id
                    )
                    stats["distributions"] += n
                    stats["logs"] += 1

                    await finish_crawl_job(session, job, success=True)

                except Exception as exc:
                    stats["errors"].append(str(exc))
                    await finish_crawl_job(session, job, success=False)
                    raise

        await self._invalidate_cache(city_code)

        logger.info(
            "管线完成: source=%s city=%s snapshots=%d distributions=%d logs=%d",
            source_name, city_code, stats["snapshots"], stats["distributions"], stats["logs"],
        )
        return stats

    async def _load_dimensions(
        self, session: AsyncSession, source: BaseSource, city_code: str, job_id: int
    ):
        """获取城市/区县列表并 upsert，返回 (city_map, dist_map, dist_list)。"""
        t0 = time.perf_counter()
        try:
            cities = await asyncio.to_thread(source.fetch_cities)
            districts = await asyncio.to_thread(source.fetch_districts)

            city_map = await upsert_cities(session, cities)

            city_districts = [d for d in districts if d.city_code == city_code]
            dist_map = await upsert_districts(session, city_districts, city_map)

            elapsed = int((time.perf_counter() - t0) * 1000)
            await create_crawl_log(
                session,
                job_id=job_id,
                url=f"{source.BASE_URL}/rank/citySel.html",
                success=True,
                status_code=200,
                record_count=len(cities) + len(city_districts),
                elapsed_ms=elapsed,
            )
            return city_map, dist_map, city_districts
        except Exception as exc:
            elapsed = int((time.perf_counter() - t0) * 1000)
            await create_crawl_log(
                session,
                job_id=job_id,
                url=f"{source.BASE_URL}/rank/citySel.html",
                success=False,
                error_message=str(exc),
                elapsed_ms=elapsed,
            )
            raise

    async def _fetch_and_log(
        self,
        session: AsyncSession,
        job_id: int,
        fetch_fn,
        *args,
    ) -> RawRecord:
        """调用采集方法并记录 crawl_log，返回 RawRecord。"""
        t0 = time.perf_counter()
        try:
            raw: RawRecord = await asyncio.to_thread(fetch_fn, *args)
            elapsed = int((time.perf_counter() - t0) * 1000)

            raw_path = save_raw(
                raw.source, raw.city_code, raw.records, raw.data_type
            )

            await create_crawl_log(
                session,
                job_id=job_id,
                url=raw.raw_url,
                success=True,
                status_code=200,
                raw_path=raw_path,
                record_count=len(raw.records),
                elapsed_ms=elapsed,
            )
            return raw
        except Exception as exc:
            elapsed = int((time.perf_counter() - t0) * 1000)
            await create_crawl_log(
                session,
                job_id=job_id,
                url="unknown",
                success=False,
                error_message=str(exc),
                elapsed_ms=elapsed,
            )
            raise

    async def _load_city_timeline(
        self, session, source, city_code, city_id, job_id
    ) -> int:
        raw = await self._fetch_and_log(
            session, job_id, source.fetch_price_timeline, city_code, "allsq1"
        )
        cleaned = clean_price_timeline(raw.records)
        return await upsert_price_snapshots(session, cleaned, "city", city_id)

    async def _load_district_timeline(
        self, session, source, city_code, dist_code, dist_id, job_id
    ) -> int:
        raw = await self._fetch_and_log(
            session, job_id, source.fetch_price_timeline, city_code, dist_code
        )
        cleaned = clean_price_timeline(raw.records)
        return await upsert_price_snapshots(session, cleaned, "district", dist_id)

    async def _load_city_distribution(
        self, session, source, city_code, city_id, job_id
    ) -> int:
        raw = await self._fetch_and_log(
            session, job_id, source.fetch_price_distribution, city_code, "allsq1"
        )
        year_month = datetime.now().strftime("%Y-%m")
        cleaned = clean_price_distribution(raw.records, year_month)
        return await upsert_price_distributions(session, cleaned, "city", city_id)

    async def _invalidate_cache(self, city_code: str) -> None:
        if self.redis is None:
            return
        try:
            keys = []
            async for key in self.redis.scan_iter(f"price:{city_code}:*"):
                keys.append(key)
            async for key in self.redis.scan_iter(f"trend:{city_code}:*"):
                keys.append(key)
            if keys:
                await self.redis.delete(*keys)
                logger.info("已清除 %d 个缓存 key", len(keys))
        except Exception:
            logger.warning("Redis 缓存清除失败，不影响入库结果", exc_info=True)
