"use client";
// app/page.tsx — cinematic landing page with inline login form
import { useState, useRef } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";
import Image from "next/image";

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
    <div className="fixed inset-0 flex flex-col items-center justify-center overflow-hidden">

      {/* ── Optimised hero image via next/image (LCP, lazy decode, blur-up) ── */}
      <Image
        src="/pi-ceo-hero.jpg"
        alt="Pi CEO — cinematic hero"
        fill
        priority
        quality={85}
        sizes="100vw"
        className="object-cover object-center"
        style={{ zIndex: 0 }}
      />

      {/* ── Gradient overlay ── */}
      <div
        className="absolute inset-0"
        style={{
          background: "linear-gradient(to bottom, rgba(10,10,10,0.50) 0%, rgba(10,10,10,0.72) 55%, rgba(10,10,10,0.93) 100%)",
          zIndex: 1,
        }}
      />

      {/* ── Content ── */}
      <div className="relative flex flex-col items-center text-center px-6" style={{ zIndex: 2 }}>

        {/* Orange π */}
        <span
          className="font-mono mb-3"
          style={{ color: "#f97316", fontSize: "18px", letterSpacing: "0.4em" }}
        >
          π
        </span>

        {/* PI CEO wordmark */}
        <h1
          className="font-sans font-bold leading-none"
          style={{
            fontSize: "clamp(72px, 14vw, 160px)",
            color: "#fafafa",
            letterSpacing: "0.06em",
            textShadow: "0 2px 40px rgba(0,0,0,0.8)",
          }}
        >
          PI CEO
        </h1>

        {/* Tagline */}
        <p
          className="font-sans font-semibold mt-2"
          style={{
            fontSize: "clamp(14px, 2.5vw, 22px)",
            color: "#fafafa",
            letterSpacing: "0.35em",
            textTransform: "uppercase",
            opacity: 0.9,
          }}
        >
          Solo DevOps Tool
        </p>

        {/* Powered by */}
        <p
          className="font-mono mt-3"
          style={{ fontSize: "10px", color: "#f97316", letterSpacing: "0.3em", textTransform: "uppercase", opacity: 0.85 }}
        >
          Powered by Claude Harness
        </p>

        {/* ── CTA / Login form ── */}
        {mode === "hero" ? (
          <button
            onClick={() => { setMode("login"); setTimeout(() => inputRef.current?.focus(), 50); }}
            className="mt-12 font-sans font-semibold tracking-widest transition-all hover:opacity-80 hover:scale-105 active:scale-95 rounded-md"
            style={{
              background: "#f97316",
              color: "#ffffff",
              padding: "14px 56px",
              fontSize: "13px",
              letterSpacing: "0.15em",
              border: "none",
              cursor: "pointer",
              boxShadow: "0 0 32px rgba(249,115,22,0.35)",
            }}
          >
            Enter ↗
          </button>
        ) : (
          <form
            onSubmit={handleLogin}
            className="mt-12 flex flex-col items-center gap-3 animate-fade-in"
            style={{ width: "280px" }}
          >
            <div className="relative w-full">
              <input
                ref={inputRef}
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={e => setPassword(e.target.value)}
                placeholder="Password"
                disabled={loading}
                className="font-sans w-full text-center rounded-md"
                style={{
                  background: "rgba(250,250,250,0.08)",
                  border: "1px solid rgba(249,115,22,0.6)",
                  color: "#fafafa",
                  padding: "12px 40px 12px 20px",
                  fontSize: "16px",
                  letterSpacing: "0.15em",
                  outline: "none",
                  width: "100%",
                  boxSizing: "border-box",
                  backdropFilter: "blur(8px)",
                }}
              />
              {/* Show/hide password toggle */}
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
                  color: "rgba(249,115,22,0.7)",
                  display: "flex",
                  alignItems: "center",
                }}
              >
                {showPassword ? (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M17.94 17.94A10.07 10.07 0 0112 20c-7 0-11-8-11-8a18.45 18.45 0 015.06-5.94"/>
                    <path d="M9.9 4.24A9.12 9.12 0 0112 4c7 0 11 8 11 8a18.5 18.5 0 01-2.16 3.19"/>
                    <line x1="1" y1="1" x2="23" y2="23"/>
                  </svg>
                ) : (
                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/>
                    <circle cx="12" cy="12" r="3"/>
                  </svg>
                )}
              </button>
            </div>

            {error && (
              <p className="font-sans text-sm" style={{ color: "#ef4444" }}>
                {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading || !password}
              className="font-sans font-semibold tracking-widest w-full transition-opacity hover:opacity-80 disabled:opacity-40 rounded-md"
              style={{
                background: "#f97316",
                color: "#ffffff",
                padding: "14px 0",
                fontSize: "13px",
                letterSpacing: "0.15em",
                border: "none",
                cursor: "pointer",
                boxShadow: "0 0 24px rgba(249,115,22,0.3)",
              }}
            >
              {loading ? "Authenticating…" : "Authenticate ↗"}
            </button>
          </form>
        )}

        {/* Footer tagline */}
        <p className="font-mono mt-8" style={{ fontSize: "9px", color: "#fafafa", opacity: 0.35, letterSpacing: "0.2em" }}>
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
