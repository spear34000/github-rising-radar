"""Repository endpoints: list (cursor pagination), detail, history, manual add."""

from __future__ import annotations

import base64
import binascii
import json
import re
import uuid
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import JSONResponse
from sqlalchemy import and_, func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..config import settings
from ..db import get_db
from ..models import Detection, Repository, RepositorySnapshot, Score
from ..repo_cards import card_select, row_gain, row_to_card

try:
    from radar_scoring import (  # type: ignore[import-not-found]
        Snapshot as ScoringSnapshot,
        compute_metrics,
        explain_score,
        hype_risk_details,
    )

    _SCORING_AVAILABLE = True
except ImportError:  # pragma: no cover - api image installs radar-scoring
    _SCORING_AVAILABLE = False

from ..schemas import (
    AddRepoRequest,
    AddRepoResponse,
    DetectionInfo,
    HistoryEvent,
    HistoryResponse,
    PaginatedRepos,
    RepoDetail,
    ScorePoint,
    SnapshotPoint,
)

router = APIRouter(prefix="/repos", tags=["repos"])

FULL_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
OWNER_NAME_RE = re.compile(r"^[A-Za-z0-9_.-]+$")

STATUS_PATTERN = r"^(normal|emerging|rising|breakout|viral|cooling)$"
CATEGORY_PATTERN = (
    r"^(AI|LLM|Agents|DevTools|Security|Database|Infrastructure|Web|Mobile|"
    r"Data|Research|Hardware|Games|Other)$"
)
SORT_PATTERN = r"^(breakout_score|growth_24h|acceleration|relative_growth|newest)$"
RANGE_PATTERN = r"^(24h|7d)$"
HISTORY_RANGE_PATTERN = r"^(7d|30d|90d|all)$"

# Fallback sort keys for rows without scores/gains. They must be lower than
# any real value so unscored repos sort last.
_NULL_BREAKOUT = -1.0
_NULL_GAIN = -1e15
_NULL_METRIC = -1e18

_HISTORY_RANGE_HOURS = {"7d": 24 * 7, "30d": 24 * 30, "90d": 24 * 90}


# ---------------------------------------------------------------------------
# cursor helpers (opaque base64 of {"s": sort, "v": value, "id": uuid})
# ---------------------------------------------------------------------------

