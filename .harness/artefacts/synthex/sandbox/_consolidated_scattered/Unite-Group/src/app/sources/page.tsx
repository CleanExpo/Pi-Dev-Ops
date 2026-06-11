'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { supabaseClient } from '@/lib/supabase/client';
import { FeedMark, CheckCircleMark, ClockMark } from '@/components/ui/marks';

interface WikiSource {
  id: string;
  title?: string;
  status: string;
  created_at?: string;
  updated_at?: string;
}

function relativeDate(iso?: string): string {
  if (!iso) return '';
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' });
}

function truncate(str: string, len: number): string {
  return str.length > len ? str.slice(0, len) + '…' : str;
}

function guessWikiPage(title?: string): string | null {
  if (!title) return null;
  const t = title.toLowerCase();
  if (t.includes('synthex')) return 'synthex';
  if (t.includes('exit') || t.includes('thesis')) return 'exit-thesis';
  if (t.includes('tech') || t.includes('news') || t.includes('drop')) return 'tech-drops';
  if (t.includes('ma-intel') || t.includes('m&a') || t.includes('acquisition')) return 'exit-thesis';
  if (t.includes('restore') || t.includes('ra-')) return 'restore-assist';
  if (t.includes('carsi')) return 'carsi';
  if (t.includes('nrpg') || t.includes('dr-')) return 'dr-nrpg';
  if (t.includes('ccw') || t.includes('crm')) return 'ccw';
  if (t.includes('seo') || t.includes('linkable')) return 'seo-linkable-assets';
  if (t.includes('creator') || t.includes('radar')) return 'creator-radar';
  if (t.includes('pi-ceo') || t.includes('architecture')) return 'pi-ceo-architecture';
  return null;
}

