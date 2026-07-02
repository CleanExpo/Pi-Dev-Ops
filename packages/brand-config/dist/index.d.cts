import { B as BrandConfig, a as BrandSlug } from './theme-factory-DiYhDafl.cjs';
export { b as BrandColour, c as BrandLogo, d as BrandMotion, e as BrandTypography, f as BrandVoice, g as BrandVoiceover, C as ColourFamily, h as CssVarMap, F as FORBIDDEN_PRONOUNS, S as SignatureMotion, T as TailwindFragment, i as ThemeTokens, o as oklchFromHex, t as themeFactory } from './theme-factory-DiYhDafl.cjs';

declare const ra: BrandConfig;

declare const dr: BrandConfig;

declare const nrpg: BrandConfig;

declare const carsi: BrandConfig;

declare const ccw: BrandConfig;

declare const synthex: BrandConfig;

declare const unite: BrandConfig;

declare const brands: Record<BrandSlug, BrandConfig>;

/**
 * Margot ElevenLabs voice — global SSOT for TypeScript consumers.
 *
 * NOT `ELEVENLABS_VOICE_ID` / `SYNTHEX_ELEVENLABS_VOICE_ID` — those are for
 * other agents. Margot surfaces must use this constant or `resolveMargotVoice()`.
 *
 * Keep in sync with `.harness/margot/assets/margot_identity.json` and
 * `app/server/margot_voice.py`.
 */
declare const MARGOT_ELEVENLABS_VOICE_ID: "p43fx6U8afP2xoq1Ai9f";

/**
 * Margot embeddable assistant surfaces — SSOT for per-project bubbles.
 *
 * Same Margot persona + avatar everywhere; role label, welcome copy, and
 * data scope differ per brand. Backend routes must enforce tenant_id /
 * project_slug — UI copy alone is not isolation.
 */
type MargotSurfaceProject = 'unite-group' | 'restoreassist' | 'carsi';
interface MargotSurfaceConfig {
    project: MargotSurfaceProject;
    /** Supabase / margot_conversations tenant slug */
    tenantId: string;
    displayName: 'Margot';
    roleLabel: string;
    welcomeMessage: string;
    /** Injected into assistant system prompts — project data boundary */
    scopeLock: string;
    /** Public path to canonical avatar (each site copies to /margot/avatar.png) */
    avatarPath: string;
    /** Bubble launcher accent (hex) — from brand-config theme */
    accentColor: string;
}
declare const MARGOT_CANONICAL_AVATAR_PATH = "/margot/avatar.png";
declare const MARGOT_DISPLAY_NAME: "Margot";
declare const margotSurfaces: Record<MargotSurfaceProject, MargotSurfaceConfig>;
declare function getMargotSurface(project: MargotSurfaceProject): MargotSurfaceConfig;

export { BrandConfig, BrandSlug, MARGOT_CANONICAL_AVATAR_PATH, MARGOT_DISPLAY_NAME, MARGOT_ELEVENLABS_VOICE_ID, type MargotSurfaceConfig, type MargotSurfaceProject, brands, carsi, ccw, dr, getMargotSurface, margotSurfaces, nrpg, ra, synthex, unite };
