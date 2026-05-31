'use client';

import { useEffect, useState, use } from 'react';
import Link from 'next/link';
import {
  AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine,
} from 'recharts';
import { BusinessLogo } from '@/components/empire/BusinessLogo';
import {
  ArrowLeftMark, ExternalMark, UrgentMark, HighMark, MedMark,
  RefreshMark, HealthMark,
} from '@/components/ui/marks';

// ─── Types ────────────────────────────────────────────────────────────────────

type HealthSnapshot = {
  snapshot_at: string;
  overall_health: number | null;
  security_score: number | null;
  dependencies: number | null;
  security_findings: number | null;
};

type BusinessDetail = {
  id: string;
  name: string;
  status: string;
  arr_aud: number;
  overall_health: number | null;
  security_score: number | null;
  dependencies: number | null;
  security_findings: number | null;
  snapshot_at: string | null;
};

type Ticket = {
  id: string;
  title: string;
  state: string;
  stateType: string;
  priority: number;
  url: string;
};

// ─── Static metadata ──────────────────────────────────────────────────────────

const BUSINESS_NAMES: Record<string, string> = {
  'synthex': 'Synthex',
  'restoreassist': 'RestoreAssist',
  'dr-nrpg': 'NRPG',
  'carsi': 'CARSI',
  'ccw-crm': 'CCW-CRM',
  'disaster-recovery': 'DR Platform',
};

const LINEAR_PROJECT_URLS: Record<string, string> = {
  'synthex': 'https://linear.app/unite-group/team/SYN',
  'restoreassist': 'https://linear.app/unite-group/team/RA',
  'dr-nrpg': 'https://linear.app/unite-group/team/NRPG',
  'carsi': 'https://linear.app/unite-group/team/CARSI',
  'ccw-crm': 'https://linear.app/unite-group/team/CCW',
  'disaster-recovery': 'https://linear.app/unite-group/team/DR',
};

// ─── Helpers ──────────────────────────────────────────────────────────────────

function healthColor(score: number | null): string {
  if (score === null) return 'var(--ink-disabled)';
  if (score >= 80) return 'var(--green-400)';
  if (score >= 50) return 'var(--orange-400)';
  return 'var(--red-400)';
}

function healthGradientId(score: number | null): string {
  if (score === null) return 'grad-neutral';
  if (score >= 80) return 'grad-green';
  if (score >= 50) return 'grad-amber';
  return 'grad-red';
}

function statusLabel(status: string): string {
  if (status === 'operational') return 'OPERATIONAL';
  if (status === 'building') return 'BUILDING';
  if (status === 'degraded') return 'DEGRADED';
  if (status === 'down') return 'DOWN';
  return status.toUpperCase();
}

function statusStyle(status: string): React.CSSProperties {
  if (status === 'operational') {
    return { background: 'rgba(34,197,94,0.12)', color: 'var(--green-400)', border: '1px solid rgba(34,197,94,0.3)' };
  }
  if (status === 'building') {
    return { background: 'rgba(234,179,8,0.12)', color: 'var(--orange-400)', border: '1px solid rgba(234,179,8,0.3)' };
  }
  return { background: 'rgba(239,68,68,0.12)', color: 'var(--red-400)', border: '1px solid rgba(239,68,68,0.3)' };
}

function formatArr(arr: number): string {
  if (arr <= 0) return '';
  if (arr >= 1_000_000) return `$${(arr / 1_000_000).toFixed(1)}M ARR`;
  if (arr >= 1_000) return `$${Math.round(arr / 1_000)}k ARR`;
  return `$${arr} ARR`;
}

function relativeTime(iso: string | null): string {
  if (!iso) return '—';
  const diff = Date.now() - new Date(iso).getTime();
  const m = Math.floor(diff / 60_000);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  return `${Math.floor(h / 24)}d ago`;
}

function formatChartDate(iso: string): string {
  const d = new Date(iso);
  return `${d.getMonth() + 1}/${d.getDate()}`;
}

// ─── Priority mark ────────────────────────────────────────────────────────────

function PriorityMark({ priority }: { priority: number }) {
  if (priority === 1) return <UrgentMark size={12} color="var(--red-400)" />;
  if (priority === 2) return <HighMark size={12} color="var(--orange-400)" />;
  return <MedMark size={12} color="var(--ink-tertiary)" />;
}

