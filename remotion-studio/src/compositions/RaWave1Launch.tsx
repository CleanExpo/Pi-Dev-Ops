/**
 * RA Wave 1 Launch — POC composition.
 *
 * 1080×1080, 30fps, 75s total, 10 scenes mapped from
 * `briefs/ra-2026-05-15-wave-1-launch.storyboard.json`.
 *
 * Locked palette per the brief (overrides brand-config which is currently teal):
 *   navy   #1C2E47   (primary background)
 *   warm   #8A6B4E   (accent / warm tone)
 *   light  #D4A574   (headline / numeric)
 *   dark   #050505   (deep accent / vignette)
 *
 * Geometric only — no Lucide, no stock, no illustration.
 */
import React from 'react';
import {
  AbsoluteFill,
  Audio,
  Img,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import { z } from 'zod';

// Locked palette.
const NAVY = '#1C2E47';
// v2 timing fix — tail buffer at end of every scene + gap between scenes
// to fix v1 cutoffs (voiceover/text clipped at scene boundaries).
const TAIL_FRAMES = 12; // 0.4s @ 30fps — held content after VO ends
const GAP_FRAMES = 9;   // 0.3s @ 30fps — navy fade-through between scenes
const WARM = '#8A6B4E';
const LIGHT = '#D4A574';
const DARK = '#050505';

const DISPLAY_FONT =
  "'Inter', 'Helvetica Neue', Helvetica, Arial, system-ui, sans-serif";
const MONO_FONT =
  "'JetBrains Mono', 'SF Mono', Menlo, Consolas, monospace";

// ── Schema ──────────────────────────────────────────────────────────────────

export const raWave1SceneSchema = z.object({
  sceneId: z.string(),
  durationSec: z.number(),
  voiceover: z.string(),
  onScreenText: z.string(),
  voiceoverAudioPath: z.string().optional(),
});

export const raWave1Schema = z.object({
  brand: z.literal('ra'),
  storyboard: z.array(raWave1SceneSchema),
});

export type RaWave1Scene = z.infer<typeof raWave1SceneSchema>;
export type RaWave1Props = z.infer<typeof raWave1Schema>;

// ── Shared primitives ──────────────────────────────────────────────────────

const FilmGrain: React.FC<{ opacity?: number }> = ({ opacity = 0.04 }) => {
  // A static, low-amplitude noise overlay would normally come from an SVG
  // turbulence. For a clean POC we use a CSS noise via radial gradient.
  return (
    <AbsoluteFill
      style={{
        pointerEvents: 'none',
        opacity,
        background:
          'radial-gradient(circle at 30% 20%, rgba(255,255,255,0.06), transparent 60%), radial-gradient(circle at 70% 80%, rgba(0,0,0,0.18), transparent 55%)',
      }}
    />
  );
};

const Vignette: React.FC = () => (
  <AbsoluteFill
    style={{
      pointerEvents: 'none',
      boxShadow: `inset 0 0 280px 80px ${DARK}`,
    }}
  />
);

const Watermark: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const opacity = interpolate(frame, [0, fps * 0.8], [0, 0.55], {
    extrapolateRight: 'clamp',
  });
  return (
    <div
      style={{
        position: 'absolute',
        right: 40,
        bottom: 32,
        display: 'flex',
        alignItems: 'center',
        gap: 10,
        opacity,
        zIndex: 50,
      }}
    >
      <div style={{ width: 10, height: 10, background: LIGHT, borderRadius: 2 }} />
      <div
        style={{
          fontFamily: DISPLAY_FONT,
          fontSize: 14,
          letterSpacing: '0.22em',
          textTransform: 'uppercase',
          color: LIGHT,
          opacity: 0.9,
        }}
      >
        RestoreAssist
      </div>
    </div>
  );
};

const SceneBg: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <AbsoluteFill style={{ background: NAVY, overflow: 'hidden' }}>
    <FilmGrain />
    {children}
    <Vignette />
    <Watermark />
  </AbsoluteFill>
);

/** Helper — fade in over `dur` frames starting at `start`. */
function fadeIn(frame: number, start: number, dur: number): number {
  return interpolate(frame, [start, start + dur], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
}

/** Helper — slide up + fade in. */
function slideUp(
  frame: number,
  start: number,
  dur: number,
): { opacity: number; ty: number } {
  const t = interpolate(frame, [start, start + dur], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
  });
  return { opacity: t, ty: (1 - t) * 28 };
}

