# GitHub Rising Radar 🔥📡

**Catch repositories the moment they start breaking out — not after
they're already famous.**

GitHub Trending shows what's *already* hot. Rising Radar watches star
velocity, acceleration, and activity-backed growth to surface
repositories *as the breakout begins* — with the detection timestamp to
prove "we saw it before it was cool."

## What it does

- 🔥 **Breakout feed** — Top Rising / Emerging / Breakout / Viral / New / Cooling
- 📈 **Real metrics** — star velocity (1h/6h/24h/7d), acceleration,
  relative growth, fork velocity — computed from observed snapshots,
  never fabricated
- 🧮 **Deterministic scoring** — 0–100 Breakout Score with full
  component decomposition (no black box)
- 🌱 **Organic Score + Hype Risk** — is the growth backed by real
  development activity? (never presented as a "bot detector")
- 🕰️ **Before it was cool** — first-detection records are kept forever,
  even if the scoring formula changes
- 🔍 Filters (category, language, age, stars, status), sorting, repo
  detail with annotated charts, 2–5 repo comparison
- 🛠️ Documented REST API (`/docs`), CLI (`radar add owner/repo`), Docker Compose

## Versions

- **CLI (standalone)** — DB 없이 동작하는 단독 CLI. `pipx install ./cli` 후
  `rising-radar demo` / `rising-radar check owner/repo`. 상세: [`cli/README.md`](cli/README.md)
- **Web (GitHub Pages)** — 공식 홈페이지형 정적 사이트. 데모 데이터 내장,
  `<프로젝트명>.github.io` 배포 지원. 상세: [`docs/DEPLOY_PAGES.md`](docs/DEPLOY_PAGES.md)
- **Full stack** — PostgreSQL + worker + API + web (아래 Quick start)

## Quick start

```bash
cp .env.example .env
# optional: add GITHUB_TOKEN to .env for live data
docker compose up --build
```

- Web → http://localhost:3000
- API → http://localhost:8000 · OpenAPI → http://localhost:8000/docs

No token? Set `NEXT_PUBLIC_DEMO=true` (or run `radar seed-demo`) for a
clearly-labeled **DEMO DATA** mode.

## How scoring works

```
breakout = 30% star velocity + 25% acceleration + 15% relative growth
         + 10% fork growth  + 10% activity      + 10% age bonus
```

Each component is robustly normalized (log1p → robust z-score → normal
CDF) against the live corpus of tracked repos, so one outlier can't
break the scale. Same snapshots → same scores, always; every score
stores its `scoring_version`. Full formulas: [`docs/SCORING.md`](docs/SCORING.md).

Status bands: 0–29 Normal · 30–49 Emerging · 50–69 Rising ·
70–84 Breakout · 85–100 Viral · plus **Cooling** when a repo fades from
its peak.

## Architecture

```
worker ──▶ postgres ◀── api (FastAPI) ◀── web (Next.js)
  │            ▲
  ▼      rankings cache
GitHub REST API
```

Details: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) ·
[`docs/DATA_PIPELINE.md`](docs/DATA_PIPELINE.md) ·
[`docs/GITHUB_API.md`](docs/GITHUB_API.md) ·
[`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md)

## Project layout

```
apps/web        Next.js frontend
apps/api        FastAPI + SQLAlchemy 2 + Alembic
apps/worker     discovery / snapshot / scoring pipeline + `radar` CLI
packages/scoring   deterministic scoring engine (pure functions)
packages/schemas   shared pipeline DTOs
infra/docker    Dockerfiles
docs/           architecture, pipeline, scoring, api, deployment
tests/          pytest (scoring unit tests run without a DB)
```

## API examples

```bash
GET /api/repos?status=breakout&sort=breakout_score&limit=20
GET /api/repos/pallets/flask
GET /api/repos/{id}/history?range=30d
GET /api/rankings?bucket=all
GET /api/categories
GET /api/stats
POST /api/repos  {"full_name": "owner/repo"}
```

## Limitations (honest)

- History starts when *we* start watching — GitHub exposes no historic
  star counts, so pre-collection history is `unknown`, never invented.
- Scoring needs a few snapshots before velocity/acceleration are
  meaningful; the UI says "Insufficient history" until then.
- The category classifier is rule-based in v1 (LLM-swappable interface).
- Roadmap hooks (Hacker News, Reddit, social velocity, ML prediction)
  are schema-ready but not implemented — MVP first.

## License

Apache-2.0
