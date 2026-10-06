"""Unit tests for radar_worker.discovery (pure logic; no DB, no network).

NOTE: not executed in this environment (no shell access); run with:
    cd apps/worker && pytest tests/test_discovery.py -q
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from radar_worker.discovery import (
    Bucket,
    SearchConfig,
    build_query,
    dedupe_by_github_id,
    discover_bucket,
    item_to_repo_row,
    load_discovery_config,
    needs_split,
    split_range,
)


def _bucket(**overrides):
    base = dict(
        name="new_recent",
        enabled=True,
        query_template="created:{start}..{end} stars:>={min_stars}",
        min_stars=20,
        lookback_days=31,
    )
    base.update(overrides)
    return Bucket(**base)


def _item(gid=1, stars=100, full_name="octo/repo"):
    owner, name = full_name.split("/")
    return {
        "id": gid,
        "full_name": full_name,
        "name": name,
        "owner": {"login": owner},
        "description": "a repo",
        "html_url": f"https://github.com/{full_name}",
        "created_at": "2026-09-01T00:00:00Z",
        "pushed_at": "2026-10-01T00:00:00Z",
        "language": "Python",
        "license": {"key": "mit"},
        "archived": False,
        "fork": False,
        "stargazers_count": stars,
        "forks_count": 10,
        "topics": ["cli"],
    }


# --------------------------------------------------------------------------- #
# query building / splitting
# --------------------------------------------------------------------------- #
def test_build_query():
    q = build_query(_bucket(), date(2026, 9, 1), date(2026, 10, 1))
    assert q == "created:2026-09-01..2026-10-01 stars:>=20"


def test_build_query_with_language():
    b = _bucket(query_template="language:{language} created:{start}..{end} stars:>={min_stars}",
                language="Rust")
    q = build_query(b, date(2026, 9, 1), date(2026, 9, 30))
    assert q == "language:Rust created:2026-09-01..2026-09-30 stars:>=20"


def test_split_range_covers_without_gaps_or_overlap():
    (s1, e1), (s2, e2) = split_range(date(2026, 9, 1), date(2026, 10, 1))
    assert s1 == date(2026, 9, 1)
    assert e1 < s2
    assert (s2 - e1).days == 1  # contiguous
    assert e2 == date(2026, 10, 1)


def test_split_range_single_day_is_stable():
    halves = split_range(date(2026, 9, 1), date(2026, 9, 1))
    assert halves[0] == halves[1] == (date(2026, 9, 1), date(2026, 9, 1))


def test_needs_split():
    assert needs_split(950, 950)
    assert needs_split(1200, 950)
    assert not needs_split(949, 950)


# --------------------------------------------------------------------------- #
# candidate mapping / dedup
# --------------------------------------------------------------------------- #
def test_item_to_repo_row():
    now = datetime.now(timezone.utc)
    row = item_to_repo_row(_item(gid=7, stars=123), now)
    assert row is not None
    assert row["github_id"] == 7
    assert row["full_name"] == "octo/repo"
    assert row["current_stars"] == 123
    assert row["license"] == "mit"
    assert row["next_poll_at"] == now


def test_item_to_repo_row_rejects_bad_payload():
    now = datetime.now(timezone.utc)
    assert item_to_repo_row({"nope": True}, now) is None
    assert item_to_repo_row({"id": "x", "full_name": 5}, now) is None


def test_dedupe_by_github_id_keeps_highest_stars():
    rows = [
        {"github_id": 1, "current_stars": 10},
        {"github_id": 1, "current_stars": 50},
        {"github_id": 2, "current_stars": 5},
    ]
    out = dedupe_by_github_id(rows)
    assert len(out) == 2
    assert {r["github_id"]: r["current_stars"] for r in out} == {1: 50, 2: 5}


# --------------------------------------------------------------------------- #
# bucket discovery with the 1000-result cap splitter (fake GitHub client)
# --------------------------------------------------------------------------- #
class FakeGH:
    """Canned search API: total_count depends on the date range in the query."""

    def __init__(self):
        self.calls: list[tuple[str, int]] = []

    def search_repositories(self, query, *, sort="stars", order="desc",
                            per_page=100, page=1):
        self.calls.append((query, page))
        # The full-month range overflows; any sub-range fits.
        if "2026-09-01..2026-10-01" in query:
            total = 1200
        else:
            total = 400
        items = [_item(gid=page * 1000 + i, stars=10 + i) for i in range(3)] \
            if page == 1 else []
        return {"total_count": total, "items": items}


def test_discover_bucket_splits_overflowing_range():
    gh = FakeGH()
    bucket = _bucket(lookback_days=30)
    search = SearchConfig(per_page=100, max_pages_per_query=10,
                          split_threshold=950, max_split_depth=4)
    rows = discover_bucket(gh, bucket, search, today=date(2026, 10, 1))

    queries = [q for q, _ in gh.calls]
    # The overflowing full-range query was issued, then two sub-range queries.
    assert any("2026-09-01..2026-10-01" in q for q in queries)
    sub_queries = [q for q in queries if "2026-09-01..2026-10-01" not in q]
    assert len(sub_queries) >= 2
    # Items were collected from the sub-ranges (page 1 each).
    assert len(rows) == 2 * 3


def test_discover_bucket_no_split_when_under_cap():
    gh = FakeGH()
    bucket = _bucket(lookback_days=7)
    search = SearchConfig(per_page=100, max_pages_per_query=10,
                          split_threshold=950, max_split_depth=4)
    rows = discover_bucket(gh, bucket, search, today=date(2026, 10, 1))
    # One query, page 1 only has items in the fake; 400 total -> 4 pages fetched.
    assert len({q for q, _ in gh.calls}) == 1
    assert len(rows) == 3


def test_load_discovery_config(tmp_path):
    p = tmp_path / "discovery.yaml"
    p.write_text(
        "version: 1\n"
        "search:\n  per_page: 50\n  split_threshold: 900\n"
        "buckets:\n"
        "  - name: b1\n    query_template: 'stars:>={min_stars}'\n"
        "    min_stars: 5\n    lookback_days: 3\n"
        "  - name: b2\n    enabled: false\n    query_template: 'x'\n"
        "filters:\n  skip_archived: false\n",
        encoding="utf-8",
    )
    cfg = load_discovery_config(p)
    assert cfg.search.per_page == 50
    assert cfg.search.split_threshold == 900
    assert [b.name for b in cfg.buckets] == ["b1", "b2"]
    assert cfg.skip_archived is False
