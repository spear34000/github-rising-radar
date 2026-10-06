"""GitHub API adapter (REST).

Design goals:
- Minimal API calls: ETag conditional requests, paginators, batched counts.
- Rate-limit discipline: every response's ``x-ratelimit-*`` headers are
  inspected; when remaining <= threshold we sleep until reset. Secondary
  rate limits (403 + Retry-After) get exponential backoff + jitter.
- Resilience: 5xx retried, other 4xx raised, no silent swallowing.
- Security: only ``owner``/``name`` are accepted from callers and strictly
  validated; request URLs are always assembled in code. User-supplied URLs
  are never fetched (no SSRF surface). Tokens come from env and are never
  logged.

Test hooks: module-level ``sleep`` / ``utcnow`` are patchable so unit tests
never really wait.
"""

from __future__ import annotations

import itertools
import random
import re
import time
from collections import Counter, deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterator

import httpx

from .log import get_logger

log = get_logger(__name__)

# Patchable in tests.
sleep = time.sleep


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


API_BASE = "https://api.github.com"
API_VERSION = "2022-11-28"

# GitHub login / repo name rules (usernames: 1-39 chars).
_OWNER_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
_FULL_NAME_RE = re.compile(
    r"^([A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?)/([A-Za-z0-9_.-]{1,100})$"
)
_LINK_NEXT_RE = re.compile(r'<([^>]+)>\s*;\s*rel="next"')
_LINK_LAST_RE = re.compile(r'<([^>]+)>\s*;\s*rel="last"')
_PAGE_RE = re.compile(r"[?&]page=(\d+)")


class NoTokenError(RuntimeError):
    """Raised when a live GitHub call is attempted without any token."""


class GitHubApiError(RuntimeError):
    def __init__(self, status_code: int, message: str, endpoint: str = "") -> None:
        super().__init__(f"GitHub API {status_code} on {endpoint}: {message}")
        self.status_code = status_code
        self.message = message
        self.endpoint = endpoint


class RateLimitExceeded(GitHubApiError):
    """Rate-limit reset is further away than the configured max wait."""


@dataclass
class RequestMetrics:
    total_requests: int = 0
    by_endpoint: Counter = field(default_factory=Counter)
    by_status: Counter = field(default_factory=Counter)
    rate_limit_hits: int = 0
    secondary_rate_limit_hits: int = 0
    retries: int = 0
    etag_hits: int = 0

    def summary(self) -> dict[str, Any]:
        return {
            "total_requests": self.total_requests,
            "by_endpoint": dict(self.by_endpoint),
            "by_status": dict(self.by_status),
            "rate_limit_hits": self.rate_limit_hits,
            "secondary_rate_limit_hits": self.secondary_rate_limit_hits,
            "retries": self.retries,
            "etag_hits": self.etag_hits,
        }


def validate_owner_name(owner: str, name: str) -> tuple[str, str]:
    """Strictly validate owner/name; raise ValueError on anything suspicious."""
    if not _OWNER_RE.match(owner):
        raise ValueError(f"invalid GitHub owner: {owner!r}")
    if not _NAME_RE.match(name) or name in (".", ".."):
        raise ValueError(f"invalid GitHub repo name: {name!r}")
    return owner, name


def parse_full_name(full_name: str) -> tuple[str, str]:
    """Parse and validate 'owner/repo'. Raises ValueError if malformed."""
    m = _FULL_NAME_RE.match(full_name.strip())
    if not m:
        raise ValueError(
            f"invalid repository full name {full_name!r}; expected 'owner/repo'"
        )
    return m.group(1), m.group(2)


def _endpoint_label(path: str) -> str:
    """Normalize a path for metrics, e.g. /repos/o/n/issues -> /repos/{owner}/{repo}/issues."""
    return re.sub(r"^(/repos/)[^/]+/[^/]+", r"\1{owner}/{repo}", path)


def _parse_link_next(link_header: str | None) -> str | None:
    if not link_header:
        return None
    m = _LINK_NEXT_RE.search(link_header)
    return m.group(1) if m else None


def _parse_link_last_page(link_header: str | None) -> int | None:
    if not link_header:
        return None
    m = _LINK_LAST_RE.search(link_header)
    if not m:
        return None
    pm = _PAGE_RE.search(m.group(1))
    return int(pm.group(1)) if pm else None


