// components/control/GoalTicketForm.tsx — Goal → analyze → approve → Linear
"use client";

import { useEffect, useState } from "react";
import { useActiveProject } from "./ProjectSelector";
import GoalDraftReview, {
  draftsFromAnalyze,
  filePayloadFromDraft,
  type AnalysisPayload,
  type DraftTicket,
} from "./GoalDraftReview";
import styles from "./control-deck.module.css";

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
  hint?: string;
  detail?: { error?: string; fields?: string[]; hint?: string; repo?: string };
}

function errorMessage(data: ErrorBody, status: number): string {
  const detail = data.detail;
  const fields = detail?.fields?.join(", ");
  return (
    data.hint
    || detail?.hint
    || (fields ? `Missing: ${fields}` : null)
    || detail?.error
    || data.error
    || `Request failed (${status})`
  );
}

function analyzingCopy(seconds: number): string {
  if (seconds < 10) return `${seconds}s · inspecting the repo. Linear is not written.`;
  if (seconds < 35) return `${seconds}s · breaking the goal into tickets. Linear is not written.`;
  return `${seconds}s · still analyzing. Linear is not written.`;
}

export default function GoalTicketForm() {
  const activeProject = useActiveProject();
  const [goal, setGoal] = useState("");
  const [repo, setRepo] = useState("");
  const [acceptance, setAcceptance] = useState("");
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState("");
  const [analysis, setAnalysis] = useState<AnalysisPayload | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [filed, setFiled] = useState<FiledTicket[]>([]);

  useEffect(() => {
    if (!activeProject) return;
    setRepo((current) => (current ? current : repoToUrl(activeProject.repo)));
  }, [activeProject]);

  useEffect(() => {
    if (!busy) {
      setElapsed(0);
      return;
    }
    const id = setInterval(() => setElapsed((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [busy]);

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
      const data = (await res.json().catch(() => ({}))) as ErrorBody & Partial<AnalysisPayload> & {
        filed?: boolean;
        tickets?: Array<Partial<DraftTicket>>;
      };
      if (!res.ok) {
        setError(errorMessage(data, res.status));
        return;
      }
      if (data.filed) {
        setError("Analyze wrote to Linear. Stopped. Nothing further was filed.");
        return;
      }
      const tickets = draftsFromAnalyze(data.tickets || []);
      if (tickets.length === 0) {
        setError("Analysis returned no tickets.");
        return;
      }
      setAnalysis({
        summary: data.summary || "",
        split_reason: data.split_reason || "",
        fallback: Boolean(data.fallback),
        code_inspected: Boolean(data.code_inspected),
        code_limitation: data.code_limitation || "",
        goal_analysis: data.goal_analysis,
        user_flow: data.user_flow,
        technical_flow: data.technical_flow,
        implementation_order: data.implementation_order,
        final_review: data.final_review,
        tickets,
      });
    } catch {
      setError("Network error — Pi CEO backend unreachable. Linear was not written.");
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
          tickets: chosen.map((t) => filePayloadFromDraft(t, sanitize)),
        }),
      });
      const data = (await res.json().catch(() => ({}))) as ErrorBody & { tickets?: FiledTicket[] };
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
      setError("Network error — Pi CEO backend unreachable. Linear was not written.");
    } finally {
      setBusy(false);
    }
  }

  const stage = confirming ? 3 : analysis ? 2 : 1;

  return (
    <div className="max-w-3xl">
      <div className={styles.stageRow} aria-label="Goal filing stages">
        {[
          { n: 1, label: "Compose" },
          { n: 2, label: "Analyze" },
          { n: 3, label: "Approve" },
        ].map((s) => (
          <div key={s.n} className={`${styles.stage} ${stage === s.n ? styles.stageOn : ""}`}>
            <div className={styles.stageNum}>Stage {s.n}</div>
            <div className={styles.stageLabel}>{s.label}</div>
          </div>
        ))}
      </div>

      <label className={styles.field}>
        <span className={styles.fieldLabel}>Goal</span>
        <textarea
          id="goal-text"
          name="goal"
          value={goal}
          onChange={(e) => setGoal(e.target.value)}
          placeholder="What should exist when this is done"
          disabled={busy || Boolean(analysis)}
          rows={3}
          className={styles.input}
        />
      </label>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>Repository</span>
        <input
          id="goal-repo"
          name="repo"
          type="text"
          value={repo}
          onChange={(e) => setRepo(e.target.value)}
          placeholder="https://github.com/CleanExpo/Synthex"
          disabled={busy || Boolean(analysis)}
          className={styles.input}
        />
      </label>
      <label className={styles.field}>
        <span className={styles.fieldLabel}>Acceptance</span>
        <textarea
          id="goal-acceptance"
          name="acceptance"
          value={acceptance}
          onChange={(e) => setAcceptance(e.target.value)}
          placeholder="How a stranger can tell this is done"
          disabled={busy || Boolean(analysis)}
          rows={3}
          className={styles.input}
        />
      </label>

      {!analysis ? (
        <div className="flex flex-wrap items-center gap-3">
          <button
            onClick={() => void analyze()}
            disabled={busy || !goal.trim() || !repo.trim() || !acceptance.trim()}
            className={styles.primary}
          >
            {busy ? "Analyzing…" : "Analyze goal"}
          </button>
          {busy ? <span className={styles.note}>{analyzingCopy(elapsed)}</span> : (
            <span className={styles.note}>Drafts first. Linear only after approve.</span>
          )}
        </div>
      ) : (
        <GoalDraftReview
          analysis={analysis}
          confirming={confirming}
          filing={busy}
          onChange={(tickets) => setAnalysis({ ...analysis, tickets })}
          onDiscard={() => { setAnalysis(null); setConfirming(false); }}
          onRequestFile={() => setConfirming(true)}
          onCancelConfirm={() => setConfirming(false)}
          onApprove={() => void approveAndFile()}
        />
      )}

      {error ? (
        <p className="mt-3 text-[13px]" style={{ color: "var(--error)" }}>{error}</p>
      ) : null}

      {filed.length > 0 ? (
        <ul className="mt-4 flex flex-col gap-2">
          {filed.map((ticket) => (
            <li key={ticket.identifier} className={styles.card}>
              <a href={ticket.url} target="_blank" rel="noopener noreferrer" style={{ color: "var(--accent)" }}>
                {ticket.identifier}
              </a>
              <span className="block text-[13px] mt-1" style={{ color: "var(--text)" }}>{ticket.title}</span>
              <span className={styles.note}>{ticket.state}{ticket.labels.length ? ` · ${ticket.labels.join(", ")}` : ""}</span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
