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

export function draftReady(ticket: {
  title: string;
  goal: string;
  acceptance: string;
  selected?: boolean;
}): boolean {
  return meetsMin(ticket.title) && meetsMin(ticket.goal) && meetsMin(ticket.acceptance);
}

export function readyToFile(
  tickets: Array<{ title: string; goal: string; acceptance: string; selected: boolean }>,
): boolean {
  const chosen = tickets.filter((ticket) => ticket.selected);
  return chosen.length > 0 && chosen.every(draftReady);
}

export function skipFiledTitles(
  tickets: Array<{ title: string; selected: boolean }>,
  filedTitles: Iterable<string>,
): string[] {
  const landed = new Set(
    [...filedTitles].map((title) => title.trim()).filter(Boolean),
  );
  return tickets
    .filter((ticket) => ticket.selected && landed.has(ticket.title.trim()))
    .map((ticket) => ticket.title.trim());
}

export function remainingHint(value: string, label: string): string {
  const n = value.trim().length;
  if (n >= MIN_BRIEF) return `${label} · ready`;
  if (n === 0) return `${label} · required · ${MIN_BRIEF}+ characters`;
  return `${label} · ${MIN_BRIEF - n} more characters`;
}
