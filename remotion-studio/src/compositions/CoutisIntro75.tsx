import React from 'react';
import {
  AbsoluteFill,
  Audio,
  Sequence,
  staticFile,
  interpolate,
  Easing,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import { z } from 'zod';
import { brands } from '../brands';
import type { BrandSlug } from '../brands';
import { signatureEntry, brandFadeIn, staggerStart } from '../motion';

// ── CoutisIntro75 ─────────────────────────────────────────────────────────────
//
// 75-second YouTube explainer introducing John Coutis OAM as host of the
// expanded NRPG industry association. Primary brand = NRPG (the body the
// video is FOR). Spokesperson brand = john-coutis (charcoal + Australian
// gold palette overlay on talking-head scenes only).
//
// HARD CONSTRAINTS (enforced in props / scene-type checks):
//  - No Coutis voice synthesis. Scenes with voiceSpeaker === 'coutis' must
//    receive voiceoverAudioPath only AFTER Coutis records the line.
//    Until then, scenes render silently with on-screen text + B-roll
//    placeholder. See render-blockers in the storyboard JSON.
//  - No Lucide / Material / FontAwesome icons. Geometric SVG marks only.
//  - Verified pricing only: $249/mo, 100 cap, lifetime locked.
//  - The NRPG mark dominates by scene 5; Coutis is the voice carrier, not
//    the hero face above the fold.
//
// Composition file path: src/compositions/CoutisIntro75.tsx
// Storyboard:           src/storyboards/coutis-intro-75-2026-05-11.json
//
// Registered in src/Root.tsx as composition id `CoutisIntro75`.

// ── Schema ────────────────────────────────────────────────────────────────────

export const coutisSceneSchema = z.object({
  sceneId: z.string(),
  sceneType: z.enum([
    'hook-talking-head',
    'supplier-collapse',
    'six-column-build',
    'trio-reveal',
    'founder-tier-scarcity',
    'signoff-talking-head',
    'endcard',
  ]),
  startSec: z.number(),
  durationSec: z.number(),
  paletteBrand: z.enum(['nrpg', 'john-coutis']),
  bgMode: z.enum(['charcoal-solid', 'neutral-solid', 'primary-solid']),
  voiceover: z.string(),
  voiceSpeaker: z.enum(['coutis', 'narrator-placeholder', 'none']),
  voiceoverAudioPath: z.string().nullable().optional(),
  requiresCoutisRecording: z.boolean().optional(),
  onScreenText: z.string(),
  data: z
    .object({
      eyebrow: z.string().optional(),
      chyronLine1: z.string().optional(),
      chyronLine2: z.string().optional(),
      framing: z.string().optional(),
      noLogosYet: z.boolean().optional(),
      suppliers: z.array(z.string()).optional(),
      collapseAtSec: z.number().optional(),
      collapseTarget: z.string().optional(),
      columns: z
        .array(z.object({ n: z.string(), label: z.string() }))
        .optional(),
      buildOrder: z.string().optional(),
      buildStrideSec: z.number().optional(),
      people: z
        .array(
          z.object({
            order: z.number(),
            name: z.string(),
            credential: z.string(),
            appearSec: z.number(),
          }),
        )
        .optional(),
      counter: z.string().optional(),
      url: z.string().optional(),
      accentColorOverride: z.string().optional(),
      pullQuote: z.string().optional(),
      pullQuoteAtSec: z.number().optional(),
      showLogo: z.boolean().optional(),
      logoBrand: z.enum(['nrpg', 'john-coutis']).optional(),
    })
    .optional(),
});

export const coutisIntroSchema = z.object({
  primaryBrand: z.literal('nrpg'),
  spokespersonBrand: z.literal('john-coutis'),
  tagline: z.string(),
  founderTier: z.object({
    priceAudPerMonth: z.number(),
    cap: z.number(),
    rateLocked: z.string(),
    url: z.string(),
  }),
  scenes: z.array(coutisSceneSchema),
});

export type CoutisScene = z.infer<typeof coutisSceneSchema>;
export type CoutisIntroProps = z.infer<typeof coutisIntroSchema>;

// ── Visual primitives ─────────────────────────────────────────────────────────

/** Slow-drifting grid — texture without competing with text. */
const DriftGrid: React.FC<{ color: string; opacity?: number }> = ({
  color,
  opacity = 0.05,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const driftX = interpolate(frame, [0, fps * 60], [0, 80]);
  const driftY = interpolate(frame, [0, fps * 60], [0, 40]);
  return (
    <AbsoluteFill style={{ pointerEvents: 'none', opacity }}>
      <svg width="100%" height="100%" style={{ transform: `translate(${driftX}px, ${driftY}px)` }}>
        <defs>
          <pattern id="cg-grid" x="0" y="0" width="80" height="80" patternUnits="userSpaceOnUse">
            <path d="M 80 0 L 0 0 0 80" fill="none" stroke={color} strokeWidth="1" />
          </pattern>
        </defs>
        <rect x="-100" y="-100" width="120%" height="120%" fill="url(#cg-grid)" />
      </svg>
    </AbsoluteFill>
  );
};

/** Horizontal accent rule that draws in over 0.6s. */
const AccentRule: React.FC<{ color: string; startFrame?: number; width?: number; height?: number }> = ({
  color,
  startFrame = 0,
  width = 240,
  height = 6,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const w = interpolate(
    frame,
    [startFrame, startFrame + fps * 0.6],
    [0, width],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic) },
  );
  return <div style={{ height, width: w, background: color, borderRadius: 2 }} />;
};

/** Coutis lower-third chyron — charcoal block with gold left-rule. */
const CoutisChyron: React.FC<{ line1: string; line2: string }> = ({ line1, line2 }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const opacity = interpolate(frame, [fps * 0.4, fps * 1.0], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  return (
    <div
      style={{
        position: 'absolute',
        left: 112,
        bottom: 96,
        display: 'flex',
        gap: 18,
        alignItems: 'stretch',
        opacity,
      }}
    >
      <div style={{ width: 6, background: '#D4A437' }} />
      <div style={{ background: '#1A1A1A', padding: '18px 28px', minWidth: 320 }}>
        <div
          style={{
            fontFamily: 'Bebas Neue, Inter',
            fontSize: 44,
            fontWeight: 700,
            letterSpacing: '0.02em',
            color: '#F5F0E6',
            lineHeight: 1.0,
            textTransform: 'uppercase',
          }}
        >
          {line1}
        </div>
        <div
          style={{
            fontFamily: 'Inter',
            fontSize: 16,
            fontWeight: 600,
            letterSpacing: '0.18em',
            color: '#D4A437',
            marginTop: 6,
            textTransform: 'uppercase',
          }}
        >
          {line2}
        </div>
      </div>
    </div>
  );
};

/** Quiet brand watermark in bottom-right. */
const BrandWatermark: React.FC<{ brand: BrandSlug }> = ({ brand }) => {
  const cfg = brands[brand];
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const opacity = interpolate(frame, [0, fps * 0.8], [0, 0.55], {
    extrapolateRight: 'clamp',
  });
  return (
    <div
      style={{
        position: 'absolute',
        right: 56,
        bottom: 48,
        display: 'flex',
        alignItems: 'center',
        gap: 12,
        opacity,
        zIndex: 50,
      }}
    >
      <div style={{ width: 14, height: 14, borderRadius: 3, background: cfg.colour.accent }} />
      <div
        style={{
          fontFamily: cfg.typography.body.family,
          fontSize: 20,
          letterSpacing: '0.2em',
          textTransform: 'uppercase',
          color: cfg.colour.family === 'consumer' ? cfg.colour.neutral['50'] : cfg.colour.primary,
          opacity: 0.85,
        }}
      >
        {cfg.displayName}
      </div>
    </div>
  );
};

/** B-roll placeholder for talking-head scenes until Coutis is filmed. */
const CoutisBRollPlaceholder: React.FC<{ framingNote?: string }> = ({ framingNote }) => {
  return (
    <div
      style={{
        position: 'absolute',
        right: 112,
        top: 112,
        bottom: 220,
        width: 720,
        background: '#3A2E1F',
        border: '2px dashed #D4A437',
        borderRadius: 8,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 32,
        textAlign: 'center',
      }}
    >
      <div
        style={{
          fontFamily: 'Bebas Neue, Inter',
          fontSize: 36,
          color: '#D4A437',
          letterSpacing: '0.04em',
        }}
      >
        COUTIS B-ROLL HERE
      </div>
      <div
        style={{
          fontFamily: 'Inter',
          fontSize: 18,
          color: '#F5F0E6',
          marginTop: 16,
          maxWidth: 520,
          lineHeight: 1.5,
        }}
      >
        {framingNote ?? 'chest-up, conversational eye level, charcoal backdrop'}
      </div>
      <div
        style={{
          fontFamily: 'Inter',
          fontSize: 14,
          color: '#E8DFCE',
          marginTop: 24,
          letterSpacing: '0.16em',
          textTransform: 'uppercase',
          opacity: 0.7,
        }}
      >
        Render-blocked until Coutis records
      </div>
    </div>
  );
};

// ── Background resolver per scene ─────────────────────────────────────────────

function sceneBg(scene: CoutisScene): { bg: string; grid: string; fg: string; sub: string } {
  if (scene.paletteBrand === 'john-coutis') {
    // Charcoal hero — Coutis talking-head scenes
    return { bg: '#1A1A1A', grid: '#F5F0E6', fg: '#F5F0E6', sub: '#D4A437' };
  }
  // NRPG palette
  const nrpg = brands.nrpg.colour;
  if (scene.bgMode === 'primary-solid') {
    return { bg: nrpg.primary, grid: nrpg.neutral['50'], fg: nrpg.neutral['50'], sub: nrpg.accent };
  }
  if (scene.bgMode === 'neutral-solid') {
    return { bg: nrpg.neutral['50'], grid: nrpg.neutral['900'], fg: nrpg.neutral['900'], sub: nrpg.primary };
  }
  // charcoal-solid fallback (rare for NRPG)
  return { bg: '#0F1626', grid: nrpg.neutral['50'], fg: nrpg.neutral['50'], sub: nrpg.accent };
}

// ── Scene renderers ───────────────────────────────────────────────────────────

// Coutis motion config — inlined from Synthex/packages/brand-config/src/brands/john-coutis.ts
// (the Pi-Dev-Ops runtime `@unite-group/brand-config` package does not yet include
// john-coutis; that migration is tracked under remotion-brand-codify, out of scope here).
const COUTIS_MOTION = {
  durations: { fast: 12, base: 28, slow: 48 },
  easing: {
    in: 'cubic-bezier(0.22, 1, 0.36, 1)',
    out: 'cubic-bezier(0.4, 0, 0.2, 1)',
    inOut: 'cubic-bezier(0.83, 0, 0.17, 1)',
  },
  signature: 'rise' as const,
  transitionFrames: 20,
};

const HookTalkingHead: React.FC<{ scene: CoutisScene }> = ({ scene }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { bg, grid, fg, sub } = sceneBg(scene);
  // Coutis brand signature is 'rise' — use it
  const entry = signatureEntry({ frame, fps, motion: COUTIS_MOTION }, 0, 80);

  return (
    <AbsoluteFill style={{ background: bg, overflow: 'hidden' }}>
      <DriftGrid color={grid} />
      {/* Left two-thirds = on-screen text. Right third = Coutis B-roll. */}
      <div
        style={{
          position: 'absolute',
          left: 112,
          top: 0,
          bottom: 0,
          width: 960,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
        }}
      >
        <div
          style={{
            fontFamily: 'Inter',
            fontSize: 22,
            color: sub,
            letterSpacing: '0.24em',
            textTransform: 'uppercase',
            marginBottom: 24,
            opacity: entry.opacity,
          }}
        >
          {scene.data?.eyebrow ?? ''}
        </div>
        <div
          style={{
            fontFamily: 'Bebas Neue, Inter',
            fontSize: 132,
            fontWeight: 700,
            color: fg,
            lineHeight: 0.95,
            letterSpacing: '0.02em',
            textTransform: 'uppercase',
            opacity: entry.opacity,
            transform: `translateY(${entry.translateY}px)`,
            whiteSpace: 'pre-line',
          }}
        >
          {scene.onScreenText}
        </div>
        <div style={{ marginTop: 36 }}>
          <AccentRule color={sub} startFrame={Math.round(fps * 0.8)} width={280} height={6} />
        </div>
      </div>
      <CoutisBRollPlaceholder framingNote={scene.data?.framing} />
      {scene.data?.chyronLine1 && scene.data?.chyronLine2 && (
        <CoutisChyron line1={scene.data.chyronLine1} line2={scene.data.chyronLine2} />
      )}
    </AbsoluteFill>
  );
};

const SupplierCollapse: React.FC<{ scene: CoutisScene }> = ({ scene }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { bg, grid, fg, sub } = sceneBg(scene);
  const suppliers = scene.data?.suppliers ?? [];
  const collapseStart = Math.round((scene.data?.collapseAtSec ?? 8.5) * fps) - Math.round(scene.startSec * fps);
  const collapseT = interpolate(frame, [collapseStart, collapseStart + fps * 1.2], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.inOut(Easing.cubic),
  });

  return (
    <AbsoluteFill style={{ background: bg, overflow: 'hidden' }}>
      <DriftGrid color={grid} />
      <AbsoluteFill style={{ padding: '120px 112px', flexDirection: 'column', justifyContent: 'center' }}>
        <div
          style={{
            fontFamily: 'Inter',
            fontSize: 22,
            color: sub,
            letterSpacing: '0.24em',
            textTransform: 'uppercase',
            marginBottom: 32,
          }}
        >
          {scene.data?.eyebrow ?? ''}
        </div>
        <div
          style={{
            fontFamily: 'Inter',
            fontWeight: 800,
            fontSize: 56,
            color: fg,
            lineHeight: 1.15,
            letterSpacing: '-0.01em',
            maxWidth: 1500,
            whiteSpace: 'pre-line',
            marginBottom: 56,
          }}
        >
          {scene.onScreenText}
        </div>
        {/* Six supplier chips — collapse toward a single NRPG mark at collapseStart */}
        <div
          style={{
            display: 'flex',
            gap: 24,
            justifyContent: 'flex-start',
            flexWrap: 'wrap',
          }}
        >
          {suppliers.map((s, i) => {
            const enter = brandFadeIn({ frame, fps, motion: brands.nrpg.motion }, staggerStart(8, i, 4));
            // Each chip drifts toward center as collapseT rises
            const centerX = 540 - i * 220;
            return (
              <div
                key={i}
                style={{
                  padding: '18px 28px',
                  border: `2px solid ${sub}`,
                  borderRadius: 4,
                  color: fg,
                  fontFamily: 'Inter',
                  fontWeight: 700,
                  fontSize: 24,
                  letterSpacing: '0.08em',
                  textTransform: 'uppercase',
                  opacity: enter * (1 - collapseT * 0.85),
                  transform: `translateX(${collapseT * centerX}px) scale(${1 - collapseT * 0.4})`,
                  transformOrigin: 'center',
                }}
              >
                {s}
              </div>
            );
          })}
        </div>
        {/* NRPG mark appearing at the collapse target */}
        <div
          style={{
            position: 'absolute',
            left: '50%',
            top: '62%',
            transform: `translate(-50%, -50%) scale(${0.4 + collapseT * 0.6})`,
            opacity: collapseT,
            display: 'flex',
            alignItems: 'center',
            gap: 18,
          }}
        >
          <svg width={88} height={88} viewBox="0 0 88 88">
            <rect x="6" y="6" width="76" height="76" rx="6" fill={sub} />
            <path d="M 24 56 L 24 28 L 44 56 L 44 28 L 64 56 L 64 28" stroke={bg} strokeWidth="6" fill="none" strokeLinecap="square" />
          </svg>
          <div
            style={{
              fontFamily: 'Inter',
              fontSize: 56,
              fontWeight: 800,
              color: fg,
              letterSpacing: '0.04em',
            }}
          >
            NRPG
          </div>
        </div>
      </AbsoluteFill>
      <BrandWatermark brand="nrpg" />
    </AbsoluteFill>
  );
};

const SixColumnBuild: React.FC<{ scene: CoutisScene }> = ({ scene }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { bg, grid, fg, sub } = sceneBg(scene);
  const columns = scene.data?.columns ?? [];
  const stride = (scene.data?.buildStrideSec ?? 1.5) * fps;

  return (
    <AbsoluteFill style={{ background: bg, overflow: 'hidden' }}>
      <DriftGrid color={grid} opacity={0.08} />
      <AbsoluteFill style={{ padding: '112px 112px', flexDirection: 'column', justifyContent: 'center' }}>
        <div
          style={{
            fontFamily: 'Inter',
            fontSize: 22,
            color: sub,
            letterSpacing: '0.24em',
            textTransform: 'uppercase',
            marginBottom: 28,
          }}
        >
          {scene.data?.eyebrow ?? ''}
        </div>
        <div
          style={{
            fontFamily: 'Inter',
            fontWeight: 800,
            fontSize: 88,
            color: fg,
            lineHeight: 1.05,
            letterSpacing: '-0.02em',
            marginBottom: 64,
          }}
        >
          {scene.onScreenText}
        </div>
        <div style={{ display: 'flex', gap: 18, alignItems: 'stretch' }}>
          {columns.map((c, i) => {
            const enter = brandFadeIn(
              { frame, fps, motion: brands.nrpg.motion },
              Math.round(i * stride),
            );
            return (
              <div
                key={c.n}
                style={{
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'flex-start',
                  borderTop: `4px solid ${sub}`,
                  paddingTop: 24,
                  opacity: enter,
                  transform: `translateY(${(1 - enter) * 32}px)`,
                }}
              >
                <div
                  style={{
                    fontFamily: 'Inter',
                    fontSize: 18,
                    fontWeight: 700,
                    color: sub,
                    letterSpacing: '0.16em',
                    marginBottom: 12,
                  }}
                >
                  {c.n}
                </div>
                <div
                  style={{
                    fontFamily: 'Inter',
                    fontWeight: 800,
                    fontSize: 36,
                    letterSpacing: '0.02em',
                    color: fg,
                    textTransform: 'uppercase',
                  }}
                >
                  {c.label}
                </div>
              </div>
            );
          })}
        </div>
      </AbsoluteFill>
      <BrandWatermark brand="nrpg" />
    </AbsoluteFill>
  );
};

const TrioReveal: React.FC<{ scene: CoutisScene }> = ({ scene }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { bg, grid, fg, sub } = sceneBg(scene);
  const people = scene.data?.people ?? [];

  return (
    <AbsoluteFill style={{ background: bg, overflow: 'hidden' }}>
      <DriftGrid color={grid} />
      <AbsoluteFill style={{ padding: '112px', flexDirection: 'column', justifyContent: 'center' }}>
        <div
          style={{
            fontFamily: 'Inter',
            fontSize: 22,
            color: sub,
            letterSpacing: '0.24em',
            textTransform: 'uppercase',
            marginBottom: 28,
          }}
        >
          {scene.data?.eyebrow ?? ''}
        </div>
        <div
          style={{
            fontFamily: 'Inter',
            fontWeight: 800,
            fontSize: 88,
            color: fg,
            lineHeight: 1.05,
            letterSpacing: '-0.02em',
            marginBottom: 64,
          }}
        >
          {scene.onScreenText}
        </div>
        <div style={{ display: 'flex', gap: 48, alignItems: 'flex-start' }}>
          {people.map((p) => {
            const appear = Math.round(p.appearSec * fps);
            const enter = brandFadeIn({ frame, fps, motion: brands.nrpg.motion }, appear);
            return (
              <div
                key={p.order}
                style={{
                  flex: 1,
                  opacity: enter,
                  transform: `translateY(${(1 - enter) * 24}px)`,
                }}
              >
                <div
                  style={{
                    width: 96,
                    height: 96,
                    borderRadius: '50%',
                    background: brands.nrpg.colour.neutral['100'],
                    border: `3px solid ${sub}`,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontFamily: 'Inter',
                    fontSize: 32,
                    fontWeight: 800,
                    color: sub,
                    marginBottom: 20,
                  }}
                >
                  {p.order}
                </div>
                <div
                  style={{
                    fontFamily: 'Inter',
                    fontWeight: 800,
                    fontSize: 36,
                    color: fg,
                    letterSpacing: '-0.01em',
                    lineHeight: 1.15,
                    marginBottom: 10,
                  }}
                >
                  {p.name}
                </div>
                <div
                  style={{
                    fontFamily: 'Inter',
                    fontSize: 22,
                    color: brands.nrpg.colour.neutral['500'],
                    lineHeight: 1.35,
                  }}
                >
                  {p.credential}
                </div>
              </div>
            );
          })}
        </div>
      </AbsoluteFill>
      <BrandWatermark brand="nrpg" />
    </AbsoluteFill>
  );
};

const FounderTierScarcity: React.FC<{ scene: CoutisScene }> = ({ scene }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { bg, grid, fg } = sceneBg(scene);
  // CANONICAL: Candy Red #b30000 (Unite-Group token, candy-red-canonical
  // 2026-05-11 opus-fix) is the scarcity accent for Founder-tier scenes —
  // overrides the earlier gold #D4A437 / NRPG-accent #F2B33D treatment.
  const scarcityAccent = scene.data?.accentColorOverride ?? '#b30000';
  const entry = signatureEntry({ frame, fps, motion: brands.nrpg.motion }, 0, 60);
  // Counter "00 of 100 claimed" — for the canonical asset the counter is static
  // at "00" because the video is rendered pre-launch; a dynamic counter would
  // require a render-per-update pipeline (out of scope for Wave 4).

  return (
    <AbsoluteFill style={{ background: bg, overflow: 'hidden' }}>
      <DriftGrid color={grid} opacity={0.08} />
      <AbsoluteFill style={{ padding: '112px', flexDirection: 'column', justifyContent: 'center' }}>
        <div
          style={{
            fontFamily: 'Inter',
            fontSize: 22,
            color: scarcityAccent,
            letterSpacing: '0.24em',
            textTransform: 'uppercase',
            marginBottom: 28,
            opacity: entry.opacity,
          }}
        >
          {scene.data?.eyebrow ?? ''}
        </div>
        <div
          style={{
            fontFamily: 'Inter',
            fontWeight: 800,
            fontSize: 120,
            color: fg,
            lineHeight: 1.0,
            letterSpacing: '-0.02em',
            whiteSpace: 'pre-line',
            opacity: entry.opacity,
            transform: `translateY(${entry.translateY}px)`,
            marginBottom: 48,
          }}
        >
          {scene.onScreenText}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 32, marginBottom: 32 }}>
          <AccentRule color={scarcityAccent} startFrame={Math.round(fps * 0.6)} width={420} height={8} />
        </div>
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 24 }}>
          <div
            style={{
              fontFamily: 'Inter',
              fontWeight: 800,
              fontSize: 56,
              color: scarcityAccent,
              letterSpacing: '-0.01em',
            }}
          >
            {scene.data?.counter ?? '00 of 100 claimed'}
          </div>
          <div
            style={{
              fontFamily: 'Inter',
              fontSize: 28,
              color: brands.nrpg.colour.neutral['50'],
              opacity: 0.85,
              letterSpacing: '0.06em',
            }}
          >
            {scene.data?.url ?? ''}
          </div>
        </div>
      </AbsoluteFill>
      <BrandWatermark brand="nrpg" />
    </AbsoluteFill>
  );
};

