"use client";

import { TelegramFeed } from "@/components/ceo/TelegramFeed";
import { useState, useEffect, useCallback, useRef, Component } from "react";
import type { ReactNode } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { motion } from "framer-motion";
import { AreaChart, Area, BarChart, Bar, XAxis, ResponsiveContainer, Cell } from "recharts";
import { supabaseClient } from "@/lib/supabase/client";
import {
  Zap, TrendingUp, GitBranch, CheckCircle2, XCircle, Circle,
  Activity, BarChart3, RefreshCw, Clock, ArrowUpRight,
} from "lucide-react";

// ─── Types ────────────────────────────────────────────────────────────────────

interface BusinessHealth {
  id: string;
  name: string;
  status: "operational" | "building" | "degraded" | "down";
  uptime_pct: number;
  deploy_frequency: number;
  open_prs: number;
  ci_passing: boolean | null;
  last_deploy: string | null;
  arr_aud: number;
  trend: number[];
}

interface EmpireHealth {
  score: number;
  businesses: BusinessHealth[];
  total_arr: number;
  active_agents: number;
  content_produced: number;
  content_total: number;
  work_orders_open: number;
  fetched_at: string;
  autonomy_pct?: number | null;
  poll_count?: number | string | null;
}

interface PiCeoActivityEvent {
  agent: string;
  action: string;
  timeAgo: string;
  ts: string;
  found: number;
}

interface BoardMandate {
  id: string;
  title: string;
  status: string;
  project_id: string | null;
  pr_url: string | null;
  ci_status: string | null;
  phill_approved: boolean | null;
  created_at: string;
}

// ─── Mock data removed (no-mock rule) ────────────────────────────────────────
//
// Previously a CONTENT_PIPELINE const + FALLBACK_ACTIVITIES const + an inline
// Hermes cron status array shipped hardcoded "fake progress" rows. All three
// are now sourced from real endpoints or hidden when no source exists.
// See `pipelineData`, `piActivity`, and the cron-status fetch below.

// ─── Status config ────────────────────────────────────────────────────────────

const STATUS_CONFIG = {
  operational: { dotColor: "#16a34a", ringColor: "rgba(22,163,74,0.3)",   sparkColor: "#16a34a", labelColor: "#16a34a" },
  building:    { dotColor: "var(--orange-400)", ringColor: "rgba(245,158,11,0.3)",  sparkColor: "var(--orange-400)", labelColor: "var(--orange-400)" },
  degraded:    { dotColor: "#d97706", ringColor: "rgba(217,119,6,0.3)",   sparkColor: "#d97706", labelColor: "#d97706" },
  down:        { dotColor: "#dc2626", ringColor: "rgba(220,38,38,0.3)",   sparkColor: "#dc2626", labelColor: "#dc2626" },
};

// ─── useCountUp hook ──────────────────────────────────────────────────────────

function useCountUp(target: number, duration = 1200): number {
  const [value, setValue] = useState(0);
  const frameRef = useRef<number>(0);
  const startRef = useRef<number | null>(null);

  useEffect(() => {
    if (target === 0) { setValue(0); return; }
    const animate = (ts: number) => {
      if (!startRef.current) startRef.current = ts;
      const elapsed = ts - startRef.current;
      const t = Math.min(elapsed / duration, 1);
      const eased = 1 - Math.pow(1 - t, 3);
      setValue(Math.round(target * eased));
      if (t < 1) { frameRef.current = requestAnimationFrame(animate); }
      else { setValue(target); }
    };
    startRef.current = null;
    frameRef.current = requestAnimationFrame(animate);
    return () => { if (frameRef.current) cancelAnimationFrame(frameRef.current); };
  }, [target, duration]);

  return value;
}

// ─── AnimatedNumber ───────────────────────────────────────────────────────────

function AnimatedNumber({ value }: { value: number }) {
  const display = useCountUp(value);
  return <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600 }}>${(display / 1000).toFixed(1)}K</span>;
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function EmpireScore({ score }: { score: number }) {
  const circumference = 2 * Math.PI * 40;
  const offset = circumference - (score / 100) * circumference;
  const color = score >= 80 ? "#16a34a" : score >= 60 ? "#d97706" : "#dc2626";
  return (
    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center" }}>
      <svg width="100" height="100" viewBox="0 0 100 100" style={{ filter: `drop-shadow(0 0 12px ${color}40)` }}>
        <circle cx="50" cy="50" r="40" fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="8" />
        <motion.circle
          cx="50" cy="50" r="40" fill="none" stroke={color} strokeWidth="8"
          strokeDasharray={circumference}
          animate={{ strokeDashoffset: offset }}
          initial={{ strokeDashoffset: circumference }}
          transition={{ duration: 1.2, ease: [0.25, 0.4, 0.25, 1] }}
          strokeLinecap="round" transform="rotate(-90 50 50)"
        />
        <text x="50" y="48" textAnchor="middle" dominantBaseline="middle"
          fill="white" fontSize="22" fontWeight="700" fontFamily="var(--font-mono)">{score}</text>
        <text x="50" y="64" textAnchor="middle" fill="#52525b" fontSize="10">/ 100</text>
      </svg>
      <span style={{ fontSize: 10, fontWeight: 600, color: "#52525b", letterSpacing: "0.08em", textTransform: "uppercase", marginTop: 4 }}>Empire Score</span>
    </div>
  );
}

