# ARCHITECTURE.md — GitHub Rising Radar

## Purpose

GitHub Trending shows what is *already* hot. Rising Radar detects the
*moment* a repository starts breaking out: star velocity, acceleration,
and activity-backed growth, scored deterministically.

## Components

```
┌─────────────┐   ┌──────────────┐   ┌────────────┐   ┌───────────┐
│   worker    │──▶│   postgres   │◀──│    api     │◀──│    web    │
│ (pipeline)  │   │ (store)      │   │ (FastAPI)  │   │ (Next.js) │
└─────────────┘   └──────────────┘   └────────────┘   └───────────┘
       │                 ▲
       ▼                 │ rankings cache
  GitHub REST API   (precomputed,
  (search+repos)     no full scans)
```

### worker (`apps/worker`)
Async pipeline (APScheduler jobs):
1. **discover_candidates** — configurable search buckets (`discovery.yaml`),
   time/star sharding to stay under the 1,000-result search limit,
   dedup by `github_id`.
2. **collect_snapshots** — adaptive polling (1h hot … 12h cold) driven by
   the latest breakout score; `FOR UPDATE SKIP LOCKED`; idempotent
   inserts (`ON CONFLICT DO NOTHING`); ETag conditional requests.
3. **calculate_scores** — metrics → robust normalization against the
   live corpus → deterministic breakout/organic/hype scores.
4. **classify_repositories** — rule-based categories, status state machine
   with hysteresis, first-seen timestamps in `detections` (never deleted).
5. **refresh_rankings** — precomputed leaderboard buckets.
6. **cleanup** — downsample snapshots older than 90 days.

Overlapping runs are prevented with a Postgres advisory lock.

### api (`apps/api`)
FastAPI, sync SQLAlchemy 2. Serves rankings from the precomputed
`rankings` table — never scans the snapshot table per request.
Cursor pagination (opaque base64), OpenAPI docs at `/docs`.

### web (`apps/web`)
Next.js 14 App Router + recharts. Tabs (Top Rising / Emerging /
Breakout / Viral / New / Cooling), filters, repo detail with annotated
charts, score decomposition, "Why is this rising?", Before-it-was-cool
panel, and 2–5 repo comparison. Demo mode (`NEXT_PUBLIC_DEMO=true`)
serves labeled mock data with a DEMO DATA banner.

### postgres
Single database; TimescaleDB optional via `POSTGRES_IMAGE`
(hypertable migration is additive — see `docs/DEPLOYMENT.md`).

## Data flow

```
GitHub API → snapshots → metrics → scores → rankings → API → web
                 │           │          │
                 │      corpus_stats   detections
                 │      (median/MAD)   (first-seen proof)
                 ▼
        "Before it was cool" record
```

## Key design decisions

- **No fabricated history.** Missing windows → `null` + low confidence +
  "Insufficient history" in the UI. GitHub does not expose historic star
  counts, so we never backfill what we did not observe.
- **Deterministic scoring.** Same snapshots → same scores, enforced by
  unit tests on synthetic fixtures. Every score stores `scoring_version`.
- **Robust normalization.** log1p + robust z-score + normal CDF against
  the live corpus; one outlier cannot destroy the scale.
- **Adaptive polling.** Hot repos are sampled hourly, cold ones every
  12h — API budget follows signal, not the other way around.
- **Secrets stay server-side.** The web app never sees `GITHUB_TOKEN`.
