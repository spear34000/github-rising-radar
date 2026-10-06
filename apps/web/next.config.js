/** @type {import('next').NextConfig} */
const isPages = process.env.GITHUB_PAGES === "true";
// For project pages (<user>.github.io/<repo>) set NEXT_PUBLIC_BASE_PATH=/<repo>
const basePath = process.env.NEXT_PUBLIC_BASE_PATH || "";

const nextConfig = {
  reactStrictMode: true,
  // Static export for GitHub Pages (<project>.github.io).
  // Run with: GITHUB_PAGES=true NEXT_PUBLIC_DEMO=true npm run build
  ...(isPages ? { output: "export", basePath, images: { unoptimized: true } } : { output: "standalone" }),
  // Trailing slash helps relative asset resolution on Pages.
  ...(isPages ? { trailingSlash: true } : {}),
};

module.exports = nextConfig;