const SignoffTalkingHead: React.FC<{ scene: CoutisScene }> = ({ scene }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { bg, grid, fg, sub } = sceneBg(scene);
  const pullQuoteStart = Math.round((scene.data?.pullQuoteAtSec ?? 8) * fps);
  const pullQuoteOpacity = interpolate(
    frame,
    [pullQuoteStart, pullQuoteStart + fps * 0.6],
    [0, 1],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' },
  );

  return (
    <AbsoluteFill style={{ background: bg, overflow: 'hidden' }}>
      <DriftGrid color={grid} />
      {/* Coutis on the right, pull-quote left */}
      <div
        style={{
          position: 'absolute',
          left: 112,
          top: 0,
          bottom: 0,
          width: 960,
          display: 'flex',
          flexDirection: 'column',
          justifyContent: 'center',
          opacity: pullQuoteOpacity,
        }}
      >
        <div
          style={{
            width: 4,
            background: sub,
            height: 80,
            marginBottom: 24,
          }}
        />
        <div
          style={{
            fontFamily: 'Inter',
            fontSize: 28,
            color: sub,
            letterSpacing: '0.04em',
            fontStyle: 'italic',
            fontWeight: 500,
            lineHeight: 1.4,
            maxWidth: 720,
            marginBottom: 32,
          }}
        >
          {scene.data?.pullQuote ?? ''}
        </div>
        <div
          style={{
            fontFamily: 'Inter',
            fontSize: 16,
            fontWeight: 600,
            letterSpacing: '0.2em',
            color: fg,
            textTransform: 'uppercase',
            opacity: 0.7,
          }}
        >
          John Coutis OAM
        </div>
      </div>
      <CoutisBRollPlaceholder framingNote={scene.data?.framing} />
    </AbsoluteFill>
  );
};

