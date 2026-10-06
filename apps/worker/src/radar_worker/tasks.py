"""APScheduler job functions for the worker.

Jobs (each independently runnable and idempotent):
- discover_candidates  (30 min) — GitHub Search buckets -> repositories
- collect_snapshots    (5 min)  — due repos -> repository_snapshots (adaptive)
- calculate_scores     (10 min) — snapshots -> scores (+ corpus_stats refresh)
- classify_repositories(15 min) — category/status -> detections
- refresh_rankings     (15 min) — rankings leaderboard cache
- cleanup              (daily)  — downsample old snapshots, prune logs

Idempotency: every write uses ON CONFLICT DO NOTHING / upserts, so a job
can be re-run or double-run safely. Cross-process exclusion uses Postgres
advisory locks (pg_try_advisory_lock).
"""

from __future__ import annotations

import signal
import threading
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, Iterator

from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import func as sa_func
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from . import collector, discovery
from .config import WorkerSettings, get_settings
from .db import Database
from .github import GitHubClient, NoTokenError
from .log import get_logger, setup_logging
from .scoring_bridge import (
    CORPUS_METRICS,
    SCORING_AVAILABLE,
    classify_category as _scoring_classify_category,
    corpus_transform,
    load_corpus_stats,
    score_repository,
    snapshots_to_inputs,
    warn_if_unavailable,
)

log = get_logger(__name__)


# --------------------------------------------------------------------------- #
# Context & locking
# --------------------------------------------------------------------------- #
@dataclass
class WorkerContext:
    settings: WorkerSettings
    db: Database
    models: Any
    _gh: GitHubClient | None = None

    @property
    def gh(self) -> GitHubClient:
        if self._gh is None:
            if not self.settings.has_github_token:
                raise NoTokenError(
                    "GITHUB_TOKENS is empty — live GitHub jobs cannot run. "
                    "Use 'radar seed-demo' for a token-free demo dataset."
                )
            self._gh = GitHubClient(
                self.settings.github_tokens,
                timeout=self.settings.gh_timeout_seconds,
                max_retries=self.settings.gh_max_retries,
                rate_limit_threshold=self.settings.gh_rate_limit_threshold,
                max_rate_limit_wait=self.settings.gh_max_rate_limit_wait_seconds,
            )
        return self._gh

    def close(self) -> None:
        if self._gh is not None:
            self._gh.close()
        self.db.dispose()


class WorkerBusy(RuntimeError):
    """Another worker instance holds the advisory lock for this job."""


@contextmanager
def advisory_lock(session: Session, job_name: str) -> Iterator[None]:
    key = f"radar_worker:{job_name}"
    locked = session.execute(
        text("SELECT pg_try_advisory_lock(hashtext(:k))"), {"k": key}
    ).scalar()
    if not locked:
        raise WorkerBusy(job_name)
    try:
        yield
    finally:
        session.execute(
            text("SELECT pg_advisory_unlock(hashtext(:k))"), {"k": key}
        )


def _run_guarded(ctx: WorkerContext, name: str, fn: Callable[[WorkerContext, Session], None]) -> None:
    log.info("job start", extra={"job": name})
    try:
        with ctx.db.session_scope() as session:
            with advisory_lock(session, name):
                fn(ctx, session)
    except WorkerBusy:
        log.warning("job skipped: lock held by another worker", extra={"job": name})
    except Exception:
        log.error("job failed", extra={"job": name}, exc_info=True)
    else:
        log.info("job done", extra={"job": name})


