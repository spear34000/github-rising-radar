/**
 * API client for the FastAPI backend (CONTRACT.md §4).
 *
 * Base URL: NEXT_PUBLIC_API_URL (default http://localhost:8000).
 * No secrets are used here — the browser never touches the GitHub token.
 *
 * When NEXT_PUBLIC_DEMO=true, all calls are served from the built-in
 * mock dataset (lib/demo.ts) and no network request is made.
 */
import type {
  AddRepoResponse,
  CategoryCount,
  RadarStats,
  RepoCard,
  RepoDetail,
  RepoListParams,
  RepoListResponse,
  HistoryResponse,
} from "./types";
import { isDemoMode, demoApi } from "./demo";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export class ApiError extends Error {
  status: number;
  body: string;
  constructor(status: number, body: string) {
    super(`API request failed (${status})`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
  });
  if (!res.ok) {
    let body = "";
    try {
      body = await res.text();
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, body);
  }
  return (await res.json()) as T;
}

function toQuery(params: RepoListParams): string {
  const q = new URLSearchParams();
  if (params.status) q.set("status", params.status);
  if (params.category) q.set("category", params.category);
  if (params.language) q.set("language", params.language);
  if (params.min_stars) q.set("min_stars", String(params.min_stars));
  if (params.max_age_days) q.set("max_age_days", String(params.max_age_days));
  if (params.sort) q.set("sort", params.sort);
  if (params.range) q.set("range", params.range);
  if (params.limit) q.set("limit", String(params.limit));
  if (params.cursor) q.set("cursor", params.cursor);
  const s = q.toString();
  return s ? `?${s}` : "";
}

export async function getRepos(
  params: RepoListParams = {},
): Promise<RepoListResponse> {
  if (isDemoMode()) return demoApi.getRepos(params);
  return req<RepoListResponse>(`/api/repos${toQuery(params)}`);
}

export async function getRepo(owner: string, name: string): Promise<RepoDetail> {
  if (isDemoMode()) return demoApi.getRepo(owner, name);
  return req<RepoDetail>(
    `/api/repos/${encodeURIComponent(owner)}/${encodeURIComponent(name)}`,
  );
}

export async function getHistory(
  id: string,
  range: "7d" | "30d" | "90d" | "all" = "30d",
): Promise<HistoryResponse> {
  if (isDemoMode()) return demoApi.getHistory(id, range);
  return req<HistoryResponse>(
    `/api/repos/${encodeURIComponent(id)}/history?range=${range}`,
  );
}

interface RankingApiResponse {
  bucket: string;
  ts: string | null;
  items: Array<{ rank: number; score: number; repo: RepoCard }>;
}

export async function getRankings(
  bucket = "all",
  limit = 50,
): Promise<RepoListResponse> {
  if (isDemoMode())
    return demoApi.getRepos({ sort: "breakout_score", limit });
  const res = await req<RankingApiResponse>(
    `/api/rankings?bucket=${encodeURIComponent(bucket)}&limit=${limit}`,
  );
  return { items: res.items.map((e) => e.repo), next_cursor: null };
}

export async function getCategories(): Promise<CategoryCount[]> {
  if (isDemoMode()) return demoApi.getCategories();
  return req<CategoryCount[]>("/api/categories");
}

export async function getStats(): Promise<RadarStats> {
  if (isDemoMode()) return demoApi.getStats();
  return req<RadarStats>("/api/stats");
}

export async function addRepo(fullName: string): Promise<AddRepoResponse> {
  if (isDemoMode()) return demoApi.addRepo(fullName);
  return req<AddRepoResponse>("/api/repos", {
    method: "POST",
    body: JSON.stringify({ full_name: fullName }),
  });
}
