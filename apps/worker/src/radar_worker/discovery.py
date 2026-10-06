"""Candidate discovery: GitHub Search buckets -> repositories table.

Pipeline:
1. Load buckets from discovery.yaml.
2. For each bucket, walk its date range. For every sub-range, run the search
   query (page 1) and inspect total_count:
     - total_count >= split_threshold and range still splittable
       -> split the range in half and recurse (bounded depth).
     - otherwise -> fetch all pages (up to max_pages_per_query).
3. Deduplicate by github_id and bulk-insert with ON CONFLICT DO NOTHING.

The 1000-result Search API cap is therefore never silently truncated: any
bucket that would overflow is subdivided until each query fits, or the max
split depth is reached (logged as a warning).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import yaml
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .github import GitHubClient
from .log import get_logger

log = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Config structures
# --------------------------------------------------------------------------- #
@dataclass
class SearchConfig:
    per_page: int = 100
    max_pages_per_query: int = 10
    split_threshold: int = 950
    max_split_depth: int = 4
    sort: str = "stars"
    order: str = "desc"


@dataclass
class Bucket:
    name: str
    enabled: bool = True
    description: str = ""
    query_template: str = ""
    min_stars: int = 10
    lookback_days: int = 7
    language: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


@dataclass
class DiscoveryConfig:
    version: int = 1
    search: SearchConfig = field(default_factory=SearchConfig)
    buckets: list[Bucket] = field(default_factory=list)
    skip_archived: bool = True
    min_stargazers_fallback: int = 5


def load_discovery_config(path: str | Path) -> DiscoveryConfig:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"discovery config not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    search_raw = raw.get("search", {})
    search = SearchConfig(
        per_page=int(search_raw.get("per_page", 100)),
        max_pages_per_query=int(search_raw.get("max_pages_per_query", 10)),
        split_threshold=int(search_raw.get("split_threshold", 950)),
        max_split_depth=int(search_raw.get("max_split_depth", 4)),
        sort=str(search_raw.get("sort", "stars")),
        order=str(search_raw.get("order", "desc")),
    )
    buckets = []
    for b in raw.get("buckets", []):
        buckets.append(
            Bucket(
                name=b["name"],
                enabled=bool(b.get("enabled", True)),
                description=b.get("description", ""),
                query_template=b.get("query_template", ""),
                min_stars=int(b.get("min_stars", 10)),
                lookback_days=int(b.get("lookback_days", 7)),
                language=b.get("language"),
                extra={k: v for k, v in b.items() if k not in {
                    "name", "enabled", "description", "query_template",
                    "min_stars", "lookback_days", "language"}},
            )
        )
    filters = raw.get("filters", {})
    return DiscoveryConfig(
        version=int(raw.get("version", 1)),
        search=search,
        buckets=buckets,
        skip_archived=bool(filters.get("skip_archived", True)),
        min_stargazers_fallback=int(filters.get("min_stargazers_fallback", 5)),
    )


# --------------------------------------------------------------------------- #
# Query building / date-range splitting
# --------------------------------------------------------------------------- #
def build_query(bucket: Bucket, start: date, end: date) -> str:
    """Render a bucket's query template for a date range (inclusive)."""
    return bucket.query_template.format(
        start=start.isoformat(),
        end=end.isoformat(),
        min_stars=bucket.min_stars,
        language=bucket.language or "",
    ).strip()


