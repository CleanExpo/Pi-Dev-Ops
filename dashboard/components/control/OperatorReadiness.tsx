import Link from "next/link";
import { repoShort } from "@/lib/control/overview-format";
import { automationLabel, needsAttention, sessionTime, type OperatorHealth, type OperatorSession } from "@/lib/operator-status";

function StatChip({ label, value, warning = false }: { label: string; value: string; warning?: boolean }) {
  return (
    <div className="flex flex-col gap-1 p-3 rounded-lg" style={{ background: "var(--panel)", border: "1px solid var(--border)" }}>
      <span className="text-[10px] font-semibold uppercase tracking-widest" style={{ color: "var(--text-dim)" }}>{label}</span>
      <span className="text-sm font-semibold" style={{ color: warning ? "var(--warning)" : "var(--text)" }}>{value}</span>
    </div>
  );
}

function SessionRow({ session }: { session: OperatorSession }) {
  const time = sessionTime(session.started);
  const completed = ["complete", "done"].includes(session.status);
  return (
    <div className="flex flex-wrap items-start justify-between gap-2 py-3" style={{ borderBottom: "1px solid var(--border)" }}>
      <div className="min-w-0 flex-1">
        <p className="text-sm break-words" style={{ color: "var(--text)" }}>{repoShort(session.repo)}</p>
        <p className="text-xs mt-1" style={{ color: "var(--text-muted)" }}>
          {session.last_phase ?? "Phase unknown"} · {session.id.slice(0, 8)} · {Number.isFinite(time) ? new Date(time).toLocaleString() : "Time unknown"}
        </p>
      </div>
      <span className="text-xs" style={{ color: needsAttention(session.status) ? "var(--warning)" : "var(--text-muted)" }}>
        {completed ? "Reported complete" : session.status}
      </span>
    </div>
  );
}

export function OperatorReadiness({ health, sessions, healthError, sessionsError }: { health: OperatorHealth | null; sessions: OperatorSession[]; healthError: boolean; sessionsError: boolean }) {
  const attentionSessions = sessions.filter(s => needsAttention(s.status));
  const automation = automationLabel(health);
  const generationBlocked = health?.generation?.status === "blocked";
  const readiness = attentionSessions.length ? "Work blocked" : generationBlocked ? "Generation blocked" : automation === "Paused" ? "Automation paused" : "Readiness unknown";

  return <>
      <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-4 gap-3 p-4" aria-live="polite">
        <StatChip label="Service" value={healthError ? "Service status unavailable" : health ? health.status === "ok" ? "Service reachable" : "Service degraded" : "Checking service"} warning={healthError || Boolean(health && health.status !== "ok")} />
        <StatChip label="Operations" value={readiness} warning={attentionSessions.length > 0 || generationBlocked} />
        <StatChip label="Delivery" value="Delivery not verified" />
        <StatChip label="Model usage" value="Billing not observed" />
      </div>
      <p className="px-4 pb-4 text-xs" style={{ color: "var(--text-muted)" }}>
        Service reachability and an armed loop do not verify readiness. Completed sessions need commit, review and deployment evidence. Model identity and billing route are not reported here.
      </p>

      {(attentionSessions.length > 0 || sessionsError) && (
        <section aria-labelledby="attention-title" className="mx-4 mb-4 p-4 rounded-lg" style={{ background: "var(--panel)", border: "1px solid var(--warning)" }}>
          <h2 id="attention-title" className="text-sm font-semibold mb-2" style={{ color: "var(--warning)" }}>Needs attention</h2>
          {sessionsError && <p className="text-xs" style={{ color: "var(--warning)" }}>Session status unavailable</p>}
          {attentionSessions.map(s => (
            <div key={s.id}>
              <SessionRow session={s} />
              <Link href="/builds" className="inline-block py-2 text-xs underline" style={{ color: "var(--accent)" }}>Inspect build logs and recovery →</Link>
            </div>
          ))}
          <p className="mt-2 text-xs" style={{ color: "var(--text-muted)" }}>Inspect the last successful phase and failure details before resuming work.</p>
          {sessionsError && <Link href="/settings" className="inline-block mt-2 text-xs underline" style={{ color: "var(--accent)" }}>Check service connection →</Link>}
        </section>
      )}

      <div className="px-4 pb-4 text-xs" style={{ color: "var(--text-muted)" }}>
        <p>Generation: <span>{health?.generation?.status ?? "Unknown"}</span></p>
        {health?.generation?.blockers.map(reason => <p key={reason} style={{ color: "var(--warning)" }}>{reason}</p>)}
        {health?.model_documentation && <><p>Model documentation: <span>{health.model_documentation.status}</span></p><p>Documentation freshness does not verify model availability or subscription access.</p></>}
      </div>
  </>;
}
