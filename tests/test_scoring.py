"""Unit tests for the deterministic scoring engine.

Synthetic time-series fixtures (no network, no DB):
  steady          low constant growth, old-ish repo
  sudden_breakout flat then sharp 24h breakout
  viral_spike     star-only explosion, no dev activity
  tiny_new_repo   3-day-old repo, 5 -> 60 stars
  old_large_repo  80k stars, slow steady growth

NOTE: these tests have not been executed in this environment
(muse.exec is unavailable). They are written to be run with:
    pytest tests/test_scoring.py -q
"""

from datetime import datetime, timedelta, timezone

from radar_scoring import (
    CorpusStats,
    Snapshot,
    acceleration_pct,
    age_bonus,
    classify_category,
    classify_status,
    compute_breakout,
    compute_corpus_stats,
    compute_metrics,
    corpus_transform,
    explain_score,
    hype_risk_details,
)

T0 = datetime(2026, 10, 1, 0, 0, tzinfo=timezone.utc)


def make_snaps(star_fn, fork_fn, hours=72, **kw):
    """Build hourly snapshots, oldest first."""
    snaps = []
    for h in range(hours + 1):
        ts = T0 + timedelta(hours=h)
        snaps.append(
            Snapshot(
                ts=ts,
                stars=int(star_fn(h)),
                forks=int(fork_fn(h)),
                watchers=int(star_fn(h) // 20),
                open_issues=kw.get("open_issues", 3),
                open_prs=kw.get("open_prs", 1),
                contributors_count=kw.get("contributors_count", 4),
                commit_count_7d=kw.get("commit_count_7d", 30),
                has_release_14d=kw.get("has_release_14d", False),
                pushed_at=kw.get("pushed_at", T0 + timedelta(hours=hours - 2)),
            )
        )
    return snaps


def corpus():
    # Fixed corpus on the transformed scale -> deterministic tests.
    import math

    return CorpusStats(
        {
            "star_velocity_24h": (math.log1p(20), 0.6),
            "acceleration": (0.0, 0.5),
            "relative_growth": (math.log1p(0.05), 0.1),
            "fork_velocity_24h": (math.log1p(0.5), 0.3),
        }
    )


def steady():
    return make_snaps(lambda h: 1000 + 2 * h, lambda h: 100 + 0.2 * h)


def sudden_breakout():
    def stars(h):
        return 500 if h <= 48 else 500 + 40 * (h - 48)

    def forks(h):
        return 50 if h <= 48 else 50 + 4 * (h - 48)

    return make_snaps(
        stars, forks, contributors_count=6, commit_count_7d=60, has_release_14d=True
    )


def viral_spike():
    def stars(h):
        return 200 if h <= 48 else 200 + 300 * (h - 48)

    return make_snaps(
        stars,
        lambda h: 20,
        contributors_count=None,
        commit_count_7d=None,
        has_release_14d=False,
    )


def tiny_new_repo():
    return make_snaps(
        lambda h: 5 + 0.76 * h,
        lambda h: 1 + 0.05 * h,
        contributors_count=1,
        commit_count_7d=8,
    )


def old_large_repo():
    return make_snaps(lambda h: 80000 + 10 * h, lambda h: 9000 + 1 * h)


NOW = T0 + timedelta(hours=72)


# ---------------------------------------------------------------- #
def test_velocity_exact():
    m = compute_metrics(steady(), age_days=60, now=NOW)
    assert m.velocity_24h == 2.0
    assert m.velocity_1h == 2.0
    assert m.acceleration == 0.0
    assert m.stars_24h_gain == 48


def test_velocity_missing_window_is_none_not_fabricated():
    snaps = make_snaps(lambda h: 10 + h, lambda h: 1, hours=1)
    m = compute_metrics(snaps, age_days=5, now=T0 + timedelta(hours=1))
    assert m.velocity_24h is None
    assert m.acceleration is None
    assert m.relative_growth is None
    assert m.confidence <= 0.3


def test_relative_growth_smoothing():
    m = compute_metrics(tiny_new_repo(), age_days=3, now=NOW)
    # gain ~18.2 over a base of 5 -> smoothed by max(5, 50)
    assert m.relative_growth is not None
    assert abs(m.relative_growth - (m.stars_24h_gain / 50.0)) < 1e-9


def test_age_bonus_bands():
    assert age_bonus(3) == 100.0
    assert age_bonus(100) == 0.0
    assert 95 < age_bonus(10) < 97
    assert 62 < age_bonus(45) < 63
    assert age_bonus(7) == 100.0


def test_age_bonus_gated_by_velocity():
    # Tiny new repo: high raw age bonus, but velocity too low to matter much.
    m = compute_metrics(tiny_new_repo(), age_days=3, now=NOW)
    assert m.age_bonus_raw == 100.0
    r = compute_breakout(m, corpus())
    assert r.breakdown["age_bonus"] < 20.0


def test_breakout_ranking_order():
    c = corpus()
    s_steady = compute_breakout(compute_metrics(steady(), 60, NOW), c)
    s_break = compute_breakout(compute_metrics(sudden_breakout(), 10, NOW), c)
    s_viral = compute_breakout(compute_metrics(viral_spike(), 5, NOW), c)
    s_tiny = compute_breakout(compute_metrics(tiny_new_repo(), 3, NOW), c)
    assert s_break.breakout_score > 70
    assert s_break.breakout_score > s_steady.breakout_score
    assert s_viral.breakout_score > s_steady.breakout_score
    assert s_tiny.breakout_score < s_break.breakout_score
    assert s_steady.status == "normal"


def test_determinism():
    c = corpus()
    snaps = sudden_breakout()
    r1 = compute_breakout(compute_metrics(snaps, 10, NOW), c)
    r2 = compute_breakout(compute_metrics(snaps, 10, NOW), c)
    assert r1 == r2
    assert 0 <= r1.breakout_score <= 100


def test_organic_and_hype_risk():
    c = corpus()
    r_viral = compute_breakout(compute_metrics(viral_spike(), 5, NOW), c)
    r_steady = compute_breakout(compute_metrics(steady(), 60, NOW), c)
    r_break = compute_breakout(compute_metrics(sudden_breakout(), 10, NOW), c)
    assert r_viral.organic_score is not None and r_viral.organic_score < 40
    assert r_steady.organic_score is not None
    assert r_steady.organic_score > r_viral.organic_score
    assert r_viral.hype_risk == "high"
    assert len(r_viral.hype_reasons) >= 2
    assert r_steady.hype_risk == "low"
    assert r_break.hype_risk == "low"


def test_status_hysteresis_and_cooling():
    # Hysteresis: 65 keeps 'breakout' (within 8 of the 70 edge).
    assert classify_status(72, "breakout") == "breakout"
    assert classify_status(65, "breakout") == "breakout"
    assert classify_status(60, "breakout") == "rising"
    # Cooling: still >= rising but far below peak and decelerating.
    assert (
        classify_status(58, "breakout", peak_score_7d=92, acceleration=-3.0)
        == "cooling"
    )
    # Recovery out of cooling.
    assert classify_status(55, "cooling") == "rising"
    assert classify_status(40, "cooling") == "cooling"


def test_old_large_repo_low_relative_growth():
    m = compute_metrics(old_large_repo(), age_days=900, now=NOW)
    assert m.relative_growth is not None and m.relative_growth < 0.01
    assert m.age_bonus_raw == 0.0


def test_category_classifier():
    assert "LLM" in classify_category(
        "A fast LLM inference engine", ["llm", "inference"], "Python"
    )
    assert "Security" in classify_category(
        "Vulnerability scanner for containers", ["security"], "Go"
    )
    assert classify_category(None, None, None) == ["Other"]
    assert "Games" in classify_category("A roguelike game engine", ["game"], "Rust")


def test_explain_score_grounded():
    m = compute_metrics(viral_spike(), age_days=5, now=NOW)
    text = explain_score(m, "foo/bar")
    assert "7,200" in text  # exact measured 24h gain
    assert "foo/bar" in text
    m2 = compute_metrics(steady(), age_days=60, now=NOW)
    assert "48 stars" in explain_score(m2, "x/y")


def test_acceleration_pct():
    m = compute_metrics(sudden_breakout(), age_days=10, now=NOW)
    pct = acceleration_pct(m)
    assert pct is not None
    # v24 = 40/h, v_prev = 0 -> floor(|v_prev|, 1) -> 40/1*100 = 4000%
    assert pct == 4000.0
    m2 = compute_metrics(steady(), age_days=60, now=NOW)
    assert acceleration_pct(m2) == 0.0
    assert acceleration_pct(compute_metrics([], age_days=1)) is None


def test_corpus_transform_matches_robust_norm_scale():
    import math

    assert corpus_transform(20.0) == math.log1p(20.0)
    assert corpus_transform(-40.0, signed=True) == -math.log1p(40.0)
    assert corpus_transform(0.0) == 0.0
    # compute_corpus_stats produces stats on the transformed scale
    ms = [compute_metrics(steady(), 60, NOW), compute_metrics(sudden_breakout(), 10, NOW)]
    stats = compute_corpus_stats(ms)
    assert stats.get("star_velocity_24h") == (0.0, 1.0)  # < 5 samples -> fallback


def test_hype_risk_details_reasons():
    m = compute_metrics(viral_spike(), age_days=5, now=NOW)
    risk, reasons = hype_risk_details(m)
    assert risk == "high"
    assert any("7,200" in r for r in reasons)
    m2 = compute_metrics(steady(), age_days=60, now=NOW)
    assert hype_risk_details(m2)[0] == "low"
