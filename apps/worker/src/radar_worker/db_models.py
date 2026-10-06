"""CONTRACT-exact SQLAlchemy models (fallback).

The canonical models live in ``radar_api.models`` (apps/api). When that
package is installed (``pip install -e ".[api]"``), ``radar_worker.db``
uses it. Until then — or when running the worker standalone — these
fallback models are used. They mirror CONTRACT.md §2 column-for-column,
so rows written here are fully compatible with the api package later.

Extra worker-owned tables (not in the contract, additive only):
- ``rankings``         — leaderboard cache (contract §2 describes its shape)
- ``corpus_stats``     — median/MAD per scoring metric for robust normalization
- ``api_request_stats``— GitHub API call log (feeds /api/stats api_calls_24h)
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    DateTime,
    Double,
    ForeignKey,
    Integer,
    Text,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


def _now_utc() -> datetime:
    from datetime import timezone

    return datetime.now(timezone.utc)


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = _uuid_pk()
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    owner: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    pushed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc
    )
    language: Mapped[str | None] = mapped_column(Text, nullable=True)
    license: Mapped[str | None] = mapped_column(Text, nullable=True)
    archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    fork: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    current_stars: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    current_forks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    topics: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, nullable=False)
    status: Mapped[str] = mapped_column(Text, default="normal", nullable=False)
    poll_interval_seconds: Mapped[int] = mapped_column(Integer, default=21600, nullable=False)
    next_poll_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_snapshot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RepositorySnapshot(Base):
    __tablename__ = "repository_snapshots"

    id: Mapped[uuid.UUID] = _uuid_pk()
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stars: Mapped[int] = mapped_column(Integer, nullable=False)
    forks: Mapped[int] = mapped_column(Integer, nullable=False)
    watchers: Mapped[int] = mapped_column(Integer, nullable=False)
    open_issues: Mapped[int] = mapped_column(Integer, nullable=False)
    open_prs: Mapped[int] = mapped_column(Integer, nullable=False)
    contributors_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commit_count_7d: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_release_14d: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )


class Score(Base):
    __tablename__ = "scores"

    id: Mapped[uuid.UUID] = _uuid_pk()
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    star_velocity_1h: Mapped[float | None] = mapped_column(Double, nullable=True)
    star_velocity_6h: Mapped[float | None] = mapped_column(Double, nullable=True)
    star_velocity_24h: Mapped[float | None] = mapped_column(Double, nullable=True)
    star_velocity_7d: Mapped[float | None] = mapped_column(Double, nullable=True)
    acceleration: Mapped[float | None] = mapped_column(Double, nullable=True)
    relative_growth: Mapped[float | None] = mapped_column(Double, nullable=True)
    fork_velocity_24h: Mapped[float | None] = mapped_column(Double, nullable=True)
    fork_star_ratio: Mapped[float | None] = mapped_column(Double, nullable=True)
    activity_score: Mapped[float | None] = mapped_column(Double, nullable=True)
    age_bonus: Mapped[float | None] = mapped_column(Double, nullable=True)
    breakout_score: Mapped[float] = mapped_column(Double, nullable=False)
    organic_score: Mapped[float | None] = mapped_column(Double, nullable=True)
    hype_risk: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    score_breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False)
    scoring_version: Mapped[str] = mapped_column(Text, default="v1", nullable=False)
    confidence: Mapped[float | None] = mapped_column(Double, nullable=True)


class Detection(Base):
    __tablename__ = "detections"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True
    )
    first_detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    stars_at_detection: Mapped[int] = mapped_column(Integer, nullable=False)
    first_emerging_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_rising_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_breakout_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    first_viral_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    peak_score: Mapped[float | None] = mapped_column(Double, nullable=True)
    peak_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    growth_since_detection: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class Ranking(Base):
    """Leaderboard cache. Unique(bucket, ts, rank)."""

    __tablename__ = "rankings"

    id: Mapped[uuid.UUID] = _uuid_pk()
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    bucket: Mapped[str] = mapped_column(Text, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[float] = mapped_column(Double, nullable=False)


class CorpusStat(Base):
    """Robust-normalization reference: median/MAD per metric over tracked repos."""

    __tablename__ = "corpus_stats"

    metric: Mapped[str] = mapped_column(Text, primary_key=True)
    median: Mapped[float] = mapped_column(Double, nullable=False)
    mad: Mapped[float] = mapped_column(Double, nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc, onupdate=_now_utc
    )


class ApiRequestStat(Base):
    """Lightweight GitHub API call log (aggregated by /api/stats). Pruned after 7 days."""

    __tablename__ = "api_request_stats"

    id: Mapped[uuid.UUID] = _uuid_pk()
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    ts: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=_now_utc, server_default=func.now()
    )


class ExternalMention(Base):
    """Extension hook for HN/Reddit/Lobsters/news mentions (MVP: table only)."""

    __tablename__ = "external_mentions"

    id: Mapped[uuid.UUID] = _uuid_pk()
    repository_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)  # hn|reddit|lobsters|news
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    ts: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    score: Mapped[int | None] = mapped_column(Integer, nullable=True)
