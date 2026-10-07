"use client";

import * as React from "react";
import Link from "next/link";
import {
  ArrowRight,
  BarChart3,
  Bell,
  Copy,
  Check,
  Flame,
  Gauge,
  GitBranch,
  Leaf,
  Radar,
  Rocket,
  ShieldCheck,
  Sparkles,
  Terminal,
  TrendingUp,
  Zap,
} from "lucide-react";
import { demoApi } from "@/lib/demo";
import type { RepoCard } from "@/lib/types";
import { RepoCardRow } from "@/components/RepoCard";
import { Button } from "@/components/ui/button";

/* ------------------------------------------------------------------ */
/* Small building blocks                                               */
/* ------------------------------------------------------------------ */

function Section({
  eyebrow,
  title,
  sub,
  children,
}: {
  eyebrow: string;
  title: string;
  sub?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="mx-auto max-w-7xl px-4 py-16 sm:px-6 sm:py-20">
      <p className="text-xs font-bold uppercase tracking-[0.2em] text-emerald-600 dark:text-emerald-400">
        {eyebrow}
      </p>
      <h2 className="mt-2 text-3xl font-bold tracking-tight sm:text-4xl">{title}</h2>
      {sub && (
        <p className="mt-3 max-w-2xl text-base text-zinc-500 dark:text-zinc-400">{sub}</p>
      )}
      <div className="mt-10">{children}</div>
    </section>
  );
}

