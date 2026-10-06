# GitHub Rising Radar — Interface Contract

이 문서는 backend/frontend subagent 간 공유 인터페이스 계약이다.
각자 구현하되 아래 스펙을 반드시 지킨다.

## 1. Repository layout

```
github-rising-radar/
  apps/
    web/          # Next.js (App Router) + TypeScript + Tailwind + shadcn/ui + recharts
    api/          # FastAPI
    worker/       # Python async worker (APScheduler 또는 asyncio loop)
  packages/
    schemas/      # Pydantic v2 스키마 (api/worker 공용) — py 패키지 `radar_schemas`
    scoring/      # 스코어링 엔진 — py 패키지 `radar_scoring`, deterministic, 순수함수 위주
  infra/
    docker/       # Dockerfile.api, Dockerfile.worker, Dockerfile.web
  scripts/
  tests/          # pytest (unit + integration), web/ 아래에 vitest + playwright smoke
  docs/           # ARCHITECTURE.md, DATA_PIPELINE.md, SCORING.md, GITHUB_API.md, DEPLOYMENT.md
  docker-compose.yml
  .env.example
  README.md
  Makefile (또는 justfile): make up / make migrate / make seed / make test
```

Python 패키지: `apps/api`, `apps/worker`, `packages/schemas`, `packages/scoring`는
각각 pyproject + src layout. 공통 import는 `pip install -e` 로 설치.

## 2. Database (PostgreSQL 16, TimescaleDB optional)

Alembic 단일 리비전 체인: `apps/api/alembic/` (또는 `packages/db/`).
테이블명·컬럼은 아래와 정확히 일치시킬 것.

### repositories
- id: UUID pk (default gen_random_uuid())
- github_id: BIGINT unique not null
- owner: TEXT not null, name: TEXT not null, full_name: TEXT unique not null
- description: TEXT nullable, url: TEXT not null
- created_at: TIMESTAMPTZ not null, pushed_at: TIMESTAMPTZ nullable
- detected_at: TIMESTAMPTZ not null default now()
- language: TEXT nullable, license: TEXT nullable (SPDX key)
- archived: BOOL default false, fork: BOOL default false
- current_stars: INT default 0, current_forks: INT default 0
- category: TEXT nullable
- topics: TEXT[] default '{}'
- status: TEXT default 'normal'  (normal|emerging|rising|breakout|viral|cooling)
- poll_interval_seconds: INT default 21600
- next_poll_at: TIMESTAMPTZ nullable
- last_snapshot_at: TIMESTAMPTZ nullable
- Indexes: (github_id), (full_name), (status), (category), (language), (current_stars desc)

### repository_snapshots
- id: UUID pk
- repository_id: UUID fk not null
- ts: TIMESTAMPTZ not null
- stars, forks, watchers, open_issues, open_prs: INT not null
- contributors_count: INT nullable
- commit_count_7d: INT nullable
- has_release_14d: BOOL not null default false (최근 14일 내 릴리즈 — activity score 신호)
- Unique (repository_id, ts). Index (repository_id, ts desc).

### scores
- id: UUID pk
- repository_id: UUID fk not null
- ts: TIMESTAMPTZ not null
- star_velocity_1h, _6h, _24h, _7d: DOUBLE nullable (stars/hour)
- acceleration: DOUBLE nullable
- relative_growth: DOUBLE nullable
- fork_velocity_24h: DOUBLE nullable
- fork_star_ratio: DOUBLE nullable
- activity_score: DOUBLE nullable (0~100)
- age_bonus: DOUBLE nullable (0~100)
- breakout_score: DOUBLE not null (0~100)
- organic_score: DOUBLE nullable (0~100)
- hype_risk: TEXT nullable (low|medium|high)
- status: TEXT not null
- score_breakdown: JSONB not null (각 컴포넌트 기여도)
- scoring_version: TEXT not null default 'v1'
- confidence: DOUBLE nullable (0~1, 데이터 부족시 낮음)
- Unique (repository_id, ts). Index (repository_id, ts desc), (breakout_score desc, ts desc).

### detections
- repository_id: UUID fk pk
- first_detected_at: TIMESTAMPTZ not null
- stars_at_detection: INT not null
- first_emerging_at, first_rising_at, first_breakout_at, first_viral_at: TIMESTAMPTZ nullable
- peak_score: DOUBLE nullable, peak_at: TIMESTAMPTZ nullable
- growth_since_detection: INT default 0 (current - stars_at_detection, 주기적 갱신)

