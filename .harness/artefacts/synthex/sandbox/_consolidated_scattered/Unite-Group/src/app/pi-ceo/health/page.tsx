'use client';

import { useState, useEffect } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import { supabaseClient } from '@/lib/supabase/client';
import { RefreshMark, BarChartMark, HealthMark } from '@/components/ui/marks';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts';
import { PortfolioTile, type PortfolioStatus } from '@/components/empire/PortfolioTile';

interface HealthSnapshot {
  id: string;
  project_id: string;
  overall_health: number;
  security_score?: number;
  snapshot_at?: string;
  created_at?: string;
}

const BUSINESSES = [
  { id: 'synthex',       label: 'Synthex',       color: '#6366f1' },
  { id: 'restoreassist', label: 'RestoreAssist',  color: '#0E7C7B' },
  { id: 'disaster-recovery', label: 'DR Platform', color: '#0B2545' },
  { id: 'dr-nrpg',      label: 'NRPG',           color: '#1A2A4F' },
  { id: 'carsi',        label: 'CARSI',           color: '#B85C38' },
  { id: 'ccw-crm',      label: 'CCW',             color: '#D62828' },
];

function scoreColor(score: number): string {
  if (score >= 80) return 'var(--green-400)';
  if (score >= 50) return 'var(--orange-400)';
  return 'var(--red-500)';
}

function scoreBg(score: number): string {
  if (score >= 80) return 'color-mix(in srgb, var(--green-400) 15%, transparent)';
  if (score >= 50) return 'color-mix(in srgb, var(--orange-400) 15%, transparent)';
  return 'color-mix(in srgb, var(--red-500) 15%, transparent)';
}

function scoreStatus(score: number): PortfolioStatus {
  if (score <= 0) return 'degraded';
  if (score >= 80) return 'operational';
  if (score >= 50) return 'degraded';
  return 'down';
}

function getTimestamp(snap: HealthSnapshot): string {
  return snap.snapshot_at || snap.created_at || '';
}

