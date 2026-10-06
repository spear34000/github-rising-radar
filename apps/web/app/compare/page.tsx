"use client";

import * as React from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { GitCompareArrows, Plus, Scale, X } from "lucide-react";
import { getHistory, getRepo } from "@/lib/api";
import type { RepoDetail } from "@/lib/types";
import {
  formatAgeDays,
  formatNumber,
  formatPct,
  formatSigned,
  formatVelocity,
} from "@/lib/utils";
import { CompareStarsChart, type CompareSeries } from "@/components/Charts";
import { ScoreBadge } from "@/components/ScoreBadge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState, ErrorState } from "@/components/EmptyState";

const METRICS: Array<{
  key: string;
  label: string;
  get: (r: RepoDetail) => string;
  mono?: boolean;
}> = [
  { key: "stars", label: "Stars", get: (r) => formatNumber(r.stars), mono: true },
  { key: "gain24", label: "24h gain", get: (r) => formatSigned(r.stars_24h_gain), mono: true },
  { key: "velocity", label: "Velocity", get: (r) => formatVelocity(r.velocity_24h), mono: true },
  { key: "accel", label: "Acceleration", get: (r) => formatPct(r.acceleration), mono: true },
  { key: "forks", label: "Forks", get: (r) => formatNumber(r.forks), mono: true },
  { key: "score", label: "Breakout score", get: (r) => (r.breakout_score === null ? "—" : String(Math.round(r.breakout_score))), mono: true },
  { key: "organic", label: "Organic score", get: (r) => (r.organic_score !== null ? String(Math.round(r.organic_score)) : "—"), mono: true },
  { key: "hype", label: "Hype risk", get: (r) => (r.hype_risk ? r.hype_risk.toUpperCase() : "—") },
  { key: "status", label: "Status", get: (r) => r.status.toUpperCase() },
  { key: "age", label: "Age", get: (r) => formatAgeDays(r.age_days) },
  { key: "lang", label: "Language", get: (r) => r.language ?? "—" },
];

