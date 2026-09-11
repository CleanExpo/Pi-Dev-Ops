"use client";

import { useEffect, useState } from "react";
import GoalDraftReview, {
  draftsFromAnalyze,
  filePayloadFromDraft,
  type AnalysisPayload,
  type DraftTicket,
} from "./GoalDraftReview";
import GoalProjectPicker, { stubBrief, type GoalProject } from "./GoalProjectPicker";
import { hasBrief, readyToAnalyze, remainingHint, ticketsToFile } from "@/lib/control/goalBrief";
import {
  PROJECT_KEPT_NOTE,
  analyzeProgress,
  analyzingCopy,
  nextAnalyzeHint,
} from "@/lib/control/goalCopy";
import {
  errorMessage,
  filedTickets,
  markLanded,
  mergeFiled,
  type FiledTicket,
  type GoalErrorBody,
} from "@/lib/control/goalErrors";
import { readGoalAnalysis, writeGoalAnalysis } from "@/lib/control/goalAnalysisStore";
import { goalStage } from "@/lib/control/goalStage";
import GoalFiledList from "./GoalFiledList";
import GoalHowTo from "./GoalHowTo";
import GoalStagePills from "./GoalStagePills";
import styles from "./control-deck.module.css";

function sanitize(s: string): string {
  return s.replace(/[<>]/g, "");
}

export default function GoalTicketForm() {
  const [goal, setGoal] = useState("");
  const [project, setProject] = useState<GoalProject | null>(null);
  const [acceptance, setAcceptance] = useState("");
  const [busy, setBusy] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState("");
  const [analysis, setAnalysis] = useState<AnalysisPayload | null>(null);
  const [confirming, setConfirming] = useState(false);
  const [filed, setFiled] = useState<FiledTicket[]>([]);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    if (!busy) {
      setElapsed(0);
      return;
    }
    const id = setInterval(() => setElapsed((n) => n + 1), 1000);
    return () => clearInterval(id);
  }, [busy]);

  useEffect(() => {
    const stored = readGoalAnalysis();
    if (stored) {
      setGoal(stored.goal);
      setAcceptance(stored.acceptance);
      setAnalysis(stored.analysis);
      setProject(stubBrief(stored.project_id, stored.project_title));
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    if (!analysis) {
      writeGoalAnalysis(null);
      return;
    }
    writeGoalAnalysis({
      project_id: project?.id || "",
      project_title: project?.title || "",
      goal,
      acceptance,
      analysis,
    });
  }, [analysis, goal, acceptance, project, hydrated]);

  const canAnalyze = readyToAnalyze(goal, acceptance, project?.id || "");

  async function analyze() {
    if (busy || !canAnalyze) return;
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
          acceptance: sanitize(acceptance.trim()),
          project_id: project?.id || "",
        }),
      });
      const data = (await res.json().catch(() => ({}))) as GoalErrorBody & Partial<AnalysisPayload> & {
        project_title?: string;
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
        code_limitation: data.project_title
          ? `Tickets grounded in project: ${data.project_title}`
          : data.code_limitation || "",
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
    if (!hasBrief(project?.id || "")) {
      setError("Select a brief before writing to Linear.");
      return;
    }
    const chosen = ticketsToFile(analysis.tickets, filed);
    if (chosen.length === 0) {
      setError("Those tickets are already in Linear.");
      return;
    }
    setError("");
    setBusy(true);
    try {
      const res = await fetch("/api/pi-ceo/api/goal-ticket", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          goal: sanitize(goal.trim()),
          acceptance: sanitize(acceptance.trim()),
          project_id: project?.id || "",
          approved: true,
          tickets: chosen.map((ticket) => filePayloadFromDraft(ticket, sanitize)),
        }),
      });
      const data = (await res.json().catch(() => ({}))) as GoalErrorBody;
      if (!res.ok) {
        const partial = filedTickets(data);
        const next = mergeFiled(filed, partial);
        setFiled(next);
        setAnalysis({ ...analysis, tickets: markLanded(analysis.tickets, next) });
        setError(errorMessage(data, res.status));
        return;
      }
      const created = mergeFiled(filed, filedTickets(data));
      if (created.length === 0) {
        setError("Approval returned no tickets. Linear may not have been written.");
        return;
      }
      setFiled(created);
      setAnalysis(null);
      setConfirming(false);
      setGoal("");
      setAcceptance("");
      writeGoalAnalysis(null);
    } catch {
      setError("Network error — Pi CEO backend unreachable. Linear was not written.");
    } finally {
      setBusy(false);
    }
  }

  const stage = goalStage({
    confirming,
    hasAnalysis: Boolean(analysis),
    analyzing: busy && !analysis,
  });

  return (
    <div className="max-w-3xl">
      <GoalStagePills stage={stage} />
      <GoalHowTo />

      <GoalProjectPicker
        selectedId={project?.id || ""}
        disabled={busy || Boolean(analysis)}
        onSelect={setProject}
      />
      <label className={styles.field}>
        <span className={styles.fieldLabel}>{remainingHint(goal, "Goal")}</span>
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
        <span className={styles.fieldLabel}>{remainingHint(acceptance, "Acceptance")}</span>
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
            disabled={busy || !canAnalyze}
            className={styles.primary}
          >
            {busy ? "Analyzing…" : "Analyze goal"}
          </button>
          {busy ? (
            <span className={styles.note}>
              {analyzingCopy(elapsed)} {analyzeProgress(elapsed)}%
            </span>
          ) : (
            <span className={styles.note}>
              {nextAnalyzeHint(goal, acceptance, project?.id || "")}
            </span>
          )}
        </div>
      ) : (
        <GoalDraftReview
          analysis={analysis}
          confirming={confirming}
          filing={busy}
          onChange={(tickets) => setAnalysis({ ...analysis, tickets })}
          onDiscard={() => {
            setAnalysis(null);
            setConfirming(false);
            writeGoalAnalysis(null);
          }}
          onRequestFile={() => setConfirming(true)}
          onCancelConfirm={() => setConfirming(false)}
          onApprove={() => void approveAndFile()}
        />
      )}

      {error ? (
        <p className="mt-3 text-[13px]" style={{ color: "var(--error)" }}>{error}</p>
      ) : null}

      {filed.length > 0 && !analysis ? (
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <p className={styles.note}>{PROJECT_KEPT_NOTE}</p>
          <button
            type="button"
            onClick={() => { setFiled([]); setError(""); writeGoalAnalysis(null); }}
            className={styles.ghost}
          >
            Start another goal
          </button>
        </div>
      ) : null}
      <GoalFiledList tickets={filed} />
    </div>
  );
}
