// hooks/useSSE.ts — SSE subscription hook with exponential-backoff reconnection
"use client";

import { useCallback, useRef, useState } from "react";
import type { TermLine, Phase, AnalysisResult, PhaseStatus } from "@/lib/types";
import { PHASES } from "@/lib/phases";

interface SSEState {
  lines:   TermLine[];
  phases:  Phase[];
  result:  Partial<AnalysisResult>;
  branch:  string | null;
  prUrl:   string | null;
  status:  "idle" | "running" | "done" | "error";
  error:   string | null;
  retries: number;
}

const initialPhases = (): Phase[] =>
  PHASES.map((p) => ({ ...p, status: "pending" as PhaseStatus }));

const BACKOFF_MS  = [1000, 2000, 4000, 8000, 16000, 30000]; // max 30 s
const MAX_RETRIES = 6;

export function useSSE() {
  const esRef        = useRef<EventSource | null>(null);
  const retryTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);
  const repoRef      = useRef<string>("");

  const [state, setState] = useState<SSEState>({
    lines:   [],
    phases:  initialPhases(),
    result:  {},
    branch:  null,
    prUrl:   null,
    status:  "idle",
    error:   null,
    retries: 0,
  });

  const connect = useCallback((repoUrl: string, retryCount: number) => {
    esRef.current?.close();

    const params = new URLSearchParams({ repo: repoUrl });
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

    es.addEventListener("result_update", (e) => {
      const { value } = JSON.parse(e.data) as { value: Partial<AnalysisResult> };
      setState((s) => ({ ...s, result: { ...s.result, ...value } }));
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

    es.addEventListener("error", (e) => {
      const data = JSON.parse((e as MessageEvent).data ?? "{}") as { message?: string };
      setState((s) => ({ ...s, status: "error", error: data.message ?? "Stream error", retries: 0 }));
      es.close();
    });

    es.onerror = () => {
      es.close();
      setState((s) => {
        if (s.status !== "running") return s;

        const nextRetry = retryCount + 1;
        if (nextRetry > MAX_RETRIES) {
          return { ...s, status: "error", error: "Connection lost after max retries" };
        }

        const delay = BACKOFF_MS[Math.min(retryCount, BACKOFF_MS.length - 1)];
        const reconnectMsg: TermLine = {
          type: "system",
          text: `  Connection lost — reconnecting in ${delay / 1000}s… (attempt ${nextRetry}/${MAX_RETRIES})`,
          ts:   Date.now() / 1000,
        };

        // Schedule reconnect — recursive useCallback is safe here (runs async, after init)
        // eslint-disable-next-line react-hooks/immutability
        retryTimeout.current = setTimeout(() => connect(repoRef.current, nextRetry), delay);

        return { ...s, lines: [...s.lines, reconnectMsg], retries: nextRetry };
      });
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const start = useCallback((repoUrl: string) => {
    // Clear any pending retry
    if (retryTimeout.current) { clearTimeout(retryTimeout.current); retryTimeout.current = null; }

    repoRef.current = repoUrl;
    setState({
      lines:   [],
      phases:  initialPhases(),
      result:  {},
      branch:  null,
      prUrl:   null,
      status:  "running",
      error:   null,
      retries: 0,
    });
    connect(repoUrl, 0);
  }, [connect]);

  const stop = useCallback(() => {
    if (retryTimeout.current) { clearTimeout(retryTimeout.current); retryTimeout.current = null; }
    esRef.current?.close();
    setState((s) => ({ ...s, status: "idle", retries: 0 }));
  }, []);

  const { retries: _, ...publicState } = state;
  return { ...publicState, reconnecting: state.status === "running" && state.retries > 0, start, stop };
}
