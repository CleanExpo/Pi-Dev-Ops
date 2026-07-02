import { B as BrandConfig, a as BrandSlug } from './theme-factory-DiYhDafl.js';
export { b as BrandColour, c as BrandLogo, d as BrandMotion, e as BrandTypography, f as BrandVoice, g as BrandVoiceover, C as ColourFamily, h as CssVarMap, F as FORBIDDEN_PRONOUNS, S as SignatureMotion, T as TailwindFragment, i as ThemeTokens, o as oklchFromHex, t as themeFactory } from './theme-factory-DiYhDafl.js';

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

export { BrandConfig, BrandSlug, MARGOT_ELEVENLABS_VOICE_ID, brands, carsi, ccw, dr, nrpg, ra, synthex, unite };
