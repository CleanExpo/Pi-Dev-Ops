'use client';

import { motion } from 'framer-motion';
import type { DesignTokens, MotionTokens } from '@/lib/loadSpecs';

function bezierToArray(s: string): number[] | undefined {
  const m = /cubic-bezier\(([-0-9.,\s]+)\)/.exec(s);
  if (!m) return undefined;
  return m[1].split(',').map((n) => Number(n.trim()));
}

export function MotionStrip({ design, motion: m }: { design: DesignTokens; motion: MotionTokens }) {
  const fps = m.fps;
  const easings = Object.entries(m.easings);
  const durBase = typeof m.durations.base === 'number' ? m.durations.base : 18;
  const durSec = durBase / fps;

  return (
    <section style={{ marginBottom: 32 }}>
      <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600, color: '#8b949b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Motion</h3>
      <div style={{ background: design.colors['neutral-50'] ?? '#fff', color: design.colors['neutral-900'] ?? '#000', padding: 24, borderRadius: 8, border: '1px solid #1f242a' }}>
        <div style={{ marginBottom: 12, fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: '#6e7780' }}>
          signature: <strong>{m.signature.name}</strong> · base {durBase}f @ {fps}fps · {durSec.toFixed(2)}s
        </div>
        <div style={{ display: 'grid', gap: 12 }}>
          {easings.map(([name, ez]) => {
            const arr = bezierToArray(ez.bezier);
            return (
              <div key={name} style={{ display: 'grid', gridTemplateColumns: '160px 1fr', gap: 16, alignItems: 'center' }}>
                <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11 }}>
                  <div>{name}</div>
                  <div style={{ color: '#6e7780', fontSize: 10 }}>{ez.use ?? ''}</div>
                </div>
                <div style={{ position: 'relative', height: 40, background: design.colors['neutral-100'] ?? '#eee', borderRadius: 4, overflow: 'hidden' }}>
                  <motion.div
                    initial={{ x: 0 }}
                    animate={{ x: 'calc(100% - 32px)' }}
                    transition={{
                      duration: durSec,
                      ease: arr && arr.length === 4 ? (arr as [number, number, number, number]) : undefined,
                      repeat: Infinity,
                      repeatType: 'reverse',
                    }}
                    style={{
                      width: 32,
                      height: 32,
                      margin: 4,
                      borderRadius: 4,
                      background: design.colors.primary,
                    }}
                  />
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
