"use client";

import Link from "next/link";
import { ExternalLink, GitFork, Star, TrendingUp } from "lucide-react";
import type { RepoCard } from "@/lib/types";
import {
  cn,
  formatAgeDays,
  formatNumber,
  formatPct,
  formatSigned,
  formatVelocity,
  LANGUAGE_COLORS,
  timeAgo,
} from "@/lib/utils";
import { ScoreBadge } from "./ScoreBadge";
import { Badge } from "./ui/badge";
import { Tooltip } from "./ui/tooltip";

export function RepoCardRow({ repo }: { repo: RepoCard }) {
  const href = `/repo/${repo.owner}/${repo.name}`;
  const langColor = repo.language ? LANGUAGE_COLORS[repo.language] ?? "#a1a1aa" : null;

  return (
    <Link
      href={href}
      className={cn(
        "group grid grid-cols-[1fr_auto] gap-4 rounded-xl border border-zinc-200 bg-white p-4 transition-colors",
        "hover:border-emerald-300 hover:shadow-md sm:p-5",
        "dark:border-zinc-800 dark:bg-zinc-900 dark:hover:border-emerald-800",
        "sm:grid-cols-[1fr_220px]",
      )}
    >
      <div className="min-w-0">
        <div className="flex flex-wrap items-center gap-2">
          <span className="truncate font-mono text-sm font-semibold text-zinc-900 group-hover:text-emerald-600 dark:text-zinc-100 dark:group-hover:text-emerald-400 sm:text-base">
            {repo.full_name}
          </span>
          <ScoreBadge status={repo.status} score={repo.breakout_score} size="sm" />
          {repo.insufficient_history && (
            <Tooltip content="Not enough snapshots yet to compute reliable velocity metrics.">
              <Badge variant="outline">thin history</Badge>
            </Tooltip>
          )}
        </div>

        {repo.description && (
          <p className="mt-1.5 line-clamp-2 text-sm text-zinc-600 dark:text-zinc-400">
            {repo.description}
          </p>
        )}

        <div className="mt-2.5 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-zinc-500 dark:text-zinc-400">
          {repo.language && (
            <span className="inline-flex items-center gap-1.5">
              <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: langColor! }} />
              {repo.language}
            </span>
          )}
          {repo.category.slice(0, 3).map((c) => (
            <Badge key={c} variant="secondary" className="px-1.5">
              {c}
            </Badge>
          ))}
          <span title={`Created ${repo.age_days.toFixed(0)} days ago`}>
            {formatAgeDays(repo.age_days)} old
          </span>
          <span className="hidden sm:inline">detected {timeAgo(repo.detected_at)}</span>
          <span
            role="link"
            tabIndex={0}
            onClick={(e) => {
              e.stopPropagation();
              window.open(repo.url, "_blank", "noreferrer");
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") window.open(repo.url, "_blank", "noreferrer");
            }}
            className="inline-flex cursor-pointer items-center gap-1 hover:text-zinc-900 dark:hover:text-zinc-100"
          >
            GitHub <ExternalLink className="h-3 w-3" />
          </span>
        </div>
      </div>

      <div className="flex flex-col items-end justify-center gap-1 border-l border-zinc-100 pl-4 text-right dark:border-zinc-800">
        <div className="font-mono text-2xl font-bold tabular-nums text-zinc-900 dark:text-zinc-100">
          {repo.breakout_score !== null ? Math.round(repo.breakout_score) : "—"}
        </div>
        <div className="text-[10px] uppercase tracking-wider text-zinc-400 dark:text-zinc-500">
          breakout
        </div>
        <div className="mt-1 space-y-1 font-mono text-xs tabular-nums text-zinc-500 dark:text-zinc-400">
          <div className="flex items-center justify-end gap-1">
            <Star className="h-3 w-3" />
            {formatNumber(repo.stars)}
            {repo.stars_24h_gain !== null && (
              <span className="text-emerald-600 dark:text-emerald-400">
                {formatSigned(repo.stars_24h_gain)}
              </span>
            )}
          </div>
          <div className="flex items-center justify-end gap-1">
            <TrendingUp className="h-3 w-3" />
            {repo.velocity_24h !== null ? formatVelocity(repo.velocity_24h) : "—"}
          </div>
          {repo.acceleration !== null && (
            <div className="text-zinc-400 dark:text-zinc-500">
              {formatPct(repo.acceleration)} accel
            </div>
          )}
        </div>
        <div className="mt-1 flex items-center justify-end gap-1 text-[11px] text-zinc-400 dark:text-zinc-500">
          <GitFork className="h-3 w-3" />
          {formatNumber(repo.forks)}
        </div>
      </div>
    </Link>
  );
}
