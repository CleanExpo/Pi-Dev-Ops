// Loader for {slug}.design.md visual tokens.
//
// Source of truth: Synthex/packages/brand-config/src/brands/{slug}.design.md
// Boundary contract: src/brands/CONTRACT.md
//
// BrandConfig.ts (runtime/behaviour) is loaded via the existing `brands` export.
// This loader is only for visual tokens that live in the .design.md companion file.

import { existsSync, readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { parse as parseYaml } from 'yaml';
import type { BrandSlug } from '@unite-group/brand-config';

const require = createRequire(import.meta.url);

export interface DesignTokens {
  version: string;
  name: string;
  description?: string;
  colors: Record<string, string>;
  typography: Record<string, TypographyToken>;
  spacing: Record<string, string | number>;
  rounded: Record<string, string>;
  components: Record<string, ComponentRecipe>;
}

export interface TypographyToken {
  fontFamily: string;
  fontSize: string;
  fontWeight: number | string;
  lineHeight: number | string;
  letterSpacing?: string;
}

export interface ComponentRecipe {
  backgroundColor?: string;
  textColor?: string;
  rounded?: string;
  padding?: string;
  typography?: string;
  size?: string;
  height?: string;
  width?: string;
}

const FRONTMATTER_RE = /^---\n([\s\S]*?)\n---/;

// Resolve to the brand-config package brands directory.
// The package's `exports` field locks down deep paths, so we resolve the main
// entry and walk up to find the package root (the dir containing package.json),
// then descend into `src/brands/`.
function brandConfigBrandsDir(): string {
  const entry = require.resolve('@unite-group/brand-config');
  let dir = dirname(entry);
  for (let i = 0; i < 8; i += 1) {
    if (existsSync(join(dir, 'package.json'))) {
      return join(dir, 'src', 'brands');
    }
    const parent = dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  throw new Error('Could not locate @unite-group/brand-config package root');
}

const cache = new Map<string, DesignTokens>();

/**
 * Load and parse a brand's `{slug}.design.md` visual tokens.
 *
 * Throws if the file is missing or YAML front matter cannot be parsed.
 * Token cross-references like `{colors.primary}` are returned as-is — call
 * `resolveToken()` from `../design` to dereference.
 */
export function loadDesign(slug: BrandSlug): DesignTokens {
  const cached = cache.get(slug);
  if (cached) return cached;

  const path = join(brandConfigBrandsDir(), `${slug}.design.md`);
  const raw = readFileSync(path, 'utf8');
  const m = FRONTMATTER_RE.exec(raw);
  if (!m) {
    throw new Error(`No YAML front matter in ${path}`);
  }
  const tokens = parseYaml(m[1]) as DesignTokens;
  cache.set(slug, tokens);
  return tokens;
}

/** Test-seam: clear the in-process cache (used in unit tests). */
export function _clearLoadDesignCache(): void {
  cache.clear();
}
