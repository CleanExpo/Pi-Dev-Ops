export const dynamic = 'force-dynamic';
/**
 * SYN-512: Synthex Client Authority Hub — Full Implementation
 * SYN-519 shipped the ISR skeleton. This is the full production build.
 *
 * ISR: Revalidate every hour. Authority Hub pages carry LocalBusiness schema
 * for Google's E.E.A.T. assessment — DO NOT remove revalidate export.
 */

// ISR config — must be at module level for Next.js to pick it up
export const revalidate = 3600; // DO NOT REMOVE (SYN-519/SYN-512)

import { notFound } from 'next/navigation';
import type { Metadata } from 'next';
import { getClientBySlug } from '@/lib/clients/getClientBySlug';
import { getClientVideos } from '@/lib/videos/getClientVideos';
import { AuthorityHubAnalytics } from './AuthorityHubAnalytics';

interface AuthorityHubPageProps {
  params: Promise<{ slug: string }>;
}

export async function generateMetadata({ params }: AuthorityHubPageProps): Promise<Metadata> {
  const { slug } = await params;
  const client = await getClientBySlug(slug);
  if (!client) {
    return { title: 'Not Found — Synthex' };
  }
  return {
    title: `${client.business_name} — Synthex Authority Hub`,
    description: client.description ?? `Verified authority profile for ${client.business_name} on Synthex.`,
    robots: { index: true, follow: true },
    openGraph: {
      title: `${client.business_name} — Synthex Authority Hub`,
      description: client.description ?? `Verified authority profile for ${client.business_name} on Synthex.`,
      type: 'website',
    },
  };
}

