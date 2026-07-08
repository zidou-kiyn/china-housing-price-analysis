"""采集任务体：手动与定时路径共用的逐城市 pipeline 执行循环。

手动路径（admin_collect）支持并发采集（CRAWL_CONCURRENCY 控制并发度）；
定时路径（collect_scheduler）传入 inter_city_delay / max_consecutive_failures
保持串行以在机房 IP 间歇限流下细水长流、不轰炸源站。
"""

from __future__ import annotations

import asyncio
import logging
import random

from app.collector.base import SourceRegistry
from app.core.config import settings
from app.core.database import async_session_factory
from app.pipeline.loaders import upsert_cities
from app.pipeline.runner import PipelineRunner
from app.services import job_runner

logger = logging.getLogger(__name__)


async def _pause_between_cities(delay_range: tuple[float, float]) -> None:
    """城市间随机间隔（独立函数便于测试打桩）。"""
    await asyncio.sleep(random.uniform(*delay_range))


async def _prefetch_city_map(source_name: str) -> dict[str, int]:
    """采集前统一拉取一次全国城市列表并 upsert，返回 {code: id} 映射。"""
    source = SourceRegistry.get(source_name)
    cities = await asyncio.to_thread(source.fetch_cities)
    async with async_session_factory() as session:
        async with session.begin():
            city_map = await upsert_cities(session, cities)
    logger.info("预取城市列表完成: %d 个城市", len(city_map))
    return city_map


async def _run_city(
    sem: asyncio.Semaphore,
    runner: PipelineRunner,
    source_name: str,
    code: str,
    city_map: dict[str, int],
    job_id: int,
    progress: dict,
    lock: asyncio.Lock,
) -> dict:
    """单城市采集任务（受 semaphore 限流）。"""
    async with sem:
        try:
            stats = await runner.run(source_name, code, city_map=city_map)
            result = {
                "city": code,
                "ok": True,
                "snapshots": stats["snapshots"],
                "distributions": stats["distributions"],
                "rejected": stats.get("rejected", 0),
                "flagged": stats.get("flagged", 0),
            }
        except Exception as exc:
            result = {"city": code, "ok": False, "error": str(exc)[:500]}

        async with lock:
            progress["done"] += 1
            progress["results"].append(result)
            await job_runner.report_progress(
                job_id, progress["done"], result=progress["results"]
            )
        return result


async def run_collect(
    job_id: int,
    city_codes: list[str],
    source_name: str,
    *,
    inter_city_delay: tuple[float, float] | None = None,
    max_consecutive_failures: int | None = None,
    runner: PipelineRunner | None = None,
) -> dict:
    """执行完整 pipeline，返回汇总。

    手动路径（inter_city_delay=None）：并发采集，CRAWL_CONCURRENCY 控制并发度。
    定时路径（inter_city_delay 有值）：保持串行 + 熔断逻辑。
    """
    runner = runner or PipelineRunner(async_session_factory)

    city_map = await _prefetch_city_map(source_name)

    use_serial = inter_city_delay is not None or max_consecutive_failures is not None

    if use_serial:
        return await _run_serial(
            job_id, city_codes, source_name, runner, city_map,
            inter_city_delay=inter_city_delay,
            max_consecutive_failures=max_consecutive_failures,
        )

    return await _run_concurrent(job_id, city_codes, source_name, runner, city_map)


async def _run_concurrent(
    job_id: int,
    city_codes: list[str],
    source_name: str,
    runner: PipelineRunner,
    city_map: dict[str, int],
) -> dict:
    """并发采集模式。"""
    sem = asyncio.Semaphore(settings.crawl_concurrency)
    lock = asyncio.Lock()
    progress = {"done": 0, "results": []}

    tasks = [
        _run_city(sem, runner, source_name, code, city_map, job_id, progress, lock)
        for code in city_codes
    ]
    await asyncio.gather(*tasks)

    return {
        "results": progress["results"],
        "circuit_broken": False,
        "skipped": [],
    }


async def _run_serial(
    job_id: int,
    city_codes: list[str],
    source_name: str,
    runner: PipelineRunner,
    city_map: dict[str, int],
    *,
    inter_city_delay: tuple[float, float] | None = None,
    max_consecutive_failures: int | None = None,
) -> dict:
    """串行采集模式（定时路径，保留熔断逻辑）。"""
    results: list[dict] = []
    skipped: list[str] = []
    circuit_broken = False
    consecutive_failures = 0

    for i, code in enumerate(city_codes, start=1):
        try:
            stats = await runner.run(source_name, code, city_map=city_map)
            results.append(
                {
                    "city": code,
                    "ok": True,
                    "snapshots": stats["snapshots"],
                    "distributions": stats["distributions"],
                    "rejected": stats.get("rejected", 0),
                    "flagged": stats.get("flagged", 0),
                }
            )
            consecutive_failures = 0
        except Exception as exc:
            results.append({"city": code, "ok": False, "error": str(exc)[:500]})
            consecutive_failures += 1

        await job_runner.report_progress(job_id, i, result=results)

        if (
            max_consecutive_failures is not None
            and consecutive_failures >= max_consecutive_failures
        ):
            circuit_broken = True
            skipped = list(city_codes[i:])
            break

        if inter_city_delay is not None and i < len(city_codes):
            await _pause_between_cities(inter_city_delay)

    return {"results": results, "circuit_broken": circuit_broken, "skipped": skipped}
