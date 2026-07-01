"use client";

import { useCallback, useState } from "react";

const API = "/api/pi-ceo/api/spec-pipeline";

type PipelineRow = {
  pipeline_id: string;
  status: string;
  proposal: string;
  updated_at?: string;
};

export default function SpecPipelinePanel() {
  const [proposal, setProposal] = useState("");
  const [dryRun, setDryRun] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastId, setLastId] = useState<string | null>(null);
  const [pipelines, setPipelines] = useState<PipelineRow[]>([]);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch(`${API}?limit=10`, { credentials: "include" });
      if (!r.ok) return;
      const data = await r.json();
      setPipelines(data.pipelines ?? []);
    } catch {
      /* ignore */
    }
  }, []);

  const run = async () => {
    if (proposal.trim().length < 10) {
      setError("Proposal must be at least 10 characters");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const r = await fetch(`${API}/run`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ proposal: proposal.trim(), dry_run: dryRun }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(data.detail ?? r.statusText);
      setLastId(data.pipeline_id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Run failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <section
      className="flex flex-col h-full min-h-0 p-4 gap-3"
      style={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8 }}
      aria-label="Machine spec pipeline"
    >
      <header className="flex items-center justify-between gap-2">
        <h2 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
          Spec Pipeline
        </h2>
        <button
          type="button"
          onClick={() => void refresh()}
          className="text-xs px-2 py-1 rounded"
          style={{ border: "1px solid var(--border)" }}
        >
          Refresh
        </button>
      </header>
      <p className="text-xs" style={{ color: "var(--text-muted)" }}>
        Judge 100 → STORM → SPM → Boardroom. Dry-run stops before build.
      </p>
      <textarea
        value={proposal}
        onChange={(e) => setProposal(e.target.value)}
        rows={4}
        placeholder="Proposal to judge and spec…"
        className="w-full text-sm p-2 rounded resize-y"
        style={{ background: "var(--background)", border: "1px solid var(--border)", color: "var(--text)" }}
      />
      <label className="flex items-center gap-2 text-xs" style={{ color: "var(--text-muted)" }}>
        <input type="checkbox" checked={dryRun} onChange={(e) => setDryRun(e.target.checked)} />
        Dry-run (no build / ship)
      </label>
      <button
        type="button"
        disabled={busy}
        onClick={() => void run()}
        className="text-sm px-3 py-2 rounded font-medium disabled:opacity-50"
        style={{ background: "var(--accent)", color: "var(--background)" }}
      >
        {busy ? "Running…" : "Run pipeline"}
      </button>
      {error && <p className="text-xs text-red-500">{error}</p>}
      {lastId && (
        <p className="text-xs" style={{ color: "var(--text-muted)" }}>
          Queued: <code>{lastId}</code> — artifacts in{" "}
          <code>.harness/spec-pipelines/{lastId}/</code>
        </p>
      )}
      <ul className="text-xs flex-1 overflow-auto space-y-1" style={{ color: "var(--text-muted)" }}>
        {pipelines.map((p) => (
          <li key={p.pipeline_id}>
            <span className="font-mono">{p.pipeline_id}</span> — {p.status}: {p.proposal}
          </li>
        ))}
      </ul>
    </section>
  );
}
