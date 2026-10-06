"""Database engine/session helpers.

Prefers the canonical models from ``radar_api.models`` when that package is
installed; otherwise falls back to ``radar_worker.db_models`` (CONTRACT-exact).
The two model sets share table/column names, so this choice only affects
which Python classes are used — never the schema.
"""

from __future__ import annotations

from types import ModuleType
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from .config import WorkerSettings
from .log import get_logger

log = get_logger(__name__)


def load_models() -> ModuleType:
    """Return the models module to use: radar_api.models if available."""
    try:
        import radar_api.models as api_models  # type: ignore[import-not-found]

        log.info("using canonical models from radar_api.models")
        return api_models
    except ImportError:
        from . import db_models as fallback

        log.info("radar_api not installed; using radar_worker.db_models fallback")
        return fallback


class Database:
    def __init__(self, settings: WorkerSettings) -> None:
        self.settings = settings
        self.models = load_models()
        self.engine = create_engine(
            settings.database_url,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,
            future=True,
        )
        self._factory = sessionmaker(bind=self.engine, autoflush=False, future=True)

    def session(self) -> Session:
        return self._factory()

    def session_scope(self) -> Iterator[Session]:
        """Context manager: commit on success, rollback on error."""
        from contextlib import contextmanager

        @contextmanager
        def _scope() -> Iterator[Session]:
            session = self._factory()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        return _scope()

    def create_all(self) -> None:
        """Create tables (dev/demo convenience; production uses Alembic)."""
        self.models.Base.metadata.create_all(self.engine)

    def dispose(self) -> None:
        self.engine.dispose()
