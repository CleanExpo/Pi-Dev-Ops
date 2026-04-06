import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow the Vercel-hosted UI to call the local FastAPI
  // All fetch calls are client-side so this only applies to SSR/API routes
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
        ],
      },
    ];
  },
};

export default nextConfig;