# --------------------------------------------------------------------------- #
# Rule-based category classifier (CONTRACT §3 classify_category)
# --------------------------------------------------------------------------- #
# Priority-ordered: the first matching category is the primary one.
_CATEGORY_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("LLM", ("llm", "large language model", "gpt", "chatgpt", "transformer",
             "llama", "mistral", "mixtral", "gemma", "qwen", "deepseek",
             "prompt engineering", "langchain", "vllm", "ollama", "rag",
             "retrieval-augmented", "inference engine", "tokenizer")),
    ("Agents", ("ai agent", "agent framework", "autonomous agent", "multi-agent",
               "multi agent", "tool calling", "function calling", "agentic",
               "computer use")),
    ("AI", ("machine learning", "deep learning", "neural network",
            "artificial intelligence", "computer vision", "reinforcement learning",
            "mlops", "pytorch", "tensorflow", "jax", "scikit", "huggingface",
            "stable diffusion", "generative ai")),
    ("Security", ("security", "vulnerability", "cve", "exploit", "pentest",
                  "penetration test", "malware", "cryptograph", "infosec",
                  "appsec", "zero-day", "fuzzing", "sast")),
    ("Database", ("database", "postgres", "mysql", "sqlite", "vector database",
                  "vector db", "orm", "query engine", "redis", "mongodb",
                  "clickhouse", "duckdb")),
    ("Infrastructure", ("kubernetes", "docker", "terraform", "devops",
                        "cloud native", "serverless", "infrastructure as code",
                        "helm", "ansible", "observability", "prometheus",
                        "grafana", "service mesh")),
    ("Data", ("data pipeline", "etl", "dataframe", "data engineering",
              "analytics", "apache spark", "airflow", "dbt", "data science",
              "pandas", "polars", "data warehouse", "streaming data")),
    ("DevTools", ("developer tool", "cli", "command line", "linter", "formatter",
                  "debugger", "vscode", "neovim", "sdk", "build tool", "ci/cd",
                  "terminal", "git ", "package manager", "bundler")),
    ("Web", ("react", "next.js", "vue", "svelte", "frontend", "web framework",
             "rest api", "graphql", "web app", "webapp", "javascript",
             "typescript", "webassembly", "wasm", "ssr")),
    ("Mobile", ("android", "ios", "flutter", "react native", "swift", "kotlin",
                "mobile app")),
    ("Research", ("arxiv", "paper implementation", "benchmark", "research",
                  "survey", "state-of-the-art", "sota", "reproducibility")),
    ("Hardware", ("embedded", "arduino", "raspberry pi", "fpga", "hardware",
                  "iot", "robotics", "microcontroller", "esp32")),
    ("Games", ("game engine", "unity", "godot", "unreal engine", "pygame",
               "roguelike", "game ")),
]

_VALID_CATEGORIES = {c for c, _ in _CATEGORY_KEYWORDS} | {"Other"}


def classify_category(
    description: str | None,
    topics: list[str] | None,
    language: str | None,
    readme_excerpt: str | None = None,
) -> list[str]:
    """Deterministic rule-based classifier -> ordered category list.

    Matches CONTRACT §3's ``classify_category`` signature. The worker does not
    fetch READMEs (quota); ``readme_excerpt`` is accepted for forward
    compatibility and may be wired to an LLM classifier later.
    """
    haystack = " ".join(
        part for part in [
            description or "",
            " ".join(topics or []),
            language or "",
            readme_excerpt or "",
        ] if part
    ).lower()
    matched = [
        category
        for category, keywords in _CATEGORY_KEYWORDS
        if any(kw in haystack for kw in keywords)
    ]
    # Deduplicate while preserving priority order; cap at 3.
    seen: list[str] = []
    for c in matched:
        if c not in seen:
            seen.append(c)
        if len(seen) == 3:
            break
    return seen or ["Other"]


def _simple_status(score: float) -> str:
    """Threshold fallback when radar_scoring is unavailable (no hysteresis)."""
    if score >= 85:
        return "viral"
    if score >= 70:
        return "breakout"
    if score >= 50:
        return "rising"
    if score >= 30:
        return "emerging"
    return "normal"