// ── Scene 1 · Hook (0–3s) ──────────────────────────────────────────────────

const Scene1Hook: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const line1 = slideUp(frame, Math.round(0.2 * fps), Math.round(0.5 * fps));
  const line2 = slideUp(frame, Math.round(1.5 * fps), Math.round(0.5 * fps));
  return (
    <SceneBg>
      <AbsoluteFill
        style={{
          padding: 108,
          flexDirection: 'column',
          justifyContent: 'center',
          gap: 24,
        }}
      >
        <div
          style={{
            fontFamily: DISPLAY_FONT,
            fontWeight: 700,
            fontSize: 78,
            lineHeight: 1.1,
            letterSpacing: '-0.02em',
            color: LIGHT,
            opacity: line1.opacity,
            transform: `translateY(${line1.ty}px)`,
          }}
        >
          Finished the dry-out at three.
        </div>
        <div
          style={{
            fontFamily: DISPLAY_FONT,
            fontWeight: 700,
            fontSize: 78,
            lineHeight: 1.1,
            letterSpacing: '-0.02em',
            color: WARM,
            opacity: line2.opacity,
            transform: `translateY(${line2.ty}px)`,
          }}
        >
          Paperwork kept you till nine.
        </div>
      </AbsoluteFill>
    </SceneBg>
  );
};

// ── Scene 2 · Problem montage (3–15s) ──────────────────────────────────────

