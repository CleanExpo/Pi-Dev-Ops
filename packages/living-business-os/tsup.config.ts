import { defineConfig } from 'tsup';

// --out-dir on the command line overrides outDir (the conformance rebuild uses an OS temp dir).
export default defineConfig({
  entry: ['src/index.ts'],
  format: ['esm', 'cjs'],
  dts: true,
  clean: true,
  target: 'node22',
  outDir: 'dist',
  sourcemap: false,
  splitting: false,
});
