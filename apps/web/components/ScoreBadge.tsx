import { cn, STATUS_META } from "@/lib/utils";
import type { RepoStatus } from "@/lib/types";

/** Status pill with the score, e.g. "🔥 BREAKOUT 92". */
export function ScoreBadge({
  status,
  score,
  size = "md",
}: {
  status: RepoStatus;
  score: number | null;
  size?: "sm" | "md" | "lg";
}) {
  const meta = STATUS_META[status] ?? STATUS_META.normal;
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full font-semibold ring-1",
        meta.bg,
        meta.ring,
        size === "sm" && "px-2 py-0.5 text-[11px]",
        size === "md" && "px-2.5 py-1 text-xs",
        size === "lg" && "px-3.5 py-1.5 text-sm",
      )}
    >
      <span className={cn("h-1.5 w-1.5 rounded-full", meta.dot)} />
      <span className={meta.text}>{meta.label.toUpperCase()}</span>
      <span className="font-mono tabular-nums text-zinc-900 dark:text-zinc-100">
        {score === null || Number.isNaN(score) ? "—" : Math.round(score)}
      </span>
    </span>
  );
}

/** Compact 0-100 score bar with label. */
export function ScoreMeter({
  value,
  label,
  hint,
}: {
  value: number | null;
  label: string;
  hint?: string;
}) {
  const v = value === null || Number.isNaN(value) ? 0 : Math.max(0, Math.min(100, value));
  const color =
    v >= 85 ? "bg-rose-500" : v >= 70 ? "bg-amber-500" : v >= 50 ? "bg-emerald-500" : v >= 30 ? "bg-sky-500" : "bg-zinc-400";
  return (
    <div title={hint}>
      <div className="flex items-baseline justify-between text-xs">
        <span className="font-medium text-zinc-500 dark:text-zinc-400">{label}</span>
        <span className="font-mono font-semibold tabular-nums">
          {value === null ? "—" : Math.round(value)}
        </span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
        <div className={cn("h-full rounded-full transition-all", color)} style={{ width: `${v}%` }} />
      </div>
    </div>
  );
}