const Scene2Problem: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  // Labels stack vertically top-right, accumulating.
  const labels = ['Re-typing', 'Hunting', 'Re-entering', 'Chasing', 'Losing'];
  // Scene starts at 3s of master timeline; component frame counts from scene start.
  // Label i appears at master seconds 5+2i → scene seconds 2+2i.
  const labelStarts = labels.map((_, i) => Math.round((2 + 2 * i) * fps));

  // Schematic chaos: three abstract panels that judder.
  const driftY = Math.sin(frame / 6) * 3;

  return (
    <SceneBg>
      <AbsoluteFill style={{ padding: 96 }}>
        {/* Schematic camera-roll thumbnails — Panel 1 */}
        <div
          style={{
            position: 'absolute',
            left: 96,
            top: 200,
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 92px)',
            gap: 10,
            transform: `translateY(${driftY}px) rotate(-1.4deg)`,
            opacity: fadeIn(frame, 0, fps * 0.5),
          }}
        >
          {Array.from({ length: 9 }).map((_, i) => (
            <div
              key={i}
              style={{
                width: 92,
                height: 70,
                background: `rgba(212, 165, 116, ${0.18 + (i % 3) * 0.05})`,
                border: `1px solid ${WARM}`,
                borderRadius: 4,
                transform: `translate(${(i % 2) * 4}px, ${(i % 3) * 3}px)`,
              }}
            />
          ))}
        </div>

        {/* Schematic Xero-like field grid — Panel 2 */}
        <div
          style={{
            position: 'absolute',
            left: 96,
            top: 540,
            width: 360,
            opacity: fadeIn(frame, fps * 2, fps * 0.5),
          }}
        >
          {Array.from({ length: 7 }).map((_, i) => (
            <div
              key={i}
              style={{
                height: 18,
                background: 'rgba(245, 247, 248, 0.12)',
                marginBottom: 8,
                borderLeft: `3px solid ${LIGHT}`,
                width: `${72 + (i * 11) % 28}%`,
              }}
            />
          ))}
          {/* cursor jump */}
          <div
            style={{
              position: 'absolute',
              left: interpolate(
                frame,
                [fps * 2, fps * 4, fps * 6, fps * 8],
                [0, 180, 60, 240],
                { extrapolateRight: 'clamp' },
              ),
              top: interpolate(
                frame,
                [fps * 2, fps * 4, fps * 6, fps * 8],
                [10, 60, 110, 150],
                { extrapolateRight: 'clamp' },
              ),
              width: 12,
              height: 18,
              background: LIGHT,
            }}
          />
        </div>

        {/* Schematic IICRC PDF outline — Panel 3 */}
        <div
          style={{
            position: 'absolute',
            right: 96,
            top: 200,
            width: 280,
            height: 360,
            border: `1px solid ${LIGHT}`,
            borderRadius: 6,
            padding: 16,
            opacity: fadeIn(frame, fps * 4, fps * 0.5),
          }}
        >
          <div
            style={{
              fontFamily: MONO_FONT,
              fontSize: 11,
              letterSpacing: '0.18em',
              color: LIGHT,
              opacity: 0.6,
              marginBottom: 14,
            }}
          >
            S500:2025
          </div>
          {Array.from({ length: 16 }).map((_, i) => (
            <div
              key={i}
              style={{
                height: 6,
                background: 'rgba(245, 247, 248, 0.16)',
                marginBottom: 6,
                width: `${88 - (i * 7) % 30}%`,
              }}
            />
          ))}
          {/* jumping highlight */}
          <div
            style={{
              position: 'absolute',
              left: 12,
              top: interpolate(
                frame,
                [fps * 4, fps * 6, fps * 8, fps * 10],
                [50, 150, 80, 220],
                { extrapolateRight: 'clamp' },
              ),
              width: 256,
              height: 12,
              background: `${WARM}55`,
              borderLeft: `3px solid ${WARM}`,
            }}
          />
        </div>

        {/* Scatter — Panel 4 — handover bundle */}
        <div
          style={{
            position: 'absolute',
            right: 96,
            bottom: 200,
            width: 320,
            height: 260,
            opacity: fadeIn(frame, fps * 6, fps * 0.5),
          }}
        >
          {Array.from({ length: 7 }).map((_, i) => {
            const angle = (i * 47) % 360;
            const r = 40 + (i % 3) * 30;
            const x = Math.cos((angle * Math.PI) / 180) * r * (frame / (fps * 12));
            const y = Math.sin((angle * Math.PI) / 180) * r * (frame / (fps * 12));
            return (
              <div
                key={i}
                style={{
                  position: 'absolute',
                  left: 140 + x,
                  top: 110 + y,
                  width: 36,
                  height: 36,
                  background: LIGHT,
                  opacity: 0.5,
                  transform: `rotate(${angle}deg)`,
                }}
              />
            );
          })}
        </div>

        {/* Stacked labels top-right */}
        <div
          style={{
            position: 'absolute',
            right: 48,
            top: 48,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'flex-end',
            gap: 10,
          }}
        >
          {labels.map((label, i) => {
            const op = fadeIn(frame, labelStarts[i], fps * 0.3);
            return (
              <div
                key={label}
                style={{
                  fontFamily: MONO_FONT,
                  fontSize: 22,
                  letterSpacing: '0.18em',
                  textTransform: 'uppercase',
                  color: LIGHT,
                  opacity: op,
                  transform: `translateX(${(1 - op) * 16}px)`,
                  background: `${DARK}80`,
                  padding: '8px 14px',
                  borderRight: `3px solid ${WARM}`,
                }}
              >
                {label}
              </div>
            );
          })}
        </div>
      </AbsoluteFill>
    </SceneBg>
  );
};

// ── Scene 3 · Pivot + Close Job demo (15–25s) ──────────────────────────────

