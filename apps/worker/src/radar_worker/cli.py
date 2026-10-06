"""`radar` console script.

Commands:
    radar add owner/repo          Register a repository (backfill start)
    radar refresh owner/repo      Force an immediate snapshot
    radar score owner/repo        Score one repository now
    radar discover [--strategy]   Run discovery once (optionally one bucket)
    radar worker [--once]         Run the scheduler (or all jobs once)
    radar seed-demo               Insert a clearly-marked synthetic demo dataset
    radar backfill owner/repo     add + immediate refresh

Live GitHub commands require GITHUB_TOKENS. seed-demo works without a token.
"""

from __future__ import annotations

import argparse
import random
import sys
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from . import collector, discovery
from .config import get_settings
from .github import NoTokenError, parse_full_name
from .log import get_logger, setup_logging
from .scoring_bridge import (
    load_corpus_stats,
    score_repository,
    snapshots_to_inputs,
    warn_if_unavailable,
)
from .tasks import (
    WorkerContext,
    calculate_scores,
    classify_repositories,
    discover_candidates,
    make_context,
    refresh_rankings,
    run_worker,
)

log = get_logger(__name__)

DEMO_OWNER = "demo-radar"  # obviously synthetic; never a real GitHub org


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def find_repo(session: Any, models: Any, full_name: str) -> Any:
    repo = session.execute(
        select(models.Repository).where(models.Repository.full_name == full_name)
    ).scalar_one_or_none()
    if repo is None:
        print(f"error: repository {full_name!r} is not tracked; use 'radar add' first",
              file=sys.stderr)
        sys.exit(3)
    return repo


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------- #
# commands
# --------------------------------------------------------------------------- #
def cmd_add(ctx: WorkerContext, full_name: str) -> None:
    owner, name = parse_full_name(full_name)
    data = ctx.gh.get_repo(owner, name)
    with ctx.db.session_scope() as session:
        row = discovery.item_to_repo_row(data, _utcnow())
        if row is None:
            print("error: GitHub returned an unusable repository payload", file=sys.stderr)
            sys.exit(4)
        inserted, skipped = discovery.store_candidates(session, ctx.models, [row])
        collector.flush_api_call_log(ctx.gh, session, ctx.models)
    print(f"added {full_name}: inserted={inserted} skipped={skipped}")
    print("note: history before now is unknown; snapshots start accumulating from here")


def cmd_refresh(ctx: WorkerContext, full_name: str) -> None:
    parse_full_name(full_name)
    with ctx.db.session_scope() as session:
        repo = find_repo(session, ctx.models, full_name)
        repo_id = repo.id
    with ctx.db.session_scope() as session:
        summary = collector.run_collection(
            ctx.gh, session, ctx.models, repository_id=repo_id
        )
    print(f"refreshed {full_name}: {summary}")


def cmd_score(ctx: WorkerContext, full_name: str) -> None:
    if not warn_if_unavailable("radar score"):
        sys.exit(5)
    parse_full_name(full_name)
    now = _utcnow()
    with ctx.db.session_scope() as session:
        repo = find_repo(session, ctx.models, full_name)
        snaps = session.execute(
            select(ctx.models.RepositorySnapshot)
            .where(ctx.models.RepositorySnapshot.repository_id == repo.id)
            .order_by(ctx.models.RepositorySnapshot.ts.desc())
            .limit(500)
        ).scalars().all()
        # snapshots_to_inputs sorts ascending; desc+limit keeps the *recent* 500.
        corpus = load_corpus_stats(session, ctx.models)
        row = score_repository(
            session, ctx.models, repo, snapshots_to_inputs(list(snaps), repo),
            corpus, now=now, prev_status=repo.status or "normal",
            version="v1",
        )
        if row is None:
            print(f"insufficient history to score {full_name} "
                  f"({len(snaps)} snapshots); collect more snapshots first")
            return
        stmt = pg_insert(ctx.models.Score).values(row)
        stmt = stmt.on_conflict_do_nothing(index_elements=["repository_id", "ts"])
        session.execute(stmt)
        repo.status = row["status"]
    print(f"{full_name}: breakout={row['breakout_score']:.1f} "
          f"status={row['status']} confidence={row['confidence']}")
    print(f"breakdown: {row['score_breakdown']}")