// ─── Health ring ──────────────────────────────────────────────────────────────

function HealthRing({ score, size = 80 }: { score: number | null; size?: number }) {
  const r = (size - 10) / 2;
  const circ = 2 * Math.PI * r;
  const pct = score !== null ? score / 100 : 0;
  const dash = pct * circ;
  const color = healthColor(score);

  return (
    <div style={{ position: 'relative', width: size, height: size, flexShrink: 0 }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--border-default)" strokeWidth={6} />
        <circle
          cx={size / 2} cy={size / 2} r={r}
          fill="none"
          stroke={color}
          strokeWidth={6}
          strokeDasharray={`${dash} ${circ - dash}`}
          strokeLinecap="square"
        />
      </svg>
      <div style={{
        position: 'absolute', inset: 0,
        display: 'flex', flexDirection: 'column',
        alignItems: 'center', justifyContent: 'center',
      }}>
        <span style={{
          fontSize: size < 60 ? 13 : 18,
          fontWeight: 700,
          fontFamily: 'var(--font-mono)',
          color,
          lineHeight: 1,
        }}>
          {score !== null ? score : '—'}
        </span>
        <span style={{ fontSize: 9, color: 'var(--ink-tertiary)', fontFamily: 'var(--font-mono)', marginTop: 1 }}>
          /100
        </span>
      </div>
    </div>
  );
}

// ─── Skeleton ─────────────────────────────────────────────────────────────────

function Shimmer({ width, height, radius = 4 }: { width: string | number; height: number; radius?: number }) {
  return (
    <div className="skeleton" style={{ width, height, borderRadius: radius, flexShrink: 0 }} />
  );
}

// ─── Section header ───────────────────────────────────────────────────────────

function SectionHeader({ label, count }: { label: string; count?: number | string }) {
  return (
    <div style={{
      padding: '14px 18px 12px',
      borderBottom: '1px solid var(--border-hairline)',
      display: 'flex',
      alignItems: 'center',
      justifyContent: 'space-between',
    }}>
      <span style={{
        fontSize: 10,
        fontWeight: 700,
        fontFamily: 'var(--font-mono)',
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        color: 'var(--ink-tertiary)',
      }}>
        {label}
      </span>
      {count !== undefined && (
        <span style={{ fontSize: 10, color: 'var(--ink-tertiary)', fontFamily: 'var(--font-mono)' }}>
          {count}
        </span>
      )}
    </div>
  );
}

// ─── Health Timeline ──────────────────────────────────────────────────────────

function HealthTimeline({ snapshots }: { snapshots: HealthSnapshot[] }) {
  const chartData = snapshots
    .slice()
    .reverse()
    .map(s => ({
      date: formatChartDate(s.snapshot_at),
      health: s.overall_health ?? 0,
    }));

  const latestScore = snapshots[0]?.overall_health ?? null;
  const gradId = healthGradientId(latestScore);
  const strokeColor = healthColor(latestScore);

  return (
    <div style={{
      background: 'var(--surface-1)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--radius-md)',
      overflow: 'hidden',
    }}>
      <SectionHeader label="Health Timeline" count={`${snapshots.length} snapshots`} />
      <div style={{ padding: '16px 12px 8px' }}>
        {chartData.length === 0 ? (
          <div style={{ height: 140, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <span style={{ fontSize: 12, color: 'var(--ink-tertiary)' }}>No snapshot data</span>
          </div>
        ) : (
          <ResponsiveContainer width="100%" height={140}>
            <AreaChart data={chartData} margin={{ top: 4, right: 4, left: -24, bottom: 0 }}>
              <defs>
                <linearGradient id="grad-green" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--green-400)" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="var(--green-400)" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="grad-amber" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--orange-400)" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="var(--orange-400)" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="grad-red" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--red-400)" stopOpacity={0.25} />
                  <stop offset="95%" stopColor="var(--red-400)" stopOpacity={0.02} />
                </linearGradient>
                <linearGradient id="grad-neutral" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="var(--ink-disabled)" stopOpacity={0.2} />
                  <stop offset="95%" stopColor="var(--ink-disabled)" stopOpacity={0.02} />
                </linearGradient>
              </defs>
              <XAxis
                dataKey="date"
                tick={{ fontSize: 9, fontFamily: 'var(--font-mono)', fill: 'var(--ink-tertiary)' }}
                axisLine={{ stroke: 'var(--border-hairline)' }}
                tickLine={false}
                interval="preserveStartEnd"
              />
              <YAxis
                domain={[0, 100]}
                tick={{ fontSize: 9, fontFamily: 'var(--font-mono)', fill: 'var(--ink-tertiary)' }}
                axisLine={false}
                tickLine={false}
                ticks={[0, 50, 80, 100]}
              />
              <Tooltip
                contentStyle={{
                  background: 'var(--surface-1)',
                  border: '1px solid var(--border-default)',
                  borderRadius: 4,
                  fontSize: 11,
                  fontFamily: 'var(--font-mono)',
                  color: 'var(--ink-primary)',
                }}
                cursor={{ stroke: 'var(--border-strong)', strokeWidth: 1 }}
              />
              <ReferenceLine y={80} stroke="var(--green-400)" strokeOpacity={0.3} strokeDasharray="3 3" />
              <ReferenceLine y={50} stroke="var(--orange-400)" strokeOpacity={0.3} strokeDasharray="3 3" />
              <Area
                type="monotone"
                dataKey="health"
                stroke={strokeColor}
                strokeWidth={1.5}
                fill={`url(#${gradId})`}
                dot={false}
                activeDot={{ r: 3, strokeWidth: 0, fill: strokeColor }}
              />
            </AreaChart>
          </ResponsiveContainer>
        )}
      </div>
    </div>
  );
}

