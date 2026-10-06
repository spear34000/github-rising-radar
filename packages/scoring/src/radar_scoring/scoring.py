"""Deterministic scoring engine for GitHub Rising Radar.

Pure functions, stdlib only. Same snapshots in -> same scores out.
See docs/SCORING.md for the full specification.

Nothing here invents history: missing windows yield ``None`` and lower
the confidence instead of being fabricated.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

SCORING_VERSION = "v1"

# Smoothing constant for relative growth: prevents tiny repos from dominating.
SMOOTHING_STARS = 50

# Robust-normalization clip range (z-space).
_Z_CLIP = 4.0
_MAD_SCALE = 1.4826  # makes MAD consistent with std for normal data
_EPS = 1e-9

# Breakout weights (renormalized over available components when some are missing).
W_VELOCITY = 0.30
W_ACCEL = 0.25
W_REL_GROWTH = 0.15
W_FORK = 0.10
W_ACTIVITY = 0.10
W_AGE = 0.10

# Status thresholds.
STATUS_BANDS = [
    (85.0, "viral"),
    (70.0, "breakout"),
    (50.0, "rising"),
    (30.0, "emerging"),
    (0.0, "normal"),
]
_HYSTERESIS = 8.0  # points below a band edge before dropping a level


# --------------------------------------------------------------------------- #
# Data types
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Snapshot:
    ts: datetime  # timezone-aware, UTC
    stars: int
    forks: int
    watchers: int = 0
    open_issues: int = 0
    open_prs: int = 0
    contributors_count: int | None = None
    commit_count_7d: int | None = None
    has_release_14d: bool = False
    pushed_at: datetime | None = None


@dataclass(frozen=True)
class Metrics:
    velocity_1h: float | None
    velocity_6h: float | None
    velocity_24h: float | None
    velocity_7d: float | None
    acceleration: float | None
    relative_growth: float | None
    fork_velocity_24h: float | None
    fork_star_ratio: float | None
    activity_score: float | None  # 0..100
    age_bonus_raw: float  # 0..100, ungated
    confidence: float  # 0..1
    # helper fields for explanations / UI
    stars_now: int = 0
    stars_24h_gain: int | None = None
    forks_24h_gain: int | None = None
    age_days: float = 0.0


@dataclass(frozen=True)
class CorpusStats:
    """Per-metric (median, mad) on the *transformed* scale.

    Transform: log1p for non-negative heavy-tailed metrics,
    signed log1p for acceleration.
    """

    stats: dict[str, tuple[float, float]] = field(default_factory=dict)

    def get(self, metric: str) -> tuple[float, float]:
        # Deterministic fallback when the corpus is not available yet.
        return self.stats.get(metric, (0.0, 1.0))


@dataclass(frozen=True)
class BreakoutResult:
    breakout_score: float  # 0..100
    breakdown: dict[str, float]  # component -> point contribution
    organic_score: float | None  # 0..100
    organic_reasons: tuple[str, ...]
    hype_risk: str  # low|medium|high
    hype_reasons: tuple[str, ...]
    status: str
    confidence: float
    scoring_version: str = SCORING_VERSION


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _ensure_utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        return ts.replace(tzinfo=timezone.utc)
    return ts.astimezone(timezone.utc)


def _phi(z: float) -> float:
    """Standard normal CDF."""
    return 0.5 * (1.0 + math.erf(z / math.sqrt(2.0)))


def _signed_log1p(x: float) -> float:
    return math.copysign(math.log1p(abs(x)), x)


def corpus_transform(value: float, signed: bool = False) -> float:
    """The transform applied before corpus median/MAD statistics.

    Must be used by anything that *builds* corpus stats (worker) so the
    stored (median, MAD) live on the same scale that ``robust_norm``
    expects. ``signed=True`` for acceleration (can be negative).
    """
    return _signed_log1p(value) if signed else math.log1p(max(value, 0.0))


def robust_norm(x: float | None, corpus: CorpusStats, metric: str, signed: bool = False) -> float | None:
    """Map a raw metric to 0..100 via robust normalization.

    Returns None when x is None (caller decides how to handle missing data).
    """
    if x is None:
        return None
    t = corpus_transform(x, signed=signed)
    median, mad = corpus.get(metric)
    z = (t - median) / (_MAD_SCALE * mad + _EPS)
    z = max(-_Z_CLIP, min(_Z_CLIP, z))
    return 100.0 * _phi(z)


def _ref_snapshot(snaps: list[Snapshot], now: datetime, window: timedelta) -> Snapshot | None:
    """Latest snapshot at/before ``now - window``, within tolerance.

    Tolerance: window + max(25% of window, 15 minutes) lookback.
    Requires the elapsed interval to be at least 50% of the window
    (shorter intervals are too noisy).
    """
    if not snaps:
        return None
    ideal = now - window
    tol = window + max(window * 0.25, timedelta(minutes=15))
    earliest = ideal - tol
    best: Snapshot | None = None
    for s in snaps:
        if earliest <= s.ts <= ideal:
            if best is None or s.ts > best.ts:
                best = s
    if best is None:
        return None
    elapsed_h = (now - best.ts).total_seconds() / 3600.0
    if elapsed_h < (window.total_seconds() / 3600.0) * 0.5:
        return None
    return best


def _velocity(now_s: Snapshot, ref: Snapshot | None) -> tuple[float | None, int | None]:
    if ref is None:
        return None, None
    hours = (now_s.ts - ref.ts).total_seconds() / 3600.0
    if hours <= 0:
        return None, None
    return (now_s.stars - ref.stars) / hours, now_s.stars - ref.stars

# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #
def age_bonus(age_days: float) -> float:
    """0..100 age bonus with linear interpolation between bands."""
    if age_days < 0:
        age_days = 0.0
    if age_days < 7:
        return 100.0
    if age_days < 30:
        return 100.0 - (age_days - 7) / 23.0 * 30.0
    if age_days < 90:
        return 70.0 - (age_days - 30) / 60.0 * 30.0
    return 0.0


def _activity_score(snaps: list[Snapshot], now: datetime) -> tuple[float | None, float]:
    """Return (activity_score 0..100 or None, confidence_penalty 0..1)."""
    if not snaps:
        return None, 1.0
    latest = snaps[-1]
    penalty = 0.0

    commits = latest.commit_count_7d
    if commits is None:
        commits_part, penalty = 0.0, penalty + 0.25
    else:
        commits_part = 100.0 * min(1.0, max(commits, 0) / 50.0)

    if latest.pushed_at is None:
        recency_part, penalty = 0.0, penalty + 0.15
    else:
        hours = max(0.0, (now - _ensure_utc(latest.pushed_at)).total_seconds() / 3600.0)
        recency_part = 100.0 * math.exp(-hours / 168.0)

    ref24 = _ref_snapshot(snaps[:-1], now, timedelta(hours=24))
    if ref24 is None:
        events_part = 0.0
        penalty += 0.1
    else:
        delta = (latest.open_prs + latest.open_issues) - (ref24.open_prs + ref24.open_issues)
        events_part = 100.0 * min(1.0, max(delta, 0) / 20.0)

    ref7d = _ref_snapshot(snaps[:-1], now, timedelta(days=7))
    if latest.contributors_count is None or ref7d is None or ref7d.contributors_count is None:
        contrib_part = 0.0
        penalty += 0.1
    else:
        growth = latest.contributors_count - ref7d.contributors_count
        contrib_part = 100.0 * min(1.0, max(growth, 0) / 10.0)

    release_part = 100.0 if latest.has_release_14d else 0.0

    score = (
        0.35 * commits_part
        + 0.20 * recency_part
        + 0.20 * events_part
        + 0.15 * contrib_part
        + 0.10 * release_part
    )
    return score, min(penalty, 0.6)


def compute_metrics(snaps: list[Snapshot], age_days: float, now: datetime | None = None) -> Metrics:
    """Compute all metrics from a time-ordered snapshot list (oldest first)."""
    now = _ensure_utc(now or datetime.now(timezone.utc))
    snaps = sorted((s for s in snaps), key=lambda s: s.ts)
    if not snaps:
        return Metrics(
            None, None, None, None, None, None, None, None, None,
            age_bonus(max(age_days, 0.0)), 0.0, 0, None, None, max(age_days, 0.0),
        )
    latest = snaps[-1]
    prior = snaps[:-1]

    v1h, _ = _velocity(latest, _ref_snapshot(prior, now, timedelta(hours=1)))
    v6h, _ = _velocity(latest, _ref_snapshot(prior, now, timedelta(hours=6)))
    v24h, gain24 = _velocity(latest, _ref_snapshot(prior, now, timedelta(hours=24)))
    v7d, _ = _velocity(latest, _ref_snapshot(prior, now, timedelta(days=7)))

    # Acceleration: recent 24h velocity minus previous 24h velocity.
    acceleration: float | None = None
    if v24h is not None:
        s24 = _ref_snapshot(prior, now, timedelta(hours=24))
        s48 = _ref_snapshot(prior, now, timedelta(hours=48))
        if s24 is not None and s48 is not None:
            hours = (s24.ts - s48.ts).total_seconds() / 3600.0
            if hours > 0:
                v_prev = (s24.stars - s48.stars) / hours
                acceleration = v24h - v_prev

    # Relative growth with smoothing.
    relative_growth: float | None = None
    if gain24 is not None:
        s24 = _ref_snapshot(prior, now, timedelta(hours=24))
        if s24 is not None:
            relative_growth = gain24 / max(s24.stars, SMOOTHING_STARS)

    # Fork signals.
    fork_velocity_24h: float | None = None
    forks_gain: int | None = None
    s24 = _ref_snapshot(prior, now, timedelta(hours=24))
    if s24 is not None:
        hours = (latest.ts - s24.ts).total_seconds() / 3600.0
        if hours > 0:
            forks_gain = latest.forks - s24.forks
            fork_velocity_24h = forks_gain / hours
    fork_star_ratio: float | None = None
    if fork_velocity_24h is not None and v24h is not None and v24h > _EPS:
        fork_star_ratio = fork_velocity_24h / v24h

    activity, act_penalty = _activity_score(snaps, now)

    # Confidence from data sufficiency.
    n = len(snaps)
    span_h = (latest.ts - snaps[0].ts).total_seconds() / 3600.0 if n > 1 else 0.0
    if n < 3:
        confidence = 0.3
    elif span_h < 24:
        confidence = 0.6
    else:
        confidence = 1.0
    missing_windows = sum(v is None for v in (v1h, v6h, v24h, v7d, acceleration))
    confidence = max(0.0, min(1.0, confidence - 0.1 * missing_windows - act_penalty * 0.5))

    return Metrics(
        velocity_1h=v1h,
        velocity_6h=v6h,
        velocity_24h=v24h,
        velocity_7d=v7d,
        acceleration=acceleration,
        relative_growth=relative_growth,
        fork_velocity_24h=fork_velocity_24h,
        fork_star_ratio=fork_star_ratio,
        activity_score=activity,
        age_bonus_raw=age_bonus(max(age_days, 0.0)),
        confidence=confidence,
        stars_now=latest.stars,
        stars_24h_gain=gain24,
        forks_24h_gain=forks_gain,
        age_days=max(age_days, 0.0),
    )


def compute_corpus_stats(all_metrics: list[Metrics]) -> CorpusStats:
    """Build corpus (median, MAD) on the transformed scale from tracked repos."""
    out: dict[str, tuple[float, float]] = {}
    specs = [
        ("star_velocity_24h", lambda m: m.velocity_24h, False),
        ("acceleration", lambda m: m.acceleration, True),
        ("relative_growth", lambda m: m.relative_growth, False),
        ("fork_velocity_24h", lambda m: m.fork_velocity_24h, False),
    ]
    for name, get, signed in specs:
        vals = []
        for m in all_metrics:
            v = get(m)
            if v is not None:
                vals.append(corpus_transform(v, signed=signed))
        if len(vals) < 5:
            continue  # not enough data; callers fall back to defaults
        vals.sort()
        mid = len(vals) // 2
        median = vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2
        mad = sorted(abs(v - median) for v in vals)[mid] if len(vals) % 2 else None
        if mad is None:
            devs = sorted(abs(v - median) for v in vals)
            mad = (devs[mid - 1] + devs[mid]) / 2
        out[name] = (median, max(mad, _EPS))
    return CorpusStats(out)

# --------------------------------------------------------------------------- #
# Breakout score
# --------------------------------------------------------------------------- #
def compute_breakout(
    m: Metrics,
    corpus: CorpusStats,
    prev_status: str = "normal",
    peak_score_7d: float | None = None,
    version: str = SCORING_VERSION,
) -> BreakoutResult:
    """Deterministic breakout scoring. Missing metrics renormalize weights."""
    nv = robust_norm(m.velocity_24h, corpus, "star_velocity_24h")
    na = robust_norm(m.acceleration, corpus, "acceleration", signed=True)
    nrg = robust_norm(m.relative_growth, corpus, "relative_growth")
    nf = robust_norm(m.fork_velocity_24h, corpus, "fork_velocity_24h")

    # Age bonus is gated: it cannot lift a repo with no velocity.
    v24 = m.velocity_24h or 0.0
    gated_age = m.age_bonus_raw * min(1.0, max(v24, 0.0) / 5.0)

    parts: list[tuple[str, float | None, float]] = [
        ("star_velocity", nv, W_VELOCITY),
        ("acceleration", na, W_ACCEL),
        ("relative_growth", nrg, W_REL_GROWTH),
        ("fork_growth", nf, W_FORK),
        ("activity", m.activity_score, W_ACTIVITY),
        ("age_bonus", gated_age, W_AGE),
    ]
    available = [(k, v, w) for k, v, w in parts if v is not None]
    breakdown: dict[str, float] = {}
    if available:
        wsum = sum(w for _, _, w in available)
        score = 0.0
        for k, v, w in available:
            contrib = v * (w / wsum)
            breakdown[k] = round(contrib, 2)
            score += contrib
    else:
        score = 0.0
    score = round(max(0.0, min(100.0, score)), 2)

    organic, organic_reasons = _organic_score(m)
    hype_risk, hype_reasons = _hype_risk(m)
    status = classify_status(score, prev_status, peak_score_7d, m.acceleration)

    return BreakoutResult(
        breakout_score=score,
        breakdown=breakdown,
        organic_score=organic,
        organic_reasons=organic_reasons,
        hype_risk=hype_risk,
        hype_reasons=hype_reasons,
        status=status,
        confidence=m.confidence,
        scoring_version=version,
    )


# --------------------------------------------------------------------------- #
# Status state machine
# --------------------------------------------------------------------------- #
def _raw_status(score: float) -> str:
    for bound, name in STATUS_BANDS:
        if score >= bound:
            return name
    return "normal"


def _level(status: str) -> int:
    order = ["normal", "emerging", "rising", "breakout", "viral"]
    return order.index(status) if status in order else 0


def classify_status(
    score: float,
    prev_status: str = "normal",
    peak_score_7d: float | None = None,
    acceleration: float | None = None,
) -> str:
    """Status with hysteresis; cooling when past-peak and decelerating."""
    raw = _raw_status(score)
    # Hysteresis on the way down: stay until 8 points below the band edge.
    if _level(raw) < _level(prev_status):
        for bound, name in STATUS_BANDS:
            if name == prev_status and score >= bound - _HYSTERESIS:
                return prev_status
    # Cooling: meaningfully below recent peak and decelerating.
    if (
        peak_score_7d is not None
        and peak_score_7d >= 50.0
        and score < 0.7 * peak_score_7d
        and (acceleration is None or acceleration < 0)
        and _level(raw) >= _level("rising")
    ):
        return "cooling"
    if prev_status == "cooling" and score >= 50.0:
        return raw
    if prev_status == "cooling":
        return "cooling"
    return raw


# --------------------------------------------------------------------------- #
# Organic score & hype risk
# --------------------------------------------------------------------------- #
def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def _organic_score(m: Metrics) -> tuple[float | None, tuple[str, ...]]:
    """Activity-backed growth 0..100. Never asserts manipulation."""
    if m.velocity_24h is None:
        return None, ("insufficient history",)
    reasons: list[str] = []

    fork_sig = 0.0
    if m.fork_velocity_24h is not None:
        fork_sig = min(1.0, max(m.fork_velocity_24h, 0.0) / 10.0)
        if m.fork_velocity_24h >= 5:
            reasons.append(f"forks growing at {m.fork_velocity_24h:.1f}/h")
    act_sig = (m.activity_score or 0.0) / 100.0
    if (m.activity_score or 0) >= 50:
        reasons.append(f"repository activity score {m.activity_score:.0f}/100")

    spike = (
        (m.relative_growth or 0) > 2.0
        and (m.fork_velocity_24h or 0) < 1.0
        and (m.activity_score or 0) < 30
    )
    if spike:
        reasons.append("star spike with little accompanying activity")

    z = 0.6 * fork_sig + 0.5 * act_sig - 1.5 * (1.0 if spike else 0.0)
    return round(100.0 * _sigmoid(z), 1), tuple(reasons)


def _hype_risk(m: Metrics) -> tuple[str, tuple[str, ...]]:
    """low|medium|high with verbatim reasons."""
    reasons: list[str] = []
    gain = m.stars_24h_gain or 0
    fv = m.fork_velocity_24h or 0.0
    act = m.activity_score or 0.0

    if gain >= 2000 and fv < 5 and act < 30:
        reasons.append(f"+{gain:,} stars / 24h")
        reasons.append("forks nearly unchanged")
        reasons.append("low repository activity")
        return "high", tuple(reasons)
    if gain >= 500 and (fv < 2 or act < 40):
        if gain:
            reasons.append(f"+{gain:,} stars / 24h outpacing forks/activity")
        return "medium", tuple(reasons)
    return "low", ("growth accompanied by proportional activity",)


def hype_risk_details(m: Metrics) -> tuple[str, tuple[str, ...]]:
    """Public wrapper for the hype-risk classifier with reasons."""
    return _hype_risk(m)

# --------------------------------------------------------------------------- #
# Small presentation helpers
# --------------------------------------------------------------------------- #
def acceleration_hint(acceleration: float | None) -> str:
    if acceleration is None:
        return "unknown"
    if acceleration > 0.5:
        return "accelerating"
    if acceleration < -0.5:
        return "decelerating"
    return "steady"


def acceleration_pct(m: Metrics) -> float | None:
    """Acceleration expressed as % change of 24h velocity vs the prior 24h.

    This is the API/UI-facing unit (e.g. "+182%"). The scoring engine
    normalizes the raw stars/h delta internally; this helper is only
    for presentation. ``None`` when the underlying values are missing.
    """
    if m.acceleration is None or m.velocity_24h is None:
        return None
    v_prev = m.velocity_24h - m.acceleration
    denom = max(abs(v_prev), 1.0)  # floor avoids division explosions
    return round(m.acceleration / denom * 100.0, 1)


# --------------------------------------------------------------------------- #
# Category classification (rule-based; LLM-swappable interface)
# --------------------------------------------------------------------------- #
CATEGORIES = [
    "AI", "LLM", "Agents", "DevTools", "Security", "Database",
    "Infrastructure", "Web", "Mobile", "Data", "Research",
    "Hardware", "Games", "Other",
]

_CATEGORY_KEYWORDS: dict[str, tuple[str, ...]] = {
    "Agents": ("agent", "multi-agent", "autonomous", "crewai", "langgraph", "autogen", "smolagents"),
    "LLM": ("llm", "large language model", "gpt", "transformer", "tokenizer", "inference engine",
            "llama", "mistral", "qwen", "vllm", "ollama"),
    "AI": ("machine learning", "deep learning", "neural", "pytorch", "tensorflow", "diffusion",
           "computer vision", "stable diffusion", "ai ", "artificial intelligence"),
    "Security": ("security", "vulnerability", "exploit", "pentest", "cve", "malware", "ctf",
                 "cryptograph", "zero-trust", "siem"),
    "Database": ("database", "postgres", "mysql", "sqlite", "redis", "vector db", "timescale",
                 "clickhouse", "orm", "sql "),
    "Infrastructure": ("kubernetes", "docker", "terraform", "devops", "ci/cd", "infrastructure",
                       "helm", "ansible", "observability", "prometheus", "self-hosted"),
    "DevTools": ("cli", "linter", "formatter", "compiler", "debugger", "sdk", "framework",
                 "boilerplate", "developer tool", "ide ", "vscode"),
    "Web": ("react", "next.js", "vue", "svelte", "frontend", "web app", "website", "css",
            "typescript", "full-stack"),
    "Mobile": ("android", "ios", "flutter", "react native", "swift", "kotlin", "mobile"),
    "Data": ("data pipeline", "etl", "dataframe", "pandas", "spark", "dashboard", "analytics",
             "visualization", "dataset"),
    "Research": ("paper", "arxiv", "benchmark", "research", "survey", "reproduc"),
    "Hardware": ("raspberry", "arduino", "embedded", "firmware", "fpga", "iot", "microcontroller"),
    "Games": ("game", "unity", "unreal", "godot", "roguelike", "game engine"),
}


def classify_category(
    description: str | None,
    topics: list[str] | None,
    language: str | None,
    readme_excerpt: str | None = None,
) -> list[str]:
    """Deterministic rule-based classifier. Returns 1-3 categories.

    Interface is intentionally narrow so an LLM classifier can replace it.
    """
    text = " ".join(
        part for part in [
            description or "",
            " ".join(topics or []),
            readme_excerpt or "",
        ] if part
    ).lower()
    if language:
        text += f" language:{language.lower()}"
    hits: list[tuple[str, int]] = []
    for cat, keywords in _CATEGORY_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw in text)
        if count:
            hits.append((cat, count))
    hits.sort(key=lambda h: (-h[1], h[0]))
    cats = [c for c, _ in hits[:3]]
    if not cats:
        return ["Other"]
    return cats


# --------------------------------------------------------------------------- #
# Deterministic "Why is this rising?" summary
# --------------------------------------------------------------------------- #
def explain_score(m: Metrics, repo_full_name: str) -> str:
    """Every sentence is grounded in measured metrics. No LLM, no invention."""
    if m.velocity_24h is None or m.stars_24h_gain is None:
        return (
            f"{repo_full_name} does not have enough snapshot history yet "
            "to explain its growth."
        )
    parts = [
        f"{repo_full_name} gained {m.stars_24h_gain:,} stars in the past 24 hours "
        f"({m.velocity_24h:.1f}/h)."
    ]
    if m.acceleration is not None:
        if m.acceleration > 0.5:
            parts.append(
                f"Growth is accelerating (+{m.acceleration:.1f} stars/h vs the prior 24h)."
            )
        elif m.acceleration < -0.5:
            parts.append(
                f"Growth is decelerating ({m.acceleration:.1f} stars/h vs the prior 24h)."
            )
        else:
            parts.append("Growth rate is roughly steady versus the prior 24h.")
    if m.relative_growth is not None:
        parts.append(
            f"That is a {m.relative_growth * 100:.0f}% relative gain on its prior base."
        )
    if m.fork_velocity_24h is not None and m.fork_velocity_24h >= 1:
        parts.append(f"Forks are growing at {m.fork_velocity_24h:.1f}/h.")
    if m.activity_score is not None:
        if m.activity_score >= 50:
            parts.append(
                f"Repository activity is healthy ({m.activity_score:.0f}/100), "
                "so the growth is backed by real development."
            )
        else:
            parts.append(
                f"Repository activity is low ({m.activity_score:.0f}/100); "
                "the star growth is not yet matched by development activity."
            )
    return " ".join(parts)
