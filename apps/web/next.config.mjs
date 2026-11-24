import { fileURLToPath } from "node:url";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Self-contained server bundle for the slim production image (see Dockerfile).
  output: "standalone",
  // Trace files from the monorepo root so workspace packages are included.
  outputFileTracingRoot: fileURLToPath(new URL("../..", import.meta.url)),
  env: {
    NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000",
  },
};

export default nextConfig;
