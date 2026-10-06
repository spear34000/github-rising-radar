import DetailClient from "./DetailClient";

/**
 * Static export (GitHub Pages) pre-renders detail pages for the demo dataset.
 * In server mode (standalone output) dynamic params still work at runtime.
 */
export function generateStaticParams() {
  if (process.env.GITHUB_PAGES !== "true") return [];
  // Demo repos from lib/demo.ts — must match SPECS owner/name.
  const specs: Array<[string, string]> = [
    ["neuralforge", "tinygrad-turbo"],
    ["quantumlabs", "agent-swarm"],
    ["bytecraft", "llm-gateway"],
    ["secops", "honeyscan"],
    ["datadive", "vectorlite"],
    ["webworks", "htmx-plus"],
    ["mobkit", "flutter-nova"],
    ["gamedev", "rogue-engine"],
    ["infraops", "k8s-cost"],
    ["researcher", "paper-qa"],
    ["devtools", "git-bisect-ui"],
    ["hardlab", "riscv-sim"],
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
