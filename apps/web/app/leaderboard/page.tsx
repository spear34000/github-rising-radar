"use client";

import * as React from "react";
import { Flame, Leaf, Rocket, Snowflake, Sparkles, TrendingUp } from "lucide-react";
import { getCategories, getRepos, getStats, ApiError } from "@/lib/api";
import type {
  CategoryCount,
  RadarStats,
  RepoCard,
  RepoListParams,
} from "@/lib/types";
import { DEFAULT_FILTERS, FilterBar, type FilterState } from "@/components/FilterBar";
import { RepoCardRow } from "@/components/RepoCard";
import { StatStrip } from "@/components/StatStrip";
import { EmptyState, ErrorState } from "@/components/EmptyState";
import { Button } from "@/components/ui/button";
import { Tabs } from "@/components/ui/tabs";
import { RepoCardSkeleton } from "@/components/ui/skeleton";

const TABS = [
  { value: "top", label: "Top Rising", icon: <TrendingUp className="h-4 w-4" /> },
  { value: "emerging", label: "Emerging", icon: <Leaf className="h-4 w-4" /> },
  { value: "breakout", label: "Breakout", icon: <Rocket className="h-4 w-4" /> },
  { value: "viral", label: "Viral", icon: <Flame className="h-4 w-4" /> },
  { value: "new", label: "New", icon: <Sparkles className="h-4 w-4" /> },
  { value: "cooling", label: "Cooling", icon: <Snowflake className="h-4 w-4" /> },
];

function tabToParams(tab: string, f: FilterState): RepoListParams {
  const base: RepoListParams = {
    category: f.category || undefined,
    language: f.language || undefined,
    min_stars: f.minStars ? Number(f.minStars) : undefined,
    max_age_days: f.maxAgeDays ? Number(f.maxAgeDays) : undefined,
    range: f.range,
    sort: f.sort,
    limit: 25,
  };
  switch (tab) {
    case "emerging":
      return { ...base, status: "emerging" };
    case "breakout":
      return { ...base, status: "breakout" };
    case "viral":
      return { ...base, status: "viral" };
    case "cooling":
      return { ...base, status: "cooling" };
    case "new":
      return { ...base, sort: "newest" };
    default:
      return { ...base, status: f.status || undefined };
  }
}

export default function LeaderboardPage() {
  const [tab, setTab] = React.useState("top");
  const [filters, setFilters] = React.useState<FilterState>(DEFAULT_FILTERS);
  const [items, setItems] = React.useState<RepoCard[]>([]);
  const [cursor, setCursor] = React.useState<string | null>(null);
  const [loading, setLoading] = React.useState(true);
  const [loadingMore, setLoadingMore] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [categories, setCategories] = React.useState<CategoryCount[]>([]);
  const [stats, setStats] = React.useState<RadarStats | null>(null);

  const paramsKey = React.useMemo(
    () => JSON.stringify(tabToParams(tab, filters)),
    [tab, filters],
  );

  const load = React.useCallback(
    async (append: boolean, params: RepoListParams, prevCursor: string | null) => {
      if (append) setLoadingMore(true);
      else setLoading(true);
      setError(null);
      try {
        const res = await getRepos({ ...params, cursor: prevCursor ?? undefined });
        setItems((old) => (append ? [...old, ...res.items] : res.items));
        setCursor(res.next_cursor);
      } catch (err) {
        setError(
          err instanceof ApiError
            ? `API returned ${err.status}. Is the backend running at the configured NEXT_PUBLIC_API_URL?`
            : "Failed to load repositories. Check your connection and try again.",
        );
      } finally {
        setLoading(false);
        setLoadingMore(false);
      }
    },
    [],
  );

  // Initial + filter/tab change
  React.useEffect(() => {
    const params = JSON.parse(paramsKey) as RepoListParams;
    setItems([]);
    setCursor(null);
    load(false, params, null);
  }, [paramsKey, load]);

  // Categories + stats once
  React.useEffect(() => {
    getCategories().then(setCategories).catch(() => {});
    getStats().then(setStats).catch(() => {});
  }, []);

  const onTab = (v: string) => {
    setTab(v);
    // Tabs are shortcuts: keep other filters, but reset status/sort conflicts.
    if (v === "new") setFilters((f) => ({ ...f, sort: "newest", status: "" }));
    else if (v === "top") setFilters((f) => ({ ...f, status: "", sort: "breakout_score" }));
    else setFilters((f) => ({ ...f, status: v }));
  };

  const onFilters = (f: FilterState) => {
    setFilters(f);
    // If the user manually changes status, detach the tab highlight.
    if (f.status !== tab && ["emerging", "breakout", "viral", "cooling"].includes(tab)) setTab("top");
    if (f.sort === "newest" && tab !== "new") setTab("new");
  };

  const retry = () => {
    const params = JSON.parse(paramsKey) as RepoListParams;
    load(false, params, null);
  };

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Leaderboard</h1>
          <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
            Not what&apos;s already trending — what&apos;s <em>starting</em> to rise, caught early.
          </p>
        </div>
        <Tabs items={TABS} value={tab} onChange={onTab} />
      </div>

      <StatStrip stats={stats} />

      <FilterBar filters={filters} onChange={onFilters} categories={categories} />

      {error ? (
        <ErrorState message={error} onRetry={retry} />
      ) : loading ? (
        <div className="space-y-3">
          {Array.from({ length: 6 }).map((_, i) => (
            <RepoCardSkeleton key={i} />
          ))}
        </div>
      ) : items.length === 0 ? (
        <EmptyState onRetry={retry} />
      ) : (
        <>
          <div className="space-y-3">
            {items.map((r) => (
              <RepoCardRow key={r.id} repo={r} />
            ))}
          </div>
          {loadingMore && (
            <div className="space-y-3">
              {Array.from({ length: 3 }).map((_, i) => (
                <RepoCardSkeleton key={i} />
              ))}
            </div>
          )}
          <div className="flex justify-center pt-2">
            {cursor ? (
              <Button
                variant="outline"
                disabled={loadingMore}
                onClick={() => {
                  const params = JSON.parse(paramsKey) as RepoListParams;
                  load(true, params, cursor);
                }}
              >
                {loadingMore ? "Loading…" : "Load more"}
              </Button>
            ) : (
              items.length > 0 && (
                <p className="text-xs text-zinc-400">You&apos;ve reached the end of this ranking.</p>
              )
            )}
          </div>
        </>
      )}
    </div>
  );
}
