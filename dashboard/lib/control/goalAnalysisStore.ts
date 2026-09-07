import type { AnalysisPayload } from "@/components/control/GoalDraftReview";

export const GOAL_ANALYSIS_KEY = "pi-ceo.control.goal-analysis";

export interface StoredGoalAnalysis {
  goal: string;
  acceptance: string;
  analysis: AnalysisPayload;
}

export function readGoalAnalysis(): StoredGoalAnalysis | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(GOAL_ANALYSIS_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredGoalAnalysis;
    if (!parsed?.analysis?.tickets?.length) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writeGoalAnalysis(payload: StoredGoalAnalysis | null): void {
  if (typeof window === "undefined") return;
  try {
    if (!payload) {
      window.sessionStorage.removeItem(GOAL_ANALYSIS_KEY);
      return;
    }
    window.sessionStorage.setItem(GOAL_ANALYSIS_KEY, JSON.stringify(payload));
  } catch {
    return;
  }
}
