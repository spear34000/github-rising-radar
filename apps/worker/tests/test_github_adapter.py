"""Unit tests for radar_worker.github (httpx.MockTransport).

NOTE: not executed in this environment (no shell access); run with:
    cd apps/worker && pytest tests/test_github_adapter.py -q
"""

from __future__ import annotations

import time

import httpx
import pytest

from radar_worker import github as gh_mod
from radar_worker.github import (
    GitHubApiError,
    GitHubClient,
    NoTokenError,
    parse_full_name,
    validate_owner_name,
)


def _client(handler, **kwargs):
    transport = httpx.MockTransport(handler)
    kwargs.setdefault("tokens", ["tok-1"])
    kwargs.setdefault("max_retries", 2)
    return GitHubClient(transport=transport, **kwargs)


def _json_response(status, payload=None, headers=None):
    return httpx.Response(status, json=payload or {}, headers=headers or {})


# --------------------------------------------------------------------------- #
# auth / tokens
# --------------------------------------------------------------------------- #
def test_auth_header_and_token_rotation():
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization"))
        return _json_response(200, {"id": 1})

    gh = _client(handler, tokens=["tok-A", "tok-B"])
    gh._request("GET", "/repos/o/n")
    gh._request("GET", "/repos/o/n2")
    assert seen == ["Bearer tok-A", "Bearer tok-B"]


def test_no_token_sends_unauthenticated():
    """Without tokens the client still works (GitHub allows 60 req/h
    unauthenticated) — it just omits the Authorization header."""
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.headers.get("authorization"))
        return _json_response(200, {"id": 1})

    gh = _client(handler, tokens=[])
    gh.get_repo("octo", "cat")
    assert seen == [None]


def test_owner_name_validation():
    validate_owner_name("octocat", "hello-world")
    with pytest.raises(ValueError):
        validate_owner_name("../evil", "x")
    with pytest.raises(ValueError):
        validate_owner_name("octocat", "../../etc")
    with pytest.raises(ValueError):
        validate_owner_name("has space", "x")


def test_parse_full_name():
    assert parse_full_name("octocat/hello-world") == ("octocat", "hello-world")
    for bad in ["", "noslash", "a/b/c", "/b", "a/", "../x", "a/b?c=d"]:
        with pytest.raises(ValueError):
            parse_full_name(bad)


# --------------------------------------------------------------------------- #
# rate limits
# --------------------------------------------------------------------------- #
def test_rate_limit_remaining_triggers_wait(monkeypatch):
    slept = []
    monkeypatch.setattr(gh_mod, "sleep", lambda s: slept.append(s))
    reset = int(time.time()) + 30

    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(200, {"ok": True}, headers={
            "x-ratelimit-remaining": "0",
            "x-ratelimit-reset": str(reset),
        })

    gh = _client(handler, rate_limit_threshold=50)
    data = gh._request("GET", "/repos/o/n")
    assert data == {"ok": True}
    assert len(slept) == 1
    assert 25 <= slept[0] <= 40  # reset - now + 2s buffer
    assert gh.metrics.rate_limit_hits == 1


def test_secondary_rate_limit_backoff(monkeypatch):
    slept = []
    monkeypatch.setattr(gh_mod, "sleep", lambda s: slept.append(s))
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return _json_response(
                403, {"message": "You have exceeded a secondary rate limit."},
                headers={"retry-after": "2"},
            )
        return _json_response(200, {"ok": True})

    gh = _client(handler)
    assert gh._request("GET", "/repos/o/n") == {"ok": True}
    assert calls["n"] == 2
    assert len(slept) == 1 and slept[0] >= 2.0  # retry-after + jitter
    assert gh.metrics.secondary_rate_limit_hits == 1


# --------------------------------------------------------------------------- #
# retries
# --------------------------------------------------------------------------- #
def test_500_retries_then_raises(monkeypatch):
    monkeypatch.setattr(gh_mod, "sleep", lambda s: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return _json_response(502, {"message": "bad gateway"})

    gh = _client(handler, max_retries=2)
    with pytest.raises(GitHubApiError) as exc:
        gh._request("GET", "/repos/o/n")
    assert calls["n"] == 3  # initial + 2 retries
    assert gh.metrics.retries == 3
    assert "max retries exceeded" in str(exc.value)


def test_404_raises_without_retry():
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return _json_response(404, {"message": "Not Found"})

    gh = _client(handler)
    with pytest.raises(GitHubApiError) as exc:
        gh.get_repo("octocat", "nope")
    assert exc.value.status_code == 404
    assert calls["n"] == 1


# --------------------------------------------------------------------------- #
# etag / paginator
# --------------------------------------------------------------------------- #
def test_etag_304_returns_cached():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.headers.get("if-none-match") == '"etag-1"':
            return httpx.Response(304)
        return _json_response(200, {"stars": 42}, headers={"etag": '"etag-1"'})

    gh = _client(handler)
    assert gh._request("GET", "/repos/o/n") == {"stars": 42}
    assert gh._request("GET", "/repos/o/n") == {"stars": 42}  # 304 -> cached
    assert gh.metrics.etag_hits == 1


def test_paginate_follows_next_link():
    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page", "1")
        if page == "1":
            link = '<https://api.github.com/repos/o/n/issues?page=2>; rel="next"'
            return _json_response(200, [{"id": 1}], headers={"link": link})
        return _json_response(200, [{"id": 2}])

    gh = _client(handler)
    pages = list(gh.paginate("/repos/o/n/issues", {"per_page": 1}))
    assert pages == [[{"id": 1}], [{"id": 2}]]


def test_count_contributors_uses_last_page():
    def handler(request: httpx.Request) -> httpx.Response:
        page = request.url.params.get("page", "1")
        if page == "1":
            link = ('<https://api.github.com/repos/o/n/contributors?per_page=100&page=3>; '
                    'rel="last"')
            return _json_response(200, [{"login": f"u{i}"} for i in range(100)],
                                  headers={"link": link})
        return _json_response(200, [{"login": f"u{i}"} for i in range(25)])

    gh = _client(handler)
    assert gh.count_contributors("o", "n") == 225


def test_commit_activity_202_then_200(monkeypatch):
    monkeypatch.setattr(gh_mod, "sleep", lambda s: None)
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(202)
        return _json_response(200, [{"week": 1, "total": 7}])

    gh = _client(handler)
    data = gh.get_commit_activity("o", "n")
    assert data == [{"week": 1, "total": 7}]
    assert calls["n"] == 3


def test_request_metrics_recorded():
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(200, {})

    gh = _client(handler)
    gh.get_repo("octocat", "hello")
    gh.search_repositories("stars:>10")
    summary = gh.metrics.summary()
    assert summary["total_requests"] == 2
    assert summary["by_endpoint"]["/repos/{owner}/{repo}"] == 1
    assert summary["by_endpoint"]["/search/repositories"] == 1
    assert len(gh.drain_call_log()) == 2
    assert len(gh.drain_call_log()) == 0  # drained
