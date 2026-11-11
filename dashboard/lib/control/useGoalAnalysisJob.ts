"use client";

import { useEffect, useRef, useState } from "react";
import { fetchProxy } from "@/lib/pi-ceo-fetch";
import {
  UNREACHABLE,
  classifyCheck,
  isFinal,
  jobStatusLabel,
  nextCheckMs,
  progressSeenAt,
  statusPath,
  waitForNextCheck,
  type AnalysisJob,
} from "@/lib/control/goalAnalysisJob";

import { draftsFromAnalyze, type AnalysisPayload, type DraftTicket } from "@/components/control/GoalDraftReview";
import type { GoalErrorBody } from "@/lib/control/goalErrors";

export type AnalyzeBody = GoalErrorBody &
  Partial<AnalysisPayload> & {
    project_title?: string;
    tickets?: Array<Partial<DraftTicket>>;
  };

/** Owns job following and its display lifetime; the form owns submission and rendering. */
export function useGoalAnalysisJob(
  busy: boolean,
  setAnalysis: (result: AnalysisPayload) => void,
  setError: (message: string) => void,
) {
  const [elapsed, setElapsed] = useState(0);
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
      const result = await fetchProxy<unknown>(statusPath(job.id), { cache: "no-store" });
      const outcome = classifyCheck(job.id, result);
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

  return { elapsed, jobLine, setJobLine, mounted, followJob, applyResult };
}
