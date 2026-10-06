"""Local JSON store: ~/.rising-radar/state.json"""
from __future__ import annotations
import json
import os
from pathlib import Path
from datetime import datetime, timezone

def state_dir() -> Path:
    d = Path(os.environ.get("RISING_RADAR_HOME", Path.home() / ".rising-radar"))
    d.mkdir(parents=True, exist_ok=True)
    return d

def state_file() -> Path:
    return state_dir() / "state.json"

def load_state() -> dict:
    f = state_file()
    if not f.exists():
        return {"watchlist": [], "snapshots": {}}
    try:
        return json.loads(f.read_text())
    except Exception:
        return {"watchlist": [], "snapshots": {}}

def save_state(s: dict) -> None:
    state_file().write_text(json.dumps(s, indent=2, ensure_ascii=False))

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()

def add_snapshot(state: dict, full_name: str, snap: dict) -> None:
    arr = state.setdefault("snapshots", {}).setdefault(full_name, [])
    arr.append({"ts": now_iso(), **snap})
    # keep last 500
    if len(arr) > 500:
        state["snapshots"][full_name] = arr[-500:]
