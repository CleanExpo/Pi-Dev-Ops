// Loader for {slug}.motion.md tokens.
//
// Source of truth: Synthex/packages/brand-config/src/brands/{slug}.motion.md
// Boundary contract: src/brands/CONTRACT.md (Phase B)
//
// Motion was promoted out of BrandConfig.ts in Phase B because choreography +
// stagger + spring physics + GSAP scroll defaults need declarative expression.

import { existsSync, readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { parse as parseYaml } from 'yaml';
import { z } from 'zod';
import type { BrandSlug } from '@unite-group/brand-config';

const require = createRequire(import.meta.url);

// ---------- Schema ----------

const EasingSchema = z.object({
  bezier: z.string().regex(/^cubic-bezier\(.+\)$/, 'must be a cubic-bezier(...) string'),
  use: z.string().optional(),
});

const SignatureSchema = z.object({
  name: z.enum(['rise', 'sweep', 'iris', 'pulse', 'whip']),
  axis: z.enum(['x', 'y', 'z']).optional(),
  amplitude: z.union([z.string(), z.number()]).optional(),
  duration: z.union([z.string(), z.number()]),
  easing: z.union([z.string(), z.object({}).passthrough()]),
  description: z.string().optional(),
});

const ChoreographyStepSchema = z.object({
  target: z.string(),
  start: z.union([z.string(), z.number()]),
  motion: z.string(),
});

const ChoreographySchema = z.object({
  description: z.string().optional(),
  sequence: z.array(ChoreographyStepSchema).optional(),
  stagger: z.number().optional(),
  motion: z.string().optional(),
});

const SpringSchema = z.object({
  damping: z.number(),
  stiffness: z.number(),
  mass: z.number(),
});

const LoopSchema = z.object({
  description: z.string().optional(),
  duration: z.union([z.string(), z.number()]),
  repeat: z.number(),
  yoyo: z.boolean().optional(),
  easing: z.string().optional(),
});

export const MotionTokensSchema = z.object({
  version: z.string(),
  name: z.string(),
  description: z.string().optional(),
  fps: z.number(),
  durations: z.record(z.string(), z.union([z.number(), z.string()])),
  easings: z.record(z.string(), EasingSchema),
  signature: SignatureSchema,
  choreography: z.record(z.string(), ChoreographySchema).optional(),
  spring: z.record(z.string(), SpringSchema).optional(),
  gsap: z
    .object({
      scrollTrigger: z
        .object({
          start: z.string().optional(),
          end: z.string().optional(),
          scrub: z.union([z.boolean(), z.number()]).optional(),
          pin: z.boolean().optional(),
          markers: z.boolean().optional(),
        })
        .optional(),
    })
    .optional(),
  loops: z.record(z.string(), LoopSchema).optional(),
  performance: z
    .object({
      maxConcurrentAnimations: z.number().optional(),
      preferTransform: z.boolean().optional(),
      prefersReducedMotion: z.enum(['respect', 'ignore']).optional(),
    })
    .optional(),
});

export type MotionTokens = z.infer<typeof MotionTokensSchema>;

// ---------- Loader ----------

const FRONTMATTER_RE = /^---\n([\s\S]*?)\n---/;

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

const cache = new Map<string, MotionTokens>();

/** Load + validate a brand's `{slug}.motion.md`. Throws on missing file or invalid schema. */
export function loadMotion(slug: BrandSlug): MotionTokens {
  const cached = cache.get(slug);
  if (cached) return cached;
  const path = join(brandConfigBrandsDir(), `${slug}.motion.md`);
  const raw = readFileSync(path, 'utf8');
  const m = FRONTMATTER_RE.exec(raw);
  if (!m) throw new Error(`No YAML front matter in ${path}`);
  const parsed = parseYaml(m[1]);
  const tokens = MotionTokensSchema.parse(parsed);
  cache.set(slug, tokens);
  return tokens;
}

/** Like loadMotion but returns null if the file does not exist (motion is required, but tests want a non-throwing variant). */
export function tryLoadMotion(slug: BrandSlug): MotionTokens | null {
  const path = join(brandConfigBrandsDir(), `${slug}.motion.md`);
  if (!existsSync(path)) return null;
  return loadMotion(slug);
}

export function _clearLoadMotionCache(): void {
  cache.clear();
}
