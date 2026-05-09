import Link from 'next/link';
import { notFound } from 'next/navigation';
import { loadIterationJob, type IterationVariant } from '@/lib/loadSpecs';

const BREAKPOINTS = [
  { label: 'mobile', width: 375 },
  { label: 'tablet', width: 768 },
  { label: 'desktop', width: 1440 },
];

function MiniBrand({ variant }: { variant: IterationVariant }) {
  const t = variant.design;
  const primary = t.colors.primary;
  const accent = t.colors.accent;
  const surface = t.colors['neutral-50'] ?? '#fff';
  const onSurface = t.colors['neutral-900'] ?? '#000';
  const display = t.typography['display-md'] ?? t.typography['display-lg'];
  const body = t.typography['body-md'];
  return (
    <div style={{ background: surface, color: onSurface, padding: 24, height: '100%', display: 'flex', flexDirection: 'column', justifyContent: 'space-between' }}>
      <div>
        <div style={{ background: primary, color: t.colors['on-primary'] ?? '#fff', padding: '8px 12px', borderRadius: 4, fontFamily: 'JetBrains Mono, monospace', fontSize: 10, display: 'inline-block', marginBottom: 16 }}>
          {variant.variant}
        </div>
        <div style={{ fontFamily: display?.fontFamily, fontSize: display?.fontSize, fontWeight: display?.fontWeight as number, lineHeight: display?.lineHeight as number, marginBottom: 12 }}>
          {t.name}
        </div>
        <div style={{ fontFamily: body?.fontFamily, fontSize: body?.fontSize, fontWeight: body?.fontWeight as number, lineHeight: body?.lineHeight as number, opacity: 0.8 }}>
          {t.description ?? 'Design variant under review.'}
        </div>
      </div>
      <div style={{ display: 'flex', gap: 8 }}>
        <div style={{ background: accent, color: t.colors['on-accent'] ?? '#000', padding: '10px 14px', borderRadius: 8, fontWeight: 600, fontSize: 14 }}>Primary CTA</div>
        <div style={{ background: t.colors.secondary ?? '#000', color: '#fff', padding: '10px 14px', borderRadius: 8, fontWeight: 600, fontSize: 14 }}>Secondary</div>
      </div>
    </div>
  );
}

export default async function BoardPage({ params }: { params: Promise<{ jobId: string }> }) {
  const { jobId } = await params;
  const variants = loadIterationJob(jobId);
  if (variants.length === 0) notFound();

  return (
    <main className="shell" style={{ maxWidth: 1800 }}>
      <div style={{ marginBottom: 8, fontFamily: 'JetBrains Mono, monospace', fontSize: 11 }}>
        <Link href="/" style={{ color: '#6e7780' }}>← all jobs</Link>
      </div>
      <h1>Board · {jobId}</h1>
      <p className="lede">{variants.length} variants × {BREAKPOINTS.length} breakpoints. Each row is a device width; each column is a variant. Pick one to approve.</p>

      <div style={{ display: 'grid', gridTemplateRows: `repeat(${BREAKPOINTS.length}, auto)`, gap: 24 }}>
        {BREAKPOINTS.map((bp) => (
          <div key={bp.label}>
            <div style={{ marginBottom: 8, fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: '#8b949b' }}>{bp.label} · {bp.width}px</div>
            <div style={{ display: 'grid', gridTemplateColumns: `repeat(${variants.length}, 1fr)`, gap: 12 }}>
              {variants.map((v) => (
                <div key={v.variant} style={{ border: '1px solid #1f242a', borderRadius: 8, overflow: 'hidden', height: 360 }}>
                  <div style={{ width: bp.width, transform: `scale(${Math.min(1, 360 / bp.width)})`, transformOrigin: 'top left', height: 360 }}>
                    <MiniBrand variant={v} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>
    </main>
  );
}
