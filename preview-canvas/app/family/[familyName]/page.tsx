import Link from 'next/link';
import { listBrands, loadDesign, tryLoadMotion, type DesignTokens, type MotionTokens } from '@/lib/loadSpecs';

// Static family map (mirrors BrandConfig.colour.family) so this page can run
// without parsing the .ts files. Keep in sync with brands when new ones land.
const FAMILY_OF: Record<string, string> = {
  ra: 'restoration',
  dr: 'safety',
  nrpg: 'safety',
  carsi: 'training',
  ccw: 'consumer',
  synthex: 'industrial',
  unite: 'industrial',
};

interface FamilyMember {
  slug: string;
  design: DesignTokens;
  motion: MotionTokens | null;
}

function CoherenceCheck({ members }: { members: FamilyMember[] }) {
  if (members.length < 2) return null;

  const signatures = new Set(members.map((m) => m.motion?.signature.name).filter(Boolean));
  const fonts = new Set(
    members
      .map((m) => Object.values(m.design.typography)[0]?.fontFamily)
      .filter(Boolean),
  );
  const checks = [
    {
      label: 'Signature motion',
      ok: signatures.size === 1,
      detail: signatures.size === 1 ? `all share '${[...signatures][0]}'` : `drift: ${[...signatures].join(', ')}`,
    },
    {
      label: 'Display typeface',
      ok: fonts.size === 1,
      detail: fonts.size === 1 ? `all use ${[...fonts][0]}` : `drift: ${[...fonts].join(', ')}`,
    },
  ];

  return (
    <div style={{ marginBottom: 24, padding: 16, border: '1px solid #1f242a', borderRadius: 8 }}>
      <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 11, color: '#8b949b', marginBottom: 8 }}>COHERENCE</div>
      {checks.map((c) => (
        <div key={c.label} style={{ display: 'flex', gap: 12, alignItems: 'baseline', padding: '4px 0' }}>
          <span style={{ color: c.ok ? '#3FA34D' : '#E0A800' }}>{c.ok ? '✓' : '⚠'}</span>
          <span style={{ fontWeight: 600 }}>{c.label}</span>
          <span style={{ color: '#8b949b', fontSize: 13 }}>— {c.detail}</span>
        </div>
      ))}
    </div>
  );
}

export default async function FamilyPage({ params }: { params: Promise<{ familyName: string }> }) {
  const { familyName } = await params;
  const slugs = listBrands().filter((slug) => FAMILY_OF[slug] === familyName);

  const members: FamilyMember[] = slugs.map((slug) => ({
    slug,
    design: loadDesign(slug),
    motion: tryLoadMotion(slug),
  }));

  return (
    <main className="shell" style={{ maxWidth: 1800 }}>
      <div style={{ marginBottom: 8, fontFamily: 'JetBrains Mono, monospace', fontSize: 11 }}>
        <Link href="/" style={{ color: '#6e7780' }}>← home</Link>
      </div>
      <h1>Family · {familyName}</h1>
      <p className="lede">{members.length} brand{members.length === 1 ? '' : 's'} in this family.</p>

      <CoherenceCheck members={members} />

      <div style={{ display: 'grid', gridTemplateColumns: `repeat(${Math.max(1, members.length)}, 1fr)`, gap: 16 }}>
        {members.map((m) => (
          <Link
            key={m.slug}
            href={`/brand/${m.slug}`}
            style={{
              background: m.design.colors.primary,
              color: m.design.colors['on-primary'] ?? '#fff',
              padding: 24,
              borderRadius: 8,
              textDecoration: 'none',
              display: 'block',
            }}
          >
            <div style={{ fontFamily: 'JetBrains Mono, monospace', fontSize: 10, opacity: 0.7 }}>{m.slug}</div>
            <div style={{ fontSize: 28, fontWeight: 700, marginTop: 4 }}>{m.design.name}</div>
            <div style={{ marginTop: 12, fontSize: 12, opacity: 0.85 }}>
              signature: {m.motion?.signature.name ?? 'n/a'}
            </div>
          </Link>
        ))}
      </div>
    </main>
  );
}