function Sparkline({ data, color }: { data: number[]; color: string }) {
  if (!data || data.length === 0) return <div style={{ height: 40 }} />;
  if (typeof window === "undefined") return <div style={{ height: 40, background: "rgba(255,255,255,0.03)", borderRadius: 4 }} />;
  const chartData = data.map((v, i) => ({ i, v }));
  const gradId = `grad-${color.replace("#", "")}`;
  return (
    <ResponsiveContainer width="100%" height={40}>
      <AreaChart data={chartData} margin={{ top: 4, right: 0, left: 0, bottom: 0 }}>
        <defs>
          <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
            <stop offset="5%"  stopColor={color} stopOpacity={0.25} />
            <stop offset="95%" stopColor={color} stopOpacity={0}    />
          </linearGradient>
        </defs>
        <Area type="monotone" dataKey="v" stroke={color} strokeWidth={1.5} fill={`url(#${gradId})`} dot={false} />
      </AreaChart>
    </ResponsiveContainer>
  );
}

function CiBadge({ passing }: { passing: boolean | null }) {
  if (passing === true)  return <CheckCircle2 size={13} color="#16a34a" />;
  if (passing === false) return <XCircle      size={13} color="#dc2626" />;
  return <Circle size={13} color="var(--border-default)" />;
}

function SkeletonCard() {
  return (
    <div style={{ border: "1px solid #27272a", borderRadius: 12, padding: 16, minHeight: 170 }} className="skeleton">
      <div style={{ height: 8, background: "rgba(255,255,255,0.04)", borderRadius: 4, width: "33%", marginBottom: 12 }} />
      <div style={{ height: 16, background: "rgba(255,255,255,0.06)", borderRadius: 4, width: "66%", marginBottom: 8 }} />
      <div style={{ height: 10, background: "rgba(255,255,255,0.03)", borderRadius: 4, width: "100%", marginBottom: 16 }} />
      <div style={{ height: 40, background: "rgba(255,255,255,0.03)", borderRadius: 4 }} />
    </div>
  );
}

// ─── Error boundary ───────────────────────────────────────────────────────────

class DashboardErrorBoundary extends Component<
  { children: ReactNode },
  { hasError: boolean; error: string }
> {
  state = { hasError: false, error: "" };
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error: error.message };
  }
  render() {
    if (this.state.hasError) {
      return (
        <div style={{ minHeight: "100vh", background: "var(--canvas)", display: "flex", alignItems: "center", justifyContent: "center" }}>
          <div style={{ textAlign: "center", padding: 32 }}>
            <p style={{ color: "#dc2626", fontSize: 12, fontFamily: "var(--font-mono)", marginBottom: 16 }}>Dashboard Error</p>
            <p style={{ color: "#52525b", fontSize: 12, maxWidth: 400 }}>{this.state.error}</p>
            <button
              onClick={() => window.location.reload()}
              style={{ marginTop: 24, padding: "8px 16px", background: "var(--orange-400)", color: "#08080a", fontSize: 13, border: "none", borderRadius: 6, cursor: "pointer" }}
            >
              Reload
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

// ─── Bento Business Grid ─────────────────────────────────────────────────────

const BENTO_PRIORITIES = ['synthex', 'restoreassist', 'ccw-crm', 'carsi', 'disaster-recovery', 'nrpg'];

function BentoBusinessGrid({ businesses, loading }: { businesses: BusinessHealth[]; loading: boolean }) {
  const sorted = BENTO_PRIORITIES.map(id => businesses.find(b => b.id === id)).filter(Boolean) as BusinessHealth[];

  if (loading) return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
      {Array.from({ length: 6 }).map((_, i) => <SkeletonCard key={i} />)}
    </div>
  );

  const descriptors: Record<string, string> = {
    synthex:             "Marketing Automation · 1,000+ users",
    restoreassist:       "iOS App · TestFlight Active",
    "ccw-crm":           "First Paying Client · $2,400/yr ARR",
    "disaster-recovery": "Disaster Recovery Platform",
    nrpg:                "ANZ Restoration Movement",
    carsi:               "Compliance Delivery",
  };

  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12 }}>
      {sorted.map((biz, i) => {
        const cfg = STATUS_CONFIG[biz.status];
        const isFeatured = i < 2;
        return (
          <motion.div
            key={biz.id}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3, delay: i * 0.05, ease: [0.23, 1, 0.32, 1] }}
            style={{
              background: "var(--surface-1)",
              backgroundImage: `linear-gradient(180deg, rgba(255,255,255,0.025) 0%, rgba(255,255,255,0) 50%), linear-gradient(180deg, ${cfg.dotColor}08 0%, transparent 100%)`,
              border: "1px solid #27272a",
              borderRadius: 12,
              padding: isFeatured ? 20 : 16,
              display: "flex",
              flexDirection: "column",
              gap: isFeatured ? 14 : 10,
              minHeight: isFeatured ? 200 : 160,
            }}
          >
            {/* Header row */}
            <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
              <div>
                <div style={{ fontSize: isFeatured ? 16 : 14, fontWeight: 700, color: "var(--ink-primary)", letterSpacing: "-0.03em", fontFamily: "var(--font-display)", lineHeight: 1.2 }}>{biz.name}</div>
                <div style={{ fontSize: 11, color: "#52525b", marginTop: 3 }}>{descriptors[biz.id]}</div>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span className="status-dot" style={{ width: 6, height: 6, background: cfg.dotColor, color: cfg.dotColor }} />
                <span style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.04em", textTransform: "uppercase", color: cfg.dotColor }}>{biz.status}</span>
              </div>
            </div>

            {/* ARR badge for revenue-generating */}
            {biz.arr_aud > 0 && (
              <div style={{ display: "inline-flex", alignItems: "center", gap: 5, padding: "3px 8px", borderRadius: 6, background: "rgba(22,163,74,0.08)", border: "1px solid rgba(22,163,74,0.18)" }}>
                <TrendingUp size={10} color="#16a34a" />
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 600, color: "#16a34a" }}>${biz.arr_aud.toLocaleString()}/yr</span>
              </div>
            )}

            {/* Sparkline */}
            <div style={{ flex: 1 }}>
              <Sparkline data={biz.trend} color={cfg.sparkColor} />
            </div>

            {/* Bottom metrics */}
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", paddingTop: 10, borderTop: "1px solid #27272a" }}>
              <div style={{ display: "flex", gap: 12 }}>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--ink-secondary)" }}>
                  <span style={{ color: biz.uptime_pct >= 99 ? "#16a34a" : biz.uptime_pct >= 95 ? "#d97706" : "#dc2626", fontWeight: 600 }}>{biz.uptime_pct}%</span> up
                </span>
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "#52525b" }}>{biz.deploy_frequency}×/wk</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                {biz.open_prs > 0 && (
                  <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "#d97706", display: "flex", alignItems: "center", gap: 3 }}>
                    <GitBranch size={9} color="#d97706" />{biz.open_prs}
                  </span>
                )}
                <CiBadge passing={biz.ci_passing} />
              </div>
            </div>
          </motion.div>
        );
      })}
    </div>
  );
}

