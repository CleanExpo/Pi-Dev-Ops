// "Needs me" — the Loop Cockpit's list of things waiting on a human.
//
// Extracted from app/(main)/loop/page.tsx so it is unit-testable on its own and
// so that page stays under the 300-line convention.
//
// The observability entries are OBJECTS, not strings. They were typed `string[]`
// and pushed straight into a rendered child, so React threw on the one list whose
// entire job is telling the founder what needs him.

export interface MCAction {
  component?: string;
  status?: string;
  owner?: string;
  severity?: string;
  next_action?: string;
  detail?: string | null;
}

export interface NeedsInputs {
  autonomy?: {
    enabled: boolean;
    stale: boolean;
    poller_iteration_errors: number;
    last_iteration_error: string | null;
  } | null;
  swarm?: { kill_switch_active?: boolean; escalation_lock_active?: boolean } | null;
  actions?: MCAction[];
  nextIssueId?: string | null;
}

export interface NeedItem {
  text: string;
  color: string;
}

const ERROR = "var(--error)";
const WARNING = "var(--warning)";
const MUTED = "var(--text-muted)";

/** One observability row rendered as a single actionable sentence. */
export function actionToNeed(a: MCAction): NeedItem {
  const what = a.next_action || `${a.component ?? "component"} is ${a.status ?? "not observed"}`;
  const which = a.component ? `${a.component}: ` : "";
  const who = a.owner ? ` — owner: ${a.owner}` : "";
  return {
    text: `${which}${what}${who}`,
    color: a.severity === "high" ? ERROR : WARNING,
  };
}

export function deriveNeeds({ autonomy, swarm, actions, nextIssueId }: NeedsInputs): NeedItem[] {
  const needs: NeedItem[] = [];

  if (swarm?.kill_switch_active)
    needs.push({ text: "Kill-switch is ACTIVE — autonomous work is paused", color: ERROR });
  if (swarm?.escalation_lock_active)
    needs.push({ text: "Escalation lock is active — awaiting approver", color: WARNING });
  if (autonomy && autonomy.enabled && autonomy.stale)
    needs.push({ text: "Autonomy poller is stale (>15m since last poll)", color: WARNING });
  if (autonomy && !autonomy.enabled)
    needs.push({ text: "Autonomy poller is disabled (TAO_AUTONOMY_ENABLED=0)", color: WARNING });
  if (autonomy && autonomy.poller_iteration_errors > 0)
    needs.push({
      text:
        `Poller has ${autonomy.poller_iteration_errors} iteration error(s)` +
        (autonomy.last_iteration_error ? `: ${autonomy.last_iteration_error}` : ""),
      color: ERROR,
    });

  for (const a of actions ?? []) needs.push(actionToNeed(a));

  if (nextIssueId) needs.push({ text: `Next queued ticket: ${nextIssueId}`, color: MUTED });

  return needs;
}
