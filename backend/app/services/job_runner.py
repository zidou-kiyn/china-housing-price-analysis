"""进程内后台任务执行器（admin_job）。

任务在接收请求的 uvicorn worker 进程内以 asyncio.create_task 执行，
状态持久化到 admin_job 表，任一 worker 均可应答轮询查询。
不做跨进程取消与断点续传：重启后遗留任务由 cleanup_stale_jobs 置为 failed。
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.core.database import async_session_factory
from app.core.errors import ApiError
from app.models.admin_job import AdminJob

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("pending", "running")

# 任务体：接收 job_id 的协程工厂，内部自建 DB session（不得复用请求 session）
JobBody = Callable[[int], Awaitable[None]]

# 持引用防止 asyncio.Task 被 GC 提前回收
_background_tasks: set[asyncio.Task] = set()


async def submit(
    kind: str, payload: dict | None, job_body: JobBody, progress_total: int = 0
) -> AdminJob:
    """创建任务并调度后台执行；同 kind 已有活跃任务时抛 409。"""
    async with async_session_factory() as session:
        active_id = await session.scalar(
            select(AdminJob.id)
            .where(AdminJob.kind == kind, AdminJob.status.in_(ACTIVE_STATUSES))
            .limit(1)
        )
        if active_id is not None:
            raise ApiError(409, f"已有进行中的 {kind} 任务（#{active_id}）", "JOB_CONFLICT")

        job = AdminJob(kind=kind, payload=payload, progress_total=progress_total)
        session.add(job)
        try:
            await session.commit()
        except IntegrityError:
            # 并发提交竞态由部分唯一索引兜底
            raise ApiError(409, f"已有进行中的 {kind} 任务", "JOB_CONFLICT")
        await session.refresh(job)

    task = asyncio.create_task(_execute(job.id, job_body), name=f"admin_job_{job.id}")
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
    return job


async def _execute(job_id: int, job_body: JobBody) -> None:
    await _update(job_id, status="running", started_at=datetime.now())
    try:
        await job_body(job_id)
    except Exception as exc:
        logger.exception("admin_job #%d 执行失败", job_id)
        await _update(
            job_id, status="failed", error=str(exc)[:2000], finished_at=datetime.now()
        )
    else:
        await _update(job_id, status="success", finished_at=datetime.now())


async def report_progress(
    job_id: int,
    done: int,
    total: int | None = None,
    result: list | None = None,
) -> None:
    """供任务体逐单元上报进度与结果摘要（每次独立短事务）。"""
    values: dict = {"progress_done": done}
    if total is not None:
        values["progress_total"] = total
    if result is not None:
        values["result"] = result
    await _update(job_id, **values)


async def cleanup_stale_jobs() -> int:
    """启动时把遗留 pending/running 任务置为 failed；幂等，多 worker 重复执行无害。"""
    async with async_session_factory() as session:
        res = await session.execute(
            update(AdminJob)
            .where(AdminJob.status.in_(ACTIVE_STATUSES))
            .values(status="failed", error="interrupted by restart", finished_at=datetime.now())
        )
        await session.commit()
        if res.rowcount:
            logger.warning("启动清理：%d 个遗留任务置为 failed", res.rowcount)
        return res.rowcount


async def _update(job_id: int, **values) -> None:
    async with async_session_factory() as session:
        await session.execute(update(AdminJob).where(AdminJob.id == job_id).values(**values))
        await session.commit()
