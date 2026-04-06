// hooks/useSSE.ts — SSE subscription hook for live analysis streaming

"use client";

import { useCallback, useRef, useState } from "react";
import type { TermLine, Phase, AnalysisResult, PhaseStatus } from "@/lib/types";
import { PHASES } from "@/lib/phases";

interface SSEState {
  lines: TermLine[];
  phases: Phase[];
  result: Partial<AnalysisResult>;
  branch: string | null;
  prUrl: string | null;
  status: "idle" | "running" | "done" | "error";
  error: string | null;
}

const initialPhases = (): Phase[] =>
  PHASES.map((p) => ({ ...p, status: "pending" as PhaseStatus }));

export function useSSE() {
  const esRef = useRef<EventSource | null>(null);
  const [state, setState] = useState<SSEState>({
    lines: [],
    phases: initialPhases(),
    result: {},
    branch: null,
    prUrl: null,
    status: "idle",
    error: null,
  });

  const start = useCallback((repoUrl: string, token: string) => {
    esRef.current?.close();
    setState({
      lines: [],
      phases: initialPhases(),
      result: {},
      branch: null,
      prUrl: null,
      status: "running",
      error: null,
    });

    const params = new URLSearchParams({ repo: repoUrl, token });
    const es = new EventSource(`/api/analyze?${params}`);
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
            ? { ...p, status, ...(status === "running" ? { startedAt: Date.now() } : {}), ...(status === "done" ? { doneAt: Date.now() } : {}) }
            : p
        ),
      }));
    });

    es.addEventListener("result_update", (e) => {
      const { value } = JSON.parse(e.data) as { value: Partial<AnalysisResult> };
      setState((s) => ({ ...s, result: { ...s.result, ...value } }));
    });

    es.addEventListener("done", (e) => {
      const data = JSON.parse(e.data) as { branch: string; prUrl?: string; result: Partial<AnalysisResult> };
      setState((s) => ({
        ...s,
        status: "done",
        branch: data.branch,
        prUrl: data.prUrl ?? null,
        result: { ...s.result, ...data.result },
      }));
      es.close();
    });

    es.addEventListener("error", (e) => {
      const data = JSON.parse((e as MessageEvent).data ?? "{}") as { message?: string };
      setState((s) => ({ ...s, status: "error", error: data.message ?? "Stream error" }));
      es.close();
    });

    es.onerror = () => {
      setState((s) =>
        s.status === "running"
          ? { ...s, status: "error", error: "Connection lost" }
          : s
      );
      es.close();
    };
  }, []);

  const stop = useCallback(() => {
    esRef.current?.close();
    setState((s) => ({ ...s, status: "idle" }));
  }, []);

  return { ...state, start, stop };
}
