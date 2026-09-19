"use client";
import { useEffect, useState } from "react";
import { fetchProxyJSON } from "@/lib/pi-ceo-fetch";
import { parseOperatorHealth, parseOperatorSessions, type OperatorHealth, type OperatorSession } from "@/lib/operator-status";

export function useOperatorObservations() {
  const [health, setHealth] = useState<OperatorHealth | null>(null);
  const [sessions, setSessions] = useState<OperatorSession[]>([]);
  const [healthError, setHealthError] = useState(false);
  const [sessionsError, setSessionsError] = useState(false);
  const [sessionsLoaded, setSessionsLoaded] = useState(false);
  const [checkedAt, setCheckedAt] = useState<string | null>(null);

  useEffect(() => {
    let disposed = false;
    let pending = false;
    let controller: AbortController | null = null;
    async function loadHealth(signal: AbortSignal) {
      try {
        const data = parseOperatorHealth(await fetchProxyJSON("/health", { cache: "no-store", signal }));
        if (!disposed) { setHealth(data); setHealthError(!data); }
      } catch { if (!disposed) { setHealth(null); setHealthError(true); } }
    }
    async function loadSessions(signal: AbortSignal) {
      try {
        const data = parseOperatorSessions(await fetchProxyJSON("/api/sessions", { cache: "no-store", signal }));
        if (!disposed) { setSessions(data ?? []); setSessionsError(!data); setSessionsLoaded(true); }
      } catch { if (!disposed) { setSessions([]); setSessionsError(true); setSessionsLoaded(true); } }
    }
    async function load() {
      if (pending) return;
      pending = true;
      const request = new AbortController();
      controller = request;
      const timeout = setTimeout(() => request.abort(), 10_000);
      await Promise.all([loadHealth(request.signal), loadSessions(request.signal)]);
      clearTimeout(timeout);
      if (!disposed) setCheckedAt(new Date().toLocaleTimeString());
      pending = false;
    }
    void load();
    const timer = setInterval(() => { void load(); }, 15_000);
    return () => { disposed = true; controller?.abort(); clearInterval(timer); };
  }, []);

  return { health, sessions, healthError, sessionsError, sessionsLoaded, checkedAt };
}
