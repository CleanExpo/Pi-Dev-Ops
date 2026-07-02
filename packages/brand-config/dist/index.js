import {
  oklchFromHex,
  themeFactory
} from "./chunk-3RFMQ4QZ.js";

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

// src/constants/margot-elevenlabs.ts
var MARGOT_ELEVENLABS_VOICE_ID = "p43fx6U8afP2xoq1Ai9f";

// src/margot-surfaces.ts
var MARGOT_CANONICAL_AVATAR_PATH = "/margot/avatar.png";
var MARGOT_DISPLAY_NAME = "Margot";
var margotSurfaces = {
  "unite-group": {
    project: "unite-group",
    tenantId: "unite-group",
    displayName: "Margot",
    roleLabel: "Personal assistant",
    welcomeMessage: "Hi \u2014 I'm Margot, your Unite-Group personal assistant. Ask about portfolio status, priorities, CRM tasks, or what to route next.",
    scopeLock: "You operate ONLY for Unite-Group portfolio context (founder operations, CRM, command centre, cross-business priorities). Do not answer as RestoreAssist, CARSI, or other portfolio products unless the user explicitly asks for a comparison. Never invent client data.",
    avatarPath: MARGOT_CANONICAL_AVATAR_PATH,
    accentColor: "#1D4ED8"
  },
  restoreassist: {
    project: "restoreassist",
    tenantId: "restoreassist",
    displayName: "Margot",
    roleLabel: "Client help",
    welcomeMessage: "Hi \u2014 I'm Margot, your RestoreAssist client help assistant. Ask how to create reports, manage clients, pricing, workflows, or platform features.",
    scopeLock: "You operate ONLY for RestoreAssist (Australian water-damage restoration platform). Use RestoreAssist features, workflows, and help content only. Do not discuss Unite-Group internal ops, CARSI courses, or unrelated portfolio businesses.",
    avatarPath: MARGOT_CANONICAL_AVATAR_PATH,
    accentColor: "#8A6B4E"
  },
  carsi: {
    project: "carsi",
    tenantId: "carsi",
    displayName: "Margot",
    roleLabel: "Online assistant",
    welcomeMessage: "Hi \u2014 I'm Margot, your CARSI online assistant. Ask about courses, IICRC disciplines, enrolment, certificates, or your learning dashboard.",
    scopeLock: "You operate ONLY for CARSI (carsi.com.au) published courses, LMS flows, and IICRC learning context. Ground course facts in the server-provided catalogue block only. Do not discuss RestoreAssist restoration workflows or Unite-Group internal operations.",
    avatarPath: MARGOT_CANONICAL_AVATAR_PATH,
    accentColor: "#2490ed"
  }
};
function getMargotSurface(project) {
  return margotSurfaces[project];
}
export {
  FORBIDDEN_PRONOUNS,
  MARGOT_CANONICAL_AVATAR_PATH,
  MARGOT_DISPLAY_NAME,
  MARGOT_ELEVENLABS_VOICE_ID,
  brands,
  carsi,
  ccw,
  dr,
  getMargotSurface,
  margotSurfaces,
  nrpg,
  oklchFromHex,
  ra,
  synthex,
  themeFactory,
  unite
};
