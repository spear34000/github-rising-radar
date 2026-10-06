import { Boxes, Camera, Flame, Gauge } from "lucide-react";
import type { RadarStats } from "@/lib/types";
import { formatNumber } from "@/lib/utils";
import { Card } from "./ui/card";

export function StatStrip({ stats }: { stats: RadarStats | null }) {
  const items = [
    { icon: Boxes, label: "Tracked repos", value: stats ? formatNumber(stats.tracked_repos) : "—" },
    { icon: Camera, label: "Snapshots / 24h", value: stats ? formatNumber(stats.snapshots_24h) : "—" },
    { icon: Flame, label: "Detections / 7d", value: stats ? formatNumber(stats.detections_7d) : "—" },
    { icon: Gauge, label: "GitHub API calls / 24h", value: stats ? formatNumber(stats.api_calls_24h) : "—" },
  ];
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      {items.map((it) => (
        <Card key={it.label} className="flex items-center gap-3 p-4">
          <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-emerald-100 text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400">
            <it.icon className="h-4 w-4" />
          </span>
          <div>
            <div className="font-mono text-lg font-bold tabular-nums">{it.value}</div>
            <div className="text-xs text-zinc-500 dark:text-zinc-400">{it.label}</div>
          </div>
        </Card>
      ))}
    </div>
  );
}
