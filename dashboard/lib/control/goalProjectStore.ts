export const GOAL_BRIEF_ID_KEY = "pi-ceo.control.goal-brief-id";

export function readGoalBriefId(): string {
  if (typeof window === "undefined") return "";
  try {
    return (window.localStorage.getItem(GOAL_BRIEF_ID_KEY) || "").trim();
  } catch {
    return "";
  }
}

export function writeGoalBriefId(id: string): void {
  if (typeof window === "undefined") return;
  try {
    const trimmed = id.trim();
    if (!trimmed) {
      window.localStorage.removeItem(GOAL_BRIEF_ID_KEY);
      return;
    }
    window.localStorage.setItem(GOAL_BRIEF_ID_KEY, trimmed);
  } catch {
    return;
  }
}
