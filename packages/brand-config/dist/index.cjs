"use strict";
var __defProp = Object.defineProperty;
var __getOwnPropDesc = Object.getOwnPropertyDescriptor;
var __getOwnPropNames = Object.getOwnPropertyNames;
var __hasOwnProp = Object.prototype.hasOwnProperty;
var __export = (target, all) => {
  for (var name in all)
    __defProp(target, name, { get: all[name], enumerable: true });
};
var __copyProps = (to, from, except, desc) => {
  if (from && typeof from === "object" || typeof from === "function") {
    for (let key of __getOwnPropNames(from))
      if (!__hasOwnProp.call(to, key) && key !== except)
        __defProp(to, key, { get: () => from[key], enumerable: !(desc = __getOwnPropDesc(from, key)) || desc.enumerable });
  }
  return to;
};
var __toCommonJS = (mod) => __copyProps(__defProp({}, "__esModule", { value: true }), mod);

// src/index.ts
var index_exports = {};
__export(index_exports, {
  FORBIDDEN_PRONOUNS: () => FORBIDDEN_PRONOUNS,
  brands: () => brands,
  carsi: () => carsi,
  ccw: () => ccw,
  dr: () => dr,
  nrpg: () => nrpg,
  oklchFromHex: () => oklchFromHex,
  ra: () => ra,
  synthex: () => synthex,
  themeFactory: () => themeFactory,
  unite: () => unite
});
module.exports = __toCommonJS(index_exports);

// src/types.ts
var FORBIDDEN_PRONOUNS = ["we", "our", "i", "us", "my"];

// src/brands/ra.ts
var ra = {
  slug: "ra",
  legalName: "RestoreAssist Pty Ltd",
  displayName: "RestoreAssist",
  tagline: "One National Inspection Standard.",
  voice: {
    tone: ["expert", "urgent"],
    forbiddenWords: [...FORBIDDEN_PRONOUNS, "leverage", "utilise", "best-in-class"],
    requiredCadence: "short"
  },
  colour: {
    primary: "#0E7C7B",
    // teal — restoration / clarity
    secondary: "#2A3D45",
    // slate
    accent: "#C5E063",
    // lime — action / NIR highlight
    neutral: { 50: "#F5F7F8", 100: "#E4E9EC", 500: "#6F7B82", 900: "#0E1518" },
    semantic: { success: "#3FA34D", warning: "#E0A800", danger: "#C0392B" },
    family: "restoration",
    darkVariant: {
      primary: "#16B5B3",
      secondary: "#1A2428",
      neutral: { 50: "#0E1518", 100: "#1A2428", 500: "#A6B0B6", 900: "#F5F7F8" }
    }
  },
  typography: {
    display: { family: "Inter", weight: 800, src: "fonts/ra/Inter-ExtraBold.woff2" },
    body: { family: "Inter", weight: 400, src: "fonts/ra/Inter-Regular.woff2" },
    mono: { family: "JetBrains Mono", weight: 500, src: "fonts/ra/JetBrainsMono-Medium.woff2" }
  },
  logo: {
    primary: "logos/ra/primary.svg",
    inverted: "logos/ra/inverted.svg",
    icon: "logos/ra/icon.svg",
    safeAreaPx: 48
  },
  motion: {
    durations: { fast: 8, base: 18, slow: 36 },
    // frames @ 30fps
    easing: {
      in: "cubic-bezier(0.22, 1, 0.36, 1)",
      // expo-out
      out: "cubic-bezier(0.64, 0, 0.78, 0)",
      // expo-in
      inOut: "cubic-bezier(0.83, 0, 0.17, 1)"
      // expo-in-out
    },
    signature: "sweep",
    // horizontal reveal — decisive
    transitionFrames: 14
  },
  voiceover: {
    elevenLabsVoiceId: "EXAVITQu4vr4xnSDxMaL",
    // Sarah — neutral AU/UK; replace with cloned voice when available
    style: "narration",
    locale: "en-AU"
  },
  doNot: [
    'never abbreviate the company name to "RA" in voiceover or on-screen titles',
    "never use red as a primary brand colour (reserved for danger only)",
    "never imply the NIR is optional or vendor-specific"
  ],
  audience: {
    primary: "restoration company owners and field technicians (AU)",
    secondary: "insurer claims teams and assessor networks"
  },
  defaultChannel: "linkedin"
};

