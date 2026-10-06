"""Shared query builder for repository cards.

A card needs, per repository, its latest score row, its latest snapshot row,
and the snapshot closest to (latest_snapshot_ts − 24h) for the 24h star gain.
The latest rows are located with ``GROUP BY repository_id / MAX(ts)``
subqueries and joined back to the row tables — a single query serves the
list/detail/ranking endpoints without scanning the snapshots table.

The 24h-gain reference snapshot must fall inside
``[latest_ts − 30h, latest_ts − 24h]`` (the 24h window plus the
``max(0.25·W, 15min)`` tolerance from docs/SCORING.md); otherwise the gain is
``None`` rather than fabricated.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Row, Select, and_, func, select, text
from sqlalchemy.orm import aliased

from .models import Repository, RepositorySnapshot, Score
from .schemas import RepoCard


@dataclass
class CardRefs:
    sc: Any  # aliased(Score): latest score row
    ls: Any  # aliased(RepositorySnapshot): latest snapshot row
    ps: Any  # aliased(RepositorySnapshot): ~24h-ago snapshot row


def card_select() -> tuple[Select, CardRefs]:
    """Base SELECT returning (Repository, <labeled card columns>).

    Callers add WHERE / ORDER BY / LIMIT. Rows are ``Row`` objects; pass them
    to :func:`row_to_card`.
    """
    score_ts_sq = (
        select(
            Score.repository_id.label("repository_id"),
            func.max(Score.ts).label("max_ts"),
        )
        .group_by(Score.repository_id)
        .subquery("score_ts")
    )
    snap_ts_sq = (
        select(
            RepositorySnapshot.repository_id.label("repository_id"),
            func.max(RepositorySnapshot.ts).label("max_ts"),
        )
        .group_by(RepositorySnapshot.repository_id)
        .subquery("snap_ts")
    )
    prev_ts_sq = (
        select(
            RepositorySnapshot.repository_id.label("repository_id"),
            func.max(RepositorySnapshot.ts).label("prev_ts"),
        )
        .join(
            snap_ts_sq,
            snap_ts_sq.c.repository_id == RepositorySnapshot.repository_id,
        )
        .where(
            RepositorySnapshot.ts <= snap_ts_sq.c.max_ts - text("interval '24 hours'"),
            RepositorySnapshot.ts >= snap_ts_sq.c.max_ts - text("interval '30 hours'"),
        )
        .group_by(RepositorySnapshot.repository_id)
        .subquery("prev_ts")
    )

    sc = aliased(Score)
    ls = aliased(RepositorySnapshot)
    ps = aliased(RepositorySnapshot)

    stmt = (
        select(
            Repository,
            sc.breakout_score.label("sc_breakout_score"),
            sc.organic_score.label("sc_organic_score"),
            sc.hype_risk.label("sc_hype_risk"),
            sc.status.label("sc_status"),
            sc.star_velocity_24h.label("sc_velocity_24h"),
            sc.acceleration.label("sc_acceleration"),
            sc.relative_growth.label("sc_relative_growth"),
            sc.score_breakdown.label("sc_breakdown"),
            sc.confidence.label("sc_confidence"),
            sc.scoring_version.label("sc_scoring_version"),
            sc.ts.label("sc_ts"),
            ls.stars.label("snap_stars"),
            ls.watchers.label("snap_watchers"),
            ls.open_issues.label("snap_open_issues"),
            ls.ts.label("snap_ts"),
            ps.stars.label("prev_stars"),
            ps.ts.label("prev_ts"),
        )
        .select_from(Repository)
        .outerjoin(score_ts_sq, score_ts_sq.c.repository_id == Repository.id)
        .outerjoin(
            sc,
            and_(sc.repository_id == Repository.id, sc.ts == score_ts_sq.c.max_ts),
        )
        .outerjoin(snap_ts_sq, snap_ts_sq.c.repository_id == Repository.id)
        .outerjoin(
            ls,
            and_(ls.repository_id == Repository.id, ls.ts == snap_ts_sq.c.max_ts),
        )
        .outerjoin(prev_ts_sq, prev_ts_sq.c.repository_id == Repository.id)
        .outerjoin(
            ps,
            and_(ps.repository_id == Repository.id, ps.ts == prev_ts_sq.c.prev_ts),
        )
    )
    return stmt, CardRefs(sc=sc, ls=ls, ps=ps)


def row_gain(mapping: Any) -> float | None:
    """24h star gain from the snapshot columns (None if unknown)."""
    snap_stars = mapping["snap_stars"]
    prev_stars = mapping["prev_stars"]
    if snap_stars is None or prev_stars is None:
        return None
    return float(snap_stars - prev_stars)


def row_acceleration_pct(mapping: Any) -> float | None:
    """Acceleration as % change of 24h velocity vs the previous 24h.

    The ``scores`` table stores the raw stars/h delta (needed for scoring);
    the API always exposes the percent form, mirroring
    ``radar_scoring.acceleration_pct`` (kept inline to avoid a hard
    dependency here).
    """
    raw = mapping["sc_acceleration"]
    v24 = mapping["sc_velocity_24h"]
    if raw is None or v24 is None:
        return None
    v_prev = v24 - raw
    denom = max(abs(v_prev), 1.0)  # floor avoids division explosions
    return round(raw / denom * 100.0, 1)


def row_to_card(row: Row, now: datetime) -> RepoCard:
    """Build a :class:`RepoCard` from a :func:`card_select` row."""
    repo = row[0]
    if not isinstance(repo, Repository):  # pragma: no cover - defensive
        raise TypeError("card_select rows must start with a Repository entity")
    m = row._mapping
    gain = row_gain(m)
    confidence = m["sc_confidence"]
    insufficient = m["sc_breakout_score"] is None or (
        confidence is not None and confidence < 0.5
    )
    age_days: int | None = None
    if repo.created_at is not None:
        age_days = max(0, (now - repo.created_at).days)
    breakdown = m["sc_breakdown"] or {}
    return RepoCard(
        id=repo.id,
        owner=repo.owner,
        name=repo.name,
        full_name=repo.full_name,
        description=repo.description,
        url=repo.url,
        language=repo.language,
        license=repo.license,
        category=[repo.category] if repo.category else [],
        stars=repo.current_stars or 0,
        forks=repo.current_forks or 0,
        age_days=age_days,
        stars_24h_gain=gain,
        velocity_24h=m["sc_velocity_24h"],
        acceleration=row_acceleration_pct(m),
        relative_growth=m["sc_relative_growth"],
        breakout_score=m["sc_breakout_score"],
        organic_score=m["sc_organic_score"],
        hype_risk=m["sc_hype_risk"],
        status=m["sc_status"] or repo.status or "normal",
        detected_at=repo.detected_at,
        score_breakdown=dict(breakdown),
        insufficient_history=bool(insufficient),
    )
