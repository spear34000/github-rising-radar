"""API endpoint tests (pytest + httpx ASGITransport).

.. note::
    NOT EXECUTED — the sandbox terminal was unavailable when these were
    written, so they have not been run. Run with a Postgres test database::

        TEST_DATABASE_URL=postgresql+psycopg://radar:radar@localhost:5432/radar_test \\
            pytest apps/api/tests -q
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timedelta, timezone

os.environ.setdefault(
    "DATABASE_URL",
    os.environ.get(
        "TEST_DATABASE_URL", "postgresql+psycopg://radar:radar@localhost:5432/radar_test"
    ),
)

import httpx  # noqa: E402
import pytest  # noqa: E402
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from radar_api import __version__  # noqa: E402
from radar_api.config import settings  # noqa: E402
from radar_api.db import get_db  # noqa: E402
from radar_api.main import create_app  # noqa: E402
from radar_api.models import Base, Detection, Repository, Score  # noqa: E402
from radar_api.routers import repos as repos_router  # noqa: E402

assert __version__  # package imports cleanly


@pytest.fixture(scope="session")
def engine():
    eng = create_engine(settings.DATABASE_URL, future=True)
    yield eng
    eng.dispose()


@pytest.fixture()
def db(engine):
    """Fresh schema per test, transactional cleanup."""
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    session = Session()
    yield session
    session.close()
    Base.metadata.drop_all(engine)


@pytest.fixture()
def client(db):
    app = create_app()

    def override_get_db():
        try:
            yield db
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    # NOTE: fastapi.testclient.TestClient (not httpx.ASGITransport) — the
    # installed httpx version only ships an async ASGI transport.
    from fastapi.testclient import TestClient

    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


def _repo(db, full_name="octo/rocket", **kw):
    owner, name = full_name.split("/")
    now = datetime.now(timezone.utc)
    repo = Repository(
        github_id=kw.pop("github_id", abs(hash(full_name)) % (2**62)),
        owner=owner,
        name=name,
        full_name=full_name,
        description="A test rocket",
        url=f"https://github.com/{full_name}",
        created_at=kw.pop("created_at", now - timedelta(days=11)),
        pushed_at=now - timedelta(hours=2),
        detected_at=now - timedelta(days=3),
        language=kw.pop("language", "Python"),
        license="mit",
        current_stars=kw.pop("current_stars", 2841),
        current_forks=120,
        category=kw.pop("category", "AI"),
        topics=["ai"],
        status=kw.pop("status", "breakout"),
        poll_interval_seconds=3600,
        next_poll_at=now,
    )
    db.add(repo)
    db.flush()
    return repo


def _score(db, repo, **kw):
    now = datetime.now(timezone.utc)
    s = Score(
        repository_id=repo.id,
        ts=kw.pop("ts", now),
        star_velocity_24h=kw.pop("star_velocity_24h", 28.4),
        acceleration=kw.pop("acceleration", 12.5),
        relative_growth=0.31,
        fork_velocity_24h=2.1,
        activity_score=72.0,
        age_bonus=70.0,
        breakout_score=kw.pop("breakout_score", 92.0),
        organic_score=88.0,
        hype_risk="low",
        status=kw.pop("status", "breakout"),
        score_breakdown={"star_velocity": 27.0, "acceleration": 23.0},
        scoring_version="v1",
        confidence=1.0,
    )
    db.add(s)
    db.flush()
    return s


def _detection(db, repo):
    now = datetime.now(timezone.utc)
    d = Detection(
        repository_id=repo.id,
        first_detected_at=now - timedelta(days=3),
        stars_at_detection=2160,
        first_breakout_at=now - timedelta(hours=5),
        growth_since_detection=681,
    )
    db.add(d)
    db.flush()
    return d


# --- health -----------------------------------------------------------------


def test_healthz(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_readyz(client):
    r = client.get("/readyz")
    assert r.status_code == 200
    assert r.json()["db"] == "ok"


# --- list --------------------------------------------------------------------


def test_list_repos_empty(client):
    r = client.get("/api/repos")
    assert r.status_code == 200
    body = r.json()
    assert body["items"] == []
    assert body["next_cursor"] is None


def test_list_repos_card_shape_and_sort(client, db):
    a = _repo(db, "octo/aaa")
    b = _repo(db, "octo/bbb")
    _score(db, a, breakout_score=92.0)
    _score(db, b, breakout_score=61.0)
    db.commit()

    r = client.get("/api/repos")
    assert r.status_code == 200
    items = r.json()["items"]
    assert [i["full_name"] for i in items] == ["octo/aaa", "octo/bbb"]
    card = items[0]
    assert card["breakout_score"] == 92.0
    assert card["velocity_24h"] == 28.4
    # acceleration is exposed as % change of 24h velocity vs prior 24h:
    # v_prev = 28.4 - 12.5 = 15.9 -> 12.5 / 15.9 * 100 ~= 78.6
    assert card["acceleration"] == pytest.approx(78.6, abs=0.1)
    assert card["stars_24h_gain"] is None  # no snapshots -> null, not fabricated
    assert card["category"] == ["AI"]
    assert card["insufficient_history"] is False
    assert set(card) >= {
        "id", "owner", "name", "full_name", "description", "url", "language",
        "license", "category", "stars", "forks", "age_days", "stars_24h_gain",
        "velocity_24h", "acceleration", "breakout_score", "organic_score",
        "hype_risk", "status", "detected_at", "score_breakdown",
        "insufficient_history",
    }


def test_list_repos_filters(client, db):
    _repo(db, "octo/py", language="Python", status="rising", current_stars=500)
    _repo(db, "octo/rs", language="Rust", status="breakout", current_stars=5000)
    db.commit()

    r = client.get("/api/repos", params={"language": "rust"})
    assert [i["full_name"] for i in r.json()["items"]] == ["octo/rs"]

    r = client.get("/api/repos", params={"status": "rising"})
    assert [i["full_name"] for i in r.json()["items"]] == ["octo/py"]

    r = client.get("/api/repos", params={"min_stars": 1000})
    assert [i["full_name"] for i in r.json()["items"]] == ["octo/rs"]

    r = client.get("/api/repos", params={"status": "nope"})
    assert r.status_code == 422


def test_list_repos_cursor_pagination(client, db):
    for i in range(3):
        repo = _repo(db, f"octo/r{i}")
        _score(db, repo, breakout_score=90.0 - i)
    db.commit()

    r1 = client.get("/api/repos", params={"limit": 2}).json()
    assert len(r1["items"]) == 2
    assert r1["next_cursor"]
    assert [i["full_name"] for i in r1["items"]] == ["octo/r0", "octo/r1"]

    r2 = client.get("/api/repos", params={"limit": 2, "cursor": r1["next_cursor"]}).json()
    assert [i["full_name"] for i in r2["items"]] == ["octo/r2"]
    assert r2["next_cursor"] is None

    bad = client.get("/api/repos", params={"cursor": "!!!not-base64!!!"})
    assert bad.status_code == 400


# --- detail ------------------------------------------------------------------


def test_repo_detail(client, db):
    repo = _repo(db, "octo/rocket")
    _score(db, repo)
    _detection(db, repo)
    db.commit()

    r = client.get("/api/repos/octo/rocket")
    assert r.status_code == 200
    body = r.json()
    assert body["full_name"] == "octo/rocket"
    assert body["breakout_score"] == 92.0
    assert body["scoring_version"] == "v1"
    assert body["detections"]["stars_at_detection"] == 2160
    assert body["detections"]["first_breakout_at"] is not None

    r = client.get("/api/repos/OCTO/ROCKET")  # case-insensitive
    assert r.status_code == 200

    r = client.get("/api/repos/octo/missing")
    assert r.status_code == 404

    r = client.get("/api/repos/bad!name/repo")
    assert r.status_code == 400


def test_repo_detail_pending_repo(client, db):
    _repo(db, "octo/fresh")  # no score rows yet
    db.commit()
    r = client.get("/api/repos/octo/fresh")
    assert r.status_code == 200
    body = r.json()
    assert body["breakout_score"] is None
    assert body["insufficient_history"] is True


# --- history -----------------------------------------------------------------


def test_repo_history_insufficient(client, db):
    repo = _repo(db, "octo/newbie")
    db.commit()
    r = client.get(f"/api/repos/{repo.id}/history")
    assert r.status_code == 200
    body = r.json()
    assert body["insufficient_history"] is True
    assert body["snapshots"] == []
    assert body["scores"] == []
    assert body["detections"] is None

    r = client.get("/api/repos/not-a-uuid/history")
    assert r.status_code == 400
    r = client.get(f"/api/repos/{uuid.uuid4()}/history")
    assert r.status_code == 404


# --- rankings / categories / stats -------------------------------------------


def test_rankings_empty(client):
    r = client.get("/api/rankings", params={"bucket": "all"})
    assert r.status_code == 200
    body = r.json()
    assert body["bucket"] == "all"
    assert body["items"] == []
    assert body["ts"] is None


def test_categories_and_stats(client, db):
    _repo(db, "octo/a1", category="AI")
    _repo(db, "octo/a2", category="AI")
    _repo(db, "octo/d1", category="DevTools")
    db.commit()

    cats = client.get("/api/categories").json()
    assert {c["name"]: c["count"] for c in cats} == {"AI": 2, "DevTools": 1}

    stats = client.get("/api/stats").json()
    assert stats["tracked_repos"] == 3
    assert stats["snapshots_24h"] == 0
    assert stats["detections_7d"] == 0
    assert stats["api_calls_24h"] >= 1


# --- POST /api/repos ----------------------------------------------------------


def test_add_repo_invalid(client):
    r = client.post("/api/repos", json={"full_name": "not a repo!!"})
    assert r.status_code == 422


def test_add_repo_stub_when_github_unreachable(client, db, monkeypatch):
    monkeypatch.setattr(repos_router, "_lookup_github", lambda full_name: None)
    r = client.post("/api/repos", json={"full_name": "octo/stub"})
    assert r.status_code == 202
    body = r.json()
    assert body["status"] == "pending"
    assert body["full_name"] == "octo/stub"

    repo = db.get(Repository, uuid.UUID(body["repository_id"]))
    assert repo is not None
    assert repo.status == "normal"
    assert repo.poll_interval_seconds == 3600
    assert repo.github_id < 0  # placeholder, reconciled by the worker

    # idempotent duplicate
    r2 = client.post("/api/repos", json={"full_name": "octo/stub"})
    assert r2.status_code == 200
    assert r2.json()["status"] == "already_tracked"


def test_add_repo_github_not_found(client, monkeypatch):
    monkeypatch.setattr(repos_router, "_lookup_github", lambda full_name: "not_found")
    r = client.post("/api/repos", json={"full_name": "octo/nope"})
    assert r.status_code == 404