// src/brands/dr.ts
var dr = {
  slug: "dr",
  legalName: "Disaster Recovery Pty Ltd",
  displayName: "Disaster Recovery",
  tagline: "When the worst happens, ready answers.",
  voice: {
    tone: ["authoritative", "reassuring"],
    forbiddenWords: [...FORBIDDEN_PRONOUNS],
    requiredCadence: "medium"
  },
  colour: {
    primary: "#0B2545",
    secondary: "#13315C",
    accent: "#FF8A00",
    neutral: { 50: "#F4F6F8", 100: "#E2E7EC", 500: "#6F7B82", 900: "#0B1726" },
    semantic: { success: "#3FA34D", warning: "#E0A800", danger: "#C0392B" },
    family: "safety"
  },
  typography: {
    display: { family: "Inter", weight: 800, src: "fonts/dr/Inter-ExtraBold.woff2" },
    body: { family: "Inter", weight: 400, src: "fonts/dr/Inter-Regular.woff2" }
  },
  logo: {
    primary: "logos/dr/primary.svg",
    inverted: "logos/dr/inverted.svg",
    icon: "logos/dr/icon.svg",
    safeAreaPx: 48
  },
  motion: {
    durations: { fast: 10, base: 22, slow: 40 },
    easing: {
      in: "cubic-bezier(0.22, 1, 0.36, 1)",
      out: "cubic-bezier(0.64, 0, 0.78, 0)",
      inOut: "cubic-bezier(0.83, 0, 0.17, 1)"
    },
    signature: "rise",
    transitionFrames: 16
  },
  voiceover: {
    elevenLabsVoiceId: "EXAVITQu4vr4xnSDxMaL",
    style: "narration",
    locale: "en-AU"
  },
  doNot: [
    "never trivialise loss in voiceover or on-screen text",
    "never use red as a primary brand colour"
  ],
  audience: { primary: "business owners and facility managers post-incident" },
  defaultChannel: "linkedin"
};

// src/brands/nrpg.ts
var nrpg = {
  slug: "nrpg",
  legalName: "NRPG",
  displayName: "NRPG",
  tagline: "Standards for the response network.",
  voice: {
    tone: ["authoritative", "expert"],
    forbiddenWords: [...FORBIDDEN_PRONOUNS],
    requiredCadence: "medium"
  },
  colour: {
    primary: "#1A2A4F",
    secondary: "#2A3D5F",
    accent: "#F2B33D",
    neutral: { 50: "#FAF8F2", 100: "#EDE7D6", 500: "#7A7468", 900: "#0F1626" },
    semantic: { success: "#3FA34D", warning: "#E0A800", danger: "#C0392B" },
    family: "safety"
  },
  typography: {
    display: { family: "Inter", weight: 800, src: "fonts/nrpg/Inter-ExtraBold.woff2" },
    body: { family: "Inter", weight: 400, src: "fonts/nrpg/Inter-Regular.woff2" }
  },
  logo: {
    primary: "logos/nrpg/primary.svg",
    inverted: "logos/nrpg/inverted.svg",
    icon: "logos/nrpg/icon.svg",
    safeAreaPx: 48
  },
  motion: {
    durations: { fast: 10, base: 22, slow: 40 },
    easing: {
      in: "cubic-bezier(0.22, 1, 0.36, 1)",
      out: "cubic-bezier(0.64, 0, 0.78, 0)",
      inOut: "cubic-bezier(0.83, 0, 0.17, 1)"
    },
    signature: "rise",
    transitionFrames: 16
  },
  voiceover: {
    elevenLabsVoiceId: "EXAVITQu4vr4xnSDxMaL",
    style: "narration",
    locale: "en-AU"
  },
  doNot: ["never present NRPG as a regulatory body \u2014 it is an industry standard"],
  audience: { primary: "industry training coordinators and response-network operators" },
  defaultChannel: "linkedin"
};

