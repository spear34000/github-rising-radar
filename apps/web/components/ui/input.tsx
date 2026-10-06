import * as React from "react";
import { cn } from "@/lib/utils";

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ className, label, id, ...props }, ref) => {
    const autoId = React.useId();
    const inputId = id ?? autoId;
    return (
      <div className="flex flex-col gap-1">
        {label && (
          <label htmlFor={inputId} className="text-xs font-medium text-zinc-500 dark:text-zinc-400">
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={cn(
            "h-9 rounded-lg border border-zinc-300 bg-white px-3 text-sm",
            "dark:border-zinc-700 dark:bg-zinc-900",
            "placeholder:text-zinc-400 focus:outline-none focus:ring-2 focus:ring-emerald-500",
            className,
          )}
          {...props}
        />
      </div>
    );
  },
);
Input.displayName = "Input";
