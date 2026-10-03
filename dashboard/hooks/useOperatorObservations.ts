"use client";
import { useSource } from "@/lib/boards/sources";
import { parseOperatorHealth, parseOperatorSessions } from "@/lib/operator-status";

// RA-7898: /health and /api/sessions come from the shared pollers (`pi-health`,
// `sessions`, 15 s each, through fetchProxy). A null value is the proxy's
// placeholder or a failed read, so it is an error, never "no sessions".
export function useOperatorObservations() {
  const healthSource = useSource<unknown>("pi-health");
  const sessionsSource = useSource<unknown>("sessions");
  const health = healthSource.seq > 0 ? parseOperatorHealth(healthSource.value) : null;
  const healthError = healthSource.seq > 0 && !health;
  const parsedSessions = sessionsSource.seq > 0 ? parseOperatorSessions(sessionsSource.value) : null;
  const sessions = parsedSessions ?? [];
  const sessionsError = sessionsSource.seq > 0 && !parsedSessions;
  const sessionsLoaded = sessionsSource.seq > 0;
  const bothRead = healthSource.fetchedAt !== null && sessionsSource.fetchedAt !== null;
  const checkedAt = bothRead
    ? new Date(Math.max(healthSource.fetchedAt ?? 0, sessionsSource.fetchedAt ?? 0)).toLocaleTimeString()
    : null;

  return { health, sessions, healthError, sessionsError, sessionsLoaded, checkedAt };
}
