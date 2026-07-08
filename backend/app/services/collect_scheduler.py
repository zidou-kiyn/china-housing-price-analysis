"""creprice 定时采集调度器：进程内 asyncio 循环，每日按配置自动采集一批城市。

设计（.trellis/tasks/07-08-creprice-scheduler/design.md）：
- 不引入 APScheduler/celery：60s 醒一次的单循环足够；每次醒来重读 settings KV，
  开关/时刻/批次改动即时生效，无需重启。
- 当日去重用 KV 原子抢占（INSERT .. ON CONFLICT DO UPDATE .. WHERE
  last_run_date IS DISTINCT FROM today）：compose 单容器但 prod uvicorn
  --workers 2，每个 worker 各持一个调度循环，抢占保证每日恰好一批；
  若未来多容器副本，需真正的分布式锁——本轮不做。
- 时刻按容器本地时区判定（当前部署容器为 UTC，前端设置项已注明）。
- 限流保护在任务体（collect_tasks.run_collect 的节流/熔断参数），手动采集不受影响。
- 循环内任何异常都被捕获并写入 state，绝不拖垮应用启动/关闭。
"""

from __future__ import annotations

import asyncio
import logging
import re
from contextlib import suppress
from datetime import datetime
from datetime import time as dtime

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import async_session_factory
from app.core.errors import ApiError
from app.models.app_setting import AppSetting
from app.models.city import City
from app.models.price_snapshot import PriceSnapshot
from app.services import job_runner
from app.services.app_settings import (
    COLLECT_SCHEDULE_STATE_KEY,
    get_collect_schedule,
    get_setting,
)
from app.services.collect_tasks import run_collect

logger = logging.getLogger(__name__)

# 调度器只服务 creprice 月度序列（PRD R2 按 creprice 覆盖选目标），
# 不跟随可切换的默认采集源——切到指数/导入类源不应改变定时批次语义。
SCHEDULE_SOURCE = "creprice"
SCHEDULE_INTER_CITY_DELAY = (10.0, 20.0)  # 城市间随机间隔秒数（限流保护）
SCHEDULE_MAX_CONSECUTIVE_FAILURES = 3  # 连续失败熔断阈值（限流表现为连续 SSL EOF/502）
WAKE_INTERVAL_SECONDS = 60.0  # 调度循环醒来间隔


def _parse_hhmm(value: str) -> dtime | None:
    """解析 "HH:MM"；格式非法返回 None（调度器跳过而非抛错）。"""
    m = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", value)
    if not m:
        return None
    return dtime(int(m.group(1)), int(m.group(2)))


async def _merge_state(patch: dict) -> None:
    """读改写合并调度状态（行锁串行化，与原子抢占互斥）；值为 None 的键被删除。"""
    async with async_session_factory() as session:
        row = await session.get(
            AppSetting, COLLECT_SCHEDULE_STATE_KEY, with_for_update=True
        )
        merged = {**(row.value if row else {}), **patch}
        merged = {k: v for k, v in merged.items() if v is not None}
        if row is None:
            session.add(AppSetting(key=COLLECT_SCHEDULE_STATE_KEY, value=merged))
        else:
            row.value = merged
        await session.commit()


async def _claim_today(session: AsyncSession, state: dict, today: str) -> bool:
    """原子抢占"今日已跑"标记：多 worker 并发醒来时恰好一个成功（返回 True）。"""
    stmt = insert(AppSetting).values(key=COLLECT_SCHEDULE_STATE_KEY, value=state)
    stmt = stmt.on_conflict_do_update(
        index_elements=["key"],
        set_={"value": stmt.excluded.value},
        where=AppSetting.value["last_run_date"].as_string().is_distinct_from(today),
    )
    result = await session.execute(stmt)
    await session.commit()
    return bool(result.rowcount)


async def _pick_targets(
    session: AsyncSession, batch: int, cursor: int | None
) -> tuple[list[str], list[tuple[int, str]]]:
    """选出本批目标：续采优先 + 扩展补位（PRD R2）。

    - 续采：有 creprice 城市快照但缺当前月的城市，max(year_month) 最旧优先；
    - 扩展：无任何 creprice 城市快照的城市，按 city.id 升序，从游标之后
      继续，扫完回绕（游标城市本身回绕后排最末）。
    返回 (续采 code 列表, 扩展 [(city_id, code), ...])，合计不超过 batch。
    """
    current_month = datetime.now().strftime("%Y-%m")

    latest = (
        select(
            PriceSnapshot.region_id,
            func.max(PriceSnapshot.year_month).label("latest"),
        )
        .where(
            PriceSnapshot.region_type == "city",
            PriceSnapshot.source == SCHEDULE_SOURCE,
        )
        .group_by(PriceSnapshot.region_id)
        .subquery()
    )
    resume_codes = list(
        (
            await session.execute(
                select(City.code)
                .join(latest, latest.c.region_id == City.id)
                .where(latest.c.latest < current_month)
                .order_by(latest.c.latest.asc(), City.id.asc())
                .limit(batch)
            )
        ).scalars()
    )

    remaining = batch - len(resume_codes)
    expand_items: list[tuple[int, str]] = []
    if remaining > 0:
        covered = (
            select(PriceSnapshot.region_id)
            .where(
                PriceSnapshot.region_type == "city",
                PriceSnapshot.source == SCHEDULE_SOURCE,
            )
            .distinct()
        )
        base = select(City.id, City.code).where(City.id.not_in(covered))
        rows = (
            await session.execute(
                base.where(City.id > (cursor or 0)).order_by(City.id).limit(remaining)
            )
        ).all()
        expand_items = [(cid, code) for cid, code in rows]
        wrap_needed = remaining - len(expand_items)
        if wrap_needed > 0 and cursor:
            rows = (
                await session.execute(
                    base.where(City.id <= cursor).order_by(City.id).limit(wrap_needed)
                )
            ).all()
            expand_items += [(cid, code) for cid, code in rows]
    return resume_codes, expand_items


