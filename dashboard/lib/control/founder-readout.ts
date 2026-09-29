import type { MissionControlLive } from "./mission-control-live";

export interface FounderAnswer {
  question: string;
  answer: string;
  detail: string;
  source: string;
  href: string;
}

const LIVE_SOURCE = "/api/pi-ceo/api/mission-control/live";
const UNKNOWN = "Unknown — current evidence is unavailable.";
const row = (question: string, answer: string, detail: string, source: string, href = LIVE_SOURCE): FounderAnswer =>
  ({ question, answer, detail, source, href });

export function founderReadout(live: MissionControlLive | null, now = Date.now()): FounderAnswer[] {
  const age = live?.ts ? now - Date.parse(live.ts) : NaN;
  const fresh = Boolean(live && !live.error && Number.isFinite(age) && age >= -30_000 && age <= 90_000);
  const sessions = fresh && Array.isArray(live?.active_sessions) ? live.active_sessions : null;
  const queue = fresh ? live?.queue : null;
  const next = queue?.next_issue_id;
  const actions = fresh && Array.isArray(live?.observability?.actions) ? live.observability.actions : null;
  const fault = actions?.find((action) => action.observed === true && action.ok === false);
  const intake = fresh ? live?.idea_pipeline : null;
  const waiting = typeof intake?.awaiting === "number" && Number.isInteger(intake.awaiting) && intake.awaiting > 0
    ? intake.awaiting : null;

  return [
    row("Where are we?", sessions ? `${sessions.length} active Pi build ${sessions.length === 1 ? "session" : "sessions"} observed.` : UNKNOWN,
      sessions ? "This is the Pi session feed, not a measure of work across every machine." : "No fresh session reading.", "Pi session feed"),
    row("What matters now?", typeof next === "string" && next.trim() ? `${next} · ${queue?.next_issue_title || "Next queue item"}` : UNKNOWN,
      next ? "Claimable queue candidate; priority and authority still need review." : "No verified next item in this reading.", "Claimable queue"),
    row("What is hard?", fault?.component ? `${fault.component}: ${fault.status || "needs attention"}` : UNKNOWN,
      fault?.next_action || "No observed fault with a named recovery action in this reading; silence is not green.", "Health observations"),
    row("What needs Phill's decision?", waiting ? `${waiting} ${waiting === 1 ? "idea awaits" : "ideas await"} disposition.` : UNKNOWN,
      waiting ? "The idea inbox is one decision source; other approvals may exist." : "No complete founder decision register is connected.", "Idea pipeline", "#idea-pipeline"),
    row("What was truly shipped?", UNKNOWN,
      "This feed records build completions, not an independently verified customer release. Deployment and outcome receipts are required.", "Release evidence missing"),
  ];
}
