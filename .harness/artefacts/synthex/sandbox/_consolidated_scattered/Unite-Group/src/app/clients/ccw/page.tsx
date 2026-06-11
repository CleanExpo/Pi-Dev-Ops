"use client";

import { useState, useEffect, useCallback } from "react";
import { useRouter } from "next/navigation";
import { motion } from "framer-motion";
import { supabaseClient } from "@/lib/supabase/client";
import type { CcwHealth } from "@/app/api/clients/ccw/health/route";
import { RefreshMark, ActivityMark, TrendUpMark, UsersMark, BarChartMark } from "@/components/ui/marks";

// CCW accent — exposed as a CSS custom property at the page root so future
// brand_config plumbing (UNI-1992/1994) can override it without touching this
// file. Consumers in this file read `var(--brand-primary)`; the literal lives
// here as the CCW default.
const BRAND_PRIMARY_DEFAULT = "#D62828";

function formatRelativeTime(isoString: string | null): string {
  if (!isoString) return "—";
  const diffMs = Date.now() - new Date(isoString).getTime();
  const diffMin = Math.floor(diffMs / 60000);
  if (diffMin < 1) return "just now";
  if (diffMin < 60) return `${diffMin} min ago`;
  const diffHr = Math.floor(diffMin / 60);
  if (diffHr < 24) return `${diffHr} hour${diffHr !== 1 ? "s" : ""} ago`;
  const diffDays = Math.floor(diffHr / 24);
  return `${diffDays} day${diffDays !== 1 ? "s" : ""} ago`;
}

function formatDate(isoString: string | null): string {
  if (!isoString) return "—";
  return new Date(isoString).toLocaleDateString("en-AU", { day: "numeric", month: "short", year: "numeric" });
}

// ── Sub-components ────────────────────────────────────────────────────────────

const card: React.CSSProperties = {
  background: "var(--surface-1)",
  border: "1px solid #27272a",
  borderRadius: 12,
  padding: 20,
};

function MetricRow({ label, value }: { label: string; value: string | number }) {
  return (
    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "baseline", padding: "8px 0", borderBottom: "1px solid #27272a" }}>
      <span style={{ fontSize: 13, color: "var(--ink-tertiary)" }}>{label}</span>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 600, color: "#94a3b8" }}>{value}</span>
    </div>
  );
}

function StatusPill({ label, type }: { label: string; type: "ok" | "warn" | "err" }) {
  const colors = { ok: { bg: "rgba(22,163,74,0.1)", border: "rgba(22,163,74,0.25)", text: "#16a34a" }, warn: { bg: "rgba(217,119,6,0.1)", border: "rgba(217,119,6,0.25)", text: "#d97706" }, err: { bg: "rgba(220,38,38,0.1)", border: "rgba(220,38,38,0.25)", text: "#dc2626" } }[type];
  return (
    <span style={{ display: "inline-block", padding: "4px 10px", borderRadius: 20, background: colors.bg, border: `1px solid ${colors.border}`, fontSize: 11, fontWeight: 700, color: colors.text, letterSpacing: "0.05em", textTransform: "uppercase" }}>{label}</span>
  );
}

function SkeletonCard() {
  return (
    <div style={{ ...card, minHeight: 180, display: "flex", flexDirection: "column", gap: 12 }}>
      {[100, 60, 80, 60].map((w, i) => (
        <div key={i} style={{ height: i === 0 ? 24 : 14, width: `${w}%`, background: "rgba(255,255,255,0.04)", borderRadius: 4 }} className="animate-pulse" />
      ))}
    </div>
  );
}

function CrmCard({ data }: { data: CcwHealth }) {
  const type = data.crm_status === "operational" ? "ok" : data.crm_status === "degraded" ? "warn" : "err";
  return (
    <motion.div style={card} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0, ease: [0.23, 1, 0.32, 1] }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
        <ActivityMark size={14} color="#94a3b8" />
        <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--ink-tertiary)", margin: 0 }}>CRM Health</p>
      </div>
      <div style={{ marginBottom: 14 }}><StatusPill label={data.crm_status} type={type} /></div>
      <MetricRow label="Uptime" value={`${data.crm_uptime_pct.toFixed(2)}%`} />
      <MetricRow label="Last deployment" value={data.last_deployment ? formatDate(data.last_deployment) : "—"} />
    </motion.div>
  );
}

