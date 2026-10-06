# DATA_PIPELINE.md — candidate discovery → snapshots → scores

## 1. Candidate discovery (`discover_candidates`, every 30 min)

We never poll all of GitHub. Discovery runs configurable *buckets*
(`apps/worker/worker/discovery.yaml`):

| bucket | intent | example query |
|---|---|---|
| `new_recent` | newborn repos with traction | `created:>2026-09-29 stars:>=20` |
| `active_pushed` | recently pushed, some stars | `pushed:>2026-10-05 stars:>=100` |
| `high_potential` | young + unusually many stars | `created:>2026-08-01 stars:>=200` |
| `per_language` | language slices | `language:python created:>2026-09-01 stars:>=50` |
| `growing_tracked` | (internal) tracked repos whose last delta was high — re-check sooner |

**1,000-result search cap:** when `total_count` approaches 1,000 the time
range is split in half recursively (created-date sharding). Star-range
sharding is the fallback.

**Dedup:** `github_id` is the identity. Inserts use
`ON CONFLICT (github_id) DO NOTHING`.

## 2. Snapshot collection (`collect_snapshots`, every minute tick)

- Selects repos with `next_poll_at <= now()` using
  `SELECT ... FOR UPDATE SKIP LOCKED` (multi-worker safe).
- Fetches: repo metadata, contributors (sample), commit activity
  (`/stats/commit_activity`, handles HTTP 202 by retrying later),
  recent releases.
- Writes one `repository_snapshots` row; unique `(repository_id, ts)`
  makes retries idempotent.
- Updates `repositories.current_stars/current_forks/pushed_at/
  last_snapshot_at`.
- **Adaptive interval** from the latest breakout score:

| score | interval |
|---|---|
| ≥ 80 | 1 h |
| 50–79 | 3 h |
| 30–49 | 6 h |
| < 30 / none | 12 h |

## 3. Metrics (`calculate_metrics` + `calculate_scores`, every 15 min)

For each repo with a new snapshot since the last run:
1. Load snapshots (newest ~8 days suffice for all windows).
2. `radar_scoring.compute_metrics` → velocities, acceleration,
   relative growth, fork signals, activity, confidence.
3. Refresh `corpus_stats` (median/MAD per metric on the transformed
   scale) from all tracked repos — every 15 min is cheap enough and
   keeps normalization current.
4. `radar_scoring.compute_breakout` → score, breakdown, organic,
   hype risk, status.
5. Insert into `scores` (unique `(repository_id, ts)`).

All timestamps UTC. Division-by-zero and tiny-denominator explosions
are guarded inside the scoring package (see `docs/SCORING.md`).

## 4. Classification (`classify_repositories`, every 15 min)

- Rule-based categories (description/topics/language/README keywords).
  Interface-compatible with a future LLM classifier.
- Status state machine with hysteresis; `cooling` when below 70% of
  the 7-day peak while decelerating.
- First-entry timestamps (`first_emerging_at`, …) written once to
  `detections` and **never deleted** — the "before it was cool" proof.

## 5. Rankings (`refresh_rankings`, every 15 min)

Precomputes top-N per bucket (`all`, `status:*`, `category:*`,
`language:*`) into `rankings`. The API reads this table; the snapshot
table is never scanned per request.

## 6. Cleanup (`cleanup`, daily)

Snapshots older than 90 days are downsampled to one per day
(keeps charts smooth, bounds table growth).

## Failure handling

- Rate limit exhaustion → the collector sleeps until `x-ratelimit-reset`;
  other tasks continue.
- Secondary rate limits (403 + `Retry-After`) → exponential backoff
  with jitter, max 5 retries.
- Any single repo failure never kills the batch (per-repo try/except
  with structured logging).
- Worker crash mid-batch → advisory lock released; next tick resumes;
  unique constraints prevent duplicates.