_STATUS_FIRST_SEEN_COLUMN = {
    "emerging": "first_emerging_at",
    "rising": "first_rising_at",
    "breakout": "first_breakout_at",
    "viral": "first_viral_at",
}


# --------------------------------------------------------------------------- #
# Jobs
# --------------------------------------------------------------------------- #
def discover_candidates(
    ctx: WorkerContext, session: Session, *, only_bucket: str | None = None
) -> None:
    """Run discovery buckets and store new repositories."""
    config = discovery.load_discovery_config(ctx.settings.discovery_yaml)
    summary = discovery.run_discovery(
        ctx.gh, session, ctx.models, config, only_bucket=only_bucket
    )
    discovery.refresh_growing_tracked(session, ctx.models)
    collector.flush_api_call_log(ctx.gh, session, ctx.models)
    log.info("discovery summary", extra={"extra": summary})


def collect_snapshots(ctx: WorkerContext, session: Session) -> None:
    """Collect snapshots for all due repositories (adaptive intervals)."""
    summary = collector.run_collection(
        ctx.gh, session, ctx.models,
        batch_size=ctx.settings.collect_batch_size,
    )
    log.info("collection summary", extra={"extra": summary})


def _median(xs: list[float]) -> float:
    s = sorted(xs)
    n = len(s)
    mid = n // 2
    return (s[mid] + s[~mid]) / 2.0 if n else 0.0


def refresh_corpus_stats(
    session: Session, models: Any, *, min_samples: int = 10,
    max_age_minutes: int = 15,
) -> dict[str, dict[str, float]]:
    """Recompute median/MAD per metric from latest scores of tracked repos.

    Values are transformed with ``radar_scoring.corpus_transform`` (log1p /
    signed log1p) BEFORE the median/MAD so the stored stats live on the same
    scale that ``robust_norm`` expects. Skips the recompute when stats are
    fresher than ``max_age_minutes``.
    """
    Score = models.Score
    CorpusStat = models.CorpusStat
    now = datetime.now(timezone.utc)

    freshest = session.execute(
        select(sa_func.max(CorpusStat.updated_at))
    ).scalar_one_or_none()
    if freshest is not None and (now - freshest) < timedelta(minutes=max_age_minutes):
        return load_corpus_stats(session, models)

    # Latest score row per repository.
    max_ts = (
        select(Score.repository_id, sa_func.max(Score.ts).label("max_ts"))
        .group_by(Score.repository_id)
        .subquery()
    )
    latest_scores = session.execute(
        select(Score).join(
            max_ts,
            (Score.repository_id == max_ts.c.repository_id)
            & (Score.ts == max_ts.c.max_ts),
        )
    ).scalars().all()

    refreshed: dict[str, dict[str, float]] = {}
    for metric, signed in CORPUS_METRICS:
        values = [
            corpus_transform(float(getattr(s, metric)), signed=signed)
            for s in latest_scores
            if getattr(s, metric) is not None
        ]
        if len(values) < min_samples:
            log.info(
                "corpus stats: not enough samples, keeping previous",
                extra={"extra": {"metric": metric, "n": len(values)}},
            )
            continue
        med = _median(values)
        mad = _median([abs(v - med) for v in values]) or 1e-9
        stmt = pg_insert(CorpusStat).values(
            metric=metric, median=med, mad=mad,
            sample_count=len(values), updated_at=now,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["metric"],
            set_={"median": med, "mad": mad,
                  "sample_count": len(values), "updated_at": now},
        )
        session.execute(stmt)
        refreshed[metric] = {"median": med, "mad": mad}
    session.commit()
    log.info("corpus stats refreshed", extra={"extra": refreshed})
    return load_corpus_stats(session, models)