def _encode_cursor(sort: str, value: object, repo_id: uuid.UUID) -> str:
    payload = {"s": sort, "v": value, "id": str(repo_id)}
    raw = json.dumps(payload, separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(raw).decode()


def _decode_cursor(cursor: str) -> dict:
    try:
        raw = base64.urlsafe_b64decode(cursor.encode())
        payload = json.loads(raw)
    except (binascii.Error, ValueError, UnicodeDecodeError) as exc:
        raise HTTPException(400, "invalid cursor") from exc
    if not isinstance(payload, dict) or {"s", "v", "id"} - set(payload):
        raise HTTPException(400, "invalid cursor")
    return payload


def _cursor_value(sort: str, row: object, detected_at: datetime) -> object:
    """Value matching the ORDER BY key expression for ``sort``."""
    m = row._mapping  # type: ignore[attr-defined]
    if sort == "breakout_score":
        v = m["sc_breakout_score"]
        return float(v) if v is not None else _NULL_BREAKOUT
    if sort == "growth_24h":
        g = row_gain(m)
        return float(g) if g is not None else _NULL_GAIN
    if sort == "acceleration":
        v = m["sc_acceleration"]
        return float(v) if v is not None else _NULL_METRIC
    if sort == "relative_growth":
        v = m["sc_relative_growth"]
        return float(v) if v is not None else _NULL_METRIC
    return detected_at.isoformat()  # newest


# ---------------------------------------------------------------------------
# GET /api/repos
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=PaginatedRepos,
    summary="List repositories",
    description=(
        "Filterable, cursor-paginated repository list. Default sort is the "
        "latest `breakout_score`. `range` filters by detection recency "
        "(repos first detected within the window)."
    ),
)
def list_repos(
    db: Session = Depends(get_db),
    status_filter: str | None = Query(default=None, alias="status", pattern=STATUS_PATTERN),
    category: str | None = Query(default=None, pattern=CATEGORY_PATTERN),
    language: str | None = Query(default=None, max_length=64),
    min_stars: int | None = Query(default=None, ge=0),
    max_age_days: int | None = Query(default=None, ge=0),
    sort: str = Query(default="breakout_score", pattern=SORT_PATTERN),
    time_range: str | None = Query(default=None, alias="range", pattern=RANGE_PATTERN),
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None, max_length=512),
) -> PaginatedRepos:
    now = datetime.now(timezone.utc)
    stmt, refs = card_select()

    if status_filter:
        stmt = stmt.where(Repository.status == status_filter)
    if category:
        stmt = stmt.where(Repository.category == category)
    if language:
        stmt = stmt.where(func.lower(Repository.language) == language.lower())
    if min_stars is not None:
        stmt = stmt.where(Repository.current_stars >= min_stars)
    if max_age_days is not None:
        stmt = stmt.where(Repository.created_at >= now - timedelta(days=max_age_days))
    if time_range:
        hours = 24 if time_range == "24h" else 24 * 7
        stmt = stmt.where(Repository.detected_at >= now - timedelta(hours=hours))

    sc, ls, ps = refs.sc, refs.ls, refs.ps
    if sort == "breakout_score":
        key = func.coalesce(sc.breakout_score, _NULL_BREAKOUT)
    elif sort == "growth_24h":
        key = func.coalesce(ls.stars - ps.stars, _NULL_GAIN)
    elif sort == "acceleration":
        key = func.coalesce(sc.acceleration, _NULL_METRIC)
    elif sort == "relative_growth":
        key = func.coalesce(sc.relative_growth, _NULL_METRIC)
    else:  # newest
        key = Repository.detected_at
    stmt = stmt.order_by(key.desc(), Repository.id.desc())

    if cursor:
        cur = _decode_cursor(cursor)
        if cur["s"] != sort:
            raise HTTPException(400, "cursor was created for a different sort")
        try:
            cur_id = uuid.UUID(str(cur["id"]))
        except ValueError as exc:
            raise HTTPException(400, "invalid cursor") from exc
        if sort == "newest":
            try:
                cur_v = datetime.fromisoformat(str(cur["v"]))
            except ValueError as exc:
                raise HTTPException(400, "invalid cursor") from exc
            if cur_v.tzinfo is None:
                cur_v = cur_v.replace(tzinfo=timezone.utc)
            stmt = stmt.where(
                or_(
                    Repository.detected_at < cur_v,
                    and_(Repository.detected_at == cur_v, Repository.id < cur_id),
                )
            )
        else:
            try:
                cur_v = float(cur["v"])
            except (TypeError, ValueError) as exc:
                raise HTTPException(400, "invalid cursor") from exc
            stmt = stmt.where(or_(key < cur_v, and_(key == cur_v, Repository.id < cur_id)))

    rows = db.execute(stmt.limit(limit + 1)).all()
    has_more = len(rows) > limit
    rows = rows[:limit]

    cards = [row_to_card(r, now) for r in rows]
    next_cursor = None
    if has_more and rows:
        last_row, last_card = rows[-1], cards[-1]
        next_cursor = _encode_cursor(
            sort, _cursor_value(sort, last_row, last_card.detected_at), last_card.id
        )
    return PaginatedRepos(items=cards, next_cursor=next_cursor)


# ---------------------------------------------------------------------------
# GET /api/repos/{id}/history  (registered before /{owner}/{name})
# ---------------------------------------------------------------------------

