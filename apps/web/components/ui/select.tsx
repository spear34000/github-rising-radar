import * as React from "react";
import { cn } from "@/lib/utils";

export interface SelectOption {
  value: string;
  label: string;
}

export function Select({
  className,
  options,
  label,
  ...props
}: React.SelectHTMLAttributes<HTMLSelectElement> & {
  options: SelectOption[];
  label?: string;
}) {
  const id = React.useId();
  return (
    <div className="flex flex-col gap-1">
      {label && (
        <label htmlFor={id} className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
          {label}
        </label>
      )}
      <select
        id={id}
        className={cn(
          "h-9 rounded-lg border border-zinc-300 bg-white px-2.5 text-sm",
          "dark:border-zinc-700 dark:bg-zinc-900",
          "focus:outline-none focus:ring-2 focus:ring-emerald-500",
          className,
        )}
        {...props}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}
