// Queue and pulse tiles for LiveActivityFeed, plus the shared UNAVAILABLE mark.
//
// The backend reports a failed Linear read as `available: false` + `error`
// with null counts (app/server/routes/mission_control.py). These tiles render
// that as UNAVAILABLE with the reason. They used to render `?? 0`, which made
// a rate-limited or broken Linear read look like an empty, quiet queue.
"use client";

import { fmtAgo } from "@/lib/control/activity-format";
import { unavailableReason, type MCPulse, type MCQueue } from "@/lib/control/mission-control-live";
import { watchLoopHref } from "@/lib/control/watchWork";

export function Unavailable({ reason }: { reason: string }) {
  return (
    <div>
      <span className="text-xl font-semibold text-rose-300">UNAVAILABLE</span>
      <div className="text-xs text-text-muted mt-1">{reason}</div>
    </div>
  );
}

export function QueueTile({ queue }: { queue: MCQueue | undefined }) {
  const down = unavailableReason(queue);
  return (
    <div>
      <div className="text-xs uppercase text-text-muted mb-1">Linear queue</div>
      {down ? <Unavailable reason={down} /> : (
        <>
          <div className="flex items-baseline gap-3">
            <div>
              <span className="text-3xl font-bold text-rose-400 tabular-nums">{queue?.urgent ?? 0}</span>
              <span className="text-xs text-text-muted ml-1">urgent</span>
            </div>
            <div>
              <span className="text-2xl font-semibold text-amber-400 tabular-nums">{queue?.high ?? 0}</span>
              <span className="text-xs text-text-muted ml-1">high</span>
            </div>
          </div>
          {queue?.next_issue_id && (
            <div className="text-xs text-text-muted mt-2 truncate">
              next:{" "}
              <a href={watchLoopHref()} className="font-mono text-cyan-400 hover:underline">
                {queue.next_issue_id}
              </a>{" "}
              {queue.next_issue_title}
            </div>
          )}
        </>
      )}
    </div>
  );
}

export function PulseTile({ pulse }: { pulse: MCPulse | undefined }) {
  const down = unavailableReason(pulse);
  return (
    <div>
      <div className="text-xs uppercase text-text-muted mb-1">Pulse heartbeat</div>
      {down ? <Unavailable reason={down} /> : (
        <>
          <div className="flex items-baseline gap-2">
            <span className="text-3xl font-bold text-emerald-400 tabular-nums">{pulse?.comments_today ?? 0}</span>
            <span className="text-xs text-text-muted">comments today</span>
          </div>
          <div className="text-xs text-text-muted mt-1">
            last: <span className="font-mono">{fmtAgo(pulse?.last_at ?? null)}</span>
            {pulse?.pulse_issue_id && <span className="ml-2 text-text-muted">→ {pulse.pulse_issue_id}</span>}
          </div>
        </>
      )}
    </div>
  );
}