def cmd_discover(ctx: WorkerContext, strategy: str | None) -> None:
    with ctx.db.session_scope() as session:
        discover_candidates(ctx, session, only_bucket=strategy)
    print("discovery complete" + (f" (strategy={strategy})" if strategy else ""))


def cmd_worker(ctx: WorkerContext, once: bool, jobs: list[str] | None) -> None:
    run_worker(ctx, once=once, only=jobs)


def cmd_backfill(ctx: WorkerContext, full_name: str) -> None:
    """add + immediate refresh. Past history stays unknown (never fabricated)."""
    owner, name = parse_full_name(full_name)
    with ctx.db.session_scope() as session:
        exists = session.execute(
            select(ctx.models.Repository.id).where(
                ctx.models.Repository.full_name == full_name
            )
        ).scalar_one_or_none()
    if exists is None:
        cmd_add(ctx, full_name)
    else:
        print(f"{full_name} already tracked")
    cmd_refresh(ctx, full_name)


# --------------------------------------------------------------------------- #
# seed-demo — synthetic, clearly marked, deterministic
# --------------------------------------------------------------------------- #
_DEMO_SCENARIOS: list[tuple[str, int]] = [
    ("steady", 5),
    ("breakout", 5),
    ("viral", 4),
    ("cooling", 4),
    ("tiny", 4),
    ("old_large", 3),
]

_DEMO_META: dict[str, dict[str, Any]] = {
    "steady": {"age_days": 200, "detected_days_ago": 60,
               "desc": "A steadily maintained developer tool with linear growth."},
    "breakout": {"age_days": 11, "detected_days_ago": 6,
                 "desc": "A new CLI that started breaking out in the last 24 hours."},
    "viral": {"age_days": 25, "detected_days_ago": 8,
              "desc": "A demo repo that went viral in the last 12 hours."},
    "cooling": {"age_days": 60, "detected_days_ago": 20,
                "desc": "Spiked three days ago and is now cooling down."},
    "tiny": {"age_days": 11, "detected_days_ago": 6,
             "desc": "A tiny new repo with fast relative growth."},
    "old_large": {"age_days": 1200, "detected_days_ago": 300,
                  "desc": "A large established project with flat growth."},
}

_DEMO_LANGS = ["Python", "TypeScript", "Rust", "Go", "Python"]
_DEMO_TOPICS = [
    ["cli", "developer-tools"], ["llm", "agents"], ["web", "framework"],
    ["data", "pipeline"], ["security", "scanner"],
]


def _demo_curve(scenario: str, hours_ago: float, rng: random.Random,
                base: float, spike: float) -> float:
    if scenario == "steady":
        return base + 0.15 * (168.0 - hours_ago)
    if scenario == "breakout":
        gain = spike * max(0.0, 1.0 - hours_ago / 24.0) if hours_ago <= 24 else 0.0
        return base + gain
    if scenario == "viral":
        gain = spike * max(0.0, 1.0 - hours_ago / 12.0) if hours_ago <= 12 else 0.0
        return base + gain
    if scenario == "cooling":
        # Peaked 72h ago (+spike), flat since.
        if hours_ago <= 72:
            return base + spike
        return base + spike * max(0.0, (168.0 - hours_ago) / 96.0)
    if scenario == "tiny":
        gain = spike * max(0.0, 1.0 - hours_ago / 24.0) if hours_ago <= 24 else 0.0
        return base + gain
    if scenario == "old_large":
        return base + 1.2 * (168.0 - hours_ago)
    return base