def _repos_needing_scores(
    session: Session, models: Any, *, limit: int
) -> list[Any]:
    """Repos whose newest snapshot is newer than their newest score (or unscored)."""
    Repository = models.Repository
    SnapshotT = models.RepositorySnapshot
    Score = models.Score

    max_snap = (
        select(SnapshotT.repository_id, sa_func.max(SnapshotT.ts).label("max_ts"))
        .group_by(SnapshotT.repository_id)
        .subquery()
    )
    max_score = (
        select(Score.repository_id, sa_func.max(Score.ts).label("max_ts"))
        .group_by(Score.repository_id)
        .subquery()
    )
    rows = session.execute(
        select(Repository)
        .join(max_snap, max_snap.c.repository_id == Repository.id)
        .outerjoin(max_score, max_score.c.repository_id == Repository.id)
        .where(
            (max_score.c.max_ts.is_(None)) | (max_snap.c.max_ts > max_score.c.max_ts)
        )
        .order_by(max_snap.c.max_ts.desc())
        .limit(limit)
    ).scalars().all()
    return list(rows)


def calculate_scores(ctx: WorkerContext, session: Session) -> None:
    """Score repos with fresh snapshots; refresh corpus stats first."""
    if not warn_if_unavailable("calculate_scores"):
        return
    corpus_stats = refresh_corpus_stats(session, ctx.models)
    repos = _repos_needing_scores(
        session, ctx.models, limit=ctx.settings.score_batch_size
    )
    now = datetime.now(timezone.utc)
    scored = 0
    Detection = getattr(ctx.models, "Detection", None)
    for repo in repos:
        snaps = session.execute(
            select(ctx.models.RepositorySnapshot)
            .where(ctx.models.RepositorySnapshot.repository_id == repo.id)
            .order_by(ctx.models.RepositorySnapshot.ts.desc())
            .limit(500)
        ).scalars().all()
        # snapshots_to_inputs sorts ascending; desc+limit keeps the *recent* 500.
        det = session.get(Detection, repo.id) if Detection is not None else None
        peak_score = (
            float(det.peak_score)
            if det is not None and det.peak_score is not None
            else None
        )
        row = score_repository(
            session, ctx.models, repo,
            snapshots_to_inputs(list(snaps), repo),
            corpus_stats, now=now,
            prev_status=repo.status or "normal",
            peak_score=peak_score,
            version="v1",
        )
        if row is None:
            continue
        stmt = pg_insert(ctx.models.Score).values(row)
        stmt = stmt.on_conflict_do_nothing(index_elements=["repository_id", "ts"])
        session.execute(stmt)
        scored += 1
        # Keep repositories.status roughly in sync even before classify runs.
        repo.status = row["status"]
    session.commit()
    log.info("scoring done", extra={"extra": {"candidates": len(repos), "scored": scored}})


