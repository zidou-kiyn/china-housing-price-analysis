"""CrawlerHttpClient 重试/退避/UA 单元测试（fake Session，不联网）。"""

import pytest
import requests

from app.collector.http_client import CrawlerHttpClient


class FakeResponse:
    def __init__(self, status_code: int, url: str = "http://fake/x"):
        self.status_code = status_code
        self.url = url

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} error")


class FakeSession:
    """前 fail_times 次请求失败，之后成功；记录每次调用参数。"""

    def __init__(self, fail_times: int = 0):
        self.fail_times = fail_times
        self.calls: list[dict] = []

    def get(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": params, "headers": headers})
        if len(self.calls) <= self.fail_times:
            raise requests.ConnectionError("boom")
        return FakeResponse(200, url)


def _client(session, max_retries=3):
    return CrawlerHttpClient(
        delay_min=0, delay_max=0, max_retries=max_retries, backoff_base=0, session=session
    )


class TestGet:
    def test_success_first_try(self):
        session = FakeSession()
        resp = _client(session).get("http://fake/x", params={"a": 1})
        assert resp.status_code == 200
        assert len(session.calls) == 1
        assert session.calls[0]["params"] == {"a": 1}

    def test_retries_then_succeeds(self):
        session = FakeSession(fail_times=2)
        resp = _client(session, max_retries=3).get("http://fake/x")
        assert resp.status_code == 200
        assert len(session.calls) == 3

    def test_exhausted_retries_raises_last_error(self):
        session = FakeSession(fail_times=99)
        with pytest.raises(requests.ConnectionError):
            _client(session, max_retries=3).get("http://fake/x")
        assert len(session.calls) == 3

    def test_http_error_is_retried(self):
        class ErrorSession(FakeSession):
            def get(self, url, params=None, headers=None, timeout=None):
                self.calls.append({"headers": headers})
                return FakeResponse(503)

        session = ErrorSession()
        with pytest.raises(requests.HTTPError):
            _client(session, max_retries=2).get("http://fake/x")
        assert len(session.calls) == 2

    def test_sends_browser_user_agent(self):
        session = FakeSession()
        _client(session).get("http://fake/x")
        ua = session.calls[0]["headers"]["User-Agent"]
        assert ua in CrawlerHttpClient.UA_LIST
        assert "Mozilla" in ua
