# GITHUB_API.md — GitHub API usage

## REST + GraphQL mix

MVP uses **REST** (`apps/worker/radar_worker/github.py`):

- `GET /search/repositories` — candidate discovery
- `GET /repos/{owner}/{repo}` — metadata snapshot
- `GET /repos/{owner}/{repo}/contributors?per_page=100` — contributor count (paginated, capped)
- `GET /repos/{owner}/{repo}/stats/commit_activity` — weekly commit sums (HTTP 202 → retry later)
- `GET /repos/{owner}/{repo}/releases?per_page=5` — release activity

GraphQL is reserved for a later optimization (single-query repo bundles);
the adapter interface is shaped so a GraphQL implementation can slot in.

## Authentication

- `GITHUB_TOKEN` (PAT classic or fine-grained), server-side only.
- Optional `GITHUB_TOKENS` comma-separated list → round-robin rotation
  for higher aggregate rate limits.
- No token → worker refuses live calls (`NoTokenError`); only demo/seed
  mode works. The web app never receives any token.

## Rate-limit discipline

| limit | value | handling |
|---|---|---|
| REST core | 5,000 req/h per token | every response's `x-ratelimit-remaining/reset` inspected; sleep until reset when low |
| Search | 30 req/min per token | discovery buckets are spaced; 429/403 → backoff |
| Secondary | dynamic | 403 with `Retry-After` → exponential backoff + jitter, ≤5 retries |

Additional measures:

- **Conditional requests**: ETags stored per repo; `304 Not Modified`
  costs nothing against the interesting limits and skips snapshot writes
  when nothing changed.
- **Batching**: discovery pages at `per_page=100`; snapshot loop uses
  `FOR UPDATE SKIP LOCKED` so multiple workers share the queue.
- **Request metrics**: per-endpoint counters + `rate_limit_hits` exposed
  via `/api/stats` (worker writes to a metrics table / in-memory agg).
- **Timeouts**: 15 s connect/read; retries only for 5xx/429/secondary.

## What we do NOT do

- No HTML scraping of github.com/trending (forbidden by spec §36).
- No fabricated historical star counts — GitHub offers no historic star
  API, so pre-collection history is `unknown`, never invented.
- No token in logs, error messages, or the frontend bundle.
