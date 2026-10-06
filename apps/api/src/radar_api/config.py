"""Application configuration via pydantic-settings.

All values can be provided through environment variables or a `.env` file.
`CORS_ORIGINS` must be JSON, e.g. ``CORS_ORIGINS='["http://localhost:3000"]'``.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- database -----------------------------------------------------------
    DATABASE_URL: str = "postgresql+psycopg://radar:radar@localhost:5432/radar"

    # --- runtime ------------------------------------------------------------
    LOG_LEVEL: str = "INFO"
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # --- pagination ---------------------------------------------------------
    DEFAULT_PAGE_LIMIT: int = 20
    MAX_PAGE_LIMIT: int = 100

    # --- abuse protection ---------------------------------------------------
    # Max requests per IP per minute. 0 disables the limiter.
    RATE_LIMIT_PER_MINUTE: int = 600

    # --- admin --------------------------------------------------------------
    # When set, POST /api/repos requires a matching `X-API-Key` header.
    # The GitHub token is intentionally NOT handled by the API service —
    # all GitHub API access lives in the worker.
    ADMIN_API_KEY: str | None = None

    # --- GitHub repo resolution (unauthenticated, used by POST /api/repos) --
    GITHUB_API_URL: str = "https://api.github.com"
    GITHUB_LOOKUP_TIMEOUT_S: float = 10.0


settings = Settings()