const Scene3Pivot: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  // 0–0.8s black hold; 0.8–2.0s "That ends now" lands; 2.5s+ screen capture enters.
  const blackHold = frame < fps * 0.8;
  const promiseFade = fadeIn(frame, Math.round(fps * 0.8), fps * 0.6);
  const promiseExit = interpolate(
    frame,
    [fps * 4, fps * 5],
    [1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' },
  );
  const screenFade = fadeIn(frame, Math.round(fps * 4.5), fps * 0.8);
  const subFade = fadeIn(frame, Math.round(fps * 6), fps * 0.5);

  if (blackHold) {
    return <AbsoluteFill style={{ background: DARK }} />;
  }

  return (
    <SceneBg>
      {/* Promise statement: lives 0.8s–5s, then fades out */}
      <AbsoluteFill
        style={{
          alignItems: 'center',
          justifyContent: 'center',
          opacity: promiseFade * promiseExit,
          zIndex: 5,
        }}
      >
        <div
          style={{
            fontFamily: DISPLAY_FONT,
            fontWeight: 700,
            fontSize: 96,
            color: LIGHT,
            letterSpacing: '-0.02em',
            textAlign: 'center',
          }}
        >
          That ends now.
        </div>
      </AbsoluteFill>

      {/* Screen capture — enters at ~4.5s scene-local */}
      <AbsoluteFill
        style={{
          alignItems: 'center',
          justifyContent: 'center',
          padding: 80,
          opacity: screenFade,
        }}
      >
        <div
          style={{
            position: 'relative',
            width: 880,
            height: 600,
            borderRadius: 16,
            overflow: 'hidden',
            boxShadow: `0 30px 80px ${DARK}, 0 0 0 1px ${WARM}33`,
            background: '#fff',
          }}
        >
          <Img
            src={staticFile('ra-wave-1-screencaps/01-close-job-prompt.png')}
            style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'top' }}
          />
          {/* underline highlight under the editable area */}
          <div
            style={{
              position: 'absolute',
              left: 60,
              right: 60,
              bottom: 140,
              height: 4,
              background: WARM,
              opacity: fadeIn(frame, fps * 5.5, fps * 0.4),
            }}
          />
        </div>
      </AbsoluteFill>

      {/* Subhead: "You confirm. AI drafts." */}
      <div
        style={{
          position: 'absolute',
          left: 0,
          right: 0,
          bottom: 100,
          textAlign: 'center',
          fontFamily: DISPLAY_FONT,
          fontWeight: 600,
          fontSize: 44,
          color: LIGHT,
          opacity: subFade,
          letterSpacing: '-0.01em',
          zIndex: 10,
        }}
      >
        You confirm. AI drafts.
      </div>
    </SceneBg>
  );
};

// ── Scene 4 · BYOK Storage demo (25–35s) ───────────────────────────────────

const Scene4Storage: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const screenFade = fadeIn(frame, 0, fps * 0.6);
  const metaFade = fadeIn(frame, Math.round(fps * 2), fps * 0.6);
  const tagFade = fadeIn(frame, Math.round(fps * 7), fps * 0.5);

  return (
    <SceneBg>
      <AbsoluteFill
        style={{
          alignItems: 'center',
          justifyContent: 'center',
          padding: 80,
          opacity: screenFade,
        }}
      >
        <div
          style={{
            width: 820,
            height: 540,
            borderRadius: 16,
            overflow: 'hidden',
            boxShadow: `0 30px 80px ${DARK}, 0 0 0 1px ${WARM}33`,
            background: '#fff',
          }}
        >
          <Img
            src={staticFile('ra-wave-1-screencaps/02-storage-card-disconnected.png')}
            style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'top' }}
          />
        </div>
      </AbsoluteFill>

      {/* Metadata strip top */}
      <div
        style={{
          position: 'absolute',
          top: 56,
          left: 0,
          right: 0,
          textAlign: 'center',
          opacity: metaFade,
        }}
      >
        <div
          style={{
            display: 'inline-block',
            fontFamily: MONO_FONT,
            fontSize: 26,
            letterSpacing: '0.28em',
            color: LIGHT,
            background: `${DARK}99`,
            padding: '14px 28px',
            border: `1px solid ${WARM}55`,
            borderRadius: 6,
          }}
        >
          SHA-256 · UTC · GPS · USER HASH
        </div>
      </div>

      {/* Bottom tagline */}
      <div
        style={{
          position: 'absolute',
          bottom: 80,
          left: 0,
          right: 0,
          textAlign: 'center',
          opacity: tagFade,
          fontFamily: DISPLAY_FONT,
          fontWeight: 700,
          fontSize: 52,
          color: WARM,
          letterSpacing: '-0.01em',
        }}
      >
        Your data. Your storage.
      </div>
    </SceneBg>
  );
};

// ── Scene 5 · Inbound DR/NRPG (35–45s) ─────────────────────────────────────
// No real DR/NRPG capture exists. Use the dashboard empty-state + overlay a
// synthetic warm-tan banner that simulates the InboundJobAlert.

