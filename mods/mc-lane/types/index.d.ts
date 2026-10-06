// mc-lane's $.state contract (docs/reference/claude-mods/interface.md, "Declare the values").
// Values here survive a reload of the hooks module; see hooks/register.ts "HOT RELOAD".
// McLaneEvent mirrors LaneEvent in hooks/lane.ts — keep them equal. This file stands
// alone: with an `import` from ../hooks, `claude plugin validate` (2.1.289) found no
// declared state.

export type McLaneEvent = {
  session_id: string
  seq: number
  kind: 'session_start' | 'tool' | 'agent_start' | 'usage' | 'session_end'
  at: string
  repo?: string
  model?: string
  tool?: string
  ok?: boolean
  ms?: number
  ctx_pct?: number
  rate_pct?: number
  cost_usd?: number
}

declare module 'claude-code' {
  interface PluginState {
    'mc-lane': {
      /** Events not yet acked by Mission Control, oldest first (capped at MAX_QUEUE). */
      queue: McLaneEvent[]
      /** Per-session event counter, the low digits of each seq. */
      counter: number
      /** The session whose session_start is recorded; '' until then. */
      started: string
    }
  }
}
