import { SearchX, WifiOff } from "lucide-react";
import { Button } from "./ui/button";

export function EmptyState({
  title = "No repositories found",
  hint = "Try widening the filters or check back later — the worker discovers new candidates continuously.",
  onRetry,
}: {
  title?: string;
  hint?: string;
  onRetry?: () => void;
}) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-dashed border-zinc-300 py-16 text-center dark:border-zinc-700">
      <SearchX className="h-8 w-8 text-zinc-400" />
      <p className="font-medium">{title}</p>
      <p className="max-w-md text-sm text-zinc-500 dark:text-zinc-400">{hint}</p>
      {onRetry && (
        <Button variant="outline" size="sm" onClick={onRetry}>
          Retry
        </Button>
      )}
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-xl border border-rose-200 bg-rose-50 py-16 text-center dark:border-rose-900 dark:bg-rose-950/30">
      <WifiOff className="h-8 w-8 text-rose-400" />
      <p className="font-medium">Couldn&apos;t load data</p>
      <p className="max-w-md text-sm text-zinc-500 dark:text-zinc-400">{message}</p>
      <Button variant="outline" size="sm" onClick={onRetry}>
        Try again
      </Button>
    </div>
  );
}