export default async function AuthorityHubPage({ params }: AuthorityHubPageProps) {
  const { slug } = await params;
  const client = await getClientBySlug(slug);
  if (!client) notFound();

  const videos = await getClientVideos(client.id);

  const location = [client.address_suburb, client.address_state]
    .filter(Boolean)
    .join(', ');

  return (
    <>
      
      
      <AuthorityHubAnalytics clientSlug={slug} />

      <main style={{ minHeight: '100vh', background: 'var(--canvas)', color: 'var(--ink-primary)' }}>
        {/* Hero */}
        <section style={{ borderBottom: '1px solid #27272a', background: 'var(--surface-1)' }}>
          <div style={{ maxWidth: 896, margin: '0 auto', padding: '48px 16px' }}>
            <div style={{ display: 'flex', alignItems: 'flex-start', gap: 24 }}>
              {client.logo_url && (
                <img
                  src={client.logo_url}
                  alt={`${client.business_name} logo`}
                  style={{ width: 80, height: 80, borderRadius: 8, objectFit: 'cover', border: '1px solid #27272a', flexShrink: 0 }}
                />
              )}
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 8, marginBottom: 8 }}>
                  <span style={{ display: 'inline-flex', alignItems: 'center', padding: '2px 10px', borderRadius: 9999, fontSize: 12, fontWeight: 500, background: 'rgba(29,78,216,0.1)', color: '#60a5fa', border: '1px solid rgba(29,78,216,0.2)' }}>
                    {client.industry}
                  </span>
                  <span style={{ display: 'inline-flex', alignItems: 'center', padding: '2px 10px', borderRadius: 9999, fontSize: 12, fontWeight: 500, background: 'rgba(22,163,74,0.1)', color: '#4ade80', border: '1px solid rgba(22,163,74,0.2)' }}>
                    Verified by Synthex
                  </span>
                  
                </div>
                <h1 style={{ fontSize: 30, fontWeight: 700, letterSpacing: '-0.03em', color: 'var(--ink-primary)', margin: 0 }}>{client.business_name}</h1>
                {location && (
                  <p style={{ marginTop: 4, color: 'var(--ink-secondary)', fontSize: 14, display: 'flex', alignItems: 'center', gap: 4 }}>
                    <svg style={{ width: 16, height: 16, flexShrink: 0 }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1 1 15 0Z" />
                    </svg>
                    {location}
                  </p>
                )}
                {client.description && (
                  <p style={{ marginTop: 12, color: 'var(--ink-secondary)', lineHeight: 1.6, maxWidth: 672 }}>
                    {client.description}
                  </p>
                )}
              </div>
            </div>
          </div>
        </section>

        <div style={{ maxWidth: 896, margin: '0 auto', padding: '40px 16px', display: 'flex', flexDirection: 'column', gap: 40 }}>
          {/* Authority Score — SYN-513 will populate this */}
          <section>
            <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16, color: 'var(--ink-primary)' }}>Authority Score</h2>
            <div style={{ borderRadius: 12, border: '1px solid #27272a', background: 'var(--surface-1)', padding: 24, display: 'flex', alignItems: 'center', gap: 24 }}>
              <div style={{ width: 80, height: 80, borderRadius: '50%', background: 'var(--surface-1)', display: 'flex', alignItems: 'center', justifyContent: 'center', border: '4px solid #27272a', flexShrink: 0 }}>
                <span style={{ fontSize: 24, fontWeight: 700, color: 'var(--ink-secondary)' }}>—</span>
              </div>
              <div>
                <p style={{ fontWeight: 500, color: 'var(--ink-secondary)', fontSize: 14, margin: 0 }}>Coming soon</p>
                <p style={{ fontSize: 14, color: 'var(--ink-secondary)', marginTop: 4 }}>
                  Authority Score is being calculated based on E.E.A.T. signals.
                  Full score available once analysis is complete.
                </p>
              </div>
            </div>
          </section>

          {/* E.E.A.T. Metrics Grid */}
          <section>
            <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16, color: 'var(--ink-primary)' }}>E.E.A.T. Index</h2>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16 }}>
              {(['Expertise', 'Experience', 'Authoritativeness', 'Trustworthiness'] as const).map((metric) => (
                <div key={metric} style={{ borderRadius: 12, border: '1px solid #27272a', background: 'var(--surface-1)', padding: 16, textAlign: 'center' }}>
                  <p style={{ fontSize: 24, fontWeight: 700, color: 'var(--ink-secondary)', margin: 0 }}>—</p>
                  <p style={{ fontSize: 12, color: 'var(--ink-secondary)', marginTop: 4, fontWeight: 500 }}>{metric}</p>
                </div>
              ))}
            </div>
          </section>

          {/* Social Proof */}
          <section>
            <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16, color: 'var(--ink-primary)' }}>Social Proof</h2>
            <div style={{ borderRadius: 12, border: '1px solid #27272a', background: 'var(--surface-1)', padding: 24 }}>
              <p style={{ fontSize: 14, color: 'var(--ink-secondary)', textAlign: 'center', padding: '16px 0', margin: 0 }}>
                Social proof metrics loading — check back soon.
              </p>
            </div>
          </section>

          {/* Contact */}
          {(client.phone || client.website_url || client.address_street) && (
            <section>
              <h2 style={{ fontSize: 18, fontWeight: 600, marginBottom: 16, color: 'var(--ink-primary)' }}>Contact</h2>
              <div style={{ borderRadius: 12, border: '1px solid #27272a', background: 'var(--surface-1)', padding: 24, display: 'flex', flexDirection: 'column', gap: 12 }}>
                {client.phone && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--ink-secondary)', fontSize: 14 }}>
                    <svg style={{ width: 16, height: 16, flexShrink: 0 }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M2.25 6.75c0 8.284 6.716 15 15 15h2.25a2.25 2.25 0 0 0 2.25-2.25v-1.372c0-.516-.351-.966-.852-1.091l-4.423-1.106c-.44-.11-.902.055-1.173.417l-.97 1.293c-.282.376-.769.542-1.21.38a12.035 12.035 0 0 1-7.143-7.143c-.162-.441.004-.928.38-1.21l1.293-.97c.363-.271.527-.734.417-1.173L6.963 3.102a1.125 1.125 0 0 0-1.091-.852H4.5A2.25 2.25 0 0 0 2.25 4.5v2.25Z" />
                    </svg>
                    <a href={`tel:${client.phone}`} style={{ color: 'var(--ink-secondary)', textDecoration: 'none' }}>{client.phone}</a>
                  </div>
                )}
                {client.website_url && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--ink-secondary)', fontSize: 14 }}>
                    <svg style={{ width: 16, height: 16, flexShrink: 0 }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M13.19 8.688a4.5 4.5 0 0 1 1.242 7.244l-4.5 4.5a4.5 4.5 0 0 1-6.364-6.364l1.757-1.757m13.35-.622 1.757-1.757a4.5 4.5 0 0 0-6.364-6.364l-4.5 4.5a4.5 4.5 0 0 0 1.242 7.244" />
                    </svg>
                    <a href={client.website_url} target="_blank" rel="noopener noreferrer" style={{ color: 'var(--ink-secondary)', textDecoration: 'none', overflow: 'hidden', textOverflow: 'ellipsis', maxWidth: 288 }}>
                      {client.website_url.replace(/^https?:\/\//, '')}
                    </a>
                  </div>
                )}
                {client.address_street && (
                  <div style={{ display: 'flex', alignItems: 'center', gap: 8, color: 'var(--ink-secondary)', fontSize: 14 }}>
                    <svg style={{ width: 16, height: 16, flexShrink: 0 }} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M15 10.5a3 3 0 1 1-6 0 3 3 0 0 1 6 0Z" />
                      <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 10.5c0 7.142-7.5 11.25-7.5 11.25S4.5 17.642 4.5 10.5a7.5 7.5 0 1 1 15 0Z" />
                    </svg>
                    <span>{[client.address_street, client.address_suburb, client.address_state, client.address_postcode].filter(Boolean).join(', ')}</span>
                  </div>
                )}
              </div>
            </section>
          )}
        </div>
      </main>
    </>
  );
}
