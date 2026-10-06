"use client";

import { RotateCcw } from "lucide-react";
import type { CategoryCount, SortKey, TimeRange } from "@/lib/types";
import { Button } from "./ui/button";
import { Input } from "./ui/input";
import { Select } from "./ui/select";

export interface FilterState {
  category: string;
  language: string;
  minStars: string;
  maxAgeDays: string;
  status: string;
  range: TimeRange;
  sort: SortKey;
}

export const DEFAULT_FILTERS: FilterState = {
  category: "",
  language: "",
  minStars: "",
  maxAgeDays: "",
  status: "",
  range: "24h",
  sort: "breakout_score",
};

export const LANGUAGES = [
  "TypeScript", "JavaScript", "Python", "Go", "Rust", "Java", "C++", "C",
  "Dart", "Ruby", "Swift", "Kotlin", "Shell",
];

const SORT_OPTIONS = [
  { value: "breakout_score", label: "Breakout Score" },
  { value: "growth_24h", label: "24h Growth" },
  { value: "acceleration", label: "Acceleration" },
  { value: "relative_growth", label: "Relative Growth" },
  { value: "newest", label: "Newest" },
];

const AGE_OPTIONS = [
  { value: "", label: "Any age" },
  { value: "7", label: "< 7 days" },
  { value: "30", label: "< 30 days" },
  { value: "90", label: "< 90 days" },
  { value: "365", label: "< 1 year" },
];

const STATUS_OPTIONS = [
  { value: "", label: "All statuses" },
  { value: "normal", label: "Normal" },
  { value: "emerging", label: "Emerging" },
  { value: "rising", label: "Rising" },
  { value: "breakout", label: "Breakout" },
  { value: "viral", label: "Viral" },
  { value: "cooling", label: "Cooling" },
];

export function FilterBar({
  filters,
  onChange,
  categories,
}: {
  filters: FilterState;
  onChange: (f: FilterState) => void;
  categories: CategoryCount[];
}) {
  const set = (patch: Partial<FilterState>) => onChange({ ...filters, ...patch });
  const isDefault = JSON.stringify(filters) === JSON.stringify(DEFAULT_FILTERS);

  return (
    <div className="rounded-xl border border-zinc-200 bg-white p-4 dark:border-zinc-800 dark:bg-zinc-900">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4 lg:grid-cols-8">
        <Select
          label="Category"
          value={filters.category}
          onChange={(e) => set({ category: e.target.value })}
          options={[{ value: "", label: "All" }, ...categories.map((c) => ({ value: c.name, label: `${c.name} (${c.count})` }))]}
        />
        <Select
          label="Language"
          value={filters.language}
          onChange={(e) => set({ language: e.target.value })}
          options={[{ value: "", label: "All" }, ...LANGUAGES.map((l) => ({ value: l, label: l }))]}
        />
        <Input
          label="Min stars"
          type="number"
          min={0}
          placeholder="0"
          value={filters.minStars}
          onChange={(e) => set({ minStars: e.target.value })}
        />
        <Select
          label="Repo age"
          value={filters.maxAgeDays}
          onChange={(e) => set({ maxAgeDays: e.target.value })}
          options={AGE_OPTIONS}
        />
        <Select
          label="Status"
          value={filters.status}
          onChange={(e) => set({ status: e.target.value })}
          options={STATUS_OPTIONS}
        />
        <Select
          label="Time range"
          value={filters.range}
          onChange={(e) => set({ range: e.target.value as TimeRange })}
          options={[
            { value: "24h", label: "24h" },
            { value: "7d", label: "7d" },
          ]}
        />
        <Select
          label="Sort by"
          value={filters.sort}
          onChange={(e) => set({ sort: e.target.value as SortKey })}
          options={SORT_OPTIONS}
        />
        <div className="flex items-end">
          <Button
            variant="ghost"
            size="sm"
            onClick={() => onChange(DEFAULT_FILTERS)}
            disabled={isDefault}
            className="w-full"
          >
            <RotateCcw className="h-3.5 w-3.5" /> Reset
          </Button>
        </div>
      </div>
    </div>
  );
}
