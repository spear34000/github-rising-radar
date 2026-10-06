import type { Metadata } from "next";
import { DemoBanner } from "@/components/AddRepoModal";
import { Header } from "@/components/Header";
import "./globals.css";

export const metadata: Metadata = {
  title: {
    default: "GitHub Rising Radar",
    template: "%s · Rising Radar",
  },
  description:
    "Catch GitHub repositories at the moment they start rising — breakout detection, star velocity and acceleration, before they trend.",
};

// Apply the saved theme (default dark) before first paint to avoid a flash.
const themeScript = `(function(){try{var t=localStorage.getItem('radar-theme');document.documentElement.classList.toggle('dark',t!=='light')}catch(e){document.documentElement.classList.add('dark')}})();`;

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark" suppressHydrationWarning>
      <script dangerouslySetInnerHTML={{ __html: themeScript }} />
      <body>
        <DemoBanner />
        <Header />
        <main className="mx-auto max-w-7xl px-4 pb-20 pt-6 sm:px-6">{children}</main>
        <footer className="border-t border-zinc-200 dark:border-zinc-800">
          <div className="mx-auto flex max-w-7xl flex-col gap-2 px-4 py-6 text-xs text-zinc-500 dark:text-zinc-400 sm:flex-row sm:items-center sm:justify-between sm:px-6">
            <p>
              <span className="font-semibold text-zinc-700 dark:text-zinc-300">Rising Radar</span>{" "}
              — breakout detection for GitHub, not a trending clone.
            </p>
            <p className="font-mono">
              scores are deterministic · timestamps UTC ·{" "}
              <a
                href="https://github.com"
                target="_blank"
                rel="noreferrer"
                className="underline hover:text-zinc-700 dark:hover:text-zinc-200"
              >
                data via GitHub API
              </a>
            </p>
          </div>
        </footer>
      </body>
    </html>
  );
}
