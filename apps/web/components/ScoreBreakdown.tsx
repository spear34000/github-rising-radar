"use client";

import { Info } from "lucide-react";
import type { ScoreBreakdown as Breakdown } from "@/lib/types";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "./ui/card";
import { Tooltip } from "./ui/tooltip";

const ROWS: Array<{ key: keyof Breakdown; label: string; hint: string }> = [
  { key: "star_velocity", label: "Star velocity", hint: "How fast stars are arriving right now, normalized against all tracked repos." },
  { key: "acceleration", label: "Acceleration", hint: "Whether growth is speeding up vs. the previous period (robust z-score of velocity change)." },
  { key: "relative_growth", label: "Relative growth", hint: "Star gain relative to repo size, with smoothing so tiny repos don't explode the score." },
  { key: "fork_growth", label: "Fork growth", hint: "Fork velocity and fork/star conversion — a proxy for people actually using the code." },
  { key: "activity", label: "Activity", hint: "Commits, releases, PRs, issues and contributor growth backing the star curve." },
  { key: "age_bonus", label: "Age bonus", hint: "Small boost for young repos — Radar exists to find things early." },
];

const BAR_COLORS: Record<keyof Breakdown, string> = {
  star_velocity: "bg-emerald-500",
  acceleration: "bg-amber-500",
  relative_growth: "bg-sky-500",
  fork_growth: "bg-violet-500",
  activity: "bg-rose-400",
  age_bonus: "bg-zinc-400",
};

export function ScoreBreakdownPanel({
  breakdown,
  total,
}: {
  breakdown: Breakdown | null;
  total: number | null;
}) {
  if (!breakdown) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Score decomposition</CardTitle>
          <CardDescription>Not enough history to decompose the score yet.</CardDescription>
        </CardHeader>
      </Card>
    );
  }
  const max = Math.max(1, ...ROWS.map((r) => breakdown[r.key]));
  return (
    <Card>
      <CardHeader>
        <CardTitle>Score decomposition</CardTitle>
        <CardDescription>
          Breakout score{" "}
          <span className="font-mono font-semibold text-zinc-900 dark:text-zinc-100">
            {total !== null ? Math.round(total) : "—"}
          </span>{" "}
          — every point, accounted for.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-2.5">
        {ROWS.map((r) => {
          const v = breakdown[r.key];
          return (
            <div key={r.key} className="grid grid-cols-[130px_1fr_52px] items-center gap-3 text-sm">
              <span className="inline-flex items-center gap-1 text-zinc-600 dark:text-zinc-400">
                {r.label}
                <Tooltip content={r.hint}>
                  <Info className="h-3 w-3 cursor-help text-zinc-400" />
                </Tooltip>
              </span>
              <div className="h-2.5 overflow-hidden rounded-full bg-zinc-100 dark:bg-zinc-800">
                <div
                  className={cn("h-full rounded-full", BAR_COLORS[r.key])}
                  style={{ width: `${Math.max(0, Math.min(100, (v / max) * 100))}%` }}
                />
              </div>
              <span className="text-right font-mono font-semibold tabular-nums">
                +{Math.round(v)}
              </span>
            </div>
          );
        })}
        <p className="pt-1 text-xs text-zinc-500 dark:text-zinc-400">
          Components are robust-normalized (percentile / log / robust z-score) against the full
          corpus, so one outlier can&apos;t dominate. Deterministic — same snapshots, same score.
        </p>
      </CardContent>
    </Card>
  );
}