export default function SourcesPage() {
  const router = useRouter();
  const [loading, setLoading]       = useState(true);
  const [completed, setCompleted]   = useState<WikiSource[]>([]);
  const [pending, setPending]       = useState<WikiSource[]>([]);

  useEffect(() => {
    supabaseClient.auth.getSession().then(({ data: { session } }) => {
      if (!session) { router.push('/login'); return; }

      Promise.all([
        supabaseClient
          .from('wiki_sources')
          .select('id, title, status, updated_at')
          .eq('status', 'completed')
          .order('updated_at', { ascending: false }),
        supabaseClient
          .from('wiki_sources')
          .select('id, title, status, updated_at')
          .eq('status', 'pending')
          .order('created_at', { ascending: false }),
      ]).then(([comp, pend]) => {
        setCompleted(comp.data || []);
        setPending(pend.data || []);
        setLoading(false);
      });
    });
  }, [router]);

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--canvas)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <div style={{ width: 24, height: 24, border: '2px solid var(--red-500)', borderTopColor: 'transparent', borderRadius: '50%', animation: 'spin 0.8s linear infinite' }} />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  // Last ingest time
  const lastIngest = completed[0]?.updated_at;

  return (
    <div style={{ minHeight: '100vh', background: 'var(--canvas)', color: 'var(--ink-primary)', padding: '32px 32px 64px' }}>

      {/* Header stats */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 32, flexWrap: 'wrap', gap: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 8,
            background: 'color-mix(in srgb, var(--red-500) 12%, transparent)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <FeedMark size={18} color="var(--red-500)" />
          </div>
          <div>
            <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--ink-primary)' }}>
              Sources Pipeline
            </h1>
            <p style={{ margin: 0, fontSize: 12, color: 'var(--ink-tertiary)', marginTop: 2 }}>
              Intelligence ingestion — files processed into 2nd Brain
            </p>
          </div>
        </div>

        {/* Stats strip */}
        <div style={{ display: 'flex', gap: 24 }}>
          <div style={{ textAlign: 'right' }}>
            <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--green-400)', fontFamily: 'var(--font-mono)', lineHeight: 1 }}>
              {completed.length}
            </div>
            <div style={{ fontSize: 10, color: 'var(--ink-tertiary)', marginTop: 2, textTransform: 'uppercase', letterSpacing: '0.07em' }}>sources processed</div>
          </div>
          {pending.length > 0 && (
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 28, fontWeight: 800, color: 'var(--orange-400)', fontFamily: 'var(--font-mono)', lineHeight: 1 }}>
                {pending.length}
              </div>
              <div style={{ fontSize: 10, color: 'var(--ink-tertiary)', marginTop: 2, textTransform: 'uppercase', letterSpacing: '0.07em' }}>pending</div>
            </div>
          )}
          {lastIngest && (
            <div style={{ textAlign: 'right' }}>
              <div style={{ fontSize: 13, fontWeight: 600, color: 'var(--ink-primary)', fontFamily: 'var(--font-mono)', lineHeight: 1.4 }}>
                {relativeDate(lastIngest)}
              </div>
              <div style={{ fontSize: 10, color: 'var(--ink-tertiary)', marginTop: 2, textTransform: 'uppercase', letterSpacing: '0.07em' }}>last ingest</div>
            </div>
          )}
        </div>
      </div>

      {/* Completed feed */}
      <div style={{ marginBottom: 40 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
          <CheckCircleMark size={13} color="var(--green-400)" />
          <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--green-400)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
            Intelligence Ingested — {completed.length} Sources Processed
          </span>
        </div>

        {/* Feed separator */}
        <div style={{ height: 1, background: 'var(--border-default)', marginBottom: 0 }} />

        <div style={{
          background: 'var(--surface-1)', border: '1px solid var(--border-default)',
          borderRadius: 'var(--radius-md)', overflow: 'hidden',
        }}>
          {completed.length === 0 ? (
            <div style={{ padding: '24px 20px', color: 'var(--ink-tertiary)', fontSize: 13 }}>
              No completed sources found.
            </div>
          ) : (
            completed.map((source, i) => {
              const name = source.title || source.id.replace(/-/g, ' ').slice(0, 50);
              const wikiPage = guessWikiPage(name);
              return (
                <div
                  key={source.id}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 12,
                    padding: '8px 16px',
                    borderBottom: i < completed.length - 1 ? '1px solid var(--border-default)' : 'none',
                  }}
                >
                  <CheckCircleMark size={12} color="var(--green-400)" />
                  <span style={{
                    flex: 1, fontSize: 12, color: 'var(--ink-secondary)',
                    fontFamily: 'var(--font-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {truncate(name, 50)}
                  </span>
                  {wikiPage && (
                    <span style={{ fontSize: 11, color: 'var(--ink-tertiary)', whiteSpace: 'nowrap' }}>
                      → <span style={{ color: 'var(--ink-secondary)' }}>{wikiPage}</span> updated
                    </span>
                  )}
                  <span style={{
                    fontSize: 11, color: 'var(--ink-tertiary)', fontFamily: 'var(--font-mono)',
                    whiteSpace: 'nowrap', minWidth: 60, textAlign: 'right',
                  }}>
                    {relativeDate(source.updated_at)}
                  </span>
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* Pending feed */}
      {pending.length > 0 && (
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 12 }}>
            <ClockMark size={13} color="var(--orange-400)" />
            <span style={{ fontSize: 11, fontWeight: 700, color: 'var(--orange-400)', textTransform: 'uppercase', letterSpacing: '0.08em' }}>
              Pending Ingestion — {pending.length} Queued
            </span>
          </div>

          <div style={{
            background: 'var(--surface-1)', border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-md)', overflow: 'hidden',
          }}>
            {pending.map((source, i) => {
              const name = source.title || source.id.replace(/-/g, ' ').slice(0, 50);
              return (
                <div
                  key={source.id}
                  style={{
                    display: 'flex', alignItems: 'center', gap: 12,
                    padding: '8px 16px',
                    borderBottom: i < pending.length - 1 ? '1px solid var(--border-default)' : 'none',
                  }}
                >
                  <ClockMark size={12} color="var(--orange-400)" />
                  <span style={{
                    flex: 1, fontSize: 12, color: 'var(--ink-secondary)',
                    fontFamily: 'var(--font-mono)', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap',
                  }}>
                    {truncate(name, 50)}
                  </span>
                  <span style={{ fontSize: 11, color: 'var(--ink-tertiary)', fontFamily: 'var(--font-mono)', whiteSpace: 'nowrap' }}>
                    {relativeDate(source.created_at)}
                  </span>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {completed.length === 0 && pending.length === 0 && (
        <div style={{ textAlign: 'center', padding: '80px 0', color: 'var(--ink-tertiary)' }}>
          <FeedMark size={40} color="var(--ink-tertiary)" />
          <p style={{ margin: '16px 0 0', fontSize: 14, color: 'var(--ink-secondary)' }}>No sources found in pipeline</p>
        </div>
      )}
    </div>
  );
}
