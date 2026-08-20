// components/control/GoalTicketForm.tsx — Goal → analyze → approve → Linear
"use client";

import { useEffect, useState } from "react";
import { useActiveProject } from "./ProjectSelector";
import GoalDraftReview, {
  type AnalysisPayload,
  type DraftTicket,
} from "./GoalDraftReview";

function sanitize(s: string): string {
  return s.replace(/[<>]/g, "");
}

function repoToUrl(repo: string): string {
  if (!repo) return "";
  if (repo.startsWith("http")) return repo;
  return `https://github.com/${repo}`;
}

interface FiledTicket {
  identifier: string;
  url: string;
  title: string;
  state: string;
  labels: string[];
}

interface ErrorBody {
  error?: string;
  detail?: { error?: string; fields?: string[]; hint?: string; repo?: string };
}

function errorMessage(data: ErrorBody, status: number): string {
  const detail = data.detail;
  const fields = detail?.fields?.join(", ");
  return (
    detail?.hint
    || (fields ? `Missing: ${fields}` : null)
    || detail?.error
    || data.error
    || `Request failed (${status})`
  );
}

const inputBase: React.CSSProperties = {
  background: "var(--panel-hover)",
  color: "var(--text)",
  border: "1px solid var(--border)",
  fontFamily: "var(--font-mono, monospace)",
  fontSize: "11px",
  outline: "none",
};