def split_range(start: date, end: date) -> tuple[tuple[date, date], tuple[date, date]]:
    """Split [start, end] into two halves (inclusive date ranges)."""
    if end <= start:
        return (start, end), (start, end)
    total_days = (end - start).days
    mid = start + timedelta(days=total_days // 2)
    return (start, mid), (mid + timedelta(days=1), end)


def needs_split(total_count: int, threshold: int) -> bool:
    return total_count >= threshold


def _today_utc() -> date:
    return datetime.now(timezone.utc).date()


# --------------------------------------------------------------------------- #
# Candidate extraction
# --------------------------------------------------------------------------- #
def item_to_repo_row(item: dict[str, Any], now: datetime) -> dict[str, Any] | None:
    """Map a GitHub search result item to a repositories row dict.

    Returns None if the item is unusable (never raises on bad payloads).
    """
    try:
        github_id = int(item["id"])
        full_name = str(item["full_name"])
        owner = str(item["owner"]["login"])
        name = str(item["name"])
    except (KeyError, TypeError, ValueError):
        return None
    license_info = item.get("license") or {}
    created_raw = item.get("created_at")
    try:
        created_at = (
            datetime.fromisoformat(created_raw.replace("Z", "+00:00"))
            if created_raw
            else now
        )
    except (ValueError, AttributeError):
        created_at = now
    pushed_raw = item.get("pushed_at")
    try:
        pushed_at = (
            datetime.fromisoformat(pushed_raw.replace("Z", "+00:00"))
            if pushed_raw
            else None
        )
    except (ValueError, AttributeError):
        pushed_at = None
    return {
        "github_id": github_id,
        "owner": owner,
        "name": name,
        "full_name": full_name,
        "description": item.get("description"),
        "url": item.get("html_url") or f"https://github.com/{full_name}",
        "created_at": created_at,
        "pushed_at": pushed_at,
        "detected_at": now,
        "language": item.get("language"),
        "license": license_info.get("key") or license_info.get("spdx_id"),
        "archived": bool(item.get("archived", False)),
        "fork": bool(item.get("fork", False)),
        "current_stars": int(item.get("stargazers_count", 0) or 0),
        "current_forks": int(item.get("forks_count", 0) or 0),
        "topics": list(item.get("topics", []) or []),
        # First poll soon after discovery so we get a baseline snapshot fast.
        "next_poll_at": now,
    }


def dedupe_by_github_id(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Deduplicate candidate rows by github_id, keeping the highest-starred row."""
    best: dict[int, dict[str, Any]] = {}
    for row in rows:
        gid = row["github_id"]
        if gid not in best or row.get("current_stars", 0) > best[gid].get("current_stars", 0):
            best[gid] = row
    return list(best.values())


# --------------------------------------------------------------------------- #
# Discovery run
# --------------------------------------------------------------------------- #
def discover_bucket(
    gh: GitHubClient,
    bucket: Bucket,
    search: SearchConfig,
    *,
    today: date | None = None,
    collect_items: bool = True,
) -> list[dict[str, Any]]:
    """Run one bucket, splitting date ranges as needed. Returns candidate rows."""
    today = today or _today_utc()
    end = today
    start = today - timedelta(days=bucket.lookback_days)
    candidates: list[dict[str, Any]] = []
    # Stack of (start, end, depth) ranges to process.
    stack: list[tuple[date, date, int]] = [(start, end, 0)]
    while stack:
        r_start, r_end, depth = stack.pop()
        query = build_query(bucket, r_start, r_end)
        log.info(
            "search bucket query",
            extra={"extra": {"bucket": bucket.name, "query": query, "depth": depth}},
        )
        first = gh.search_repositories(
            query, sort=search.sort, order=search.order,
            per_page=search.per_page, page=1,
        )
        total = int(first.get("total_count", 0) or 0)
        items = first.get("items", []) or []
        if needs_split(total, search.split_threshold):
            if depth < search.max_split_depth and r_end > r_start:
                (s1, e1), (s2, e2) = split_range(r_start, r_end)
                # Avoid infinite loop on unsplittable 1-day ranges.
                if (s1, e1) != (r_start, r_end) and (s2, e2) != (r_start, r_end):
                    log.info(
                        "splitting overflowing query range",
                        extra={"extra": {
                            "bucket": bucket.name, "total": total,
                            "range": f"{r_start}..{r_end}", "depth": depth,
                        }},
                    )
                    stack.append((s1, e1, depth + 1))
                    stack.append((s2, e2, depth + 1))
                    continue
            log.warning(
                "query exceeds search cap and cannot be split further; "
                "results beyond 1000 are truncated",
                extra={"extra": {"bucket": bucket.name, "query": query, "total": total}},
            )
        # Only collect items for queries that fit: sub-ranges re-fetch
        # everything, and the parent page would just duplicate them.
        if collect_items:
            candidates.extend(items)
        # Fetch remaining pages of this (sub-)query.
        total_pages = min(
            (total + search.per_page - 1) // search.per_page,
            search.max_pages_per_query,
        )
        for page in range(2, total_pages + 1):
            page_data = gh.search_repositories(
                query, sort=search.sort, order=search.order,
                per_page=search.per_page, page=page,
            )
            if collect_items:
                candidates.extend(page_data.get("items", []) or [])
    now = datetime.now(timezone.utc)
    rows = []
    for item in candidates:
        row = item_to_repo_row(item, now)
        if row is not None:
            rows.append(row)
    return rows


def store_candidates(
    session: Session,
    models: Any,
    rows: list[dict[str, Any]],
    *,
    skip_archived: bool = True,
    min_stars: int = 5,
) -> tuple[int, int]:
    """Insert candidates with ON CONFLICT DO NOTHING on github_id.

    Also creates detections rows for newly inserted repositories.
    Returns (inserted, skipped).
    """
    Repository = models.Repository
    Detection = getattr(models, "Detection", None)
    now = datetime.now(timezone.utc)

    filtered = [
        r for r in rows
        if not (skip_archived and r.get("archived"))
        and r.get("current_stars", 0) >= min_stars
    ]
    unique_rows = dedupe_by_github_id(filtered)
    if not unique_rows:
        return 0, 0

    # Determine which github_ids are genuinely new so we can seed detections.
    existing_ids = set(
        session.execute(
            select(Repository.github_id).where(
                Repository.github_id.in_([r["github_id"] for r in unique_rows])
            )
        ).scalars().all()
    )
    new_rows = [r for r in unique_rows if r["github_id"] not in existing_ids]

    stmt = pg_insert(Repository).values(unique_rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["github_id"])
    result = session.execute(stmt)
    inserted = result.rowcount if result.rowcount is not None else 0

    # Seed detections for the new repositories (idempotent too).
    if new_rows and Detection is not None:
        # Map github_id -> repository id for the just-inserted rows.
        id_map = dict(
            session.execute(
                select(Repository.github_id, Repository.id).where(
                    Repository.github_id.in_([r["github_id"] for r in new_rows])
                )
            ).all()
        )
        det_rows = [
            {
                "repository_id": id_map[r["github_id"]],
                "first_detected_at": r.get("detected_at") or now,
                "stars_at_detection": r.get("current_stars", 0),
            }
            for r in new_rows
            if r["github_id"] in id_map
        ]
        if det_rows:
            dstmt = pg_insert(Detection).values(det_rows)
            dstmt = dstmt.on_conflict_do_nothing()
            session.execute(dstmt)

    skipped = len(unique_rows) - inserted
    return inserted, skipped


def run_discovery(
    gh: GitHubClient,
    session: Session,
    models: Any,
    config: DiscoveryConfig,
    *,
    only_bucket: str | None = None,
) -> dict[str, Any]:
    """Run all enabled buckets (or one) and store candidates."""
    summary: dict[str, Any] = {"buckets": {}, "inserted": 0, "skipped": 0}
    for bucket in config.buckets:
        if not bucket.enabled:
            continue
        if only_bucket and bucket.name != only_bucket:
            continue
        rows = discover_bucket(gh, bucket, config.search)
        inserted, skipped = store_candidates(
            session, models, rows,
            skip_archived=config.skip_archived,
            min_stars=config.min_stargazers_fallback,
        )
        session.commit()
        summary["buckets"][bucket.name] = {
            "candidates": len(rows), "inserted": inserted, "skipped": skipped
        }
        summary["inserted"] += inserted
        summary["skipped"] += skipped
        log.info(
            "bucket done",
            extra={"extra": {"bucket": bucket.name, "inserted": inserted,
                             "skipped": skipped}},
        )
    return summary


def refresh_growing_tracked(
    session: Session, models: Any, *, detected_within_days: int = 14
) -> int:
    """CONTRACT 'growing_tracked' bucket: recently discovered repos that are
    already accelerating get their next poll pulled forward to now."""
    Repository = models.Repository
    Score = models.Score
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=detected_within_days)

    # Latest score per repository: max ts per repo, then filter hot ones.
    from sqlalchemy import func as sa_func

    max_ts = (
        select(Score.repository_id, sa_func.max(Score.ts).label("max_ts"))
        .group_by(Score.repository_id)
        .subquery()
    )
    hot_repo_ids = session.execute(
        select(Score.repository_id)
        .join(max_ts, (Score.repository_id == max_ts.c.repository_id)
              & (Score.ts == max_ts.c.max_ts))
        .join(Repository, Repository.id == Score.repository_id)
        .where(Score.breakout_score >= 50)
        .where(Repository.detected_at >= cutoff)
    ).scalars().all()

    if not hot_repo_ids:
        return 0
    updated = (
        session.query(Repository)
        .filter(Repository.id.in_(hot_repo_ids))
        .update({Repository.next_poll_at: now}, synchronize_session=False)
    )
    session.commit()
    log.info("growing_tracked refresh", extra={"extra": {"repos": updated}})
    return updated
