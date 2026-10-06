# radar-worker

Data-collection worker for GitHub Rising Radar.

Jobs (APScheduler):

- `discover_candidates` (every 30 min) — GitHub Search buckets → `repositories`
- `collect_snapshots` (every 5 min) — due repos → `repository_snapshots`
- `calculate_scores` (every 10 min) — snapshots → metrics → `scores` (+ `corpus_stats` refresh)
- `classify_repositories` (every 15 min) — category/status → `detections`
- `refresh_rankings` (every 15 min) — `rankings` leaderboard cache
- `cleanup` (daily) — downsample snapshots older than 90 days

CLI: `radar add|refresh|score|discover|worker|seed-demo|backfill`

See `worker/discovery.yaml` for discovery strategy configuration.