// ─── Ticket Kanban ────────────────────────────────────────────────────────────

function TicketCard({ ticket }: { ticket: Ticket }) {
  return (
    <div style={{
      background: 'var(--canvas)',
      border: '1px solid var(--border-hairline)',
      borderRadius: 'var(--radius-md)',
      padding: '10px 12px',
      display: 'flex',
      flexDirection: 'column',
      gap: 6,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <PriorityMark priority={ticket.priority} />
        <span style={{
          fontSize: 10,
          fontFamily: 'var(--font-mono)',
          color: 'var(--ink-tertiary)',
          flexShrink: 0,
        }}>
          {ticket.id}
        </span>
        <div style={{ flex: 1 }} />
        <a
          href={ticket.url}
          target="_blank"
          rel="noopener noreferrer"
          style={{ display: 'flex', alignItems: 'center', color: 'var(--ink-tertiary)', textDecoration: 'none' }}
          title="Open in Linear"
        >
          <ExternalMark size={10} />
        </a>
      </div>
      <span style={{
        fontSize: 12,
        color: 'var(--ink-primary)',
        lineHeight: 1.4,
        overflow: 'hidden',
        display: '-webkit-box',
        WebkitLineClamp: 2,
        WebkitBoxOrient: 'vertical' as const,
      }}>
        {ticket.title}
      </span>
    </div>
  );
}

function KanbanColumn({ label, tickets, loading }: { label: string; tickets: Ticket[]; loading: boolean }) {
  return (
    <div style={{
      flex: 1,
      minWidth: 0,
      display: 'flex',
      flexDirection: 'column',
      gap: 8,
    }}>
      <div style={{
        fontSize: 10,
        fontWeight: 700,
        fontFamily: 'var(--font-mono)',
        letterSpacing: '0.1em',
        textTransform: 'uppercase',
        color: 'var(--ink-tertiary)',
        padding: '0 2px 4px',
        borderBottom: '1px solid var(--border-hairline)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
      }}>
        <span>{label}</span>
        <span>{loading ? '…' : tickets.length}</span>
      </div>
      {loading ? (
        <>
          <Shimmer width="100%" height={64} />
          <Shimmer width="100%" height={52} />
        </>
      ) : tickets.length === 0 ? (
        <div style={{ fontSize: 11, color: 'var(--ink-disabled)', padding: '8px 2px' }}>
          None
        </div>
      ) : (
        tickets.map(t => <TicketCard key={t.id} ticket={t} />)
      )}
    </div>
  );
}

function ActiveTickets({ slug }: { slug: string }) {
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch(`/api/empire/tickets/${slug}`)
      .then(r => r.json())
      .then(json => setTickets(json.tickets ?? []))
      .catch(() => setTickets([]))
      .finally(() => setLoading(false));
  }, [slug]);

  const todo = tickets.filter(t => t.stateType === 'unstarted');
  const inProgress = tickets.filter(t => t.stateType === 'started');
  const done: Ticket[] = []; // API only returns active; done col shown as empty placeholder

  return (
    <div style={{
      background: 'var(--surface-1)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--radius-md)',
      overflow: 'hidden',
    }}>
      <SectionHeader label="Active Tickets" count={loading ? '…' : `${tickets.length} open`} />
      <div style={{ padding: '16px 16px', display: 'flex', gap: 12 }}>
        <KanbanColumn label="Todo" tickets={todo} loading={loading} />
        <KanbanColumn label="In Progress" tickets={inProgress} loading={loading} />
        <KanbanColumn label="Done (7d)" tickets={done} loading={false} />
      </div>
    </div>
  );
}

