"use client";

import * as React from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "./ui/card";
import { formatNumber } from "@/lib/utils";

export interface ChartPoint {
  t: number; // epoch ms
  stars?: number | null;
  forks?: number | null;
  velocity?: number | null; // stars/hour
  score?: number | null;
}

export interface ChartEvent {
  t: number;
  label: string;
  color: string;
}

const EVENT_COLORS: Record<string, string> = {
  detected: "#a1a1aa",
  emerging: "#38bdf8",
  rising: "#34d399",
  breakout: "#fbbf24",
  viral: "#fb7185",
  release: "#a78bfa",
};

function shortDate(t: number): string {
  return new Date(t).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "UTC" });
}

function ChartTooltip({ active, payload, label, formatter }: any) {
  if (!active || !payload?.length) return null;
  return (
    <div className="rounded-lg border border-zinc-200 bg-white px-3 py-2 text-xs shadow-lg dark:border-zinc-700 dark:bg-zinc-900">
      <div className="mb-1 font-medium text-zinc-500 dark:text-zinc-400">
        {new Date(label).toLocaleString("en-US", {
          month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
          timeZone: "UTC", hour12: false,
        })}
      </div>
      {payload.map((p: any) => (
        <div key={String(p.dataKey)} className="flex items-center justify-between gap-6 py-0.5">
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full" style={{ backgroundColor: p.color ?? p.stroke }} />
            {p.name}
          </span>
          <span className="font-mono font-semibold tabular-nums">
            {formatter ? formatter(p.value) : formatNumber(p.value)}
          </span>
        </div>
      ))}
    </div>
  );
}

function EventMarkers({ events }: { events: ChartEvent[] }) {
  return (
    <>
      {events.map((e, i) => (
        <ReferenceLine
          key={`${e.t}-${i}`}
          x={e.t}
          stroke={e.color || EVENT_COLORS[e.label.toLowerCase()] || "#a1a1aa"}
          strokeDasharray="4 3"
          label={{
            value: e.label,
            position: "insideTopLeft",
            fontSize: 10,
            fill: "#71717a",
          }}
        />
      ))}
    </>
  );
}

function ChartShell({
  title,
  description,
  children,
  height = 260,
}: {
  title: string;
  description?: string;
  children: React.ReactNode;
  height?: number;
}) {
  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm">{title}</CardTitle>
        {description && <CardDescription>{description}</CardDescription>}
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={height}>
          {children as React.ReactElement}
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}

const axisProps = {
  tickLine: false,
  axisLine: false,
  tick: { fontSize: 11, fill: "#71717a" },
} as const;

export function StarsChart({ data, events }: { data: ChartPoint[]; events: ChartEvent[] }) {
  return (
    <ChartShell title="Stars over time" description="Cumulative star count from snapshots">
      <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="starsGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#10b981" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#10b981" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" opacity={0.5} vertical={false} />
        <XAxis dataKey="t" tickFormatter={shortDate} {...axisProps} minTickGap={40} />
        <YAxis tickFormatter={(v: number) => formatNumber(v, true)} {...axisProps} width={48} />
        <Tooltip content={<ChartTooltip />} cursor={{ stroke: "#52525b", strokeDasharray: "3 3" }} />
        <EventMarkers events={events} />
        <Area
          type="monotone"
          dataKey="stars"
          name="Stars"
          stroke="#10b981"
          strokeWidth={2}
          fill="url(#starsGrad)"
          dot={false}
        />
      </AreaChart>
    </ChartShell>
  );
}

export function VelocityChart({ data, events }: { data: ChartPoint[]; events: ChartEvent[] }) {
  return (
    <ChartShell title="Star velocity" description="Stars per hour, derived from snapshot deltas">
      <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" opacity={0.5} vertical={false} />
        <XAxis dataKey="t" tickFormatter={shortDate} {...axisProps} minTickGap={40} />
        <YAxis tickFormatter={(v: number) => `${v}`} {...axisProps} width={40} />
        <Tooltip
          content={<ChartTooltip formatter={(v: number) => `${v.toFixed(1)}/h`} />}
          cursor={{ stroke: "#52525b", strokeDasharray: "3 3" }}
        />
        <EventMarkers events={events} />
        <Line
          type="monotone"
          dataKey="velocity"
          name="Velocity"
          stroke="#38bdf8"
          strokeWidth={2}
          dot={false}
          connectNulls
        />
      </LineChart>
    </ChartShell>
  );
}