def cmd_seed_demo(ctx: WorkerContext) -> None:
    """Insert 25 synthetic demo repos with scenario time series.

    Every description is prefixed with [DEMO] and the owner is 'demo-radar'
    so this data can never be mistaken for real GitHub data.
    """
    now = _utcnow()
    ctx.db.create_all()  # dev convenience; production uses Alembic

    with ctx.db.session_scope() as session:
        models = ctx.models
        total_repos = 0
        total_snaps = 0
        idx = 0
        for scenario, count in _DEMO_SCENARIOS:
            meta = _DEMO_META[scenario]
            for n in range(count):
                idx += 1
                rng = random.Random(20261006 + idx)  # deterministic
                name = f"demo-{scenario}-{n + 1:02d}"
                full_name = f"{DEMO_OWNER}/{name}"
                base = {
                    "steady": rng.uniform(300, 900),
                    "breakout": rng.uniform(150, 500),
                    "viral": rng.uniform(400, 1200),
                    "cooling": rng.uniform(200, 600),
                    "tiny": rng.uniform(5, 15),
                    "old_large": rng.uniform(30000, 60000),
                }[scenario]
                spike = {
                    "steady": 0.0, "breakout": rng.uniform(1200, 2500),
                    "viral": rng.uniform(6000, 12000),
                    "cooling": rng.uniform(2000, 3500),
                    "tiny": rng.uniform(40, 80), "old_large": 0.0,
                }[scenario]
                age_days = meta["age_days"]
                created_at = now - timedelta(days=age_days)
                detected_at = now - timedelta(days=meta["detected_days_ago"])

                # Hourly snapshots for the past 7 days, monotone non-decreasing.
                star_points: list[tuple[datetime, float]] = []
                for k in range(168):
                    hours_ago = 167 - k
                    ts = now - timedelta(hours=hours_ago)
                    raw = _demo_curve(scenario, hours_ago, rng, base, spike)
                    raw += rng.gauss(0, max(1.0, base * 0.004))
                    star_points.append((ts, max(1.0, raw)))
                monotone: list[tuple[datetime, int]] = []
                running = 0
                for ts, s in star_points:
                    running = max(running, int(round(s)))
                    monotone.append((ts, running))

                current_stars = monotone[-1][1]
                # stars_at_detection: interpolate from the curve.
                det_hours_ago = meta["detected_days_ago"] * 24.0
                det_stars = int(round(_demo_curve(scenario, det_hours_ago, rng, base, spike)))

                lang = _DEMO_LANGS[idx % len(_DEMO_LANGS)]
                topics = _DEMO_TOPICS[idx % len(_DEMO_TOPICS)]
                repo_row = {
                    "github_id": 9_000_000 + idx,  # synthetic id space
                    "owner": DEMO_OWNER,
                    "name": name,
                    "full_name": full_name,
                    "description": (
                        f"[DEMO] Synthetic demo data — not a real repository. {meta['desc']}"
                    ),
                    "url": f"https://github.com/{full_name}",
                    "created_at": created_at,
                    "pushed_at": now - timedelta(hours=rng.uniform(1, 48)),
                    "detected_at": detected_at,
                    "language": lang,
                    "license": "Apache-2.0",
                    "archived": False,
                    "fork": False,
                    "current_stars": current_stars,
                    "current_forks": max(1, int(current_stars / 12)),
                    "topics": topics,
                    "status": "normal",
                    "next_poll_at": now,
                }
                stmt = pg_insert(models.Repository).values(repo_row)
                stmt = stmt.on_conflict_do_nothing(index_elements=["github_id"])
                session.execute(stmt)
                repo_id = session.execute(
                    select(models.Repository.id).where(
                        models.Repository.github_id == repo_row["github_id"]
                    )
                ).scalar_one()

                det_stmt = pg_insert(models.Detection).values({
                    "repository_id": repo_id,
                    "first_detected_at": detected_at,
                    "stars_at_detection": det_stars,
                    "growth_since_detection": current_stars - det_stars,
                })
                det_stmt = det_stmt.on_conflict_do_nothing()
                session.execute(det_stmt)

                snap_rows = []
                contrib_base = rng.randint(1, 5)
                for ts, stars in monotone:
                    forks = max(0, int(stars / 12 + rng.gauss(0, 2)))
                    snap_rows.append({
                        "repository_id": repo_id,
                        "ts": ts,
                        "stars": stars,
                        "forks": forks,
                        "watchers": max(0, int(stars / 8 + rng.gauss(0, 3))),
                        "open_issues": rng.randint(0, 30),
                        "open_prs": rng.randint(0, 8),
                        "contributors_count": contrib_base + (
                            rng.randint(0, 6) if stars > base * 1.5 else 0),
                        "commit_count_7d": rng.randint(0, 40),
                    })
                sstmt = pg_insert(models.RepositorySnapshot).values(snap_rows)
                sstmt = sstmt.on_conflict_do_nothing(
                    index_elements=["repository_id", "ts"])
                session.execute(sstmt)
                total_repos += 1
                total_snaps += len(snap_rows)

        session.commit()
        print(f"seeded {total_repos} [DEMO] repos, {total_snaps} snapshots")

        # Score + classify right away so the demo UI has data (if scoring exists).
        if warn_if_unavailable("seed-demo scoring"):
            calculate_scores(ctx, session)
            classify_repositories(ctx, session)
            refresh_rankings(ctx, session)
            print("demo repos scored, classified, and ranked")
        else:
            print("radar_scoring not installed: demo data inserted unscored")


