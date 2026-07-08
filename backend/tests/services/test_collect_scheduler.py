"""collect_scheduler 定时采集调度器单测（真实 DB，pipeline/提交打桩）。"""

from datetime import datetime
from types import SimpleNamespace

import pytest
import pytest_asyncio
from sqlalchemy import delete, select

from app.core.database import async_session_factory
from app.core.errors import ApiError
from app.models.app_setting import AppSetting
from app.models.city import City
from app.models.price_snapshot import PriceSnapshot
from app.services import collect_scheduler as cs
from app.services import collect_tasks
from app.services.app_settings import (
    COLLECT_SCHEDULE_KEY,
    COLLECT_SCHEDULE_STATE_KEY,
    get_setting,
    set_setting,
)

pytestmark = [pytest.mark.slow, pytest.mark.asyncio(loop_scope="session")]

# 写入真实 DB 的测试城市代码（泄漏会出现在前端页面，必须前后清理）
TEST_CITY_CODES = ["t_sched_a", "t_sched_b", "t_sched_c", "t_sched_d", "t_sched_e"]
SCHEDULE_KEYS = [COLLECT_SCHEDULE_KEY, COLLECT_SCHEDULE_STATE_KEY]


async def _purge_cities() -> None:
    async with async_session_factory() as s:
        ids = (
            (await s.execute(select(City.id).where(City.code.in_(TEST_CITY_CODES))))
            .scalars()
            .all()
        )
        if ids:
            await s.execute(
                delete(PriceSnapshot).where(
                    PriceSnapshot.region_type == "city",
                    PriceSnapshot.region_id.in_(ids),
                )
            )
            await s.execute(delete(City).where(City.id.in_(ids)))
        await s.commit()


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _isolate_schedule_settings():
    """暂存并恢复定时采集的配置/状态 KV：测试从空状态开始，结束后原样放回。"""
    async with async_session_factory() as s:
        originals = {}
        for key in SCHEDULE_KEYS:
            row = await s.get(AppSetting, key)
            originals[key] = row.value if row else None
        await s.execute(delete(AppSetting).where(AppSetting.key.in_(SCHEDULE_KEYS)))
        await s.commit()

    yield

    async with async_session_factory() as s:
        await s.execute(delete(AppSetting).where(AppSetting.key.in_(SCHEDULE_KEYS)))
        for key, value in originals.items():
            if value is not None:
                s.add(AppSetting(key=key, value=value))
        await s.commit()


@pytest_asyncio.fixture(loop_scope="session")
async def sched_cities():
    """5 个测试城市：a/b 有 creprice 旧数据（缺当月），c 仅 58 年度，d/e 无数据。"""
    await _purge_cities()
    async with async_session_factory() as s:
        cities = {
            code: City(name=f"调度{code[-1]}市", code=code) for code in TEST_CITY_CODES
        }
        s.add_all(cities.values())
        await s.flush()
        ids = {code: c.id for code, c in cities.items()}
        s.add_all(
            [
                # a 最旧（2024-01），b 次旧（2024-03）——续采应 a 在 b 前
                PriceSnapshot(
                    region_type="city", region_id=ids["t_sched_a"],
                    year_month="2024-01", supply_price=10000, source="creprice",
                ),
                PriceSnapshot(
                    region_type="city", region_id=ids["t_sched_b"],
                    year_month="2024-03", supply_price=10000, source="creprice",
                ),
                # c 只有 58 年度数据：对 creprice 覆盖而言仍属"未采集"，应进扩展
                PriceSnapshot(
                    region_type="city", region_id=ids["t_sched_c"],
                    year_month="2024", supply_price=9000, source="58",
                ),
            ]
        )
        await s.commit()
    yield ids
    await _purge_cities()


