import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    include: ['test/**/*.test.{ts,mjs}'],
    testTimeout: 30000,
    hookTimeout: 30000,
  },
});
