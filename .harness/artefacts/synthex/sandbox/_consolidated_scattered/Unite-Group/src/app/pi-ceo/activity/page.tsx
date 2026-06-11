'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { supabaseClient } from '@/lib/supabase/client';
import { RefreshMark, ActivityMark, BranchMark, AlertMark, ArrowUpRightMark } from '@/components/ui/marks';

interface ActivityRecord {
  id: string;
  project_id?: string;
  action_type?: string;
  title?: string;
  detail?: string;
  url?: string;
  created_at?: string;
}

const BUSINESS_COLORS: Record<string, string> = {
  synthex:          '#6366f1',
  restoreassist:    '#0E7C7B',
  'restore-assist': '#0E7C7B',
  'disaster-recovery': '#0B2545',
  'dr-nrpg':        '#1A2A4F',
  'dr-platform':    '#0B2545',
  nrpg:             '#1A2A4F',
  carsi:            '#B85C38',
  'ccw-crm':        '#D62828',
  ccw:              '#D62828',
};

function bizColor(projectId?: string): string {
  if (!projectId) return 'var(--ink-tertiary)';
  const key = projectId.toLowerCase();
  return BUSINESS_COLORS[key] || 'var(--ink-secondary)';
}

function ActionMark({ type }: { type?: string }) {
  const t = (type || '').toLowerCase();
  if (t.includes('pr_merged') || t.includes('deploy') || t.includes('branch')) {
    return <BranchMark size={14} color="var(--ink-secondary)" />;
  }
  if (t.includes('security') || t.includes('alert') || t.includes('vulnerability')) {
    return <AlertMark size={14} color="var(--red-500)" />;
  }
  return <ActivityMark size={14} color="var(--ink-tertiary)" />;
}

