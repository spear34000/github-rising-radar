# GitHub Pages 배포 가이드 — `<프로젝트명>.github.io`

웹을 공식 홈페이지 형태로 GitHub Pages에 올리는 방법입니다. Pages 빌드는
**데모 데이터 내장 정적 사이트**라 백엔드가 필요 없습니다.

## A. 조직/사용자 사이트 (`<user>.github.io`)

레포 이름을 `<user>.github.io` 로 만들면 루트 도메인에 바로 배포됩니다.

```bash
# 1. GitHub에서 <user>.github.io 레포 생성 후 push
git remote add origin git@github.com:<user>/<user>.github.io.git
git push -u origin main

# 2. Settings → Pages → Source: "GitHub Actions" 선택
# 3. main에 push하면 .github/workflows/deploy-pages.yml 이 자동 배포
```

워크플로우는 `NEXT_PUBLIC_BASE_PATH` 를 빈 값으로 두어 루트 경로로 빌드합니다.

## B. 프로젝트 페이지 (`<user>.github.io/github-rising-radar`)

일반 레포에 push하면 워크플로우가 레포 이름으로 `basePath` 를 자동 설정합니다.
별도 설정 불필요 — push 후 Settings → Pages → Source: "GitHub Actions".

## 로컬 미리보기 (Pages 빌드와 동일 조건)

```bash
cd apps/web
GITHUB_PAGES=true NEXT_PUBLIC_DEMO=true npm run build
npx serve out   # http://localhost:3000
```

## 주의

- Pages 버전은 `NEXT_PUBLIC_DEMO=true` 고정 — "DEMO DATA" 배너가 항상 표시됩니다.
- 실제 백엔드 연결 버전은 `docker compose up --build` (풀스택) 로 실행하세요.
- `CNAME` 파일로 커스텀 도메인 연결 가능 (Settings → Pages → Custom domain).
