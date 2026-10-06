"""Minimal GitHub REST client (stdlib only)."""
from __future__ import annotations
import json
import os
import urllib.request
import urllib.error

API = "https://api.github.com"

def _headers() -> dict:
    h = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "rising-radar-cli/0.1.0",
    }
    tok = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if tok:
        h["Authorization"] = f"Bearer {tok.strip()}"
    return h

def get_repo(full_name: str) -> dict:
    req = urllib.request.Request(f"{API}/repos/{full_name}", headers=_headers())
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode()[:500] if hasattr(e, "read") else ""
        raise RuntimeError(f"GitHub API {e.code} for {full_name}: {body}")