const Scene5Inbound: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const screenFade = fadeIn(frame, 0, fps * 0.6);
  const bannerEnter = spring({
    frame: frame - Math.round(fps * 1.2),
    fps,
    config: { damping: 12, mass: 0.6 },
  });
  // Tap animation: 4.5s in.
  const tapPulse = interpolate(
    frame,
    [fps * 4.5, fps * 4.7, fps * 4.9],
    [0, 1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' },
  );
  // Banner fades out at 5.5s.
  const bannerFadeOut = interpolate(
    frame,
    [fps * 5.5, fps * 6.0],
    [1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' },
  );

  const line1 = slideUp(frame, Math.round(fps * 6.0), fps * 0.4);
  const line2 = slideUp(frame, Math.round(fps * 7.8), fps * 0.4);

  return (
    <SceneBg>
      <AbsoluteFill
        style={{
          alignItems: 'center',
          justifyContent: 'center',
          padding: 80,
          opacity: screenFade,
        }}
      >
        <div
          style={{
            position: 'relative',
            width: 820,
            height: 540,
            borderRadius: 16,
            overflow: 'hidden',
            boxShadow: `0 30px 80px ${DARK}, 0 0 0 1px ${WARM}33`,
            background: '#fff',
          }}
        >
          <Img
            src={staticFile('ra-wave-1-screencaps/04-dashboard-empty-state.png')}
            style={{ width: '100%', height: '100%', objectFit: 'cover', objectPosition: 'top' }}
          />
          {/* Synthetic InboundJobAlert banner overlay */}
          <div
            style={{
              position: 'absolute',
              top: 24,
              left: 24,
              right: 24,
              background: WARM,
              borderRadius: 10,
              padding: '18px 22px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              transform: `translateY(${(1 - bannerEnter) * -60}px) scaleY(${0.6 + 0.4 * bannerEnter})`,
              opacity: bannerEnter * bannerFadeOut,
              boxShadow: `0 12px 40px ${DARK}66`,
            }}
          >
            <div>
              <div
                style={{
                  fontFamily: MONO_FONT,
                  fontSize: 11,
                  letterSpacing: '0.24em',
                  textTransform: 'uppercase',
                  color: NAVY,
                  opacity: 0.75,
                  marginBottom: 4,
                }}
              >
                Disaster Recovery — new job
              </div>
              <div
                style={{
                  fontFamily: DISPLAY_FONT,
                  fontWeight: 700,
                  fontSize: 18,
                  color: NAVY,
                }}
              >
                14 Bowen Tce, New Farm QBR · Insurer: Suncorp
              </div>
            </div>
            <div
              style={{
                position: 'relative',
                background: NAVY,
                color: LIGHT,
                padding: '10px 18px',
                borderRadius: 6,
                fontFamily: DISPLAY_FONT,
                fontWeight: 700,
                fontSize: 14,
                letterSpacing: '0.06em',
              }}
            >
              Accept &amp; Start
              {/* Tap pulse */}
              <div
                style={{
                  position: 'absolute',
                  inset: -6,
                  borderRadius: 10,
                  border: `2px solid ${LIGHT}`,
                  opacity: tapPulse * 0.9,
                  transform: `scale(${1 + tapPulse * 0.3})`,
                }}
              />
            </div>
          </div>
        </div>
      </AbsoluteFill>

      {/* Slide-up callouts */}
      <div
        style={{
          position: 'absolute',
          bottom: 140,
          left: 0,
          right: 0,
          textAlign: 'center',
          opacity: line1.opacity,
          transform: `translateY(${line1.ty}px)`,
          fontFamily: DISPLAY_FONT,
          fontWeight: 700,
          fontSize: 46,
          color: LIGHT,
        }}
      >
        No re-typing.
      </div>
      <div
        style={{
          position: 'absolute',
          bottom: 70,
          left: 0,
          right: 0,
          textAlign: 'center',
          opacity: line2.opacity,
          transform: `translateY(${line2.ty}px)`,
          fontFamily: DISPLAY_FONT,
          fontWeight: 700,
          fontSize: 46,
          color: WARM,
        }}
      >
        No double-handling.
      </div>
    </SceneBg>
  );
};

// ── Scene 6 · Positioning (45–52s) — slow map of Australia ─────────────────

const Scene6Positioning: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  // Slow fill of the map outline over 7 seconds.
  const fill = interpolate(frame, [0, fps * 7], [0, 1], {
    extrapolateRight: 'clamp',
  });
  return (
    <SceneBg>
      <AbsoluteFill style={{ alignItems: 'center', justifyContent: 'center' }}>
        <svg
          width="700"
          height="700"
          viewBox="0 0 700 700"
          style={{ opacity: 0.95 }}
        >
          {/* Stylised Australia outline (rough geometric simplification). */}
          <defs>
            <linearGradient id="ausFill" x1="0" y1="0" x2="1" y2="1">
              <stop offset="0%" stopColor={LIGHT} stopOpacity={0.18} />
              <stop offset="100%" stopColor={LIGHT} stopOpacity={0.04} />
            </linearGradient>
          </defs>
          <path
            d="M 140 260
               L 220 200 L 330 200 L 430 220 L 530 250
               L 580 320 L 600 410 L 560 480 L 530 510
               L 540 560 L 500 590 L 430 580 L 360 540
               L 280 540 L 220 560 L 160 530 L 130 460
               L 110 380 L 130 320 Z"
            fill="url(#ausFill)"
            stroke={LIGHT}
            strokeWidth="3"
            strokeDasharray="2200"
            strokeDashoffset={2200 * (1 - fill)}
          />
          {/* Tasmania */}
          <ellipse
            cx="480"
            cy="635"
            rx="34"
            ry="22"
            fill="none"
            stroke={LIGHT}
            strokeWidth="3"
            opacity={interpolate(frame, [fps * 3, fps * 4], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })}
          />
          {/* Brisbane dot */}
          <circle
            cx="555"
            cy="345"
            r="12"
            fill={WARM}
            opacity={interpolate(frame, [fps * 4, fps * 5], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })}
          />
          <circle
            cx="555"
            cy="345"
            r={20 + Math.sin(frame / 12) * 4}
            fill="none"
            stroke={WARM}
            strokeWidth="2"
            opacity={interpolate(frame, [fps * 4.5, fps * 5.5], [0, 0.6], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })}
          />
        </svg>
        {/* Label */}
        <div
          style={{
            position: 'absolute',
            top: 'calc(50% + 250px)',
            fontFamily: MONO_FONT,
            fontSize: 18,
            letterSpacing: '0.32em',
            color: WARM,
            textTransform: 'uppercase',
            opacity: fadeIn(frame, fps * 5, fps * 0.5),
          }}
        >
          Brisbane
        </div>
      </AbsoluteFill>
    </SceneBg>
  );
};

