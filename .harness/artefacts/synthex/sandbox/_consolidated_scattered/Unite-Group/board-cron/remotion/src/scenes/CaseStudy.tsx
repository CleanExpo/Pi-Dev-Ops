// Requires: npm install remotion @remotion/core in board-cron/remotion/
// Composition: CaseStudyVideo — 1080x1920 (vertical short-form), 60-90s at 30fps
// Used by: SYN-508 Featured in Synthex pipeline

import React from 'react';

// If Remotion is available, these imports will work:
// import { AbsoluteFill, useCurrentFrame, useVideoConfig, interpolate } from 'remotion';

export interface CaseStudyVideoProps {
  clientName: string;
  intro: string;
  results: string;
  quote: string;
  cta: string;
  accentColor?: string;
}

// Remotion composition: 1080x1920, 30fps, ~2100 frames (70s)
export const CaseStudyVideo: React.FC<CaseStudyVideoProps> = ({
  clientName,
  intro,
  results,
  quote,
  cta,
  accentColor = '#7c3aed',
}) => {
  // Sections: intro (0-300f), results (300-900f), quote (900-1200f), cta (1200-1500f)
  return (
    <div
      style={{
        width: 1080,
        height: 1920,
        background: '#0a0a0a',
        color: '#ffffff',
        fontFamily: 'sans-serif',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 80,
        gap: 40,
      }}
    >
      <div style={{ fontSize: 48, fontWeight: 700, color: accentColor, textAlign: 'center' }}>
        {clientName}
      </div>
      <div style={{ fontSize: 36, textAlign: 'center', lineHeight: 1.4 }}>
        {intro}
      </div>
      <div style={{ fontSize: 28, textAlign: 'center', color: '#a3a3a3', lineHeight: 1.5 }}>
        {results}
      </div>
      <div style={{ fontSize: 32, fontStyle: 'italic', textAlign: 'center', color: '#e5e5e5' }}>
        {quote}
      </div>
      <div
        style={{
          background: accentColor,
          borderRadius: 16,
          padding: '20px 40px',
          fontSize: 28,
          fontWeight: 600,
          textAlign: 'center',
        }}
      >
        {cta}
      </div>
      <div style={{ position: 'absolute', bottom: 60, fontSize: 24, color: '#6b7280' }}>
        synthex.social
      </div>
    </div>
  );
};