export default function HealthPage() {
  const router = useRouter();
  const [loading, setLoading]   = useState(true);
  const [snapshots, setSnapshots] = useState<HealthSnapshot[]>([]);
  const [selected, setSelected] = useState<string>(BUSINESSES[0].id);

  useEffect(() => {
    supabaseClient.auth.getSession().then(({ data: { session } }) => {
      if (!session) { router.push('/login'); return; }

      fetch('/api/intelligence/health-snapshots')
        .then(r => r.json())
        .then(({ snapshots: data }) => {
          setSnapshots((data as HealthSnapshot[]) || []);
          setLoading(false);
        })
        .catch(() => setLoading(false));
    });
  }, [router]);

  // Build chart data for selected business
  const bizSnaps = snapshots
    .filter(s => s.project_id === selected)
    .map(s => ({
      date: getTimestamp(s)
        ? new Date(getTimestamp(s)).toLocaleDateString('en-AU', { day: 'numeric', month: 'short' })
        : '',
      health: Math.round(s.overall_health ?? 0),
      security: Math.round(s.security_score ?? 0),
    }));

  // Dedupe by date label (keep last of each day)
  const seen = new Map<string, typeof bizSnaps[0]>();
  bizSnaps.forEach(s => seen.set(s.date, s));
  const chartData = Array.from(seen.values());

  const currentSnap = bizSnaps[bizSnaps.length - 1];
  const currentHealth = currentSnap?.health ?? 0;
  const currentSecurity = currentSnap?.security ?? 0;
  const selectedBiz = BUSINESSES.find(b => b.id === selected)!;

  // Summary cards for all businesses
  const bizSummaries = BUSINESSES.map(biz => {
    const bizRows = snapshots.filter(s => s.project_id === biz.id);
    const latest = bizRows[bizRows.length - 1];
    return {
      ...biz,
      score: latest ? Math.round(latest.overall_health ?? 0) : 0,
      count: bizRows.length,
    };
  });

  if (loading) {
    return (
      <div style={{ minHeight: '100vh', background: 'var(--canvas)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <RefreshMark size={18} color="var(--ink-tertiary)" />
      </div>
    );
  }

  return (
    <div style={{ minHeight: '100vh', background: 'var(--canvas)', color: 'var(--ink-primary)', padding: '32px 32px 64px' }}>

      {/* Back link */}
      <Link href="/en/empire" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: 12, color: 'var(--ink-tertiary)', textDecoration: 'none', marginBottom: 24 }}>
        ← Command Center
      </Link>

      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 28 }}>
        <div style={{
          width: 36, height: 36, borderRadius: 8,
          background: 'color-mix(in srgb, var(--green-400) 12%, transparent)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
        }}>
          <BarChartMark size={18} color="var(--green-400)" />
        </div>
        <div>
          <h1 style={{ margin: 0, fontSize: 20, fontWeight: 700, letterSpacing: '-0.02em', color: 'var(--ink-primary)' }}>
            Health History
          </h1>
          <p style={{ margin: 0, fontSize: 12, color: 'var(--ink-tertiary)', marginTop: 2 }}>
            <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--ink-secondary)' }}>
              {snapshots.length.toLocaleString()}
            </span>{' '}health snapshots — portfolio system vitals
          </p>
        </div>
      </div>

      {/* Business selector tabs */}
      <div style={{ display: 'flex', gap: 6, marginBottom: 24, flexWrap: 'wrap' }}>
        {bizSummaries.map(biz => {
          const isSelected = biz.id === selected;
          return (
            <button
              key={biz.id}
              onClick={() => setSelected(biz.id)}
              style={{
                display: 'flex', alignItems: 'center', gap: 8,
                padding: '7px 14px', border: 'none', cursor: 'pointer', borderRadius: 6,
                background: isSelected ? biz.color : 'var(--surface-1)',
                outline: isSelected ? 'none' : '1px solid var(--border-default)',
                transition: 'all 0.1s',
              }}
            >
              <span style={{
                fontSize: 12, fontWeight: 600,
                color: isSelected ? '#fff' : 'var(--ink-secondary)',
              }}>
                {biz.label}
              </span>
              {biz.score > 0 && (
                <span style={{
                  fontSize: 11, fontFamily: 'var(--font-mono)', fontWeight: 700,
                  color: isSelected ? 'rgba(255,255,255,0.8)' : scoreColor(biz.score),
                }}>
                  {biz.score}
                </span>
              )}
              {biz.count > 0 && (
                <span style={{
                  fontSize: 10, fontFamily: 'var(--font-mono)',
                  color: isSelected ? 'rgba(255,255,255,0.5)' : 'var(--ink-tertiary)',
                }}>
                  /{biz.count}
                </span>
              )}
            </button>
          );
        })}
      </div>

      {/* Main chart panel */}
      <div style={{
        background: 'var(--surface-1)', border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-md)', padding: '24px', marginBottom: 24,
      }}>
        {/* Panel header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 20 }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
            <HealthMark size={16} color={selectedBiz.color} />
            <span style={{ fontSize: 14, fontWeight: 600, color: 'var(--ink-primary)' }}>
              {selectedBiz.label} — Health Over Time
            </span>
          </div>
          <div style={{ display: 'flex', gap: 16 }}>
            <div style={{ textAlign: 'right' }}>
              <div style={{
                fontSize: 26, fontWeight: 800, fontFamily: 'var(--font-mono)', lineHeight: 1,
                color: currentHealth > 0 ? scoreColor(currentHealth) : 'var(--ink-tertiary)',
              }}>
                {currentHealth > 0 ? currentHealth : '—'}
              </div>
              <div style={{ fontSize: 9, color: 'var(--ink-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', marginTop: 2 }}>
                health
              </div>
            </div>
            {currentSecurity > 0 && (
              <div style={{ textAlign: 'right' }}>
                <div style={{
                  fontSize: 26, fontWeight: 800, fontFamily: 'var(--font-mono)', lineHeight: 1,
                  color: scoreColor(currentSecurity),
                }}>
                  {currentSecurity}
                </div>
                <div style={{ fontSize: 9, color: 'var(--ink-tertiary)', textTransform: 'uppercase', letterSpacing: '0.08em', marginTop: 2 }}>
                  security
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Chart */}
        {chartData.length < 2 ? (
          <div style={{ height: 200, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--ink-tertiary)', fontSize: 13 }}>
            {chartData.length === 0 ? 'No data for this business' : 'Need more snapshots to chart'}
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={200}>
            <AreaChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}>
              <defs>
                <linearGradient id="gradHealth" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor={selectedBiz.color} stopOpacity={0.35} />
                  <stop offset="95%" stopColor={selectedBiz.color} stopOpacity={0} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="date"
                tick={{ fill: 'var(--ink-tertiary)', fontSize: 10 }}
                axisLine={false} tickLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                domain={[0, 100]}
                tick={{ fill: 'var(--ink-tertiary)', fontSize: 10 }}
                axisLine={false} tickLine={false}
              />
              <Tooltip
                contentStyle={{
                  background: 'var(--surface-2)', border: '1px solid var(--border-default)',
                  borderRadius: 6, fontSize: 12, color: 'var(--ink-primary)',
                }}
                itemStyle={{ color: selectedBiz.color }}
                formatter={(val: number) => [`${val}`, 'Health']}
              />
              <Area
                type="monotone"
                dataKey="health"
                stroke={selectedBiz.color}
                strokeWidth={2}
                fill="url(#gradHealth)"
                dot={false}
                activeDot={{ r: 4, fill: selectedBiz.color }}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>

      {/* Metrics strip */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 12 }}>
        <PortfolioTile
          title="Current Health"
          status={scoreStatus(currentHealth)}
          brandSlug="pi-ceo"
        >
          <div style={{
            fontSize: 32, fontWeight: 800, fontFamily: 'var(--font-mono)',
            color: currentHealth > 0 ? scoreColor(currentHealth) : 'var(--ink-tertiary)',
            lineHeight: 1,
          }}>
            {currentHealth > 0 ? currentHealth : '—'}
          </div>
          {currentHealth > 0 && (
            <div style={{
              display: 'inline-block', marginTop: 8, fontSize: 10, padding: '2px 8px',
              borderRadius: 4, fontWeight: 600,
              color: scoreColor(currentHealth),
              background: scoreBg(currentHealth),
            }}>
              {currentHealth >= 80 ? 'Healthy' : currentHealth >= 50 ? 'Degraded' : 'Critical'}
            </div>
          )}
        </PortfolioTile>

        <PortfolioTile
          title="Security Score"
          status={scoreStatus(currentSecurity)}
          brandSlug="pi-ceo"
        >
          <div style={{
            fontSize: 32, fontWeight: 800, fontFamily: 'var(--font-mono)',
            color: currentSecurity > 0 ? scoreColor(currentSecurity) : 'var(--ink-tertiary)',
            lineHeight: 1,
          }}>
            {currentSecurity > 0 ? currentSecurity : '—'}
          </div>
        </PortfolioTile>

        <PortfolioTile
          title="Snapshots"
          description={`for ${selectedBiz.label}`}
          status={bizSnaps.length > 0 ? 'operational' : 'degraded'}
          brandSlug="pi-ceo"
        >
          <div style={{ fontSize: 32, fontWeight: 800, fontFamily: 'var(--font-mono)', color: 'var(--ink-primary)', lineHeight: 1 }}>
            {bizSnaps.length}
          </div>
        </PortfolioTile>
      </div>
    </div>
  );
}
