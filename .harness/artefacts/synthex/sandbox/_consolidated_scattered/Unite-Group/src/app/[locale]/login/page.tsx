"use client";

import { useState, useEffect } from "react";
import Link from 'next/link';
import { useParams, useRouter } from "next/navigation";
import { supabaseClient } from "@/lib/supabase/client";
import {
  SpotlightCard,
  SpotlightCardContent,
} from '@/components/ui/spotlight-card';

// Live clock for telemetry panel
function Clock() {
  const [time, setTime] = useState("");
  useEffect(() => {
    const tick = () => setTime(new Date().toLocaleTimeString("en-AU", { hour12: false, timeZone: "Australia/Brisbane" }));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, []);
  return <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--ink-tertiary)", letterSpacing: "0.1em" }}>{time} AEST</span>;
}

const BUSINESSES = [
  { name: "SYNTHEX",       health: 50,  arr: null,    status: "LIVE"  },
  { name: "RESTOREASSIST", health: 85,  arr: null,    status: "LIVE"  },
  { name: "CCW-CRM",       health: 78,  arr: 33000,   status: "LIVE"  },
  { name: "DR PLATFORM",   health: 71,  arr: null,    status: "LIVE"  },
  { name: "NRPG",          health: 50,  arr: null,    status: "BUILD" },
  { name: "CARSI",         health: 65,  arr: null,    status: "LIVE"  },
];

function HealthBar({ value }: { value: number }) {
  const color = value >= 80 ? "#22c55e" : value >= 60 ? "#f59e0b" : "#ef4444";
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <div style={{ flex: 1, height: 2, background: "#1a1a1d", position: "relative" }}>
        <div style={{ position: "absolute", left: 0, top: 0, height: "100%", width: `${value}%`, background: color, transition: "width 1s ease" }} />
      </div>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color, width: 28, textAlign: "right" }}>{value}</span>
    </div>
  );
}