// ── Scene 7 · Proof numbers (52–58s) ───────────────────────────────────────

const Scene7Proof: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();

  // Three numbers, cross-faded. Each lives ~2s.
  // Scene-local timing:
  //   0.0–2.0s : "0" + "app-switches"
  //   2.0–4.0s : "S500 §7.1–§12.3" + "cited on every report"
  //   4.0–6.0s : "100%" + "your storage. your data."
  const phaseA = interpolate(
    frame,
    [0, fps * 0.3, fps * 1.7, fps * 2.0],
    [0, 1, 1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' },
  );
  const phaseB = interpolate(
    frame,
    [fps * 1.9, fps * 2.2, fps * 3.7, fps * 4.0],
    [0, 1, 1, 0],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' },
  );
  const phaseC = interpolate(
    frame,
    [fps * 3.9, fps * 4.2, fps * 6.0],
    [0, 1, 1],
    { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' },
  );

  const NumBlock: React.FC<{
    big: string;
    label: string;
    opacity: number;
    bigSize?: number;
  }> = ({ big, label, opacity, bigSize = 320 }) => (
    <div
      style={{
        position: 'absolute',
        inset: 0,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 4,
        opacity,
      }}
    >
      <div
        style={{
          fontFamily: DISPLAY_FONT,
          fontWeight: 800,
          fontSize: bigSize,
          color: LIGHT,
          lineHeight: 0.95,
          letterSpacing: '-0.04em',
          transform: `translateY(${(1 - opacity) * 24}px)`,
        }}
      >
        {big}
      </div>
      <div
        style={{
          fontFamily: MONO_FONT,
          fontSize: 22,
          letterSpacing: '0.22em',
          textTransform: 'uppercase',
          color: WARM,
          marginTop: 18,
        }}
      >
        {label}
      </div>
    </div>
  );

  return (
    <SceneBg>
      <NumBlock big="0" label="app-switches" opacity={phaseA} />
      <NumBlock
        big="S500 §7.1–§12.3"
        label="cited on every report"
        opacity={phaseB}
        bigSize={120}
      />
      <NumBlock big="100%" label="your storage. your data." opacity={phaseC} />
    </SceneBg>
  );
};

// ── Scene 8 · Australian Built tagline (58–65s) ────────────────────────────

const Scene8Tagline: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  // Stack three lines, slide-up.
  const l1 = slideUp(frame, Math.round(fps * 0.2), fps * 0.5);
  const l2 = slideUp(frame, Math.round(fps * 2.2), fps * 0.5);
  const l3 = slideUp(frame, Math.round(fps * 4.2), fps * 0.6);
  return (
    <SceneBg>
      <AbsoluteFill
        style={{
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 28,
          padding: 80,
        }}
      >
        <div
          style={{
            fontFamily: DISPLAY_FONT,
            fontWeight: 700,
            fontSize: 64,
            color: LIGHT,
            opacity: l1.opacity,
            transform: `translateY(${l1.ty}px)`,
            letterSpacing: '-0.02em',
          }}
        >
          Built in Brisbane.
        </div>
        <div
          style={{
            fontFamily: DISPLAY_FONT,
            fontWeight: 700,
            fontSize: 64,
            color: LIGHT,
            opacity: l2.opacity,
            transform: `translateY(${l2.ty}px)`,
            letterSpacing: '-0.02em',
          }}
        >
          For Australian tradies.
        </div>
        <div
          style={{
            fontFamily: DISPLAY_FONT,
            fontWeight: 700,
            fontSize: 52,
            color: WARM,
            opacity: l3.opacity,
            transform: `translateY(${l3.ty}px)`,
            textAlign: 'center',
            maxWidth: 900,
            letterSpacing: '-0.01em',
            lineHeight: 1.2,
          }}
        >
          By a restoration business that runs on it.
        </div>
      </AbsoluteFill>
    </SceneBg>
  );
};

