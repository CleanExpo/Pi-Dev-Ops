"use client";

import { useState, FormEvent } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";

export default function LoginPage() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);
  const router = useRouter();

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await api.login(password);
      router.push("/dashboard");
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Login failed");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="relative min-h-screen flex items-center justify-center overflow-hidden">

      {/* ── Hero image (full bleed) ── */}
      {/* eslint-disable-next-line @next/next/no-img-element */}
      <img
        src="/pi-ceo-hero.jpg"
        alt=""
        aria-hidden="true"
        className="absolute inset-0 w-full h-full object-cover object-center"
        style={{ filter: "brightness(0.55)" }}
      />

      {/* ── Overlay layers ── */}
      {/* Dark vignette around edges */}
      <div className="absolute inset-0 bg-gradient-to-b from-black/60 via-transparent to-black/80" />
      {/* Orange radial glow — mirrors the fire in the image */}
      <div
        className="absolute inset-0 pointer-events-none"
        style={{
          background:
            "radial-gradient(ellipse 70% 60% at 50% 40%, rgba(232,117,26,0.18) 0%, transparent 70%)",
        }}
      />
      {/* Bottom ground plane */}
      <div className="absolute bottom-0 left-0 right-0 h-48 bg-gradient-to-t from-black/90 to-transparent" />

      {/* ── Login card ── */}
      <div className="relative z-10 w-full max-w-sm mx-4">

        {/* Logo lockup */}
        <div className="text-center mb-8">
          <div className="flex items-center justify-center gap-1 mb-1">
            {/* π symbol in orange, matching the hero image logo */}
            <span
              className="font-bebas text-5xl leading-none"
              style={{ color: "#E8751A" }}
            >
              π
            </span>
            <span className="font-bebas text-6xl tracking-widest text-white leading-none">
              i CEO
            </span>
          </div>
          <p className="text-white/80 text-sm font-barlow font-medium tracking-widest uppercase">
            Solo DevOps Tool
          </p>
          <p className="text-white/40 text-xs font-barlow tracking-wider mt-0.5">
            Powered by Claude Harness
          </p>
        </div>

        {/* Tier badges */}
        <div className="flex items-center justify-center gap-2 mb-6 font-mono text-[10px]">
          <span
            className="px-2 py-0.5 rounded border"
            style={{
              color: "#E8751A",
              borderColor: "rgba(232,117,26,0.4)",
              backgroundColor: "rgba(232,117,26,0.1)",
            }}
          >
            Opus 4.6
          </span>
          <span className="px-2 py-0.5 rounded border border-white/20 text-white/50">
            Sonnet 4.6
          </span>
          <span className="px-2 py-0.5 rounded border border-white/20 text-white/50">
            Haiku 4.5
          </span>
        </div>

        {/* Card */}
        <div
          className="rounded-xl p-7 border"
          style={{
            background: "rgba(10,10,10,0.75)",
            backdropFilter: "blur(16px)",
            WebkitBackdropFilter: "blur(16px)",
            borderColor: "rgba(232,117,26,0.25)",
            boxShadow:
              "0 0 40px rgba(232,117,26,0.12), 0 20px 60px rgba(0,0,0,0.5)",
          }}
        >
          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block font-mono text-[10px] text-white/40 uppercase tracking-widest mb-2">
                Access Key
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter TAO_PASSWORD"
                autoFocus
                className="w-full rounded-lg px-4 py-3 font-mono text-sm text-white placeholder:text-white/25 transition-all duration-200 border"
                style={{
                  background: "rgba(255,255,255,0.05)",
                  borderColor: "rgba(255,255,255,0.12)",
                  outline: "none",
                }}
                onFocus={(e) => {
                  e.currentTarget.style.borderColor = "#E8751A";
                  e.currentTarget.style.boxShadow =
                    "0 0 0 1px rgba(232,117,26,0.4)";
                }}
                onBlur={(e) => {
                  e.currentTarget.style.borderColor =
                    "rgba(255,255,255,0.12)";
                  e.currentTarget.style.boxShadow = "none";
                }}
                disabled={loading}
              />
            </div>

            {error && (
              <p className="font-mono text-xs text-red-400 bg-red-500/10 border border-red-500/20 rounded-lg px-3 py-2">
                ✗ {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading || !password}
              className="w-full font-barlow font-bold text-sm tracking-widest uppercase py-3.5 rounded-lg transition-all duration-200 disabled:opacity-40 disabled:cursor-not-allowed active:scale-[0.99]"
              style={{
                background: loading || !password
                  ? "rgba(232,117,26,0.4)"
                  : "linear-gradient(135deg, #E8751A 0%, #FF9D4D 100%)",
                color: "#0A0A0A",
                boxShadow: loading || !password
                  ? "none"
                  : "0 4px 20px rgba(232,117,26,0.35)",
              }}
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span
                    className="inline-block w-3.5 h-3.5 border-2 border-black/30 border-t-black/80 rounded-full animate-spin"
                  />
                  Authenticating…
                </span>
              ) : (
                "Enter Dashboard →"
              )}
            </button>
          </form>
        </div>

        {/* Footer */}
        <p className="text-center font-mono text-[10px] text-white/25 mt-5">
          {process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:7777"}
        </p>
      </div>
    </main>
  );
}