export default function LoginPage() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mounted, setMounted] = useState(false);
  const router = useRouter();
  // Preserve the active locale on post-login redirect — a /fr/login submitter
  // should land on /fr/command-center, not get bounced to /en/.
  const params = useParams<{ locale?: string }>();
  const locale = typeof params.locale === 'string' ? params.locale : 'en';

  useEffect(() => { setMounted(true); }, []);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      const { error } = await supabaseClient.auth.signInWithPassword({ email, password });
      if (error) throw error;
      router.push(`/${locale}/command-center`);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Authentication failed");
    } finally {
      setLoading(false);
    }
  };

  const totalARR = BUSINESSES.reduce((s, b) => s + (b.arr || 0), 0);

  return (
    <>
      <style>{`
        @keyframes scan {
          0% { transform: translateY(-100%); }
          100% { transform: translateY(100vh); }
        }
        @keyframes blink {
          0%, 100% { opacity: 1; }
          50% { opacity: 0; }
        }
        @keyframes pulse-amber {
          0%, 100% { box-shadow: 0 0 0 0 rgba(245,158,11,0.4); }
          50% { box-shadow: 0 0 0 6px rgba(245,158,11,0); }
        }
        .scan-line {
          position: absolute; left: 0; right: 0; height: 1px;
          background: linear-gradient(90deg, transparent, rgba(245,158,11,0.15), transparent);
          animation: scan 4s linear infinite;
          pointer-events: none;
        }
        .cursor { animation: blink 1.2s step-end infinite; }
        .amber-pulse { animation: pulse-amber 2.5s ease-in-out infinite; }
        @media (max-width: 900px) {
          .telemetry-panel { display: none !important; }
          .form-panel { border-left: none !important; }
        }
      `}</style>

      <div style={{ minHeight: "100vh", display: "flex", background: "#08080a", fontFamily: "var(--font-display, system-ui)" }}>

        {/* ── LEFT: MISSION TELEMETRY ──────────────────────────────────────── */}
        <div className="telemetry-panel" style={{
          width: 480, flexShrink: 0, display: "flex", flexDirection: "column",
          padding: "32px 36px", background: "#08080a",
          borderRight: "1px solid rgba(245,158,11,0.12)",
          position: "relative", overflow: "hidden",
        }}>
          {/* Subtle grid overlay */}
          <div style={{
            position: "absolute", inset: 0, opacity: 0.03, pointerEvents: "none",
            backgroundImage: "linear-gradient(#f59e0b 1px, transparent 1px), linear-gradient(90deg, #f59e0b 1px, transparent 1px)",
            backgroundSize: "32px 32px",
          }} />
          {/* Scan line animation */}
          <div className="scan-line" />

          {/* Header */}
          <div style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", marginBottom: 48 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
              <img src="/logo-mark.svg" width={36} height={36} alt="Unite Group" style={{ opacity: 0.95 }} />
              <div>
                <div style={{ fontSize: 13, fontWeight: 700, color: "#f0f0f2", letterSpacing: "0.06em", textTransform: "uppercase" }}>
                  Unite Group
                </div>
                <div style={{ display: "flex", alignItems: "center", gap: 5, marginTop: 2 }}>
                  <span className="amber-pulse" style={{ width: 5, height: 5, borderRadius: "50%", background: "#f59e0b", display: "inline-block" }} />
                  <span style={{ fontSize: 9, color: "#f59e0b", fontWeight: 600, letterSpacing: "0.15em", textTransform: "uppercase", fontFamily: "var(--font-mono)" }}>
                    EMPIRE / CLASSIFIED
                  </span>
                </div>
              </div>
            </div>
            <Clock />
          </div>

          {/* Large empire identifier */}
          <div style={{ marginBottom: 40 }}>
            <div style={{
              fontSize: 68, fontWeight: 800, color: "#f0f0f2",
              letterSpacing: "-0.04em", lineHeight: 0.9,
              textTransform: "uppercase",
            }}>
              EMPIRE<br />
              <span style={{ color: "#f59e0b" }}>CMD</span><br />
              CTR
            </div>
            <div style={{
              marginTop: 12, fontFamily: "var(--font-mono)", fontSize: 10,
              color: "var(--ink-tertiary)", letterSpacing: "0.15em",
              borderLeft: "2px solid #f59e0b", paddingLeft: 10,
            }}>
              6 BUSINESSES · PI-CEO SWARM · 100% AUTONOMY<br />
              AUTH REQUIRED · ACCESS LOGGED
            </div>
          </div>

          {/* Telemetry: business health */}
          <div style={{ flex: 1 }}>
            <div style={{
              fontSize: 9, fontWeight: 600, letterSpacing: "0.2em",
              textTransform: "uppercase", color: "var(--ink-tertiary)",
              fontFamily: "var(--font-mono)", marginBottom: 12,
              display: "flex", alignItems: "center", gap: 8,
            }}>
              <span style={{ flex: 1, height: 1, background: "#1a1a1d", display: "inline-block" }} />
              PORTFOLIO TELEMETRY
              <span style={{ flex: 1, height: 1, background: "#1a1a1d", display: "inline-block" }} />
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {BUSINESSES.map(biz => (
                <div key={biz.name} style={{ display: "grid", gridTemplateColumns: "110px 1fr 44px", gap: 10, alignItems: "center" }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
                    <span style={{
                      fontSize: 8, fontWeight: 600, fontFamily: "var(--font-mono)",
                      letterSpacing: "0.05em", color: biz.status === "LIVE" ? "#22c55e" : "#f59e0b",
                      padding: "1px 5px", border: `1px solid ${biz.status === "LIVE" ? "#166534" : "#78350f"}`,
                      borderRadius: 2,
                    }}>{biz.status}</span>
                  </div>
                  <HealthBar value={biz.health} />
                  <div style={{ textAlign: "right" }}>
                    {biz.arr ? (
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "#22c55e" }}>
                        ${(biz.arr / 1000).toFixed(0)}K
                      </span>
                    ) : (
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "#27272a" }}>—</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>

          {/* Footer strip */}
          <div style={{
            marginTop: 32, paddingTop: 16,
            borderTop: "1px solid #1a1a1d",
            display: "flex", justifyContent: "space-between", alignItems: "center",
          }}>
            <div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--ink-tertiary)", letterSpacing: "0.1em" }}>TOTAL ARR</div>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 18, fontWeight: 700, color: "#22c55e", letterSpacing: "-0.02em" }}>
                ${(totalARR / 1000).toFixed(0)}K<span style={{ fontSize: 10, color: "var(--ink-tertiary)" }}>/yr</span>
              </div>
            </div>
            <div style={{ textAlign: "right" }}>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--ink-tertiary)", letterSpacing: "0.1em" }}>SWARM STATUS</div>
              <div style={{ display: "flex", alignItems: "center", gap: 5, justifyContent: "flex-end" }}>
                <span style={{ width: 4, height: 4, borderRadius: "50%", background: "#22c55e", display: "inline-block" }} />
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "#22c55e" }}>NOMINAL</span>
              </div>
            </div>
          </div>
        </div>

        {/* ── RIGHT: AUTH PANEL ────────────────────────────────────────────── */}
        <div className="form-panel" style={{
          flex: 1, display: "flex", flexDirection: "column",
          alignItems: "center", justifyContent: "center",
          padding: "40px 32px",
          background: "#08080a",
          borderLeft: "1px solid #1a1a1d",
          position: "relative",
        }}>

          {/* Corner decorations */}
          {[
            { top: 20, left: 20, borderTop: "1px solid #2a2a2e", borderLeft: "1px solid #2a2a2e" },
            { top: 20, right: 20, borderTop: "1px solid #2a2a2e", borderRight: "1px solid #2a2a2e" },
            { bottom: 20, left: 20, borderBottom: "1px solid #2a2a2e", borderLeft: "1px solid #2a2a2e" },
            { bottom: 20, right: 20, borderBottom: "1px solid #2a2a2e", borderRight: "1px solid #2a2a2e" },
          ].map((s, i) => (
            <div key={i} style={{ position: "absolute", width: 20, height: 20, ...s }} />
          ))}

          <SpotlightCard
            spotlightColor="rgba(179, 0, 0, 0.30)"
            borderRadius={12}
            style={{ width: "100%", maxWidth: 340 }}
          >
            <SpotlightCardContent>

            {/* Auth header */}
            <div style={{ marginBottom: 36 }}>
              <div style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--ink-tertiary)", letterSpacing: "0.2em", marginBottom: 8 }}>
                {'// SECURE ACCESS TERMINAL'}
              </div>
              <h2 style={{
                fontSize: 28, fontWeight: 800, color: "#f0f0f2",
                letterSpacing: "-0.03em", margin: 0, textTransform: "uppercase",
                lineHeight: 1.1,
              }}>
                AUTHENTICATE
                <span className="cursor" style={{ color: "#f59e0b", marginLeft: 2 }}>_</span>
              </h2>
              <p style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--ink-tertiary)", margin: "8px 0 0", letterSpacing: "0.05em" }}>
                AUTHORISED PERSONNEL ONLY
              </p>
            </div>

            {/* Error */}
            {error && (
              <div style={{
                marginBottom: 16, padding: "10px 14px",
                border: "1px solid rgba(239,68,68,0.3)",
                background: "rgba(239,68,68,0.06)",
                borderRadius: 2,
                fontFamily: "var(--font-mono)", fontSize: 11, color: "#ef4444",
              }}>
                ERR: {error}
              </div>
            )}

            {/* Form */}
            <form onSubmit={handleLogin} style={{ display: "flex", flexDirection: "column", gap: 0 }}>

              {/* Email field */}
              <div style={{ marginBottom: 16 }}>
                <div style={{
                  fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--ink-tertiary)",
                  letterSpacing: "0.2em", marginBottom: 6, textTransform: "uppercase",
                }}>
                  &gt; EMAIL IDENTIFIER
                </div>
                <input
                  type="email" required autoComplete="email"
                  value={email} onChange={e => setEmail(e.target.value)}
                  placeholder="user@unite-group.in"
                  style={{
                    width: "100%", padding: "11px 14px",
                    fontSize: 13, fontFamily: "var(--font-mono)",
                    background: "#0d0d10",
                    border: "1px solid #27272a",
                    borderRadius: 2, color: "#f0f0f2",
                    outline: "none", boxSizing: "border-box",
                    transition: "border-color 0.15s",
                    letterSpacing: "0.02em",
                  }}
                  onFocus={e => (e.target.style.borderColor = "#f59e0b")}
                  onBlur={e => (e.target.style.borderColor = "#27272a")}
                />
              </div>

              {/* Password field */}
              <div style={{ marginBottom: 28 }}>
                <div style={{
                  fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--ink-tertiary)",
                  letterSpacing: "0.2em", marginBottom: 6, textTransform: "uppercase",
                  display: "flex", justifyContent: "space-between",
                }}>
                  <span>&gt; ACCESS CODE</span>
                  <Link href={`/${locale}/reset-password`} style={{ color: "#f59e0b", textDecoration: "none" }}>RESET</Link>
                </div>
                <input
                  type="password" required autoComplete="current-password"
                  value={password} onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••••••"
                  style={{
                    width: "100%", padding: "11px 14px",
                    fontSize: 14, fontFamily: "var(--font-mono)",
                    background: "#0d0d10",
                    border: "1px solid #27272a",
                    borderRadius: 2, color: "#f0f0f2",
                    outline: "none", boxSizing: "border-box",
                    transition: "border-color 0.15s",
                    letterSpacing: "0.1em",
                  }}
                  onFocus={e => (e.target.style.borderColor = "#f59e0b")}
                  onBlur={e => (e.target.style.borderColor = "#27272a")}
                />
              </div>

              {/* Submit */}
              <button
                type="submit" disabled={loading}
                style={{
                  width: "100%", padding: "13px 0",
                  fontSize: 12, fontWeight: 700,
                  fontFamily: "var(--font-mono)",
                  letterSpacing: "0.2em", textTransform: "uppercase",
                  background: loading ? "#1a1a1d" : "#f59e0b",
                  color: loading ? "#3f3f46" : "#08080a",
                  border: "none", borderRadius: 2,
                  cursor: loading ? "not-allowed" : "pointer",
                  transition: "all 0.15s ease",
                }}
                onMouseEnter={e => { if (!loading) (e.currentTarget as HTMLButtonElement).style.background = "#fbbf24"; }}
                onMouseLeave={e => { if (!loading) (e.currentTarget as HTMLButtonElement).style.background = "#f59e0b"; }}
              >
                {loading ? "VERIFYING..." : "GRANT ACCESS →"}
              </button>
            </form>

            {/* Google Sign-In */}
            <div style={{ marginTop: 20, paddingTop: 16, borderTop: "1px solid #27272a" }}>
              <button
                type="button"
                onClick={() => supabaseClient.auth.signInWithOAuth({
                  provider: 'google',
                  options: { redirectTo: `${window.location.origin}/en/ceo` }
                })}
                style={{
                  width: "100%", padding: "10px 0", fontSize: 12, fontWeight: 600,
                  fontFamily: "var(--font-mono)", letterSpacing: "0.1em",
                  textTransform: "uppercase",
                  background: "transparent",
                  border: "1px solid #27272a", borderRadius: 2,
                  color: "#a1a1aa", cursor: "pointer", transition: "all 0.15s",
                  display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                }}
                onMouseEnter={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = "#3f3f46"; (e.currentTarget as HTMLButtonElement).style.color = "#fafafa"; }}
                onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.borderColor = "#27272a"; (e.currentTarget as HTMLButtonElement).style.color = "#a1a1aa"; }}
              >
                <svg width="14" height="14" viewBox="0 0 24 24"><path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/><path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/><path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/><path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/></svg>
                CONTINUE WITH GOOGLE
              </button>
            </div>

            {/* Status bar */}
            <div style={{
              marginTop: 32, paddingTop: 16,
              borderTop: "1px solid #1a1a1d",
              display: "flex", justifyContent: "space-between", alignItems: "center",
            }}>
              <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
                <span style={{ width: 4, height: 4, borderRadius: "50%", background: "#22c55e", display: "inline-block" }} />
                <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--ink-tertiary)", letterSpacing: "0.1em" }}>
                  ALL SYSTEMS NOMINAL
                </span>
              </div>
              {mounted && <Clock />}
            </div>

            </SpotlightCardContent>
          </SpotlightCard>
        </div>
      </div>
    </>
  );
}
