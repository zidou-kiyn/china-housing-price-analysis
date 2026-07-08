"""采集任务体：手动与定时路径共用的逐城市 pipeline 执行循环。

手动路径（admin_collect）不带节流与熔断，保持既有行为；
定时路径（collect_scheduler）传入 inter_city_delay / max_consecutive_failures
以在机房 IP 间歇限流（连续 SSL EOF/502）下细水长流、不轰炸源站。
"""

from __future__ import annotations

import asyncio
import random

from app.core.database import async_session_factory
from app.pipeline.runner import PipelineRunner
from app.services import job_runner


async def _pause_between_cities(delay_range: tuple[float, float]) -> None:
    """城市间随机间隔（独立函数便于测试打桩）。"""
    await asyncio.sleep(random.uniform(*delay_range))


async def run_collect(
    job_id: int,
    city_codes: list[str],
    source_name: str,
    *,
    inter_city_delay: tuple[float, float] | None = None,
    max_consecutive_failures: int | None = None,
    runner: PipelineRunner | None = None,
) -> dict:
    """逐城市执行完整 pipeline，单城失败不中断（除非触发熔断），进度写入 job。

    - inter_city_delay: (min, max) 秒，城市之间随机 sleep；None = 不等待（手动路径）。
    - max_consecutive_failures: 连续失败 N 城即熔断本批（限流强信号），
      剩余城市记入 skipped 留给下一批；None = 不熔断（手动路径）。
    返回 {"results": [...], "circuit_broken": bool, "skipped": [...]}，
    results 元素结构与既有手动采集 job result 完全一致。
    """
    runner = runner or PipelineRunner(async_session_factory)
    results: list[dict] = []
    skipped: list[str] = []
    circuit_broken = False
    consecutive_failures = 0

    for i, code in enumerate(city_codes, start=1):
        try:
            stats = await runner.run(source_name, code)
            results.append(
                {
                    "city": code,
                    "ok": True,
                    "snapshots": stats["snapshots"],
                    "distributions": stats["distributions"],
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
            # 连续失败是限流的强信号：终止本批，剩余城市留给下一次调度
            circuit_broken = True
            skipped = list(city_codes[i:])
            break

        if inter_city_delay is not None and i < len(city_codes):
            await _pause_between_cities(inter_city_delay)

    return {"results": results, "circuit_broken": circuit_broken, "skipped": skipped}
