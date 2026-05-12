import React from 'react';
import {
  AbsoluteFill,
  Audio,
  Img,
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
import { readableOn, brandGradient } from '../colour';

// ── Schema ──────────────────────────────────────────────────────────────────
//
// A scene now has an optional structured `data` blob that the visual
// renderer for its sceneType reads. Keeps backward compat: storyboards from
// before today still work because the schema fields are all optional.

export const explainerSceneSchema = z.object({
  sceneId: z.string(),
  sceneType: z
    .enum(['hook', 'body', 'cta', 'stat', 'flow', 'comparison', 'keypoints', 'screenshot'])
    .optional(),
  durationSec: z.number(),
  voiceover: z.string(),
  onScreenText: z.string(),
  voiceoverAudioPath: z.string().optional(),
  data: z
    .object({
      stats: z
        .array(z.object({ value: z.string(), label: z.string() }))
        .optional(),
      flowSteps: z.array(z.string()).optional(),
      comparisonRows: z
        .array(z.object({ them: z.string(), us: z.string() }))
        .optional(),
      keypoints: z.array(z.string()).optional(),
      eyebrow: z.string().optional(),
      footnote: z.string().optional(),
      screenshotSrc: z.string().optional(),
      caption: z.string().optional(),
    })
    .optional(),
});

export const explainerSchema = z.object({
  brand: z.enum(['dr', 'nrpg', 'ra', 'carsi', 'ccw', 'synthex', 'unite']),
  storyboard: z.array(explainerSceneSchema),
  hookSec: z.number(),
  ctaSec: z.number(),
});

export type ExplainerScene = z.infer<typeof explainerSceneSchema>;
export type ExplainerProps = z.infer<typeof explainerSchema>;

// Picks a sceneType when the storyboard didn't set one explicitly.
function resolveSceneType(scene: ExplainerScene): NonNullable<ExplainerScene['sceneType']> {
  if (scene.sceneType) return scene.sceneType;
  if (scene.sceneId === 'hook') return 'hook';
  if (scene.sceneId === 'cta') return 'cta';
  if (scene.sceneId.startsWith('stat')) return 'stat';
  if (scene.sceneId.startsWith('flow')) return 'flow';
  if (scene.sceneId.startsWith('compare')) return 'comparison';
  if (scene.sceneId.startsWith('key')) return 'keypoints';
  return 'body';
}

// ── Visual primitives ──────────────────────────────────────────────────────

/** Slow-drifting grid pattern. Adds visual texture without competing with text. */
const AnimatedGrid: React.FC<{ color: string; opacity?: number }> = ({
  color,
  opacity = 0.06,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const driftX = interpolate(frame, [0, fps * 60], [0, 80]);
  const driftY = interpolate(frame, [0, fps * 60], [0, 40]);
  return (
    <AbsoluteFill style={{ pointerEvents: 'none', opacity }}>
      <svg width="100%" height="100%" style={{ transform: `translate(${driftX}px, ${driftY}px)` }}>
        <defs>
          <pattern id="agrid" x="0" y="0" width="80" height="80" patternUnits="userSpaceOnUse">
            <path d="M 80 0 L 0 0 0 80" fill="none" stroke={color} strokeWidth="1" />
          </pattern>
        </defs>
        <rect x="-100" y="-100" width="120%" height="120%" fill="url(#agrid)" />
      </svg>
    </AbsoluteFill>
  );
};

/** Soft blurred accent orbs that drift across the frame. Adds depth. */
const DriftOrbs: React.FC<{ accent: string; primary: string }> = ({ accent, primary }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const t = frame / fps;
  const o1x = 200 + Math.sin(t * 0.4) * 240;
  const o1y = 800 + Math.cos(t * 0.3) * 80;
  const o2x = 1500 + Math.cos(t * 0.5) * 200;
  const o2y = 200 + Math.sin(t * 0.4) * 100;
  return (
    <AbsoluteFill style={{ pointerEvents: 'none' }}>
      <div
        style={{
          position: 'absolute',
          left: o1x,
          top: o1y,
          width: 400,
          height: 400,
          borderRadius: '50%',
          background: accent,
          filter: 'blur(120px)',
          opacity: 0.18,
        }}
      />
      <div
        style={{
          position: 'absolute',
          left: o2x,
          top: o2y,
          width: 500,
          height: 500,
          borderRadius: '50%',
          background: primary,
          filter: 'blur(140px)',
          opacity: 0.22,
        }}
      />
    </AbsoluteFill>
  );
};

/** Brand watermark in bottom-right corner. Quiet but always present. */
const BrandWatermark: React.FC<{ brand: BrandSlug }> = ({ brand }) => {
  const cfg = brands[brand];
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const opacity = interpolate(frame, [0, fps * 0.8], [0, 0.6], {
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
      <div
        style={{
          width: 16,
          height: 16,
          borderRadius: 4,
          background: cfg.colour.accent,
        }}
      />
      <div
        style={{
          fontFamily: cfg.typography.body.family,
          fontSize: 22,
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
          color: cfg.colour.neutral['50'],
          opacity: 0.85,
        }}
      >
        {cfg.displayName}
      </div>
    </div>
  );
};

/** Animated horizontal accent rule that draws in. */
const AccentRule: React.FC<{ color: string; startFrame?: number; width?: number }> = ({
  color,
  startFrame = 0,
  width = 240,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const w = interpolate(
    frame,
    [startFrame, startFrame + fps * 0.6],
    [0, width],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp', easing: Easing.out(Easing.cubic) },
  );
  return (
    <div
      style={{
        height: 8,
        width: w,
        background: color,
        borderRadius: 4,
      }}
    />
  );
};

/** Common scene wrapper · provides background, animated bg layers, watermark. */
const SceneFrame: React.FC<{
  brand: BrandSlug;
  bgMode: 'gradient' | 'solid-secondary' | 'solid-neutral';
  children: React.ReactNode;
}> = ({ brand, bgMode, children }) => {
  const cfg = brands[brand];
  const bg =
    bgMode === 'gradient'
      ? brandGradient(cfg.colour, 135)
      : bgMode === 'solid-secondary'
      ? cfg.colour.secondary
      : cfg.colour.neutral['50'];
  const gridColor =
    bgMode === 'solid-neutral' ? cfg.colour.neutral['900'] : cfg.colour.neutral['50'];
  return (
    <AbsoluteFill style={{ background: bg, overflow: 'hidden' }}>
      <AnimatedGrid color={gridColor} />
      {bgMode !== 'solid-neutral' && (
        <DriftOrbs accent={cfg.colour.accent} primary={cfg.colour.primary} />
      )}
      {children}
      <BrandWatermark brand={brand} />
    </AbsoluteFill>
  );
};

// ── Scene components ───────────────────────────────────────────────────────

const Hook: React.FC<{ scene: ExplainerScene; brand: BrandSlug }> = ({ scene, brand }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const cfg = brands[brand];
  const entry = signatureEntry({ frame, fps, motion: cfg.motion }, 0, 100);
  const fg = readableOn(cfg.colour.primary, cfg.colour);
  const eyebrow = scene.data?.eyebrow;

  return (
    <SceneFrame brand={brand} bgMode="gradient">
      <AbsoluteFill
        style={{
          alignItems: 'center',
          justifyContent: 'center',
          padding: 96,
        }}
      >
        <div
          style={{
            transform: `translate(${entry.translateX}px, ${entry.translateY}px) scale(${entry.scale})`,
            opacity: entry.opacity,
            color: fg,
            textAlign: 'center',
            maxWidth: 1600,
          }}
        >
          {eyebrow && (
            <div
              style={{
                fontFamily: cfg.typography.body.family,
                fontSize: 28,
                letterSpacing: '0.24em',
                textTransform: 'uppercase',
                marginBottom: 28,
                opacity: 0.85,
              }}
            >
              {eyebrow}
            </div>
          )}
          <div
            style={{
              fontFamily: cfg.typography.display.family,
              fontWeight: cfg.typography.display.weight,
              fontSize: 104,
              lineHeight: 1.05,
              letterSpacing: '-0.02em',
            }}
          >
            {scene.onScreenText}
          </div>
          <div style={{ marginTop: 44, display: 'flex', justifyContent: 'center' }}>
            <AccentRule color={cfg.colour.accent} startFrame={Math.round(fps * 0.6)} width={320} />
          </div>
        </div>
      </AbsoluteFill>
    </SceneFrame>
  );
};

const Body: React.FC<{ scene: ExplainerScene; brand: BrandSlug }> = ({ scene, brand }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const cfg = brands[brand];
  const motion = { frame, fps, motion: cfg.motion };
  const titleEntry = signatureEntry(motion, 4, 60);
  const lineFade = brandFadeIn(motion, staggerStart(16, 0, 6));
  const eyebrow = scene.data?.eyebrow ?? `${cfg.displayName} — ${cfg.tagline}`;

  return (
    <SceneFrame brand={brand} bgMode="solid-neutral">
      <AbsoluteFill
        style={{
          padding: '120px 120px 160px',
          flexDirection: 'column',
          justifyContent: 'center',
        }}
      >
        <div
          style={{
            color: cfg.colour.primary,
            fontFamily: cfg.typography.display.family,
            fontWeight: cfg.typography.display.weight,
            fontSize: 36,
            letterSpacing: '0.18em',
            textTransform: 'uppercase',
            marginBottom: 28,
            opacity: titleEntry.opacity,
            transform: `translateX(${titleEntry.translateX}px)`,
          }}
        >
          {eyebrow}
        </div>
        <div
          style={{
            color: cfg.colour.neutral['900'],
            fontFamily: cfg.typography.display.family,
            fontWeight: cfg.typography.display.weight,
            fontSize: 78,
            lineHeight: 1.15,
            letterSpacing: '-0.01em',
            maxWidth: 1500,
            opacity: lineFade,
          }}
        >
          {scene.onScreenText}
        </div>
        <div style={{ marginTop: 40 }}>
          <AccentRule color={cfg.colour.accent} startFrame={Math.round(fps * 0.4)} width={280} />
        </div>
        {scene.data?.footnote && (
          <div
            style={{
              marginTop: 40,
              fontFamily: cfg.typography.body.family,
              fontSize: 28,
              color: cfg.colour.neutral['500'],
              opacity: lineFade,
            }}
          >
            {scene.data.footnote}
          </div>
        )}
      </AbsoluteFill>
    </SceneFrame>
  );
};

const StatScene: React.FC<{ scene: ExplainerScene; brand: BrandSlug }> = ({ scene, brand }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const cfg = brands[brand];
  const stats = scene.data?.stats ?? [];
  const eyebrow = scene.data?.eyebrow;

  return (
    <SceneFrame brand={brand} bgMode="solid-neutral">
      <AbsoluteFill
        style={{
          padding: 120,
          flexDirection: 'column',
          justifyContent: 'center',
        }}
      >
        {eyebrow && (
          <div
            style={{
              color: cfg.colour.primary,
              fontFamily: cfg.typography.display.family,
              fontSize: 36,
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              marginBottom: 24,
            }}
          >
            {eyebrow}
          </div>
        )}
        <div
          style={{
            color: cfg.colour.neutral['900'],
            fontFamily: cfg.typography.display.family,
            fontWeight: cfg.typography.display.weight,
            fontSize: 56,
            letterSpacing: '-0.01em',
            marginBottom: 56,
            maxWidth: 1500,
          }}
        >
          {scene.onScreenText}
        </div>
        <div style={{ display: 'flex', gap: 32 }}>
          {stats.map((s, i) => {
            const enter = brandFadeIn({ frame, fps, motion: cfg.motion }, staggerStart(8, i, 6));
            return (
              <div
                key={i}
                style={{
                  flex: 1,
                  background: '#FFFFFF',
                  border: `1px solid ${cfg.colour.neutral['100']}`,
                  borderLeft: `8px solid ${cfg.colour.accent}`,
                  borderRadius: 12,
                  padding: '40px 36px',
                  opacity: enter,
                  transform: `translateY(${(1 - enter) * 24}px)`,
                  boxShadow: '0 10px 40px rgba(0,0,0,0.04)',
                }}
              >
                <div
                  style={{
                    fontFamily: cfg.typography.display.family,
                    fontWeight: cfg.typography.display.weight,
                    fontSize: 96,
                    color: cfg.colour.primary,
                    lineHeight: 1,
                    letterSpacing: '-0.03em',
                  }}
                >
                  {s.value}
                </div>
                <div
                  style={{
                    fontFamily: cfg.typography.body.family,
                    fontSize: 26,
                    color: cfg.colour.neutral['900'],
                    marginTop: 16,
                    lineHeight: 1.3,
                  }}
                >
                  {s.label}
                </div>
              </div>
            );
          })}
        </div>
      </AbsoluteFill>
    </SceneFrame>
  );
};

const FlowScene: React.FC<{ scene: ExplainerScene; brand: BrandSlug }> = ({ scene, brand }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const cfg = brands[brand];
  const steps = scene.data?.flowSteps ?? [];
  const eyebrow = scene.data?.eyebrow;

  return (
    <SceneFrame brand={brand} bgMode="solid-neutral">
      <AbsoluteFill
        style={{
          padding: 120,
          flexDirection: 'column',
          justifyContent: 'center',
        }}
      >
        {eyebrow && (
          <div
            style={{
              color: cfg.colour.primary,
              fontFamily: cfg.typography.display.family,
              fontSize: 36,
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              marginBottom: 24,
            }}
          >
            {eyebrow}
          </div>
        )}
        <div
          style={{
            color: cfg.colour.neutral['900'],
            fontFamily: cfg.typography.display.family,
            fontWeight: cfg.typography.display.weight,
            fontSize: 56,
            letterSpacing: '-0.01em',
            marginBottom: 64,
            maxWidth: 1500,
          }}
        >
          {scene.onScreenText}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 16, justifyContent: 'space-between' }}>
          {steps.map((s, i) => {
            const enter = brandFadeIn({ frame, fps, motion: cfg.motion }, staggerStart(6, i, 5));
            return (
              <React.Fragment key={i}>
                <div
                  style={{
                    flex: 1,
                    minWidth: 0,
                    opacity: enter,
                    transform: `translateY(${(1 - enter) * 16}px)`,
                  }}
                >
                  <div
                    style={{
                      width: 56,
                      height: 56,
                      borderRadius: '50%',
                      background: cfg.colour.primary,
                      color: cfg.colour.neutral['50'],
                      fontFamily: cfg.typography.display.family,
                      fontWeight: cfg.typography.display.weight,
                      fontSize: 28,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      marginBottom: 20,
                    }}
                  >
                    {i + 1}
                  </div>
                  <div
                    style={{
                      fontFamily: cfg.typography.display.family,
                      fontWeight: cfg.typography.display.weight,
                      fontSize: 32,
                      lineHeight: 1.2,
                      color: cfg.colour.neutral['900'],
                    }}
                  >
                    {s}
                  </div>
                </div>
                {i < steps.length - 1 && (
                  <div
                    style={{
                      width: 36,
                      height: 4,
                      background: cfg.colour.accent,
                      opacity: enter,
                      borderRadius: 2,
                    }}
                  />
                )}
              </React.Fragment>
            );
          })}
        </div>
      </AbsoluteFill>
    </SceneFrame>
  );
};

const ComparisonScene: React.FC<{ scene: ExplainerScene; brand: BrandSlug }> = ({
  scene,
  brand,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const cfg = brands[brand];
  const rows = scene.data?.comparisonRows ?? [];
  const eyebrow = scene.data?.eyebrow;

  return (
    <SceneFrame brand={brand} bgMode="solid-neutral">
      <AbsoluteFill style={{ padding: 120, flexDirection: 'column', justifyContent: 'center' }}>
        {eyebrow && (
          <div
            style={{
              color: cfg.colour.primary,
              fontFamily: cfg.typography.display.family,
              fontSize: 36,
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              marginBottom: 24,
            }}
          >
            {eyebrow}
          </div>
        )}
        <div
          style={{
            color: cfg.colour.neutral['900'],
            fontFamily: cfg.typography.display.family,
            fontWeight: cfg.typography.display.weight,
            fontSize: 56,
            letterSpacing: '-0.01em',
            marginBottom: 56,
            maxWidth: 1500,
          }}
        >
          {scene.onScreenText}
        </div>
        <div style={{ display: 'flex', gap: 40 }}>
          <div style={{ flex: 1, opacity: 0.6 }}>
            <div
              style={{
                fontFamily: cfg.typography.body.family,
                fontSize: 22,
                letterSpacing: '0.2em',
                textTransform: 'uppercase',
                color: cfg.colour.neutral['500'],
                marginBottom: 24,
              }}
            >
              Today
            </div>
            {rows.map((r, i) => (
              <div
                key={i}
                style={{
                  fontFamily: cfg.typography.body.family,
                  fontSize: 32,
                  lineHeight: 1.5,
                  color: cfg.colour.neutral['900'],
                  marginBottom: 20,
                  paddingLeft: 28,
                  borderLeft: `4px solid ${cfg.colour.neutral['100']}`,
                }}
              >
                {r.them}
              </div>
            ))}
          </div>
          <div style={{ flex: 1 }}>
            <div
              style={{
                fontFamily: cfg.typography.body.family,
                fontSize: 22,
                letterSpacing: '0.2em',
                textTransform: 'uppercase',
                color: cfg.colour.primary,
                marginBottom: 24,
              }}
            >
              With {cfg.displayName}
            </div>
            {rows.map((r, i) => {
              const enter = brandFadeIn(
                { frame, fps, motion: cfg.motion },
                staggerStart(8, i, 5),
              );
              return (
                <div
                  key={i}
                  style={{
                    fontFamily: cfg.typography.display.family,
                    fontWeight: cfg.typography.display.weight,
                    fontSize: 36,
                    lineHeight: 1.3,
                    color: cfg.colour.neutral['900'],
                    marginBottom: 20,
                    paddingLeft: 28,
                    borderLeft: `4px solid ${cfg.colour.accent}`,
                    opacity: enter,
                    transform: `translateX(${(1 - enter) * 16}px)`,
                  }}
                >
                  {r.us}
                </div>
              );
            })}
          </div>
        </div>
      </AbsoluteFill>
    </SceneFrame>
  );
};

const KeypointsScene: React.FC<{ scene: ExplainerScene; brand: BrandSlug }> = ({
  scene,
  brand,
}) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const cfg = brands[brand];
  const points = scene.data?.keypoints ?? [];
  const eyebrow = scene.data?.eyebrow;

  return (
    <SceneFrame brand={brand} bgMode="solid-neutral">
      <AbsoluteFill style={{ padding: 120, flexDirection: 'column', justifyContent: 'center' }}>
        {eyebrow && (
          <div
            style={{
              color: cfg.colour.primary,
              fontFamily: cfg.typography.display.family,
              fontSize: 36,
              letterSpacing: '0.18em',
              textTransform: 'uppercase',
              marginBottom: 24,
            }}
          >
            {eyebrow}
          </div>
        )}
        <div
          style={{
            color: cfg.colour.neutral['900'],
            fontFamily: cfg.typography.display.family,
            fontWeight: cfg.typography.display.weight,
            fontSize: 56,
            letterSpacing: '-0.01em',
            marginBottom: 48,
            maxWidth: 1500,
          }}
        >
          {scene.onScreenText}
        </div>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 22 }}>
          {points.map((p, i) => {
            const enter = brandFadeIn({ frame, fps, motion: cfg.motion }, staggerStart(8, i, 6));
            return (
              <div
                key={i}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 28,
                  opacity: enter,
                  transform: `translateX(${(1 - enter) * 24}px)`,
                }}
              >
                <div
                  style={{
                    width: 48,
                    height: 48,
                    borderRadius: 12,
                    background: cfg.colour.primary,
                    color: cfg.colour.neutral['50'],
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontFamily: cfg.typography.display.family,
                    fontWeight: cfg.typography.display.weight,
                    fontSize: 26,
                    flexShrink: 0,
                  }}
                >
                  ✓
                </div>
                <div
                  style={{
                    fontFamily: cfg.typography.display.family,
                    fontWeight: cfg.typography.display.weight,
                    fontSize: 40,
                    lineHeight: 1.3,
                    color: cfg.colour.neutral['900'],
                  }}
                >
                  {p}
                </div>
              </div>
            );
          })}
        </div>
      </AbsoluteFill>
    </SceneFrame>
  );
};

