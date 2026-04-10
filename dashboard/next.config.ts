// next.config.ts — Next.js configuration
// CSP is generated per-request with a nonce in middleware.ts (RA-518).
// Static security headers are set here; Content-Security-Policy is omitted.
import type { NextConfig } from "next";

// RA-526 — Fail fast at build/startup if critical env vars are missing in production
if (process.env.NODE_ENV === "production") {
  const required = ["PI_CEO_URL", "PI_CEO_PASSWORD"] as const;
  const missing = required.filter((k) => !process.env[k]);
  if (missing.length) {
    throw new Error(
      `Missing required environment variables: ${missing.join(", ")}\n` +
      `Set these in Vercel project settings or dashboard/.env.local`
    );
  }
}

const nextConfig: NextConfig = {
  async headers() {
    return [
      {
        source: "/(.*)",
        headers: [
          { key: "X-Frame-Options", value: "DENY" },
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
        ],
      },
    ];
  },
};

export default nextConfig;
