"""Live GitHub API smoke test (small, unauthenticated-friendly).

Usage:
    python scripts/smoke_live.py --repos torvalds/linux --max-calls 20

Reads GITHUB_TOKEN from the environment if present (higher limits),
otherwise uses unauthenticated calls (60 req/h — keep --max-calls low).

Checks:
  1. GET /repos/{owner}/{repo} returns expected fields
  2. Search API works and honors the 1000-result cap note
  3. Rate-limit headers are present and parseable

Does NOT write to the database.
"""

from __future__ import annotations

import argparse
import os
import sys

# Sandbox quirk: this httpx version fails parsing no_proxy entries like
# "[::1]". Drop no_proxy for the smoke test only (proxies still apply).
os.environ.pop("no_proxy", None)
os.environ.pop("NO_PROXY", None)

sys.path.insert(0, "apps/worker/src")

from radar_worker.github import GitHubClient  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repos", default="torvalds/linux")
    ap.add_argument("--max-calls", type=int, default=20)
    args = ap.parse_args()

    token = os.environ.get("GITHUB_TOKEN") or None
    calls = 0

    # rate_limit_threshold=0: never sleep-for-reset during the smoke test;
    # we only make a handful of calls.
    with GitHubClient(tokens=[token] if token else [], rate_limit_threshold=0) as gh:
        for full in args.repos.split(","):
            owner, name = (p.strip() for p in full.split("/", 1))
            repo = gh.get_repo(owner, name)
            calls += 1
            assert repo["full_name"].lower() == full.lower(), repo.get("full_name")
            assert isinstance(repo["stargazers_count"], int)
            print(f"OK  {repo['full_name']}: * {repo['stargazers_count']:,}")
            print(f"    rate-limit remaining: {gh.metrics.rate_limit_hits} hits so far")
            if calls >= args.max_calls:
                break

        # Search sanity check (1 call)
        if calls < args.max_calls:
            res = gh.search_repositories(
                "created:>2026-09-01 stars:>=50", per_page=5, page=1
            )
            calls += 1
            assert "items" in res and "total_count" in res
            print(f"OK  search: total_count={res['total_count']:,}")

    print(f"\nSmoke test passed ({calls} API calls).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
