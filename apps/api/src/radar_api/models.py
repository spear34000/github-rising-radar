"""SQLAlchemy 2 ORM models.

Table and column names match CONTRACT.md §2 exactly. All timestamps are
TIMESTAMPTZ (UTC). Do not rename anything here without updating the contract
and the Alembic migration (``alembic/versions/0001_initial.py``).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Double,
    ForeignKey,
    Index,
    Integer,
    Text,
    UniqueConstraint,
    Uuid,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TIMESTAMP
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Declarative base for all Radar models."""


TSTZ = TIMESTAMP(timezone=True)


class Repository(Base):
    __tablename__ = "repositories"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    github_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False)
    owner: Mapped[str] = mapped_column(Text, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    full_name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TSTZ, nullable=False)
    pushed_at: Mapped[datetime | None] = mapped_column(TSTZ, nullable=True)
    detected_at: Mapped[datetime] = mapped_column(
        TSTZ, nullable=False, server_default=text("now()")
    )
    language: Mapped[str | None] = mapped_column(Text, nullable=True)
    license: Mapped[str | None] = mapped_column(Text, nullable=True)  # SPDX key
    archived: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    fork: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    current_stars: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    current_forks: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    category: Mapped[str | None] = mapped_column(Text, nullable=True)
    topics: Mapped[list[str]] = mapped_column(
        ARRAY(Text), nullable=False, default=list, server_default=text("'{}'")
    )
    status: Mapped[str] = mapped_column(
        Text, nullable=False, default="normal", server_default=text("'normal'")
    )  # normal|emerging|rising|breakout|viral|cooling
    poll_interval_seconds: Mapped[int] = mapped_column(
        Integer, nullable=False, default=21600, server_default=text("21600")
    )
    next_poll_at: Mapped[datetime | None] = mapped_column(TSTZ, nullable=True)
    last_snapshot_at: Mapped[datetime | None] = mapped_column(TSTZ, nullable=True)

    snapshots: Mapped[list[RepositorySnapshot]] = relationship(
        back_populates="repository", cascade="all, delete-orphan", passive_deletes=True
    )
    scores: Mapped[list[Score]] = relationship(
        back_populates="repository", cascade="all, delete-orphan", passive_deletes=True
    )
    detection: Mapped[Detection | None] = relationship(
        back_populates="repository",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

    __table_args__ = (
        Index("ix_repositories_github_id", "github_id"),
        Index("ix_repositories_full_name", "full_name"),
        Index("ix_repositories_status", "status"),
        Index("ix_repositories_category", "category"),
        Index("ix_repositories_language", "language"),
    )


# Defined at module level so the DESC expression can reference the column.
Index("ix_repositories_current_stars_desc", Repository.current_stars.desc())


class RepositorySnapshot(Base):
    __tablename__ = "repository_snapshots"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(TSTZ, nullable=False)
    stars: Mapped[int] = mapped_column(Integer, nullable=False)
    forks: Mapped[int] = mapped_column(Integer, nullable=False)
    watchers: Mapped[int] = mapped_column(Integer, nullable=False)
    open_issues: Mapped[int] = mapped_column(Integer, nullable=False)
    open_prs: Mapped[int] = mapped_column(Integer, nullable=False)
    contributors_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    commit_count_7d: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_release_14d: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )  # release published in the 14 days before ts

    repository: Mapped[Repository] = relationship(back_populates="snapshots")

    __table_args__ = (
        UniqueConstraint("repository_id", "ts", name="uq_repository_snapshots_repo_ts"),
        Index(
            "ix_repository_snapshots_repo_ts",
            "repository_id",
            text("ts DESC"),
        ),
    )


