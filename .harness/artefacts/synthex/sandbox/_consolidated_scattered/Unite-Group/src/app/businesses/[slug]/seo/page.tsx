"use client";
import Link from 'next/link';

import { useState, useEffect } from "react";
import { useRouter, useParams } from "next/navigation";
import { motion } from "framer-motion";
import { CheckCircleMark, CloseMark, RefreshMark, ExternalMark } from "@/components/ui/marks";
import { supabaseClient } from "@/lib/supabase/client";

const SLUG_TO_DOMAIN: Record<string, { name: string; domain: string; color: string }> = {
  synthex:       { name: 'Synthex',       domain: 'synthex.social',                    color: '#6366f1' },
  restoreassist: { name: 'RestoreAssist', domain: 'restoreassist.app',                  color: '#0E7C7B' },
  'ccw-crm':     { name: 'CCW-CRM',       domain: 'carpetcleanerswarehouse.com.au',     color: '#dc2626' },
  'dr-platform': { name: 'DR Platform',   domain: 'disasterrecovery.com.au',            color: '#2563eb' },
  nrpg:          { name: 'NRPG',          domain: 'nrpg.com.au',                        color: '#16a34a' },
  carsi:         { name: 'CARSI',         domain: 'carsi.com.au',                       color: '#d97706' },
};

interface SEOCheck { pass: boolean; value: string; note: string; }
interface SEOResult {
  domain: string; fetchedAt: string; score: number; error?: string;
  checks: Record<string, SEOCheck>;
}

const CHECK_LABELS: Record<string, string> = {
  title: 'Page Title', description: 'Meta Description', ogTitle: 'OG Title',
  ogImage: 'OG Image', canonical: 'Canonical URL', h1: 'H1 Heading',
  robots: 'Robots Meta', sitemap: 'Sitemap',
};

function ScoreRing({ score, color }: { score: number; color: string }) {
  const r = 44;
  const circ = 2 * Math.PI * r;
  const offset = circ - (score / 100) * circ;
  const ringColor = score >= 75 ? '#16a34a' : score >= 50 ? '#d97706' : '#dc2626';
  // color prop reserved for future per-brand ring theming
  void color;
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 8 }}>
      <svg width={104} height={104} viewBox="0 0 104 104">
        <circle cx={52} cy={52} r={r} fill="none" stroke="var(--border-default)" strokeWidth={8} />
        <motion.circle
          cx={52} cy={52} r={r} fill="none" stroke={ringColor} strokeWidth={8}
          strokeLinecap="round" transform="rotate(-90 52 52)"
          strokeDasharray={circ}
          initial={{ strokeDashoffset: circ }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 1.2, ease: [0.23, 1, 0.32, 1] }}
        />
        <text x={52} y={48} textAnchor="middle" dominantBaseline="middle"
          fill="var(--ink-primary)" fontSize={22} fontWeight={700} fontFamily="var(--font-mono)">{score}</text>
        <text x={52} y={66} textAnchor="middle" fill="#52525b" fontSize={11}>/ 100</text>
      </svg>
      <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.08em', textTransform: 'uppercase', color: '#52525b' }}>SEO Score</span>
    </div>
  );
}