@router.get(
    "/{repo_id}/history",
    response_model=HistoryResponse,
    summary="Repository history",
    description=(
        "Snapshots, scores, detection milestones and annotated events. "
        "Unknown history is returned as null with `insufficient_history: true` — "
        "never fabricated."
    ),
)
def repo_history(
    repo_id: str,
    db: Session = Depends(get_db),
    range_: str = Query(default="30d", alias="range", pattern=HISTORY_RANGE_PATTERN),
) -> HistoryResponse:
    try:
        rid = uuid.UUID(repo_id)
    except ValueError as exc:
        raise HTTPException(400, "invalid repository id") from exc
    repo = db.get(Repository, rid)
    if repo is None:
        raise HTTPException(404, "repository not found")

    now = datetime.now(timezone.utc)
    cutoff = None if range_ == "all" else now - timedelta(hours=_HISTORY_RANGE_HOURS[range_])

    snap_q = (
        select(RepositorySnapshot)
        .where(RepositorySnapshot.repository_id == rid)
        .order_by(RepositorySnapshot.ts.asc())
    )
    score_q = select(Score).where(Score.repository_id == rid).order_by(Score.ts.asc())
    if cutoff is not None:
        snap_q = snap_q.where(RepositorySnapshot.ts >= cutoff)
        score_q = score_q.where(Score.ts >= cutoff)
    snapshots = db.execute(snap_q).scalars().all()
    scores = db.execute(score_q).scalars().all()
    detection = db.get(Detection, rid)

    stmt, _ = card_select()
    card_row = db.execute(stmt.where(Repository.id == rid)).one_or_none()
    card = row_to_card(card_row, now) if card_row else None
    if card is None:  # pragma: no cover - defensive; repo was just fetched above
        raise HTTPException(404, "repository not found")

    detection_info = _detection_info(detection) if detection else None
    events = _detection_events(detection)

    latest_confidence = scores[-1].confidence if scores else None
    insufficient = (
        not scores
        or len(snapshots) < 2
        or (latest_confidence is not None and latest_confidence < 0.5)
    )

    return HistoryResponse(
        repository=card,
        snapshots=[
            SnapshotPoint(
                ts=s.ts,
                stars=s.stars,
                forks=s.forks,
                watchers=s.watchers,
                open_issues=s.open_issues,
                open_prs=s.open_prs,
                contributors_count=s.contributors_count,
                commit_count_7d=s.commit_count_7d,
            )
            for s in snapshots
        ],
        scores=[
            ScorePoint(
                ts=s.ts,
                breakout_score=s.breakout_score,
                velocity_24h=s.star_velocity_24h,
                acceleration=_pct(s.acceleration, s.star_velocity_24h),
            )
            for s in scores
        ],
        detections=detection_info,
        events=events,
        insufficient_history=bool(insufficient),
    )


# ---------------------------------------------------------------------------
# GET /api/repos/{owner}/{name}
# ---------------------------------------------------------------------------

@router.get(
    "/{owner}/{name}",
    response_model=RepoDetail,
    summary="Repository detail",
    description="Header card plus latest score metadata and detection info.",
)
def repo_detail(owner: str, name: str, db: Session = Depends(get_db)) -> RepoDetail:
    if not OWNER_NAME_RE.fullmatch(owner) or not OWNER_NAME_RE.fullmatch(name):
        raise HTTPException(400, "invalid owner/name")
    full_name = f"{owner}/{name}"
    repo = db.execute(
        select(Repository).where(func.lower(Repository.full_name) == full_name.lower())
    ).scalar_one_or_none()
    if repo is None:
        raise HTTPException(404, "repository not found")

    now = datetime.now(timezone.utc)
    stmt, _ = card_select()
    row = db.execute(stmt.where(Repository.id == repo.id)).one_or_none()
    if row is None:  # pragma: no cover - defensive
        raise HTTPException(404, "repository not found")
    card = row_to_card(row, now)
    m = row._mapping
    detection = db.get(Detection, repo.id)

    why_rising, hype_risk_reasons = _explain(repo, db, now)

    return RepoDetail(
        **card.model_dump(),
        topics=list(repo.topics or []),
        watchers=m["snap_watchers"],
        open_issues=m["snap_open_issues"],
        created_at=repo.created_at,
        pushed_at=repo.pushed_at,
        score_ts=m["sc_ts"],
        scoring_version=m["sc_scoring_version"],
        confidence=m["sc_confidence"],
        detections=_detection_info(detection) if detection else None,
        why_rising=why_rising,
        hype_risk_reasons=list(hype_risk_reasons),
    )


