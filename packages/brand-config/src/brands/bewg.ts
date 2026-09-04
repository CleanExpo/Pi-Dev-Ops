import { BrandConfig, FORBIDDEN_PRONOUNS } from '../types';

export const bewg: BrandConfig = {
  slug: 'bewg',
  legalName: 'Building Environmental Wellness Group',
  displayName: 'BEWG',
  tagline: 'Independent building science investigation.',
  voice: {
    tone: ['expert', 'authoritative'],
    forbiddenWords: [...FORBIDDEN_PRONOUNS, 'leverage', 'utilise', 'holistic', 'peace of mind'],
    requiredCadence: 'medium',
  },
  colour: {
    primary: '#12475E',     // diagnostic blue — the building
    secondary: '#1C2B33',   // graphite — structural weight
    accent: '#F0A202',      // thermal amber — the finding, never decoration
    neutral: { 50: '#F6F8F9', 100: '#E3EAED', 500: '#6B7D86', 900: '#0C1418' },
    semantic: { success: '#2F8F4E', warning: '#E0A800', danger: '#B23A28' },
    family: 'restoration',
    darkVariant: {
      primary: '#3E9CBF',
      secondary: '#131E24',
      neutral: { 50: '#0C1418', 100: '#131E24', 500: '#9BAAB2', 900: '#F6F8F9' },
    },
  },
  typography: {
    display: { family: 'Inter', weight: 800, src: 'fonts/bewg/Inter-ExtraBold.woff2' },
    body: { family: 'Inter', weight: 400, src: 'fonts/bewg/Inter-Regular.woff2' },
    mono: { family: 'JetBrains Mono', weight: 500, src: 'fonts/bewg/JetBrainsMono-Medium.woff2' },
  },
  logo: {
    primary: 'logos/bewg/primary.svg',
    inverted: 'logos/bewg/inverted.svg',
    icon: 'logos/bewg/icon.svg',
    safeAreaPx: 40,
  },
  motion: {
    durations: { fast: 8, base: 20, slow: 40 },          // frames @ 30fps
    easing: {
      in: 'cubic-bezier(0.22, 1, 0.36, 1)',
      out: 'cubic-bezier(0.64, 0, 0.78, 0)',
      inOut: 'cubic-bezier(0.83, 0, 0.17, 1)',
    },
    signature: 'iris',                                    // measured disclosure — focus tightens onto the finding
    transitionFrames: 16,
  },
  voiceover: {
    elevenLabsVoiceId: 'EXAVITQu4vr4xnSDxMaL',           // neutral AU/UK placeholder
    style: 'narration',
    locale: 'en-AU',
  },
  doNot: [
    'never state a credential, accreditation or capability BEWG has not confirmed',
    'never imply a health or medical conclusion — findings are building conditions, not diagnoses',
    'never use danger red to mark a building finding; severity is amber because it is measured',
    'never claim independence from remediation unless BEWG genuinely does not perform it',
  ],
  audience: {
    primary: 'building owners, strata committees and facility managers (AU)',
    secondary: 'insurers, loss adjusters and construction lawyers',
  },
  defaultChannel: 'linkedin',
};