class GitHubClient:
    """Synchronous GitHub REST client with rate-limit handling and retries."""

    def __init__(
        self,
        tokens: list[str] | None,
        *,
        base_url: str = API_BASE,
        timeout: float = 30.0,
        max_retries: int = 5,
        rate_limit_threshold: int = 50,
        max_rate_limit_wait: int = 3600,
        user_agent: str = "github-rising-radar/0.1",
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.tokens = [t for t in (tokens or []) if t]
        self._token_cycle = itertools.cycle(self.tokens) if self.tokens else None
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.rate_limit_threshold = rate_limit_threshold
        self.max_rate_limit_wait = max_rate_limit_wait
        self.metrics = RequestMetrics()
        # Per-request call log for api_request_stats persistence (bounded).
        self._call_log: deque[tuple[str, int, datetime]] = deque(maxlen=10000)
        # ETag cache: cache_key -> (etag, parsed_json)
        self._etag_cache: dict[str, tuple[str, Any]] = {}
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            transport=transport,
            headers={
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": API_VERSION,
                "User-Agent": user_agent,
            },
        )

    # ------------------------------------------------------------------ #
    # context manager
    # ------------------------------------------------------------------ #
    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *exc: Any) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    # ------------------------------------------------------------------ #
    # internals
    # ------------------------------------------------------------------ #
    def _next_token(self) -> str | None:
        """Next token, or None when running unauthenticated (60 req/h)."""
        if self._token_cycle is None:
            return None
        return next(self._token_cycle)

    def _cache_key(self, method: str, url: str, params: dict[str, Any] | None) -> str:
        parts = [method.upper(), url]
        if params:
            parts.append("&".join(f"{k}={v}" for k, v in sorted(params.items())))
        return "|".join(parts)

    def _record_call(self, endpoint: str, status_code: int) -> None:
        self.metrics.total_requests += 1
        self.metrics.by_endpoint[endpoint] += 1
        self.metrics.by_status[status_code] += 1
        self._call_log.append((endpoint, status_code, utcnow()))

    def drain_call_log(self) -> list[tuple[str, int, datetime]]:
        """Return and clear the per-request call log (for DB persistence)."""
        items = list(self._call_log)
        self._call_log.clear()
        return items

    def _sleep_until_reset(self, reset_epoch: float, endpoint: str) -> None:
        wait = reset_epoch - utcnow().timestamp() + 2.0  # small buffer
        if wait <= 0:
            return
        if wait > self.max_rate_limit_wait:
            raise RateLimitExceeded(
                403,
                f"rate limit reset in {wait:.0f}s exceeds max wait "
                f"{self.max_rate_limit_wait}s",
                endpoint,
            )
        log.warning(
            "rate limit exhausted; sleeping until reset",
            extra={"extra": {"endpoint": endpoint, "wait_s": round(wait, 1)}},
        )
        sleep(wait)

    def _backoff_sleep(self, attempt: int, retry_after: float | None = None) -> None:
        base = retry_after if retry_after is not None else (2.0 * (2**attempt))
        delay = min(base + random.uniform(0, 1.0), 120.0)
        sleep(delay)

    def _check_rate_limit_headers(self, resp: httpx.Response, endpoint: str) -> None:
        """After any response: if remaining budget is low, wait for reset."""
        remaining = resp.headers.get("x-ratelimit-remaining")
        reset = resp.headers.get("x-ratelimit-reset")
        if remaining is None or reset is None:
            return
        try:
            if int(remaining) <= self.rate_limit_threshold:
                self.metrics.rate_limit_hits += 1
                self._sleep_until_reset(float(reset), endpoint)
        except ValueError:
            pass  # malformed headers: ignore

    def _request(
        self,
        method: str,
        path_or_url: str,
        params: dict[str, Any] | None = None,
    ) -> Any:
        """Core request with ETag, retries, and rate-limit handling.

        Returns parsed JSON (or cached JSON on 304).
        """
        is_absolute = path_or_url.startswith("http")
        url = path_or_url if is_absolute else f"{self.base_url}{path_or_url}"
        endpoint = _endpoint_label(path_or_url if not is_absolute else self._strip_base(url))
        token = self._next_token()
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        cache_key = self._cache_key(method, url, params)
        cached = self._etag_cache.get(cache_key)
        if cached is not None:
            headers["If-None-Match"] = cached[0]

        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._client.request(method, url, params=params, headers=headers)
            except (httpx.ConnectError, httpx.ReadTimeout, httpx.ConnectTimeout) as e:
                last_error = e
                self.metrics.retries += 1
                log.warning("transport error; retrying", extra={"extra": {"attempt": attempt}})
                self._backoff_sleep(attempt)
                continue

            self._record_call(endpoint, resp.status_code)
            self._check_rate_limit_headers(resp, endpoint)

            if resp.status_code == 304 and cached is not None:
                self.metrics.etag_hits += 1
                return cached[1]

            if 200 <= resp.status_code < 300:
                etag = resp.headers.get("etag")
                data = resp.json()
                if etag:
                    self._etag_cache[cache_key] = (etag, data)
                return data

            if resp.status_code == 403:
                retry_after = resp.headers.get("retry-after")
                body = resp.text.lower()
                if retry_after is not None or "secondary rate limit" in body:
                    self.metrics.secondary_rate_limit_hits += 1
                    self.metrics.retries += 1
                    log.warning(
                        "secondary rate limit; backing off",
                        extra={"extra": {"endpoint": endpoint, "attempt": attempt}},
                    )
                    self._backoff_sleep(
                        attempt,
                        float(retry_after) if retry_after else None,
                    )
                    last_error = GitHubApiError(403, "secondary rate limit", endpoint)
                    continue
                remaining = resp.headers.get("x-ratelimit-remaining")
                if remaining == "0":
                    # Primary limit exhausted without Retry-After: wait for reset.
                    reset = resp.headers.get("x-ratelimit-reset")
                    self.metrics.rate_limit_hits += 1
                    self.metrics.retries += 1
                    self._sleep_until_reset(float(reset) if reset else 60.0, endpoint)
                    last_error = GitHubApiError(403, "rate limit exhausted", endpoint)
                    continue
                raise GitHubApiError(403, self._error_message(resp), endpoint)

            if resp.status_code == 429:
                self.metrics.retries += 1
                retry_after = resp.headers.get("retry-after")
                log.warning("429 too many requests; backing off")
                self._backoff_sleep(
                    attempt, float(retry_after) if retry_after else None
                )
                last_error = GitHubApiError(429, "too many requests", endpoint)
                continue

            if 500 <= resp.status_code < 600:
                self.metrics.retries += 1
                log.warning(
                    "server error; retrying",
                    extra={"extra": {"status": resp.status_code, "attempt": attempt}},
                )
                self._backoff_sleep(attempt)
                last_error = GitHubApiError(
                    resp.status_code, self._error_message(resp), endpoint
                )
                continue

            # Other 4xx (400/401/404/422...): not retried.
            raise GitHubApiError(resp.status_code, self._error_message(resp), endpoint)

        raise GitHubApiError(
            599, f"max retries exceeded ({self.max_retries}): {last_error}", endpoint
        )

    @staticmethod
    def _strip_base(url: str) -> str:
        if url.startswith(API_BASE):
            return url[len(API_BASE):]
        return url

    @staticmethod
    def _error_message(resp: httpx.Response) -> str:
        try:
            data = resp.json()
            if isinstance(data, dict) and "message" in data:
                return str(data["message"])[:300]
        except Exception:
            pass
        return resp.text[:300]

    # ------------------------------------------------------------------ #
    # paginator
    # ------------------------------------------------------------------ #
    def paginate(
        self, path: str, params: dict[str, Any] | None = None, *, max_pages: int = 10
    ) -> Iterator[list[Any]]:
        """Yield pages of list results, following Link rel=next.

        Uses the raw next URL (params already encoded in it).
        """
        next_url: str | None = path
        next_params = dict(params or {})
        for _ in range(max_pages):
            assert next_url is not None
            # We need the raw response for Link headers, so go one level down.
            token = self._next_token()
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            url = next_url if next_url.startswith("http") else f"{self.base_url}{next_url}"
            resp = self._client.get(url, params=next_params, headers=headers)
            endpoint = _endpoint_label(self._strip_base(url))
            self._record_call(endpoint, resp.status_code)
            self._check_rate_limit_headers(resp, endpoint)
            if resp.status_code != 200:
                raise GitHubApiError(resp.status_code, self._error_message(resp), endpoint)
            data = resp.json()
            yield data if isinstance(data, list) else []
            nxt = _parse_link_next(resp.headers.get("link"))
            if not nxt:
                break
            next_url, next_params = nxt, None
        else:
            log.warning("paginate hit max_pages", extra={"extra": {"path": path}})

    # ------------------------------------------------------------------ #
    # public API
    # ------------------------------------------------------------------ #
    def get_repo(self, owner: str, name: str) -> dict[str, Any]:
        validate_owner_name(owner, name)
        return self._request("GET", f"/repos/{owner}/{name}")

    def search_repositories(
        self,
        query: str,
        *,
        sort: str = "stars",
        order: str = "desc",
        per_page: int = 30,
        page: int = 1,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            "/search/repositories",
            {"q": query, "sort": sort, "order": order, "per_page": per_page, "page": page},
        )

    def count_contributors(self, owner: str, name: str) -> int | None:
        """Best-effort contributor count using Link rel=last pagination.

        Returns None on failure (caller stores NULL, never fabricates).
        """
        validate_owner_name(owner, name)
        try:
            token = self._next_token()
            headers = {"Authorization": f"Bearer {token}"} if token else {}
            resp = self._client.get(
                f"{self.base_url}/repos/{owner}/{name}/contributors",
                params={"per_page": 100, "anon": "1"},
                headers=headers,
            )
            endpoint = "/repos/{owner}/{repo}/contributors"
            self._record_call(endpoint, resp.status_code)
            self._check_rate_limit_headers(resp, endpoint)
            if resp.status_code != 200:
                return None
            first_page = resp.json()
            last_page_num = _parse_link_last_page(resp.headers.get("link"))
            if last_page_num is None or last_page_num <= 1:
                return len(first_page) if isinstance(first_page, list) else None
            # Fetch only the last page to compute the total cheaply.
            last = self._request(
                "GET",
                f"/repos/{owner}/{name}/contributors",
                {"per_page": 100, "anon": "1", "page": last_page_num},
            )
            last_len = len(last) if isinstance(last, list) else 0
            return (last_page_num - 1) * 100 + last_len
        except Exception as e:  # best-effort signal
            log.warning("count_contributors failed", extra={"extra": {"err": str(e)[:200]}})
            return None

    def get_commit_activity(self, owner: str, name: str) -> list[dict[str, Any]] | None:
        """52 weeks of commit activity. Returns None if unavailable.

        GitHub returns 202 while computing statistics; we poll a few times.
        """
        validate_owner_name(owner, name)
        token = self._next_token()
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        endpoint = "/repos/{owner}/{repo}/stats/commit_activity"
        for attempt in range(6):
            resp = self._client.get(
                f"{self.base_url}/repos/{owner}/{name}/stats/commit_activity",
                headers=headers,
            )
            self._record_call(endpoint, resp.status_code)
            self._check_rate_limit_headers(resp, endpoint)
            if resp.status_code == 200:
                data = resp.json()
                return data if isinstance(data, list) else None
            if resp.status_code == 202:
                log.info("commit activity computing; waiting")
                sleep(5)
                continue
            log.warning(
                "commit activity unavailable",
                extra={"extra": {"status": resp.status_code}},
            )
            return None
        log.warning("commit activity still computing after retries; giving up")
        return None

    def get_releases(
        self, owner: str, name: str, per_page: int = 5
    ) -> list[dict[str, Any]]:
        validate_owner_name(owner, name)
        data = self._request(
            "GET", f"/repos/{owner}/{name}/releases", {"per_page": per_page}
        )
        return data if isinstance(data, list) else []

    def count_open_prs(self, owner: str, name: str) -> int | None:
        """Open PR count via the search API (total_count only)."""
        validate_owner_name(owner, name)
        try:
            data = self._request(
                "GET",
                "/search/issues",
                {"q": f"repo:{owner}/{name} type:pr state:open", "per_page": 1},
            )
            total = data.get("total_count") if isinstance(data, dict) else None
            return int(total) if total is not None else None
        except Exception as e:
            log.warning("count_open_prs failed", extra={"extra": {"err": str(e)[:200]}})
            return None
