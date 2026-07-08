import logging
import os
import sys
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.cache import redis_client
from app.core.config import settings
from app.core.database import engine
from app.core.errors import register_exception_handlers
from app.core.logging import setup_logging
from app.services.collect_scheduler import collect_scheduler
from app.services.job_runner import cleanup_stale_jobs

setup_logging(settings.log_level)
access_logger = logging.getLogger("app.access")


def _scheduler_enabled() -> bool:
    """pytest 导入 app 时绝不启动调度循环（避免测试悬挂任务/意外采集）。

    判定：pytest 进程中 sys.modules 必含 "pytest"（conftest 由 pytest 加载）；
    另留 COLLECT_SCHEDULER_DISABLED=1 环境变量供部署侧显式关停循环本身
    （日常开关走 admin settings 的 collect_schedule.enabled，无需重启）。
    """
    if "pytest" in sys.modules:
        return False
    return os.environ.get("COLLECT_SCHEDULER_DISABLED", "") != "1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 重启后遗留的 running 任务标记 failed（多 worker 重复执行幂等）
    await cleanup_stale_jobs()
    # 定时采集调度循环（每 worker 一个；当日批次由 KV 原子抢占保证唯一）
    if _scheduler_enabled():
        collect_scheduler.start()
    yield
    await collect_scheduler.stop()
    await engine.dispose()
    await redis_client.aclose()


app = FastAPI(
    title="城市房价分析系统",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)
app.include_router(api_router, prefix="/api/v1")


@app.middleware("http")
async def access_log_middleware(request: Request, call_next):
    if request.url.path == "/health":
        return await call_next(request)
    t0 = time.perf_counter()
    response = await call_next(request)
    elapsed_ms = (time.perf_counter() - t0) * 1000
    access_logger.info(
        "%s %s -> %d (%.1fms)", request.method, request.url.path, response.status_code, elapsed_ms
    )
    return response


@app.get("/health")
async def health_check():
    return {"status": "ok"}