class TestPickTargets:
    async def test_resume_oldest_first_then_expand(self, sched_cities):
        ids = sched_cities
        async with async_session_factory() as s:
            resume, expand = await cs._pick_targets(s, batch=100000, cursor=None)

        # 续采：a（2024-01）先于 b（2024-03）；两者都不在扩展里
        mine = [c for c in resume if c in TEST_CITY_CODES]
        assert mine == ["t_sched_a", "t_sched_b"]
        expand_codes = [code for _, code in expand]
        assert "t_sched_a" not in expand_codes
        assert "t_sched_b" not in expand_codes

        # 扩展：c（仅 58 年度）/d/e 都算无 creprice 数据，按 city.id 升序
        mine_expand = [(cid, code) for cid, code in expand if code in TEST_CITY_CODES]
        assert mine_expand == [
            (ids["t_sched_c"], "t_sched_c"),
            (ids["t_sched_d"], "t_sched_d"),
            (ids["t_sched_e"], "t_sched_e"),
        ]
        assert "t_sched_c" not in resume

    async def test_batch_limit(self, sched_cities):
        async with async_session_factory() as s:
            resume, expand = await cs._pick_targets(s, batch=1, cursor=None)
        assert len(resume) + len(expand) == 1

    async def test_expand_cursor_continues_after(self, sched_cities):
        ids = sched_cities
        async with async_session_factory() as s:
            _, expand = await cs._pick_targets(
                s, batch=100000, cursor=ids["t_sched_c"]
            )
        mine = [code for _, code in expand if code in TEST_CITY_CODES]
        # 从 c 之后继续：d、e 在前，c 回绕到末尾
        assert mine == ["t_sched_d", "t_sched_e", "t_sched_c"]

    async def test_expand_cursor_wraps_at_end(self, sched_cities):
        ids = sched_cities
        async with async_session_factory() as s:
            _, expand = await cs._pick_targets(
                s, batch=100000, cursor=ids["t_sched_e"]
            )
        mine = [code for _, code in expand if code in TEST_CITY_CODES]
        # 游标在最后一个城市：回绕后从头扫，测试城市按 id 序排在真实城市之后
        assert mine == ["t_sched_c", "t_sched_d", "t_sched_e"]


class _StubRunner:
    """PipelineRunner 打桩：按城市代码决定成功/失败。"""

    def __init__(self, fail: set[str]):
        self.fail = fail
        self.calls: list[str] = []

    async def run(self, source_name: str, code: str, **kwargs) -> dict:
        self.calls.append(code)
        if code in self.fail:
            raise RuntimeError("ssl eof (simulated rate limit)")
        return {"snapshots": 3, "distributions": 1, "logs": 2, "errors": []}


@pytest.fixture
def _no_prefetch(monkeypatch):
    async def fake_prefetch(source_name):
        return {}

    monkeypatch.setattr(collect_tasks, "_prefetch_city_map", fake_prefetch)


@pytest.fixture
def _no_progress(monkeypatch):
    async def noop(job_id, done, total=None, result=None):
        pass

    monkeypatch.setattr(collect_tasks.job_runner, "report_progress", noop)


@pytest.fixture
def _no_pause(monkeypatch):
    pauses: list[tuple[float, float]] = []

    async def fake_pause(delay_range):
        pauses.append(delay_range)

    monkeypatch.setattr(collect_tasks, "_pause_between_cities", fake_pause)
    return pauses


class TestRunCollectCircuitBreaker:
    async def test_breaks_after_consecutive_failures(self, _no_prefetch, _no_progress, _no_pause):
        codes = ["c1", "c2", "c3", "c4", "c5"]
        runner = _StubRunner(fail=set(codes))
        summary = await collect_tasks.run_collect(
            1, codes, "creprice", max_consecutive_failures=3, runner=runner
        )
        assert len(summary["results"]) == 3
        assert summary["circuit_broken"] is True
        assert summary["skipped"] == ["c4", "c5"]

    async def test_success_resets_failure_streak(self, _no_prefetch, _no_progress, _no_pause):
        codes = ["f1", "f2", "s1", "f3", "f4", "f5", "never"]
        runner = _StubRunner(fail={"f1", "f2", "f3", "f4", "f5"})
        summary = await collect_tasks.run_collect(
            1, codes, "creprice", max_consecutive_failures=3, runner=runner
        )
        # f1 f2 后 s1 归零，f3 f4 f5 连续 3 失败熔断，never 未尝试
        assert [r["city"] for r in summary["results"]] == codes[:6]
        assert summary["circuit_broken"] is True
        assert summary["skipped"] == ["never"]

    async def test_manual_path_never_breaks(self, _no_prefetch, _no_progress, _no_pause):
        codes = ["c1", "c2", "c3", "c4", "c5"]
        runner = _StubRunner(fail=set(codes))
        summary = await collect_tasks.run_collect(1, codes, "creprice", runner=runner)
        assert len(summary["results"]) == 5
        assert summary["circuit_broken"] is False
        assert summary["skipped"] == []

    async def test_inter_city_pause_between_cities(
        self, _no_prefetch, _no_progress, _no_pause
    ):
        codes = ["c1", "c2", "c3"]
        runner = _StubRunner(fail=set())
        await collect_tasks.run_collect(
            1, codes, "creprice", inter_city_delay=(10.0, 20.0), runner=runner
        )
        # 城市之间 sleep（n-1 次），且使用配置的区间
        assert _no_pause == [(10.0, 20.0), (10.0, 20.0)]

    async def test_manual_path_no_pause(self, _no_prefetch, _no_progress, _no_pause):
        runner = _StubRunner(fail=set())
        await collect_tasks.run_collect(1, ["c1", "c2"], "creprice", runner=runner)
        assert _no_pause == []


