"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const API = "/api/pi-ceo/api/spec-pipeline";
const POLL_MS = 4000;

const BARE_TYPE_TOKENS = new Set([
  "str", "int", "bool", "float", "dict", "list", "tuple", "none", "any",
]);

function validateProposalClient(text: string): string | null {
  const proposal = text.trim();
  if (proposal.length < 10) {
    return "Proposal must be at least 10 characters";
  }
  if (BARE_TYPE_TOKENS.has(proposal.toLowerCase())) {
    return `Rejected before submit: bare type token "${proposal}"`;
  }
  if (/<[A-Za-z][\w\s-]*>/.test(proposal)) {
    return "Rejected before submit: angle-bracket placeholder detected";
  }
  return null;
}

function formatApiError(data: unknown, fallback: string): string {
  if (!data || typeof data !== "object" || !("detail" in data)) return fallback;
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: string }).msg);
        }
        return String(item);
      })
      .join("; ");
  }
  return fallback;
}

type StageRow = {
  stage: string;
  status: string;
  reason?: string;
  score?: number;
  decision?: string;
  count?: number;
};

type PipelineRow = {
  pipeline_id: string;
  status: string;
  proposal: string;
  updated_at?: string;
};

type PipelineDetail = {
  meta: {
    pipeline_id: string;
    status: string;
    reason?: string;
    pr_url?: string;
    stages?: StageRow[];
    judge_score?: number;
  };
  running?: string;
  handoff: boolean;
};

function stageLabel(row: StageRow): string {
  const bits = [row.stage, row.status];
  if (row.score != null) bits.push(`${row.score}`);
  if (row.decision) bits.push(row.decision);
  if (row.reason) bits.push(row.reason.slice(0, 48));
  return bits.join(" · ");
}

function statusColour(status: string): string {
  if (status === "blocked" || status === "error") return "#F87171";
  if (status === "dry_complete" || status === "complete") return "#4ADE80";
  if (status === "running" || status === "queued") return "#FBBF24";
  return "var(--text-muted)";
}

export default function SpecPipelinePanel() {
  const [proposal, setProposal] = useState("");
  const [dryRun, setDryRun] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastId, setLastId] = useState<string | null>(null);
  const [live, setLive] = useState<PipelineDetail | null>(null);
  const [pipelines, setPipelines] = useState<PipelineRow[]>([]);
  const [copiedId, setCopiedId] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

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

  const fetchDetail = useCallback(async (pipelineId: string) => {
    try {
      const r = await fetch(`${API}/${pipelineId}`, { credentials: "include" });
      if (!r.ok) return;
      const data = (await r.json()) as PipelineDetail;
      setLive(data);
      const terminal = data.meta.status;
      if (
        terminal !== "running" &&
        (!data.running || !["running", "queued"].includes(data.running))
      ) {
        await refresh();
      }
    } catch {
      /* ignore */
    }
  }, [refresh]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!lastId) return;
    void fetchDetail(lastId);
    pollRef.current = setInterval(() => void fetchDetail(lastId), POLL_MS);
    return () => {
      if (pollRef.current) clearInterval(pollRef.current);
    };
  }, [lastId, fetchDetail]);

  const run = async () => {
    const clientErr = validateProposalClient(proposal);
    if (clientErr) {
      setError(clientErr);
      return;
    }
    setBusy(true);
    setError(null);
    setLive(null);
    try {
      const r = await fetch(`${API}/run`, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ proposal: proposal.trim(), dry_run: dryRun }),
      });
      const data = await r.json();
      if (!r.ok) throw new Error(formatApiError(data, r.statusText));
      setLastId(data.pipeline_id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Run failed");
    } finally {
      setBusy(false);
    }
  };

  const copyPipelineId = async () => {
    if (!lastId) return;
    try {
      await navigator.clipboard.writeText(lastId);
      setCopiedId(true);
      setTimeout(() => setCopiedId(false), 2000);
    } catch {
      setError("Clipboard copy denied");
    }
  };

  const displayStatus = live
    ? (live.running && ["running", "queued"].includes(live.running)
        ? live.running
        : live.meta.status)
    : null;

  const stages = live?.meta.stages ?? [];

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
        Validate → STORM → Judge ↔ Board ↔ SPM → Boardroom. Dry-run stops before build.
      </p>
      <details className="text-xs" style={{ color: "var(--text-muted)" }}>
        <summary className="cursor-pointer hover:underline">Proposal validation rules</summary>
        <ul className="mt-1 list-disc pl-4 space-y-0.5">
          <li>At least 10 characters after trimming</li>
          <li>Not a bare type token (str, int, bool, …)</li>
          <li>No angle-bracket placeholders like &lt;feature-name&gt;</li>
          <li>Must not target 🚫 boundary files (config.py, auth.py, secrets)</li>
        </ul>
      </details>
      <textarea
        value={proposal}
        onChange={(e) => setProposal(e.target.value)}
        rows={4}
        placeholder="Proposal to judge and spec…"
        title="Min 10 chars; no bare type tokens (str); no <placeholders>"
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
        <div className="text-xs space-y-2" style={{ color: "var(--text-muted)" }}>
          <p className="flex items-center gap-2 flex-wrap">
            <span>
              Pipeline: <code>{lastId}</code>
            </span>
            <button
              type="button"
              onClick={() => void copyPipelineId()}
              className="text-[10px] px-1.5 py-0.5 rounded"
              style={{ border: "1px solid var(--border)" }}
              aria-label="Copy pipeline id"
            >
              {copiedId ? "Copied" : "Copy id"}
            </button>
          </p>
          {displayStatus && (
            <p>
              Status:{" "}
              <strong style={{ color: statusColour(displayStatus) }}>{displayStatus}</strong>
              {live?.meta.reason ? ` — ${live.meta.reason}` : ""}
              {live?.meta.judge_score != null ? ` (judge ${live.meta.judge_score})` : ""}
              {live?.meta.pr_url ? (
                <>
                  {" "}
                  — <a href={live.meta.pr_url}>PR</a>
                </>
              ) : null}
            </p>
          )}
          {stages.length > 0 && (
            <ul className="flex flex-wrap gap-1" aria-label="Pipeline stages">
              {stages.map((s, i) => (
                <li
                  key={`${s.stage}-${i}`}
                  className="font-mono px-1.5 py-0.5 rounded text-[10px]"
                  style={{
                    border: "1px solid var(--border)",
                    color: s.status === "blocked" ? "#F87171" : "var(--text-muted)",
                  }}
                  title={s.reason}
                >
                  {stageLabel(s)}
                </li>
              ))}
            </ul>
          )}
          <p>
            Artifacts: <code>.harness/spec-pipelines/{lastId}/</code>
            {live?.handoff ? " (handoff written)" : ""}
          </p>
        </div>
      )}
      <ul className="text-xs flex-1 overflow-auto space-y-1" style={{ color: "var(--text-muted)" }}>
        {pipelines.map((p) => (
          <li key={p.pipeline_id}>
            <button
              type="button"
              className="text-left hover:underline"
              onClick={() => setLastId(p.pipeline_id)}
            >
              <span className="font-mono">{p.pipeline_id}</span> — {p.status}: {p.proposal}
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