// ─── Key Metrics Strip ────────────────────────────────────────────────────────

function MetricsStrip({ biz, onRescan }: { biz: BusinessDetail | null; onRescan?: () => void }) {
  // Truthful UX: distinguish "scanner ran and found zero" from "scanner never ran".
  // A snapshot older than 30 days — or missing entirely — is treated as stale; we
  // render "Not yet scanned" rather than a meaningless 0/100 score.
  const SCAN_FRESHNESS_DAYS = 30;
  const scannedAt = biz?.snapshot_at ?? null;
  const isStale = (() => {
    if (!scannedAt) return true;
    const ageMs = Date.now() - new Date(scannedAt).getTime();
    return ageMs > SCAN_FRESHNESS_DAYS * 24 * 60 * 60 * 1000;
  })();

  const STALE_LABEL = 'Not yet scanned';

  const securityValue = isStale
    ? STALE_LABEL
    : biz?.security_score !== null && biz?.security_score !== undefined
      ? `${biz.security_score}/100`
      : '—';
  const findingsValue = isStale
    ? STALE_LABEL
    : biz?.security_findings !== null && biz?.security_findings !== undefined
      ? String(biz.security_findings)
      : '—';
  const depsValue = isStale
    ? STALE_LABEL
    : biz?.dependencies !== null && biz?.dependencies !== undefined
      ? `${biz.dependencies}/100`
      : '—';

  const metrics = [
    {
      label: 'Security Score',
      value: securityValue,
      color: isStale ? 'var(--ink-tertiary)' : healthColor(biz?.security_score ?? null),
    },
    {
      label: 'Findings',
      value: findingsValue,
      color: isStale
        ? 'var(--ink-tertiary)'
        : (biz?.security_findings ?? 0) > 0 ? 'var(--orange-400)' : 'var(--green-400)',
    },
    {
      label: 'Dep Score',
      value: depsValue,
      color: isStale ? 'var(--ink-tertiary)' : healthColor(biz?.dependencies ?? null),
    },
    {
      label: 'Last Scanned',
      value: scannedAt ? relativeTime(scannedAt) : 'never',
      color: 'var(--ink-secondary)',
    },
  ];

  return (
    <div style={{
      display: 'flex',
      gap: 1,
      background: 'var(--border-hairline)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--radius-md)',
      overflow: 'hidden',
    }}>
      {metrics.map(m => (
        <div key={m.label} style={{
          flex: 1,
          background: 'var(--surface-1)',
          padding: '12px 16px',
          display: 'flex',
          flexDirection: 'column',
          gap: 4,
        }}>
          <div style={{
            fontSize: 10,
            color: 'var(--ink-tertiary)',
            fontFamily: 'var(--font-mono)',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
          }}>
            {m.label}
          </div>
          {biz === null ? (
            <Shimmer width="60%" height={16} />
          ) : (
            <div style={{
              fontSize: isStale ? 12 : 16,
              fontWeight: 700,
              fontFamily: 'var(--font-mono)',
              color: m.color,
            }}>
              {m.value}
            </div>
          )}
          {/* Inline rescan CTA on the Last Scanned cell only, when stale */}
          {isStale && biz !== null && onRescan && m.label === 'Last Scanned' && (
            <button
              type="button"
              onClick={onRescan}
              style={{
                marginTop: 2,
                alignSelf: 'flex-start',
                padding: '2px 8px',
                fontSize: 10,
                fontWeight: 600,
                fontFamily: 'var(--font-mono)',
                letterSpacing: '0.06em',
                textTransform: 'uppercase',
                background: 'transparent',
                color: 'var(--orange-400)',
                border: '1px solid rgba(234,179,8,0.3)',
                borderRadius: 'var(--radius-sm)',
                cursor: 'pointer',
              }}
            >
              Re-run scan
            </button>
          )}
        </div>
      ))}
    </div>
  );
}

