"use client";

import * as React from "react";
import Link from "next/link";
import {
  AlertCircle,
  ArrowLeft,
  ExternalLink,
  GitFork,
  History,
  Star,
} from "lucide-react";
import { getHistory, getRepo, ApiError } from "@/lib/api";
import type { HistoryResponse, RepoDetail } from "@/lib/types";
import {
  formatAgeDays,
  formatDateTime,
  formatNumber,
  formatPct,
  formatSigned,
  formatVelocity,
  LANGUAGE_COLORS,
  timeAgo,
} from "@/lib/utils";
import { ScoreBadge, ScoreMeter } from "@/components/ScoreBadge";
import { ScoreBreakdownPanel } from "@/components/ScoreBreakdown";
import { BeforeCool, WhyRising } from "@/components/WhyRising";
import { HypeRiskPanel } from "@/components/HypeRisk";
import {
  ForksChart,
  ScoreChart,
  StarsChart,
  VelocityChart,
  type ChartEvent,
  type ChartPoint,
} from "@/components/Charts";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { Select } from "@/components/ui/select";
import { ErrorState } from "@/components/EmptyState";

const EVENT_COLORS: Record<string, string> = {
  detected: "#a1a1aa",
  emerging: "#38bdf8",
  rising: "#34d399",
  breakout: "#fbbf24",
  viral: "#fb7185",
  release: "#a78bfa",
};

function mergeChartData(h: HistoryResponse): ChartPoint[] {
  const scoreBy = new Map(h.scores.map((s) => [s.ts, s]));
  return h.snapshots.map((snap) => {
    const sc = scoreBy.get(snap.ts);
    const t = new Date(snap.ts).getTime();
    return {
      t,
      stars: snap.stars,
      forks: snap.forks,
      velocity: sc?.velocity_24h ?? null,
      score: sc ? sc.breakout_score : null,
    };
  });
}

function eventsToMarkers(h: HistoryResponse): ChartEvent[] {
  return h.events.map((e) => ({
    t: new Date(e.ts).getTime(),
    label: e.label,
    color: EVENT_COLORS[e.type] ?? "#a1a1aa",
  }));
}

