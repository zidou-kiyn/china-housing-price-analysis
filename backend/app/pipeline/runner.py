"""管线编排器：串联采集→清洗→入库→日志全流程。"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.collector.base import BaseSource, DataType, RawRecord, SourceRegistry
from app.collector.storage import save_raw
from app.core.cache import invalidate_api_caches, redis_client
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
from app.pipeline.snapshot_validator import validate_snapshot_records

logger = logging.getLogger(__name__)


class PipelineRunner:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        redis=None,
    ) -> None:
        self.session_factory = session_factory
        self.redis = redis if redis is not None else redis_client

    async def run(self, source_name: str, city_code: str) -> dict:
        """端到端执行单城市采集入库，返回统计摘要。"""
        source = SourceRegistry.get(source_name)
        stats = {
            "snapshots": 0,
            "distributions": 0,
            "logs": 0,
            "errors": [],
            # snapshot_validator 统计：rejected=值域/格式拦截，flagged=环比跳变标记
            "rejected": 0,
            "flagged": 0,
        }

        # ¥/㎡ 时序管线只适用于声明 PRICE_TIMELINE 的源；指数类源（如 govstats）走独立路径，
        # 直接拒绝以避免把指数值污染进 supply_price。
        if not source.supports(DataType.PRICE_TIMELINE):
            raise ValueError(
                f"数据源 {source_name} 不支持 ¥/㎡ 时序采集"
                f"（price_unit={getattr(source, 'price_unit', '?')}）；"
                "指数类源需专用入库管线，参见 govstats 任务文档"
            )

        # 按源能力自适应：不支持区县 / 分布的源跳过对应阶段，只跑城市级时序（最小能力）。
        supports_dist = source.supports(DataType.DISTRICTS)
        supports_distribution = source.supports(DataType.PRICE_DISTRIBUTION)

        async with self.session_factory() as session:
            async with session.begin():
                job = await create_crawl_job(session, source_name, city_code)

                try:
                    city_map, dist_map, dist_list = await self._load_dimensions(
                        session, source, city_code, job.id, with_districts=supports_dist
                    )
                    stats["logs"] += 1

                    city_id = city_map.get(city_code)
                    if city_id is None:
                        raise ValueError(f"城市 {city_code} 不在数据源城市列表中")

                    n, rejected, flagged = await self._load_city_timeline(
                        session, source, city_code, city_id, job.id
                    )
                    stats["snapshots"] += n
                    stats["rejected"] += rejected
                    stats["flagged"] += flagged
                    stats["logs"] += 1

                    if supports_dist:
                        for dist in dist_list:
                            dist_id = dist_map.get(dist.code)
                            if dist_id is None:
                                continue
                            n, rejected, flagged = await self._load_district_timeline(
                                session, source, city_code, dist.code, dist_id, job.id
                            )
                            stats["snapshots"] += n
                            stats["rejected"] += rejected
                            stats["flagged"] += flagged
                            stats["logs"] += 1

                    if supports_distribution:
                        n = await self._load_city_distribution(
                            session, source, city_code, city_id, job.id
                        )
                        stats["distributions"] += n
                        stats["logs"] += 1

                        if supports_dist:
                            for dist in dist_list:
                                dist_id = dist_map.get(dist.code)
                                if dist_id is None:
                                    continue
                                n = await self._load_district_distribution(
                                    session, source, city_code, dist.code, dist_id, job.id
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
        self,
        session: AsyncSession,
        source: BaseSource,
        city_code: str,
        job_id: int,
        with_districts: bool = True,
    ):
        """获取城市（可选区县）列表并 upsert，返回 (city_map, dist_map, dist_list)。

        with_districts=False（源不支持区县）时跳过 fetch_districts，返回空区县。
        """
        t0 = time.perf_counter()
        base = getattr(source, "base_url", "") or source.source_name
        try:
            cities = await asyncio.to_thread(source.fetch_cities)
            if with_districts:
                city_districts = await asyncio.to_thread(source.fetch_districts, city_code)
            else:
                city_districts = []

            city_map = await upsert_cities(session, cities)
            dist_map = await upsert_districts(session, city_districts, city_map)

            elapsed = int((time.perf_counter() - t0) * 1000)
            await create_crawl_log(
                session,
                job_id=job_id,
                url=f"{base}/city/{city_code}.html",
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
                url=f"{base}/rank/citySel.html",
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
        district_code: str | None = None,
    ) -> RawRecord:
        """调用采集方法并记录 crawl_log，返回 RawRecord。"""
        t0 = time.perf_counter()
        try:
            raw: RawRecord = await asyncio.to_thread(fetch_fn, *args)
            elapsed = int((time.perf_counter() - t0) * 1000)

            raw_path = save_raw(
                raw.source, raw.city_code, raw.records, raw.data_type,
                district_code=district_code,
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
    ) -> tuple[int, int, int]:
        raw = await self._fetch_and_log(
            session, job_id, source.fetch_price_timeline, city_code, "allsq1"
        )
        vr = validate_snapshot_records(clean_price_timeline(raw.records))
        n = await upsert_price_snapshots(
            session, vr.accepted, "city", city_id, source=source.source_name
        )
        return n, len(vr.rejected), len(vr.flagged)

    async def _load_district_timeline(
        self, session, source, city_code, dist_code, dist_id, job_id
    ) -> tuple[int, int, int]:
        raw = await self._fetch_and_log(
            session, job_id, source.fetch_price_timeline, city_code, dist_code,
            district_code=dist_code,
        )
        vr = validate_snapshot_records(clean_price_timeline(raw.records))
        n = await upsert_price_snapshots(
            session, vr.accepted, "district", dist_id, source=source.source_name
        )
        return n, len(vr.rejected), len(vr.flagged)

    async def _load_city_distribution(
        self, session, source, city_code, city_id, job_id
    ) -> int:
        raw = await self._fetch_and_log(
            session, job_id, source.fetch_price_distribution, city_code, "allsq1"
        )
        year_month = datetime.now().strftime("%Y-%m")
        cleaned = clean_price_distribution(raw.records, year_month)
        return await upsert_price_distributions(session, cleaned, "city", city_id)

    async def _load_district_distribution(
        self, session, source, city_code, dist_code, dist_id, job_id
    ) -> int:
        raw = await self._fetch_and_log(
            session, job_id, source.fetch_price_distribution, city_code, dist_code,
            district_code=dist_code,
        )
        year_month = datetime.now().strftime("%Y-%m")
        cleaned = clean_price_distribution(raw.records, year_month)
        return await upsert_price_distributions(session, cleaned, "district", dist_id)

    async def _invalidate_cache(self, city_code: str) -> None:
        try:
            deleted = await invalidate_api_caches(self.redis, city_code)
            if deleted:
                logger.info("已清除 %d 个缓存 key", deleted)
        except Exception:
            logger.warning("Redis 缓存清除失败，不影响入库结果", exc_info=True)
