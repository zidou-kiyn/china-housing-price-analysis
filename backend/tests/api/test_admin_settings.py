"""采集代理设置端点与注入链路测试（外部请求打桩）。"""

import pytest
import pytest_asyncio
import requests
from sqlalchemy import delete

from app.api.v1 import admin_settings
from app.collector.http_client import CrawlerHttpClient
from app.core.database import async_session_factory
from app.models.app_setting import AppSetting
from app.services.app_settings import get_proxy_url_sync

pytestmark = [pytest.mark.slow, pytest.mark.asyncio(loop_scope="session")]

PROXY_URL = "http://user:secretpass@10.0.0.1:2260"


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _clean_setting():
    yield
    async with async_session_factory() as s:
        await s.execute(delete(AppSetting).where(AppSetting.key == "crawler_proxy"))
        await s.commit()


class TestProxyCrud:
    async def test_default_empty(self, client, admin_headers):
        resp = await client.get("/api/v1/admin/settings/proxy", headers=admin_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"enabled": False, "url_masked": None, "has_url": False}

    async def test_save_and_mask(self, client, admin_headers):
        resp = await client.put(
            "/api/v1/admin/settings/proxy",
            json={"enabled": True, "url": PROXY_URL},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["enabled"] is True
        assert data["has_url"] is True
        assert data["url_masked"] == "http://user:***@10.0.0.1:2260"
        assert "secretpass" not in resp.text

    async def test_toggle_keeps_url(self, client, admin_headers):
        await client.put(
            "/api/v1/admin/settings/proxy",
            json={"enabled": True, "url": PROXY_URL},
            headers=admin_headers,
        )
        # 仅改开关（url 缺省）
        resp = await client.put(
            "/api/v1/admin/settings/proxy", json={"enabled": False}, headers=admin_headers
        )
        data = resp.json()
        assert data["enabled"] is False
        assert data["has_url"] is True

    async def test_clear_url(self, client, admin_headers):
        await client.put(
            "/api/v1/admin/settings/proxy",
            json={"enabled": True, "url": PROXY_URL},
            headers=admin_headers,
        )
        resp = await client.put(
            "/api/v1/admin/settings/proxy",
            json={"enabled": False, "url": ""},
            headers=admin_headers,
        )
        assert resp.json()["has_url"] is False

    async def test_enable_without_url_422(self, client, admin_headers):
        resp = await client.put(
            "/api/v1/admin/settings/proxy", json={"enabled": True}, headers=admin_headers
        )
        assert resp.status_code == 422

    async def test_invalid_url_422(self, client, admin_headers):
        resp = await client.put(
            "/api/v1/admin/settings/proxy",
            json={"enabled": True, "url": "ftp://nope"},
            headers=admin_headers,
        )
        assert resp.status_code == 422

    async def test_forbidden_for_user(self, client, auth_headers):
        for method, path, body in [
            ("get", "/api/v1/admin/settings/proxy", None),
            ("put", "/api/v1/admin/settings/proxy", {"enabled": False}),
            ("post", "/api/v1/admin/settings/proxy/test", {"url": PROXY_URL}),
        ]:
            resp = await getattr(client, method)(
                path, **({"json": body} if body is not None else {}), headers=auth_headers
            )
            assert resp.status_code == 403


class TestProxyProbe:
    async def test_probe_success(self, client, admin_headers, monkeypatch):
        captured = {}

        def fake_get(url, proxies=None, headers=None, timeout=None):
            captured["proxies"] = proxies

            class R:
                status_code = 200

            return R()

        monkeypatch.setattr(admin_settings.requests, "get", fake_get)
        resp = await client.post(
            "/api/v1/admin/settings/proxy/test", json={"url": PROXY_URL}, headers=admin_headers
        )
        data = resp.json()
        assert data["ok"] is True
        assert data["status_code"] == 200
        assert captured["proxies"] == {"http": PROXY_URL, "https": PROXY_URL}

    async def test_probe_timeout_reports_error(self, client, admin_headers, monkeypatch):
        def fake_get(*args, **kwargs):
            raise requests.ConnectTimeout("proxy unreachable")

        monkeypatch.setattr(admin_settings.requests, "get", fake_get)
        resp = await client.post(
            "/api/v1/admin/settings/proxy/test", json={"url": PROXY_URL}, headers=admin_headers
        )
        data = resp.json()
        assert data["ok"] is False
        assert "ConnectTimeout" in data["error"]

    async def test_probe_uses_saved_url(self, client, admin_headers, monkeypatch):
        await client.put(
            "/api/v1/admin/settings/proxy",
            json={"enabled": False, "url": PROXY_URL},
            headers=admin_headers,
        )
        seen = {}

        def fake_get(url, proxies=None, **kwargs):
            seen["proxies"] = proxies

            class R:
                status_code = 200

            return R()

        monkeypatch.setattr(admin_settings.requests, "get", fake_get)
        resp = await client.post(
            "/api/v1/admin/settings/proxy/test", json={}, headers=admin_headers
        )
        assert resp.json()["ok"] is True
        assert seen["proxies"]["https"] == PROXY_URL

    async def test_probe_no_url_422(self, client, admin_headers):
        resp = await client.post(
            "/api/v1/admin/settings/proxy/test", json={}, headers=admin_headers
        )
        assert resp.status_code == 422


class TestInjection:
    async def test_sync_reader_respects_enabled(self, client, admin_headers):
        await client.put(
            "/api/v1/admin/settings/proxy",
            json={"enabled": True, "url": PROXY_URL},
            headers=admin_headers,
        )
        assert get_proxy_url_sync() == PROXY_URL

        await client.put(
            "/api/v1/admin/settings/proxy", json={"enabled": False}, headers=admin_headers
        )
        assert get_proxy_url_sync() is None

    async def test_http_client_auto_proxy(self, client, admin_headers):
        await client.put(
            "/api/v1/admin/settings/proxy",
            json={"enabled": True, "url": PROXY_URL},
            headers=admin_headers,
        )
        auto = CrawlerHttpClient()
        assert auto.session.proxies == {"http": PROXY_URL, "https": PROXY_URL}

        direct = CrawlerHttpClient(proxy=False)
        assert direct.session.proxies == {}

        explicit = CrawlerHttpClient(proxy="http://other:1080")
        assert explicit.session.proxies["https"] == "http://other:1080"
