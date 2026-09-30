import pytest
import requests

from usdbrl_lab.ingest.fallback import fetch_with_fallback
from usdbrl_lab.ingest.retry import USER_AGENT, make_http_get
from usdbrl_lab.sources.base import FetchResult, SourceError


class FakeResp:
    def __init__(self, status, body=b"{}"):
        self.status_code = status
        self.content = body


class FakeSession:
    def __init__(self, script):
        self.script = list(script)
        self.headers = requests.Session().headers.copy()
        self.calls = 0

    def get(self, url, params=None, timeout=None):
        self.calls += 1
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return FakeResp(item)


def _client(script):
    session = FakeSession(script)
    sleeps = []
    get = make_http_get(20, [2, 8, 30], [429, 500, 502, 503, 504], session, sleeps.append)
    return get, session, sleeps


def test_user_agent_overrides_requests_default():
    _, session, _ = _client([200])
    assert session.headers["User-Agent"] == USER_AGENT
    assert "python-requests" not in session.headers["User-Agent"]


def test_retries_on_429_then_succeeds():
    get, session, sleeps = _client([429, 503, 200])
    assert get("https://example.invalid", {}).status == 200
    assert session.calls == 3
    assert sleeps == [2, 8]


def test_timeout_is_retried():
    get, session, _ = _client([requests.Timeout(), 200])
    assert get("https://example.invalid", {}).status == 200


def test_other_4xx_fails_immediately():
    get, session, sleeps = _client([404])
    with pytest.raises(SourceError) as exc:
        get("https://example.invalid", {})
    assert exc.value.status == 404
    assert session.calls == 1 and sleeps == []


def test_gives_up_after_all_waits():
    get, session, sleeps = _client([429, 429, 429, 429])
    with pytest.raises(SourceError, match="429"):
        get("https://example.invalid", {})
    assert sleeps == [2, 8, 30]


def test_fallback_chain_without_usable_source_returns_none():
    def broken():
        raise SourceError("http", "HTTP 503", 503)

    result, used, attempts = fetch_with_fallback(["yahoo"], {"yahoo": broken})
    assert result is None and used is None
    assert attempts == [
        {"source": "yahoo", "status": "failed", "kind": "http", "message": "HTTP 503"}
    ]


def test_fallback_never_improvises_unlisted_sources():
    ok = FetchResult("x", "s", "5m", None)
    result, used, attempts = fetch_with_fallback(["yahoo"], {"awesomeapi": lambda: ok})
    assert result is None
    assert attempts == [{"source": "yahoo", "status": "not_available"}]


def test_configured_chain_is_yahoo_only(cfg):
    assert cfg["sources"]["price_fallback_order"] == ["yahoo"]