// ─── Quick Actions ────────────────────────────────────────────────────────────

function ActionButton({
  label, href, onClick, icon,
}: {
  label: string;
  href?: string;
  onClick?: () => void;
  icon?: React.ReactNode;
}) {
  const style: React.CSSProperties = {
    flex: 1,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    padding: '11px 16px',
    fontSize: 12,
    fontWeight: 600,
    fontFamily: 'var(--font-mono)',
    letterSpacing: '0.04em',
    color: 'var(--ink-primary)',
    background: 'var(--surface-1)',
    border: '1px solid var(--border-default)',
    borderRadius: 'var(--radius-md)',
    cursor: 'pointer',
    textDecoration: 'none',
    transition: 'border-color 0.15s',
  };

  if (href) {
    return (
      <a
        href={href}
        target={href.startsWith('http') ? '_blank' : undefined}
        rel={href.startsWith('http') ? 'noopener noreferrer' : undefined}
        style={style}
        onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--border-strong)')}
        onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--border-default)')}
      >
        {icon}
        {label}
      </a>
    );
  }

  return (
    <button
      onClick={onClick}
      style={{ ...style, fontFamily: 'var(--font-mono)' }}
      onMouseEnter={e => (e.currentTarget.style.borderColor = 'var(--border-strong)')}
      onMouseLeave={e => (e.currentTarget.style.borderColor = 'var(--border-default)')}
    >
      {icon}
      {label}
    </button>
  );
}

function QuickActions({ slug, onScanQueued }: { slug: string; onScanQueued?: () => void }) {
  // Real scan trigger — POSTs to /api/empire/rescan/[slug] which inserts a row
  // into scan_requests for the Pi-CEO worker to consume. Polls the same
  // endpoint with GET to surface honest status updates to the operator.
  const [status, setStatus] = useState<'idle' | 'queued' | 'running' | 'completed' | 'failed'>('idle');
  const [requestId, setRequestId] = useState<string | null>(null);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  async function triggerScan() {
    setStatus('queued');
    setErrorMsg(null);
    try {
      const res = await fetch(`/api/empire/rescan/${slug}`, { method: 'POST' });
      if (!res.ok) {
        const body = await res.json().catch(() => ({}));
        setStatus('failed');
        setErrorMsg(body.error ?? `HTTP ${res.status}`);
        return;
      }
      const json: { request_id: string; status: string } = await res.json();
      setRequestId(json.request_id);
      setStatus('queued');
      onScanQueued?.();
    } catch (err) {
      setStatus('failed');
      setErrorMsg(err instanceof Error ? err.message : 'Network error');
    }
  }

  // Poll for status updates every 10s while a scan is in flight.
  useEffect(() => {
    if (!requestId || status === 'completed' || status === 'failed') return;
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`/api/empire/rescan/${slug}`);
        if (!res.ok) return;
        const json: {
          latest: { id: string; status: string; error: string | null } | null;
        } = await res.json();
        if (json.latest?.id === requestId) {
          const s = json.latest.status;
          if (s === 'running' || s === 'completed' || s === 'failed') {
            setStatus(s);
            if (s === 'failed') setErrorMsg(json.latest.error ?? 'Worker reported failure');
            if (s === 'completed') clearInterval(interval);
          }
        }
      } catch {
        // ignore transient poll failures — next tick will retry
      }
    }, 10_000);
    return () => clearInterval(interval);
  }, [requestId, status, slug]);

  const scanLabel = (() => {
    if (status === 'queued')    return 'Queued for scan';
    if (status === 'running')   return 'Scanning…';
    if (status === 'completed') return 'Scan completed';
    if (status === 'failed')    return errorMsg ? `Failed: ${errorMsg}` : 'Scan failed';
    return 'Trigger Pi-CEO Scan';
  })();

  return (
    <div style={{
      background: 'var(--surface-1)',
      border: '1px solid var(--border-default)',
      borderRadius: 'var(--radius-md)',
      overflow: 'hidden',
    }}>
      <SectionHeader label="Quick Actions" />
      <div style={{ padding: '14px 16px', display: 'flex', gap: 10 }}>
        <ActionButton
          label="Run SEO Audit"
          href={`/businesses/${slug}/seo`}
          icon={<HealthMark size={14} />}
        />
        <ActionButton
          label="View in Linear"
          href={LINEAR_PROJECT_URLS[slug] ?? 'https://linear.app'}
          icon={<ExternalMark size={12} />}
        />
        <ActionButton
          label={scanLabel}
          onClick={triggerScan}
          icon={<RefreshMark size={14} />}
        />
      </div>
    </div>
  );
}

