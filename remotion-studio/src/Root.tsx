import React from 'react';
import { Composition } from 'remotion';
import { Explainer, defaultExplainerProps, explainerSchema } from './compositions/Explainer';

export const RemotionRoot: React.FC = () => {
  return (
    <>
      <Composition
        id="Explainer"
        component={Explainer}
        durationInFrames={1800}
        fps={30}
        width={1920}
        height={1080}
        schema={explainerSchema}
        defaultProps={defaultExplainerProps}
      />
    </>
  );
};
