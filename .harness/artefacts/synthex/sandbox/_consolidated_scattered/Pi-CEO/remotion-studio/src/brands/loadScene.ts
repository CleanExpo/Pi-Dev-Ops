// Loader for {slug}.scene.md tokens (3D / WebGL).
//
// Source of truth: Synthex/packages/brand-config/src/brands/{slug}.scene.md
// Boundary contract: src/brands/CONTRACT.md (Phase B)
//
// Scene is OPTIONAL — most brands won't have a .scene.md. Use tryLoadScene().

import { existsSync, readFileSync } from 'node:fs';
import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { parse as parseYaml } from 'yaml';
import { z } from 'zod';
import type { BrandSlug } from '@unite-group/brand-config';

const require = createRequire(import.meta.url);

// ---------- Schema ----------

const PerspectiveCameraSchema = z.object({
  type: z.literal('perspective'),
  fov: z.number(),
  position: z.tuple([z.number(), z.number(), z.number()]),
  target: z.tuple([z.number(), z.number(), z.number()]).optional(),
});

const OrthographicCameraSchema = z.object({
  type: z.literal('orthographic'),
  zoom: z.number(),
  position: z.tuple([z.number(), z.number(), z.number()]),
});

const CameraSchema = z.union([PerspectiveCameraSchema, OrthographicCameraSchema]);

const LightSchema = z.object({
  type: z.enum(['directional', 'point', 'spot', 'ambient']).optional(),
  intensity: z.number(),
  position: z.tuple([z.number(), z.number(), z.number()]).optional(),
  color: z.string(),
});

const LightsSchema = z.object({
  ambient: LightSchema.optional(),
  key: LightSchema.optional(),
  fill: LightSchema.optional(),
  rim: LightSchema.optional(),
});

const MaterialSchema = z.object({
  type: z.enum(['basic', 'standard', 'physical', 'lambert', 'phong', 'toon']),
  color: z.string(),
  roughness: z.number().optional(),
  metalness: z.number().optional(),
  transmission: z.number().optional(),
  thickness: z.number().optional(),
  transparent: z.boolean().optional(),
  opacity: z.number().optional(),
});

const SceneElementSchema = z.object({
  type: z.string(),
  geometry: z.string().optional(),
  material: z.string(),
  count: z.number().optional(),
  layout: z.string().optional(),
  size: z.union([z.tuple([z.number(), z.number(), z.number()]), z.number()]).optional(),
  motion: z
    .object({
      axis: z.enum(['x', 'y', 'z']).optional(),
      speed: z.number().optional(),
    })
    .optional(),
});

const ScenePresetSchema = z.object({
  description: z.string().optional(),
  camera: z.string(),
  background: z.string(),
  elements: z.array(SceneElementSchema),
});

export const SceneTokensSchema = z.object({
  version: z.string(),
  name: z.string(),
  description: z.string().optional(),
  renderer: z.enum(['react-three-fiber', 'three', 'remotion-3d']).default('react-three-fiber'),
  camera: z.record(z.string(), CameraSchema),
  lights: z.record(z.string(), LightsSchema),
  materials: z.record(z.string(), MaterialSchema),
  scenes: z.record(z.string(), ScenePresetSchema),
  post: z
    .record(
      z.string(),
      z.object({
        bloom: z
          .object({
            intensity: z.number(),
            threshold: z.number().optional(),
            radius: z.number().optional(),
          })
          .optional(),
        vignette: z.object({ darkness: z.number() }).optional(),
      })
    )
    .optional(),
  performance: z.object({
    targetFps: z.number(),
    maxDrawCalls: z.number().optional(),
    maxPolygons: z.number().optional(),
    raycaster: z.boolean().optional(),
    prefersReducedMotion: z.enum(['respect', 'pause-particles', 'ignore']).optional(),
  }),
});

export type SceneTokens = z.infer<typeof SceneTokensSchema>;

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

const cache = new Map<string, SceneTokens>();

/** Load + validate a brand's `{slug}.scene.md`. Throws on missing file or invalid schema. */
export function loadScene(slug: BrandSlug): SceneTokens {
  const cached = cache.get(slug);
  if (cached) return cached;
  const path = join(brandConfigBrandsDir(), `${slug}.scene.md`);
  const raw = readFileSync(path, 'utf8');
  const m = FRONTMATTER_RE.exec(raw);
  if (!m) throw new Error(`No YAML front matter in ${path}`);
  const parsed = parseYaml(m[1]);
  const tokens = SceneTokensSchema.parse(parsed);
  cache.set(slug, tokens);
  return tokens;
}

/** Like loadScene but returns null if file does not exist (scene is optional). */
export function tryLoadScene(slug: BrandSlug): SceneTokens | null {
  const path = join(brandConfigBrandsDir(), `${slug}.scene.md`);
  if (!existsSync(path)) return null;
  return loadScene(slug);
}

export function _clearLoadSceneCache(): void {
  cache.clear();
}