export default function DetailClient({
  owner,
  name,
}: {
  owner: string;
  name: string;
}) {
  const [repo, setRepo] = React.useState<RepoDetail | null>(null);
  const [history, setHistory] = React.useState<HistoryResponse | null>(null);
  const [range, setRange] = React.useState<"7d" | "30d" | "90d" | "all">("30d");
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);

  const load = React.useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const r = await getRepo(owner, name);
      setRepo(r);
      const h = await getHistory(r.id, range);
      setHistory(h);
    } catch (err) {
      setError(
        err instanceof ApiError && err.status === 404
          ? "Repository not found. It may not be tracked yet — use “Track repo” to add it."
          : "Failed to load repository details.",
      );
    } finally {
      setLoading(false);
    }
  }, [owner, name, range]);

  React.useEffect(() => {
    load();
  }, [load]);

  if (loading) return <DetailSkeleton />;
  if (error || !repo) return <ErrorState message={error ?? "Unknown error"} onRetry={load} />;

  const chartData = history ? mergeChartData(history) : [];
  const markers = history ? eventsToMarkers(history) : [];
  const langColor = repo.language ? LANGUAGE_COLORS[repo.language] ?? "#a1a1aa" : null;

  return (
    <div className="space-y-5">
      <Link
        href="/"
        className="inline-flex items-center gap-1.5 text-sm text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
      >
        <ArrowLeft className="h-4 w-4" /> Leaderboard
      </Link>

      {/* Header */}
      <div className="rounded-xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-900 sm:p-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="font-mono text-xl font-bold tracking-tight sm:text-2xl">
                {repo.full_name}
              </h1>
              <ScoreBadge status={repo.status} score={repo.breakout_score} size="lg" />
            </div>
            {repo.description && (
              <p className="mt-2 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
                {repo.description}
              </p>
            )}
            <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs text-zinc-500 dark:text-zinc-400">
              {repo.language && (
                <span className="inline-flex items-center gap-1.5">
                  <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: langColor! }} />
                  {repo.language}
                </span>
              )}
              {repo.license && <span>{repo.license}</span>}
              {repo.category.map((c) => (
                <Badge key={c} variant="secondary">
                  {c}
                </Badge>
              ))}
              <span>{formatAgeDays(repo.age_days)} old</span>
              <span>detected {timeAgo(repo.detected_at)}</span>
              {repo.pushed_at && <span>pushed {timeAgo(repo.pushed_at)}</span>}
              <a
                href={repo.url}
                target="_blank"
                rel="noreferrer"
                className="inline-flex items-center gap-1 font-medium text-emerald-600 hover:underline dark:text-emerald-400"
              >
                GitHub <ExternalLink className="h-3 w-3" />
              </a>
            </div>
          </div>
          <div className="grid grid-cols-2 gap-x-8 gap-y-3 sm:grid-cols-4">
            <HeaderStat icon={<Star className="h-4 w-4" />} label="Stars" value={formatNumber(repo.stars)} sub={repo.stars_24h_gain !== null ? `${formatSigned(repo.stars_24h_gain)} / 24h` : "—"} />
            <HeaderStat icon={<GitFork className="h-4 w-4" />} label="Forks" value={formatNumber(repo.forks)} />
            <HeaderStat label="Velocity" value={formatVelocity(repo.velocity_24h)} sub={repo.acceleration !== null ? `accel ${formatPct(repo.acceleration)}` : "—"} />
            <HeaderStat label="Scoring" value={repo.scoring_version} sub={repo.confidence !== null ? `confidence ${(repo.confidence * 100).toFixed(0)}%` : "—"} />
          </div>
        </div>
      </div>

      {repo.insufficient_history && (
        <div className="flex items-start gap-3 rounded-xl border border-amber-300 bg-amber-50 p-4 text-sm dark:border-amber-800 dark:bg-amber-950/40">
          <AlertCircle className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" />
          <p>
            <span className="font-semibold">Insufficient history.</span> This repository was
            detected recently, so velocity and acceleration aren&apos;t reliable yet. Metrics below
            are partial — nothing is estimated or backfilled.
          </p>
        </div>
      )}

      {/* Charts */}
      <div className="flex items-center justify-between">
        <h2 className="flex items-center gap-2 text-lg font-semibold">
          <History className="h-4 w-4" /> History
        </h2>
        <Select
          value={range}
          onChange={(e) => setRange(e.target.value as typeof range)}
          options={[
            { value: "7d", label: "7 days" },
            { value: "30d", label: "30 days" },
            { value: "90d", label: "90 days" },
            { value: "all", label: "All" },
          ]}
          aria-label="History range"
        />
      </div>

      {chartData.length === 0 ? (
        <Card>
          <CardContent className="py-12 text-center text-sm text-zinc-500">
            No snapshots yet for this range.
          </CardContent>
        </Card>
      ) : (
        <div className="grid gap-4 lg:grid-cols-2">
          <StarsChart data={chartData} events={markers} />
          <VelocityChart data={chartData} events={markers} />
          <ScoreChart data={chartData} events={markers} />
          <ForksChart data={chartData} />
        </div>
      )}

      {/* Detection timeline */}
      {history && history.events.length > 0 && (
        <Card>
          <CardHeader className="pb-2">
            <CardTitle className="text-sm">Detection timeline</CardTitle>
          </CardHeader>
          <CardContent>
            <ol className="flex flex-wrap gap-x-6 gap-y-2">
              {history.events.map((e, i) => (
                <li key={`${e.ts}-${i}`} className="flex items-center gap-2 text-sm">
                  <span
                    className="h-2.5 w-2.5 rounded-full"
                    style={{ backgroundColor: EVENT_COLORS[e.type] ?? "#a1a1aa" }}
                  />
                  <span className="font-medium">{e.label}</span>
                  <span className="font-mono text-xs text-zinc-500 dark:text-zinc-400">
                    {formatDateTime(e.ts)}
                  </span>
                </li>
              ))}
            </ol>
          </CardContent>
        </Card>
      )}

      {/* Explanation + organic + hype */}
      <div className="grid gap-4 lg:grid-cols-2">
        <ScoreBreakdownPanel breakdown={repo.score_breakdown} total={repo.breakout_score} />
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2">
            <Card className="p-5">
              <div className="text-xs font-medium text-zinc-500 dark:text-zinc-400">Organic score</div>
              <div className="mt-1 font-mono text-3xl font-bold tabular-nums">
                {repo.organic_score !== null ? Math.round(repo.organic_score) : "—"}
                <span className="text-sm font-normal text-zinc-400">/100</span>
              </div>
              <p className="mt-2 text-xs text-zinc-500 dark:text-zinc-400">
                How much the growth is backed by real activity (forks, contributors, releases).
              </p>
            </Card>
            <Card className="p-5">
              <ScoreMeter value={repo.organic_score} label="Activity-backed growth" />
              <div className="mt-3">
                <ScoreMeter value={repo.breakout_score} label="Breakout score" />
              </div>
            </Card>
          </div>
          <HypeRiskPanel
            level={repo.hype_risk}
            reasons={repo.hype_risk_reasons}
            organicScore={repo.organic_score}
          />
        </div>
      </div>

      <WhyRising repo={repo} />
      <BeforeCool repo={repo} />
    </div>
  );
}

function HeaderStat({
  icon,
  label,
  value,
  sub,
}: {
  icon?: React.ReactNode;
  label: string;
  value: string;
  sub?: string;
}) {
  return (
    <div>
      <div className="flex items-center gap-1.5 text-xs text-zinc-500 dark:text-zinc-400">
        {icon}
        {label}
      </div>
      <div className="mt-0.5 font-mono text-xl font-bold tabular-nums">{value}</div>
      {sub && <div className="font-mono text-xs text-zinc-500 dark:text-zinc-400">{sub}</div>}
    </div>
  );
}

function DetailSkeleton() {
  return (
    <div className="space-y-5">
      <Skeleton className="h-4 w-32" />
      <Skeleton className="h-40 w-full" />
      <div className="grid gap-4 lg:grid-cols-2">
        {Array.from({ length: 4 }).map((_, i) => (
          <Skeleton key={i} className="h-72 w-full" />
        ))}
      </div>
    </div>
  );
}
