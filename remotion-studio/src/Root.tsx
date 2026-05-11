import React from 'react';
import { Composition } from 'remotion';
import { Explainer, defaultExplainerProps, explainerSchema } from './compositions/Explainer';
import {
  CoutisIntro75,
  defaultCoutisIntroProps,
  coutisIntroSchema,
} from './compositions/CoutisIntro75';

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
    </>
  );
};