export default function SEOAuditPage() {
  const router = useRouter();
  const params = useParams();
  const slug = params.slug as string;
  const meta = SLUG_TO_DOMAIN[slug];

  const [result, setResult] = useState<SEOResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [mounted, setMounted] = useState(false);

  useEffect(() => { setMounted(true); }, []);

  useEffect(() => {
    supabaseClient.auth.getSession().then(({ data: { session } }) => {
      if (!session) router.push('/en/login');
    });
  }, [router]);

  const runAudit = async () => {
    if (!meta) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/seo/audit?domain=${meta.domain}`);
      if (res.ok) setResult(await res.json());
    } catch { /* retain */ }
    finally { setLoading(false); }
  };

  useEffect(() => { if (mounted && meta) runAudit(); }, [mounted, slug]);

  if (!mounted) return null;

  if (!meta) return (
    <div style={{ minHeight: '100vh', background: 'var(--canvas)', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      <div style={{ textAlign: 'center' }}>
        <p style={{ color: '#52525b', fontFamily: 'var(--font-mono)', fontSize: 13 }}>Unknown business: {slug}</p>
        <Link href="/ceo" style={{ color: '#b30000', fontSize: 12, marginTop: 12, display: 'block' }}>← Back to Command Center</Link>
      </div>
    </div>
  );

  const checkEntries = result ? Object.entries(result.checks) : [];
  const passed = checkEntries.filter(([, c]) => c.pass).length;

  return (
    <div style={{ minHeight: '100vh', background: 'var(--canvas)', color: 'var(--ink-primary)' }}>
      {/* Page title */}
      <div style={{ padding: "24px 24px 0", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <div>
          <h1 style={{ fontSize: 18, fontWeight: 700, color: "var(--ink-primary)", letterSpacing: "-0.02em", margin: 0, fontFamily: "var(--font-display)", display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 8, height: 8, borderRadius: '50%', background: meta.color, display: 'inline-block' }} />
            {meta.name} — SEO Audit
          </h1>
          <p style={{ fontSize: 11, color: "#52525b", margin: "3px 0 0", fontFamily: "var(--font-mono)" }}>
            <a href={`https://${meta.domain}`} target="_blank" rel="noopener noreferrer"
              style={{ color: '#52525b', textDecoration: 'none' }}
              onMouseEnter={e => (e.currentTarget.style.color = 'var(--ink-secondary)')}
              onMouseLeave={e => (e.currentTarget.style.color = '#52525b')}
            >
              {meta.domain} <ExternalMark size={9} />
            </a>
          </p>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
          <a
            href={`/api/seo/audit/pdf?domain=${meta.domain}`}
            download
            style={{
              display: 'flex', alignItems: 'center', gap: 6, padding: '5px 12px',
              fontSize: 11, fontWeight: 500, borderRadius: 7,
              border: '1px solid rgba(29,78,216,0.4)', color: '#60a5fa',
              textDecoration: 'none', background: 'rgba(29,78,216,0.08)',
              transition: 'all 0.1s ease',
            }}
            onMouseEnter={e => { (e.currentTarget as HTMLAnchorElement).style.background = 'rgba(29,78,216,0.15)'; }}
            onMouseLeave={e => { (e.currentTarget as HTMLAnchorElement).style.background = 'rgba(29,78,216,0.08)'; }}
          >
            <span style={{ fontSize: 13 }}>↓</span> Download PDF Report
          </a>
          <button
            onClick={runAudit} disabled={loading}
            style={{ display: 'flex', alignItems: 'center', gap: 5, padding: '5px 12px', fontSize: 11, borderRadius: 7, border: '1px solid #27272a', color: loading ? '#52525b' : 'var(--ink-secondary)', background: 'transparent', cursor: loading ? 'not-allowed' : 'pointer', transition: 'all 0.1s' }}
          >
            <RefreshMark size={11} className={loading ? 'spin' : undefined} />
            {loading ? 'Scanning…' : 'Re-run'}
          </button>
        </div>
      </div>

      <main style={{ maxWidth: 1200, margin: '0 auto', padding: '32px 24px', display: 'flex', flexDirection: 'column', gap: 24 }}>

        {/* Score + summary row */}
        <div style={{ display: 'flex', gap: 16, alignItems: 'stretch' }}>

          {/* Score ring card */}
          <div style={{ background: 'var(--surface-1)', backgroundImage: 'linear-gradient(180deg,rgba(255,255,255,0.025) 0%,transparent 50%)', border: '1px solid #27272a', borderRadius: 12, padding: 24, display: 'flex', alignItems: 'center', justifyContent: 'center', minWidth: 160 }}>
            {loading ? (
              <div className="skeleton" style={{ width: 104, height: 104, borderRadius: '50%' }} />
            ) : (
              <ScoreRing score={result?.score ?? 0} color={meta.color} />
            )}
          </div>

          {/* Summary stats */}
          <div style={{ flex: 1, background: 'var(--surface-1)', backgroundImage: 'linear-gradient(180deg,rgba(255,255,255,0.025) 0%,transparent 50%)', border: '1px solid #27272a', borderRadius: 12, padding: 24, display: 'flex', flexDirection: 'column', gap: 12 }}>
            <div style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#52525b' }}>Audit Summary</div>
            {loading ? (
              <div className="skeleton" style={{ height: 40, borderRadius: 6 }} />
            ) : (
              <>
                <div style={{ fontSize: 16, fontWeight: 600, color: '#d4d4d8', letterSpacing: '-0.02em' }}>
                  {passed} of {checkEntries.length} checks passing
                  {result?.error && <span style={{ fontSize: 12, color: '#d97706', marginLeft: 12 }}>⚠ {result.error}</span>}
                </div>
                <div style={{ fontSize: 12, color: '#52525b' }}>
                  Last scanned: <span style={{ fontFamily: 'var(--font-mono)', color: 'var(--ink-secondary)' }}>{result ? new Date(result.fetchedAt).toLocaleTimeString() : '—'}</span>
                  &nbsp;·&nbsp;Domain: <a href={`https://${meta.domain}`} target="_blank" rel="noopener noreferrer" style={{ fontFamily: 'var(--font-mono)', color: 'var(--red-500)', textDecoration: 'none' }}>{meta.domain}</a>
                </div>
              </>
            )}
          </div>
        </div>

        {/* Checklist */}
        <div style={{ background: 'var(--surface-1)', backgroundImage: 'linear-gradient(180deg,rgba(255,255,255,0.025) 0%,transparent 50%)', border: '1px solid #27272a', borderRadius: 12, overflow: 'hidden' }}>
          <div style={{ padding: '16px 20px', borderBottom: '1px solid #27272a' }}>
            <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: '0.1em', textTransform: 'uppercase', color: '#52525b' }}>SEO Checks</span>
          </div>

          {loading ? (
            Array.from({ length: 8 }).map((_, i) => (
              <div key={i} className="skeleton" style={{ height: 52, borderBottom: i < 7 ? '1px solid #27272a' : 'none' }} />
            ))
          ) : (
            checkEntries.map(([key, check], i) => (
              <motion.div
                key={key}
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: i * 0.04, ease: [0.23, 1, 0.32, 1] }}
                style={{
                  display: 'grid',
                  gridTemplateColumns: '20px 140px 1fr auto',
                  alignItems: 'center',
                  gap: 16,
                  padding: '13px 20px',
                  borderBottom: i < checkEntries.length - 1 ? '1px solid #27272a' : 'none',
                  background: !check.pass ? 'rgba(220,38,38,0.03)' : 'transparent',
                }}
              >
                {check.pass
                  ? <CheckCircleMark size={14} color="#16a34a" />
                  : <CloseMark size={14} color="#dc2626" />
                }
                <span style={{ fontSize: 12, fontWeight: 500, color: '#d4d4d8', letterSpacing: '-0.01em' }}>
                  {CHECK_LABELS[key] ?? key}
                </span>
                <span style={{ fontSize: 11, color: '#52525b', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {check.value || '—'}
                </span>
                <span style={{ fontSize: 10, fontFamily: 'var(--font-mono)', color: check.pass ? '#16a34a' : '#dc2626', whiteSpace: 'nowrap' }}>
                  {check.note}
                </span>
              </motion.div>
            ))
          )}
        </div>
      </main>
    </div>
  );
}