class Score(Base):
    __tablename__ = "scores"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    ts: Mapped[datetime] = mapped_column(TSTZ, nullable=False)
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
    hype_risk: Mapped[str | None] = mapped_column(Text, nullable=True)  # low|medium|high
    status: Mapped[str] = mapped_column(Text, nullable=False)
    score_breakdown: Mapped[dict] = mapped_column(JSONB, nullable=False)
    scoring_version: Mapped[str] = mapped_column(
        Text, nullable=False, default="v1", server_default=text("'v1'")
    )
    confidence: Mapped[float | None] = mapped_column(Double, nullable=True)

    repository: Mapped[Repository] = relationship(back_populates="scores")

    __table_args__ = (
        UniqueConstraint("repository_id", "ts", name="uq_scores_repo_ts"),
        Index("ix_scores_repo_ts", "repository_id", text("ts DESC")),
        Index("ix_scores_breakout_ts", text("breakout_score DESC"), text("ts DESC")),
    )


class Detection(Base):
    __tablename__ = "detections"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repositories.id", ondelete="CASCADE"), primary_key=True
    )
    first_detected_at: Mapped[datetime] = mapped_column(TSTZ, nullable=False)
    stars_at_detection: Mapped[int] = mapped_column(Integer, nullable=False)
    first_emerging_at: Mapped[datetime | None] = mapped_column(TSTZ, nullable=True)
    first_rising_at: Mapped[datetime | None] = mapped_column(TSTZ, nullable=True)
    first_breakout_at: Mapped[datetime | None] = mapped_column(TSTZ, nullable=True)
    first_viral_at: Mapped[datetime | None] = mapped_column(TSTZ, nullable=True)
    peak_score: Mapped[float | None] = mapped_column(Double, nullable=True)
    peak_at: Mapped[datetime | None] = mapped_column(TSTZ, nullable=True)
    growth_since_detection: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    repository: Mapped[Repository] = relationship(back_populates="detection")


class Ranking(Base):
    """Leaderboard cache: rankings are READ from here, never computed by
    scanning the snapshots table per request (see CONTRACT.md §2)."""

    __tablename__ = "rankings"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    bucket: Mapped[str] = mapped_column(Text, nullable=False)
    ts: Mapped[datetime] = mapped_column(TSTZ, nullable=False)
    rank: Mapped[int] = mapped_column(Integer, nullable=False)
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    score: Mapped[float] = mapped_column(Double, nullable=False)

    __table_args__ = (
        UniqueConstraint("bucket", "ts", "rank", name="uq_rankings_bucket_ts_rank"),
        Index("ix_rankings_bucket_ts_rank", "bucket", "ts", "rank"),
    )


class CorpusStat(Base):
    """Corpus distribution stats used by the scoring engine for robust
    normalization (median/MAD per metric, on the transformed scale).
    One row per metric, upserted by the worker."""

    __tablename__ = "corpus_stats"

    metric: Mapped[str] = mapped_column(Text, primary_key=True)
    median: Mapped[float] = mapped_column(Double, nullable=False)
    mad: Mapped[float] = mapped_column(Double, nullable=False)
    sample_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    updated_at: Mapped[datetime] = mapped_column(
        TSTZ, nullable=False, server_default=text("now()")
    )


class ApiRequestStat(Base):
    """GitHub API call log written by the worker (feeds /api/stats)."""

    __tablename__ = "api_request_stats"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    status_code: Mapped[int] = mapped_column(Integer, nullable=False)
    ts: Mapped[datetime] = mapped_column(
        TSTZ, nullable=False, server_default=text("now()")
    )

    __table_args__ = (
        Index("ix_api_request_stats_ts", "ts"),
    )


class ExternalMention(Base):
    """Extension table for HN/Reddit/Lobsters/news mentions. MVP: table only."""

    __tablename__ = "external_mentions"

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid, primary_key=True, default=uuid.uuid4, server_default=text("gen_random_uuid()")
    )
    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("repositories.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(Text, nullable=False)  # hn|reddit|lobsters|news
    external_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    ts: Mapped[datetime | None] = mapped_column(TSTZ, nullable=True)
    score: Mapped[float | None] = mapped_column(Double, nullable=True)

    __table_args__ = (
        Index("ix_external_mentions_repo_ts", "repository_id", "ts"),
    )
