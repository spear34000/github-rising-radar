# SCORING.md — GitHub Rising Radar scoring specification

All formulas are implemented in `packages/scoring` and must be
**deterministic**: identical snapshots → identical scores.
Every stored score carries `scoring_version` (current: `v1`).

Timestamps are UTC. Velocities are stars per hour.

## 1. Star velocity

For a window `W` (1h, 6h, 24h, 7d):

```
v_W = (stars(now) - stars(t_ref)) / hours(now - t_ref)
```

`t_ref` = the latest snapshot at or before `now - W`.
Tolerance: the snapshot must be within `W + max(0.25*W, 15min)` of the ideal
time, otherwise that window's velocity is `null` (never fabricated).

## 2. Acceleration

```
accel = v_24h_recent - v_24h_previous
```

where `v_24h_recent` covers [now-24h, now] and `v_24h_previous` covers
[now-48h, now-24h]. If either window is missing → `null`, and `confidence`
is reduced.

**API-facing unit:** the REST API exposes acceleration as a *percent*
(`acceleration_pct = accel / max(|v_prev|, 1) * 100`, e.g. `+182%`).
The scoring engine normalizes the raw stars/h delta internally; the
percent form is presentation-only, computed by
`radar_scoring.acceleration_pct()`.

Alternative accepted: slope of least-squares linear regression over the
velocity time series when ≥ 4 velocity points exist. `v1` uses the
difference method (stable with sparse snapshots).

## 3. Relative growth

```
rel_growth = stars_gain_24h / max(stars_24h_ago, SMOOTHING_STARS)
SMOOTHING_STARS = 50
```

Prevents tiny repos (e.g. 2 → 20 stars) from dominating.

## 4. Fork signals

```
fork_velocity_24h = (forks(now) - forks(t_ref_24h)) / hours
fork_star_ratio   = fork_velocity_24h / max(star_velocity_24h, epsilon)
```

Fork weight is deliberately lower than star weight.

## 5. Activity score (0–100)

Weighted combination of z-scored signals (each 0–100 clipped):

- commit activity (commits in last 7d): 35%
- pushed_at recency (hours since push, decayed): 20%
- PR + issue events (open_prs + open_issues delta): 20%
- contributors growth: 15%
- release in last 14d: 10%

Separates real projects from README-only viral lists.

## 6. Age bonus (0–100)

```
age < 7d   → 100
7–30d      → 70
30–90d     → 40
> 90d      → 0
```

Linear interpolation between band edges. The bonus **cannot** push an
inactive repo to the top: it only adds up to 10% of the final score and
requires non-zero velocity to have any effect (implemented as
`age_bonus * min(1, velocity_24h / 5)` gate).

## 7. Robust normalization

Each raw metric `x` is normalized against the corpus of tracked repos:

1. `log1p` transform for heavy-tailed metrics (velocity, growth).
2. Robust z-score: `z = (x_t - median) / (1.4826 * MAD)`, clipped to [-4, 4].
3. Percentile mapped to 0–100: `100 * Φ(z)` (Φ = standard normal CDF).

Corpus stats (`median`, `MAD` per metric) are recomputed by the worker
every 15 minutes from all tracked repos and stored in `corpus_stats`.
One outlier can never destroy the scale.

## 8. Breakout score (0–100)

```
breakout = 0.30 * norm(star_velocity_24h)
         + 0.25 * norm(acceleration)
         + 0.15 * norm(relative_growth)
         + 0.10 * norm(fork_velocity_24h)
         + 0.10 * activity_score/100*100
         + 0.10 * gated_age_bonus
```

`score_breakdown` stores each term's point contribution so the UI can
render the decomposition bar.

## 9. Status state machine

```
0–29  → normal
30–49 → emerging
50–69 → rising
70–84 → breakout
85–100 → viral
```

Hysteresis: a repo leaves a status only when the score drops 8 points
below the lower bound (prevents flapping).

**Cooling**: if `score < 0.7 * peak_score_7d` AND `acceleration < 0`
for two consecutive scoring runs → `cooling`, until score recovers
above the rising threshold.

First-entry timestamps are written to `detections` and never deleted,
even if the scoring formula changes later.

## 10. Organic score (0–100) — activity-backed growth

Not a "bot detector". Measures how much of the star growth is
accompanied by real repository activity:

positive signals: fork growth, contributor growth, issue/PR activity,
commits, releases.
suspicious pattern: star spike with near-zero other activity.

```
organic = 100 * sigmoid(0.6*z_fork + 0.8*z_contrib + 0.5*z_activity
                       - 1.2*star_only_spike_indicator)
```

Always shown with the explanation: "Low organic score means growth is
not accompanied by development activity — it does not prove manipulation."

## 11. Hype risk (low | medium | high)

Rule-based, with reasons stored:

- high: stars_48h_gain > 2000 AND fork_velocity_24h < 5 AND no release in 30d
  AND contributors_count <= 2
- medium: star spike with activity below median
- low: otherwise

The UI lists the triggering reasons verbatim.

## 12. Confidence (0–1)

- < 3 snapshots → 0.3
- < 24h of history → 0.6
- otherwise → 1.0 (minus 0.1 per missing velocity window)

UI shows "Insufficient history" when confidence < 0.5 and hides
velocity/acceleration numbers instead of inventing them.
