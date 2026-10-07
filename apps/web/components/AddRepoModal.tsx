"use client";

import * as React from "react";
import Link from "next/link";
import { FlaskConical, Loader2, X } from "lucide-react";
import { addRepo, ApiError } from "@/lib/api";
import { isDemoMode } from "@/lib/demo";
import { Button } from "./ui/button";
import { Input } from "./ui/input";

export function AddRepoModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [value, setValue] = React.useState("");
  const [state, setState] = React.useState<"idle" | "loading" | "done" | "error">("idle");
  const [message, setMessage] = React.useState("");

  React.useEffect(() => {
    if (open) {
      setValue("");
      setState("idle");
      setMessage("");
    }
  }, [open ]);

  if (!open) return null;

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    const fullName = value.trim();
    if (!/^[\w.-]+\/[\w.-]+$/.test(fullName)) {
      setState("error");
      setMessage("Enter a repository as owner/name.");
      return;
    }
    setState("loading");
    try {
      const res = await addRepo(fullName);
      setState("done");
      setMessage(
        isDemoMode()
          ? `Demo mode: ${fullName} is already in the mock dataset.`
          : `Queued for tracking (job ${res.job_id}). Snapshots will appear shortly.`,
      );
    } catch (err) {
      setState("error");
      setMessage(err instanceof ApiError ? `Failed (${err.status}). Is the API running?` : "Failed to queue repository.");
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-black/50" onClick={onClose} />
      <div className="relative w-full max-w-md rounded-xl border border-zinc-200 bg-white p-6 shadow-xl dark:border-zinc-800 dark:bg-zinc-900">
        <button
          onClick={onClose}
          aria-label="Close"
          className="absolute right-4 top-4 text-zinc-400 hover:text-zinc-600 dark:hover:text-zinc-200"
        >
          <X className="h-4 w-4" />
        </button>
        <h2 className="text-lg font-semibold">Track a repository</h2>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Radar will start collecting snapshots and scoring it.
        </p>
        <form onSubmit={submit} className="mt-4 space-y-3">
          <Input
            label="Repository"
            placeholder="owner/name"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            autoFocus
          />
          {message && (
            <p className={`text-sm ${state === "error" ? "text-rose-500" : "text-emerald-600 dark:text-emerald-400"}`}>
              {message}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="ghost" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={state === "loading"}>
              {state === "loading" && <Loader2 className="h-4 w-4 animate-spin" />}
              Start tracking
            </Button>
          </div>
        </form>
      </div>
    </div>
  );
}

export function DemoBanner() {
  if (!isDemoMode()) return null;
  return (
    <div className="sticky top-0 z-50 flex items-center justify-center gap-2 bg-emerald-500 px-4 py-1.5 text-xs font-bold uppercase tracking-widest text-zinc-950">
      <FlaskConical className="h-3.5 w-3.5" />
      Real GitHub data · snapshot 2026-10-07
    </div>
  );
}

export function DemoNotice() {
  return (
    <p className="text-xs text-zinc-400">
      Showing real GitHub repositories (snapshot 2026-10-07). Scores from stars/day velocity.
    </p>
  );
}
