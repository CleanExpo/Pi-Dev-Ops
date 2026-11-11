"use client";

import { useEffect, useRef, useState } from "react";
import GoalDraftReview, {
  draftsFromAnalyze,
  filePayloadFromDraft,
  type AnalysisPayload,
  type DraftTicket,
} from "./GoalDraftReview";
import GoalProjectPicker, { stubBrief, type GoalProject } from "./GoalProjectPicker";
import { writeGoalBriefId } from "@/lib/control/goalProjectStore";
import { acceptanceLabel, hasBrief, readyToAnalyze, remainingHint, ticketsToFile } from "@/lib/control/goalBrief";
import {
  PROJECT_KEPT_NOTE,
  WRITE_MAYBE_STARTED,
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
import { readGoalFiled, writeGoalFiled } from "@/lib/control/goalFiledStore";
import { goalStage } from "@/lib/control/goalStage";
import {
  UNREACHABLE,
  classifyCheck,
  isAnalysisJob,
  isFinal,
  jobStatusLabel,
  newIdempotencyKey,
  nextCheckMs,
  progressSeenAt,
  statusPath,
  waitForNextCheck,
  type AnalysisJob,
} from "@/lib/control/goalAnalysisJob";
import GoalFiledList from "./GoalFiledList";
import GoalHowTo from "./GoalHowTo";
import GoalStagePills from "./GoalStagePills";
import styles from "./control-deck.module.css";

type AnalyzeBody = GoalErrorBody &
  Partial<AnalysisPayload> & {
    project_title?: string;
    tickets?: Array<Partial<DraftTicket>>;
  };

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
  // UNI-3306: the status line of a submitted analysis job, while it is being checked.
  const [jobLine, setJobLine] = useState("");
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

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
    setFiled(readGoalFiled());
    setHydrated(true);
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    writeGoalFiled(filed);
  }, [filed, hydrated]);

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

  // One owner for turning an analysis result into drafts: the inline reply and a
  // finished job's result take the same path.
  function applyResult(data: AnalyzeBody) {
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
  }

  // UNI-3306 (grill 14 Q5): check every 3 s; a failed check shows UNREACHABLE and
  // backs off 3/6/12/30 s, never the last status; pause while the tab is hidden;
  // stop on finished or failed. Progress age starts from the server-computed
  // last_progress_age_s of each read and runs on the browser clock in between, so a
  // job already stalled when first seen shows as stalled at once.
  async function followJob(first: AnalysisJob) {
    let job = first;
    let failures = 0;
    let receivedAt = Date.now();
    let progress = progressSeenAt(job, receivedAt, null);
    let started = receivedAt - (job.elapsed_s ?? 0) * 1000;
    const describe = () => {
      const secs = (ms: number) => Math.max(0, Math.round(ms / 1000));
      const sinceProgress = Date.now() - progress.at;
      return `${jobStatusLabel(job, sinceProgress)} · ${secs(Date.now() - started)} s elapsed · last progress ${secs(sinceProgress)} s ago`;
    };
    setJobLine(describe());
    while (mounted.current && !isFinal(job)) {
      await waitForNextCheck(nextCheckMs(failures));
      if (!mounted.current) return;
      let outcome;
      try {
        const res = await fetch(statusPath(job.id), { method: "GET" });
        const body = await res.json().catch(() => null);
        outcome = classifyCheck(job.id, res.status, res.headers.get("X-Upstream-Status"), body);
      } catch {
        outcome = { kind: "retry" } as const;
      }
      if (!mounted.current) return;
      if (outcome.kind === "stop") {
        setError(outcome.message);
        return;
      }
      if (outcome.kind === "retry") {
        failures += 1;
        setJobLine(UNREACHABLE);
        continue;
      }
      failures = 0;
      job = outcome.job;
      receivedAt = Date.now();
      progress = progressSeenAt(job, receivedAt, progress);
      started = receivedAt - (job.elapsed_s ?? 0) * 1000;
      setJobLine(describe());
    }
    if (!mounted.current) return;
    if (job.status === "failed") {
      setError(`Analysis failed: ${job.failure_reason || "no reason was recorded"}. Linear was not written.`);
      return;
    }
    if (typeof job.result !== "object" || job.result === null) {
      setError("The analysis finished without a result. Linear was not written. Analyze again.");
      return;
    }
    applyResult(job.result as AnalyzeBody);
  }

  async function analyze() {
    if (busy || !canAnalyze) return;
    setError("");
    setConfirming(false);
    setJobLine("");
    setBusy(true);
    try {
      const res = await fetch("/api/pi-ceo/api/goal-ticket/analyze", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          goal: sanitize(goal.trim()),
          acceptance: sanitize(acceptance.trim()),
          project_id: project?.id || "",
          idempotency_key: newIdempotencyKey(),
        }),
      });
      const data = (await res.json().catch(() => ({}))) as AnalyzeBody;
      if (!res.ok) {
        setError(errorMessage(data, res.status));
        return;
      }
      if (res.status === 202) {
        if (!isAnalysisJob(data)) {
          setError("The server accepted the analysis but returned no job to check. Linear was not written.");
          return;
        }
        await followJob(data);
        return;
      }
      applyResult(data);
    } catch {
      setError("Network error — Pi CEO backend unreachable. Linear was not written.");
    } finally {
      if (mounted.current) {
        setJobLine("");
        setBusy(false);
      }
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
        setError(WRITE_MAYBE_STARTED);
        return;
      }
      setFiled(created);
      setAnalysis(null);
      setConfirming(false);
      setGoal("");
      setAcceptance("");
      writeGoalAnalysis(null);
    } catch {
      setError(WRITE_MAYBE_STARTED);
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
        onClear={() => { setProject(null); writeGoalBriefId(""); }}
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
        <span className={styles.fieldLabel}>{acceptanceLabel(acceptance)}</span>
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
            <span className={styles.note} role="status">
              {jobLine || `${analyzingCopy(elapsed)} ${analyzeProgress(elapsed)}%`}
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
            onClick={() => setError("")}
            className={styles.ghost}
          >
            Write the next goal
          </button>
        </div>
      ) : null}
      <GoalFiledList tickets={filed} />
    </div>
  );
}
