// Server-side loader for the three brand spec files. Mirrors the loader logic
// from `Pi-Dev-Ops/remotion-studio/src/brands/loadDesign.ts` but avoids
// importing it directly so this app stays self-contained.

import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { parse as parseYaml } from 'yaml';
import { z } from 'zod';

const FRONTMATTER_RE = /^---\n([\s\S]*?)\n---/;

// Resolve to the local Pi-Dev-Ops brand-config copy (same pattern as remotion-studio).
function brandConfigBrandsDir(): string {
  // preview-canvas/lib/loadSpecs.ts → preview-canvas → Pi-Dev-Ops → packages/brand-config/src/brands
  const here = dirname(new URL(import.meta.url).pathname);
  return resolve(here, '..', '..', 'packages', 'brand-config', 'src', 'brands');
}

function iterationsRoot(): string {
  const here = dirname(new URL(import.meta.url).pathname);
  return resolve(here, '..', '..', '.research', 'design', 'iterations');
}

// ---------- Types (loose; full validation lives in remotion-studio) ----------

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
}

export interface MotionTokens {
  version: string;
  name: string;
  fps: number;
  durations: Record<string, number | string>;
  easings: Record<string, { bezier: string; use?: string }>;
  signature: { name: string; axis?: string; duration: number | string; easing: string | object };
  choreography?: Record<string, unknown>;
  spring?: Record<string, { damping: number; stiffness: number; mass: number }>;
  loops?: Record<string, { duration: number | string; repeat: number }>;
  performance?: Record<string, unknown>;
}

export interface SceneTokens {
  version: string;
  name: string;
  renderer: string;
  camera: Record<string, unknown>;
  lights: Record<string, unknown>;
  materials: Record<string, unknown>;
  scenes: Record<string, unknown>;
  performance: { targetFps: number; maxDrawCalls?: number; maxPolygons?: number };
}

// ---------- Loader ----------

function readYamlFrontMatter<T>(path: string): T {
  const raw = readFileSync(path, 'utf8');
  const m = FRONTMATTER_RE.exec(raw);
  if (!m) throw new Error(`No YAML front matter in ${path}`);
  return parseYaml(m[1]) as T;
}

export function loadDesign(slug: string): DesignTokens {
  const path = join(brandConfigBrandsDir(), `${slug}.design.md`);
  return readYamlFrontMatter<DesignTokens>(path);
}

export function loadMotion(slug: string): MotionTokens {
  const path = join(brandConfigBrandsDir(), `${slug}.motion.md`);
  return readYamlFrontMatter<MotionTokens>(path);
}

export function tryLoadMotion(slug: string): MotionTokens | null {
  const path = join(brandConfigBrandsDir(), `${slug}.motion.md`);
  if (!existsSync(path)) return null;
  return readYamlFrontMatter<MotionTokens>(path);
}

export function loadScene(slug: string): SceneTokens {
  const path = join(brandConfigBrandsDir(), `${slug}.scene.md`);
  return readYamlFrontMatter<SceneTokens>(path);
}

export function tryLoadScene(slug: string): SceneTokens | null {
  const path = join(brandConfigBrandsDir(), `${slug}.scene.md`);
  if (!existsSync(path)) return null;
  return readYamlFrontMatter<SceneTokens>(path);
}

// ---------- Listings ----------

export function listBrands(): string[] {
  const dir = brandConfigBrandsDir();
  return readdirSync(dir)
    .filter((f) => f.endsWith('.design.md'))
    .map((f) => f.replace('.design.md', ''))
    .sort();
}

export interface IterationVariant {
  jobId: string;
  variant: string;
  design: DesignTokens;
  motion: MotionTokens | null;
  scene: SceneTokens | null;
  notes?: string;
}

export function loadIterationJob(jobId: string): IterationVariant[] {
  const dir = join(iterationsRoot(), jobId);
  if (!existsSync(dir)) return [];
  const variants = readdirSync(dir).filter((f) => f.endsWith('.design.md')).sort();
  return variants.map((file) => {
    const variant = file.replace('.design.md', '');
    return {
      jobId,
      variant,
      design: readYamlFrontMatter<DesignTokens>(join(dir, file)),
      motion: existsSync(join(dir, `${variant}.motion.md`))
        ? readYamlFrontMatter<MotionTokens>(join(dir, `${variant}.motion.md`))
        : null,
      scene: existsSync(join(dir, `${variant}.scene.md`))
        ? readYamlFrontMatter<SceneTokens>(join(dir, `${variant}.scene.md`))
        : null,
    };
  });
}

export function listIterationJobs(): string[] {
  const root = iterationsRoot();
  if (!existsSync(root)) return [];
  return readdirSync(root).sort();
}

// ---------- Token resolution ----------

const REF_RE = /^\{([\w.-]+)\}$/;

export function resolveToken(tokens: DesignTokens, value: string | undefined): string | undefined {
  if (!value) return undefined;
  const m = REF_RE.exec(value);
  if (!m) return value;
  const path = m[1].split('.');
  let cursor: unknown = tokens;
  for (const seg of path) {
    if (cursor && typeof cursor === 'object' && seg in (cursor as Record<string, unknown>)) {
      cursor = (cursor as Record<string, unknown>)[seg];
    } else {
      return value;
    }
  }
  if (typeof cursor === 'string' && REF_RE.test(cursor)) {
    return resolveToken(tokens, cursor);
  }
  return typeof cursor === 'string' ? cursor : value;
}

// ---------- Contrast (for Palette WCAG badges) ----------

function hexToRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '');
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return [r, g, b];
}

function relLuminance([r, g, b]: [number, number, number]): number {
  const channel = (c: number) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b);
}

export function contrastRatio(fg: string, bg: string): number {
  const lf = relLuminance(hexToRgb(fg));
  const lb = relLuminance(hexToRgb(bg));
  const [light, dark] = lf > lb ? [lf, lb] : [lb, lf];
  return Math.round(((light + 0.05) / (dark + 0.05)) * 100) / 100;
}

export function wcagLevel(ratio: number): 'AAA' | 'AA' | 'AA-large' | 'fail' {
  if (ratio >= 7) return 'AAA';
  if (ratio >= 4.5) return 'AA';
  if (ratio >= 3) return 'AA-large';
  return 'fail';
}
