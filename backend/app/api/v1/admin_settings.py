"""管理端设置端点：采集代理配置与连通性测试。"""

from __future__ import annotations

import asyncio
import time
from urllib.parse import urlsplit, urlunsplit

import requests
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_session, require_admin
from app.core.errors import ApiError
from app.models.user import UserAccount
from app.schemas.settings import (
    CollectScheduleOut,
    CollectScheduleUpdate,
    ProxySettingOut,
    ProxySettingUpdate,
    ProxyTestRequest,
    ProxyTestResult,
)
from app.services.app_settings import (
    COLLECT_SCHEDULE_KEY,
    COLLECT_SCHEDULE_STATE_KEY,
    PROXY_KEY,
    get_collect_schedule,
    get_setting,
    set_setting,
)

router = APIRouter(prefix="/admin/settings", tags=["admin"])

PROXY_SCHEMES = ("http", "https", "socks5", "socks5h")
TEST_TARGET = "https://www.creprice.cn/rank/citySel.html"
TEST_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def _validate_proxy_url(url: str) -> None:
    parts = urlsplit(url)
    if parts.scheme not in PROXY_SCHEMES or not parts.hostname or not parts.port:
        raise ApiError(
            422,
            "代理 URL 格式无效，应为 http(s)://[user:pass@]host:port 或 socks5://…",
            "VALIDATION_ERROR",
        )


def mask_proxy_url(url: str) -> str:
    """密码脱敏：http://user:***@host:port。"""
    parts = urlsplit(url)
    if parts.password is None:
        return url
    host_port = parts.hostname + (f":{parts.port}" if parts.port else "")
    netloc = f"{parts.username}:***@{host_port}"
    return urlunsplit((parts.scheme, netloc, parts.path, parts.query, parts.fragment))


async def _load(db: AsyncSession) -> dict:
    return (await get_setting(db, PROXY_KEY)) or {"enabled": False, "url": ""}


def _to_out(value: dict) -> ProxySettingOut:
    url = (value.get("url") or "").strip()
    return ProxySettingOut(
        enabled=bool(value.get("enabled")),
        url_masked=mask_proxy_url(url) if url else None,
        has_url=bool(url),
    )


@router.get("/proxy", response_model=ProxySettingOut)
async def get_proxy_setting(
    db: AsyncSession = Depends(get_session),
    _admin: UserAccount = Depends(require_admin),
):
    return _to_out(await _load(db))


@router.put("/proxy", response_model=ProxySettingOut)
async def update_proxy_setting(
    payload: ProxySettingUpdate,
    db: AsyncSession = Depends(get_session),
    _admin: UserAccount = Depends(require_admin),
):
    value = await _load(db)
    value["enabled"] = payload.enabled

    if payload.url is not None:  # None = 仅改开关，保留已存 URL
        url = payload.url.strip()
        if url:
            _validate_proxy_url(url)
        value["url"] = url

    if value["enabled"] and not (value.get("url") or "").strip():
        raise ApiError(422, "启用代理前请先填写代理 URL", "VALIDATION_ERROR")

    await set_setting(db, PROXY_KEY, value)
    return _to_out(value)


def _probe(proxy_url: str) -> ProxyTestResult:
    t0 = time.perf_counter()
    try:
        resp = requests.get(
            TEST_TARGET,
            proxies={"http": proxy_url, "https": proxy_url},
            headers={"User-Agent": TEST_UA},
            timeout=15,
        )
        elapsed = int((time.perf_counter() - t0) * 1000)
        return ProxyTestResult(
            ok=resp.status_code == 200, status_code=resp.status_code, elapsed_ms=elapsed
        )
    except requests.RequestException as exc:
        elapsed = int((time.perf_counter() - t0) * 1000)
        return ProxyTestResult(
            ok=False, elapsed_ms=elapsed, error=f"{type(exc).__name__}: {str(exc)[:200]}"
        )


# ---- 定时采集 ----


async def _schedule_out(db: AsyncSession) -> CollectScheduleOut:
    config = await get_collect_schedule(db)
    state = await get_setting(db, COLLECT_SCHEDULE_STATE_KEY)
    return CollectScheduleOut(
        enabled=bool(config["enabled"]),
        time=str(config["time"]),
        batch=int(config["batch"]),
        state=state,
    )


@router.get("/collect-schedule", response_model=CollectScheduleOut)
async def read_collect_schedule(
    db: AsyncSession = Depends(get_session),
    _admin: UserAccount = Depends(require_admin),
):
    """读取定时采集配置与上次运行状态。"""
    return await _schedule_out(db)


@router.put("/collect-schedule", response_model=CollectScheduleOut)
async def update_collect_schedule(
    payload: CollectScheduleUpdate,
    db: AsyncSession = Depends(get_session),
    _admin: UserAccount = Depends(require_admin),
):
    """保存定时采集配置；调度循环每分钟重读 KV，改动即时生效（无需重启）。"""
    await set_setting(
        db,
        COLLECT_SCHEDULE_KEY,
        {"enabled": payload.enabled, "time": payload.time, "batch": payload.batch},
    )
    return await _schedule_out(db)


@router.post("/proxy/test", response_model=ProxyTestResult)
async def test_proxy(
    payload: ProxyTestRequest,
    db: AsyncSession = Depends(get_session),
    _admin: UserAccount = Depends(require_admin),
):
    """经代理请求 creprice 城市页（单次、15s 超时），验证代理对采集源的可用性。"""
    url = (payload.url or "").strip()
    if not url:
        url = ((await _load(db)).get("url") or "").strip()
    if not url:
        raise ApiError(422, "未提供代理 URL 且尚未保存过配置", "VALIDATION_ERROR")
    _validate_proxy_url(url)

    return await asyncio.to_thread(_probe, url)