const Cta: React.FC<{ scene: ExplainerScene; brand: BrandSlug }> = ({ scene, brand }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const cfg = brands[brand];
  const entry = signatureEntry({ frame, fps, motion: cfg.motion }, 0, 80);
  const fg = readableOn(cfg.colour.secondary, cfg.colour);

  return (
    <SceneFrame brand={brand} bgMode="solid-secondary">
      <AbsoluteFill
        style={{
          alignItems: 'center',
          justifyContent: 'center',
          padding: 96,
          flexDirection: 'column',
        }}
      >
        <div
          style={{
            transform: `scale(${entry.scale}) translate(${entry.translateX}px, ${entry.translateY}px)`,
            opacity: entry.opacity,
            color: fg,
            fontFamily: cfg.typography.display.family,
            fontWeight: cfg.typography.display.weight,
            fontSize: 112,
            textAlign: 'center',
            letterSpacing: '-0.02em',
            lineHeight: 1.05,
            maxWidth: 1700,
          }}
        >
          {scene.onScreenText}
        </div>
        <div style={{ marginTop: 48 }}>
          <AccentRule color={cfg.colour.accent} startFrame={Math.round(fps * 0.5)} width={360} />
        </div>
        <div
          style={{
            marginTop: 48,
            color: cfg.colour.accent,
            fontFamily: cfg.typography.body.family,
            fontSize: 36,
            letterSpacing: '0.22em',
            textTransform: 'uppercase',
            opacity: entry.opacity,
          }}
        >
          {scene.data?.eyebrow ?? 'Learn more'}
        </div>
      </AbsoluteFill>
    </SceneFrame>
  );
};