async def _run_scheduled_collect(
    job_id: int, resume_codes: list[str], expand_items: list[tuple[int, str]]
) -> None:
    """定时批次任务体：带节流+熔断执行，结束后把摘要与扩展游标写回 state。"""
    codes = resume_codes + [code for _, code in expand_items]
    summary = await run_collect(
        job_id,
        codes,
        SCHEDULE_SOURCE,
        inter_city_delay=SCHEDULE_INTER_CITY_DELAY,
        max_consecutive_failures=SCHEDULE_MAX_CONSECUTIVE_FAILURES,
    )
    results = summary["results"]
    patch: dict = {
        "last_result": {
            "submitted": len(codes),
            "ok": sum(1 for r in results if r["ok"]),
            "failed": sum(1 for r in results if not r["ok"]),
            "circuit_broken": summary["circuit_broken"],
            "skipped": summary["skipped"],
        }
    }
    # 游标只越过"实际尝试过"的扩展城市；熔断跳过的留给下一批继续
    attempted = {r["city"] for r in results}
    attempted_expand = [cid for cid, code in expand_items if code in attempted]
    if attempted_expand:
        patch["expand_cursor"] = attempted_expand[-1]
    await _merge_state(patch)

    if results and not any(r["ok"] for r in results):
        raise RuntimeError(f"定时批次全部 {len(results)} 个城市采集失败")


class CollectScheduler:
    """FastAPI lifespan 内启动/停止的后台调度循环。"""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._task = asyncio.create_task(self._loop(), name="collect_scheduler")
        logger.info("定时采集调度器已启动（每 %.0fs 检查一次配置）", WAKE_INTERVAL_SECONDS)

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None

    async def _loop(self) -> None:
        while True:
            try:
                await self._tick(datetime.now())
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.exception("定时采集调度检查失败")
                with suppress(Exception):  # state 写入再失败也不能让循环挂掉
                    await _merge_state(
                        {"last_error": f"{type(exc).__name__}: {str(exc)[:300]}"}
                    )
            await asyncio.sleep(WAKE_INTERVAL_SECONDS)

    async def _tick(self, now: datetime) -> None:
        """单次调度检查（now 注入便于测试）：到点且今日未跑则挑目标提交批次。"""
        async with async_session_factory() as session:
            config = await get_collect_schedule(session)
            if not config.get("enabled"):
                return
            trigger = _parse_hhmm(str(config.get("time", "")))
            if trigger is None:
                logger.warning("定时采集时刻配置无效，跳过: %r", config.get("time"))
                return
            if now.time() < trigger:
                return

            state = (await get_setting(session, COLLECT_SCHEDULE_STATE_KEY)) or {}
            today = now.date().isoformat()
            if state.get("last_run_date") == today:
                return

            try:
                batch = int(config.get("batch") or 5)
            except (TypeError, ValueError):
                batch = 5
            batch = max(1, min(batch, 20))
            resume_codes, expand_items = await _pick_targets(
                session, batch, state.get("expand_cursor")
            )

            claim = {
                **state,
                "last_run_date": today,
                "last_run_at": now.isoformat(timespec="seconds"),
            }
            if not await _claim_today(session, claim, today):
                return  # 另一个 worker 已抢占今日批次

        targets = resume_codes + [code for _, code in expand_items]
        if not targets:
            await _merge_state({"last_result": {"submitted": 0, "note": "无待采集城市"}})
            logger.info("定时采集：今日无待采集城市")
            return

        try:
            job = await job_runner.submit(
                "collect",
                {"city_codes": targets, "source": SCHEDULE_SOURCE, "trigger": "schedule"},
                lambda job_id: _run_scheduled_collect(job_id, resume_codes, expand_items),
                progress_total=len(targets),
            )
        except ApiError as exc:
            # 与手动采集互斥（409）：撤销今日抢占，下一轮醒来自动重试
            await _merge_state({"last_run_date": None, "last_error": f"提交让位: {exc.detail}"})
            return
        except Exception as exc:
            await _merge_state({"last_run_date": None, "last_error": f"提交失败: {str(exc)[:300]}"})
            raise
        await _merge_state({"last_job_id": job.id, "last_error": None})
        logger.info("定时采集批次已提交: job #%d，%d 个城市", job.id, len(targets))


collect_scheduler = CollectScheduler()