def _explain(
    repo: Repository, db: Session, now: datetime
) -> tuple[str | None, list[str]]:
    """Deterministic 'Why is this rising?' + hype-risk reasons.

    Recomputed from the latest snapshots with the same scoring package the
    worker uses — every sentence is grounded in measured metrics.
    """
    if not _SCORING_AVAILABLE:
        return None, []
    snaps = (
        db.execute(
            select(RepositorySnapshot)
            .where(RepositorySnapshot.repository_id == repo.id)
            .order_by(RepositorySnapshot.ts.desc())
            .limit(500)
        )
        .scalars()
        .all()
    )
    if len(snaps) < 2:
        return None, []
    inputs = [
        ScoringSnapshot(
            ts=s.ts,
            stars=s.stars,
            forks=s.forks,
            watchers=s.watchers,
            open_issues=s.open_issues,
            open_prs=s.open_prs,
            contributors_count=s.contributors_count,
            commit_count_7d=s.commit_count_7d,
            has_release_14d=bool(s.has_release_14d),
            pushed_at=repo.pushed_at,
        )
        for s in snaps
    ]
    age_days = (
        (now - repo.created_at).total_seconds() / 86400.0
        if repo.created_at
        else 0.0
    )
    metrics = compute_metrics(inputs, age_days, now)
    _, reasons = hype_risk_details(metrics)
    return explain_score(metrics, repo.full_name), list(reasons)


# ---------------------------------------------------------------------------
# POST /api/repos
# ---------------------------------------------------------------------------

