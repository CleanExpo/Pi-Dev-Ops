export const CONTROL_GOAL_CTA = "Goal → Linear";

export const LINEAR_DEST_NOTE =
  "These tickets write to the CleanExpo/Pi-Dev-Ops Linear Backlog.";

export const CHILD_TICKETS_NOTE =
  "Each sub-task becomes a child Linear ticket under its parent.";

export const TWO_PROJECTS_NOTE =
  "This list is product briefs. The repo in the top bar is a different picker.";

export const PROJECT_KEPT_NOTE = "Brief kept. Write the next goal, or start another.";

export const ANALYZE_STAGE_NOTE = "Drafts first. Linear only after you confirm.";

export const HOW_TO_GET_THE_GOAL = [
  "Create a brief first: product name, what it is, who it is for. Add More context only when it changes the tickets.",
  "Write the goal as the thing that must exist when this is done — one outcome, not a wish list.",
  "Write acceptance as how a stranger can tell it is done, without asking you. If they would have to guess, rewrite it.",
  "Analyze. This only drafts. Linear is not written. If the drafts miss the requirement, discard and rewrite the goal.",
  "Read every draft. Uncheck anything that is not this goal. Rewrite vague titles and acceptance. Sub-tasks you edit become child tickets.",
  "Write to Linear. Confirm once. Open each link. If a stranger cannot test the acceptance, rewrite the ticket — do not treat it as done.",
  "If a write stops halfway, already-landed tickets stay marked. Write the rest. Keep the brief and start the next goal.",
];

export function analyzingCopy(seconds: number): string {
  if (seconds < 8) return "Reading the brief. Linear is not written.";
  if (seconds < 25) return "Breaking the goal into tickets. Linear is not written.";
  if (seconds < 50) return "Still drafting tickets. Linear is not written.";
  return "Finishing the drafts. Linear is not written.";
}

export function analyzeProgress(seconds: number): number {
  return Math.min(99, Math.round((seconds / 70) * 100));
}
