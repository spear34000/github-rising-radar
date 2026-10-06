"""rising-radar CLI — DB 없이 동작하는 단독 버전.

Commands:
  rising-radar check owner/repo   GitHub에서 현재 지표를 가져와 속도/가속도 표시
  rising-radar watch owner/repo   워치리스트에 추가 (+ 즉시 스냅샷)
  rising-radar unwatch owner/repo 워치리스트에서 제거
  rising-radar list               워치리스트의 breakout 스코어 순위
  rising-radar demo               데모 데이터로 리더보드 미리보기 (API 불필요)
"""
from __future__ import annotations
import argparse
import sys
from datetime import datetime, timezone

from . import github, store

# scoring 엔진은 선택적: 있으면 정식 스코어, 없으면 velocity만 표시
try:
    from radar_scoring import (
        Snapshot, compute_metrics, compute_breakout, compute_corpus_stats, CorpusStats,
    )
    HAS_SCORING = True
except Exception:
    HAS_SCORING = False


def _parse_ts(s: str) -> datetime:
    d = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _velocity(snaps: list[dict], hours: float) -> float | None:
    if len(snaps) < 2:
        return None
    now = _parse_ts(snaps[-1]["ts"])
    target = None
    for s in reversed(snaps[:-1]):
        if (now - _parse_ts(s["ts"])).total_seconds() >= hours * 3600:
            target = s
            break
    if target is None:
        target = snaps[0]
    dt_h = (now - _parse_ts(target["ts"])).total_seconds() / 3600
    if dt_h <= 0:
        return None
    return (snaps[-1]["stars"] - target["stars"]) / dt_h


def cmd_check(full_name: str) -> int:
    st = store.load_state()
    try:
        data = github.get_repo(full_name)
    except RuntimeError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    snap = {
        "stars": data.get("stargazers_count", 0),
        "forks": data.get("forks_count", 0),
        "watchers": data.get("subscribers_count", 0),
        "open_issues": data.get("open_issues_count", 0),
        "language": data.get("language"),
        "description": data.get("description"),
    }
    store.add_snapshot(st, full_name, snap)
    store.save_state(st)
    snaps = st["snapshots"][full_name]

    v24 = _velocity(snaps, 24)
    v7d = _velocity(snaps, 24 * 7)
    print(f"★ {full_name}")
    if snap["description"]:
        print(f"  {snap['description'][:120]}")
    print(f"  stars: {snap['stars']:,}  forks: {snap['forks']:,}  language: {snap['language']}")
    print(f"  snapshots: {len(snaps)}")
    if v24 is not None:
        print(f"  velocity 24h: {v24:.1f} stars/h  (+{v24*24:,.0f}/day)")
    else:
        print("  velocity 24h: n/a (스냅샷이 2개 이상 필요 — 주기적으로 check 실행)")
    if v7d is not None:
        print(f"  velocity 7d avg: {v7d:.1f} stars/h")
    if HAS_SCORING and len(snaps) >= 3:
        try:
            snapshots = [
                Snapshot(ts=_parse_ts(s["ts"]), stars=s["stars"], forks=s["forks"])
                for s in snaps[-50:]
            ]
            m = compute_metrics(snapshots)
            corpus = CorpusStats()
            r = compute_breakout(m, corpus, prev_status="normal")
            print(f"  breakout: {r.breakout_score:.1f}/100  status: {r.status}  hype: {r.hype_risk}")
        except Exception as e:
            print(f"  (scoring skipped: {e})")
    elif not HAS_SCORING:
        print("  (pip install ../packages/scoring 하면 breakout 스코어 표시)")
    print(f"  https://github.com/{full_name}")
    return 0


def cmd_watch(full_name: str) -> int:
    st = store.load_state()
    if full_name not in st["watchlist"]:
        st["watchlist"].append(full_name)
        print(f"watching {full_name}")
    else:
        print(f"already watching {full_name}")
    store.save_state(st)
    return cmd_check(full_name)


def cmd_unwatch(full_name: str) -> int:
    st = store.load_state()
    if full_name in st["watchlist"]:
        st["watchlist"].remove(full_name)
        store.save_state(st)
        print(f"unwatched {full_name}")
    else:
        print(f"not in watchlist: {full_name}")
    return 0


def cmd_list() -> int:
    st = store.load_state()
    wl = st["watchlist"]
    if not wl:
        print("watchlist가 비어 있습니다. `rising-radar watch owner/repo`로 추가하세요.")
        print("API 없이 미리보기: `rising-radar demo`")
        return 0
    rows = []
    for full in wl:
        snaps = st["snapshots"].get(full, [])
        v24 = _velocity(snaps, 24) if len(snaps) >= 2 else None
        stars = snaps[-1]["stars"] if snaps else 0
        rows.append((v24 or -1, full, stars, len(snaps)))
    rows.sort(reverse=True)
    print(f"{'repo':<35} {'stars':>10} {'vel24h':>10} {'snaps':>6}")
    print("-" * 65)
    for v24, full, stars, n in rows:
        v = f"{v24:.1f}/h" if v24 >= 0 else "n/a"
        print(f"{full:<35} {stars:>10,} {v:>10} {n:>6}")
    return 0


DEMO = [
    ("neuralforge/tinygrad-turbo", 92, "breakout", "+681/24h"),
    ("quantumlabs/agent-swarm", 97, "viral", "+5,300/24h"),
    ("datadive/vectorlite", 85, "breakout", "+420/24h"),
    ("bytecraft/llm-gateway", 64, "rising", "+95/24h"),
    ("devtools/git-bisect-ui", 76, "breakout", "+2,900/24h (hype:high)"),
]


def cmd_demo() -> int:
    print("🔥 Rising Radar — DEMO leaderboard (synthetic data)")
    print(f"{'repo':<35} {'score':>6} {'status':>10} {'gain':>18}")
    print("-" * 72)
    for repo, score, status, gain in DEMO:
        print(f"{repo:<35} {score:>6.1f} {status:>10} {gain:>18}")
    print("\n실제 데이터: `rising-radar check owner/repo` (GITHUB_TOKEN 권장)")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rising-radar", description="GitHub Rising Radar — standalone CLI")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="fetch + show velocity for a repo")
    c.add_argument("full_name", help="owner/repo")
    w = sub.add_parser("watch", help="add repo to watchlist and snapshot now")
    w.add_argument("full_name", help="owner/repo")
    u = sub.add_parser("unwatch", help="remove repo from watchlist")
    u.add_argument("full_name", help="owner/repo")
    sub.add_parser("list", help="ranked watchlist")
    sub.add_parser("demo", help="demo leaderboard (no API needed)")
    return p


def main(argv=None) -> None:
    args = build_parser().parse_args(argv)
    if args.cmd == "check":
        sys.exit(cmd_check(args.full_name))
    elif args.cmd == "watch":
        sys.exit(cmd_watch(args.full_name))
    elif args.cmd == "unwatch":
        sys.exit(cmd_unwatch(args.full_name))
    elif args.cmd == "list":
        sys.exit(cmd_list())
    elif args.cmd == "demo":
        sys.exit(cmd_demo())


if __name__ == "__main__":
    main()
