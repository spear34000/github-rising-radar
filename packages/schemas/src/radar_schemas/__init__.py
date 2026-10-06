"""Shared internal DTOs for the pipeline (worker -> DB -> API).

These are transport/storage shapes, not the public REST contract
(see apps/api schemas for that).
"""

from __future__ import annotations

from datetime import datetime
from pydantic import BaseModel, Field


class SnapshotIn(BaseModel):
    repository_id: str
    ts: datetime
    stars: int = Field(ge=0)
    forks: int = Field(ge=0)
    watchers: int = Field(ge=0, default=0)
    open_issues: int = Field(ge=0, default=0)
    open_prs: int = Field(ge=0, default=0)
    contributors_count: int | None = Field(ge=0, default=None)
    commit_count_7d: int | None = Field(ge=0, default=None)


class ScoreIn(BaseModel):
    repository_id: str
    ts: datetime
    star_velocity_1h: float | None = None
    star_velocity_6h: float | None = None
    star_velocity_24h: float | None = None
    star_velocity_7d: float | None = None
    acceleration: float | None = None
    relative_growth: float | None = None
    fork_velocity_24h: float | None = None
    fork_star_ratio: float | None = None
    activity_score: float | None = None
    age_bonus: float | None = None
    breakout_score: float = Field(ge=0, le=100)
    organic_score: float | None = Field(ge=0, le=100, default=None)
    hype_risk: str | None = None
    status: str
    score_breakdown: dict[str, float] = Field(default_factory=dict)
    scoring_version: str = "v1"
    confidence: float | None = Field(ge=0, le=1, default=None)


class CorpusStatIn(BaseModel):
    metric: str
    median: float
    mad: float
    p90: float | None = None
    sample_size: int = Field(ge=0, default=0)
