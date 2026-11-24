import { fileURLToPath } from "node:url";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Keep dev servers from writing framework-managed instructions into the worktree.
  agentRules: false,
  // Self-contained server bundle for the slim production image (see Dockerfile).
  output: "standalone",
  // Trace files from the monorepo root so workspace packages are included.
  outputFileTracingRoot: fileURLToPath(new URL("../..", import.meta.url)),
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  },
};

export default nextConfig;
