"""异常处理链单元测试：ApiError 渲染与未捕获异常兜底（独立 app，不联库）。"""

import httpx
import pytest
from fastapi import FastAPI

from app.core.errors import ApiError, register_exception_handlers

pytestmark = pytest.mark.asyncio


def _build_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/coded-error")
    async def coded_error():
        raise ApiError(404, "找不到资源", "RESOURCE_NOT_FOUND")

    @app.get("/boom")
    async def boom():
        raise RuntimeError("意外崩溃")

    return app


def _client(app: FastAPI) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
    return httpx.AsyncClient(transport=transport, base_url="http://test")


async def test_api_error_renders_code():
    async with _client(_build_app()) as client:
        resp = await client.get("/coded-error")
    assert resp.status_code == 404
    assert resp.json() == {"detail": "找不到资源", "code": "RESOURCE_NOT_FOUND"}


async def test_unhandled_exception_returns_500_json(caplog):
    async with _client(_build_app()) as client:
        with caplog.at_level("ERROR"):
            resp = await client.get("/boom")
    assert resp.status_code == 500
    assert resp.json() == {"detail": "服务器内部错误", "code": "INTERNAL_ERROR"}
    assert "未捕获异常" in caplog.text
    assert "RuntimeError" in caplog.text
