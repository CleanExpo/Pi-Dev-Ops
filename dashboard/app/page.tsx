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
    <main className="min-h-screen bg-pi-dark flex items-center justify-center relative overflow-hidden">
      {/* Background grid */}
      <div
        className="absolute inset-0 opacity-[0.03]"
        style={{
          backgroundImage:
            "linear-gradient(#E8751A 1px, transparent 1px), linear-gradient(90deg, #E8751A 1px, transparent 1px)",
          backgroundSize: "40px 40px",
        }}
      />

      {/* Orange ambient glow */}
      <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-[600px] h-[600px] bg-pi-orange/5 rounded-full blur-3xl pointer-events-none" />

      <div className="relative w-full max-w-sm mx-4 animate-slide-up">
        {/* Logo */}
        <div className="text-center mb-10">
          <div className="inline-flex items-center gap-2 mb-2">
            <span className="w-2 h-8 bg-pi-orange rounded-sm" />
            <h1 className="font-bebas text-6xl tracking-widest text-pi-cream">
              PI CEO
            </h1>
            <span className="w-2 h-8 bg-pi-orange rounded-sm" />
          </div>
          <p className="font-mono text-xs text-pi-muted tracking-widest uppercase">
            Solo DevOps Tool
          </p>
          <div className="mt-3 flex items-center justify-center gap-2 text-[10px] font-mono text-pi-muted">
            <span className="px-2 py-0.5 border border-pi-border rounded text-pi-orange/70">
              Opus 4.6
            </span>
            <span className="px-2 py-0.5 border border-pi-border rounded">
              Sonnet 4.6
            </span>
            <span className="px-2 py-0.5 border border-pi-border rounded">
              Haiku 4.5
            </span>
          </div>
        </div>

        {/* Card */}
        <div className="bg-pi-dark-2 border border-pi-border rounded-lg p-8 glow-orange">
          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label className="block font-mono text-xs text-pi-muted uppercase tracking-wider mb-2">
                Access Key
              </label>
              <input
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter TAO_PASSWORD"
                autoFocus
                className="w-full bg-pi-dark-3 border border-pi-border rounded px-4 py-3 font-mono text-sm text-pi-cream placeholder:text-pi-muted/40 transition-all duration-200 focus:border-pi-orange"
                disabled={loading}
              />
            </div>

            {error && (
              <p className="font-mono text-xs text-red-400 bg-red-400/10 border border-red-400/20 rounded px-3 py-2">
                ✗ {error}
              </p>
            )}

            <button
              type="submit"
              disabled={loading || !password}
              className="w-full bg-pi-orange text-pi-dark font-barlow font-semibold text-sm tracking-wider uppercase py-3 rounded transition-all duration-200 hover:bg-pi-orange/90 disabled:opacity-40 disabled:cursor-not-allowed active:scale-[0.99]"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <span className="inline-block w-3 h-3 border-2 border-pi-dark/40 border-t-pi-dark rounded-full animate-spin" />
                  Authenticating...
                </span>
              ) : (
                "Enter Dashboard →"
              )}
            </button>
          </form>
        </div>

        {/* Footer */}
        <p className="text-center font-mono text-[10px] text-pi-muted/40 mt-6">
          Connects to{" "}
          <span className="text-pi-orange/60">
            {process.env.NEXT_PUBLIC_API_URL ?? "http://127.0.0.1:7777"}
          </span>
        </p>
      </div>
    </main>
  );
}