export default function GoalTicketForm() {
  const activeProject = useActiveProject();
  const [goal, setGoal] = useState("");
  const [repo, setRepo] = useState("");
  const [acceptance, setAcceptance] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [analysis, setAnalysis] = useState<AnalysisPayload | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [filed, setFiled] = useState<FiledTicket[]>([]);

  useEffect(() => {
    if (!activeProject) return;
    const url = repoToUrl(activeProject.repo);
    setRepo((current) => (current ? current : url));
  }, [activeProject]);

  async function analyze() {
    if (busy) return;
    setError("");
    setFiled([]);
    setConfirming(false);
    setBusy(true);
    try {
      const res = await fetch("/api/pi-ceo/api/goal-ticket/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          goal: sanitize(goal.trim()),
          repo: sanitize(repo.trim()),
          acceptance: sanitize(acceptance.trim()),
        }),
      });
      const data = (await res.json().catch(() => ({}))) as ErrorBody & {
        summary?: string;
        product?: string;
        engineering?: string;
        split_reason?: string;
        fallback?: boolean;
        filed?: boolean;
        tickets?: Array<{ title?: string; goal?: string; acceptance?: string; rationale?: string }>;
      };
      if (!res.ok) {
        setError(errorMessage(data, res.status));
        return;
      }
      if (data.filed) {
        setError("Analyze wrote to Linear. Stopped. Nothing further was filed.");
        return;
      }
      const tickets = (data.tickets || [])
        .filter((t) => t.title && t.goal && t.acceptance)
        .map((t) => ({
          title: t.title || "",
          goal: t.goal || "",
          acceptance: t.acceptance || "",
          rationale: t.rationale || "",
          selected: true,
        }));
      if (tickets.length === 0) {
        setError("Analysis returned no tickets.");
        return;
      }
      setAnalysis({
        summary: data.summary || "",
        product: data.product || "",
        engineering: data.engineering || "",
        split_reason: data.split_reason || "",
        fallback: Boolean(data.fallback),
        tickets,
      });
    } catch {
      setError("Network error — Pi CEO backend unreachable.");
    } finally {
      setBusy(false);
    }
  }

  async function approveAndFile() {
    if (busy || !analysis) return;
    const chosen = analysis.tickets.filter((t) => t.selected);
    if (chosen.length === 0) return;
    setError("");
    setBusy(true);
    try {
      const res = await fetch("/api/pi-ceo/api/goal-ticket", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          goal: sanitize(goal.trim()),
          repo: sanitize(repo.trim()),
          acceptance: sanitize(acceptance.trim()),
          approved: true,
          tickets: chosen.map((t) => ({
            title: sanitize(t.title.trim()),
            goal: sanitize(t.goal.trim()),
            acceptance: sanitize(t.acceptance.trim()),
            rationale: sanitize(t.rationale.trim()),
          })),
        }),
      });
      const data = (await res.json().catch(() => ({}))) as ErrorBody & {
        tickets?: FiledTicket[];
      };
      if (!res.ok) {
        setError(errorMessage(data, res.status));
        return;
      }
      const created = (data.tickets || []).filter((t) => t.identifier && t.url);
      if (created.length === 0) {
        setError("Approval returned no tickets. Linear may not have been written.");
        return;
      }
      setFiled(created);
      setAnalysis(null);
      setConfirming(false);
      setGoal("");
      setAcceptance("");
    } catch {
      setError("Network error — Pi CEO backend unreachable.");
    } finally {
      setBusy(false);
    }
  }

  function setTickets(tickets: DraftTicket[]) {
    if (!analysis) return;
    setAnalysis({ ...analysis, tickets });
  }

  return (
    <div className="flex flex-col gap-2 max-w-3xl">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-widest font-mono" style={{ color: "var(--text-dim)" }}>
          <span style={{ color: "var(--accent)" }} aria-hidden="true">$ </span>
          goal → linear tickets
        </span>
        <span className="text-[10px] font-mono" style={{ color: "var(--text-muted)" }}>
          Analyze first — Linear only after approve
        </span>
      </div>

      <textarea
        id="goal-text"
        name="goal"
        value={goal}
        onChange={(e) => setGoal(e.target.value)}
        placeholder="Goal — what should exist when this is done"
        disabled={busy || Boolean(analysis)}
        rows={2}
        className="w-full px-2.5 py-2 rounded-md bg-transparent outline-none resize-none disabled:opacity-50 text-[11px]"
        style={inputBase}
        aria-label="Goal"
      />
      <input
        id="goal-repo"
        name="repo"
        type="text"
        value={repo}
        onChange={(e) => setRepo(e.target.value)}
        placeholder="https://github.com/owner/repo"
        disabled={busy || Boolean(analysis)}
        className="w-full h-9 px-2.5 rounded-md bg-transparent outline-none disabled:opacity-50 text-[11px]"
        style={inputBase}
        aria-label="Target repository"
      />
      <textarea
        id="goal-acceptance"
        name="acceptance"
        value={acceptance}
        onChange={(e) => setAcceptance(e.target.value)}
        placeholder="Acceptance — how a stranger can tell this is done"
        disabled={busy || Boolean(analysis)}
        rows={2}
        className="w-full px-2.5 py-2 rounded-md bg-transparent outline-none resize-none disabled:opacity-50 text-[11px]"
        style={inputBase}
        aria-label="Acceptance criteria"
      />

      {!analysis ? (
        <div className="flex items-center gap-2">
          <button
            onClick={() => void analyze()}
            disabled={busy || !goal.trim() || !repo.trim() || !acceptance.trim()}
            className="h-8 px-3 rounded-md text-xs font-mono font-medium disabled:opacity-30"
            style={{ background: "var(--accent)", color: "var(--on-accent)" }}
          >
            {busy ? "analyzing…" : "analyze goal"}
          </button>
          {busy ? (
            <span className="text-[11px] font-mono" style={{ color: "var(--text-muted)" }}>
              Reading as product + engineering. Nothing is filed yet.
            </span>
          ) : null}
        </div>
      ) : (
        <GoalDraftReview
          analysis={analysis}
          confirming={confirming}
          filing={busy}
          onChange={setTickets}
          onDiscard={() => { setAnalysis(null); setConfirming(false); }}
          onRequestFile={() => setConfirming(true)}
          onCancelConfirm={() => setConfirming(false)}
          onApprove={() => void approveAndFile()}
        />
      )}

      {error ? (
        <p className="text-[11px] font-mono" style={{ color: "var(--error)" }}>{error}</p>
      ) : null}

      {filed.length > 0 ? (
        <ul className="flex flex-col gap-1">
          {filed.map((ticket) => (
            <li key={ticket.identifier} className="text-[11px] font-mono" style={{ color: "var(--success)" }}>
              Filed{" "}
              <a href={ticket.url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent)" }}>
                {ticket.identifier}
              </a>
              {" "}· {ticket.title} · {ticket.state}
              {ticket.labels.length > 0 ? ` · ${ticket.labels.join(", ")}` : ""}
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