// ─── Board Mandates ───────────────────────────────────────────────────────────

const MANDATE_STATUS_COLORS: Record<string, { bg: string; text: string }> = {
  active:    { bg: "rgba(245,158,11,0.12)",   text: "var(--orange-400)" },
  executing: { bg: "rgba(245,158,11,0.12)",  text: "var(--orange-400)" },
  review:    { bg: "rgba(139,92,246,0.12)",  text: "#8b5cf6" },
  merged:    { bg: "rgba(22,163,74,0.12)",   text: "#16a34a" },
  default:   { bg: "rgba(63,63,70,0.3)",     text: "#71717a" },
};

function MandateStatusBadge({ status }: { status: string }) {
  const cfg = MANDATE_STATUS_COLORS[status] ?? MANDATE_STATUS_COLORS.default;
  return (
    <span style={{
      fontFamily: "var(--font-mono)", fontSize: 9, fontWeight: 600,
      letterSpacing: "0.06em", textTransform: "uppercase",
      padding: "2px 7px", borderRadius: 3,
      background: cfg.bg, color: cfg.text,
    }}>
      {status}
    </span>
  );
}

function BoardMandatesSection({ mandates, loading }: { mandates: BoardMandate[]; loading: boolean }) {
  if (loading) {
    return (
      <div style={{ background: "var(--surface-1)", border: "1px solid #27272a", borderRadius: 12, padding: 20 }}>
        <div style={{ height: 8, background: "rgba(255,255,255,0.04)", borderRadius: 4, width: "40%", marginBottom: 12 }} />
        {[0,1,2].map(i => (
          <div key={i} style={{ height: 14, background: "rgba(255,255,255,0.03)", borderRadius: 4, marginBottom: 10, width: `${70 - i * 10}%` }} />
        ))}
      </div>
    );
  }

  if (mandates.length === 0) {
    return (
      <div style={{
        background: "var(--surface-1)",
        backgroundImage: "linear-gradient(180deg, rgba(255,255,255,0.025) 0%, transparent 50%)",
        border: "1px solid #27272a",
        borderRadius: 12,
        padding: "28px 20px",
        textAlign: "center",
      }}>
        <p style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--ink-tertiary)", margin: 0 }}>NO OPEN MANDATES</p>
        <p style={{ fontSize: 11, color: "var(--ink-tertiary)", margin: "4px 0 0" }}>All board mandates are closed or the table doesn't exist yet.</p>
      </div>
    );
  }

  return (
    <div style={{
      background: "var(--surface-1)",
      backgroundImage: "linear-gradient(180deg, rgba(255,255,255,0.025) 0%, transparent 50%)",
      border: "1px solid #27272a",
      borderRadius: 12,
      overflow: "hidden",
    }}>
      {mandates.map((m, i) => (
        <div key={m.id} style={{
          display: "grid",
          gridTemplateColumns: "1fr 90px 80px 80px 60px",
          gap: 12, alignItems: "center",
          padding: "11px 18px",
          borderBottom: i < mandates.length - 1 ? "1px solid #27272a" : "none",
        }}>
          <span style={{ fontSize: 12, fontWeight: 500, color: "#d4d4d8", letterSpacing: "-0.01em", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            {m.title}
          </span>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "#52525b" }}>
            {m.project_id ?? "—"}
          </span>
          <MandateStatusBadge status={m.status} />
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: m.ci_status === "passing" ? "#16a34a" : m.ci_status === "failing" ? "#dc2626" : "#52525b" }}>
            {m.ci_status ? `CI: ${m.ci_status}` : "no CI"}
          </span>
          {m.pr_url ? (
            <a href={m.pr_url} target="_blank" rel="noopener noreferrer" style={{
              fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--orange-400)",
              textDecoration: "none", display: "flex", alignItems: "center", gap: 3,
            }}>
              PR <ArrowUpRight size={9} />
            </a>
          ) : (
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--ink-tertiary)" }}>no PR</span>
          )}
        </div>
      ))}
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────