class _StubJobRunner:
    """job_runner 打桩：记录提交，可注入冲突。"""

    def __init__(self, conflict: bool = False):
        self.conflict = conflict
        self.submissions: list[dict] = []

    async def submit(self, kind, payload, job_body, progress_total=0):
        if self.conflict:
            raise ApiError(409, "已有进行中的 collect 任务", "JOB_CONFLICT")
        self.submissions.append({"kind": kind, "payload": payload})
        return SimpleNamespace(id=4242)


@pytest_asyncio.fixture(loop_scope="session")
async def tick_env(monkeypatch):
    """_tick 依赖打桩：目标选择固定返回、提交进桩；配置写入 KV。"""
    stub = _StubJobRunner()

    async def fake_pick(session, batch, cursor):
        return (["t_sched_a"], [(999999, "t_sched_d")])

    monkeypatch.setattr(cs, "_pick_targets", fake_pick)
    monkeypatch.setattr(cs, "job_runner", stub)

    async def set_config(enabled=True, time="03:30", batch=5):
        async with async_session_factory() as s:
            await set_setting(
                s,
                COLLECT_SCHEDULE_KEY,
                {"enabled": enabled, "time": time, "batch": batch},
            )

    return SimpleNamespace(stub=stub, set_config=set_config)


async def _read_state() -> dict:
    async with async_session_factory() as s:
        return (await get_setting(s, COLLECT_SCHEDULE_STATE_KEY)) or {}


class TestTick:
    scheduler = cs.CollectScheduler()

    async def test_disabled_never_submits(self, tick_env):
        # 未写配置 = 默认关闭
        await self.scheduler._tick(datetime(2026, 7, 8, 12, 0))
        assert tick_env.stub.submissions == []

    async def test_before_trigger_time_skips(self, tick_env):
        await tick_env.set_config(enabled=True, time="03:30")
        await self.scheduler._tick(datetime(2026, 7, 8, 3, 29))
        assert tick_env.stub.submissions == []

    async def test_fires_once_per_day(self, tick_env):
        await tick_env.set_config(enabled=True, time="03:30", batch=5)
        now = datetime(2026, 7, 8, 3, 31)
        await self.scheduler._tick(now)

        assert len(tick_env.stub.submissions) == 1
        sub = tick_env.stub.submissions[0]
        assert sub["kind"] == "collect"
        assert sub["payload"]["trigger"] == "schedule"
        assert sub["payload"]["source"] == "creprice"
        assert sub["payload"]["city_codes"] == ["t_sched_a", "t_sched_d"]

        state = await _read_state()
        assert state["last_run_date"] == "2026-07-08"
        assert state["last_job_id"] == 4242

        # 同日再 tick（包括更晚时刻）不重复触发
        await self.scheduler._tick(datetime(2026, 7, 8, 3, 32))
        await self.scheduler._tick(datetime(2026, 7, 8, 23, 59))
        assert len(tick_env.stub.submissions) == 1

        # 次日到点再次触发
        await self.scheduler._tick(datetime(2026, 7, 9, 3, 31))
        assert len(tick_env.stub.submissions) == 2

    async def test_config_change_applies_without_restart(self, tick_env):
        await tick_env.set_config(enabled=False)
        await self.scheduler._tick(datetime(2026, 7, 8, 4, 0))
        assert tick_env.stub.submissions == []
        # 打开开关后（无任何重启动作）下一次 tick 即生效
        await tick_env.set_config(enabled=True, time="03:30")
        await self.scheduler._tick(datetime(2026, 7, 8, 4, 1))
        assert len(tick_env.stub.submissions) == 1

    async def test_invalid_time_config_skips(self, tick_env):
        async with async_session_factory() as s:
            await set_setting(
                s, COLLECT_SCHEDULE_KEY, {"enabled": True, "time": "25:99", "batch": 5}
            )
        await self.scheduler._tick(datetime(2026, 7, 8, 12, 0))
        assert tick_env.stub.submissions == []

    async def test_submit_conflict_reverts_claim_and_retries(self, tick_env):
        await tick_env.set_config(enabled=True, time="03:30")
        tick_env.stub.conflict = True
        await self.scheduler._tick(datetime(2026, 7, 8, 3, 31))
        state = await _read_state()
        assert "last_run_date" not in state  # 抢占被撤销
        assert "提交让位" in state["last_error"]

        # 冲突解除后同日重试成功
        tick_env.stub.conflict = False
        await self.scheduler._tick(datetime(2026, 7, 8, 3, 32))
        assert len(tick_env.stub.submissions) == 1
        assert (await _read_state())["last_run_date"] == "2026-07-08"

    async def test_no_targets_still_claims_day(self, tick_env, monkeypatch):
        async def empty_pick(session, batch, cursor):
            return ([], [])

        monkeypatch.setattr(cs, "_pick_targets", empty_pick)
        await tick_env.set_config(enabled=True, time="03:30")
        await self.scheduler._tick(datetime(2026, 7, 8, 3, 31))
        assert tick_env.stub.submissions == []
        state = await _read_state()
        assert state["last_run_date"] == "2026-07-08"
        assert state["last_result"] == {"submitted": 0, "note": "无待采集城市"}


