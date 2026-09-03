import type { NextConfig } from 'next';

/** Static export — this is a marketing site with no server-side work.
 *  `out/` deploys to any static host and keeps the CSP tight. */
const nextConfig: NextConfig = {
  output: 'export',
  trailingSlash: true,
  images: { unoptimized: true },
  reactStrictMode: true,
};

export default nextConfig;
