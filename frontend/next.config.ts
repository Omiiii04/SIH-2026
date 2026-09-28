import type { NextConfig } from "next";

// Server-side only — never sent to the browser.
// LAN users hit Next.js at :3000; Next.js server forwards to FastAPI.
const ORCHESTRATOR_URL =
  process.env.ORCHESTRATOR_URL ?? "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${ORCHESTRATOR_URL}/api/:path*`,
      },
      {
        source: "/health",
        destination: `${ORCHESTRATOR_URL}/health`,
      },
      {
        source: "/health/:path*",
        destination: `${ORCHESTRATOR_URL}/health/:path*`,
      },
    ];
  },
};

export default nextConfig;
