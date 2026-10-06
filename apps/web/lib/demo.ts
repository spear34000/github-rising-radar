/**
 * Built-in DEMO dataset — used only when NEXT_PUBLIC_DEMO=true.
 *
 * This is synthetic, deterministically generated mock data. It is NEVER
 * presented as real data: the UI renders a persistent "DEMO DATA" banner
 * whenever this module serves traffic.
 */
import type {
  AddRepoResponse,
  CategoryCount,
  DetectionInfo,
  HistoryResponse,
  RadarStats,
  RepoCard,
  RepoDetail,
  RepoEvent,
  RepoListParams,
  RepoListResponse,
  RepoStatus,
  ScoreBreakdown,
  ScorePoint,
  SnapshotPoint,
} from "./types";

export function isDemoMode(): boolean {
  return process.env.NEXT_PUBLIC_DEMO === "true";
}

/* ------------------------------------------------------------------ */
/* Deterministic PRNG so demo data is stable across reloads.            */
/* ------------------------------------------------------------------ */

function mulberry32(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

type Profile =
  | "breakout"
  | "viral"
  | "rising"
  | "emerging"
  | "cooling"
  | "steady"
  | "old"
  | "tiny"
  | "fake";

interface RepoSpec {
  owner: string;
  name: string;
  description: string;
  language: string;
  license: string;
  category: string[];
  topics: string[];
  ageDays: number;
  baseStars: number;
  profile: Profile;
  breakout: number; // breakout_score
  organic: number | null;
  hype: "low" | "medium" | "high";
  breakdown: ScoreBreakdown;
  status: RepoStatus;
  hasRelease: boolean;
}

const DAY = 86_400_000;
const DAYS = 35;
const now = Date.now();

const SPECS: RepoSpec[] = [
  {
    owner: "neuralforge", name: "tinygrad-turbo",
    description: "A from-scratch deep learning compiler with a 4k-line codebase and sub-second kernel fusion.",
    language: "Python", license: "MIT", category: ["AI", "Infrastructure"],
    topics: ["deep-learning", "compiler", "gpu"], ageDays: 11, baseStars: 120,
    profile: "breakout", breakout: 92, organic: 88, hype: "low",
    breakdown: { star_velocity: 27, acceleration: 23, relative_growth: 14, fork_growth: 8, activity: 12, age_bonus: 8 },
    status: "breakout", hasRelease: true,
  },
  {
    owner: "quantumlabs", name: "agent-swarm",
    description: "Coordinate fleets of coding agents with shared memory, task graphs and human-in-the-loop gates.",
    language: "TypeScript", license: "Apache-2.0", category: ["Agents", "AI"],
    topics: ["agents", "orchestration", "llm"], ageDays: 23, baseStars: 400,
    profile: "viral", breakout: 97, organic: 71, hype: "medium",
    breakdown: { star_velocity: 30, acceleration: 25, relative_growth: 15, fork_growth: 7, activity: 12, age_bonus: 8 },
    status: "viral", hasRelease: true,
  },
  {
    owner: "bytecraft", name: "llm-gateway",
    description: "One OpenAI-compatible endpoint in front of every provider, with failover, caching and cost routing.",
    language: "Go", license: "Apache-2.0", category: ["LLM", "Infrastructure"],
    topics: ["llm", "proxy", "gateway"], ageDays: 34, baseStars: 900,
    profile: "rising", breakout: 64, organic: 82, hype: "low",
    breakdown: { star_velocity: 18, acceleration: 12, relative_growth: 8, fork_growth: 7, activity: 13, age_bonus: 6 },
    status: "rising", hasRelease: false,
  },
  {
    owner: "secops", name: "honeyscan",
    description: "Deploy deceptive services in one command and get alerted the moment scanners touch them.",
    language: "Rust", license: "MIT", category: ["Security", "DevTools"],
    topics: ["honeypot", "security", "detection"], ageDays: 6, baseStars: 45,
    profile: "emerging", breakout: 41, organic: 76, hype: "low",
    breakdown: { star_velocity: 10, acceleration: 8, relative_growth: 6, fork_growth: 4, activity: 5, age_bonus: 8 },
    status: "emerging", hasRelease: false,
  },
  {
    owner: "datadive", name: "vectorlite",
    description: "SQLite extension for vector search: 200k QPS on a laptop, zero dependencies.",
    language: "Python", license: "Apache-2.0", category: ["Database", "Data"],
    topics: ["vector-search", "sqlite", "embeddings"], ageDays: 45, baseStars: 1500,
    profile: "breakout", breakout: 85, organic: 90, hype: "low",
    breakdown: { star_velocity: 25, acceleration: 20, relative_growth: 10, fork_growth: 9, activity: 15, age_bonus: 6 },
    status: "breakout", hasRelease: true,
  },
  {
    owner: "webworks", name: "htmx-plus",
    description: "Progressive enhancement utilities on top of htmx: morphing, islands and optimistic UI.",
    language: "JavaScript", license: "MIT", category: ["Web"],
    topics: ["htmx", "frontend", "hypermedia"], ageDays: 120, baseStars: 28000,
    profile: "cooling", breakout: 38, organic: 84, hype: "low",
    breakdown: { star_velocity: 12, acceleration: 2, relative_growth: 3, fork_growth: 6, activity: 14, age_bonus: 1 },
    status: "cooling", hasRelease: false,
  },
  {
    owner: "mobkit", name: "flutter-nova",
    description: "Material 3 component kit for Flutter with 120+ widgets and motion presets.",
    language: "Dart", license: "BSD-3-Clause", category: ["Mobile"],
    topics: ["flutter", "ui-kit", "material"], ageDays: 400, baseStars: 45000,
    profile: "old", breakout: 18, organic: 70, hype: "low",
    breakdown: { star_velocity: 6, acceleration: 1, relative_growth: 1, fork_growth: 4, activity: 6, age_bonus: 0 },
    status: "normal", hasRelease: true,
  },
  {
    owner: "gamedev", name: "rogue-engine",
    description: "Data-oriented 2D roguelike engine in C++20 with deterministic netcode and replay support.",
    language: "C++", license: "MIT", category: ["Games"],
    topics: ["game-engine", "roguelike", "cpp"], ageDays: 60, baseStars: 2100,
    profile: "rising", breakout: 58, organic: 79, hype: "low",
    breakdown: { star_velocity: 16, acceleration: 11, relative_growth: 8, fork_growth: 6, activity: 12, age_bonus: 5 },
    status: "rising", hasRelease: true,
  },
  {
    owner: "infraops", name: "k8s-cost",
    description: "Show per-namespace Kubernetes spend in your terminal, with right-sizing suggestions.",
    language: "Go", license: "Apache-2.0", category: ["Infrastructure", "DevTools"],
    topics: ["kubernetes", "finops", "cli"], ageDays: 9, baseStars: 180,
    profile: "emerging", breakout: 44, organic: 81, hype: "low",
    breakdown: { star_velocity: 11, acceleration: 9, relative_growth: 7, fork_growth: 5, activity: 4, age_bonus: 8 },
    status: "emerging", hasRelease: false,
  },
  {
    owner: "researcher", name: "paper-qa",
    description: "Ask questions over a folder of PDFs with citations; runs fully offline with local models.",
    language: "Python", license: "MIT", category: ["Research", "AI"],
    topics: ["rag", "papers", "local-llm"], ageDays: 3, baseStars: 12,
    profile: "tiny", breakout: 22, organic: null, hype: "low",
    breakdown: { star_velocity: 5, acceleration: 3, relative_growth: 4, fork_growth: 1, activity: 2, age_bonus: 7 },
    status: "normal", hasRelease: false,
  },
  {
    owner: "devtools", name: "git-bisect-ui",
    description: "A visual interface for git bisect with one-click good/bad marking.",
    language: "TypeScript", license: "MIT", category: ["DevTools"],
    topics: ["git", "debugging", "tui"], ageDays: 15, baseStars: 90,
    profile: "fake", breakout: 76, organic: 24, hype: "high",
    breakdown: { star_velocity: 28, acceleration: 24, relative_growth: 15, fork_growth: 1, activity: 2, age_bonus: 6 },
    status: "breakout", hasRelease: false,
  },
  {
    owner: "hardlab", name: "riscv-sim",
    description: "Cycle-accurate RISC-V simulator with a web-based pipeline visualizer.",
    language: "C", license: "GPL-3.0", category: ["Hardware"],
    topics: ["riscv", "simulator", "cpu"], ageDays: 200, baseStars: 6800,
    profile: "steady", breakout: 26, organic: 74, hype: "low",
    breakdown: { star_velocity: 7, acceleration: 3, relative_growth: 2, fork_growth: 5, activity: 9, age_bonus: 0 },
    status: "normal", hasRelease: false,
  },
];

/** Daily star gains for each profile (35 days, oldest -> newest). */
function dailyGains(profile: Profile, rng: () => number): number[] {
  const g: number[] = [];
  for (let i = 0; i < DAYS; i++) {
    const tail = DAYS - 1 - i; // days ago
    let v = 0;
    switch (profile) {
      case "breakout":
        v = tail > 6 ? 2 + rng() * 3 : [45, 95, 170, 280, 420, 560, 681][6 - tail] * (0.9 + rng() * 0.2);
        break;
      case "viral":
        v = tail > 3 ? 4 + rng() * 5 : [950, 2400, 4100, 5300][3 - tail] * (0.9 + rng() * 0.2);
        break;
      case "rising":
        v = 8 + i * 1.1 + rng() * 8;
        break;
      case "emerging":
        v = tail > 4 ? 1 + rng() * 2 : Math.min(180, 4 * Math.pow(1.9, 4 - tail)) * (0.85 + rng() * 0.3);
        break;
      case "cooling":
        v = tail >= 9 && tail <= 12
          ? [320, 720, 1150, 860][12 - tail] * (0.9 + rng() * 0.2)
          : 10 + rng() * 12;
        break;
      case "steady":
        v = 6 + rng() * 7;
        break;
      case "old":
        v = 22 + rng() * 18;
        break;
      case "tiny":
        v = rng() < 0.6 ? 0 : 1 + Math.floor(rng() * 3);
        break;
      case "fake":
        v = tail > 2 ? rng() * 2 : [1400, 3100, 2900][2 - tail] * (0.9 + rng() * 0.2);
        break;
    }
    g.push(Math.max(0, Math.round(v)));
  }
  return g;
}

const FORK_RATIO: Record<Profile, number> = {
  breakout: 0.16, viral: 0.1, rising: 0.14, emerging: 0.12,
  cooling: 0.13, steady: 0.11, old: 0.12, tiny: 0.08, fake: 0.015,
};

interface BuiltRepo {
  card: RepoCard;
  detail: RepoDetail;
  snapshots: SnapshotPoint[];
  scores: ScorePoint[];
  events: RepoEvent[];
  detections: DetectionInfo;
}

function buildRepo(spec: RepoSpec, idx: number): BuiltRepo {
  const rng = mulberry32(1000 + idx * 77);
  const gains = dailyGains(spec.profile, rng);
  const forkRatio = FORK_RATIO[spec.profile];

  const snapshots: SnapshotPoint[] = [];
  let stars = spec.baseStars;
  let forks = Math.round(spec.baseStars * forkRatio);
  const createdAt = new Date(now - spec.ageDays * DAY).toISOString();
  const detectedAt = new Date(now - Math.min(spec.ageDays, 30) * DAY + 36e5).toISOString();

  for (let i = 0; i < DAYS; i++) {
    stars += gains[i];
    forks += Math.round(gains[i] * forkRatio * (0.7 + rng() * 0.6));
    const ts = new Date(now - (DAYS - 1 - i) * DAY);
    snapshots.push({
      ts: ts.toISOString(),
      stars,
      forks,
      watchers: Math.round(stars * 0.06),
      open_issues: Math.round(4 + rng() * 30 * (spec.profile === "old" ? 3 : 1)),
      open_prs: Math.round(rng() * 12),
      contributors_count:
        spec.profile === "tiny" ? 1 : Math.round(2 + rng() * (spec.profile === "fake" ? 1 : 25)),
    });
  }

  const last = snapshots[DAYS - 1];
  const dayBefore = snapshots[DAYS - 2];
  const twoDaysBefore = snapshots[DAYS - 3];
  const gain24 = last.stars - dayBefore.stars;
  const prevGain24 = dayBefore.stars - twoDaysBefore.stars;
  const velocity24 = gain24 / 24;
  // Same convention as radar_scoring.acceleration_pct: % change of 24h
  // velocity vs the previous 24h, floored denominator to avoid explosions.
  const prevVelocity24 = prevGain24 / 24;
  const acceleration =
    ((velocity24 - prevVelocity24) / Math.max(Math.abs(prevVelocity24), 1)) * 100;

  // Synthetic score series: ramps up following the star curve.
  const scores: ScorePoint[] = snapshots.map((s, i) => {
    const frac = s.stars / last.stars;
    const ramp = Math.min(1, 0.25 + 0.75 * Math.pow(frac, 0.6));
    const g24 = i === 0 ? 0 : s.stars - snapshots[i - 1].stars;
    const gp = i <= 1 ? Math.max(g24, 1) : snapshots[i - 1].stars - snapshots[i - 2].stars;
    const v24 = g24 / 24;
    const vp = gp / 24;
    const apct = ((v24 - vp) / Math.max(Math.abs(vp), 1)) * 100;
    return {
      ts: s.ts,
      breakout_score: Math.round(spec.breakout * ramp * 10) / 10,
      velocity_24h: Math.round(v24 * 10) / 10,
      acceleration: Math.round(apct * 10) / 10,
    };
  });

  const detections: DetectionInfo = {
    first_detected_at: detectedAt,
    stars_at_detection: snapshots[2].stars,
    first_emerging_at:
      spec.ageDays > 4 ? new Date(now - Math.min(spec.ageDays - 2, 26) * DAY).toISOString() : null,
    first_rising_at: ["rising", "breakout", "viral", "cooling"].includes(spec.profile)
      ? new Date(now - 12 * DAY).toISOString()
      : null,
    first_breakout_at: ["breakout", "viral", "fake"].includes(spec.profile)
      ? new Date(now - 5 * DAY).toISOString()
      : null,
    first_viral_at: spec.profile === "viral" ? new Date(now - 2 * DAY).toISOString() : null,
    peak_score: spec.breakout,
    peak_at: new Date(now - 1 * DAY).toISOString(),
    growth_since_detection: last.stars - snapshots[2].stars,
  };

  const events: RepoEvent[] = [{ ts: detectedAt, type: "detected", label: "First detected" }];
  if (detections.first_emerging_at)
    events.push({ ts: detections.first_emerging_at, type: "emerging", label: "Emerging" });
  if (detections.first_rising_at)
    events.push({ ts: detections.first_rising_at, type: "rising", label: "Rising" });
  if (detections.first_breakout_at)
    events.push({ ts: detections.first_breakout_at, type: "breakout", label: "Breakout" });
  if (detections.first_viral_at)
    events.push({ ts: detections.first_viral_at, type: "viral", label: "Viral" });
  if (spec.hasRelease)
    events.push({ ts: new Date(now - 8 * DAY).toISOString(), type: "release", label: "Release v0.1.0" });
  events.sort((a, b) => a.ts.localeCompare(b.ts));

  const whyRising = (() => {
    const major = d_first_major(detections);
    const accelTxt = `${acceleration >= 0 ? "+" : ""}${acceleration.toFixed(0)}%`;
    if (major)
      return (
        `This repository gained ${gain24.toLocaleString("en-US")} stars in the past 24 hours ` +
        `at ${velocity24.toFixed(1)} stars/hour, with acceleration of ${accelTxt} versus the ` +
        `previous 24 hours. Forks grew to ${last.forks.toLocaleString("en-US")} total, and the ` +
        `repository reached ${major} status ${daysAgo(majorTs(detections))}.`
      );
    return (
      `This repository is accumulating stars steadily at ${velocity24.toFixed(1)} stars/hour ` +
      `(+${gain24.toLocaleString("en-US")} in the past 24 hours). Activity signals are being ` +
      `collected to confirm whether this becomes a breakout.`
    );
  })();

  const card: RepoCard = {
    id: `demo-${spec.owner}-${spec.name}`,
    owner: spec.owner,
    name: spec.name,
    full_name: `${spec.owner}/${spec.name}`,
    description: spec.description,
    url: `https://github.com/${spec.owner}/${spec.name}`,
    language: spec.language,
    license: spec.license,
    category: spec.category,
    stars: last.stars,
    forks: last.forks,
    age_days: spec.ageDays,
    stars_24h_gain: gain24,
    velocity_24h: Math.round(velocity24 * 10) / 10,
    acceleration: Math.round(acceleration * 10) / 10,
    relative_growth: Math.round((gain24 / Math.max(dayBefore.stars, 50)) * 1000) / 1000,
    breakout_score: spec.breakout,
    organic_score: spec.organic,
    hype_risk: spec.hype,
    status: spec.status,
    detected_at: detectedAt,
    score_breakdown: spec.breakdown,
    insufficient_history: spec.profile === "tiny",
  };

  const hypeReasons =
    spec.hype === "high"
      ? [
          `+${gain24.toLocaleString("en-US")} stars in 24h, but forks barely moved (${last.forks.toLocaleString("en-US")} total)`,
          "Almost no new contributors in the past 7 days",
          "No release published; commit activity is flat",
          "Star curve is vertical while every other signal is flat — treat the score with skepticism",
        ]
      : spec.hype === "medium"
        ? [
            `+${gain24.toLocaleString("en-US")} stars in 24h outpaces fork growth`,
            "Contributor growth is lagging behind the star curve",
          ]
        : [
            "Fork growth tracks the star curve",
            "Multiple active contributors in the past 7 days",
            ...(spec.hasRelease ? ["Recent release published"] : []),
          ];

  const detail: RepoDetail = {
    ...card,
    topics: spec.topics,
    watchers: last.watchers,
    open_issues: last.open_issues,
    created_at: createdAt,
    pushed_at: new Date(now - 6 * 36e5).toISOString(),
    confidence: spec.profile === "tiny" ? 0.35 : 0.92,
    scoring_version: "v1",
    why_rising: whyRising,
    hype_risk_reasons: hypeReasons,
    detections,
  };

  return { card, detail, snapshots, scores, events, detections };
}

function d_first_major(d: DetectionInfo): string | null {
  return d.first_viral_at ? "viral" : d.first_breakout_at ? "breakout" : d.first_rising_at ? "rising" : d.first_emerging_at ? "emerging" : null;
}

function majorTs(d: DetectionInfo): string {
  return (d.first_viral_at ?? d.first_breakout_at ?? d.first_rising_at ?? d.first_emerging_at ?? d.first_detected_at) as string;
}

function daysAgo(iso: string): string {
  const d = Math.max(0, Math.round((now - new Date(iso).getTime()) / DAY));
  return d === 0 ? "today" : `${d} day${d === 1 ? "" : "s"} ago`;
}

const REPOS: BuiltRepo[] = SPECS.map((s, i) => buildRepo(s, i));
const byId = new Map(REPOS.map((r) => [r.card.id, r]));
const byName = new Map(REPOS.map((r) => [r.card.full_name.toLowerCase(), r]));

/* ------------------------------------------------------------------ */
/* Demo API — same shapes as the real backend.                         */
/* ------------------------------------------------------------------ */

export const demoApi = {
  async getRepos(params: RepoListParams = {}): Promise<RepoListResponse> {
    let items = REPOS.map((r) => r.card);
    if (params.status) items = items.filter((r) => r.status === params.status);
    if (params.category) items = items.filter((r) => r.category.includes(params.category!));
    if (params.language) items = items.filter((r) => r.language === params.language);
    if (params.min_stars) items = items.filter((r) => r.stars >= params.min_stars!);
    if (params.max_age_days) items = items.filter((r) => r.age_days <= params.max_age_days!);

    const sorters: Record<string, (r: RepoCard) => number> = {
      breakout_score: (r) => r.breakout_score ?? -1,
      growth_24h: (r) => r.stars_24h_gain ?? -Infinity,
      acceleration: (r) => r.acceleration ?? -Infinity,
      relative_growth: (r) => r.relative_growth ?? -Infinity,
      newest: (r) => new Date(r.detected_at).getTime(),
    };
    const sorter = sorters[params.sort ?? "breakout_score"] ?? sorters.breakout_score;
    items = [...items].sort((a, b) => sorter(b) - sorter(a));

    const limit = params.limit ?? 25;
    const start = params.cursor ? parseInt(params.cursor, 10) || 0 : 0;
    const page = items.slice(start, start + limit);
    return {
      items: page,
      next_cursor: start + limit < items.length ? String(start + limit) : null,
    };
  },

  async getRepo(owner: string, name: string): Promise<RepoDetail> {
    const r = byName.get(`${owner}/${name}`.toLowerCase());
    if (!r) throw new Error(`Demo repo not found: ${owner}/${name}`);
    return r.detail;
  },

  async getHistory(id: string, range: "7d" | "30d" | "90d" | "all" = "30d"): Promise<HistoryResponse> {
    const r = byId.get(id);
    if (!r) throw new Error(`Demo repo not found: ${id}`);
    const days = range === "7d" ? 7 : range === "30d" ? 30 : r.snapshots.length;
    return {
      snapshots: r.snapshots.slice(-days),
      scores: r.scores.slice(-days),
      detections: r.detections,
      events: r.events,
      insufficient_history: r.card.insufficient_history,
    };
  },

  async getCategories(): Promise<CategoryCount[]> {
    const counts = new Map<string, number>();
    REPOS.forEach((r) => r.card.category.forEach((c) => counts.set(c, (counts.get(c) ?? 0) + 1)));
    return [...counts.entries()]
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => b.count - a.count);
  },

  async getStats(): Promise<RadarStats> {
    return {
      tracked_repos: REPOS.length,
      snapshots_24h: REPOS.length * 4,
      detections_7d: 3,
      api_calls_24h: 1874,
    };
  },

  async addRepo(fullName: string): Promise<AddRepoResponse> {
    return { job_id: `demo-${Date.now()}`, status: `queued (demo): ${fullName}` };
  },
};
