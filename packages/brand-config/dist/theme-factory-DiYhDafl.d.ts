type BrandSlug = 'dr' | 'nrpg' | 'ra' | 'carsi' | 'ccw' | 'synthex' | 'unite';
type ColourFamily = 'restoration' | 'safety' | 'industrial' | 'consumer' | 'training';
type SignatureMotion = 'rise' | 'sweep' | 'pulse' | 'iris' | 'whip';
interface BrandColour {
    primary: string;
    secondary: string;
    accent: string;
    neutral: {
        50: string;
        100: string;
        500: string;
        900: string;
    };
    semantic: {
        success: string;
        warning: string;
        danger: string;
    };
    family: ColourFamily;
    darkVariant?: Partial<Omit<BrandColour, 'family' | 'darkVariant'>>;
}
interface BrandTypography {
    display: {
        family: string;
        weight: number;
        src: string;
    };
    body: {
        family: string;
        weight: number;
        src: string;
    };
    mono?: {
        family: string;
        weight: number;
        src: string;
    };
}
interface BrandLogo {
    primary: string;
    inverted: string;
    icon: string;
    safeAreaPx: number;
}
interface BrandMotion {
    durations: {
        fast: number;
        base: number;
        slow: number;
    };
    easing: {
        in: string;
        out: string;
        inOut: string;
    };
    signature: SignatureMotion;
    transitionFrames: number;
}
interface BrandVoiceover {
    elevenLabsVoiceId: string;
    style: 'narration' | 'conversational' | 'urgent';
    locale: 'en-AU' | 'en-GB' | 'en-US';
}
interface BrandVoice {
    tone: Array<'authoritative' | 'reassuring' | 'urgent' | 'expert' | 'warm'>;
    forbiddenWords: string[];
    requiredCadence?: 'short' | 'medium' | 'long';
}
interface BrandConfig {
    slug: BrandSlug;
    legalName: string;
    displayName: string;
    tagline: string;
    voice: BrandVoice;
    colour: BrandColour;
    typography: BrandTypography;
    logo: BrandLogo;
    motion: BrandMotion;
    voiceover: BrandVoiceover;
    doNot: string[];
    audience: {
        primary: string;
        secondary?: string;
    };
    defaultChannel: 'linkedin' | 'youtube' | 'instagram' | 'training';
}
declare const FORBIDDEN_PRONOUNS: string[];

/**
 * Bridge from BrandConfig to web-app theme primitives.
 *
 * - `cssVars` — flat `Record<string, string>` for injection into `:root` (light)
 *   and `.dark` (dark) selectors. Keys follow Tailwind v4 / shadcn convention
 *   (`--background`, `--foreground`, `--primary`, etc).
 * - `tailwind` — fragment for Tailwind v3 `theme.extend.colors` consumers.
 *   Tailwind v4 consumers should prefer the `cssVars` payload + `@theme inline`.
 * - `tokens` — raw OKLch + hex tokens for downstream consumers that want
 *   explicit colour-space access (PDF rendering, design-tool exports).
 */
interface ThemeTokens {
    hex: string;
    oklch: string;
}
type CssVarMap = Record<string, string>;
interface TailwindFragment {
    colors: Record<string, string | Record<string, string>>;
    fontFamily: Record<string, string[]>;
    fontWeight: Record<string, string>;
}
interface ThemeOutput {
    brand: string;
    cssVars: {
        light: CssVarMap;
        dark: CssVarMap;
    };
    tailwind: TailwindFragment;
    tokens: {
        primary: ThemeTokens;
        secondary: ThemeTokens;
        accent: ThemeTokens;
        neutral: Record<'50' | '100' | '500' | '900', ThemeTokens>;
        semantic: Record<'success' | 'warning' | 'danger', ThemeTokens>;
    };
}
/** Convert hex (#RRGGBB) → CSS-Color-4 oklch() string. Pure function. */
declare function oklchFromHex(hex: string): string;
declare function themeFactory(brand: BrandConfig): ThemeOutput;

export { type BrandConfig as B, type ColourFamily as C, FORBIDDEN_PRONOUNS as F, type SignatureMotion as S, type TailwindFragment as T, type BrandSlug as a, type BrandColour as b, type BrandLogo as c, type BrandMotion as d, type BrandTypography as e, type BrandVoice as f, type BrandVoiceover as g, type CssVarMap as h, type ThemeTokens as i, type ThemeOutput as j, oklchFromHex as o, themeFactory as t };
