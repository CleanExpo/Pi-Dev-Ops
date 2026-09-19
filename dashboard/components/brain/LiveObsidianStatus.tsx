"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import { fetchProxyJSON } from "@/lib/pi-ceo-fetch";

type ObsidianHealth = {
  ok: boolean;
  vault_present: boolean;
  vault_writable: boolean;
  remote_configured: boolean;
  remote_host: string;
  rest_reachable: boolean;
  detail: string;
  checked_at: string;
};

export default function LiveObsidianStatus() {
  const [h, setH] = useState<ObsidianHealth | null>(null);
  const [err, setErr] = useState(false);
  const [loading, setLoading] = useState(true);
  const activeRequest = useRef<AbortController | null>(null);

  const load = useCallback(async () => {
    activeRequest.current?.abort();
    const request = new AbortController();
    activeRequest.current = request;
    const timeout = setTimeout(() => request.abort(), 10_000);
    setLoading(true);
    try {
      const data: unknown = await fetchProxyJSON("/api/health/obsidian", { cache: "no-store", signal: request.signal });
      if (!data || typeof data !== "object" || !("ok" in data) || typeof data.ok !== "boolean") {
        throw new Error("Probe response invalid");
      }
      const fields = data as Record<string, unknown>;
      if (activeRequest.current !== request) return;
      setH({
        ok: data.ok,
        vault_present: fields.vault_present === true,
        vault_writable: fields.vault_writable === true,
        remote_configured: fields.remote_configured === true,
        remote_host: typeof fields.remote_host === "string" ? fields.remote_host : "",
        rest_reachable: fields.rest_reachable === true,
        detail: typeof fields.detail === "string" ? fields.detail : "",
        checked_at: typeof fields.checked_at === "string" ? fields.checked_at : "",
      });
      setErr(false);
    } catch {
      if (activeRequest.current === request) { setH(null); setErr(true); }
    } finally {
      clearTimeout(timeout);
      if (activeRequest.current === request) { activeRequest.current = null; setLoading(false); }
    }
  }, []);

  useEffect(() => {
    void load();
    return () => { activeRequest.current?.abort(); activeRequest.current = null; };
  }, [load]);

  const ok = h?.ok === true;
  const checkedAt = h?.checked_at ? new Date(h.checked_at) : null;
  const bg = err
    ? "color-mix(in srgb, var(--text-dim) 22%, transparent)"
    : ok
      ? "color-mix(in srgb, var(--success) 18%, transparent)"
      : "color-mix(in srgb, var(--error) 18%, transparent)";
  const fg = err ? "var(--text-muted)" : ok ? "var(--success)" : "var(--error)";
  const label = loading ? "Checking…" : err ? "Probe unreachable" : ok ? "Connected" : "No connection";

  return (
    <section
      className="p-4 rounded-lg flex flex-col gap-2"
      style={{ background: "var(--panel)", border: "1px solid var(--border)" }}
    >
      <div className="flex items-center justify-between">
        <h2 className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
          Obsidian — live status
        </h2>
        <button
          type="button"
          onClick={() => void load()}
          disabled={loading}
          className="text-[11px] underline"
          style={{ color: "var(--accent)" }}
        >
          Re-check
        </button>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <span
          className="text-xs font-semibold uppercase tracking-wider px-2 py-0.5 rounded"
          style={{ background: bg, color: fg }}
        >
          {label}
        </span>
        {h && !err && !loading && (
          <span className="text-xs" style={{ color: "var(--text-muted)" }}>
            vault {h.vault_writable ? "writable ✓" : h.vault_present ? "present" : "—"}
            {" · "}REST{" "}
            {h.remote_configured ? (h.rest_reachable ? "reachable ✓" : "unreachable ✗") : "not configured"}
            {h.detail ? ` (${h.detail})` : ""}
          </span>
        )}
      </div>
      {checkedAt && Number.isFinite(checkedAt.getTime()) && !err && !loading && (
        <p className="text-[10px]" style={{ color: "var(--text-dim)" }}>
          checked {checkedAt.toLocaleTimeString()}
        </p>
      )}
    </section>
  );
}