// src/brands/carsi.ts
var carsi = {
  slug: "carsi",
  legalName: "CARSI",
  displayName: "CARSI",
  tagline: "Inspection-led training.",
  voice: {
    tone: ["expert", "warm"],
    forbiddenWords: [...FORBIDDEN_PRONOUNS],
    requiredCadence: "medium"
  },
  colour: {
    primary: "#B85C38",
    secondary: "#2D2A26",
    accent: "#F2E8D5",
    neutral: { 50: "#FBF8F2", 100: "#EFE7D9", 500: "#736B5E", 900: "#1A1714" },
    semantic: { success: "#3FA34D", warning: "#E0A800", danger: "#C0392B" },
    family: "training"
  },
  typography: {
    display: { family: "Lora", weight: 700, src: "fonts/carsi/Lora-Bold.woff2" },
    body: { family: "Inter", weight: 400, src: "fonts/carsi/Inter-Regular.woff2" }
  },
  logo: {
    primary: "logos/carsi/primary.svg",
    inverted: "logos/carsi/inverted.svg",
    icon: "logos/carsi/icon.svg",
    safeAreaPx: 48
  },
  motion: {
    durations: { fast: 12, base: 24, slow: 42 },
    easing: {
      in: "cubic-bezier(0.22, 1, 0.36, 1)",
      out: "cubic-bezier(0.64, 0, 0.78, 0)",
      inOut: "cubic-bezier(0.83, 0, 0.17, 1)"
    },
    signature: "iris",
    transitionFrames: 18
  },
  voiceover: {
    elevenLabsVoiceId: "EXAVITQu4vr4xnSDxMaL",
    style: "narration",
    locale: "en-AU"
  },
  doNot: ["never use clinical jargon without on-screen definition"],
  audience: { primary: "restoration trainees and technical inspectors" },
  defaultChannel: "youtube"
};

// src/brands/ccw.ts
var ccw = {
  slug: "ccw",
  legalName: "Carpet Cleaners Warehouse",
  displayName: "CCW",
  tagline: "Trade prices. Same-day dispatch.",
  voice: {
    tone: ["warm", "urgent"],
    forbiddenWords: [...FORBIDDEN_PRONOUNS, "cheap", "discounted"],
    requiredCadence: "short"
  },
  colour: {
    primary: "#D62828",
    secondary: "#003049",
    accent: "#F77F00",
    neutral: { 50: "#FFFFFF", 100: "#F5F5F5", 500: "#737373", 900: "#1A1A1A" },
    semantic: { success: "#3FA34D", warning: "#E0A800", danger: "#7B0F0F" },
    family: "consumer"
  },
  typography: {
    display: { family: "Outfit", weight: 800, src: "fonts/ccw/Outfit-ExtraBold.woff2" },
    body: { family: "Inter", weight: 400, src: "fonts/ccw/Inter-Regular.woff2" }
  },
  logo: {
    primary: "logos/ccw/primary.svg",
    inverted: "logos/ccw/inverted.svg",
    icon: "logos/ccw/icon.svg",
    safeAreaPx: 32
  },
  motion: {
    durations: { fast: 6, base: 14, slow: 28 },
    easing: {
      in: "cubic-bezier(0.34, 1.56, 0.64, 1)",
      // overshoot — retail energy
      out: "cubic-bezier(0.36, 0, 0.66, -0.56)",
      inOut: "cubic-bezier(0.65, 0, 0.35, 1)"
    },
    signature: "pulse",
    transitionFrames: 10
  },
  voiceover: {
    elevenLabsVoiceId: "EXAVITQu4vr4xnSDxMaL",
    style: "conversational",
    locale: "en-AU"
  },
  doNot: [
    'never claim products are "the cheapest" \u2014 use "trade pricing" instead',
    "never use red type on coloured backgrounds (reserve red for hero/CTA)"
  ],
  audience: { primary: "professional carpet cleaners and restoration trades (AU)" },
  defaultChannel: "instagram"
};