class TestScheduledJobBody:
    async def test_writes_summary_and_cursor(self, monkeypatch):
        async def fake_run_collect(job_id, codes, source, **kwargs):
            assert kwargs["inter_city_delay"] == cs.SCHEDULE_INTER_CITY_DELAY
            assert (
                kwargs["max_consecutive_failures"]
                == cs.SCHEDULE_MAX_CONSECUTIVE_FAILURES
            )
            return {
                "results": [
                    {"city": "t_sched_a", "ok": True, "snapshots": 3, "distributions": 1},
                    {"city": "t_sched_c", "ok": False, "error": "boom"},
                ],
                "circuit_broken": True,
                "skipped": ["t_sched_d"],
            }

        monkeypatch.setattr(cs, "run_collect", fake_run_collect)
        await cs._run_scheduled_collect(
            1, ["t_sched_a"], [(101, "t_sched_c"), (102, "t_sched_d")]
        )
        state = await _read_state()
        assert state["last_result"] == {
            "submitted": 3,
            "ok": 1,
            "failed": 1,
            "circuit_broken": True,
            "skipped": ["t_sched_d"],
        }
        # 游标只越过实际尝试的扩展城市 c（101），跳过的 d（102）留给下一批
        assert state["expand_cursor"] == 101

    async def test_all_failed_marks_job_failed(self, monkeypatch):
        async def fake_run_collect(job_id, codes, source, **kwargs):
            return {
                "results": [{"city": c, "ok": False, "error": "x"} for c in codes],
                "circuit_broken": True,
                "skipped": [],
            }

        monkeypatch.setattr(cs, "run_collect", fake_run_collect)
        with pytest.raises(RuntimeError, match="全部"):
            await cs._run_scheduled_collect(1, ["t_sched_a"], [(101, "t_sched_c")])


class TestLifespanGuard:
    async def test_scheduler_not_started_under_pytest(self):
        from app.main import _scheduler_enabled

        assert _scheduler_enabled() is False

    async def test_stop_without_start_is_noop(self):
        sched = cs.CollectScheduler()
        await sched.stop()  # 不抛错


class TestParseHhmm:
    async def test_valid_and_invalid(self):
        assert cs._parse_hhmm("00:00") is not None
        assert cs._parse_hhmm("23:59") is not None
        parsed = cs._parse_hhmm("03:30")
        assert (parsed.hour, parsed.minute) == (3, 30)
        for bad in ("24:00", "3:30", "03:60", "0330", "", "abc"):
            assert cs._parse_hhmm(bad) is None
