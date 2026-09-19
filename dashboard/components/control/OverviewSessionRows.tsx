import { repoShort, skillFromPhase, statusDot } from "@/lib/control/overview-format";
import { sessionTime, type OperatorSession } from "@/lib/operator-status";

export function AgentCard({ session }: { session: OperatorSession }) {
  const live = ["cloning", "building", "evaluating", "created"].includes(session.status);
  return (
    <div
      className="flex items-start gap-3 px-3 py-2.5 rounded-lg"
      style={{
        background: "var(--panel)",
        border: `1px solid ${live ? "var(--accent)" : "var(--border)"}`,
        opacity: live ? 1 : 0.65,
      }}
    >
      <div className="flex flex-col items-center gap-1 pt-0.5">
        <span
          className="w-2 h-2 rounded-full shrink-0"
          style={{ background: statusDot(session.status) }}
        />
        {live && (
          <span
            className="text-[8px] font-semibold uppercase tracking-wider"
            style={{ color: "var(--accent)" }}
          >
            LIVE
          </span>
        )}
      </div>
      <div className="flex-1 min-w-0">
        <p className="text-xs font-medium truncate" style={{ color: "var(--text)" }}>
          {repoShort(session.repo)}
        </p>
        <p className="text-[10px] mt-0.5" style={{ color: "var(--text-muted)" }}>
          {skillFromPhase(session.last_phase)}
          {session.evaluator_score !== undefined && session.evaluator_score > 0 && (
            <span style={{ color: session.evaluator_score >= 8 ? "var(--success)" : "var(--text-dim)" }}>
              {" "}· {session.evaluator_score}/10
            </span>
          )}
        </p>
      </div>
      <span
        className="text-[9px] font-mono shrink-0 mt-0.5"
        style={{ color: "var(--text-dim)" }}
      >
        {session.id.slice(0, 6)}
      </span>
    </div>
  );
}

export function ActivityRow({ session, index }: { session: OperatorSession; index: number }) {
  const ts = new Date(sessionTime(session.started));
  const timeStr = ts.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  const live = ["cloning", "building", "evaluating", "created"].includes(session.status);

  return (
    <div
      className="flex items-center gap-3 px-3 py-2 text-xs font-mono"
      style={{
        borderBottom: "1px solid var(--border)",
        background: index % 2 === 0 ? "transparent" : "rgba(255,255,255,0.01)",
      }}
    >
      <span className="shrink-0 w-10 text-right" style={{ color: "var(--text-dim)" }}>
        {timeStr}
      </span>
      <span
        className="w-1.5 h-1.5 rounded-full shrink-0"
        style={{ background: statusDot(session.status) }}
      />
      <span className="flex-1 truncate" style={{ color: "var(--text-muted)" }}>
        {repoShort(session.repo)}
      </span>
      <span
        className="shrink-0 text-[9px] px-1.5 py-0.5 rounded uppercase tracking-wide"
        style={{
          background: live ? "rgba(249,115,22,0.12)" : "transparent",
          color: live ? "var(--accent)" : "var(--text-dim)",
          border: `1px solid ${live ? "var(--accent)" : "var(--border)"}`,
        }}
      >
        {["complete", "done"].includes(session.status) ? "Reported complete" : session.status}
      </span>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────────────
