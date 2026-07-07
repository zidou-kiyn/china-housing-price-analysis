"""job_runner 后台任务执行器单测（真实 DB，任务体打桩）。"""

import asyncio

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.core.database import async_session_factory
from app.core.errors import ApiError
from app.models.admin_job import AdminJob
from app.services import job_runner

pytestmark = [pytest.mark.slow, pytest.mark.asyncio(loop_scope="session")]

TEST_KIND = "t_unit"
TEST_KIND_2 = "t_unit2"


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _clean_jobs():
    yield
    async with async_session_factory() as s:
        await s.execute(
            delete(AdminJob).where(AdminJob.kind.in_([TEST_KIND, TEST_KIND_2]))
        )
        await s.commit()


async def _get_job(job_id: int) -> AdminJob:
    async with async_session_factory() as s:
        return (
            await s.execute(select(AdminJob).where(AdminJob.id == job_id))
        ).scalar_one()


async def _wait_final(job_id: int, timeout: float = 5.0) -> AdminJob:
    """轮询等待任务进入终态。"""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        job = await _get_job(job_id)
        if job.status in ("success", "failed"):
            return job
        await asyncio.sleep(0.05)
    raise TimeoutError(f"job #{job_id} 未在 {timeout}s 内结束（status={job.status}）")


class TestLifecycle:
    async def test_success_flow_with_progress(self):
        async def body(job_id: int) -> None:
            await job_runner.report_progress(job_id, 1, total=2, result=[{"unit": 1, "ok": True}])
            await job_runner.report_progress(
                job_id, 2, result=[{"unit": 1, "ok": True}, {"unit": 2, "ok": True}]
            )

        job = await job_runner.submit(TEST_KIND, {"cities": ["a", "b"]}, body, progress_total=2)
        assert job.status == "pending"
        assert job.payload == {"cities": ["a", "b"]}

        final = await _wait_final(job.id)
        assert final.status == "success"
        assert final.progress_done == 2
        assert final.progress_total == 2
        assert len(final.result) == 2
        assert final.started_at is not None
        assert final.finished_at is not None

    async def test_exception_marks_failed(self):
        async def body(job_id: int) -> None:
            raise RuntimeError("boom")

        job = await job_runner.submit(TEST_KIND, None, body)
        final = await _wait_final(job.id)
        assert final.status == "failed"
        assert "boom" in final.error

    async def test_failure_keeps_partial_result(self):
        async def body(job_id: int) -> None:
            await job_runner.report_progress(job_id, 1, result=[{"unit": 1, "ok": False}])
            raise RuntimeError("later boom")

        job = await job_runner.submit(TEST_KIND, None, body)
        final = await _wait_final(job.id)
        assert final.status == "failed"
        assert final.result == [{"unit": 1, "ok": False}]


class TestMutex:
    async def test_same_kind_conflict_409(self):
        release = asyncio.Event()

        async def body(job_id: int) -> None:
            await release.wait()

        job = await job_runner.submit(TEST_KIND, None, body)
        try:
            with pytest.raises(ApiError) as exc_info:
                await job_runner.submit(TEST_KIND, None, body)
            assert exc_info.value.status_code == 409
            assert exc_info.value.code == "JOB_CONFLICT"
        finally:
            release.set()
        await _wait_final(job.id)

    async def test_different_kind_allowed(self):
        release = asyncio.Event()

        async def body(job_id: int) -> None:
            await release.wait()

        job1 = await job_runner.submit(TEST_KIND, None, body)
        job2 = await job_runner.submit(TEST_KIND_2, None, body)
        release.set()
        assert (await _wait_final(job1.id)).status == "success"
        assert (await _wait_final(job2.id)).status == "success"

    async def test_resubmit_after_final_ok(self):
        async def body(job_id: int) -> None:
            pass

        job1 = await job_runner.submit(TEST_KIND, None, body)
        await _wait_final(job1.id)
        job2 = await job_runner.submit(TEST_KIND, None, body)
        final = await _wait_final(job2.id)
        assert final.status == "success"


class TestStartupCleanup:
    async def test_stale_jobs_marked_failed(self):
        async with async_session_factory() as s:
            stale = AdminJob(kind=TEST_KIND, status="running")
            s.add(stale)
            await s.commit()
            await s.refresh(stale)

        cleaned = await job_runner.cleanup_stale_jobs()
        assert cleaned >= 1

        job = await _get_job(stale.id)
        assert job.status == "failed"
        assert job.error == "interrupted by restart"
        assert job.finished_at is not None

    async def test_cleanup_idempotent(self):
        # 没有活跃任务时再次清理不报错、不误伤终态任务
        async def body(job_id: int) -> None:
            pass

        job = await job_runner.submit(TEST_KIND, None, body)
        final = await _wait_final(job.id)
        await job_runner.cleanup_stale_jobs()
        job_after = await _get_job(final.id)
        assert job_after.status == "success"
