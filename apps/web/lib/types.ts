/**
 * Shared frontend types — mirrors CONTRACT.md §4 exactly.
 * All timestamps are UTC ISO8601 strings.
 */

export type RepoStatus =
  | "normal"
  | "emerging"
  | "rising"
  | "breakout"
  | "viral"
  | "cooling";

export type HypeRisk = "low" | "medium" | "high";

export type SortKey =
  | "breakout_score"
  | "growth_24h"
  | "acceleration"
  | "relative_growth"
  | "newest";

export type TimeRange = "24h" | "7d";

/** Per-component contribution to the breakout score (sums to breakout_score). */
export interface ScoreBreakdown {
  star_velocity: number;
  acceleration: number;
  relative_growth: number;
  fork_growth: number;
  activity: number;
  age_bonus: number;
}

/** RepoCard — the leaderboard row payload from GET /api/repos. */
export interface RepoCard {
  id: string;
  owner: string;
  name: string;
  full_name: string;
  description: string | null;
  url: string;
  language: string | null;
  license: string | null;
  category: string[];
  stars: number;
  forks: number;
  age_days: number;
  stars_24h_gain: number | null;
  velocity_24h: number | null; // stars/hour
  acceleration: number | null; // % change of 24h velocity vs previous 24h
  relative_growth: number | null; // 24h gain / max(prior stars, 50)
  breakout_score: number | null; // 0-100
  organic_score: number | null; // 0-100
  hype_risk: HypeRisk | null;
  status: RepoStatus;
  detected_at: string;
  score_breakdown: ScoreBreakdown | null;
  insufficient_history: boolean;
}

export interface RepoListResponse {
  items: RepoCard[];
  next_cursor: string | null;
}

export interface DetectionInfo {
  first_detected_at: string;
  stars_at_detection: number;
  first_emerging_at: string | null;
  first_rising_at: string | null;
  first_breakout_at: string | null;
  first_viral_at: string | null;
  peak_score: number | null;
  peak_at: string | null;
  growth_since_detection: number;
}

export interface RepoEvent {
  ts: string;
  type: "detected" | "emerging" | "rising" | "breakout" | "viral" | "release";
  label: string;
}

export interface SnapshotPoint {
  ts: string;
  stars: number;
  forks: number;
  watchers: number;
  open_issues: number;
  open_prs: number;
  contributors_count: number | null;
}

export interface ScorePoint {
  ts: string;
  breakout_score: number;
  velocity_24h: number | null;
  acceleration: number | null;
}

export interface HistoryResponse {
  snapshots: SnapshotPoint[];
  scores: ScorePoint[];
  detections: DetectionInfo | null;
  events: RepoEvent[];
  insufficient_history: boolean;
}

/** RepoDetail — GET /api/repos/{owner}/{name}. */
export interface RepoDetail extends RepoCard {
  topics: string[];
  watchers: number;
  open_issues: number;
  created_at: string;
  pushed_at: string | null;
  confidence: number | null; // 0-1, low when history is thin
  scoring_version: string;
  why_rising: string | null;
  hype_risk_reasons: string[];
  detections: DetectionInfo | null;
}

export interface CategoryCount {
  name: string;
  count: number;
}

export interface RadarStats {
  tracked_repos: number;
  snapshots_24h: number;
  detections_7d: number;
  api_calls_24h: number;
}

export interface AddRepoResponse {
  job_id: string;
  status: string;
}

export interface RepoListParams {
  status?: string;
  category?: string;
  language?: string;
  min_stars?: number;
  max_age_days?: number;
  sort?: SortKey;
  range?: TimeRange;
  limit?: number;
  cursor?: string;
}
