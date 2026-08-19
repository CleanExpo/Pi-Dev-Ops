// components/control/GoalTicketForm.tsx — Goal → Linear Backlog (first hop)
"use client";

import { useEffect, useState } from "react";
import { useActiveProject } from "./ProjectSelector";

function sanitize(s: string): string {
  return s.replace(/[<>]/g, "");
}

function repoToUrl(repo: string): string {
  if (!repo) return "";
  if (repo.startsWith("http")) return repo;
  return `https://github.com/${repo}`;
}

interface CreatedTicket {
  identifier: string;
  url: string;
  title: string;
  state: string;
  labels: string[];
}

export default function GoalTicketForm() {
  const activeProject = useActiveProject();
  const [goal, setGoal] = useState("");
  const [repo, setRepo] = useState("");
  const [acceptance, setAcceptance] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const [ticket, setTicket] = useState<CreatedTicket | null>(null);

  useEffect(() => {
    if (!activeProject) return;
    const url = repoToUrl(activeProject.repo);
    setRepo((current) => (current ? current : url));
  }, [activeProject]);

  async function submit() {
    if (submitting) return;
    setError("");
    setTicket(null);
    setSubmitting(true);
    try {
      const res = await fetch("/api/pi-ceo/api/goal-ticket", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          goal: sanitize(goal.trim()),
          repo: sanitize(repo.trim()),
          acceptance: sanitize(acceptance.trim()),
        }),
      });
      const data = (await res.json().catch(() => ({}))) as {
        identifier?: string;
        url?: string;
        title?: string;
        state?: string;
        labels?: string[];
        error?: string;
        detail?: { error?: string; fields?: string[]; hint?: string; repo?: string };
      };
      if (!res.ok) {
        const detail = data.detail;
        const fields = detail?.fields?.join(", ");
        setError(
          detail?.hint
            || (fields ? `Missing: ${fields}` : null)
            || detail?.error
            || data.error
            || `Could not file ticket (${res.status})`,
        );
        return;
      }
      if (!data.identifier || !data.url) {
        setError("Ticket was not returned. Nothing filed.");
        return;
      }
      setTicket({
        identifier: data.identifier,
        url: data.url,
        title: data.title || "",
        state: data.state || "Backlog",
        labels: data.labels || [],
      });
      setGoal("");
      setAcceptance("");
    } catch {
      setError("Network error — Pi CEO backend unreachable.");
    } finally {
      setSubmitting(false);
    }
  }

  const inputBase: React.CSSProperties = {
    background: "var(--panel-hover)",
    color: "var(--text)",
    border: "1px solid var(--border)",
    fontFamily: "var(--font-mono, monospace)",
    fontSize: "11px",
    outline: "none",
  };

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-center justify-between">
        <span className="text-[10px] uppercase tracking-widest font-mono" style={{ color: "var(--text-dim)" }}>
          <span style={{ color: "var(--accent)" }} aria-hidden="true">$ </span>
          goal → linear ticket
        </span>
        <span className="text-[10px] font-mono" style={{ color: "var(--text-muted)" }}>
          Backlog only — does not start a build
        </span>
      </div>

      <textarea
        id="goal-text"
        name="goal"
        value={goal}
        onChange={(e) => setGoal(e.target.value)}
        placeholder="Goal — what should exist when this is done"
        disabled={submitting}
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
        disabled={submitting}
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
        disabled={submitting}
        rows={2}
        className="w-full px-2.5 py-2 rounded-md bg-transparent outline-none resize-none disabled:opacity-50 text-[11px]"
        style={inputBase}
        aria-label="Acceptance criteria"
      />

      <div className="flex items-center gap-2">
        <button
          onClick={() => void submit()}
          disabled={submitting || !goal.trim() || !repo.trim() || !acceptance.trim()}
          className="h-8 px-3 rounded-md text-xs font-mono font-medium disabled:opacity-30"
          style={{ background: "var(--accent)", color: "var(--on-accent)" }}
        >
          {submitting ? "filing…" : "file ticket"}
        </button>
      </div>

      {error && (
        <p className="text-[11px] font-mono" style={{ color: "var(--error)" }}>
          {error}
        </p>
      )}

      {ticket && (
        <p className="text-[11px] font-mono" style={{ color: "var(--success)" }}>
          Filed{" "}
          <a href={ticket.url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent)" }}>
            {ticket.identifier}
          </a>
          {" "}· {ticket.state}
          {ticket.labels.length > 0 ? ` · ${ticket.labels.join(", ")}` : ""}
        </p>
      )}
    </div>
  );
}