function timeAgo(dateStr?: string): string {
  if (!dateStr) return '';
  const diff = Date.now() - new Date(dateStr).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  const days = Math.floor(hrs / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(dateStr).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' });
}

export default function ActivityPage() {
  const router = useRouter();
  const [loading, setLoading]       = useState(true);
  const [allRecords, setAllRecords] = useState<ActivityRecord[]>([]);
  const [projectFilter, setProjectFilter] = useState<string>('all');
  const [typeFilter, setTypeFilter]       = useState<string>('all');
  const [projects, setProjects]     = useState<string[]>([]);
  const [types, setTypes]           = useState<string[]>([]);

  useEffect(() => {
    supabaseClient.auth.getSession().then(({ data: { session } }) => {
      if (!session) { router.push('/login'); return; }
      supabaseClient
        .from('pi_ceo_activity')
        .select('*')
        .order('created_at', { ascending: false })
        .limit(131)
        .then(({ data }) => {
          const rows = data || [];
          setAllRecords(rows);
          const uniqueProjects = Array.from(new Set(rows.map((r: ActivityRecord) => r.project_id).filter(Boolean))) as string[];
          const uniqueTypes    = Array.from(new Set(rows.map((r: ActivityRecord) => r.action_type).filter(Boolean))) as string[];
          setProjects(uniqueProjects);
          setTypes(uniqueTypes);
          setLoading(false);
        });
    });
  }, [router]);

  const records = allRecords.filter(r => {
    const matchProject = projectFilter === 'all' || r.project_id === projectFilter;
    const matchType    = typeFilter === 'all' || r.action_type === typeFilter;
    return matchProject && matchType;
  });

  const selectStyle: React.CSSProperties = {
    background: 'var(--surface-1)', border: '1px solid var(--border-default)',
    color: 'var(--ink-secondary)', fontSize: 12, padding: '6px 10px',
    borderRadius: 6, cursor: 'pointer', outline: 'none',
  };

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--canvas)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <RefreshMark size={18} color="var(--ink-tertiary)" />
        <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      </div>
    );
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--canvas)', color: 'var(--ink-primary)', padding: '32px 32px 64px' }}>

      {/* Back link */}
      <Link href="/en/empire" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--ink-tertiary)', textDecoration: 'none', marginBottom: 24 }}>
        ← Command Center
      </Link>

      {/* Header + filters */}
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 28, flexWrap: 'wrap', gap: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div style={{
            width: 36, height: 36, borderRadius: 8,
            background: 'color-mix(in srgb, var(--red-500) 10%, transparent)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}>
            <ActivityMark size={18} color="var(--red-500)" />
          </div>
          <div>
            <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--ink-primary)' }}>
              Pi-CEO Activity Log
            </h1>
            <p style={{ margin: 0, fontSize: 12, color: 'var(--ink-tertiary)', marginTop: 2 }}>
              <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--ink-secondary)' }}>{records.length}</span>
              {' '}of {allRecords.length} actions — autonomous agent feed
            </p>
          </div>
        </div>

        {/* Filter bar */}
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {projects.length > 0 && (
            <select value={projectFilter} onChange={e => setProjectFilter(e.target.value)} style={selectStyle}>
              <option value="all">All businesses</option>
              {projects.map(p => <option key={p} value={p}>{p}</option>)}
            </select>
          )}
          {types.length > 0 && (
            <select value={typeFilter} onChange={e => setTypeFilter(e.target.value)} style={selectStyle}>
              <option value="all">All types</option>
              {types.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          )}
        </div>
      </div>

      {records.length === 0 ? (
        <div style={{ textAlign: 'center', padding: '80px 0', color: 'var(--ink-tertiary)' }}>
          <ActivityMark size={36} color="var(--ink-tertiary)" />
          <p style={{ margin: '16px 0 0', fontSize: 14, color: 'var(--ink-secondary)' }}>No activity matching filters</p>
        </div>
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {records.map((rec) => {
            const color = bizColor(rec.project_id);
            const isLinear = rec.url?.includes('linear.app');
            return (
              <div
                key={rec.id}
                style={{
                  padding: '12px 16px',
                  background: 'var(--surface-1)',
                  border: '1px solid var(--border-default)',
                  borderRadius: 'var(--radius-md)',
                  borderLeft: `3px solid ${color}`,
                }}
              >
                {/* Top row: mark + type + project + time */}
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: rec.title ? 6 : 0 }}>
                  <ActionMark type={rec.action_type} />

                  {rec.action_type && (
                    <span style={{
                      fontSize: 10, fontWeight: 700, color: 'var(--ink-tertiary)',
                      textTransform: 'uppercase', letterSpacing: '0.08em',
                      fontFamily: 'var(--font-mono)',
                    }}>
                      {rec.action_type.replace(/_/g, ' ')}
                    </span>
                  )}

                  {rec.project_id && (
                    <span style={{
                      fontSize: 10, fontWeight: 600, padding: '1px 7px',
                      borderRadius: 3, letterSpacing: '0.04em',
                      color: '#fff',
                      background: color,
                    }}>
                      {rec.project_id}
                    </span>
                  )}

                  <span style={{
                    fontSize: 11, color: 'var(--ink-tertiary)', marginLeft: 'auto',
                    fontFamily: 'var(--font-mono)',
                  }}>
                    {timeAgo(rec.created_at)}
                  </span>
                </div>

                {/* Title */}
                {rec.title && (
                  <div style={{ fontSize: 13, fontWeight: 500, color: 'var(--ink-primary)', marginBottom: rec.detail ? 3 : 0, paddingLeft: 22 }}>
                    {rec.title}
                  </div>
                )}

                {/* Detail */}
                {rec.detail && (
                  <div style={{
                    fontSize: 12, color: 'var(--ink-secondary)', lineHeight: 1.5,
                    paddingLeft: 22,
                    overflow: 'hidden', textOverflow: 'ellipsis',
                    display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical' as const,
                  }}>
                    {rec.detail}
                  </div>
                )}

                {/* Linear link */}
                {isLinear && rec.url && (
                  <a
                    href={rec.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{
                      display: 'inline-flex', alignItems: 'center', gap: 4,
                      marginTop: 8, marginLeft: 22, fontSize: 11,
                      color: 'var(--ink-tertiary)', textDecoration: 'none',
                    }}
                  >
                    <ArrowUpRightMark size={10} color="var(--ink-tertiary)" />
                    Open in Linear
                  </a>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
