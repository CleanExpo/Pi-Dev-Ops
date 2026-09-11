import type { FiledTicket } from "@/lib/control/goalErrors";

export const GOAL_FILED_KEY = "pi-ceo.control.goal-filed";

function valid(ticket: FiledTicket): boolean {
  return Boolean(ticket.identifier && ticket.url);
}

export function readGoalFiled(): FiledTicket[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.sessionStorage.getItem(GOAL_FILED_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as FiledTicket[];
    return Array.isArray(parsed) ? parsed.filter(valid) : [];
  } catch {
    return [];
  }
}

export function writeGoalFiled(tickets: FiledTicket[]): void {
  if (typeof window === "undefined") return;
  try {
    const next = tickets.filter(valid);
    if (next.length === 0) {
      window.sessionStorage.removeItem(GOAL_FILED_KEY);
      return;
    }
    window.sessionStorage.setItem(GOAL_FILED_KEY, JSON.stringify(next));
  } catch {
    return;
  }
}