def classify_repositories(ctx: WorkerContext, session: Session) -> None:
    """Category classification + status transitions + detections bookkeeping."""
    Repository = ctx.models.Repository
    Score = ctx.models.Score
    Detection = getattr(ctx.models, "Detection", None)

    # Latest score per repo, joined with the repo row.
    max_ts = (
        select(Score.repository_id, sa_func.max(Score.ts).label("max_ts"))
        .group_by(Score.repository_id)
        .subquery()
    )
    rows = session.execute(
        select(Repository, Score)
        .join(Score, Score.repository_id == Repository.id)
        .join(max_ts, (Score.repository_id == max_ts.c.repository_id)
              & (Score.ts == max_ts.c.max_ts))
    ).all()

    classified = 0
    _classify_status = None
    if SCORING_AVAILABLE:
        from .scoring_bridge import classify_status as _classify_status

    for repo, score in rows:
        # --- category (canonical implementation lives in radar_scoring;
        # fall back to the local rule-based copy when it is unavailable) ---
        _classifier = _scoring_classify_category or classify_category
        categories = _classifier(
            repo.description, list(repo.topics or []), repo.language
        )
        primary = categories[0] if categories else "Other"
        if repo.category != primary:
            repo.category = primary

        # --- status transition ---
        if _classify_status is not None:
            det = session.get(Detection, repo.id) if Detection else None
            peak_score = (
                float(det.peak_score)
                if det is not None and det.peak_score is not None
                else None
            )
            accel = (
                float(score.acceleration)
                if score.acceleration is not None
                else None
            )
            new_status = _classify_status(
                float(score.breakout_score),
                repo.status or "normal",
                peak_score,
                accel,
            )
        else:
            new_status = _simple_status(float(score.breakout_score))

        prev_status = repo.status or "normal"
        if new_status != prev_status:
            repo.status = new_status
            log.info(
                "status transition",
                extra={"extra": {"repo": repo.full_name,
                                 "from": prev_status, "to": new_status,
                                 "score": round(float(score.breakout_score), 1)}},
            )

        # --- detections bookkeeping ---
        if Detection is not None:
            det = session.get(Detection, repo.id)
            if det is None:
                det = Detection(
                    repository_id=repo.id,
                    first_detected_at=repo.detected_at,
                    stars_at_detection=repo.current_stars,
                )
                session.add(det)
            col = _STATUS_FIRST_SEEN_COLUMN.get(new_status)
            if col and getattr(det, col) is None:
                setattr(det, col, score.ts)
            if det.peak_score is None or float(score.breakout_score) > det.peak_score:
                det.peak_score = float(score.breakout_score)
                det.peak_at = score.ts
            det.growth_since_detection = repo.current_stars - det.stars_at_detection
        classified += 1
    session.commit()
    log.info("classification done", extra={"extra": {"repos": classified}})


def refresh_rankings(ctx: WorkerContext, session: Session) -> None:
    """Rebuild the rankings leaderboard cache (top N per bucket)."""
    Repository = ctx.models.Repository
    Score = ctx.models.Score
    Ranking = ctx.models.Ranking
    now = datetime.now(timezone.utc)
    top_n = ctx.settings.rankings_top_n

    max_ts = (
        select(Score.repository_id, sa_func.max(Score.ts).label("max_ts"))
        .group_by(Score.repository_id)
        .subquery()
    )
    latest = (
        select(Score.repository_id, Score.breakout_score, Score.ts)
        .join(max_ts, (Score.repository_id == max_ts.c.repository_id)
              & (Score.ts == max_ts.c.max_ts))
        .subquery()
    )

    # Buckets: all + per status + per category + per language.
    buckets: dict[str, Any] = {"all": None}
    for (status,) in session.execute(
        select(Repository.status).distinct()
    ).all():
        if status:
            buckets[f"status:{status}"] = ("status", status)
    for (cat,) in session.execute(
        select(Repository.category).where(Repository.category.is_not(None)).distinct()
    ).all():
        buckets[f"category:{cat}"] = ("category", cat)
    for (lang,) in session.execute(
        select(Repository.language).where(Repository.language.is_not(None)).distinct()
    ).all():
        buckets[f"lang:{lang}"] = ("language", lang)

    total_rows = 0
    for bucket, filtr in buckets.items():
        q = (
            select(Repository.id, latest.c.breakout_score)
            .join(latest, latest.c.repository_id == Repository.id)
        )
        if filtr is not None:
            column, value = filtr
            q = q.where(getattr(Repository, column) == value)
        q = q.order_by(latest.c.breakout_score.desc()).limit(top_n)
        entries = session.execute(q).all()
        rows = [
            {"ts": now, "bucket": bucket, "rank": i + 1,
             "repository_id": repo_id, "score": float(score)}
            for i, (repo_id, score) in enumerate(entries)
        ]
        if rows:
            stmt = pg_insert(Ranking).values(rows)
            stmt = stmt.on_conflict_do_nothing(
                index_elements=["bucket", "ts", "rank"]
            )
            session.execute(stmt)
            total_rows += len(rows)
    session.commit()
    log.info("rankings refreshed",
             extra={"extra": {"buckets": len(buckets), "rows": total_rows}})