// src/brands/synthex.ts
var synthex = {
  slug: "synthex",
  legalName: "Synthex",
  displayName: "Synthex",
  tagline: "Synthetic intelligence at production scale.",
  voice: {
    tone: ["expert", "authoritative"],
    forbiddenWords: [...FORBIDDEN_PRONOUNS, "leverage", "synergy"],
    requiredCadence: "medium"
  },
  colour: {
    primary: "#6366F1",
    // indigo — synthetic / abstract
    secondary: "#0F172A",
    // slate-900
    accent: "#22D3EE",
    // cyan — signal / output
    neutral: { 50: "#F8FAFC", 100: "#E2E8F0", 500: "#64748B", 900: "#0F172A" },
    semantic: { success: "#10B981", warning: "#F59E0B", danger: "#EF4444" },
    family: "industrial"
  },
  typography: {
    display: { family: "Inter", weight: 800, src: "fonts/synthex/Inter-ExtraBold.woff2" },
    body: { family: "Inter", weight: 400, src: "fonts/synthex/Inter-Regular.woff2" },
    mono: { family: "JetBrains Mono", weight: 500, src: "fonts/synthex/JetBrainsMono-Medium.woff2" }
  },
  logo: {
    primary: "logos/synthex/primary.svg",
    inverted: "logos/synthex/inverted.svg",
    icon: "logos/synthex/icon.svg",
    safeAreaPx: 40
  },
  motion: {
    durations: { fast: 8, base: 16, slow: 32 },
    easing: {
      in: "cubic-bezier(0.22, 1, 0.36, 1)",
      out: "cubic-bezier(0.64, 0, 0.78, 0)",
      inOut: "cubic-bezier(0.83, 0, 0.17, 1)"
    },
    signature: "sweep",
    transitionFrames: 12
  },
  voiceover: {
    elevenLabsVoiceId: "EXAVITQu4vr4xnSDxMaL",
    style: "narration",
    locale: "en-AU"
  },
  doNot: [
    "never imply Synthex generates training data without consent",
    "never use stock AI-clich\xE9 imagery (glowing brains, blue particles)"
  ],
  audience: {
    primary: "ML engineers and platform teams shipping AI products",
    secondary: "CTOs evaluating synthetic-data infrastructure"
  },
  defaultChannel: "linkedin"
};

// src/brands/unite.ts
var unite = {
  slug: "unite",
  legalName: "Unite Group",
  displayName: "Unite Group",
  tagline: "Connected service for the field.",
  voice: {
    tone: ["warm", "expert"],
    forbiddenWords: [...FORBIDDEN_PRONOUNS],
    requiredCadence: "medium"
  },
  colour: {
    primary: "#1D4ED8",
    // blue — trust, network
    secondary: "#1E293B",
    accent: "#FBBF24",
    // amber — signal
    neutral: { 50: "#F8FAFC", 100: "#E2E8F0", 500: "#64748B", 900: "#0F172A" },
    semantic: { success: "#16A34A", warning: "#D97706", danger: "#DC2626" },
    family: "industrial"
  },
  typography: {
    display: { family: "Inter", weight: 700, src: "fonts/unite/Inter-Bold.woff2" },
    body: { family: "Inter", weight: 400, src: "fonts/unite/Inter-Regular.woff2" }
  },
  logo: {
    primary: "logos/unite/primary.svg",
    inverted: "logos/unite/inverted.svg",
    icon: "logos/unite/icon.svg",
    safeAreaPx: 40
  },
  motion: {
    durations: { fast: 10, base: 20, slow: 36 },
    easing: {
      in: "cubic-bezier(0.22, 1, 0.36, 1)",
      out: "cubic-bezier(0.64, 0, 0.78, 0)",
      inOut: "cubic-bezier(0.83, 0, 0.17, 1)"
    },
    signature: "rise",
    transitionFrames: 14
  },
  voiceover: {
    elevenLabsVoiceId: "EXAVITQu4vr4xnSDxMaL",
    style: "conversational",
    locale: "en-AU"
  },
  doNot: [
    "never present Unite Group as a single-vertical company \u2014 it spans multiple service lines"
  ],
  audience: { primary: "field-services operators across the Unite portfolio" },
  defaultChannel: "linkedin"
};

// src/brands/index.ts
var brands = {
  ra,
  dr,
  nrpg,
  carsi,
  ccw,
  synthex,
  unite
};

