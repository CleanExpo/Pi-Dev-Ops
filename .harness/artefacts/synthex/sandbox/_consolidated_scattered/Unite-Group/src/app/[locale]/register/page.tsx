// @ts-nocheck
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { supabaseClient } from "@/lib/supabase/client";
import Link from "next/link";
import { LoaderMark, CheckCircleMark } from "@/components/ui/marks";
import { motion } from "framer-motion";
import {
  SpotlightCard,
  SpotlightCardHeader,
  SpotlightCardTitle,
  SpotlightCardContent,
} from "@/components/ui/spotlight-card";

const PORTFOLIO = [
  { name: "Synthex",        status: "operational", color: "#16a34a" },
  { name: "RestoreAssist",  status: "building",    color: "var(--red-500)" },
  { name: "CCW",            status: "operational", color: "#16a34a" },
  { name: "CARSI",          status: "building",    color: "var(--red-500)" },
  { name: "DR Platform",    status: "building",    color: "var(--red-500)" },
  { name: "NRPG",           status: "building",    color: "var(--red-500)" },
];

export default function Register() {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const router = useRouter();

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirmPassword) { setError("Passwords do not match"); return; }
    if (password.length < 6) { setError("Password must be at least 6 characters"); return; }
    setLoading(true);
    setError(null);
    try {
      const { error: signUpError, data } = await supabaseClient.auth.signUp({
        email, password,
        options: { data: { first_name: firstName, last_name: lastName } },
      });
      if (signUpError) throw signUpError;
      if (data.user) {
        const conversion_copy_variant = Math.random() < 0.5 ? "win" : "control";
        await supabaseClient.from("profiles").insert([{
          id: data.user.id, first_name: firstName, last_name: lastName,
          role: "user", conversion_copy_variant,
        }]);
      }
      setSuccess(true);
      setTimeout(() => router.push("/login"), 3000);
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred during registration");
    } finally {
      setLoading(false);
    }
  };

  const inputStyle: React.CSSProperties = {
    width: "100%",
    borderRadius: 10,
    padding: "10px 14px",
    fontSize: 14,
    color: "var(--ink-primary)",
    background: "var(--surface-1)",
    border: "1px solid #27272a",
    outline: "none",
    boxSizing: "border-box",
    transition: "border-color 0.12s ease",
  };

  return (
    <div style={{ minHeight: "100vh", display: "flex", background: "var(--canvas)" }}>

      {/* Left panel */}
      <motion.div
        initial={{ opacity: 0, y: 8 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: [0.23, 1, 0.32, 1] }}
        style={{ width: "45%", background: "var(--surface-1)", backgroundImage: "linear-gradient(180deg, rgba(255,255,255,0.025) 0%, rgba(255,255,255,0) 50%)", borderRight: "1px solid #27272a", padding: "48px 40px", display: "flex", flexDirection: "column", gap: 32 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <div style={{ width: 32, height: 32, borderRadius: 8, background: "var(--red-500)", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 800, fontSize: 14, color: "#fff" }}>U</div>
          <div>
            <div style={{ fontSize: 14, fontWeight: 700, color: "var(--ink-primary)", letterSpacing: "-0.02em" }}>Unite Group</div>
            <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
              <span style={{ width: 5, height: 5, borderRadius: "50%", background: "#fbbf24", display: "inline-block" }} />
              <span style={{ fontSize: 9, color: "#fbbf24", fontWeight: 600, letterSpacing: "0.06em", textTransform: "uppercase" }}>Empire</span>
            </div>
          </div>
        </div>

        <div>
          <h1 style={{ fontSize: 28, fontWeight: 700, color: "var(--ink-primary)", letterSpacing: "-0.03em", lineHeight: 1.15, margin: 0 }}>Join the Empire</h1>
          <p style={{ fontSize: 14, color: "#52525b", marginTop: 10 }}>6 portfolio businesses. 200+ people. One command center.</p>
        </div>

        <div>
          <p style={{ fontSize: 10, fontWeight: 600, letterSpacing: "0.1em", textTransform: "uppercase", color: "#52525b", marginBottom: 10 }}>Portfolio Status</p>
          <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
            {PORTFOLIO.map((biz) => (
              <div key={biz.name} style={{ display: "flex", alignItems: "center", justifyContent: "space-between", padding: "8px 12px", background: "var(--surface-1)", border: "1px solid #27272a", borderRadius: 8 }}>
                <span style={{ fontSize: 13, color: "#94a3b8" }}>{biz.name}</span>
                <div style={{ display: "flex", alignItems: "center", gap: 5 }}>
                  <span className="status-dot" style={{ width: 5, height: 5, background: biz.color, color: biz.color }} />
                  <span style={{ fontSize: 9, fontWeight: 600, letterSpacing: "0.05em", textTransform: "uppercase", color: biz.color }}>{biz.status}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </motion.div>

      {/* Right form panel */}
      <div style={{ flex: 1, display: "flex", alignItems: "center", justifyContent: "center", padding: 40 }}>
        <SpotlightCard
          spotlightColor="rgba(179, 0, 0, 0.30)"
          borderRadius={12}
          style={{ width: "100%", maxWidth: 440 }}
        >
          <SpotlightCardHeader>
            <SpotlightCardTitle style={{ fontSize: 22, color: "var(--ink-primary)", letterSpacing: "-0.02em" }}>Create your account</SpotlightCardTitle>
            <p style={{ fontSize: 14, color: "#52525b", marginTop: 6 }}>Enter your details to request access.</p>
          </SpotlightCardHeader>
          <SpotlightCardContent>

          {error && (
            <div style={{ marginBottom: 16, padding: "12px 14px", borderRadius: 10, background: "rgba(220,38,38,0.08)", border: "1px solid rgba(220,38,38,0.25)" }}>
              <p style={{ fontSize: 13, color: "#f87171", margin: 0 }}>{error}</p>
            </div>
          )}

          {success ? (
            <div style={{ textAlign: "center", padding: "32px 0" }}>
              <CheckCircleMark size={40} color="#16a34a" className="mx-auto mb-3" />
              <h3 style={{ fontSize: 18, fontWeight: 600, color: "var(--ink-primary)", margin: "0 0 8px" }}>Account created</h3>
              <p style={{ fontSize: 14, color: "#52525b" }}>Check your email for verification. Redirecting to sign in&hellip;</p>
            </div>
          ) : (
            <form onSubmit={handleRegister} style={{ display: "flex", flexDirection: "column", gap: 14 }}>
              <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                <div>
                  <label style={{ display: "block", fontSize: 13, fontWeight: 500, color: "#94a3b8", marginBottom: 6 }}>First name</label>
                  <input
                    type="text" required value={firstName} onChange={e => setFirstName(e.target.value)}
                    placeholder="Phill" style={inputStyle}
                    onFocus={e => (e.target.style.borderColor = "var(--red-500)")}
                    onBlur={e => (e.target.style.borderColor = "var(--border-default)")}
                  />
                </div>
                <div>
                  <label style={{ display: "block", fontSize: 13, fontWeight: 500, color: "#94a3b8", marginBottom: 6 }}>Last name</label>
                  <input
                    type="text" required value={lastName} onChange={e => setLastName(e.target.value)}
                    placeholder="McGurk" style={inputStyle}
                    onFocus={e => (e.target.style.borderColor = "var(--red-500)")}
                    onBlur={e => (e.target.style.borderColor = "var(--border-default)")}
                  />
                </div>
              </div>

              <div>
                <label style={{ display: "block", fontSize: 13, fontWeight: 500, color: "#94a3b8", marginBottom: 6 }}>Email address</label>
                <input
                  type="email" required value={email} onChange={e => setEmail(e.target.value)}
                  placeholder="you@example.com" style={inputStyle}
                  onFocus={e => (e.target.style.borderColor = "var(--red-500)")}
                  onBlur={e => (e.target.style.borderColor = "var(--border-default)")}
                />
              </div>

              <div>
                <label style={{ display: "block", fontSize: 13, fontWeight: 500, color: "#94a3b8", marginBottom: 6 }}>Password</label>
                <input
                  type="password" required minLength={6} value={password} onChange={e => setPassword(e.target.value)}
                  placeholder="••••••••" style={inputStyle}
                  onFocus={e => (e.target.style.borderColor = "var(--red-500)")}
                  onBlur={e => (e.target.style.borderColor = "var(--border-default)")}
                />
                <p style={{ fontSize: 11, color: "#52525b", marginTop: 5 }}>Minimum 6 characters</p>
              </div>

              <div>
                <label style={{ display: "block", fontSize: 13, fontWeight: 500, color: "#94a3b8", marginBottom: 6 }}>Confirm password</label>
                <input
                  type="password" required value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)}
                  placeholder="••••••••" style={inputStyle}
                  onFocus={e => (e.target.style.borderColor = "var(--red-500)")}
                  onBlur={e => (e.target.style.borderColor = "var(--border-default)")}
                />
              </div>

              <button
                type="submit" disabled={loading}
                style={{
                  width: "100%", padding: "11px 0", borderRadius: 10, fontSize: 14, fontWeight: 600, color: "#fff",
                  background: "var(--red-500)", border: "none", cursor: loading ? "not-allowed" : "pointer",
                  opacity: loading ? 0.6 : 1, display: "flex", alignItems: "center", justifyContent: "center", gap: 8,
                  transition: "background 0.16s ease",
                }}
                onMouseEnter={e => { if (!loading) (e.currentTarget as HTMLButtonElement).style.background = "var(--red-400)"; }}
                onMouseLeave={e => { (e.currentTarget as HTMLButtonElement).style.background = "var(--red-500)"; }}
                onMouseDown={e => { (e.currentTarget as HTMLButtonElement).style.transform = "scale(0.97)"; }}
                onMouseUp={e => { (e.currentTarget as HTMLButtonElement).style.transform = "scale(1)"; }}
              >
                {loading ? <><LoaderMark size={15} className="animate-spin" />Creating account…</> : "Create account"}
              </button>
            </form>
          )}

          <p style={{ fontSize: 13, color: "#52525b", textAlign: "center", marginTop: 24 }}>
            Already have an account?{" "}
            <Link href="/login" style={{ color: "var(--red-400)", textDecoration: "none", fontWeight: 500 }}>Sign in</Link>
          </p>
          </SpotlightCardContent>
        </SpotlightCard>
      </div>
    </div>
  );
}