def cleanup(ctx: WorkerContext, session: Session) -> None:
    """Downsample snapshots older than 90d (keep 1/day/repo); prune logs."""
    SnapshotT = ctx.models.RepositorySnapshot
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=90)

    # Keep the latest snapshot per (repository_id, day) before the cutoff.
    keep = (
        select(sa_func.max(SnapshotT.id))
        .where(SnapshotT.ts < cutoff)
        .group_by(
            SnapshotT.repository_id,
            sa_func.date_trunc("day", SnapshotT.ts),
        )
        .subquery()
    )
    deleted_snaps = session.execute(
        SnapshotT.__table__.delete()
        .where(SnapshotT.ts < cutoff)
        .where(~SnapshotT.id.in_(select(keep)))
    ).rowcount

    deleted_stats = 0
    if hasattr(ctx.models, "ApiRequestStat"):
        deleted_stats = session.execute(
            ctx.models.ApiRequestStat.__table__.delete().where(
                ctx.models.ApiRequestStat.ts < now - timedelta(days=7)
            )
        ).rowcount

    deleted_rankings = 0
    if hasattr(ctx.models, "Ranking"):
        deleted_rankings = session.execute(
            ctx.models.Ranking.__table__.delete().where(
                ctx.models.Ranking.ts < now - timedelta(days=30)
            )
        ).rowcount

    session.commit()
    log.info("cleanup done", extra={"extra": {
        "snapshots_deleted": deleted_snaps,
        "api_stats_deleted": deleted_stats,
        "rankings_deleted": deleted_rankings,
    }})


# --------------------------------------------------------------------------- #
# Scheduler
# --------------------------------------------------------------------------- #
JOBS: list[tuple[str, Callable[[WorkerContext, Session], None], str]] = [
    ("discover_candidates", discover_candidates, "discover_interval_min"),
    ("collect_snapshots", collect_snapshots, "collect_interval_min"),
    ("calculate_scores", calculate_scores, "score_interval_min"),
    ("classify_repositories", classify_repositories, "classify_interval_min"),
    ("refresh_rankings", refresh_rankings, "rankings_interval_min"),
    ("cleanup", cleanup, "cleanup_interval_min"),
]


def build_scheduler(ctx: WorkerContext) -> BackgroundScheduler:
    sched = BackgroundScheduler(timezone="UTC")
    for name, fn, interval_attr in JOBS:
        minutes = getattr(ctx.settings, interval_attr)
        sched.add_job(
            _run_guarded,
            "interval",
            minutes=minutes,
            id=name,
            args=[ctx, name, fn],
            max_instances=1,
            coalesce=True,
            misfire_grace_time=300,
        )
        log.info("job scheduled",
                 extra={"extra": {"job": name, "every_min": minutes}})
    return sched


def run_worker(ctx: WorkerContext, *, once: bool = False,
               only: list[str] | None = None) -> None:
    """Run the worker: once (sequential) or as a long-running scheduler."""
    setup_logging(ctx.settings.log_level, ctx.settings.log_json)
    selected = [
        (name, fn) for name, fn, _ in JOBS
        if only is None or name in only
    ]
    if once:
        for name, fn in selected:
            _run_guarded(ctx, name, fn)
        return
    sched = build_scheduler(ctx)
    stop = threading.Event()

    def _handle_signal(signum: int, _frame: Any) -> None:
        log.info("shutdown signal received", extra={"extra": {"signal": signum}})
        stop.set()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    sched.start()
    log.info("worker scheduler started; waiting for shutdown")
    stop.wait()
    log.info("shutting down scheduler")
    sched.shutdown(wait=True)
    ctx.close()


def make_context(settings: WorkerSettings | None = None) -> WorkerContext:
    settings = settings or get_settings()
    db = Database(settings)
    return WorkerContext(settings=settings, db=db, models=db.models)
