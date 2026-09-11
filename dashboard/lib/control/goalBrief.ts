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

export function hasBrief(projectId: string): boolean {
  return Boolean(projectId.trim());
}

export function readyToAnalyze(
  goal: string,
  acceptance: string,
  projectId: string,
): boolean {
  return meetsMin(goal) && meetsMin(acceptance) && hasBrief(projectId);
}

const VAGUE_ACCEPTANCE = new Set([
  "it works",
  "done",
  "works",
  "ok",
  "looks good",
  "as expected",
  "finished",
  "complete",
  "all good",
  "good",
]);

const OBSERVE = /see|show|click|open|refresh|appear|remain|display|visible|error|fail|save|list|return|load|stay|keep|empty|message|select|type|press/i;

export function acceptanceHint(value: string): string {
  const text = value.trim();
  if (!meetsMin(text)) return "";
  const bare = text.toLowerCase().replace(/[.!]+$/g, "");
  if (VAGUE_ACCEPTANCE.has(bare)) {
    return "Say what a stranger sees or does. “It works” is not enough.";
  }
  if (!OBSERVE.test(text)) {
    return "Name what a stranger sees or clicks to know this is done.";
  }
  return "";
}

export function acceptanceLabel(value: string): string {
  return acceptanceHint(value) || remainingHint(value, "Acceptance");
}

export function acceptanceReady(value: string): boolean {
  return meetsMin(value) && !acceptanceHint(value);
}

export function draftReady(ticket: {
  title: string;
  goal: string;
  acceptance: string;
  selected?: boolean;
}): boolean {
  return meetsMin(ticket.title) && meetsMin(ticket.goal) && acceptanceReady(ticket.acceptance);
}

export function readyToFile(
  tickets: Array<{ title: string; goal: string; acceptance: string; selected: boolean }>,
): boolean {
  const chosen = tickets.filter((ticket) => ticket.selected);
  return chosen.length > 0 && chosen.every(draftReady);
}

export function ticketsToFile<T extends {
  selected: boolean;
  title: string;
  landed_identifier?: string;
}>(
  tickets: T[],
  filed: Array<{ identifier: string; title: string }>,
): T[] {
  const ids = new Set(filed.map((ticket) => ticket.identifier).filter(Boolean));
  return tickets.filter((ticket) => {
    if (!ticket.selected) return false;
    if (ticket.landed_identifier && ids.has(ticket.landed_identifier)) return false;
    return !filed.some(
      (row) => row.identifier && row.title.trim() === ticket.title.trim(),
    );
  });
}

export function remainingHint(value: string, label: string): string {
  const n = value.trim().length;
  if (n === 0 || n >= MIN_BRIEF) return label;
  return `${label} · ${MIN_BRIEF - n} more`;
}
