# DEPLOYMENT.md

## Local (one command)

```bash
cp .env.example .env
# add your GITHUB_TOKEN to .env (optional — without it you get demo mode)
docker compose up --build
```

- Web: http://localhost:3000
- API: http://localhost:8000 (OpenAPI: http://localhost:8000/docs)
- Postgres: localhost:5432

Migrations run automatically on API startup (`alembic upgrade head`).

## Demo mode (no token)

```bash
NEXT_PUBLIC_DEMO=true docker compose up --build
# or: docker compose run --rm worker radar seed-demo
```

The UI shows a **DEMO DATA** banner; seeded repos are synthetic and
marked `[DEMO]` in their descriptions.

## Useful commands

```bash
make migrate        # run alembic migrations (local dev)
make seed           # radar seed-demo
make test           # pytest (tests/ — scoring unit tests run without a DB)
make smoke          # live GitHub smoke test (few repos, ~20 API calls)

# CLI inside the worker container
docker compose run --rm worker radar add owner/repo
docker compose run --rm worker radar refresh owner/repo
docker compose run --rm worker radar discover --once
```

## TimescaleDB (optional)

```bash
# .env
POSTGRES_IMAGE=timescale/timescaledb:latest-pg16
```

Then enable the hypertable (additive, safe to apply on existing data):

```sql
SELECT create_hypertable('repository_snapshots', 'ts', if_not_exists => TRUE);
SELECT create_hypertable('scores', 'ts', if_not_exists => TRUE);
```

Continuous aggregates for 1-day rollups can be added later; the
`rankings` cache table already keeps hot queries off the raw tables.

## Production notes

- Put the API behind TLS termination (Caddy/Traefik/Nginx).
- Set `POSTGRES_PASSWORD` to a strong value; do not expose 5432 publicly.
- Scale workers horizontally — the advisory lock + `SKIP LOCKED`
  queue make this safe.
- Back up Postgres; `detections` is the irreplaceable "proof" table.
- Monitor: `/healthz`, `/readyz`, `/api/stats` (snapshots/24h,
  API calls/24h, rate-limit hits).