// ─── Page ─────────────────────────────────────────────────────────────────────

export default function BusinessDetailPage({
  params,
}: {
  params: Promise<{ slug: string; locale: string }>;
}) {
  const { slug, locale } = use(params);

  const [biz, setBiz] = useState<BusinessDetail | null>(null);
  const [snapshots, setSnapshots] = useState<HealthSnapshot[]>([]);
  const [loading, setLoading] = useState(true);
  const [wikiContext, setWikiContext] = useState<{
    mission: string; positioning: string; techStack: string;
    keyRisks: string; lastUpdated: string; fullContent: string;
  } | null>(null);

  useEffect(() => {
    async function load() {
      try {
        const res = await fetch('/api/empire/businesses', { cache: 'no-store' });
        const json = await res.json();
        const businesses: BusinessDetail[] = json.businesses ?? [];
        const found = businesses.find(b => b.id === slug) ?? null;
        setBiz(found);

        // Build fake timeline from the single snapshot for now
        // In future this would be GET /api/empire/snapshots/[slug]
        if (found?.snapshot_at) {
          setSnapshots([{
            snapshot_at: found.snapshot_at,
            overall_health: found.overall_health,
            security_score: found.security_score,
            dependencies: found.dependencies,
            security_findings: found.security_findings,
          }]);
        }
      } catch {
        setBiz(null);
      } finally {
        setLoading(false);
      }
    }
    load();

    // Wiki context: fetch from 2nd Brain
    fetch(`/api/wiki/context/${slug}`)
      .then(r => r.json())
      .then(data => !data.error && setWikiContext(data))
      .catch(() => {});
  }, [slug]);

  const name = biz?.name ?? BUSINESS_NAMES[slug] ?? slug;
  const score = biz?.overall_health ?? null;
  const status = biz?.status ?? 'building';
  const arrLabel = formatArr(biz?.arr_aud ?? 0);

  return (
    <div style={{
      minHeight: '100vh',
      background: 'var(--canvas)',
      color: 'var(--ink-primary)',
      fontFamily: 'system-ui, sans-serif',
    }}>
      {/* ─── Header ──────────────────────────────────────────────────────────── */}
      <header style={{
        borderBottom: '1px solid var(--border-hairline)',
        padding: '14px 32px',
        background: 'var(--surface-1)',
        display: 'flex',
        alignItems: 'center',
        gap: 20,
      }}>
        {/* Back link */}
        <Link
          href={`/${locale}/empire`}
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            fontSize: 12,
            fontWeight: 600,
            fontFamily: 'var(--font-mono)',
            color: 'var(--ink-tertiary)',
            textDecoration: 'none',
            letterSpacing: '0.04em',
            flexShrink: 0,
          }}
        >
          <ArrowLeftMark size={14} />
          Command Center
        </Link>

        <div style={{ width: 1, height: 24, background: 'var(--border-hairline)', flexShrink: 0 }} />

        {/* Logo + name */}
        <BusinessLogo slug={slug} size="md" />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div style={{ fontSize: 17, fontWeight: 600, letterSpacing: '-0.3px' }}>
            {name}
          </div>
          {loading ? (
            <Shimmer width={120} height={11} />
          ) : (
            <div style={{ fontSize: 11, color: 'var(--ink-tertiary)', marginTop: 2 }}>
              {slug}
            </div>
          )}
        </div>

        {/* Health ring */}
        <HealthRing score={score} size={80} />

        {/* ARR badge */}
        {arrLabel && (
          <div style={{
            padding: '5px 12px',
            background: 'rgba(34,197,94,0.1)',
            border: '1px solid rgba(34,197,94,0.25)',
            borderRadius: 'var(--radius-md)',
            fontSize: 12,
            fontWeight: 700,
            fontFamily: 'var(--font-mono)',
            color: 'var(--green-400)',
            flexShrink: 0,
          }}>
            {arrLabel}
          </div>
        )}

        {/* Status badge */}
        <div style={{
          ...statusStyle(status),
          padding: '5px 12px',
          borderRadius: 'var(--radius-md)',
          fontSize: 10,
          fontWeight: 700,
          fontFamily: 'var(--font-mono)',
          letterSpacing: '0.08em',
          flexShrink: 0,
        }}>
          {statusLabel(status)}
        </div>
      </header>

      {/* ─── Main ────────────────────────────────────────────────────────────── */}
      <main style={{ padding: '24px 32px', maxWidth: 1280, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 16 }}>

        {/* Key Metrics Strip */}
        <MetricsStrip
          biz={loading ? null : biz}
          onRescan={async () => {
            // Fire-and-forget queue insert; QuickActions below is the
            // primary surface for follow-up status. We use the same endpoint
            // so the operator gets one queued request, not two.
            try {
              await fetch(`/api/empire/rescan/${slug}`, { method: 'POST' });
            } catch {
              // surfaced via the Quick Actions button on retry
            }
          }}
        />

        {/* Wiki Context Panel — FROM THE 2ND BRAIN */}
        {wikiContext && (
          <section style={{ marginTop: 24 }}>
            <div style={{ fontSize: 'var(--text-2xs)', fontWeight: 600,
              letterSpacing: 'var(--tracking-caps)', textTransform: 'uppercase',
              color: 'var(--ink-tertiary)', marginBottom: 12 }}>
              FROM THE 2ND BRAIN
            </div>
            <div style={{ background: 'var(--surface-1)', border: '1px solid var(--border-default)',
              borderLeft: '3px solid var(--red-500)', borderRadius: 'var(--radius-md)', padding: 16 }}>
              {wikiContext.mission && (
                <p style={{ fontSize: 13, color: 'var(--ink-secondary)', margin: '0 0 12px', lineHeight: 1.5 }}>
                  {wikiContext.mission}
                </p>
              )}
              {wikiContext.techStack && (
                <div style={{ marginTop: 8 }}>
                  <span style={{ fontSize: 11, color: 'var(--ink-tertiary)', fontFamily: 'var(--font-mono)' }}>
                    STACK
                  </span>
                  <p style={{ fontSize: 12, color: 'var(--ink-secondary)', margin: '4px 0 0', fontFamily: 'var(--font-mono)' }}>
                    {wikiContext.techStack.slice(0, 200)}
                  </p>
                </div>
              )}
              {wikiContext.keyRisks && (
                <div style={{ marginTop: 8 }}>
                  <span style={{ fontSize: 11, color: 'var(--orange-400)', fontFamily: 'var(--font-mono)' }}>
                    KEY RISKS
                  </span>
                  <p style={{ fontSize: 12, color: 'var(--ink-secondary)', margin: '4px 0 0' }}>
                    {wikiContext.keyRisks.slice(0, 200)}
                  </p>
                </div>
              )}
              <div style={{ marginTop: 12, fontSize: 11, color: 'var(--ink-tertiary)', fontFamily: 'var(--font-mono)' }}>
                Wiki updated {wikiContext.lastUpdated ? new Date(wikiContext.lastUpdated).toLocaleDateString('en-AU') : 'unknown'}
              </div>
            </div>
          </section>
        )}

        {/* Health Timeline */}
        {loading ? (
          <div style={{
            background: 'var(--surface-1)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-md)',
            overflow: 'hidden',
          }}>
            <SectionHeader label="Health Timeline" />
            <div style={{ padding: 16 }}>
              <Shimmer width="100%" height={140} />
            </div>
          </div>
        ) : (
          <HealthTimeline snapshots={snapshots} />
        )}

        {/* Active Tickets */}
        <ActiveTickets slug={slug} />

        {/* Quick Actions */}
        <QuickActions slug={slug} />
      </main>
    </div>
  );
}
