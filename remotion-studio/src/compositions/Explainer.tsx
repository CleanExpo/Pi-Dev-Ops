import React from 'react';
import { AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { z } from 'zod';
import { brands } from '../brands';
import type { BrandSlug } from '../brands';
import { signatureEntry, brandFadeIn, staggerStart } from '../motion';
import { readableOn, brandGradient } from '../colour';

export const explainerSceneSchema = z.object({
  sceneId: z.string(),
  durationSec: z.number(),
  voiceover: z.string(),
  onScreenText: z.string(),
  voiceoverAudioPath: z.string().optional(),
});

export const explainerSchema = z.object({
  brand: z.enum(['dr', 'nrpg', 'ra', 'carsi', 'ccw', 'synthex', 'unite']),
  storyboard: z.array(explainerSceneSchema),
  hookSec: z.number(),
  ctaSec: z.number(),
});

export type ExplainerScene = z.infer<typeof explainerSceneSchema>;
export type ExplainerProps = z.infer<typeof explainerSchema>;

export const defaultExplainerProps: ExplainerProps = {
  brand: 'ra',
  hookSec: 8,
  ctaSec: 8,
  storyboard: [
    {
      sceneId: 'hook',
      durationSec: 8,
      onScreenText: 'Australia ships hundreds of restoration report formats. One should be enough.',
      voiceover: 'Australia ships hundreds of restoration report formats. One should be enough.',
    },
    {
      sceneId: 'body',
      durationSec: 44,
      onScreenText: 'The National Inspection Report standardises every job, every insurer, every assessor.',
      voiceover: 'The National Inspection Report standardises every job, every insurer, every assessor.',
    },
    {
      sceneId: 'cta',
      durationSec: 8,
      onScreenText: 'RestoreAssist. One National Inspection Standard.',
      voiceover: 'RestoreAssist. One National Inspection Standard.',
    },
  ],
};

const Hook: React.FC<{ text: string; brand: BrandSlug }> = ({ text, brand }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const cfg = brands[brand];
  const entry = signatureEntry({ frame, fps, motion: cfg.motion }, 0, 120);
  const fg = readableOn(cfg.colour.primary, cfg.colour);

  return (
    <AbsoluteFill
      style={{
        background: brandGradient(cfg.colour, 135),
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
          fontFamily: cfg.typography.display.family,
          fontWeight: cfg.typography.display.weight,
          fontSize: 96,
          lineHeight: 1.05,
          letterSpacing: '-0.02em',
          textAlign: 'center',
          maxWidth: 1600,
        }}
      >
        {text}
      </div>
    </AbsoluteFill>
  );
};

const Body: React.FC<{ text: string; brand: BrandSlug }> = ({ text, brand }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const cfg = brands[brand];
  const motion = { frame, fps, motion: cfg.motion };
  const titleEntry = signatureEntry(motion, 6, 60);
  const lineFade = brandFadeIn(motion, staggerStart(20, 0, 6));

  return (
    <AbsoluteFill
      style={{
        backgroundColor: cfg.colour.neutral['50'],
        padding: 96,
        flexDirection: 'column',
        justifyContent: 'center',
      }}
    >
      <div
        style={{
          color: cfg.colour.primary,
          fontFamily: cfg.typography.display.family,
          fontWeight: cfg.typography.display.weight,
          fontSize: 48,
          letterSpacing: '0.12em',
          textTransform: 'uppercase',
          marginBottom: 32,
          opacity: titleEntry.opacity,
          transform: `translateX(${titleEntry.translateX}px)`,
        }}
      >
        {cfg.displayName} — {cfg.tagline}
      </div>
      <div
        style={{
          color: cfg.colour.neutral['900'],
          fontFamily: cfg.typography.body.family,
          fontWeight: cfg.typography.body.weight,
          fontSize: 72,
          lineHeight: 1.2,
          maxWidth: 1500,
          opacity: lineFade,
        }}
      >
        {text}
      </div>
      <div
        style={{
          marginTop: 48,
          height: 8,
          width: 240,
          background: cfg.colour.accent,
          opacity: lineFade,
        }}
      />
    </AbsoluteFill>
  );
};

const Cta: React.FC<{ text: string; brand: BrandSlug }> = ({ text, brand }) => {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const cfg = brands[brand];
  const entry = signatureEntry({ frame, fps, motion: cfg.motion }, 0, 100);
  const fg = readableOn(cfg.colour.secondary, cfg.colour);

  return (
    <AbsoluteFill
      style={{
        backgroundColor: cfg.colour.secondary,
        alignItems: 'center',
        justifyContent: 'center',
        padding: 96,
      }}
    >
      <div
        style={{
          transform: `scale(${entry.scale}) translate(${entry.translateX}px, ${entry.translateY}px)`,
          opacity: entry.opacity,
          color: fg,
          fontFamily: cfg.typography.display.family,
          fontWeight: cfg.typography.display.weight,
          fontSize: 108,
          textAlign: 'center',
          letterSpacing: '-0.02em',
          lineHeight: 1.05,
        }}
      >
        {text}
      </div>
      <div
        style={{
          marginTop: 56,
          color: cfg.colour.accent,
          fontFamily: cfg.typography.body.family,
          fontSize: 36,
          letterSpacing: '0.18em',
          textTransform: 'uppercase',
          opacity: entry.opacity,
        }}
      >
        Learn more
      </div>
    </AbsoluteFill>
  );
};

export const Explainer: React.FC<ExplainerProps> = ({ brand, storyboard }) => {
  const { fps } = useVideoConfig();
  let cursor = 0;
  return (
    <AbsoluteFill style={{ backgroundColor: '#000' }}>
      {storyboard.map((scene) => {
        const start = cursor;
        const dur = Math.round(scene.durationSec * fps);
        cursor += dur;
        const Body$ =
          scene.sceneId === 'hook' ? Hook : scene.sceneId === 'cta' ? Cta : Body;
        return (
          <Sequence key={scene.sceneId} from={start} durationInFrames={dur} name={scene.sceneId}>
            <Body$ text={scene.onScreenText} brand={brand} />
            {scene.voiceoverAudioPath ? (
              <Audio src={staticFile(scene.voiceoverAudioPath)} />
            ) : null}
          </Sequence>
        );
      })}
    </AbsoluteFill>
  );
};
