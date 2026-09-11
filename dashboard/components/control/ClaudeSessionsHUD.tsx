// ClaudeSessionsHUD.tsx — Claude Code session token/context usage, VS-Code-style.
//
// Reads `claude_hud` off the same /api/mission-control/live payload
// LiveActivityFeed already polls every 5s (see app/server/claude_session_hud.py).
// Renders one bar per LIVE Claude Code session on the backend's own host: percent
// of context window used, and the stage the context-ceiling hook itself assigned
// (ok / handoff / hard) — the same thresholds shown on the terminal status line.
//
// HONESTY: `available: false` (wrong host, directory absent/unreadable) renders a
// distinct "can't see this host's sessions" state — never collapsed into "0
// sessions running", which is what RA-1109's surface-treatment ban exists to stop.

export interface ClaudeHudSession {
  session_id: string;
  project: string | null;
  stage: string | null;
  pct: number | null;
  used_tokens: number | null;
  window: number | null;
  age_s: number;
}

export interface ClaudeHud {
  available: boolean;
  reason: string | null;
  checked_dir: string;
  sessions: ClaudeHudSession[];
  counts: { live: number; handoff: number; hard: number };
}

function stageColor(stage: string | null): string {
  if (stage === "hard") return "bg-rose-500";
  if (stage === "handoff") return "bg-amber-500";
  if (stage === "ok") return "bg-emerald-500";
  return "bg-slate-600"; // turn-zero / estimator-unavailable / unknown
}

function stageLabel(stage: string | null): string {
  if (stage === "hard" || stage === "handoff" || stage === "ok") return stage;
  if (stage === "turn-zero") return "starting";
  if (stage === "estimator-unavailable") return "no estimate";
  return "unknown";
}

function SessionBar({ s }: { s: ClaudeHudSession }) {
  const pct = typeof s.pct === "number" ? Math.min(100, Math.max(0, s.pct)) : null;
  return (
    <div className="py-2 px-3 rounded bg-slate-900/50 border border-slate-800">
      <div className="flex items-center gap-2 mb-1.5">
        <span className="text-sm text-slate-200 font-medium truncate">
          {s.project ?? "unknown project"}
        </span>
        <span
          className={`px-1.5 py-0.5 rounded text-[11px] font-mono text-white ${stageColor(s.stage)}`}
        >
          {stageLabel(s.stage)}
        </span>
        <span className="ml-auto text-xs text-text-muted tabular-nums">
          {pct !== null ? `${pct.toFixed(1)}%` : "—"}
        </span>
      </div>
      <div className="h-1.5 w-full rounded bg-slate-800 overflow-hidden">
        <div
          className={`h-full ${stageColor(s.stage)}`}
          style={{ width: pct !== null ? `${pct}%` : "0%" }}
        />
      </div>
      {s.used_tokens !== null && s.window !== null && (
        <div className="text-[11px] text-text-muted mt-1 tabular-nums">
          {s.used_tokens.toLocaleString()} / {s.window.toLocaleString()} tokens
        </div>
      )}
    </div>
  );
}

export default function ClaudeSessionsHUD({ data }: { data: ClaudeHud | undefined }) {
  if (!data) return null;

  return (
    <div className="p-4 border-b border-slate-800">
      <div className="text-xs uppercase text-text-muted mb-2 flex items-center gap-2">
        Claude Code sessions
        <span className="px-1.5 py-0.5 bg-slate-800 rounded text-slate-300 tabular-nums">
          {data.counts.live}
        </span>
        {data.counts.hard > 0 && (
          <span className="px-1.5 py-0.5 bg-rose-500/20 text-rose-300 rounded">
            {data.counts.hard} at hard stop
          </span>
        )}
        {data.counts.handoff > 0 && (
          <span className="px-1.5 py-0.5 bg-amber-500/20 text-amber-300 rounded">
            {data.counts.handoff} approaching handoff
          </span>
        )}
      </div>

      {!data.available ? (
        <div className="text-sm text-text-muted italic">
          Can&apos;t see this host&apos;s sessions — {data.reason} ({data.checked_dir}).
        </div>
      ) : data.sessions.length === 0 ? (
        <div className="text-sm text-text-muted italic">
          No Claude Code session active on this host in the last 10 minutes.
        </div>
      ) : (
        <div className="space-y-2">
          {data.sessions.map((s) => (
            <SessionBar key={s.session_id} s={s} />
          ))}
        </div>
      )}
    </div>
  );
}
