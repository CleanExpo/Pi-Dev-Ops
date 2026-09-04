#!/usr/bin/env node
/* Generates app/brand-tokens.css from packages/brand-config — the design SSOT.
 *
 * The site never hand-writes brand colours. themeFactory(bewg) emits shadcn-convention
 * CSS variables, which is what @unite-group/ui components consume, so the same tokens
 * drive this site and every other surface in the estate.
 *
 *   node scripts/gen-tokens.mjs            write the file
 *   node scripts/gen-tokens.mjs --check    fail if the committed file is out of date
 *
 * brand-config ships TypeScript with extensionless relative imports, so it is compiled
 * to a temp dir first rather than loaded directly.
 */
import { execFileSync } from 'node:child_process';
import { mkdtempSync, readFileSync, writeFileSync, readdirSync, statSync } from 'node:fs';
import { join, dirname, resolve } from 'node:path';
import { tmpdir } from 'node:os';
import { fileURLToPath, pathToFileURL } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const SITE = resolve(HERE, '..');
const BRAND = resolve(SITE, '../../packages/brand-config');
const OUT = join(SITE, 'app', 'brand-tokens.css');

function compileBrandConfig() {
  const dir = mkdtempSync(join(tmpdir(), 'bewg-tokens-'));
  execFileSync(
    join(SITE, 'node_modules', '.bin', 'tsc'),
    ['-p', join(BRAND, 'tsconfig.json'), '--outDir', dir,
     '--declaration', 'false', '--noEmit', 'false', '--module', 'esnext',
     '--moduleResolution', 'bundler'],
    { stdio: 'pipe' }
  );
  /* tsc preserves extensionless specifiers; Node's ESM loader needs them. */
  const walk = (d) => readdirSync(d).flatMap((e) => {
    const p = join(d, e);
    return statSync(p).isDirectory() ? walk(p) : p.endsWith('.js') ? [p] : [];
  });
  for (const f of walk(dir)) {
    writeFileSync(f, readFileSync(f, 'utf8').replace(
      /from '(\.[^']*?)(\.js)?'/g,
      (_m, spec) => `from '${spec}.js'`
    ));
  }
  writeFileSync(join(dir, 'package.json'), '{"type":"module"}');
  return dir;
}

const block = (vars, indent = '  ') =>
  Object.entries(vars).map(([k, v]) => `${indent}${k}: ${v};`).join('\n');

const dir = compileBrandConfig();
const { bewg } = await import(pathToFileURL(join(dir, 'brands', 'index.js')).href);
const { themeFactory } = await import(pathToFileURL(join(dir, 'theme-factory.js')).href);
const theme = themeFactory(bewg);

const mapped = Object.keys(theme.cssVars.light)
  .map((k) => `  --color-${k.replace(/^--/, '')}: var(${k});`)
  .join('\n');

const css = `/* GENERATED FILE — DO NOT EDIT.
 * Source: packages/brand-config/src/brands/bewg.ts (spec: bewg.design.md)
 * Regenerate: node scripts/gen-tokens.mjs
 * Verify:     node scripts/gen-tokens.mjs --check
 *
 * shadcn-convention variables emitted by themeFactory, so @unite-group/ui
 * components render in BEWG's identity without per-site overrides.
 */

:root {
${block(theme.cssVars.light)}
}

.dark {
${block(theme.cssVars.dark)}
}

@theme inline {
${mapped}
}
`;

if (process.argv.includes('--check')) {
  let current = '';
  try { current = readFileSync(OUT, 'utf8'); } catch { /* missing counts as drift */ }
  if (current !== css) {
    console.error('brand-tokens.css is out of date with packages/brand-config.');
    console.error('Run: node scripts/gen-tokens.mjs');
    process.exit(1);
  }
  console.log(`brand-tokens.css matches brand-config (${Object.keys(theme.cssVars.light).length} tokens).`);
} else {
  writeFileSync(OUT, css);
  console.log(`Wrote app/brand-tokens.css — ${Object.keys(theme.cssVars.light).length} light / ${Object.keys(theme.cssVars.dark).length} dark tokens from brand "${theme.brand}".`);
}