export function ScoreChart({ data, events }: { data: ChartPoint[]; events: ChartEvent[] }) {
  return (
    <ChartShell title="Breakout score" description="0–100, deterministic scoring v1">
      <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" opacity={0.5} vertical={false} />
        <XAxis dataKey="t" tickFormatter={shortDate} {...axisProps} minTickGap={40} />
        <YAxis domain={[0, 100]} {...axisProps} width={36} />
        <Tooltip content={<ChartTooltip formatter={(v: number) => v.toFixed(0)} />} cursor={{ stroke: "#52525b", strokeDasharray: "3 3" }} />
        <EventMarkers events={events} />
        <ReferenceLine y={85} stroke="#fb7185" strokeDasharray="4 3" label={{ value: "viral", fontSize: 10, fill: "#71717a", position: "insideTopRight" }} />
        <ReferenceLine y={70} stroke="#fbbf24" strokeDasharray="4 3" label={{ value: "breakout", fontSize: 10, fill: "#71717a", position: "insideTopRight" }} />
        <Line
          type="monotone"
          dataKey="score"
          name="Score"
          stroke="#f59e0b"
          strokeWidth={2}
          dot={false}
          connectNulls
        />
      </LineChart>
    </ChartShell>
  );
}

export function ForksChart({ data }: { data: ChartPoint[] }) {
  return (
    <ChartShell title="Forks over time" description="Fork count from snapshots">
      <AreaChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id="forksGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#a78bfa" stopOpacity={0.35} />
            <stop offset="100%" stopColor="#a78bfa" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" opacity={0.5} vertical={false} />
        <XAxis dataKey="t" tickFormatter={shortDate} {...axisProps} minTickGap={40} />
        <YAxis tickFormatter={(v: number) => formatNumber(v, true)} {...axisProps} width={48} />
        <Tooltip content={<ChartTooltip />} cursor={{ stroke: "#52525b", strokeDasharray: "3 3" }} />
        <Area
          type="monotone"
          dataKey="forks"
          name="Forks"
          stroke="#a78bfa"
          strokeWidth={2}
          fill="url(#forksGrad)"
          dot={false}
        />
      </AreaChart>
    </ChartShell>
  );
}

const COMPARE_COLORS = ["#10b981", "#38bdf8", "#f59e0b", "#fb7185", "#a78bfa"];

export interface CompareSeries {
  name: string;
  points: Array<{ t: number; stars: number }>;
}

export function CompareStarsChart({
  series,
  normalized,
}: {
  series: CompareSeries[];
  normalized: boolean;
}) {
  const allT = React.useMemo(() => {
    const set = new Set<number>();
    series.forEach((s) => s.points.forEach((p) => set.add(p.t)));
    return [...set].sort((a, b) => a - b);
  }, [series]);

  const data = React.useMemo(() => {
    const maxBy: Record<string, number> = {};
    series.forEach((s) => {
      maxBy[s.name] = Math.max(1, ...s.points.map((p) => p.stars));
    });
    const byName: Record<string, Map<number, number>> = {};
    series.forEach((s) => {
      byName[s.name] = new Map(s.points.map((p) => [p.t, p.stars]));
    });
    return allT.map((t) => {
      const row: Record<string, number | null> = { t };
      series.forEach((s) => {
        const v = byName[s.name].get(t) ?? null;
        row[s.name] = v === null ? null : normalized ? (v / maxBy[s.name]) * 100 : v;
      });
      return row;
    });
  }, [allT, series, normalized]);

  return (
    <ResponsiveContainer width="100%" height={320}>
      <LineChart data={data} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="#27272a" opacity={0.5} vertical={false} />
        <XAxis dataKey="t" tickFormatter={shortDate} {...axisProps} minTickGap={48} />
        <YAxis
          tickFormatter={(v: number) => (normalized ? `${v.toFixed(0)}%` : formatNumber(v, true))}
          {...axisProps}
          width={52}
        />
        <Tooltip
          content={
            <ChartTooltip
              formatter={(v: number) => (normalized ? `${v.toFixed(1)}% of peak` : formatNumber(v))}
            />
          }
          cursor={{ stroke: "#52525b", strokeDasharray: "3 3" }}
        />
        {series.map((s, i) => (
          <Line
            key={s.name}
            type="monotone"
            dataKey={s.name}
            name={s.name}
            stroke={COMPARE_COLORS[i % COMPARE_COLORS.length]}
            strokeWidth={2}
            dot={false}
            connectNulls
          />
        ))}
      </LineChart>
    </ResponsiveContainer>
  );
}
