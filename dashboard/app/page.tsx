"use client";
// app/page.tsx — cinematic landing page with inline login form
import { useState, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

function LoginForm() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const redirect = searchParams.get("redirect") || "/dashboard";

  const [mode, setMode] = useState<"hero" | "login">("hero");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError("");
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password }),
      });
      if (res.ok) {
        router.push(redirect);
      } else {
        setError("Invalid password");
        setPassword("");
        inputRef.current?.focus();
      }
    } catch {
      setError("Server unreachable");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div
      className="fixed inset-0 flex flex-col items-center justify-center"
      style={{
        backgroundImage: "url(/pi-ceo-hero.jpg)",
        backgroundSize: "cover",
        backgroundPosition: "center",
        backgroundRepeat: "no-repeat",
      }}
    >
      <div
        className="absolute inset-0"
        style={{ background: "linear-gradient(to bottom, rgba(10,10,10,0.55) 0%, rgba(10,10,10,0.75) 60%, rgba(10,10,10,0.92) 100%)" }}
      />

      <div className="relative flex flex-col items-center text-center px-6">
        <span className="font-mono mb-3 tracking-widest" style={{ color: "#E8751A", fontSize: "18px", letterSpacing: "0.4em" }}>π</span>

        <h1
          className="font-display leading-none"
          style={{ fontSize: "clamp(72px, 14vw, 160px)", color: "#F0EDE8", letterSpacing: "0.06em", textShadow: "0 2px 40px rgba(0,0,0,0.8)" }}
        >
          PI CEO
        </h1>

        <p style={{ fontFamily: "'Barlow', sans-serif", fontWeight: 600, fontSize: "clamp(14px, 2.5vw, 22px)", color: "#F0EDE8", letterSpacing: "0.35em", marginTop: "8px", textTransform: "uppercase", opacity: 0.9 }}>
          Solo DevOps Tool
        </p>

        <p className="font-mono mt-3" style={{ fontSize: "10px", color: "#E8751A", letterSpacing: "0.3em", textTransform: "uppercase", opacity: 0.85 }}>
          Powered by Claude Harness
        </p>

        {mode === "hero" ? (
          <button
            onClick={() => { setMode("login"); setTimeout(() => inputRef.current?.focus(), 50); }}
            className="mt-12 font-mono font-bold tracking-widest transition-opacity hover:opacity-80"
            style={{ background: "#E8751A", color: "#FFFFFF", padding: "14px 56px", fontSize: "13px", letterSpacing: "0.25em", border: "none", cursor: "pointer" }}
          >
            ENTER ↗
          </button>
        ) : (
          <form onSubmit={handleLogin} className="mt-12 flex flex-col items-center gap-3" style={{ width: "280px" }}>
            <div className="relative w-full">
              <input
                ref={inputRef}
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="PASSWORD"
                disabled={loading}
                className="font-mono w-full text-center"
                style={{
                  background: "rgba(240,237,232,0.08)",
                  border: "1px solid rgba(232,117,26,0.6)",
                  color: "#F0EDE8",
                  padding: "12px 40px 12px 20px",
                  fontSize: "13px",
                  letterSpacing: "0.25em",
                  outline: "none",
                  width: "100%",
                  boxSizing: "border-box",
                }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(v => !v)}
                tabIndex={-1}
                aria-label={showPassword ? "Hide password" : "Show password"}
                style={{
                  position: "absolute",
                  right: "10px",
                  top: "50%",
                  transform: "translateY(-50%)",
                  background: "none",
                  border: "none",
                  cursor: "pointer",
                  padding: "4px",
                  color: "rgba(232,117,26,0.7)",
                  display: "flex",
                  alignItems: "center",
                }}
              >
                {showPassword ? (
                  /* Eye-off icon */
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/>
                    <path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/>
                    <line x1="1" y1="1" x2="23" y2="23"/>
                  </svg>
                ) : (
                  /* Eye icon */
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                    <circle cx="12" cy="12" r="3"/>
                  </svg>
                )}
              </button>
            </div>
            {error && (
              <p className="font-mono" style={{ color: "#F87171", fontSize: "11px", letterSpacing: "0.15em" }}>
                {error.toUpperCase()}
              </p>
            )}
            <button
              type="submit"
              disabled={loading || !password}
              className="font-mono font-bold tracking-widest w-full transition-opacity hover:opacity-80 disabled:opacity-40"
              style={{ background: "#E8751A", color: "#FFFFFF", padding: "14px 0", fontSize: "13px", letterSpacing: "0.25em", border: "none", cursor: "pointer" }}
            >
              {loading ? "AUTHENTICATING…" : "AUTHENTICATE ↗"}
            </button>
          </form>
        )}

        <p className="font-mono mt-8" style={{ fontSize: "9px", color: "#F0EDE8", opacity: 0.35, letterSpacing: "0.2em" }}>
          8 ANALYSIS PHASES · CLAUDE OPUS 4.6 · TAO FRAMEWORK
        </p>
      </div>
    </div>
  );
}

export default function LandingPage() {
  return (
    <Suspense>
      <LoginForm />
    </Suspense>
  );
}