// ── Scene 9 · CTA spoken (65–72s) ──────────────────────────────────────────

const RaLogoLockup: React.FC<{ opacity: number }> = ({ opacity }) => (
  // Geometric brand mark — stacked navy/warm rectangles + 'RA' wordmark.
  // Custom Remotion vector. No Lucide. No AI image.
  <div
    style={{
      display: 'flex',
      alignItems: 'center',
      gap: 18,
      opacity,
    }}
  >
    <svg width="92" height="92" viewBox="0 0 92 92">
      <rect x="6" y="6" width="80" height="80" rx="10" fill={NAVY} stroke={LIGHT} strokeWidth="2" />
      <rect x="18" y="18" width="32" height="56" fill={WARM} />
      <rect x="54" y="38" width="20" height="36" fill={LIGHT} />
    </svg>
    <div
      style={{
        fontFamily: DISPLAY_FONT,
        fontWeight: 800,
        fontSize: 56,
        letterSpacing: '-0.02em',
        color: LIGHT,
      }}
    >
      RestoreAssist
    </div>
  </div>
);

const Scene9Cta: React.FC = () => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const logoFade = fadeIn(frame, Math.round(fps * 0.5), fps * 0.8);
  const urlFade = fadeIn(frame, Math.round(fps * 2.5), fps * 0.8);
  return (
    <SceneBg>
      <AbsoluteFill style={{ flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 80 }}>
        <RaLogoLockup opacity={logoFade} />
        <div style={{ position: 'relative', opacity: urlFade }}>
          <div
            style={{
              fontFamily: DISPLAY_FONT,
              fontWeight: 700,
              fontSize: 96,
              color: LIGHT,
              letterSpacing: '-0.02em',
            }}
          >
            restoreassist.app
          </div>
          <div
            style={{
              position: 'absolute',
              left: 0,
              right: 0,
              bottom: -8,
              height: 6,
              background: WARM,
              transform: `scaleX(${interpolate(frame, [fps * 3.2, fps * 4.0], [0, 1], { extrapolateLeft: 'clamp', extrapolateRight: 'clamp' })})`,
              transformOrigin: 'left',
            }}
          />
        </div>
      </AbsoluteFill>
    </SceneBg>
  );
};

// ── Scene 10 · Silent lockup (72–75s) ──────────────────────────────────────

