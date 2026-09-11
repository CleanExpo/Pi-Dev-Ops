import { hasBrief, meetsMin, readyToCreate, readyToFile } from "@/lib/control/goalBrief";

export const CONTROL_GOAL_CTA = "Goal → Linear";

export const LINEAR_DEST_NOTE =
  "These tickets write to the CleanExpo/Pi-Dev-Ops Linear Backlog.";

export const CHILD_TICKETS_NOTE =
  "Each sub-task becomes a child Linear ticket under its parent.";

export const TWO_PROJECTS_NOTE =
  "This list is product briefs. The repo in the top bar is a different picker.";

export const PROJECT_KEPT_NOTE = "Brief kept. Write the next goal, or start another.";

export const ANALYZE_STAGE_NOTE = "Drafts first. Linear only after you confirm.";

export const MORE_ANALYSIS = "More analysis";
export const LESS_ANALYSIS = "Hide analysis";

export const FALLBACK_DRAFT_NOTE =
  "This is a fallback draft. Analyze could not finish a plan. Edit the ticket so a stranger can test it, or discard and rewrite the goal. Linear is not written yet.";

export const BRIEFS_EMPTY_NOTE =
  "No briefs yet. Press Create brief — product name, what it is, and who it is for.";

export const BRIEFS_LOAD_FAIL_NOTE =
  "Briefs could not be loaded. Press Try again, or Create brief.";

export const BRIEF_NOT_CREATED_NOTE =
  "The brief was not created. Check the three required fields and try again.";

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

export function nextAnalyzeHint(
  goal: string,
  acceptance: string,
  projectId: string,
): string {
  if (!hasBrief(projectId)) return "Select a brief, or press Create brief.";
  if (!meetsMin(goal)) return "Write the goal — what must exist when this is done.";
  if (!meetsMin(acceptance)) return "Write acceptance — how a stranger can tell this is done.";
  return ANALYZE_STAGE_NOTE;
}

export function nextSaveBriefHint(draft: {
  title: string;
  description: string;
  audience: string;
}): string {
  if (readyToCreate(draft)) return "Save the brief, then write the goal.";
  if (!meetsMin(draft.title)) return "Write the product name (8+ characters), then Save brief.";
  if (!meetsMin(draft.description)) return "Write what this product is (8+ characters), then Save brief.";
  return "Write who it is for (8+ characters), then Save brief.";
}

export function nextWriteHint(
  tickets: Array<{ title: string; goal: string; acceptance: string; selected: boolean }>,
): string {
  const chosen = tickets.filter((ticket) => ticket.selected);
  if (chosen.length === 0) {
    return "Select at least one ticket, or discard and rewrite the goal.";
  }
  if (!readyToFile(tickets)) {
    return "Each selected ticket needs a title, goal, and acceptance of 8+ characters.";
  }
  return "Draft only — nothing has been written to Linear. Press Write to Linear when the tickets are right.";
}
