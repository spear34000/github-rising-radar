"""Pydantic v2 request/response schemas.

Field names match CONTRACT.md §4 exactly. Numeric fields are ``None`` (not
fabricated) when history is insufficient, together with
``insufficient_history: true``.
"""

from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

FULL_NAME_PATTERN = r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$"


class RepoCard(BaseModel):
    """Leaderboard card. Field set mirrors CONTRACT.md §4."""

    id: UUID
    owner: str
    name: str
    full_name: str
    description: str | None
    url: str
    language: str | None
    license: str | None
    category: list[str] = Field(default_factory=list)
    stars: int
    forks: int
    age_days: int | None
    stars_24h_gain: float | None
    velocity_24h: float | None  # stars/hour
    acceleration: float | None  # % change of 24h velocity vs previous 24h
    relative_growth: float | None  # 24h gain / max(prior stars, 50)
    breakout_score: float | None
    organic_score: float | None
    hype_risk: str | None
    status: str
    detected_at: datetime
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    insufficient_history: bool = False


class DetectionInfo(BaseModel):
    first_detected_at: datetime
    stars_at_detection: int
    growth_since_detection: int
    first_emerging_at: datetime | None = None
    first_rising_at: datetime | None = None
    first_breakout_at: datetime | None = None
    first_viral_at: datetime | None = None
    peak_score: float | None = None
    peak_at: datetime | None = None


class RepoDetail(RepoCard):
    """Repository detail header: card + latest score metadata + detection info."""

    topics: list[str] = Field(default_factory=list)
    watchers: int | None = None
    open_issues: int | None = None
    created_at: datetime | None = None
    pushed_at: datetime | None = None
    score_ts: datetime | None = None
    scoring_version: str | None = None
    confidence: float | None = None
    detections: DetectionInfo | None = None
    # Deterministic, grounded explanations computed from the latest snapshots.
    why_rising: str | None = None
    hype_risk_reasons: list[str] = Field(default_factory=list)


class SnapshotPoint(BaseModel):
    ts: datetime
    stars: int
    forks: int
    watchers: int
    open_issues: int
    open_prs: int
    contributors_count: int | None = None
    commit_count_7d: int | None = None


class ScorePoint(BaseModel):
    """One scored point in a repo's history (UI-friendly field names)."""

    ts: datetime
    breakout_score: float | None = None
    velocity_24h: float | None = None
    acceleration: float | None = None  # % change of 24h velocity vs prior 24h


class HistoryEvent(BaseModel):
    type: str  # detected|emerging|rising|breakout|viral
    ts: datetime
    label: str
    description: str | None = None


class HistoryResponse(BaseModel):
    repository: RepoCard
    snapshots: list[SnapshotPoint] = Field(default_factory=list)
    scores: list[ScorePoint] = Field(default_factory=list)
    detections: DetectionInfo | None = None
    events: list[HistoryEvent] = Field(default_factory=list)
    insufficient_history: bool = False


class RankingEntry(BaseModel):
    rank: int
    score: float
    repo: RepoCard


class RankingResponse(BaseModel):
    bucket: str
    ts: datetime | None = None
    items: list[RankingEntry] = Field(default_factory=list)


class CategoryStat(BaseModel):
    name: str
    count: int


class StatsResponse(BaseModel):
    tracked_repos: int
    snapshots_24h: int
    detections_7d: int
    api_calls_24h: int


class AddRepoRequest(BaseModel):
    full_name: str = Field(min_length=3, max_length=200)

    @field_validator("full_name")
    @classmethod
    def _validate_full_name(cls, v: str) -> str:
        v = v.strip()
        if not re.fullmatch(FULL_NAME_PATTERN, v):
            raise ValueError("full_name must look like 'owner/repo'")
        return v


class AddRepoResponse(BaseModel):
    job_id: UUID
    repository_id: UUID
    full_name: str
    status: str  # pending | already_tracked


class PaginatedRepos(BaseModel):
    items: list[RepoCard] = Field(default_factory=list)
    next_cursor: str | None = None
