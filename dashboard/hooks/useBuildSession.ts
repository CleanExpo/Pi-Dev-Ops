"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchProxy } from "@/lib/pi-ceo-fetch";
import type { TermLine } from "@/lib/types";

type State = {
  lines: TermLine[]; status: "idle" | "running" | "done" | "error";
  error: string | null; sessionId: string | null; sessionStatus: string;
};
const initial: State = { lines: [], status: "idle", error: null, sessionId: null, sessionStatus: "" };
const terminal = new Set(["done", "complete", "failed", "killed", "blocked", "stalled", "interrupted", "error"]);
type Observation = { disposed: boolean; stream?: EventSource; timer?: ReturnType<typeof setInterval>; requests: Set<AbortController> };

/** A build is launched once; reconnecting observation must never launch more work. */
export function useBuildSession() {
  const [state, setState] = useState<State>(initial);
  const active = useRef<Observation | null>(null);
  const sid = useRef<string | null>(null);
  const stopping = useRef(false);
  const dispose = useCallback(() => {
    const run = active.current;
    if (!run) return;
    run.disposed = true;
    run.stream?.close();
    clearInterval(run.timer);
    for (const request of run.requests) request.abort();
    active.current = null;
  }, []);
  useEffect(() => dispose, [dispose]);

  const start = useCallback(async (repo: string, brief = "") => {
    if (active.current) return;
    const run: Observation = { disposed: false, requests: new Set<AbortController>() };
    active.current = run;
    sid.current = null;
    setState({ ...initial, status: "running", sessionStatus: "Requesting build" });
    async function request(url: string, options?: RequestInit) {
      const controller = new AbortController();
      run.requests.add(controller);
      const timeout = setTimeout(() => controller.abort(), 10_000);
      try {
        const result = await fetchProxy<Record<string, unknown>>(url, { ...options, signal: controller.signal });
        if (!result.ok) throw new Error("Backend request unavailable");
        return result.data;
      } finally { clearTimeout(timeout); run.requests.delete(controller); }
    }
    try {
      const receipt = await request("/api/build", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ repo_url: repo, brief }),
      });
      if (run.disposed) return;
      if (typeof receipt?.session_id !== "string" || !/^[a-zA-Z0-9_-]+$/.test(receipt.session_id)) {
        throw new Error("Invalid build session receipt. Inspect Builds before retrying.");
      }
      const id: string = receipt.session_id;
      sid.current = id;
      setState(s => ({ ...s, sessionId: id, sessionStatus: "Checking session status" }));
      const stream = new EventSource(`/api/pi-ceo/api/sessions/${id}/logs`);
      run.stream = stream;
      stream.onmessage = event => {
        if (run.disposed) return;
        try {
          const line = JSON.parse(event.data);
          if (line.type === "done" || line.type === "closed") { stream.close(); return; }
          if (typeof line.text !== "string") return;
          const type: TermLine["type"] = ["phase", "tool", "agent", "success", "error", "system", "output"].includes(line.type) ? line.type : "output";
          setState(s => ({ ...s, lines: [...s.lines.slice(-1999), { type, text: line.text, ts: typeof line.ts === "number" ? line.ts : Date.now() / 1000 }] }));
        } catch { /* Keepalives and malformed logs are not outcome evidence. */ }
      };
      stream.onerror = () => { stream.close(); };
      let pending = false;
      async function poll() {
        if (pending || run.disposed) return;
        pending = true;
        try {
          const sessions = await request("/api/sessions", { cache: "no-store" });
          if (run.disposed) return;
          const session = Array.isArray(sessions) ? sessions.find(s => s?.id === id) : null;
          if (!session || typeof session.status !== "string") throw new Error("Session status unavailable");
          const done = session.status === "done" || session.status === "complete";
          const ended = terminal.has(session.status);
          setState(s => ({ ...s, status: done ? "done" : ended ? "error" : "running",
            sessionStatus: done ? "Reported complete" : session.status,
            error: ended && !done ? `Session ended: ${session.status}` : null }));
          if (ended) dispose();
        } catch {
          if (!run.disposed) setState(s => ({ ...s, sessionStatus: "Status unknown", error: "Session status unavailable. Inspect Builds before starting another build." }));
        } finally { pending = false; }
      }
      run.timer = setInterval(() => { void poll(); }, 4000);
      void poll();
    } catch (error) {
      if (!run.disposed) {
        const detail = error instanceof Error ? error.message : "Build request failed";
        setState(s => ({ ...s, status: "error", sessionStatus: "Launch unconfirmed", error: `${detail} Inspect Builds before retrying; launch was not confirmed.` }));
        dispose();
      }
    }
  }, [dispose]);

  const stop = useCallback(async () => {
    if (!sid.current || stopping.current || !active.current) return;
    stopping.current = true;
    const run = active.current;
    const controller = new AbortController();
    run.requests.add(controller);
    const timeout = setTimeout(() => controller.abort(), 10_000);
    try {
      const response = await fetch(`/api/pi-ceo/api/sessions/${sid.current}/kill`, { method: "POST", signal: controller.signal });
      const body = await response.json();
      if (!response.ok || body?.ok !== true) throw new Error("Cancellation not confirmed; check Builds.");
      if (!run.disposed) { setState(s => ({ ...s, status: "idle", sessionStatus: "Cancellation requested", error: null })); dispose(); }
    } catch (error) {
      if (!run.disposed) setState(s => ({ ...s, error: error instanceof Error ? error.message : "Cancellation failed" }));
    } finally { clearTimeout(timeout); run.requests.delete(controller); stopping.current = false; }
  }, [dispose]);

  return { ...state, start, stop };
}
