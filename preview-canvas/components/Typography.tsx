import type { DesignTokens } from '@/lib/loadSpecs';

const SAMPLE: Record<string, string> = {
  'display-xl': 'One National Inspection Standard',
  'display-lg': 'One National Inspection Standard',
  'display-md': 'One National Inspection Standard',
  headline: 'A field-instrument readout, not a marketing site.',
  'body-lg': 'Lead with NIR data and field evidence — voice is direct, grounded, informed, human.',
  'body-md': 'Lead with NIR data and field evidence — voice is direct, grounded, informed, human.',
  caption: 'NIR-2024-04-15 · INSPECTOR-04 · MOISTURE 27%',
  'mono-md': 'NIR-2024-04-15-001',
  'mono-lg': 'NIR-2024-04-15-001',
};

export function Typography({ tokens }: { tokens: DesignTokens }) {
  const entries = Object.entries(tokens.typography);

  return (
    <section style={{ marginBottom: 32 }}>
      <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600, color: '#8b949b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Typography</h3>
      <div style={{ background: tokens.colors['neutral-50'] ?? '#fff', color: tokens.colors['neutral-900'] ?? '#000', padding: 24, borderRadius: 8, border: '1px solid #1f242a' }}>
        {entries.map(([name, t]) => (
          <div key={name} style={{ marginBottom: 16, display: 'grid', gridTemplateColumns: '120px 1fr', gap: 16, alignItems: 'baseline' }}>
            <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: '#6e7780' }}>{name}</div>
            <div
              style={{
                fontFamily: t.fontFamily,
                fontSize: t.fontSize,
                fontWeight: t.fontWeight as number,
                lineHeight: t.lineHeight as number,
                letterSpacing: t.letterSpacing,
              }}
            >
              {SAMPLE[name] ?? 'The quick brown fox jumps over the lazy dog.'}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}