def _lookup_github(full_name: str) -> dict | str | None:
    """Resolve ``owner/repo`` via the public GitHub REST API (no token).

    Returns the repo JSON dict, the string ``"not_found"`` for a GitHub 404,
    or ``None`` when GitHub is unreachable / rate-limited.
    """
    url = f"{settings.GITHUB_API_URL}/repos/{full_name}"
    try:
        with httpx.Client(
            timeout=settings.GITHUB_LOOKUP_TIMEOUT_S, follow_redirects=True
        ) as client:
            resp = client.get(
                url,
                headers={
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "github-rising-radar/0.1",
                },
            )
    except httpx.HTTPError:
        return None
    if resp.status_code == 404:
        return "not_found"
    if resp.status_code != 200:
        return None
    try:
        data = resp.json()
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def _parse_github_dt(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@router.post(
    "",
    response_model=AddRepoResponse,
    status_code=202,
    summary="Manually register a repository",
    description=(
        "Backfill entry point (`radar add owner/repo`). Creates a pending "
        "repository row (status=normal, 1h poll interval) for the worker to "
        "pick up. Returns 202 on creation, 200 if already tracked. "
        "GitHub metadata is resolved with an unauthenticated lookup; when "
        "GitHub is unreachable a stub row is stored and the worker "
        "reconciles it (negative placeholder github_id) on first snapshot."
    ),
)
def add_repo(
    body: AddRepoRequest,
    db: Session = Depends(get_db),
    x_api_key: str | None = Header(default=None, alias="X-API-Key"),
) -> AddRepoResponse | JSONResponse:
    if settings.ADMIN_API_KEY and x_api_key != settings.ADMIN_API_KEY:
        raise HTTPException(401, "invalid api key")

    full_name = body.full_name  # already stripped + validated by the schema
    existing = db.execute(
        select(Repository).where(func.lower(Repository.full_name) == full_name.lower())
    ).scalar_one_or_none()
    if existing is not None:
        return JSONResponse(
            status_code=200,
            content=AddRepoResponse(
                job_id=uuid.uuid4(),
                repository_id=existing.id,
                full_name=existing.full_name,
                status="already_tracked",
            ).model_dump(mode="json"),
        )

    lookup = _lookup_github(full_name)
    if lookup == "not_found":
        raise HTTPException(404, f"repository '{full_name}' not found on GitHub")

    now = datetime.now(timezone.utc)
    if isinstance(lookup, dict):
        lic = lookup.get("license") or {}
        repo = Repository(
            github_id=int(lookup["id"]),
            owner=str(lookup["owner"]["login"]),
            name=str(lookup["name"]),
            full_name=str(lookup["full_name"]),
            description=lookup.get("description"),
            url=str(lookup.get("html_url") or f"https://github.com/{full_name}"),
            created_at=_parse_github_dt(lookup.get("created_at")) or now,
            pushed_at=_parse_github_dt(lookup.get("pushed_at")),
            detected_at=now,
            language=lookup.get("language"),
            license=lic.get("key") if isinstance(lic, dict) else None,
            archived=bool(lookup.get("archived")),
            fork=bool(lookup.get("fork")),
            current_stars=int(lookup.get("stargazers_count") or 0),
            current_forks=int(lookup.get("forks_count") or 0),
            topics=list(lookup.get("topics") or []),
            status="normal",
            poll_interval_seconds=3600,
            next_poll_at=now,
        )
        stars_at_detection = repo.current_stars
    else:
        # GitHub unreachable: store a stub; the worker reconciles the negative
        # placeholder github_id on its first successful snapshot.
        owner, name = full_name.split("/")
        repo = Repository(
            github_id=-int(now.timestamp() * 1_000_000),
            owner=owner,
            name=name,
            full_name=full_name,
            description=None,
            url=f"https://github.com/{full_name}",
            created_at=now,
            pushed_at=None,
            detected_at=now,
            status="normal",
            poll_interval_seconds=3600,
            next_poll_at=now,
        )
        stars_at_detection = 0

    db.add(repo)
    try:
        db.flush()
    except IntegrityError:
        # Lost a race with a concurrent insert for the same repo.
        db.rollback()
        dup = db.execute(
            select(Repository).where(func.lower(Repository.full_name) == full_name.lower())
        ).scalar_one_or_none()
        if dup is None:  # pragma: no cover - defensive
            raise HTTPException(409, "repository already tracked")
        return JSONResponse(
            status_code=200,
            content=AddRepoResponse(
                job_id=uuid.uuid4(),
                repository_id=dup.id,
                full_name=dup.full_name,
                status="already_tracked",
            ).model_dump(mode="json"),
        )
    db.add(
        Detection(
            repository_id=repo.id,
            first_detected_at=now,
            stars_at_detection=stars_at_detection,
            growth_since_detection=0,
        )
    )
    db.commit()
    return AddRepoResponse(
        job_id=uuid.uuid4(),
        repository_id=repo.id,
        full_name=repo.full_name,
        status="pending",
    )


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def _pct(raw: float | None, v24: float | None) -> float | None:
    """Raw stars/h acceleration -> API-facing % (mirrors row_acceleration_pct)."""
    if raw is None or v24 is None:
        return None
    v_prev = v24 - raw
    return round(raw / max(abs(v_prev), 1.0) * 100.0, 1)


def _detection_info(detection: Detection) -> DetectionInfo:
    return DetectionInfo(
        first_detected_at=detection.first_detected_at,
        stars_at_detection=detection.stars_at_detection,
        growth_since_detection=detection.growth_since_detection,
        first_emerging_at=detection.first_emerging_at,
        first_rising_at=detection.first_rising_at,
        first_breakout_at=detection.first_breakout_at,
        first_viral_at=detection.first_viral_at,
        peak_score=detection.peak_score,
        peak_at=detection.peak_at,
    )


def _detection_events(detection: Detection | None) -> list[HistoryEvent]:
    if detection is None:
        return []
    events = [
        HistoryEvent(
            type="detected",
            ts=detection.first_detected_at,
            label="First detected by Radar",
            description=f"{detection.stars_at_detection} stars at detection",
        )
    ]
    for status_name, ts in (
        ("emerging", detection.first_emerging_at),
        ("rising", detection.first_rising_at),
        ("breakout", detection.first_breakout_at),
        ("viral", detection.first_viral_at),
    ):
        if ts is not None:
            events.append(
                HistoryEvent(
                    type=status_name,
                    ts=ts,
                    label=f"Reached {status_name} status",
                    description=None,
                )
            )
    events.sort(key=lambda e: e.ts)
    return events
