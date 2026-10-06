import { Quote, Sparkles } from "lucide-react";
import type { RepoDetail } from "@/lib/types";
import { formatNumber, formatPct, formatSigned, formatVelocity } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "./ui/card";
import { Badge } from "./ui/badge";

/**
 * Deterministic "Why is this rising?" summary.
 * Every sentence is grounded in actual metrics/events — no LLM hallucination.
 */
export function WhyRising({ repo }: { repo: RepoDetail }) {
  if (!repo.why_rising && repo.insufficient_history) {
    return (
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4" /> Why is this rising?
          </CardTitle>
        </CardHeader>
        <CardContent>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">Insufficient history</p>
        </CardContent>
      </Card>
    );
  }

  const chips: string[] = [];
  if (repo.stars_24h_gain !== null)
    chips.push(`${formatSigned(repo.stars_24h_gain)} stars / 24h`);
  if (repo.velocity_24h !== null) chips.push(`velocity ${formatVelocity(repo.velocity_24h)}`);
  if (repo.acceleration !== null) chips.push(`acceleration ${formatPct(repo.acceleration)}`);
  if (repo.organic_score !== null) chips.push(`organic ${Math.round(repo.organic_score)}/100`);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Sparkles className="h-4 w-4" /> Why is this rising?
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-3">
          <Quote className="h-4 w-4 shrink-0 rotate-180 text-emerald-500" />
          <p className="text-sm leading-relaxed">
            {repo.why_rising ?? "Not enough signal yet to explain this movement."}
          </p>
        </div>
        {chips.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {chips.map((c) => (
              <Badge key={c} variant="secondary" className="font-mono">
                {c}
              </Badge>
            ))}
          </div>
        )}
        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          Generated deterministically from snapshot metrics and detected events — no language model
          involved, so nothing here is invented.
        </p>
      </CardContent>
    </Card>
  );
}

/** "Before it was cool" — proof Radar caught it early. */
export function BeforeCool({ repo }: { repo: RepoDetail }) {
  const d = repo.detections;
  if (!d) return null;

  const firstMajor = d.first_viral_at ?? d.first_breakout_at ?? d.first_rising_at ?? d.first_emerging_at;
  const daysBefore = firstMajor
    ? Math.max(0, Math.round((new Date(firstMajor).getTime() - new Date(d.first_detected_at).getTime()) / 86_400_000))
    : null;
  const growthPct =
    d.stars_at_detection > 0 ? (d.growth_since_detection / d.stars_at_detection) * 100 : null;

  return (
    <Card className="border-emerald-200 dark:border-emerald-900">
      <CardHeader>
        <CardTitle>Before it was cool</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div>
            <div className="text-xs text-zinc-500 dark:text-zinc-400">Radar first detected</div>
            <div className="mt-1 font-mono text-xl font-bold tabular-nums">
              {formatNumber(d.stars_at_detection)}
            </div>
            <div className="text-xs text-zinc-500 dark:text-zinc-400">stars</div>
          </div>
          <div>
            <div className="text-xs text-zinc-500 dark:text-zinc-400">Current</div>
            <div className="mt-1 font-mono text-xl font-bold tabular-nums text-emerald-600 dark:text-emerald-400">
              {formatNumber(repo.stars)}
            </div>
            <div className="text-xs text-zinc-500 dark:text-zinc-400">stars</div>
          </div>
          <div>
            <div className="text-xs text-zinc-500 dark:text-zinc-400">Growth since detection</div>
            <div className="mt-1 font-mono text-xl font-bold tabular-nums">
              {formatSigned(d.growth_since_detection)}
            </div>
            <div className="text-xs text-zinc-500 dark:text-zinc-400">
              {growthPct !== null ? formatPct(growthPct) : "—"}
            </div>
          </div>
          <div>
            <div className="text-xs text-zinc-500 dark:text-zinc-400">Early by</div>
            <div className="mt-1 font-mono text-xl font-bold tabular-nums">
              {daysBefore !== null ? `${daysBefore}d` : "—"}
            </div>
            <div className="text-xs text-zinc-500 dark:text-zinc-400">before major breakout</div>
          </div>
        </div>
        <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
          Detection records are append-only — they are never rewritten when the scoring formula
          changes, so this is verifiable proof of early detection.
        </p>
      </CardContent>
    </Card>
  );
}