function Code({ children }: { children: string }) {
  const [copied, setCopied] = React.useState(false);
  return (
    <div className="group relative">
      <pre className="overflow-x-auto rounded-xl bg-zinc-950 p-4 pr-12 font-mono text-sm text-zinc-100 dark:bg-black">
        <code>{children}</code>
      </pre>
      <button
        onClick={() => {
          navigator.clipboard.writeText(children).catch(() => {});
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        }}
        className="absolute right-3 top-3 rounded-md p-1.5 text-zinc-400 opacity-0 transition group-hover:opacity-100 hover:bg-zinc-800 hover:text-zinc-100"
        aria-label="Copy"
      >
        {copied ? <Check className="h-4 w-4 text-emerald-400" /> : <Copy className="h-4 w-4" />}
      </button>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Live demo leaderboard preview (demo data, no backend)               */
/* ------------------------------------------------------------------ */

function LiveDemo() {
  const [items, setItems] = React.useState<RepoCard[]>([]);
  React.useEffect(() => {
    demoApi.getRepos({ sort: "breakout_score", limit: 5 }).then((r) => setItems(r.items));
  }, []);
  return (
    <div className="overflow-hidden rounded-2xl border border-zinc-200 bg-white shadow-xl dark:border-zinc-800 dark:bg-zinc-900">
      <div className="flex items-center justify-between border-b border-zinc-200 px-5 py-3 dark:border-zinc-800">
        <div className="flex items-center gap-2">
          <span className="h-2.5 w-2.5 rounded-full bg-red-400" />
          <span className="h-2.5 w-2.5 rounded-full bg-amber-400" />
          <span className="h-2.5 w-2.5 rounded-full bg-emerald-400" />
        </div>
        <p className="font-mono text-xs text-zinc-400">rising-radar — live demo</p>
        <span className="rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold uppercase text-amber-700 dark:bg-amber-900/40 dark:text-amber-300">
          Live snapshot · 2026-10-07
        </span>
      </div>
      <div className="space-y-3 p-5">
        {items.length === 0 ? (
          <p className="text-sm text-zinc-400">Loading…</p>
        ) : (
          items.map((r) => <RepoCardRow key={r.id} repo={r} />)
        )}
      </div>
      <div className="border-t border-zinc-200 px-5 py-4 dark:border-zinc-800">
        <Link href="/leaderboard">
          <Button className="w-full">
            Open the full leaderboard <ArrowRight className="h-4 w-4" />
          </Button>
        </Link>
      </div>
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

const FEATURES = [
  {
    icon: Zap,
    title: "Star velocity, not star count",
    body: "We track stars/hour across 1h / 6h / 24h / 7d windows from observed snapshots — so a 200-star repo gaining 500/day outranks a 50k-star repo gaining 50.",
  },
  {
    icon: TrendingUp,
    title: "Acceleration detection",
    body: "Not just how fast stars arrive, but whether that rate is increasing. A repo going 10 → 50 → 200 stars/day scores above one flat at 100/day.",
  },
  {
    icon: Gauge,
    title: "Deterministic 0–100 score",
    body: "30% velocity + 25% acceleration + 15% relative growth + 10% fork growth + 10% activity + 10% age bonus. Same snapshots → same score, always. No black box.",
  },
  {
    icon: Leaf,
    title: "Organic Score + Hype Risk",
    body: "Is the star spike backed by forks, contributors and releases? High stars with flat activity get flagged — never presented as bot detection, just healthy skepticism.",
  },
  {
    icon: Bell,
    title: "Detection timestamps",
    body: "Every first detection is stored permanently. If a repo blows up next month, the record shows exactly when the radar flagged it.",
  },
  {
    icon: GitBranch,
    title: "CLI + API + Web",
    body: "Use the standalone CLI with zero infrastructure, the documented REST API, or this hosted leaderboard. Docker Compose runs the full pipeline in one command.",
  },
];

const STEPS = [
  {
    n: "01",
    title: "Discover",
    body: "The worker scans GitHub discovery buckets (new repos, rising stars per language, topic watchlists) and registers candidates before they trend.",
  },
  {
    n: "02",
    title: "Snapshot",
    body: "Stars, forks, watchers, issues, contributors and commit activity are snapshotted on an adaptive schedule — hot repos poll faster. History starts when we start watching; never fabricated.",
  },
  {
    n: "03",
    title: "Score & surface",
    body: "Every snapshot recomputes velocity, acceleration and the breakout score with robust normalization against the live corpus. Hysteresis + cooling keeps the leaderboard stable, not jittery.",
  },
];

export default function HomePage() {
  return (
    <div className="-mx-4 -mt-6 sm:-mx-6">
      {/* ------------------------------ HERO ------------------------------ */}
      <div className="relative overflow-hidden">
        <div
          className="pointer-events-none absolute inset-0"
          style={{
            background:
              "radial-gradient(60rem 30rem at 50% -10%, rgba(16,185,129,0.18), transparent), radial-gradient(40rem 20rem at 85% 20%, rgba(59,130,246,0.12), transparent)",
          }}
        />
        <div className="relative mx-auto max-w-7xl px-4 pb-16 pt-20 text-center sm:px-6 sm:pt-28">
          <div className="mb-6 inline-flex items-center gap-2 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-semibold text-emerald-700 dark:border-emerald-900 dark:bg-emerald-950/60 dark:text-emerald-300">
            <Sparkles className="h-3.5 w-3.5" />
            Open source · Apache-2.0 · deterministic scoring
          </div>
          <h1 className="mx-auto max-w-4xl text-4xl font-extrabold tracking-tight sm:text-6xl">
            Star velocity,{" "}
            <span className="bg-gradient-to-r from-emerald-500 to-teal-400 bg-clip-text text-transparent">
              not star count
            </span>
          </h1>
          <p className="mx-auto mt-6 max-w-2xl text-lg text-zinc-500 dark:text-zinc-400">
            GitHub Trending ranks by total stars, so the same big repos sit there for weeks.
            Rising Radar ranks by how fast stars are arriving right now — velocity, acceleration,
            and whether the growth is backed by real activity. Each detection is timestamped,
            so you can check whether it actually called the breakout early.
          </p>
          <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
            <Link href="/leaderboard">
              <Button size="lg" className="bg-emerald-500 text-zinc-950 hover:bg-emerald-400">
                <Flame className="h-5 w-5" /> See what&apos;s rising
              </Button>
            </Link>
            <Link href="#cli">
              <Button size="lg" variant="outline">
                <Terminal className="h-5 w-5" /> Install the CLI
              </Button>
            </Link>
          </div>

          {/* stat strip */}
          <div className="mx-auto mt-12 grid max-w-3xl grid-cols-2 gap-4 sm:grid-cols-4">
            {[
              ["6", "signal windows"],
              ["0–100", "breakout score"],
              ["100%", "deterministic"],
              ["0", "history invented"],
            ].map(([v, l]) => (
              <div
                key={l}
                className="rounded-2xl border border-zinc-200 bg-white/70 px-4 py-5 backdrop-blur dark:border-zinc-800 dark:bg-zinc-900/70"
              >
                <p className="text-2xl font-extrabold text-emerald-600 dark:text-emerald-400">{v}</p>
                <p className="mt-1 text-xs text-zinc-500 dark:text-zinc-400">{l}</p>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* --------------------------- LIVE DEMO --------------------------- */}
      <Section
        eyebrow="Live demo"
        title="What a breakout looks like in numbers"
        sub="Real repositories from GitHub, snapshot taken 2026-10-07. Scores computed from stars/day velocity."
      >
        <div className="grid items-start gap-8 lg:grid-cols-5">
          <div className="lg:col-span-3">
            <LiveDemo />
          </div>
          <div className="space-y-4 lg:col-span-2">
            {[
              {
                icon: Rocket,
                t: "Small repos can outrank big ones",
                d: "A 120-star CLI gaining 680 stars in 24h scores 92 — above a 45k-star UI kit gaining 30. Relative growth counts, not just absolute.",
              },
              {
                icon: ShieldCheck,
                t: "Manufactured spikes get flagged",
                d: "2,900 new stars with zero forks and one contributor? That's high hype risk — the score gets discounted, not celebrated.",
              },
              {
                icon: BarChart3,
                t: "Every score explained",
                d: "Click any repo for the full component breakdown, annotated charts and the why-rising narrative.",
              },
            ].map((f) => (
              <div
                key={f.t}
                className="flex gap-4 rounded-2xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900"
              >
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-300">
                  <f.icon className="h-5 w-5" />
                </span>
                <div>
                  <p className="font-semibold">{f.t}</p>
                  <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">{f.d}</p>
                </div>
              </div>
            ))}
            <Link href="/compare" className="flex items-center gap-1 text-sm font-medium text-emerald-600 hover:underline dark:text-emerald-400">
              Compare up to 5 repos side by side <ArrowRight className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </Section>

      {/* --------------------------- FEATURES --------------------------- */}
      <div className="border-y border-zinc-200 bg-zinc-100/50 dark:border-zinc-800 dark:bg-zinc-900/40">
        <Section
          eyebrow="Why Rising Radar"
          title="What it actually measures"
          sub="Six signals, one deterministic score. Same snapshots in, same score out — no model, no vibes."
        >
          <div className="grid gap-5 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map((f) => (
              <div
                key={f.title}
                className="rounded-2xl border border-zinc-200 bg-white p-6 transition hover:shadow-lg dark:border-zinc-800 dark:bg-zinc-900"
              >
                <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-zinc-950 text-emerald-400 dark:bg-emerald-500 dark:text-zinc-950">
                  <f.icon className="h-5 w-5" />
                </span>
                <h3 className="mt-4 text-lg font-bold">{f.title}</h3>
                <p className="mt-2 text-sm leading-relaxed text-zinc-500 dark:text-zinc-400">{f.body}</p>
              </div>
            ))}
          </div>
        </Section>
      </div>

      {/* -------------------------- HOW IT WORKS -------------------------- */}
      <Section
        eyebrow="How it works"
        title="Discover → snapshot → score"
        sub="A worker pipeline backed by PostgreSQL. The scoring engine is pure functions — stdlib only, fully tested."
      >
        <div className="grid gap-5 md:grid-cols-3">
          {STEPS.map((s) => (
            <div
              key={s.n}
              className="relative rounded-2xl border border-zinc-200 bg-white p-6 dark:border-zinc-800 dark:bg-zinc-900"
            >
              <p className="font-mono text-4xl font-extrabold text-zinc-200 dark:text-zinc-800">{s.n}</p>
              <h3 className="mt-2 text-lg font-bold">{s.title}</h3>
              <p className="mt-2 text-sm leading-relaxed text-zinc-500 dark:text-zinc-400">{s.body}</p>
            </div>
          ))}
        </div>
        <div className="mt-8">
          <Code>{`breakout = 30% star velocity + 25% acceleration + 15% relative growth
         + 10% fork growth  + 10% activity      + 10% age bonus`}</Code>
          <p className="mt-3 text-xs text-zinc-400">
            Each component is robustly normalized (log1p → robust z-score → normal CDF) against the
            live corpus, so one outlier can&apos;t break the scale. Full spec in docs/SCORING.md.
          </p>
        </div>
      </Section>

      {/* ------------------------------ CLI ------------------------------ */}
      <div id="cli" className="border-y border-zinc-200 bg-zinc-950 py-2 text-zinc-100 dark:border-zinc-800">
        <Section
          eyebrow="CLI"
          title="Works with zero setup"
          sub="The standalone CLI needs no database — snapshots live in ~/.rising-radar. Track your own watchlist from the terminal."
        >
          <div className="grid gap-8 lg:grid-cols-2">
            <div className="space-y-4">
              <Code>{`pipx install ./cli
# or: pip install ./cli

rising-radar demo              # no API key needed
rising-radar check owner/repo  # snapshot + velocity
rising-radar watch owner/repo  # add to watchlist
rising-radar list              # ranked by velocity`}</Code>
              <p className="text-sm text-zinc-400">
                Set <code className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-xs">GITHUB_TOKEN</code> to
                raise the rate limit from 60 to 5,000 requests/hour. The more often you{" "}
                <code className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-xs">check</code>, the
                sharper the velocity signal.
              </p>
            </div>
            <div className="space-y-4">
              <div className="rounded-2xl border border-zinc-800 bg-zinc-900 p-6">
                <p className="font-mono text-xs text-zinc-500">$ rising-radar check NandhaKishorM/laya</p>
                <pre className="mt-3 font-mono text-sm leading-relaxed text-zinc-200">
{`★ NandhaKishorM/laya
  stars: 31,259  forks: 2,847  language: Python
  velocity: 1,645 stars/day (19 days old)
  breakout: 97/100  status: breakout`}
                </pre>
              </div>
              <div className="flex items-center gap-3 text-sm text-zinc-400">
                <Radar className="h-5 w-5 text-emerald-400" />
                Full pipeline (PostgreSQL + API + worker)?{" "}
                <code className="rounded bg-zinc-800 px-1.5 py-0.5 font-mono text-xs">docker compose up --build</code>
              </div>
            </div>
          </div>
        </Section>
      </div>

      {/* --------------------------- COMPARISON --------------------------- */}
      <Section
        eyebrow="Honest comparison"
        title="Radar vs. Trending"
        sub="Trending answers 'what's popular'. The radar answers 'what's speeding up'. Different question, different ranking."
      >
        <div className="overflow-hidden rounded-2xl border border-zinc-200 dark:border-zinc-800">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-zinc-200 bg-zinc-50 dark:border-zinc-800 dark:bg-zinc-900">
                <th className="px-5 py-3 font-medium text-zinc-400"> </th>
                <th className="px-5 py-3 font-bold text-emerald-600 dark:text-emerald-400">Rising Radar</th>
                <th className="px-5 py-3 font-medium text-zinc-500">GitHub Trending</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-zinc-200 dark:divide-zinc-800">
              {[
                ["Moment captured", "As growth begins", "After it's famous"],
                ["Primary signal", "Velocity + acceleration", "Total stars"],
                ["Small repos", "First-class (relative growth)", "Invisible"],
                ["Score explained", "Full breakdown per repo", "—"],
                ["Hype skepticism", "Organic score / hype risk", "—"],
                ["Provenance", "Permanent detection timestamps", "—"],
              ].map(([k, a, b]) => (
                <tr key={k} className="bg-white dark:bg-zinc-950">
                  <td className="px-5 py-3 font-medium text-zinc-500">{k}</td>
                  <td className="px-5 py-3 font-semibold">{a}</td>
                  <td className="px-5 py-3 text-zinc-500 dark:text-zinc-400">{b}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {/* ------------------------------ CTA ------------------------------ */}
      <div className="mx-auto max-w-7xl px-4 pb-20 sm:px-6">
        <div className="relative overflow-hidden rounded-3xl bg-zinc-950 px-8 py-14 text-center text-zinc-100 sm:px-16">
          <div
            className="pointer-events-none absolute inset-0"
            style={{
              background:
                "radial-gradient(40rem 20rem at 50% 0%, rgba(16,185,129,0.25), transparent)",
            }}
          />
          <div className="relative">
            <Radar className="mx-auto h-12 w-12 text-emerald-400" />
            <h2 className="mx-auto mt-4 max-w-2xl text-3xl font-extrabold tracking-tight sm:text-4xl">
              Watch repos gain velocity, not just stars
            </h2>
            <p className="mx-auto mt-3 max-w-xl text-zinc-400">
              Run the leaderboard, install the CLI, or deploy the full pipeline yourself.
              Apache-2.0 — the scoring formula is in the repo, not a black box.
            </p>
            <div className="mt-8 flex flex-col items-center justify-center gap-3 sm:flex-row">
              <Link href="/leaderboard">
                <Button size="lg" className="bg-emerald-500 text-zinc-950 hover:bg-emerald-400">
                  <Flame className="h-5 w-5" /> Launch the leaderboard
                </Button>
              </Link>
              <a
                href="https://github.com"
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-2 rounded-lg border border-zinc-700 px-6 py-3 text-sm font-semibold hover:bg-zinc-900"
              >
                <GitBranch className="h-4 w-4" /> Star on GitHub
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