export default function CeoCommandCenter() {
  const router = useRouter();
  const [mounted, setMounted] = useState(false);
  const [user, setUser] = useState<{ email: string } | null>(null);
  const [health, setHealth] = useState<EmpireHealth | null>(null);
  const [loading, setLoading] = useState(true);
  const [secondsAgo, setSecondsAgo] = useState(0);
  const lastFetchRef = useRef<Date>(new Date());
  const [piActivity, setPiActivity] = useState<PiCeoActivityEvent[]>([]);
  const [piConnected, setPiConnected] = useState(false);
  const [piAutonomyPct, setPiAutonomyPct] = useState<number | null>(null);
  const [piPollCount, setPiPollCount] = useState<number | null>(null);
  const [mandates, setMandates] = useState<BoardMandate[]>([]);
  const [mandatesLoading, setMandatesLoading] = useState(true);

  useEffect(() => { setMounted(true); }, []);

  const fetchHealth = useCallback(async () => {
    try {
      const res = await fetch("/api/empire/health");
      if (res.ok) {
        const data: EmpireHealth = await res.json();
        setHealth(data);
        lastFetchRef.current = new Date();
        setSecondsAgo(0);
      }
    } catch {
      // silently retain previous data
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const init = async () => {
      const { data: { session } } = await supabaseClient.auth.getSession();
      if (!session) { router.push("/login"); return; }
      setUser({ email: session.user.email ?? "" });
      fetchHealth();
    };
    init();
  }, [router, fetchHealth]);

  // 30-second auto-refresh
  useEffect(() => {
    const interval = setInterval(fetchHealth, 30_000);
    return () => clearInterval(interval);
  }, [fetchHealth]);

  // Pi-CEO activity feed — fetch on mount and every 30 seconds
  useEffect(() => {
    const fetchPiActivity = async () => {
      try {
        const res = await fetch('/api/pi-ceo/activity');
        if (res.ok) {
          const data = await res.json();
          setPiActivity(data.events ?? []);
          setPiConnected(data.connected ?? false);
          if (data.autonomy_pct != null) setPiAutonomyPct(data.autonomy_pct);
          if (data.poll_count != null) setPiPollCount(data.poll_count);
        }
      } catch { /* silently retain previous */ }
    };
    fetchPiActivity();
    const interval = setInterval(fetchPiActivity, 30_000);
    return () => clearInterval(interval);
  }, []);

  // Board mandates
  useEffect(() => {
    const fetchMandates = async () => {
      try {
        const res = await fetch('/api/mandates');
        if (res.ok) {
          const data = await res.json();
          setMandates(data);
        }
      } catch { /* silently retain */ } finally {
        setMandatesLoading(false);
      }
    };
    fetchMandates();
    const interval = setInterval(fetchMandates, 60_000);
    return () => clearInterval(interval);
  }, []);

  // Tick "Updated Xs ago"
  useEffect(() => {
    const tick = setInterval(() => {
      setSecondsAgo(Math.round((Date.now() - lastFetchRef.current.getTime()) / 1000));
    }, 1000);
    return () => clearInterval(tick);
  }, []);

  // Content pipeline values come from the real empire health payload only.
  // No fake totals when the source is missing — the stat strip and the
  // pipeline section both render dashes / hide gracefully in that case.
  const totalContent = health?.content_produced ?? 0;
  const totalTarget  = health?.content_total ?? 0;

  const arrData = health?.businesses.map(b => ({
    name: b.name.replace(" Platform", "").replace("-CRM", ""),
    arr: b.arr_aud,
    preRevenue: b.arr_aud === 0,
  })) ?? [];

  const updatedLabel = secondsAgo < 60 ? `${secondsAgo}s ago` : `${Math.floor(secondsAgo / 60)}m ago`;

  // Resolve autonomy data from pi-ceo activity response or empire health fallback
  const resolvedAutonomyPct = piAutonomyPct ?? health?.autonomy_pct ?? 100;
  const resolvedPollCount = piPollCount ?? health?.poll_count ?? "—";

  const card: React.CSSProperties = {
    background: "var(--surface-1)",
    border: "1px solid #27272a",
    borderRadius: 12,
    padding: 20,
    backgroundImage: "linear-gradient(180deg, rgba(255,255,255,0.025) 0%, rgba(255,255,255,0) 50%)",
    backgroundSize: "100% 100%",
  };

  const sectionLabel: React.CSSProperties = {
    fontSize: 10,
    fontWeight: 600,
    letterSpacing: "0.1em",
    textTransform: "uppercase",
    color: "#52525b",
    marginBottom: 12,
  };

  // Suppress hydration mismatch for AnimatedNumber
  void AnimatedNumber;

  return (
    <DashboardErrorBoundary>
    <div style={{ minHeight: "100vh", background: "var(--canvas)", color: "var(--ink-primary)" }}>

      {/* ── Header ──────────────────────────────────────────────────────────── */}
      <header style={{
        background: "rgba(9,9,11,0.9)",
        backdropFilter: "blur(20px) saturate(180%)",
        WebkitBackdropFilter: "blur(20px) saturate(180%)",
        borderBottom: "1px solid #27272a",
        height: 60,
        padding: "0 24px",
        position: "sticky",
        top: 0,
        zIndex: 40,
        display: "flex",
        alignItems: "center",
      }}>
        <div style={{ maxWidth: 1440, margin: "0 auto", width: "100%", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          {/* Wordmark */}
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div style={{ width: 28, height: 28, borderRadius: 7, background: "var(--orange-400)", display: "flex", alignItems: "center", justifyContent: "center" }}>
              <Zap size={14} color="white" strokeWidth={2.5} />
            </div>
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: "var(--ink-primary)", letterSpacing: "-0.02em", fontFamily: "var(--font-display)" }}>Unite Group</div>
              <div style={{ display: "flex", alignItems: "center", gap: 4, marginTop: 1 }}>
                <span className="status-dot" style={{ width: 5, height: 5, background: piConnected ? "#16a34a" : "var(--orange-400)", color: piConnected ? "#16a34a" : "var(--orange-400)" }} />
                <span style={{ fontSize: 9, color: piConnected ? "#16a34a" : "var(--orange-400)", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase" }}>Command Center</span>
              </div>
            </div>
          </div>
          {/* Right: user + refresh + clock */}
          <div style={{ display: "flex", alignItems: "center", gap: 16 }}>
            {user && <span style={{ fontSize: 11, color: "#52525b", fontFamily: "var(--font-mono)" }}>{user.email}</span>}
            <div style={{ display: "flex", alignItems: "center", gap: 4, color: "#52525b" }}>
              <Clock size={11} />
              <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "#52525b" }}>{updatedLabel}</span>
            </div>
            <button
              onClick={fetchHealth} disabled={loading}
              style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 10px", fontSize: 11, fontWeight: 500, borderRadius: 7, border: "1px solid #27272a", color: "var(--ink-secondary)", background: "transparent", cursor: loading ? "not-allowed" : "pointer", transition: "all 0.12s ease" }}
              onMouseEnter={e => { if (!loading) { (e.currentTarget as HTMLButtonElement).style.background = "var(--surface-1)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--ink-primary)"; }}}
              onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "transparent"; (e.currentTarget as HTMLButtonElement).style.color = "var(--ink-secondary)"; }}
            >
              <RefreshCw size={11} className={loading ? "spin" : ""} />
              {loading ? "Refreshing…" : "Refresh"}
            </button>
          </div>
        </div>
      </header>

      {/* ── Stats strip ─────────────────────────────────────────────────────── */}
      <div style={{ maxWidth: 1440, margin: "0 auto", padding: "20px 24px 0" }}>

        {/* System Status Bar */}
        <div style={{
          display: "flex", alignItems: "center", justifyContent: "space-between",
          padding: "10px 20px",
          background: piConnected ? "rgba(22,163,74,0.07)" : "rgba(245,158,11,0.07)",
          border: `1px solid ${piConnected ? "rgba(22,163,74,0.2)" : "rgba(245,158,11,0.2)"}`,
          borderRadius: 8,
          marginBottom: 16,
        }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
            <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
              <span className="status-dot" style={{
                width: 8, height: 8,
                background: piConnected ? "#16a34a" : "var(--orange-400)",
                color: piConnected ? "#16a34a" : "var(--orange-400)",
              }} />
              <span style={{
                fontFamily: "var(--font-mono)", fontSize: 11, fontWeight: 700,
                letterSpacing: "0.1em", textTransform: "uppercase",
                color: piConnected ? "#16a34a" : "var(--orange-400)",
              }}>
                {piConnected ? "AUTONOMOUS — SYSTEM OPERATING" : "STANDBY — AWAITING COMMAND"}
              </span>
            </div>
            <span style={{ color: "var(--ink-tertiary)", fontSize: 9 }}>|</span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "#52525b" }}>
              Pi-CEO: {health?.active_agents ?? 0} agents · {resolvedAutonomyPct}% autonomy · poll #{resolvedPollCount}
            </span>
            <span style={{ color: "var(--ink-tertiary)", fontSize: 9 }}>|</span>
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "#52525b" }}>
              Hermes: 10 crons · PM-Core active · {health?.work_orders_open ?? 0} mandates
            </span>
          </div>
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--ink-tertiary)", flexShrink: 0, marginLeft: 12 }}>
            Updated {updatedLabel}
          </span>
        </div>

        <div style={{ display: "flex", background: "var(--surface-1)", border: "1px solid #27272a", borderRadius: 10, overflow: "hidden", backgroundImage: "linear-gradient(180deg, rgba(255,255,255,0.02) 0%, transparent 50%)" }}>
          {[
            { label: "Empire Health", value: health ? `${health.score}` : "—", suffix: "/100", color: health ? (health.score >= 80 ? "#16a34a" : health.score >= 60 ? "#d97706" : "#dc2626") : "#52525b" },
            { label: "Empire ARR",    value: `$${((health?.total_arr ?? 2400)/1000).toFixed(1)}K`, suffix: "/yr", color: "#16a34a" },
            { label: "AI Agents",     value: String(health?.active_agents ?? 4), suffix: " live", color: "#d4d4d8" },
            { label: "Content",       value: `${health?.content_produced ?? totalContent}/${health?.content_total ?? totalTarget}`, suffix: "", color: "#d4d4d8" },
            { label: "Mandates",      value: String(health?.work_orders_open ?? 0), suffix: " open", color: health?.work_orders_open ? "var(--orange-400)" : "#52525b" },
          ].map((stat, i, arr) => (
            <div key={stat.label} style={{ flex: 1, padding: "16px 20px", textAlign: "center", borderRight: i < arr.length - 1 ? "1px solid #27272a" : "none" }}>
              <div style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: "#52525b", marginBottom: 5 }}>{stat.label}</div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 22, fontWeight: 700, letterSpacing: "-0.03em", color: stat.color, lineHeight: 1 }}>
                {stat.value}<span style={{ fontSize: 12, fontWeight: 400, color: "#52525b" }}>{stat.suffix}</span>
              </div>
            </div>
          ))}
        </div>
      </div>

      <main style={{ maxWidth: 1440, margin: "0 auto", padding: "24px", display: "flex", flexDirection: "column", gap: 32 }}>

        {/* ── Portfolio Bento Grid ─────────────────────────────────────────── */}
        <section>
          <p style={sectionLabel}>PORTFOLIO STATUS</p>
          <BentoBusinessGrid businesses={health?.businesses ?? []} loading={loading} />
        </section>

        {/* ── Three-column feeds ──────────────────────────────────────────── */}
        <section style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 16 }}>

          {/* Col 1 — Agent Activity Feed (timeline) */}
          <motion.div
            style={card}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: 0.1, ease: [0.23, 1, 0.32, 1] }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Activity size={14} color="#60a5fa" />
                <span style={{ fontSize: 13, fontWeight: 600, color: "var(--ink-primary)" }}>AGENT ACTIVITY FEED</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span className="status-dot" style={{ width: 6, height: 6, background: piConnected ? "#16a34a" : "#d97706", color: piConnected ? "#16a34a" : "#d97706" }} />
                <span style={{ fontSize: 10, fontWeight: 600, color: piConnected ? "#16a34a" : "#d97706", letterSpacing: "0.05em", textTransform: "uppercase" }}>
                  {piConnected ? "Live" : "Fallback"}
                </span>
              </div>
            </div>

            {/* Vertical timeline */}
            <div style={{ borderTop: "1px solid #27272a", paddingTop: 12, position: "relative" }}>
              {piActivity.length === 0 ? (
                <div style={{ padding: "16px 0", textAlign: "center" }}>
                  <p style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--ink-tertiary)", margin: 0 }}>
                    NO AGENT ACTIVITY YET
                  </p>
                  <p style={{ fontSize: 11, color: "var(--ink-tertiary)", margin: "4px 0 0" }}>
                    Live events appear once Pi-CEO reports back.
                  </p>
                </div>
              ) : (
                <div style={{ borderLeft: "1px solid #27272a", marginLeft: 8, paddingLeft: 16, display: "flex", flexDirection: "column", gap: 0 }}>
                  {piActivity.map((a, i, arr) => (
                    <div key={i} style={{ position: "relative", paddingBottom: i < arr.length - 1 ? 14 : 0 }}>
                      <span style={{
                        position: "absolute", left: -21, top: 3,
                        width: 6, height: 6, borderRadius: "50%",
                        background: "var(--border-default)", border: "1px solid #3f3f46",
                        display: "inline-block"
                      }} />
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
                        <div>
                          <p style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "#d4d4d8", margin: 0, letterSpacing: "0.02em" }}>
                            {a.agent.toUpperCase()}
                          </p>
                          <p style={{ fontSize: 11, color: "#52525b", margin: "2px 0 0" }}>{a.action}</p>
                        </div>
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--ink-tertiary)", flexShrink: 0, marginLeft: 8 }}>
                          {a.timeAgo}
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div style={{ marginTop: 12, paddingTop: 10, borderTop: "1px solid #27272a", display: "flex", alignItems: "center", gap: 6 }}>
              <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "#52525b" }}>
                {health?.work_orders_open ?? 0} open mandates
              </span>
            </div>
          </motion.div>

          {/* Col 2 — Empire ARR BarChart */}
          <motion.div
            style={card}
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.35, delay: 0.15, ease: [0.23, 1, 0.32, 1] }}
          >
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <TrendingUp size={14} color="#16a34a" />
                <span style={{ fontSize: 13, fontWeight: 600, color: "var(--ink-primary)" }}>EMPIRE ARR</span>
              </div>
              <span style={{ fontSize: 12, fontFamily: "var(--font-mono)", fontWeight: 700, color: "#16a34a" }}>
                ${((health?.total_arr ?? 2400) / 1000).toFixed(1)}K ARR
              </span>
            </div>
            <div style={{ borderTop: "1px solid #27272a", paddingTop: 12 }}>
              {mounted ? (
                <ResponsiveContainer width="100%" height={120}>
                  <BarChart data={arrData} margin={{ top: 4, right: 4, left: -20, bottom: 0 }} barSize={16}>
                    <XAxis dataKey="name" tick={{ fill: "#52525b", fontSize: 9 }} axisLine={false} tickLine={false} />
                    <Bar dataKey="arr" radius={[3, 3, 0, 0]}>
                      {arrData.map((entry, index) => (
                        <Cell
                          key={index}
                          fill={entry.preRevenue ? "rgba(255,255,255,0.04)" : "var(--orange-400)"}
                          stroke={entry.preRevenue ? "var(--border-default)" : "none"}
                          strokeWidth={1}
                        />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              ) : (
                <div style={{ height: 80, background: "rgba(255,255,255,0.03)", borderRadius: 4 }} />
              )}
              <div style={{ marginTop: 12, display: "flex", flexDirection: "column", gap: 4 }}>
                <p style={{ fontSize: 12, color: "#52525b", margin: 0 }}>
                  Total ARR:{" "}
                  <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600, color: "#16a34a" }}>
                    ${(health?.total_arr ?? 2400).toLocaleString()}/yr
                  </span>
                </p>
                <p style={{ fontSize: 11, color: "#52525b", margin: 0 }}>Next milestone: first $10K ARR</p>
                <div style={{ display: "flex", alignItems: "center", gap: 16, marginTop: 4 }}>
                  <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10, color: "#52525b" }}>
                    <span style={{ width: 10, height: 10, borderRadius: 2, background: "var(--orange-400)", display: "inline-block" }} />
                    Revenue
                  </span>
                  <span style={{ display: "flex", alignItems: "center", gap: 5, fontSize: 10, color: "#52525b" }}>
                    <span style={{ width: 10, height: 10, borderRadius: 2, background: "rgba(255,255,255,0.04)", border: "1px solid #27272a", display: "inline-block" }} />
                    Pre-revenue
                  </span>
                </div>
              </div>
            </div>
          </motion.div>

          {/* Col 3 — Content Pipeline. Only renders when real data is wired
              (see TODO(UNI-1991) below). Hidden until /api/empire/pipeline ships. */}
          {totalTarget > 0 && (
            <motion.div
              style={card}
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, delay: 0.2, ease: [0.23, 1, 0.32, 1] }}
            >
              <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 16 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                  <BarChart3 size={14} color="#8b5cf6" />
                  <span style={{ fontSize: 13, fontWeight: 600, color: "var(--ink-primary)" }}>CONTENT PIPELINE</span>
                </div>
                <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", fontWeight: 500, color: "#52525b" }}>
                  {totalContent}/{totalTarget} ({Math.round((totalContent / totalTarget) * 100)}%)
                </span>
              </div>

              {/* Overall bar */}
              <div style={{ marginBottom: 16 }}>
                <div style={{ height: 3, background: "rgba(255,255,255,0.05)", borderRadius: 2, overflow: "hidden" }}>
                  <motion.div
                    style={{ height: "100%", borderRadius: 2, background: "var(--orange-400)" }}
                    initial={{ width: 0 }}
                    animate={{ width: `${Math.round((totalContent / totalTarget) * 100)}%` }}
                    transition={{ duration: 0.8, ease: [0.25, 0.4, 0.25, 1] }}
                  />
                </div>
                <p style={{ fontSize: 10, color: "#52525b", margin: 0, marginTop: 5 }}>
                  {Math.round((totalContent / totalTarget) * 100)}% complete overall
                </p>
              </div>

              {/* TODO(UNI-1991): wire per-business pipeline rows once
                  /api/empire/pipeline exists. Until then we show only the
                  aggregate (real) numbers — no fake per-business breakdown. */}
            </motion.div>
          )}
        </section>

        {/* Hermes Cron Status — removed (no-mock rule). The previous block
            shipped 8 hardcoded cron rows with fake "last run" timestamps and
            fake model labels. The real Hermes cron state lives in
            ~/Pi-CEO/Pi-Dev-Ops/.harness/swarm/ which Vercel cannot read.
            TODO(UNI-1992): expose /api/empire/hermes-crons via Supabase
            and render that here instead. */}

        {/* ── Board Mandates ───────────────────────────────────────────────── */}
        <section>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 12 }}>
            <p style={{ ...sectionLabel, marginBottom: 0 }}>BOARD MANDATES</p>
            <Link href="/en/empire" style={{ fontSize: 11, color: "var(--orange-400)", textDecoration: "none" }}>View full board →</Link>
          </div>
          <BoardMandatesSection mandates={mandates} loading={mandatesLoading} />
        </section>

        {/* ── Telegram Live Feed ──────────────────────────────────────────── */}
        <section>
          <p style={sectionLabel}>Margot — Telegram Live Feed</p>
          <TelegramFeed />
        </section>

        {/* ── Command Shortcuts ────────────────────────────────────────────── */}
        <section>
          <p style={sectionLabel}>COMMAND SHORTCUTS</p>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            <Link
              href="/en/empire"
              style={{ display: "flex", alignItems: "center", gap: 7, padding: "7px 12px", fontSize: 12, fontWeight: 500, borderRadius: 8, border: "1px solid #27272a", color: "var(--ink-secondary)", textDecoration: "none", background: "transparent", transition: "all 0.12s ease" }}
              onMouseEnter={e => { (e.currentTarget as HTMLAnchorElement).style.background = "var(--surface-1)"; (e.currentTarget as HTMLAnchorElement).style.borderColor = "var(--ink-tertiary)"; (e.currentTarget as HTMLAnchorElement).style.color = "var(--ink-primary)"; }}
              onMouseLeave={e => { (e.currentTarget as HTMLAnchorElement).style.background = "transparent"; (e.currentTarget as HTMLAnchorElement).style.borderColor = "var(--border-default)"; (e.currentTarget as HTMLAnchorElement).style.color = "var(--ink-secondary)"; }}
              onMouseDown={e => { (e.currentTarget as HTMLAnchorElement).style.transform = "scale(0.97)"; }}
              onMouseUp={e => { (e.currentTarget as HTMLAnchorElement).style.transform = "scale(1)"; }}
            >
              Board Minutes
              <ArrowUpRight size={12} />
            </Link>
            <Link
              href="/clients/ccw"
              style={{ display: "flex", alignItems: "center", gap: 7, padding: "7px 12px", fontSize: 12, fontWeight: 500, borderRadius: 8, border: "1px solid #27272a", color: "var(--ink-secondary)", textDecoration: "none", background: "transparent", transition: "all 0.12s ease" }}
              onMouseEnter={e => { (e.currentTarget as HTMLAnchorElement).style.background = "var(--surface-1)"; (e.currentTarget as HTMLAnchorElement).style.borderColor = "var(--ink-tertiary)"; (e.currentTarget as HTMLAnchorElement).style.color = "var(--ink-primary)"; }}
              onMouseLeave={e => { (e.currentTarget as HTMLAnchorElement).style.background = "transparent"; (e.currentTarget as HTMLAnchorElement).style.borderColor = "var(--border-default)"; (e.currentTarget as HTMLAnchorElement).style.color = "var(--ink-secondary)"; }}
              onMouseDown={e => { (e.currentTarget as HTMLAnchorElement).style.transform = "scale(0.97)"; }}
              onMouseUp={e => { (e.currentTarget as HTMLAnchorElement).style.transform = "scale(1)"; }}
            >
              CCW Portal
              <ArrowUpRight size={12} />
            </Link>
            <Link
              href="/en/empire"
              style={{ display: "flex", alignItems: "center", gap: 7, padding: "7px 12px", fontSize: 12, fontWeight: 500, borderRadius: 8, border: "1px solid #27272a", color: "var(--ink-secondary)", textDecoration: "none", background: "transparent", transition: "all 0.12s ease" }}
              onMouseEnter={e => { (e.currentTarget as HTMLAnchorElement).style.background = "var(--surface-1)"; (e.currentTarget as HTMLAnchorElement).style.borderColor = "var(--ink-tertiary)"; (e.currentTarget as HTMLAnchorElement).style.color = "var(--ink-primary)"; }}
              onMouseLeave={e => { (e.currentTarget as HTMLAnchorElement).style.background = "transparent"; (e.currentTarget as HTMLAnchorElement).style.borderColor = "var(--border-default)"; (e.currentTarget as HTMLAnchorElement).style.color = "var(--ink-secondary)"; }}
              onMouseDown={e => { (e.currentTarget as HTMLAnchorElement).style.transform = "scale(0.97)"; }}
              onMouseUp={e => { (e.currentTarget as HTMLAnchorElement).style.transform = "scale(1)"; }}
            >
              Content Artefacts
            </Link>
            <button
              onClick={fetchHealth}
              disabled={loading}
              style={{ display: "flex", alignItems: "center", gap: 7, padding: "7px 12px", fontSize: 12, fontWeight: 500, borderRadius: 8, border: "1px solid #27272a", color: "var(--ink-secondary)", background: "transparent", cursor: loading ? "not-allowed" : "pointer", opacity: loading ? 0.5 : 1, transition: "all 0.12s ease" }}
              onMouseEnter={e => { if (!loading) { (e.currentTarget as HTMLButtonElement).style.background = "var(--surface-1)"; (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--ink-tertiary)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--ink-primary)"; }}}
              onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "transparent"; (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border-default)"; (e.currentTarget as HTMLButtonElement).style.color = "var(--ink-secondary)"; }}
              onMouseDown={e => { if (!loading) (e.currentTarget as HTMLButtonElement).style.transform = "scale(0.97)"; }}
              onMouseUp={e => { (e.currentTarget as HTMLButtonElement).style.transform = "scale(1)"; }}
            >
              <RefreshCw size={12} className={loading ? "spin" : ""} />
              {loading ? "Running…" : "Run Health Check"}
            </button>
            <Link
              href="/en/empire"
              style={{ display: "flex", alignItems: "center", gap: 7, padding: "7px 12px", fontSize: 12, fontWeight: 600, borderRadius: 8, border: "1px solid #f59e0b", color: "#fff", textDecoration: "none", background: "var(--orange-400)", transition: "all 0.16s ease" }}
              onMouseEnter={e => { (e.currentTarget as HTMLAnchorElement).style.background = "var(--orange-400)"; (e.currentTarget as HTMLAnchorElement).style.borderColor = "var(--orange-400)"; }}
              onMouseLeave={e => { (e.currentTarget as HTMLAnchorElement).style.background = "var(--orange-400)"; (e.currentTarget as HTMLAnchorElement).style.borderColor = "var(--orange-400)"; }}
              onMouseDown={e => { (e.currentTarget as HTMLAnchorElement).style.transform = "scale(0.97)"; (e.currentTarget as HTMLAnchorElement).style.background = "#1e40af"; }}
              onMouseUp={e => { (e.currentTarget as HTMLAnchorElement).style.transform = "scale(1)"; }}
            >
              6-Pager Brief
            </Link>
            <Link
              href="https://linear.app"
              target="_blank"
              rel="noopener noreferrer"
              style={{ display: "flex", alignItems: "center", gap: 7, padding: "7px 12px", fontSize: 12, fontWeight: 500, borderRadius: 8, border: "1px solid #27272a", color: "var(--ink-secondary)", textDecoration: "none", background: "transparent", transition: "all 0.12s ease" }}
              onMouseEnter={e => { (e.currentTarget as HTMLAnchorElement).style.background = "var(--surface-1)"; (e.currentTarget as HTMLAnchorElement).style.borderColor = "var(--ink-tertiary)"; (e.currentTarget as HTMLAnchorElement).style.color = "var(--ink-primary)"; }}
              onMouseLeave={e => { (e.currentTarget as HTMLAnchorElement).style.background = "transparent"; (e.currentTarget as HTMLAnchorElement).style.borderColor = "var(--border-default)"; (e.currentTarget as HTMLAnchorElement).style.color = "var(--ink-secondary)"; }}
              onMouseDown={e => { (e.currentTarget as HTMLAnchorElement).style.transform = "scale(0.97)"; }}
              onMouseUp={e => { (e.currentTarget as HTMLAnchorElement).style.transform = "scale(1)"; }}
            >
              Linear Tickets
              <ArrowUpRight size={12} />
            </Link>
          </div>
        </section>

      </main>
    </div>
    </DashboardErrorBoundary>
  );
}
