"""Bridge between worker tasks and the ``radar_scoring`` package.

Real ``radar_scoring`` API (packages/scoring/src/radar_scoring/scoring.py)::

    compute_metrics(snaps: list[Snapshot], age_days: float,
                    now: datetime | None = None) -> Metrics
    compute_breakout(m: Metrics, corpus: CorpusStats,
                     prev_status: str = "normal",
                     peak_score_7d: float | None = None,
                     version: str = "v1") -> BreakoutResult
    classify_status(score: float, prev_status: str = "normal",
                    peak_score_7d: float | None = None,
                    acceleration: float | None = None) -> str
    explain_score(m: Metrics, repo_full_name: str) -> str
    acceleration_pct(m: Metrics) -> float | None   # API-facing % unit
    corpus_transform(value: float, signed: bool = False) -> float

If ``radar_scoring`` is not installed, ``SCORING_AVAILABLE`` is False and the
scoring tasks skip with a warning instead of crashing — discovery and
collection keep working.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from .log import get_logger

log = get_logger(__name__)

try:
    from radar_scoring import (  # type: ignore[import-not-found]
        CorpusStats,
        Snapshot as ScoringSnapshot,
        acceleration_pct,
        classify_category,
        classify_status,
        compute_breakout,
        compute_metrics,
        corpus_transform,
        explain_score,
    )

    SCORING_AVAILABLE = True
    _IMPORT_ERROR: Exception | None = None
except ImportError as e:  # packages/scoring not installed yet
    SCORING_AVAILABLE = False
    _IMPORT_ERROR = e
    CorpusStats = None  # type: ignore[assignment]
    ScoringSnapshot = None  # type: ignore[assignment]
    acceleration_pct = None  # type: ignore[assignment]
    classify_category = None  # type: ignore[assignment]
    classify_status = None  # type: ignore[assignment]
    compute_metrics = None  # type: ignore[assignment]
    compute_breakout = None  # type: ignore[assignment]
    corpus_transform = None  # type: ignore[assignment]
    explain_score = None  # type: ignore[assignment]


def warn_if_unavailable(task_name: str) -> bool:
    """Log a warning when scoring is unavailable. Returns True if available."""
    if SCORING_AVAILABLE:
        return True
    log.warning(
        "skipping task: radar_scoring package not installed",
        extra={"extra": {"task": task_name, "err": str(_IMPORT_ERROR)[:200]}},
    )
    return False


# Metrics consumed by compute_breakout's robust normalization.
# (metric_name, signed_transform?)
CORPUS_METRICS: tuple[tuple[str, bool], ...] = (
    ("star_velocity_24h", False),
    ("acceleration", True),
    ("relative_growth", False),
    ("fork_velocity_24h", False),
)


def snapshots_to_inputs(rows: list[Any], repo: Any = None) -> list[Any]:
    """Map ORM snapshot rows (or dicts) to ``radar_scoring.Snapshot`` inputs.

    Sorted oldest-first. ``has_release_14d`` comes from the snapshot row when
    the column exists, else False (never invented). ``pushed_at`` falls back
    to the repository row.
    """
    if not SCORING_AVAILABLE:
        return []
    out: list[Any] = []
    pushed_at = getattr(repo, "pushed_at", None) if repo is not None else None
    for r in rows:
        if isinstance(r, dict):
            get = r.get  # type: ignore[assignment]
        else:
            get = lambda k, _r=r: getattr(_r, k, None)  # noqa: E731
        out.append(
            ScoringSnapshot(
                ts=get("ts"),
                stars=int(get("stars") or 0),
                forks=int(get("forks") or 0),
                watchers=int(get("watchers") or 0),
                open_issues=int(get("open_issues") or 0),
                open_prs=int(get("open_prs") or 0),
                contributors_count=get("contributors_count"),
                commit_count_7d=get("commit_count_7d"),
                has_release_14d=bool(get("has_release_14d") or False),
                pushed_at=pushed_at,
            )
        )
    return sorted(out, key=lambda s: s.ts)


def load_corpus_stats(session: Any, models: Any) -> dict[str, dict[str, float]]:
    """Read median/MAD per metric from the corpus_stats table (log scale)."""
    stats: dict[str, dict[str, float]] = {}
    if not hasattr(models, "CorpusStat"):
        return stats
    for row in session.query(models.CorpusStat).all():
        stats[row.metric] = {"median": float(row.median), "mad": float(row.mad)}
    return stats


def corpus_stats_to_obj(stats: dict[str, dict[str, float]]) -> Any:
    """Convert the worker's dict form to ``radar_scoring.CorpusStats``."""
    return CorpusStats(
        {k: (v["median"], v["mad"]) for k, v in stats.items()}
    )


def score_repository(
    session: Any,
    models: Any,
    repo: Any,
    snapshots: list[Any],
    corpus_stats: dict[str, dict[str, float]],
    *,
    now: datetime,
    prev_status: str = "normal",
    peak_score: float | None = None,
    version: str = "v1",
) -> dict[str, Any] | None:
    """Run compute_metrics + compute_breakout; return a scores-row dict.

    Returns None when scoring is unavailable or inputs are insufficient.
    The ``scores.acceleration`` column stores the raw stars/h delta; the API
    layer converts it to percent via ``acceleration_pct`` for responses.
    """
    if not warn_if_unavailable("score_repository"):
        return None
    if len(snapshots) < 2:
        return None

    created_at = getattr(repo, "created_at", None)
    age_days = (
        (now - created_at).total_seconds() / 86400.0 if created_at else 0.0
    )
    metrics = compute_metrics(snapshots, age_days, now)
    result = compute_breakout(
        metrics,
        corpus_stats_to_obj(corpus_stats),
        prev_status=prev_status or "normal",
        peak_score_7d=peak_score,
        version=version,
    )

    breakdown = dict(getattr(result, "breakdown", {}) or {})
    return {
        "repository_id": repo.id,
        "ts": now,
        "star_velocity_1h": metrics.velocity_1h,
        "star_velocity_6h": metrics.velocity_6h,
        "star_velocity_24h": metrics.velocity_24h,
        "star_velocity_7d": metrics.velocity_7d,
        "acceleration": metrics.acceleration,
        "relative_growth": metrics.relative_growth,
        "fork_velocity_24h": metrics.fork_velocity_24h,
        "fork_star_ratio": metrics.fork_star_ratio,
        "activity_score": metrics.activity_score,
        "age_bonus": metrics.age_bonus_raw,
        "breakout_score": float(result.breakout_score),
        "organic_score": result.organic_score,
        "hype_risk": result.hype_risk,
        "status": result.status,
        "score_breakdown": breakdown,
        "scoring_version": version,
        "confidence": result.confidence,
    }


def describe_score(repo_full_name: str, snapshots: list[Any],
                   age_days: float, now: datetime,
                   corpus_stats: dict[str, dict[str, float]]) -> str | None:
    """Deterministic 'Why is this rising?' summary (grounded, no LLM)."""
    if not warn_if_unavailable("describe_score"):
        return None
    metrics = compute_metrics(snapshots, age_days, now)
    return explain_score(metrics, repo_full_name)
