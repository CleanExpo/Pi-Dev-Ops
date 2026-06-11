'use client';

import Image from 'next/image';
import { useState } from 'react';
import {
  SynthexMark, RestoreAssistMark, DRPlatformMark,
  NRPGMark, CARSIMark, CCWMark
} from '@/components/ui/marks';

const BUSINESS_LOGOS: Record<string, string> = {
  'synthex':           '/logos/synthex.png',
  'restoreassist':     '/logos/restoreassist.png',
  'disaster-recovery': '/logos/disaster-recovery.png',
  'dr-nrpg':           '/logos/nrpg.png',
  'carsi':             '/logos/carsi.png',
  'ccw-crm':           '/logos/ccw.svg',
};

const BUSINESS_MARKS: Record<string, React.ComponentType<{ size?: number; color?: string }>> = {
  'synthex':           SynthexMark,
  'restoreassist':     RestoreAssistMark,
  'disaster-recovery': DRPlatformMark,
  'dr-nrpg':           NRPGMark,
  'carsi':             CARSIMark,
  'ccw-crm':           CCWMark,
};

const BUSINESS_COLORS: Record<string, string> = {
  'synthex':           '#6366f1',
  'restoreassist':     '#0E7C7B',
  'disaster-recovery': '#0B2545',
  'dr-nrpg':           '#1A2A4F',
  'carsi':             '#B85C38',
  'ccw-crm':           '#D62828',
};

interface BusinessLogoProps {
  slug: string;
  size?: 'sm' | 'md' | 'lg';
  showMark?: boolean;
  className?: string;
}

export function BusinessLogo({ slug, size = 'md', showMark = false, className }: BusinessLogoProps) {
  const [imgError, setImgError] = useState(false);
  const logoPath = BUSINESS_LOGOS[slug];
  const Mark = BUSINESS_MARKS[slug];
  const color = BUSINESS_COLORS[slug] ?? 'var(--ink-secondary)';

  const dims = { sm: 24, md: 32, lg: 48 }[size];

  // If no logo or image failed, show the geometric mark
  if (!logoPath || imgError || showMark) {
    if (!Mark) return null;
    return (
      <div
        className={className}
        style={{
          width: dims,
          height: dims,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          borderRadius: 4,
          background: `${color}18`,
          border: `1px solid ${color}40`,
          flexShrink: 0,
        }}
      >
        <Mark size={dims * 0.6} color={color} />
      </div>
    );
  }

  return (
    <div
      className={className}
      style={{
        width: dims,
        height: dims,
        borderRadius: 4,
        overflow: 'hidden',
        flexShrink: 0,
        background: 'var(--surface-2)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <Image
        src={logoPath}
        alt={slug}
        width={dims}
        height={dims}
        style={{ objectFit: 'contain', maxWidth: '100%', maxHeight: '100%' }}
        onError={() => setImgError(true)}
      />
    </div>
  );
}