// src/theme-factory.ts
function oklchFromHex(hex) {
  const h = hex.replace("#", "");
  const r = parseInt(h.slice(0, 2), 16) / 255;
  const g = parseInt(h.slice(2, 4), 16) / 255;
  const b = parseInt(h.slice(4, 6), 16) / 255;
  const lin = (c) => c <= 0.04045 ? c / 12.92 : Math.pow((c + 0.055) / 1.055, 2.4);
  const lr = lin(r);
  const lg = lin(g);
  const lb = lin(b);
  const l_ = Math.cbrt(0.4122214708 * lr + 0.5363325363 * lg + 0.0514459929 * lb);
  const m_ = Math.cbrt(0.2119034982 * lr + 0.6806995451 * lg + 0.1073969566 * lb);
  const s_ = Math.cbrt(0.0883024619 * lr + 0.2817188376 * lg + 0.6299787005 * lb);
  const L = 0.2104542553 * l_ + 0.793617785 * m_ - 0.0040720468 * s_;
  const a = 1.9779984951 * l_ - 2.428592205 * m_ + 0.4505937099 * s_;
  const B = 0.0259040371 * l_ + 0.7827717662 * m_ - 0.808675766 * s_;
  const C = Math.sqrt(a * a + B * B);
  let H = Math.atan2(B, a) * 180 / Math.PI;
  if (H < 0) H += 360;
  const lPct = (L * 100).toFixed(1);
  const cStr = C.toFixed(3);
  const hStr = H.toFixed(1);
  return `oklch(${lPct}% ${cStr} ${hStr})`;
}
function token(hex) {
  return { hex, oklch: oklchFromHex(hex) };
}
function cssVarsFromColour(c, mode) {
  const dv = c.darkVariant ?? {};
  const isDark = mode === "dark";
  const primary = isDark ? dv.primary ?? c.primary : c.primary;
  const secondary = isDark ? dv.secondary ?? c.secondary : c.secondary;
  const accent = isDark ? dv.accent ?? c.accent : c.accent;
  const neutral = isDark ? { ...c.neutral, ...dv.neutral ?? {} } : c.neutral;
  const background = isDark ? neutral["900"] : neutral["50"];
  const foreground = isDark ? neutral["50"] : neutral["900"];
  const muted = isDark ? neutral["500"] : neutral["100"];
  const mutedFg = isDark ? neutral["100"] : neutral["500"];
  return {
    "--background": oklchFromHex(background),
    "--foreground": oklchFromHex(foreground),
    "--primary": oklchFromHex(primary),
    "--primary-foreground": oklchFromHex(neutral["50"]),
    "--secondary": oklchFromHex(secondary),
    "--secondary-foreground": oklchFromHex(neutral["50"]),
    "--accent": oklchFromHex(accent),
    "--accent-foreground": oklchFromHex(neutral["900"]),
    "--muted": oklchFromHex(muted),
    "--muted-foreground": oklchFromHex(mutedFg),
    "--border": oklchFromHex(neutral["100"]),
    "--input": oklchFromHex(neutral["100"]),
    "--ring": oklchFromHex(primary),
    "--success": oklchFromHex(c.semantic.success),
    "--warning": oklchFromHex(c.semantic.warning),
    "--destructive": oklchFromHex(c.semantic.danger),
    "--radius": "0.5rem"
  };
}
function tailwindFromBrand(b) {
  const c = b.colour;
  const families = {
    sans: [b.typography.body.family, "system-ui", "sans-serif"],
    display: [b.typography.display.family, "system-ui", "sans-serif"]
  };
  if (b.typography.mono) {
    families.mono = [b.typography.mono.family, "ui-monospace", "monospace"];
  }
  return {
    colors: {
      brand: {
        primary: c.primary,
        secondary: c.secondary,
        accent: c.accent
      },
      neutral: c.neutral,
      success: c.semantic.success,
      warning: c.semantic.warning,
      danger: c.semantic.danger
    },
    fontFamily: families,
    fontWeight: {
      display: String(b.typography.display.weight),
      body: String(b.typography.body.weight),
      mono: String(b.typography.mono?.weight ?? 500)
    }
  };
}
function themeFactory(brand) {
  const c = brand.colour;
  return {
    brand: brand.slug,
    cssVars: {
      light: cssVarsFromColour(c, "light"),
      dark: cssVarsFromColour(c, "dark")
    },
    tailwind: tailwindFromBrand(brand),
    tokens: {
      primary: token(c.primary),
      secondary: token(c.secondary),
      accent: token(c.accent),
      neutral: {
        "50": token(c.neutral["50"]),
        "100": token(c.neutral["100"]),
        "500": token(c.neutral["500"]),
        "900": token(c.neutral["900"])
      },
      semantic: {
        success: token(c.semantic.success),
        warning: token(c.semantic.warning),
        danger: token(c.semantic.danger)
      }
    }
  };
}
// Annotate the CommonJS export names for ESM import in node:
0 && (module.exports = {
  FORBIDDEN_PRONOUNS,
  brands,
  carsi,
  ccw,
  dr,
  nrpg,
  oklchFromHex,
  ra,
  synthex,
  themeFactory,
  unite
});