# --------------------------------------------------------------------------- #
# entrypoint
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="radar", description="GitHub Rising Radar worker CLI")
    sub = p.add_subparsers(dest="command", required=True)

    a = sub.add_parser("add", help="register a repository for tracking")
    a.add_argument("full_name", help="owner/repo")

    r = sub.add_parser("refresh", help="force an immediate snapshot")
    r.add_argument("full_name", help="owner/repo")

    s = sub.add_parser("score", help="score one repository now")
    s.add_argument("full_name", help="owner/repo")

    d = sub.add_parser("discover", help="run candidate discovery once")
    d.add_argument("--strategy", default=None,
                   help="run only this discovery bucket")

    w = sub.add_parser("worker", help="run the worker")
    w.add_argument("--once", action="store_true",
                   help="run all jobs once and exit")
    w.add_argument("--jobs", default=None,
                   help="comma-separated job names (with --once)")

    sub.add_parser("seed-demo", help="insert synthetic, clearly-marked demo data")

    b = sub.add_parser("backfill", help="register a repo and snapshot it now")
    b.add_argument("full_name", help="owner/repo")
    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    settings = get_settings()
    setup_logging(settings.log_level, settings.log_json)
    ctx = make_context(settings)
    try:
        live_commands = {"add", "refresh", "discover", "worker", "backfill"}
        if args.command in live_commands and not settings.has_github_token:
            print("error: GITHUB_TOKENS is not set — live GitHub access unavailable.\n"
                  "Use 'radar seed-demo' for a token-free demo dataset.",
                  file=sys.stderr)
            sys.exit(2)
        if args.command == "add":
            cmd_add(ctx, args.full_name)
        elif args.command == "refresh":
            cmd_refresh(ctx, args.full_name)
        elif args.command == "score":
            cmd_score(ctx, args.full_name)
        elif args.command == "discover":
            cmd_discover(ctx, args.strategy)
        elif args.command == "worker":
            jobs = args.jobs.split(",") if args.jobs else None
            cmd_worker(ctx, once=args.once, jobs=jobs)
        elif args.command == "seed-demo":
            cmd_seed_demo(ctx)
        elif args.command == "backfill":
            cmd_backfill(ctx, args.full_name)
    except NoTokenError as e:
        print(f"error: {e}", file=sys.stderr)
        sys.exit(2)
    finally:
        ctx.close()


if __name__ == "__main__":
    main()
