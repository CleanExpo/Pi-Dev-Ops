// Design-token helpers for Remotion compositions.
//
// Companion to ../brands/loadDesign.ts. Compositions call `loadDesign(slug)`
// to get raw tokens, then use these helpers to resolve cross-references
// (`{colors.primary}` → `#E55A2B`) and pull recipes by name.

import type { BrandSlug } from '@unite-group/brand-config';
import {
  loadDesign,
  type ComponentRecipe,
  type DesignTokens,
  type TypographyToken,
} from '../brands/loadDesign';
import {
  loadMotion,
  tryLoadMotion,
  type MotionTokens,
} from '../brands/loadMotion';
import {
  loadScene,
  tryLoadScene,
  type SceneTokens,
} from '../brands/loadScene';

export type { DesignTokens, ComponentRecipe, TypographyToken, MotionTokens, SceneTokens };
export { loadDesign, loadMotion, tryLoadMotion, loadScene, tryLoadScene };

const REF_RE = /^\{([\w.-]+)\}$/;

/**
 * Resolve a token reference like `{colors.primary}` against a DesignTokens tree.
 * Returns the raw string when not a reference.
 */
export function resolveToken<T = string>(
  tokens: DesignTokens,
  value: string | number | undefined,
): T | undefined {
  if (value === undefined || value === null) return undefined;
  if (typeof value === 'number') return value as unknown as T;
  const m = REF_RE.exec(value);
  if (!m) return value as unknown as T;
  const path = m[1].split('.');
  let cursor: unknown = tokens;
  for (const seg of path) {
    if (cursor && typeof cursor === 'object' && seg in (cursor as Record<string, unknown>)) {
      cursor = (cursor as Record<string, unknown>)[seg];
    } else {
      throw new Error(`Unresolved token reference: ${value}`);
    }
  }
  // Recursively resolve in case the target is itself a reference.
  if (typeof cursor === 'string' && REF_RE.test(cursor)) {
    return resolveToken<T>(tokens, cursor);
  }
  return cursor as T;
}

/** Get a colour hex by token name (e.g. `'primary'` → `'#E55A2B'`). */
export function colour(tokens: DesignTokens, name: string): string {
  const v = tokens.colors[name];
  if (!v) throw new Error(`Unknown colour token: ${name}`);
  return resolveToken<string>(tokens, v) ?? v;
}

/** Get a spacing value by token name (e.g. `'md'` → `'16px'`). */
export function spacing(tokens: DesignTokens, name: string): string {
  const v = tokens.spacing[name];
  if (v === undefined) throw new Error(`Unknown spacing token: ${name}`);
  return typeof v === 'number' ? `${v}px` : v;
}

/** Get a typography token by name (e.g. `'display-xl'`). */
export function typography(tokens: DesignTokens, name: string): TypographyToken {
  const v = tokens.typography[name];
  if (!v) throw new Error(`Unknown typography token: ${name}`);
  return v;
}

/**
 * Look up a component recipe by name and resolve all of its references.
 * Returns concrete CSS-ready values.
 */
export function componentRecipe(
  tokens: DesignTokens,
  name: string,
): {
  backgroundColor?: string;
  textColor?: string;
  rounded?: string;
  padding?: string;
  typography?: TypographyToken;
} {
  const recipe = tokens.components[name];
  if (!recipe) throw new Error(`Unknown component recipe: ${name}`);
  const out: ReturnType<typeof componentRecipe> = {};
  if (recipe.backgroundColor) out.backgroundColor = resolveToken<string>(tokens, recipe.backgroundColor);
  if (recipe.textColor) out.textColor = resolveToken<string>(tokens, recipe.textColor);
  if (recipe.rounded) out.rounded = resolveToken<string>(tokens, recipe.rounded);
  if (recipe.padding) out.padding = resolveToken<string>(tokens, recipe.padding);
  if (recipe.typography) {
    const ref = REF_RE.exec(recipe.typography);
    if (ref) {
      const path = ref[1].split('.');
      if (path[0] === 'typography') {
        out.typography = tokens.typography[path[1]];
      }
    }
  }
  return out;
}

/** Convenience: pull a brand's tokens in one call. */
export function brandDesign(slug: BrandSlug): DesignTokens {
  return loadDesign(slug);
}
