import DetailClient from "./DetailClient";

/**
 * Static export (GitHub Pages) pre-renders detail pages for the demo dataset.
 * In server mode (standalone output) dynamic params still work at runtime.
 */
export function generateStaticParams() {
  if (process.env.GITHUB_PAGES !== "true") return [];
  // Real repos from lib/demo.ts — must match SPECS owner/name.
  const specs: Array<[string, string]> = [
    ["NandhaKishorM", "laya"],
    ["storytold", "photocraft"],
    ["Niko1221", "Strata"],
    ["browser-use", "jev-ultrafast"],
    ["KKKKhazix", "AIHOT"],
    ["jev-chat", "jev-chat-jarvis"],
    ["robbietilton", "Compositor"],
    ["cdyforever", "how-to-live-better"],
    ["zai-org", "ZCode"],
    ["shihabal3amri", "DiPlay"],
    ["jaredpalmer", "kev"],
    ["yetone", "magpie"],
    ["mizorewww", "laya-mlx"],
    ["tamaratran", "fast-jev-compaction"],
    ["Mak5er", "AirCard"],
  ];
  return specs.map(([owner, name]) => ({ owner, name }));
}

export default function RepoDetailPage({
  params,
}: {
  params: { owner: string; name: string };
}) {
  return <DetailClient owner={params.owner} name={params.name} />;
}
