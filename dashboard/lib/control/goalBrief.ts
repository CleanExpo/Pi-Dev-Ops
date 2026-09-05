/** Shared Goal brief rules. Must match `app/server/goal_ticket.py` `_MIN_TEXT`. */

export const MIN_BRIEF = 8;

export function meetsMin(value: string): boolean {
  return value.trim().length >= MIN_BRIEF;
}

export function readyToCreate(draft: {
  title: string;
  description: string;
  audience: string;
}): boolean {
  return meetsMin(draft.title) && meetsMin(draft.description) && meetsMin(draft.audience);
}

export function readyToAnalyze(
  goal: string,
  acceptance: string,
  projectId: string,
): boolean {
  return meetsMin(goal) && meetsMin(acceptance) && Boolean(projectId.trim());
}

export function remainingHint(value: string, label: string): string {
  const n = value.trim().length;
  if (n >= MIN_BRIEF) return `${label} · ready`;
  if (n === 0) return `${label} · required · ${MIN_BRIEF}+ characters`;
  return `${label} · ${MIN_BRIEF - n} more characters`;
}
