"""Worker configuration via environment variables / .env file.

Secrets (GitHub tokens, DB password inside DATABASE_URL) are read from the
environment only — never logged, never committed.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated

from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


def _split_csv(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [v.strip() for v in value if v and str(v).strip()]
    return [v.strip() for v in value.split(",") if v.strip()]


CsvList = Annotated[list[str], BeforeValidator(_split_csv)]

_PACKAGE_DIR = Path(__file__).resolve().parent
# Task spec location: apps/worker/worker/discovery.yaml
_DEFAULT_DISCOVERY_YAML = _PACKAGE_DIR.parent.parent / "worker" / "discovery.yaml"


class WorkerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql+psycopg://radar:radar@localhost:5432/radar",
        description="SQLAlchemy URL, e.g. postgresql+psycopg://user:pass@host:5432/db",
    )

    # Comma-separated GitHub personal access tokens. Worker round-robins them.
    # Empty → worker refuses live GitHub calls (demo/seed mode only).
    github_tokens: CsvList = Field(default_factory=list)

    discovery_yaml: Path = Field(default=_DEFAULT_DISCOVERY_YAML)

    # Job intervals (minutes)
    discover_interval_min: int = 30
    collect_interval_min: int = 5
    score_interval_min: int = 10
    classify_interval_min: int = 15
    rankings_interval_min: int = 15
    cleanup_interval_min: int = 1440

    # Collection tuning
    collect_batch_size: int = 50
    score_batch_size: int = 500
    rankings_top_n: int = 100

    # GitHub client tuning
    gh_timeout_seconds: float = 30.0
    gh_max_retries: int = 5
    gh_rate_limit_threshold: int = 50  # sleep until reset when remaining <= this
    gh_max_rate_limit_wait_seconds: int = 3600

    log_level: str = "INFO"
    log_json: bool = False

    @property
    def has_github_token(self) -> bool:
        return bool(self.github_tokens)


@lru_cache
def get_settings() -> WorkerSettings:
    return WorkerSettings()
