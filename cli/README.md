# rising-radar CLI

GitHub Rising Radar의 **DB 없는 단독 CLI** 버전. GitHub API로 직접 조회하고 스냅샷은 `~/.rising-radar/state.json`에 로컬 저장합니다.

## 설치

```bash
# pipx (권장)
pipx install ./cli
# 또는 pip
pip install ./cli
# scoring 엔진까지 (breakout 스코어 표시)
pip install ./packages/scoring
```

## 사용법

```bash
# 데모 리더보드 (API 불필요)
rising-radar demo

# 단일 레포 체크 (스냅샷 저장)
rising-radar check owner/repo

# 워치리스트
rising-radar watch owner/repo
rising-radar list
rising-radar unwatch owner/repo
```

반복 실행할수록 velocity/가속도가 정확해집니다. GitHub rate limit(시간당 60회)을 넘기려면:

```bash
export GITHUB_TOKEN=ghp_...
```

## 명령어

| 명령 | 설명 |
|------|------|
| `check owner/repo` | 현재 stars/forks 조회 + 24h velocity 표시 |
| `watch owner/repo` | 워치리스트 추가 + 즉시 스냅샷 |
| `list` | 워치리스트를 velocity 순으로 정렬 |
| `unwatch owner/repo` | 워치리스트에서 제거 |
| `demo` | 합성 데모 리더보드 |

## 데이터

- `~/.rising-radar/state.json`에 저장 (삭제하면 초기화)
- `RISING_RADAR_HOME` 환경변수로 경로 변경 가능
- 히스토리는 수집 시점부터만 쌓입니다 (과거는 추정하지 않음)

## 풀스택 버전과 차이

| | CLI (이것) | 풀스택 (docker compose) |
|---|---|---|
| DB | 불필요 (로컬 JSON) | PostgreSQL |
| 스코어링 | velocity 중심 (scoring 설치 시 breakout 표시) | 전체 파이프라인 |
| 랭킹 | 내 워치리스트만 | 전체 코퍼스 대상 |

License: Apache-2.0