function SlaCard({ data }: { data: CcwHealth }) {
  const type = data.sla_status === "green" ? "ok" : data.sla_status === "warn" ? "warn" : "err";
  return (
    <motion.div style={card} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.05, ease: [0.23, 1, 0.32, 1] }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
        <TrendUpMark size={14} color="#94a3b8" />
        <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--ink-tertiary)", margin: 0 }}>SLA Status</p>
      </div>
      <div style={{ marginBottom: 14 }}><StatusPill label={data.sla_status} type={type} /></div>
      <MetricRow label="First response" value={data.sla_first_response_minutes != null ? `${data.sla_first_response_minutes} min` : "No open tickets"} />
      <MetricRow label="Open tickets" value={data.open_tickets} />
      <p style={{ fontSize: 10, color: "var(--ink-tertiary)", marginTop: 10 }}>Target: 15 min warn · 60 min critical</p>
    </motion.div>
  );
}

function AgentsCard({ data }: { data: CcwHealth }) {
  return (
    <motion.div style={card} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.1, ease: [0.23, 1, 0.32, 1] }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
        <UsersMark size={14} color="#94a3b8" />
        <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--ink-tertiary)", margin: 0 }}>AI Agent Activity</p>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 14 }}>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 32, fontWeight: 700, color: "#f8fafc", lineHeight: 1 }}>{data.agents_active}</span>
        <span style={{ fontSize: 13, color: "var(--ink-tertiary)" }}>agents active</span>
      </div>
      <MetricRow label="Last action" value={data.last_agent_action ?? "—"} />
      <MetricRow label="Last active" value={formatRelativeTime(data.last_agent_at)} />
      <div style={{ marginTop: 12 }}>
        <span style={{ display: "inline-block", padding: "3px 10px", borderRadius: 20, background: "rgba(29,78,216,0.1)", border: "1px solid rgba(29,78,216,0.2)", fontSize: 10, fontWeight: 700, color: "var(--red-400)", letterSpacing: "0.04em" }}>Powered by Pi-CEO</span>
      </div>
    </motion.div>
  );
}

function CampaignsCard({ data }: { data: CcwHealth }) {
  const openRate = data.avg_open_rate_pct;
  const isGood = openRate != null && openRate >= 30;
  return (
    <motion.div style={card} initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: 0.3, delay: 0.15, ease: [0.23, 1, 0.32, 1] }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 14 }}>
        <BarChartMark size={14} color="#94a3b8" />
        <p style={{ fontSize: 10, fontWeight: 700, letterSpacing: "0.08em", textTransform: "uppercase", color: "var(--ink-tertiary)", margin: 0 }}>Synthex Campaigns</p>
      </div>
      <div style={{ display: "flex", alignItems: "baseline", gap: 6, marginBottom: 14 }}>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 32, fontWeight: 700, color: isGood ? "#16a34a" : "#f8fafc", lineHeight: 1 }}>
          {openRate != null ? `${openRate.toFixed(1)}%` : "—"}
        </span>
        <span style={{ fontSize: 13, color: "var(--ink-tertiary)" }}>avg open rate</span>
      </div>
      <MetricRow label="Active campaigns" value={data.active_campaigns} />
      <MetricRow label="Last sent" value={formatDate(data.last_campaign_sent)} />
      {isGood && <p style={{ fontSize: 12, fontWeight: 600, color: "#16a34a", marginTop: 10 }}>{openRate!.toFixed(1)}% open rate — 2× industry average</p>}
    </motion.div>
  );
}

// ── Main page ─────────────────────────────────────────────────────────────────