function CompareView() {
  const searchParams = useSearchParams();
  const initial = React.useMemo(
    () =>
      (searchParams.get("repos") ?? "")
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean)
        .slice(0, 5),
    [searchParams],
  );

  const [names, setNames] = React.useState<string[]>(initial);
  const [repos, setRepos] = React.useState<RepoDetail[]>([]);
  const [series, setSeries] = React.useState<CompareSeries[]>([]);
  const [loading, setLoading] = React.useState(true);
  const [error, setError] = React.useState<string | null>(null);
  const [normalized, setNormalized] = React.useState(false);
  const [adding, setAdding] = React.useState("");

  React.useEffect(() => {
    setNames(initial);
  }, [initial]);

  React.useEffect(() => {
    let cancelled = false;
    const run = async () => {
      if (names.length === 0) {
        setRepos([]);
        setSeries([]);
        setLoading(false);
        return;
      }
      setLoading(true);
      setError(null);
      try {
        const details = await Promise.all(
          names.map((n) => {
            const [owner, repo] = n.split("/");
            return getRepo(owner, repo);
          }),
        );
        if (cancelled) return;
        setRepos(details);
        const s = await Promise.all(
          details.map(async (d) => {
            const h = await getHistory(d.id, "30d");
            return {
              name: d.full_name,
              points: h.snapshots.map((p) => ({
                t: new Date(p.ts).getTime(),
                stars: p.stars,
              })),
            };
          }),
        );
        if (!cancelled) setSeries(s);
      } catch {
        if (!cancelled) setError("One or more repositories could not be loaded. Check the owner/name spelling.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    run();
    return () => {
      cancelled = true;
    };
  }, [names]);

  const add = (e: React.FormEvent) => {
    e.preventDefault();
    const v = adding.trim();
    if (!/^[\w.-]+\/[\w.-]+$/.test(v)) return;
    if (names.includes(v) || names.length >= 5) return;
    setNames([...names, v]);
    setAdding("");
  };

  const remove = (n: string) => setNames(names.filter((x) => x !== n));

  return (
    <div className="space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-2xl font-bold tracking-tight">
          <GitCompareArrows className="h-6 w-6" /> Compare
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Pick 2–5 repositories and compare their trajectories side by side.
        </p>
      </div>

      <Card>
        <CardContent className="flex flex-col gap-3 pt-5 sm:flex-row sm:items-end">
          <form onSubmit={add} className="flex flex-1 items-end gap-2">
            <div className="flex-1">
              <Input
                label="Add repository (owner/name)"
                placeholder="owner/name"
                value={adding}
                onChange={(e) => setAdding(e.target.value)}
                disabled={names.length >= 5}
              />
            </div>
            <Button type="submit" variant="outline" disabled={names.length >= 5}>
              <Plus className="h-4 w-4" /> Add
            </Button>
          </form>
          <div className="flex flex-wrap gap-1.5">
            {names.map((n) => (
              <span
                key={n}
                className="inline-flex items-center gap-1 rounded-full bg-zinc-100 px-2.5 py-1 font-mono text-xs dark:bg-zinc-800"
              >
                {n}
                <button onClick={() => remove(n)} aria-label={`Remove ${n}`} className="text-zinc-400 hover:text-zinc-700 dark:hover:text-zinc-200">
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
        </CardContent>
      </Card>

      {loading ? (
        <div className="space-y-3">
          <Skeleton className="h-80 w-full" />
          <Skeleton className="h-64 w-full" />
        </div>
      ) : error ? (
        <ErrorState message={error} onRetry={() => setNames([...names])} />
      ) : repos.length < 2 ? (
        <EmptyState
          title="Add at least two repositories"
          hint="Use the input above, or share a link like /compare?repos=owner1/name1,owner2/name2"
        />
      ) : (
        <>
          <Card>
            <CardHeader className="flex flex-row items-center justify-between pb-2">
              <CardTitle className="text-sm">Stars over time</CardTitle>
              <label className="flex cursor-pointer items-center gap-2 text-xs text-zinc-500 dark:text-zinc-400">
                <input
                  type="checkbox"
                  checked={normalized}
                  onChange={(e) => setNormalized(e.target.checked)}
                  className="h-4 w-4 accent-emerald-500"
                />
                <span className="inline-flex items-center gap-1">
                  <Scale className="h-3.5 w-3.5" /> Normalize (% of peak)
                </span>
              </label>
            </CardHeader>
            <CardContent>
              <CompareStarsChart series={series} normalized={normalized} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Metrics</CardTitle>
            </CardHeader>
            <CardContent className="overflow-x-auto">
              <table className="w-full min-w-[560px] text-sm">
                <thead>
                  <tr className="border-b border-zinc-200 dark:border-zinc-800">
                    <th className="py-2 pr-4 text-left text-xs font-medium text-zinc-500">Metric</th>
                    {repos.map((r) => (
                      <th key={r.id} className="px-3 py-2 text-right">
                        <Link
                          href={`/repo/${r.owner}/${r.name}`}
                          className="font-mono text-xs font-semibold hover:text-emerald-600 dark:hover:text-emerald-400"
                        >
                          {r.full_name}
                        </Link>
                        <div className="mt-1 flex justify-end">
                          <ScoreBadge status={r.status} score={r.breakout_score} size="sm" />
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {METRICS.map((m) => (
                    <tr key={m.key} className="border-b border-zinc-100 last:border-0 dark:border-zinc-800/60">
                      <td className="py-2.5 pr-4 text-xs font-medium text-zinc-500 dark:text-zinc-400">
                        {m.label}
                      </td>
                      {repos.map((r) => (
                        <td
                          key={r.id}
                          className={`px-3 py-2.5 text-right tabular-nums ${m.mono ? "font-mono" : ""}`}
                        >
                          {m.get(r)}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </CardContent>
          </Card>
        </>
      )}
    </div>
  );
}

export default function ComparePage() {
  return (
    <React.Suspense
      fallback={
        <div className="space-y-3">
          <Skeleton className="h-8 w-48" />
          <Skeleton className="h-80 w-full" />
        </div>
      }
    >
      <CompareView />
    </React.Suspense>
  );
}