// ── Screenshot scene · embeds a real captured PNG with brand chrome ────────

const ScreenshotScene: React.FC<{ scene: ExplainerScene; brand: BrandSlug }> = ({ scene, brand }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const cfg = brands[brand];
  const entry = signatureEntry({ frame, fps, motion: cfg.motion }, 0, 80);
  const fg = readableOn(cfg.colour.secondary, cfg.colour);
  const src = scene.data?.screenshotSrc;

  return (
    <SceneFrame brand={brand} bgMode="solid-secondary">
      <AbsoluteFill
        style={{
          alignItems: 'center',
          justifyContent: 'center',
          padding: 80,
          flexDirection: 'column',
          gap: 32,
        }}
      >
        {scene.data?.eyebrow && (
          <div
            style={{
              color: cfg.colour.accent,
              fontFamily: cfg.typography.body.family,
              fontSize: 28,
              letterSpacing: '0.22em',
              textTransform: 'uppercase',
              opacity: entry.opacity,
            }}
          >
            {scene.data.eyebrow}
          </div>
        )}

        {src ? (
          <div
            style={{
              transform: `scale(${entry.scale}) translate(${entry.translateX}px, ${entry.translateY}px)`,
              opacity: entry.opacity,
              borderRadius: 16,
              overflow: 'hidden',
              boxShadow: `0 30px 80px rgba(0,0,0,0.45), 0 0 0 4px ${cfg.colour.accent}`,
              maxWidth: 1500,
              maxHeight: 760,
            }}
          >
            <Img
              src={staticFile(src)}
              style={{ display: 'block', width: '100%', height: 'auto', objectFit: 'contain' }}
            />
          </div>
        ) : (
          <div style={{ color: fg, fontSize: 32 }}>screenshot missing</div>
        )}

        <div
          style={{
            color: fg,
            fontFamily: cfg.typography.display.family,
            fontWeight: cfg.typography.display.weight,
            fontSize: 56,
            textAlign: 'center',
            letterSpacing: '-0.02em',
            lineHeight: 1.1,
            maxWidth: 1600,
            opacity: entry.opacity,
          }}
        >
          {scene.onScreenText}
        </div>

        {scene.data?.caption && (
          <div
            style={{
              color: cfg.colour.accent,
              fontFamily: cfg.typography.body.family,
              fontSize: 32,
              textAlign: 'center',
              maxWidth: 1400,
              opacity: entry.opacity,
            }}
          >
            {scene.data.caption}
          </div>
        )}
      </AbsoluteFill>
    </SceneFrame>
  );
};

