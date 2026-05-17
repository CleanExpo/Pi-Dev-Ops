import React from 'react';
import { Composition } from 'remotion';
import { Explainer, defaultExplainerProps, explainerSchema } from './compositions/Explainer';
import {
  CoutisIntro75,
  defaultCoutisIntroProps,
  coutisIntroSchema,
} from './compositions/CoutisIntro75';
import {
  RaWave1Launch,
  defaultRaWave1Props,
  raWave1Schema,
} from './compositions/RaWave1Launch';

const FPS = 30;

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="Explainer"
        component={Explainer}
        durationInFrames={1800}
        fps={FPS}
        width={1920}
        height={1080}
        schema={explainerSchema}
        defaultProps={defaultExplainerProps}
        calculateMetadata={({ props }) => {
          const sb = (props as { storyboard?: Array<{ durationSec?: number }> }).storyboard;
          if (!Array.isArray(sb) || sb.length === 0) {
            return { durationInFrames: 1800 };
          }
          const totalSec = sb.reduce((s, sc) => s + (sc.durationSec ?? 0), 0);
          const frames = Math.max(1, Math.round(totalSec * FPS));
          return { durationInFrames: frames };
        }}
      />
      <Composition
        id="CoutisIntro75"
        component={CoutisIntro75}
        durationInFrames={75 * FPS}
        fps={FPS}
        width={1920}
        height={1080}
        schema={coutisIntroSchema}
        defaultProps={defaultCoutisIntroProps}
        calculateMetadata={({ props }) => {
          const sc = (props as { scenes?: Array<{ durationSec?: number }> }).scenes;
          if (!Array.isArray(sc) || sc.length === 0) {
            return { durationInFrames: 75 * FPS };
          }
          const totalSec = sc.reduce((s, x) => s + (x.durationSec ?? 0), 0);
          return { durationInFrames: Math.max(1, Math.round(totalSec * FPS)) };
        }}
      />
      <Composition
        id="RaWave1Launch"
        component={RaWave1Launch}
        // v2 timing — default POC timings are audio-fit: 91.4s base + 7s scene padding, rounded up.
        durationInFrames={99 * FPS}
        fps={FPS}
        width={1080}
        height={1080}
        schema={raWave1Schema}
        defaultProps={defaultRaWave1Props}
        calculateMetadata={({ props }) => {
          // Must stay in sync with TAIL_FRAMES + GAP_FRAMES in RaWave1Launch.tsx (21 total per scene).
          const PADDING_PER_SCENE = 21;
          const sb = (props as { storyboard?: Array<{ durationSec?: number }> }).storyboard;
          if (!Array.isArray(sb) || sb.length === 0) {
            return { durationInFrames: 99 * FPS };
          }
          const totalSec = sb.reduce((s, x) => s + (x.durationSec ?? 0), 0);
          const baseFrames = Math.max(1, Math.round(totalSec * FPS));
          return { durationInFrames: baseFrames + sb.length * PADDING_PER_SCENE };
        }}
      />
    </>
  );
};