const Scene10Lockup: React.FC = () => (
  <SceneBg>
    <AbsoluteFill style={{ flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: 80 }}>
      <RaLogoLockup opacity={1} />
      <div style={{ position: 'relative' }}>
        <div
          style={{
            fontFamily: DISPLAY_FONT,
            fontWeight: 700,
            fontSize: 96,
            color: LIGHT,
            letterSpacing: '-0.02em',
          }}
        >
          restoreassist.app
        </div>
        <div
          style={{
            position: 'absolute',
            left: 0,
            right: 0,
            bottom: -8,
            height: 6,
            background: WARM,
          }}
        />
      </div>
    </AbsoluteFill>
  </SceneBg>
);

// ── Default props ──────────────────────────────────────────────────────────

export const defaultRaWave1Props: RaWave1Props = {
  brand: 'ra',
  storyboard: [
    { sceneId: 'scene-01-hook', durationSec: 3, voiceover: '', onScreenText: '', voiceoverAudioPath: 'audio/ra-wave-1-launch-poc/scene-0.mp3' },
    { sceneId: 'scene-02-problem-montage', durationSec: 13.8, voiceover: '', onScreenText: '', voiceoverAudioPath: 'audio/ra-wave-1-launch-poc/scene-1.mp3' },
    { sceneId: 'scene-03-pivot-demo1', durationSec: 13.1, voiceover: '', onScreenText: '', voiceoverAudioPath: 'audio/ra-wave-1-launch-poc/scene-2.mp3' },
    { sceneId: 'scene-04-demo-storage-byok', durationSec: 13, voiceover: '', onScreenText: '', voiceoverAudioPath: 'audio/ra-wave-1-launch-poc/scene-3.mp3' },
    { sceneId: 'scene-05-demo-inbound', durationSec: 10, voiceover: '', onScreenText: '', voiceoverAudioPath: 'audio/ra-wave-1-launch-poc/scene-4.mp3' },
    { sceneId: 'scene-06-positioning', durationSec: 10.5, voiceover: '', onScreenText: '', voiceoverAudioPath: 'audio/ra-wave-1-launch-poc/scene-5.mp3' },
    { sceneId: 'scene-07-proof-numbers', durationSec: 11, voiceover: '', onScreenText: '', voiceoverAudioPath: 'audio/ra-wave-1-launch-poc/scene-6.mp3' },
    { sceneId: 'scene-08-australian-built', durationSec: 7, voiceover: '', onScreenText: '', voiceoverAudioPath: 'audio/ra-wave-1-launch-poc/scene-7.mp3' },
    { sceneId: 'scene-09-cta-spoken', durationSec: 7, voiceover: '', onScreenText: '', voiceoverAudioPath: 'audio/ra-wave-1-launch-poc/scene-8.mp3' },
    { sceneId: 'scene-10-silent-lockup', durationSec: 3, voiceover: '', onScreenText: '' }, // scene 10 silent by design
  ],
};

// ── Composition ────────────────────────────────────────────────────────────

const SCENE_ORDER = [
  Scene1Hook,
  Scene2Problem,
  Scene3Pivot,
  Scene4Storage,
  Scene5Inbound,
  Scene6Positioning,
  Scene7Proof,
  Scene8Tagline,
  Scene9Cta,
  Scene10Lockup,
];

export const RaWave1Launch: React.FC<RaWave1Props> = ({ storyboard }) => {
  const { fps } = useVideoConfig();
  let cursor = 0;
  return (
    // v2 — outer background NAVY (not DARK) so the GAP_FRAMES between
    // scenes reads as a brief navy fade-through, not a black flash.
    <AbsoluteFill style={{ backgroundColor: NAVY }}>
      {storyboard.map((scene, i) => {
        const Component = SCENE_ORDER[i];
        if (!Component) return null;
        const start = cursor;
        const baseDur = Math.max(1, Math.round(scene.durationSec * fps));
        // Scene Sequence runs for baseDur + TAIL_FRAMES so content holds after VO ends.
        const seqDur = baseDur + TAIL_FRAMES;
        // Cursor advances by seqDur + GAP_FRAMES so next scene starts after the breath.
        cursor += seqDur + GAP_FRAMES;
        return (
          <Sequence
            key={scene.sceneId}
            from={start}
            durationInFrames={seqDur}
            name={scene.sceneId}
          >
            <Component />
            {scene.voiceoverAudioPath ? (
              <Audio src={staticFile(scene.voiceoverAudioPath)} />
            ) : null}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
