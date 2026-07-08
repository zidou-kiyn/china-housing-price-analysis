"""采集代理设置端点与注入链路测试（外部请求打桩）。"""

import pytest
import pytest_asyncio
import requests
from sqlalchemy import delete

from app.api.v1 import admin_settings
from app.collector.http_client import CrawlerHttpClient
from app.core.database import async_session_factory
from app.models.app_setting import AppSetting
from app.services.app_settings import (
    COLLECT_SCHEDULE_KEY,
    COLLECT_SCHEDULE_STATE_KEY,
    get_proxy_url_sync,
)

pytestmark = [pytest.mark.slow, pytest.mark.asyncio(loop_scope="session")]

PROXY_URL = "http://user:secretpass@10.0.0.1:2260"
SCHEDULE_KEYS = [COLLECT_SCHEDULE_KEY, COLLECT_SCHEDULE_STATE_KEY]


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _isolate_setting():
    """暂存并恢复 dev 环境的真实代理配置：测试从空状态开始，结束后原样放回。"""
    async with async_session_factory() as s:
        row = await s.get(AppSetting, "crawler_proxy")
        original = row.value if row else None
        await s.execute(delete(AppSetting).where(AppSetting.key == "crawler_proxy"))
        await s.commit()

    yield

    async with async_session_factory() as s:
        await s.execute(delete(AppSetting).where(AppSetting.key == "crawler_proxy"))
        if original is not None:
            s.add(AppSetting(key="crawler_proxy", value=original))
        await s.commit()


@pytest_asyncio.fixture(autouse=True, loop_scope="session")
async def _isolate_schedule_setting():
    """暂存并恢复定时采集配置/状态 KV，避免污染 dev 环境真实配置。"""
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


class TestCollectScheduleCrud:
    async def test_default_disabled(self, client, admin_headers):
        resp = await client.get(
            "/api/v1/admin/settings/collect-schedule", headers=admin_headers
        )
        assert resp.status_code == 200
        assert resp.json() == {
            "enabled": False,
            "time": "03:30",
            "batch": 5,
            "state": None,
        }

    async def test_put_roundtrip(self, client, admin_headers):
        resp = await client.put(
            "/api/v1/admin/settings/collect-schedule",
            json={"enabled": True, "time": "04:15", "batch": 8},
            headers=admin_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert (data["enabled"], data["time"], data["batch"]) == (True, "04:15", 8)

        resp = await client.get(
            "/api/v1/admin/settings/collect-schedule", headers=admin_headers
        )
        data = resp.json()
        assert (data["enabled"], data["time"], data["batch"]) == (True, "04:15", 8)

    async def test_state_echoed_back(self, client, admin_headers):
        async with async_session_factory() as s:
            s.add(
                AppSetting(
                    key=COLLECT_SCHEDULE_STATE_KEY,
                    value={"last_run_date": "2026-07-08", "last_job_id": 7},
                )
            )
            await s.commit()
        resp = await client.get(
            "/api/v1/admin/settings/collect-schedule", headers=admin_headers
        )
        assert resp.json()["state"] == {"last_run_date": "2026-07-08", "last_job_id": 7}

    async def test_invalid_time_422(self, client, admin_headers):
        for bad in ("24:00", "3:30", "03:60", "abc"):
            resp = await client.put(
                "/api/v1/admin/settings/collect-schedule",
                json={"enabled": False, "time": bad, "batch": 5},
                headers=admin_headers,
            )
            assert resp.status_code == 422, bad

    async def test_invalid_batch_422(self, client, admin_headers):
        for bad in (0, 21):
            resp = await client.put(
                "/api/v1/admin/settings/collect-schedule",
                json={"enabled": False, "time": "03:30", "batch": bad},
                headers=admin_headers,
            )
            assert resp.status_code == 422, bad

    async def test_forbidden_for_user(self, client, auth_headers):
        resp = await client.get(
            "/api/v1/admin/settings/collect-schedule", headers=auth_headers
        )
        assert resp.status_code == 403
        resp = await client.put(
            "/api/v1/admin/settings/collect-schedule",
            json={"enabled": False, "time": "03:30", "batch": 5},
            headers=auth_headers,
        )
        assert resp.status_code == 403


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