// ── Default props (kept for backwards-compat with existing scripts) ────────

export const defaultExplainerProps: ExplainerProps = {
  brand: 'ra',
  hookSec: 5,
  ctaSec: 5,
  storyboard: [
    {
      sceneId: 'hook',
      sceneType: 'hook',
      durationSec: 5,
      onScreenText: 'Australia ships hundreds of restoration report formats. One should be enough.',
      voiceover: 'Australia ships hundreds of restoration report formats.',
      data: { eyebrow: 'The fragmentation problem' },
    },
    {
      sceneId: 'stat-1',
      sceneType: 'stat',
      durationSec: 6,
      onScreenText: 'The fragmentation tax on every claim',
      voiceover: 'Three numbers that drive the cost.',
      data: {
        eyebrow: 'By the numbers',
        stats: [
          { value: '50+', label: 'distinct report formats in active use' },
          { value: '20–30%', label: 'of jobs need a re-inspection' },
          { value: '$2–5k', label: 'cost per re-inspection cycle' },
        ],
      },
    },
    {
      sceneId: 'flow-1',
      sceneType: 'flow',
      durationSec: 7,
      onScreenText: 'One workflow, end to end',
      voiceover: 'Five steps. One system.',
      data: {
        eyebrow: 'How it runs',
        flowSteps: ['Inspection', 'AI Analysis', 'Scoping', 'Estimating', 'Reporting'],
      },
    },
    {
      sceneId: 'body-1',
      sceneType: 'body',
      durationSec: 5,
      onScreenText: 'The National Inspection Report standardises every job, every insurer, every assessor.',
      voiceover:
        'The National Inspection Report standardises every job, every insurer, every assessor.',
      data: { footnote: 'Built on IICRC S500 / S520 / S700.' },
    },
    {
      sceneId: 'cta',
      sceneType: 'cta',
      durationSec: 4,
      onScreenText: 'One System. Fewer Gaps. More Confidence.',
      voiceover: 'RestoreAssist. One National Inspection Standard.',
      data: { eyebrow: 'Now on the App Store' },
    },
  ],
};

// ── Main composition ───────────────────────────────────────────────────────

export const Explainer: React.FC<ExplainerProps> = ({ brand, storyboard }) => {
  const { fps } = useVideoConfig();
  let cursor = 0;
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      {storyboard.map((scene) => {
        const start = cursor;
        const dur = Math.max(1, Math.round(scene.durationSec * fps));
        cursor += dur;
        const sceneType = resolveSceneType(scene);
        const SceneComponent =
          sceneType === 'hook'
            ? Hook
            : sceneType === 'cta'
            ? Cta
            : sceneType === 'stat'
            ? StatScene
            : sceneType === 'flow'
            ? FlowScene
            : sceneType === 'comparison'
            ? ComparisonScene
            : sceneType === 'keypoints'
            ? KeypointsScene
            : sceneType === 'screenshot'
            ? ScreenshotScene
            : Body;
        return (
          <Sequence key={scene.sceneId} from={start} durationInFrames={dur} name={scene.sceneId}>
            <SceneComponent scene={scene} brand={brand} />
            {scene.voiceoverAudioPath ? (
              <Audio src={staticFile(scene.voiceoverAudioPath)} />
            ) : null}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
