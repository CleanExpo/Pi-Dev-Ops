import type { NextConfig } from 'next';

const config: NextConfig = {
  // The brand-config is a workspace dep with .design.md / .motion.md / .scene.md files we read at runtime via fs.
  // Mark `three` and `yaml` as transpiled so server components can import them cleanly.
  transpilePackages: ['@unite-group/brand-config'],
  experimental: {
    // The preview canvas reads files at runtime, so disable Vercel build-time output tracing for these.
  },
};

export default config;
