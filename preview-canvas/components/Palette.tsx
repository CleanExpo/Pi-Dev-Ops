import { contrastRatio, wcagLevel, type DesignTokens } from '@/lib/loadSpecs';

const TEXT_PAIRS: Array<[string, string]> = [
  ['on-primary', 'primary'],
  ['on-secondary', 'secondary'],
  ['on-accent', 'accent'],
  ['neutral-900', 'neutral-50'],
  ['neutral-50', 'neutral-900'],
];

export function Palette({ tokens }: { tokens: DesignTokens }) {
  const swatches = Object.entries(tokens.colors).filter(
    ([k, v]) => typeof v === 'string' && v.startsWith('#'),
  );

  return (
    <section style={{ marginBottom: 32 }}>
      <h3 style={{ margin: '0 0 12px', fontSize: 14, fontWeight: 600, color: '#8b949b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Colour</h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(140px, 1fr))', gap: 8 }}>
        {swatches.map(([name, hex]) => (
          <div key={name} style={{ borderRadius: 8, overflow: 'hidden', border: '1px solid #1f242a' }}>
            <div style={{ background: hex, height: 64 }} />
            <div style={{ padding: '8px 10px', background: '#11141a', fontFamily: 'JetBrains Mono, monospace', fontSize: 11 }}>
              <div style={{ color: '#c4cdd3' }}>{name}</div>
              <div style={{ color: '#6e7780' }}>{hex}</div>
            </div>
          </div>
        ))}
      </div>

      <h3 style={{ margin: '20px 0 12px', fontSize: 14, fontWeight: 600, color: '#8b949b', textTransform: 'uppercase', letterSpacing: '0.05em' }}>Contrast (WCAG)</h3>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))', gap: 8 }}>
        {TEXT_PAIRS.map(([fgName, bgName]) => {
          const fg = tokens.colors[fgName];
          const bg = tokens.colors[bgName];
          if (!fg || !bg || !fg.startsWith('#') || !bg.startsWith('#')) return null;
          const ratio = contrastRatio(fg, bg);
          const level = wcagLevel(ratio);
          const color = level === 'fail' ? '#EF4444' : level === 'AA-large' ? '#E0A800' : '#3FA34D';
          return (
            <div key={`${fgName}-on-${bgName}`} style={{ background: bg, color: fg, padding: '12px 14px', borderRadius: 6, border: '1px solid #1f242a' }}>
              <div style={{ fontSize: 16, fontWeight: 600 }}>{fgName} on {bgName}</div>
              <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, marginTop: 4 }}>
                <span style={{ color, padding: '2px 6px', background: 'rgba(0,0,0,0.2)', borderRadius: 4 }}>{level}</span>
                <span style={{ marginLeft: 8, opacity: 0.85 }}>{ratio.toFixed(2)}:1</span>
              </div>
            </div>
          );
        })}
      </div>
    </section>
  );
}
