"""Ranking endpoints — read from the ``rankings`` cache table.

The leaderboard is NEVER computed by scanning the snapshots table per
request; the worker's ``refresh_rankings`` task maintains ``rankings`` and
the API only reads the latest snapshot per bucket.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..db import get_db
from ..models import Ranking, Repository
from ..repo_cards import card_select, row_to_card
from ..schemas import RankingEntry, RankingResponse

router = APIRouter(prefix="/rankings", tags=["rankings"])

BUCKET_PATTERN = r"^[A-Za-z0-9:_-]+$"


@router.get(
    "",
    response_model=RankingResponse,
    summary="Ranking snapshot",
    description=(
        "Latest precomputed ranking for a bucket (e.g. `all`, `status:breakout`, "
        "`category:AI`, `lang:Python`). Each entry carries the full repo card."
    ),
)
def get_rankings(
    db: Session = Depends(get_db),
    bucket: str = Query(default="all", pattern=BUCKET_PATTERN, max_length=64),
    limit: int = Query(default=20, ge=1, le=100),
) -> RankingResponse:
    latest_ts = db.scalar(select(func.max(Ranking.ts)).where(Ranking.bucket == bucket))
    if latest_ts is None:
        return RankingResponse(bucket=bucket, ts=None, items=[])

    entries = (
        db.execute(
            select(Ranking)
            .where(Ranking.bucket == bucket, Ranking.ts == latest_ts)
            .order_by(Ranking.rank.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    if not entries:
        return RankingResponse(bucket=bucket, ts=latest_ts, items=[])

    now = datetime.now(timezone.utc)
    stmt, _ = card_select()
    rows = db.execute(
        stmt.where(Repository.id.in_([e.repository_id for e in entries]))
    ).all()
    cards = {}
    for r in rows:
        card = row_to_card(r, now)
        cards[card.id] = card

    items = [
        RankingEntry(rank=e.rank, score=e.score, repo=cards[e.repository_id])
        for e in entries
        if e.repository_id in cards
    ]
    return RankingResponse(bucket=bucket, ts=latest_ts, items=items)
