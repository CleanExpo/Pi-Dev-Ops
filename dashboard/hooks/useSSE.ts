// hooks/useSSE.ts — one analysis request with streamed results
"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { TermLine, Phase, AnalysisResult, PhaseStatus } from "@/lib/types";
import { PHASES } from "@/lib/phases";

interface PhaseMetric {
  duration_s: number;
  cost_usd: number;
}

interface SSEState {
  lines:        TermLine[];
  phases:       Phase[];
  result:       Partial<AnalysisResult>;
  branch:       string | null;
  prUrl:        string | null;
  linearUrl:    string | null;
  linearId:     string | null;
  status:       "idle" | "running" | "done" | "error";
  error:        string | null;
  retries:      number;
  phaseMetrics: Record<string, PhaseMetric>;
}

const initialPhases = (): Phase[] =>
  PHASES.map((p) => ({ ...p, status: "pending" as PhaseStatus }));

export function useSSE() {
  const esRef        = useRef<EventSource | null>(null);
  useEffect(() => () => { esRef.current?.close(); }, []);

  const [state, setState] = useState<SSEState>({
    lines:        [],
    phases:       initialPhases(),
    result:       {},
    branch:       null,
    prUrl:        null,
    linearUrl:    null,
    linearId:     null,
    status:       "idle",
    error:        null,
    retries:      0,
    phaseMetrics: {},
  });

  const briefRef = useRef<string>("");

  const connect = useCallback((repoUrl: string) => {
    esRef.current?.close();

    const params = new URLSearchParams({ repo: repoUrl });
    if (briefRef.current) params.set("brief", briefRef.current);
    const es     = new EventSource(`/api/analyze?${params}`);
    esRef.current = es;

    es.addEventListener("line", (e) => {
      const line = JSON.parse(e.data) as TermLine;
      setState((s) => ({ ...s, lines: [...s.lines, line] }));
    });

    es.addEventListener("branch", (e) => {
      const { branch } = JSON.parse(e.data) as { branch: string };
      setState((s) => ({ ...s, branch }));
    });

    es.addEventListener("phase_update", (e) => {
      const { phaseId, status } = JSON.parse(e.data) as { phaseId: number; status: PhaseStatus };
      setState((s) => ({
        ...s,
        phases: s.phases.map((p) =>
          p.id === phaseId
            ? {
                ...p, status,
                ...(status === "running" ? { startedAt: Date.now() } : {}),
                ...(status === "done"    ? { doneAt:    Date.now() } : {}),
              }
            : p
        ),
      }));
    });

    es.addEventListener("phase_metric", (e) => {
      const { phase, duration_s, cost_usd } = JSON.parse(e.data) as {
        phase: string;
        duration_s: number;
        cost_usd: number;
      };
      setState((s) => ({
        ...s,
        phaseMetrics: { ...s.phaseMetrics, [phase]: { duration_s, cost_usd } },
      }));
    });

    es.addEventListener("result_update", (e) => {
      const { value } = JSON.parse(e.data) as { value: Partial<AnalysisResult> };
      setState((s) => ({ ...s, result: { ...s.result, ...value } }));
    });

    es.addEventListener("linear_ticket", (e) => {
      const data = JSON.parse(e.data) as { url: string; identifier: string };
      setState((s) => ({ ...s, linearUrl: data.url, linearId: data.identifier }));
    });

    es.addEventListener("done", (e) => {
      const data = JSON.parse(e.data) as { branch: string; prUrl?: string; result: Partial<AnalysisResult> };
      setState((s) => ({
        ...s,
        status:  "done",
        retries: 0,
        branch:  data.branch,
        prUrl:   data.prUrl ?? null,
        result:  { ...s.result, ...data.result },
      }));
      es.close();
    });

    // Server-sent "error" events — only fire when the route explicitly sends
    // `event: error\ndata: {...}`. Native connection drops have no .data and
    // must fall through to onerror (which reports lost observation).
    es.addEventListener("error", (e) => {
      const msgData = (e as MessageEvent).data;
      if (!msgData) return; // no data = connection drop; let onerror handle it
      try {
        const data = JSON.parse(msgData) as { message?: string };
        if (data.message) {
          setState((s) => ({ ...s, status: "error", error: data.message!, retries: 0 }));
          es.close();
        }
      } catch { /* malformed — ignore, let onerror handle */ }
    });

    // "timeout" event — server hit its budget, has partial results
    es.addEventListener("timeout", () => {
      setState((s) => ({
        ...s,
        status: "error",
        error:  "Analysis timed out — partial results shown. Re-run to complete.",
        retries: 0,
      }));
      es.close();
    });

    es.onerror = () => {
      es.close();
      setState((s) => {
        if (s.status !== "running") return s;

        // GET /api/analyze creates work: repeating it would launch another run.
        return { ...s, status: "error", retries: 0, error: "Analysis connection lost. Check History before starting another analysis." };
      });
    };
  }, []);

  const start = useCallback((repoUrl: string, brief?: string) => {
    briefRef.current = brief ?? "";
    setState({
      lines:        [],
      phases:       initialPhases(),
      result:       {},
      branch:       null,
      prUrl:        null,
      linearUrl:    null,
      linearId:     null,
      status:       "running",
      error:        null,
      retries:      0,
      phaseMetrics: {},
    });
    connect(repoUrl);
  }, [connect]);

  const stop = useCallback(() => {
    esRef.current?.close();
    setState((s) => ({ ...s, status: "idle", retries: 0 }));
  }, []);

  const { retries: _, ...publicState } = state;
  return { ...publicState, reconnecting: state.retries > 0 && state.status === "running", start, stop };
}
