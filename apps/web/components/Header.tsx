"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Activity, GitCompareArrows, House, Plus, Radar } from "lucide-react";
import { cn } from "@/lib/utils";
import { ThemeToggle } from "./ThemeToggle";
import { Button } from "./ui/button";
import { AddRepoModal } from "./AddRepoModal";
import * as React from "react";

const NAV = [
  { href: "/", label: "Home", icon: House },
  { href: "/leaderboard", label: "Leaderboard", icon: Activity },
  { href: "/compare", label: "Compare", icon: GitCompareArrows },
];

export function Header() {
  const pathname = usePathname();
  const [modalOpen, setModalOpen] = React.useState(false);

  return (
    <header className="sticky top-0 z-40 border-b border-zinc-200 bg-white/80 backdrop-blur dark:border-zinc-800 dark:bg-zinc-950/80">
      <div className="mx-auto flex h-14 max-w-7xl items-center gap-4 px-4 sm:px-6">
        <Link href="/" className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-emerald-500 text-zinc-950">
            <Radar className="h-5 w-5" />
          </span>
          <span className="text-sm font-bold tracking-tight sm:text-base">
            Rising Radar
            <span className="ml-2 hidden rounded bg-zinc-100 px-1.5 py-0.5 text-[10px] font-medium uppercase text-zinc-500 dark:bg-zinc-800 dark:text-zinc-400 sm:inline">
              beta
            </span>
          </span>
        </Link>

        <nav className="flex items-center gap-1">
          {NAV.map((n) => {
            const active = n.href === "/" ? pathname === "/" : pathname.startsWith(n.href);
            return (
              <Link
                key={n.href}
                href={n.href}
                className={cn(
                  "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-sm font-medium transition-colors",
                  active
                    ? "bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100"
                    : "text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100",
                )}
              >
                <n.icon className="h-4 w-4" />
                <span className="hidden sm:inline">{n.label}</span>
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto flex items-center gap-1">
          <Button variant="outline" size="sm" onClick={() => setModalOpen(true)}>
            <Plus className="h-4 w-4" />
            <span className="hidden sm:inline">Track repo</span>
          </Button>
          <ThemeToggle />
        </div>
      </div>
      <AddRepoModal open={modalOpen} onClose={() => setModalOpen(false)} />
    </header>
  );
}