const Endcard: React.FC<{ scene: CoutisScene }> = ({ scene }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const { bg, grid, fg, sub } = sceneBg(scene);
  const entry = signatureEntry({ frame, fps, motion: brands.nrpg.motion }, 0, 40);

  return (
    <AbsoluteFill style={{ background: bg, overflow: 'hidden' }}>
      <DriftGrid color={grid} opacity={0.07} />
      <AbsoluteFill
        style={{
          alignItems: 'center',
          justifyContent: 'center',
          flexDirection: 'column',
          padding: 96,
        }}
      >
        {/* NRPG mark — geometric, no Lucide */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 24,
            opacity: entry.opacity,
            transform: `translateY(${entry.translateY}px)`,
            marginBottom: 40,
          }}
        >
          <svg width={120} height={120} viewBox="0 0 120 120">
            <rect x="8" y="8" width="104" height="104" rx="8" fill={sub} />
            <path
              d="M 32 80 L 32 40 L 60 80 L 60 40 L 88 80 L 88 40"
              stroke={bg}
              strokeWidth="8"
              fill="none"
              strokeLinecap="square"
            />
          </svg>
          <div
            style={{
              fontFamily: 'Inter',
              fontWeight: 800,
              fontSize: 88,
              color: fg,
              letterSpacing: '0.04em',
            }}
          >
            NRPG
          </div>
        </div>
        <div
          style={{
            fontFamily: 'Inter',
            fontWeight: 700,
            fontSize: 48,
            color: fg,
            letterSpacing: '-0.01em',
            opacity: entry.opacity,
            marginBottom: 32,
          }}
        >
          {scene.onScreenText}
        </div>
        <div style={{ marginBottom: 32 }}>
          <AccentRule color={sub} startFrame={Math.round(fps * 0.4)} width={280} height={6} />
        </div>
        <div
          style={{
            fontFamily: 'Inter',
            fontSize: 28,
            color: sub,
            letterSpacing: '0.12em',
          }}
        >
          {scene.data?.url ?? ''}
        </div>
      </AbsoluteFill>
    </AbsoluteFill>
  );
};