### corpus_stats (robust normalization reference)
- metric: TEXT pk (star_velocity_24h | acceleration | relative_growth | fork_velocity_24h)
- median, mad: DOUBLE not null — on the *transformed* scale (log1p / signed log1p)
- sample_count: INT, updated_at: TIMESTAMPTZ

### rankings (leaderboard 캐시 — snapshot table 전체 스캔 방지)
- id: UUID pk
- ts: TIMESTAMPTZ not null
- bucket: TEXT not null  (예: all, category:AI, lang:Python, status:breakout)
- repo_ids: UUID[] / 또는 별도 ranking_entries 테이블
- 단순화: `rankings` 테이블로: (bucket, rank, repository_id, score, ts), Unique(bucket, ts, rank)

### external_mentions (확장용, MVP는 테이블만)
- id, repository_id fk, source (hn|reddit|lobsters|news), external_id, url, title, ts, score

## 3. Scoring engine 계약 (`packages/scoring`)

순수 함수, deterministic, numpy/pandas 없이 표준 라이브러리만(선택 의존성 허용하되 최소).
진입점:

```python
def compute_metrics(snaps: list[Snapshot], age_days: float,
                    now: datetime | None = None) -> Metrics
    # Snapshot: (ts, stars, forks, watchers, open_issues, open_prs,
    #            contributors_count, commit_count_7d, has_release_14d, pushed_at)
    # Metrics: velocity_1h/6h/24h/7d, acceleration (stars/h delta),
    #          relative_growth, fork_velocity_24h, fork_star_ratio,
    #          activity_score, age_bonus_raw, confidence

def compute_breakout(m: Metrics, corpus: CorpusStats,
                     prev_status: str = "normal",
                     peak_score_7d: float | None = None,
                     version: str = "v1") -> BreakoutResult
    # CorpusStats: 각 metric의 분포(변환 스케일 상의 median/MAD) — robust normalization용
    # BreakoutResult: breakout_score, breakdown{star_velocity, acceleration, relative_growth,
    #               fork_growth, activity, age_bonus}, organic_score(+reasons),
    #               hype_risk(+reasons), status, confidence

def classify_status(score: float, prev_status: str = "normal",
                    peak_score_7d: float | None = None,
                    acceleration: float | None = None) -> str
    # 0-29 normal, 30-49 emerging, 50-69 rising, 70-84 breakout, 85-100 viral
    # hysteresis 8pt; peak 대비 하락 + 감속 → cooling

def acceleration_pct(m: Metrics) -> float | None
    # API/UI용 단위: 24h velocity의 전일 대비 % 변화

def corpus_transform(value: float, signed: bool = False) -> float
    # corpus 통계 구축 시 적용하는 변환 (log1p / signed log1p)

def classify_category(description, topics, language, readme_excerpt=None) -> list[str]
    # 규칙 기반. 카테고리: AI, LLM, Agents, DevTools, Security, Database, Infrastructure,
    #   Web, Mobile, Data, Research, Hardware, Games, Other

def explain_score(m: Metrics, repo_full_name: str) -> str
    # deterministic 요약 문장 ("Why is this rising?")

def compute_corpus_stats(all_metrics: list[Metrics]) -> CorpusStats
```

스무딩 상수: `SMOOTHING_STARS = 50` (relative_growth 분모).
Acceleration: recent 24h velocity − previous 24h velocity 를 robust z 로 정규화.
CorpusStats는 worker가 주기적으로 전체 tracked repos 분포에서 계산해 DB(`corpus_stats` 테이블 또는 JSON 파일)에 저장.

## 4. FastAPI 계약 (`apps/api`)

Base path `/api`. OpenAPI 자동 문서. Cursor pagination: `?cursor=<opaque>&limit=`.

- `GET /api/repos` — query: status, category, language, min_stars, max_age_days, sort
  (breakout_score|growth_24h|acceleration|relative_growth|newest), range(24h|7d), limit, cursor
  → `{ items: [RepoCard], next_cursor }`
