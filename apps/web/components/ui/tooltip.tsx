"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

/** Lightweight CSS-only tooltip (no positioning library needed). */
export function Tooltip({
  content,
  children,
  className,
}: {
  content: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  return (
    <span className={cn("group relative inline-flex", className)}>
      {children}
      <span
        role="tooltip"
        className={cn(
          "pointer-events-none absolute bottom-full left-1/2 z-50 mb-2 w-max max-w-xs -translate-x-1/2",
          "rounded-lg border border-zinc-200 bg-white px-3 py-2 text-xs shadow-lg",
          "dark:border-zinc-700 dark:bg-zinc-900",
          "opacity-0 transition-opacity group-hover:opacity-100 group-focus-within:opacity-100",
        )}
      >
        {content}
      </span>
    </span>
  );
}