// ── Default props (used by Remotion Studio preview) ──────────────────────────
//
// Mirrors src/storyboards/coutis-intro-75-2026-05-11.json. Keep in sync; the
// JSON is the source of truth for the actual render — these defaults exist so
// `npm start` previews this composition without an external props file.

export const defaultCoutisIntroProps: CoutisIntroProps = {
  primaryBrand: 'nrpg',
  spokespersonBrand: 'john-coutis',
  tagline: 'The peak body that runs jobs.',
  founderTier: { priceAudPerMonth: 249, cap: 100, rateLocked: 'lifetime', url: 'unitegroup.in/association' },
  scenes: [
    {
      sceneId: 'hook-coutis-coldopen',
      sceneType: 'hook-talking-head',
      startSec: 0,
      durationSec: 5,
      paletteBrand: 'john-coutis',
      bgMode: 'charcoal-solid',
      voiceover: 'Six suppliers, one job. You already pay them all.',
      voiceSpeaker: 'coutis',
      voiceoverAudioPath: null,
      requiresCoutisRecording: true,
      onScreenText: 'SIX SUPPLIERS,\nONE JOB.',
      data: {
        eyebrow: 'John Coutis OAM',
        chyronLine1: 'JOHN COUTIS',
        chyronLine2: 'OAM',
        framing: 'chest-up, conversational eye level, charcoal backdrop',
        noLogosYet: true,
      },
    },
    {
      sceneId: 'problem-six-suppliers',
      sceneType: 'supplier-collapse',
      startSec: 5,
      durationSec: 10,
      paletteBrand: 'nrpg',
      bgMode: 'neutral-solid',
      voiceover:
        'Australian restoration firms pay six suppliers to do the work of one peak body. Cert. Leads. Marketing. Software. Insurance. Equipment.',
      voiceSpeaker: 'narrator-placeholder',
      voiceoverAudioPath: null,
      onScreenText: 'Six invoices.\nSix counter-parties.\nSix points of failure.',
      data: {
        eyebrow: 'The Six-Supplier Tax',
        suppliers: ['Cert', 'Leads', 'Marketing', 'Software', 'Insurance', 'Equipment'],
        collapseAtSec: 8.5,
        collapseTarget: 'NRPG mark',
      },
    },
    {
      sceneId: 'moat-member-as-a-service',
      sceneType: 'six-column-build',
      startSec: 15,
      durationSec: 15,
      paletteBrand: 'nrpg',
      bgMode: 'primary-solid',
      voiceover:
        'The expanded NRPG association bundles every one of those suppliers into one membership. Member-as-a-Service. Cert held to international benchmark. Jobs routed to certified firms. Marketing run for the trade, not by the trade.',
      voiceSpeaker: 'narrator-placeholder',
      voiceoverAudioPath: null,
      onScreenText: 'Member-as-a-Service.',
      data: {
        eyebrow: 'What The Association Does',
        columns: [
          { n: '01', label: 'CERT' },
          { n: '02', label: 'LEADS' },
          { n: '03', label: 'MARKETING' },
          { n: '04', label: 'SOFTWARE' },
          { n: '05', label: 'INSURANCE' },
          { n: '06', label: 'EQUIPMENT' },
        ],
        buildOrder: 'stagger-left-to-right',
        buildStrideSec: 1.5,
      },
    },
    {
      sceneId: 'founding-trio',
      sceneType: 'trio-reveal',
      startSec: 30,
      durationSec: 15,
      paletteBrand: 'nrpg',
      bgMode: 'neutral-solid',
      voiceover:
        'Founded by three people. Phill McGurk, Unite-Group. Toby Bredhauer, Carpet Cleaners Warehouse, national equipment distribution. John Coutis OAM, Order of Australia Medal recipient, twenty-five-year keynote speaker, audience of six million worldwide.',
      voiceSpeaker: 'narrator-placeholder',
      voiceoverAudioPath: null,
      onScreenText: 'Founding partners.',
      data: {
        eyebrow: 'Founding Partners',
        people: [
          { order: 1, name: 'PHILL McGURK', credential: 'Unite-Group · NRPG', appearSec: 1.0 },
          { order: 2, name: 'TOBY BREDHAUER', credential: 'Carpet Cleaners Warehouse', appearSec: 5.5 },
          { order: 3, name: 'JOHN COUTIS OAM', credential: 'Order of Australia Medal · 25-yr keynote', appearSec: 10.0 },
        ],
      },
    },
    {
      sceneId: 'the-ask-founder-tier',
      sceneType: 'founder-tier-scarcity',
      startSec: 45,
      durationSec: 15,
      paletteBrand: 'nrpg',
      bgMode: 'primary-solid',
      voiceover:
        'Founder tier opens today. One hundred places. Two hundred and forty-nine dollars per month. Locked at that rate for life. The cap is small so the founding cohort actually steers year-one decisions. Link in the description.',
      voiceSpeaker: 'narrator-placeholder',
      voiceoverAudioPath: null,
      onScreenText: '100 places.\n$249 / month.\nLocked for life.',
      data: {
        eyebrow: 'Founder Tier — Wave 0',
        counter: '00 of 100 claimed',
        url: 'unitegroup.in/association',
        accentColorOverride: '#b30000',
      },
    },
    {
      sceneId: 'coutis-signoff',
      sceneType: 'signoff-talking-head',
      startSec: 60,
      durationSec: 12,
      paletteBrand: 'john-coutis',
      bgMode: 'charcoal-solid',
      voiceover:
        'One body. One membership. One hundred founder places. If you run a crew in this country, this was built for you. Link below.',
      voiceSpeaker: 'coutis',
      voiceoverAudioPath: null,
      requiresCoutisRecording: true,
      onScreenText: '',
      data: {
        eyebrow: 'John Coutis OAM',
        framing:
          'chest-up, conversational eye level, charcoal backdrop, final beat of held silence before cut',
        pullQuoteAtSec: 8.0,
        pullQuote: 'Built for the people who run the jobs.',
      },
    },
    {
      sceneId: 'endcard',
      sceneType: 'endcard',
      startSec: 72,
      durationSec: 3,
      paletteBrand: 'nrpg',
      bgMode: 'primary-solid',
      voiceover: '',
      voiceSpeaker: 'none',
      voiceoverAudioPath: null,
      onScreenText: 'The peak body that runs jobs.',
      data: { eyebrow: 'NRPG', url: 'unitegroup.in/association', showLogo: true, logoBrand: 'nrpg' },
    },
  ],
};

// ── Main composition ─────────────────────────────────────────────────────────

export const CoutisIntro75: React.FC<CoutisIntroProps> = ({ scenes }) => {
  const { fps } = useVideoConfig();
  let cursor = 0;
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      {scenes.map((scene) => {
        const start = cursor;
        const dur = Math.max(1, Math.round(scene.durationSec * fps));
        cursor += dur;
        const SceneComponent =
          scene.sceneType === 'hook-talking-head'
            ? HookTalkingHead
            : scene.sceneType === 'supplier-collapse'
            ? SupplierCollapse
            : scene.sceneType === 'six-column-build'
            ? SixColumnBuild
            : scene.sceneType === 'trio-reveal'
            ? TrioReveal
            : scene.sceneType === 'founder-tier-scarcity'
            ? FounderTierScarcity
            : scene.sceneType === 'signoff-talking-head'
            ? SignoffTalkingHead
            : Endcard;
        return (
          <Sequence key={scene.sceneId} from={start} durationInFrames={dur} name={scene.sceneId}>
            <SceneComponent scene={scene} />
            {scene.voiceoverAudioPath ? (
              <Audio src={staticFile(scene.voiceoverAudioPath)} />
            ) : null}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
