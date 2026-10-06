import type { RepoStatus } from "./types";

/** Minimal classnames joiner (no external deps). */
export function cn(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

/** 2841 -> "2,841" ; 12500 -> "12.5k" when compact. */
export function formatNumber(n: number | null | undefined, compact = false): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  if (compact && Math.abs(n) >= 10000) {
    const v = n / 1000;
    return `${v >= 100 ? Math.round(v) : v.toFixed(1).replace(/\.0$/, "")}k`;
  }
  return Math.round(n).toLocaleString("en-US");
}

export function formatSigned(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${formatNumber(n)}`;
}

export function formatPct(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  const sign = n > 0 ? "+" : "";
  return `${sign}${n.toFixed(digits)}%`;
}

/** stars/hour -> "28.4/h" */
export function formatVelocity(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const abs = Math.abs(v);
  const shown = abs >= 100 ? Math.round(v).toString() : v.toFixed(1);
  return `${shown}/h`;
}

export function formatAgeDays(days: number | null | undefined): string {
  if (days === null || days === undefined || Number.isNaN(days)) return "—";
  if (days < 1) return "<1 day";
  if (days < 30) return `${Math.round(days)} days`;
  if (days < 365) return `${(days / 30).toFixed(days < 90 ? 0 : 1)} mo`;
  return `${(days / 365).toFixed(1)} yr`;
}

export function timeAgo(iso: string | null | undefined): string {
  if (!iso) return "—";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return "—";
  const s = Math.max(0, Math.floor((Date.now() - then) / 1000));
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d ago`;
  const mo = Math.floor(d / 30);
  if (mo < 12) return `${mo}mo ago`;
  return `${Math.floor(mo / 12)}y ago`;
}

export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  });
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "UTC",
    hour12: false,
  });
}

export const STATUS_META: Record<
  RepoStatus,
  { label: string; dot: string; text: string; ring: string; bg: string }
> = {
  normal: {
    label: "Normal",
    dot: "bg-zinc-400",
    text: "text-zinc-500 dark:text-zinc-400",
    ring: "ring-zinc-300 dark:ring-zinc-700",
    bg: "bg-zinc-100 dark:bg-zinc-800",
  },
  emerging: {
    label: "Emerging",
    dot: "bg-sky-400",
    text: "text-sky-600 dark:text-sky-400",
    ring: "ring-sky-300 dark:ring-sky-800",
    bg: "bg-sky-100 dark:bg-sky-950",
  },
  rising: {
    label: "Rising",
    dot: "bg-emerald-400",
    text: "text-emerald-600 dark:text-emerald-400",
    ring: "ring-emerald-300 dark:ring-emerald-800",
    bg: "bg-emerald-100 dark:bg-emerald-950",
  },
  breakout: {
    label: "Breakout",
    dot: "bg-amber-400",
    text: "text-amber-600 dark:text-amber-400",
    ring: "ring-amber-300 dark:ring-amber-800",
    bg: "bg-amber-100 dark:bg-amber-950",
  },
  viral: {
    label: "Viral",
    dot: "bg-rose-500",
    text: "text-rose-600 dark:text-rose-400",
    ring: "ring-rose-300 dark:ring-rose-800",
    bg: "bg-rose-100 dark:bg-rose-950",
  },
  cooling: {
    label: "Cooling",
    dot: "bg-violet-400",
    text: "text-violet-600 dark:text-violet-400",
    ring: "ring-violet-300 dark:ring-violet-800",
    bg: "bg-violet-100 dark:bg-violet-950",
  },
};

export const HYPE_META = {
  low: { label: "Low", cls: "text-emerald-600 dark:text-emerald-400" },
  medium: { label: "Medium", cls: "text-amber-600 dark:text-amber-400" },
  high: { label: "High", cls: "text-rose-600 dark:text-rose-400" },
} as const;

export const LANGUAGE_COLORS: Record<string, string> = {
  TypeScript: "#3178c6",
  JavaScript: "#f1e05a",
  Python: "#3572A5",
  Go: "#00ADD8",
  Rust: "#dea584",
  Java: "#b07219",
  "C++": "#f34b7d",
  C: "#555555",
  Dart: "#00B4AB",
  Ruby: "#701516",
  Swift: "#F05138",
  Kotlin: "#A97BFF",
  Shell: "#89e051",
};