- `GET /api/repos/{owner}/{name}` → RepoDetail (card + topics, watchers,
  open_issues, created_at, pushed_at, confidence, scoring_version,
  why_rising (deterministic grounded summary), hype_risk_reasons, detections)
- `GET /api/repos/{id}/history` — query: range(7d|30d|90d|all)
  → `{ snapshots: [...], scores: [...], detections: {...}, events: [...] }`
- `GET /api/rankings?bucket=&limit=` → ranking snapshot
- `GET /api/categories` → [{name, count}]
- `GET /api/stats` → {tracked_repos, snapshots_24h, detections_7d, api_calls_24h}
- `POST /api/repos` body `{full_name}` → 수동 등록 (backfill). 202 + job id
- `GET /healthz`, `GET /readyz`

RepoCard JSON 필드:
`{id, owner, name, full_name, description, url, language, license, category[],
 stars, forks, age_days, stars_24h_gain, velocity_24h, acceleration,
 relative_growth, breakout_score, organic_score, hype_risk, status,
 detected_at, score_breakdown{...}}`

- `velocity_24h`: stars/hour (float, nullable)
- `acceleration`: **percent** change of 24h velocity vs the previous 24h
  (float, nullable; e.g. `+182.0` = +182%). Use `radar_scoring.acceleration_pct()`.
  The scoring engine normalizes the raw stars/h delta internally — the API
  always exposes the percent form.
- `relative_growth`: 24h gain / max(prior stars, 50) (float, nullable)

"history 부족" 시 해당 필드는 null + `"insufficient_history": true`. 절대 지어내지 않는다.

## 5. Worker tasks (`apps/worker`)

- `discover_candidates` (30분): configurable discovery strategies (YAML: `worker/discovery.yaml`)
  buckets: new_recent, active_pushed, growing_tracked, high_potential, per_language
  GitHub Search API; 1000 결과 제한 → created/star 구간 분할; github_id dedup.
- `collect_snapshots`: `next_poll_at <= now()` 인 repos를 adaptive interval로 수집.
  REST `/repos/{o}/{n}` + contributors/commit activity (GraphQL은 MVP에서 선택).
- `calculate_metrics` + `calculate_scores`: 새 snapshot → metrics → corpus_stats로 score → scores insert
- `classify_repositories`: category/status 전이 → detections 업데이트
- `refresh_rankings`: rankings 테이블 갱신
- `cleanup`: 오래된 snapshot 정리(90일 초과는 1일 1개로 다운샘플)
- job idempotency: unique constraints + `ON CONFLICT DO NOTHING`, worker lock은
  postgres advisory lock.

GitHub adapter (`apps/worker/radar_worker/github.py` 또는 `packages/`):
token auth, rate-limit inspection (`x-ratelimit-*` 헤더), exponential backoff+jitter,
secondary rate limit(403 + Retry-After) 대응, conditional requests(ETag), paginator,
request metrics 카운터. 토큰 없으면 demo/seed 모드로만 동작.

## 6. CLI (`radar` console script, worker 패키지에 포함)

- `radar add owner/repo`, `radar refresh owner/repo`, `radar score owner/repo`
- `radar discover [--strategy ...]`, `radar worker [--once]`
- `radar seed-demo`, `radar backfill owner/repo`

## 7. Frontend (`apps/web`)

- `/` : 탭 (Top Rising / Emerging / Breakout / Viral / New / Cooling) + 필터
  (category, language, age, min stars, status, time range) + 정렬
- `/repo/[owner]/[name]` : 헤더 + 차트(Stars, Velocity, Breakout score, Forks, recharts)
  + detection annotations + score decomposition + "Why is this rising?" + Before-it-was-cool 패널
- `/compare?repos=a,b,c` : 2~5개 비교 차트
- Demo 모드: `NEXT_PUBLIC_DEMO=true` 시 목업 API 라우트, 화면 상단에 DEMO DATA 배지
- API base URL: `NEXT_PUBLIC_API_URL` (기본 http://localhost:8000)

## 8. 공통 규칙

- 모든 timestamp UTC, ISO8601.
- scoring_version 저장, 동일 입력→동일 출력 (테스트로 검증).
- 과거 데이터捏造 금지. history 부족 → null + insufficient_history.
- Token은 서버 전용. `.env.example`에 전부 문서화.
- 한국어/영어: UI 영문 기본 (개발자 타깃), docs 영문.
