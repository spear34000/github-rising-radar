import { AlertTriangle, ShieldCheck } from "lucide-react";
import type { HypeRisk } from "@/lib/types";
import { cn, HYPE_META } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "./ui/card";

/**
 * Hype risk panel — explicitly NOT a "star bot detector".
 * It measures how much the star growth is backed by real repository activity.
 */
export function HypeRiskPanel({
  level,
  reasons,
  organicScore,
}: {
  level: HypeRisk | null;
  reasons: string[];
  organicScore: number | null;
}) {
  if (!level) {
    return (
      <Card>
        <CardHeader>
          <CardTitle>Hype risk</CardTitle>
          <CardDescription>Insufficient history</CardDescription>
        </CardHeader>
      </Card>
    );
  }
  const meta = HYPE_META[level];
  const high = level === "high";
  return (
    <Card className={cn(high && "border-rose-200 dark:border-rose-900")}>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          {high ? <AlertTriangle className="h-4 w-4 text-rose-500" /> : <ShieldCheck className="h-4 w-4 text-emerald-500" />}
          Hype risk: <span className={meta.cls}>{meta.label}</span>
        </CardTitle>
        <CardDescription>
          Activity-backed growth, not a bot accusation. Organic score:{" "}
          <span className="font-mono font-semibold text-zinc-900 dark:text-zinc-100">
            {organicScore !== null ? `${Math.round(organicScore)}/100` : "—"}
          </span>
        </CardDescription>
      </CardHeader>
      <CardContent>
        {reasons.length > 0 ? (
          <ul className="space-y-1.5 text-sm">
            {reasons.map((r) => (
              <li key={r} className="flex items-start gap-2">
                <span className={cn("mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full", high ? "bg-rose-500" : "bg-emerald-500")} />
                <span className="text-zinc-600 dark:text-zinc-400">{r}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-zinc-500 dark:text-zinc-400">No suspicious patterns detected.</p>
        )}
        <p className="mt-3 text-xs text-zinc-500 dark:text-zinc-400">
          This panel never claims manipulation — it only shows whether the star curve is accompanied
          by forks, contributors, releases and other real activity.
        </p>
      </CardContent>
    </Card>
  );
}
