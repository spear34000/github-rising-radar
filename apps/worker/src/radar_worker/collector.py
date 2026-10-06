"""Snapshot collector.

For every repository whose ``next_poll_at`` is due (claimed with
``FOR UPDATE SKIP LOCKED`` so multiple workers never double-collect):

1. Fetch repo metadata + contributors/commit-activity/releases from GitHub.
2. Insert one ``repository_snapshots`` row (ON CONFLICT DO NOTHING on
   (repository_id, ts) — duplicate polls of the same instant are skipped).
3. Update ``repositories`` current counters + ``last_snapshot_at``.
4. Recompute the adaptive poll interval from the latest breakout_score and
   set ``next_poll_at``.

Adaptive intervals (breakout_score):
    >= 80  -> 1h      (hot)
    >= 50  -> 3h      (warm)
    >= 30  -> 6h      (watch)
    else   -> 12h     (cold)
    no score yet -> 6h

All timestamps UTC. Failures for one repo never abort the batch.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from .github import GitHubClient
from .log import get_logger

log = get_logger(__name__)

# (min_score, interval_seconds)
_POLL_TIERS: list[tuple[float, int]] = [
    (80.0, 3600),    # hot
    (50.0, 10800),   # warm
    (30.0, 21600),   # watch
    (0.0, 43200),    # cold
]
_DEFAULT_INTERVAL_SECONDS = 21600  # 6h when no score exists yet


def poll_interval_for_score(breakout_score: float | None) -> int:
    """Adaptive polling interval from the latest breakout score."""
    if breakout_score is None:
        return _DEFAULT_INTERVAL_SECONDS
    for min_score, seconds in _POLL_TIERS:
        if breakout_score >= min_score:
            return seconds
    return _POLL_TIERS[-1][1]


def _parse_github_ts(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, AttributeError):
        return None


def fetch_due_repositories(
    session: Session, models: Any, *, limit: int, now: datetime
) -> list[Any]:
    """Claim up to ``limit`` due repos with FOR UPDATE SKIP LOCKED."""
    Repository = models.Repository
    stmt = (
        select(Repository)
        .where(
            (Repository.next_poll_at.is_(None)) | (Repository.next_poll_at <= now),
            Repository.archived.is_(False),
        )
        .order_by(Repository.next_poll_at.asc().nulls_first())
        .limit(limit)
        .with_for_update(skip_locked=True)
    )
    return list(session.execute(stmt).scalars().all())


def latest_breakout_score(
    session: Session, models: Any, repository_id: Any
) -> float | None:
    Score = models.Score
    return session.execute(
        select(Score.breakout_score)
        .where(Score.repository_id == repository_id)
        .order_by(Score.ts.desc())
        .limit(1)
    ).scalar_one_or_none()


def collect_repo_snapshot(
    gh: GitHubClient,
    session: Session,
    models: Any,
    repo: Any,
    *,
    now: datetime,
) -> bool:
    """Collect a single snapshot for ``repo``. Returns True if stored."""
    RepositorySnapshot = models.RepositorySnapshot
    Repository = models.Repository

    try:
        data = gh.get_repo(repo.owner, repo.name)
    except Exception as e:
        log.warning(
            "get_repo failed; repo will be retried on next poll",
            extra={"extra": {"repo": repo.full_name, "err": str(e)[:200]}},
        )
        # Push the poll forward a bit so one bad repo doesn't hot-loop.
        repo.next_poll_at = now + timedelta(minutes=30)
        return False

    # Best-effort enrichment signals (None -> NULL, never fabricated).
    # Each is independently guarded: one flaky endpoint must not kill
    # the whole snapshot.
    contributors = gh.count_contributors(repo.owner, repo.name)
    try:
        commit_activity = gh.get_commit_activity(repo.owner, repo.name)
    except Exception as e:
        log.warning(
            "get_commit_activity failed",
            extra={"extra": {"repo": repo.full_name, "err": str(e)[:200]}},
        )
        commit_activity = None
    commit_count_7d: int | None = None
    if commit_activity:
        try:
            # Last entry = trailing (partial) calendar week from /stats.
            commit_count_7d = int(commit_activity[-1].get("total", 0))
        except (IndexError, TypeError, ValueError, AttributeError):
            commit_count_7d = None
    try:
        releases = gh.get_releases(repo.owner, repo.name, per_page=5)
    except Exception:
        releases = []
    has_release_14d = False
    cutoff = now - timedelta(days=14)
    for rel in releases:
        pub = _parse_github_ts(rel.get("published_at") or rel.get("created_at"))
        if pub is not None and pub >= cutoff:
            has_release_14d = True
            break
    open_prs = gh.count_open_prs(repo.owner, repo.name)

    license_info = data.get("license") or {}
    stars = int(data.get("stargazers_count", 0) or 0)
    forks = int(data.get("forks_count", 0) or 0)

    snapshot_row = {
        "repository_id": repo.id,
        "ts": now,
        "stars": stars,
        "forks": forks,
        "watchers": int(data.get("subscribers_count", 0) or 0),
        "open_issues": int(data.get("open_issues_count", 0) or 0),
        # open_issues_count includes PRs on GitHub; open_prs is the precise count.
        # CONTRACT requires NOT NULL: fall back to 0 only when the API failed.
        "open_prs": open_prs if open_prs is not None else 0,
        "contributors_count": contributors,
        "commit_count_7d": commit_count_7d,
        "has_release_14d": has_release_14d,
    }
    stmt = pg_insert(RepositorySnapshot).values(snapshot_row)
    stmt = stmt.on_conflict_do_nothing(index_elements=["repository_id", "ts"])
    result = session.execute(stmt)
    stored = (result.rowcount or 0) > 0

    # Refresh the repository's current counters.
    repo.current_stars = stars
    repo.current_forks = forks
    repo.pushed_at = _parse_github_ts(data.get("pushed_at"))
    repo.language = data.get("language")
    repo.description = data.get("description")
    repo.archived = bool(data.get("archived", False))
    repo.topics = list(data.get("topics", []) or [])
    lic = license_info.get("key") or license_info.get("spdx_id")
    if lic:
        repo.license = lic
    if stored:
        repo.last_snapshot_at = now

    score = latest_breakout_score(session, models, repo.id)
    interval = poll_interval_for_score(score)
    repo.poll_interval_seconds = interval
    repo.next_poll_at = now + timedelta(seconds=interval)

    # Keep detections.growth_since_detection fresh.
    if hasattr(models, "Detection"):
        det = session.get(models.Detection, repo.id)
        if det is not None:
            det.growth_since_detection = stars - det.stars_at_detection

    log.info(
        "snapshot collected",
        extra={"extra": {
            "repo": repo.full_name, "stars": stars,
            "interval_s": interval, "stored": stored,
        }},
    )
    return stored


def run_collection(
    gh: GitHubClient,
    session: Session,
    models: Any,
    *,
    batch_size: int = 50,
    repository_id: Any | None = None,
) -> dict[str, Any]:
    """Collect snapshots for all due repos (or one repo by id for CLI)."""
    now = datetime.now(timezone.utc)
    Repository = models.Repository

    if repository_id is not None:
        repos = [session.get(Repository, repository_id)]
        repos = [r for r in repos if r is not None]
    else:
        repos = fetch_due_repositories(session, models, limit=batch_size, now=now)

    summary = {"attempted": len(repos), "stored": 0, "failed": 0}
    for repo in repos:
        try:
            if collect_repo_snapshot(gh, session, models, repo, now=now):
                summary["stored"] += 1
            session.commit()
        except Exception as e:
            session.rollback()
            summary["failed"] += 1
            log.error(
                "snapshot collection failed",
                extra={"extra": {"repo": getattr(repo, "full_name", "?"),
                                 "err": str(e)[:300]}},
            )
    # Persist GitHub API call metrics for /api/stats.
    flush_api_call_log(gh, session, models)
    session.commit()
    return summary


def flush_api_call_log(gh: GitHubClient, session: Session, models: Any) -> int:
    """Bulk-insert the client's per-request call log into api_request_stats."""
    if not hasattr(models, "ApiRequestStat"):
        gh.drain_call_log()
        return 0
    calls = gh.drain_call_log()
    if not calls:
        return 0
    rows = [
        {"endpoint": endpoint, "status_code": status, "ts": ts}
        for endpoint, status, ts in calls
    ]
    session.execute(pg_insert(models.ApiRequestStat).values(rows))
    return len(rows)


def pending_count(session: Session, models: Any) -> int:
    """How many repos are currently due for a snapshot."""
    Repository = models.Repository
    now = datetime.now(timezone.utc)
    return session.execute(
        select(sa_func.count())
        .select_from(Repository)
        .where(
            (Repository.next_poll_at.is_(None)) | (Repository.next_poll_at <= now),
            Repository.archived.is_(False),
        )
    ).scalar_one()