export default function CcwPortal() {
  const router = useRouter();
  const [health, setHealth] = useState<CcwHealth | null>(null);
  const [loadingAuth, setLoadingAuth] = useState(true);
  const [loadingData, setLoadingData] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    supabaseClient.auth.getSession().then(({ data: { session } }) => {
      if (!session) { router.push("/login"); return; }
      setLoadingAuth(false);
    });
  }, [router]);

  const fetchHealth = useCallback(async () => {
    setLoadingData(true); setError(null);
    try {
      const res = await fetch("/api/clients/ccw/health", { cache: "no-store" });
      if (!res.ok) throw new Error(`API error: ${res.status}`);
      setHealth(await res.json());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load data");
    } finally {
      setLoadingData(false);
    }
  }, []);

  useEffect(() => { if (!loadingAuth) fetchHealth(); }, [loadingAuth, fetchHealth]);

  if (loadingAuth) {
    return (
      <div style={{ minHeight: "100vh", background: "var(--canvas)", display: "flex", alignItems: "center", justifyContent: "center" }}>
        <p style={{ color: "var(--ink-tertiary)", fontSize: 14 }}>Authenticating&hellip;</p>
      </div>
    );
  }

  return (
    <div style={{ minHeight: "100vh", background: "var(--canvas)", color: "#f8fafc", ["--brand-primary" as string]: BRAND_PRIMARY_DEFAULT }}>

      {/* Portal header — brand-primary accent confined to header only */}
      <header style={{ background: "var(--surface-1)", borderBottom: "1px solid #27272a", padding: "0 24px" }}>
        {/* Brand accent bar at very top */}
        <div style={{ height: 3, background: "var(--brand-primary)", marginLeft: -24, marginRight: -24 }} />
        <div style={{ maxWidth: 1100, margin: "0 auto", height: 60, display: "flex", alignItems: "center", justifyContent: "space-between" }}>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            <div style={{ width: 36, height: 36, borderRadius: 8, background: "var(--brand-primary)", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: 12, color: "#fff", flexShrink: 0 }}>CCW</div>
            <div>
              <div style={{ fontSize: 14, fontWeight: 700, color: "#f8fafc", letterSpacing: "-0.02em" }}>Carpet Cleaners Warehouse</div>
              <div style={{ fontSize: 10, color: "var(--ink-tertiary)", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase" }}>Business Intelligence Portal</div>
            </div>
          </div>
          <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
            {health && (
              <span style={{ fontSize: 11, fontFamily: "var(--font-mono)", color: "var(--ink-tertiary)" }}>
                Updated {formatRelativeTime(health.fetched_at)}
                {health.source === "pi_ceo_api" ? " · live" : " · cached"}
              </span>
            )}
            <button
              onClick={fetchHealth} disabled={loadingData}
              style={{ display: "flex", alignItems: "center", gap: 5, padding: "5px 10px", fontSize: 11, fontWeight: 500, borderRadius: 7, border: "1px solid #27272a", color: "#94a3b8", background: "transparent", cursor: loadingData ? "not-allowed" : "pointer", transition: "all 0.12s ease" }}
              onMouseEnter={e => { if (!loadingData) { (e.currentTarget as HTMLButtonElement).style.background = "var(--surface-1)"; (e.currentTarget as HTMLButtonElement).style.color = "#f8fafc"; } }}
              onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "transparent"; (e.currentTarget as HTMLButtonElement).style.color = "#94a3b8"; }}
            >
              <RefreshMark size={11} className={loadingData ? "spin" : undefined} />
              {loadingData ? "Loading…" : "Refresh"}
            </button>
          </div>
        </div>
      </header>

      <main style={{ maxWidth: 1100, margin: "0 auto", padding: "32px 24px 48px" }}>

        {/* Page title */}
        <div style={{ marginBottom: 24 }}>
          <h1 style={{ fontSize: 22, fontWeight: 700, color: "#f8fafc", letterSpacing: "-0.02em", margin: 0 }}>Business Health Dashboard</h1>
          <p style={{ margin: 0, fontSize: 14, color: "var(--ink-tertiary)", marginTop: 4 }}>Real-time status for your CRM, SLA, AI agents, and marketing campaigns.</p>
        </div>

        {/* Error banner */}
        {error && (
          <div style={{ marginBottom: 20, padding: "12px 16px", borderRadius: 10, background: "rgba(220,38,38,0.08)", border: "1px solid rgba(220,38,38,0.25)", display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <span style={{ fontSize: 14, color: "#f87171" }}>{error}</span>
            <button onClick={fetchHealth} style={{ background: "var(--brand-primary)", color: "#fff", border: "none", borderRadius: 6, padding: "4px 12px", fontSize: 13, fontWeight: 600, cursor: "pointer" }}>Retry</button>
          </div>
        )}

        {/* 4 metric cards */}
        <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 16 }}>
          {loadingData || !health ? (
            <><SkeletonCard /><SkeletonCard /><SkeletonCard /><SkeletonCard /></>
          ) : (
            <><CrmCard data={health} /><SlaCard data={health} /><AgentsCard data={health} /><CampaignsCard data={health} /></>
          )}
        </div>

        {/* Footer */}
        <p style={{ marginTop: 32, fontSize: 12, color: "var(--ink-tertiary)", textAlign: "center" }}>
          Powered by Unite-Hub · Data refreshes every 60 seconds ·{" "}
          <a href="mailto:contact@unite-group.in" style={{ color: "var(--red-400)", textDecoration: "none" }}>contact@unite-group.in</a>
        </p>
      </main>
    </div>
  );
}
