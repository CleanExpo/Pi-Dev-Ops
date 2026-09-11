import type { AnalysisPayload } from "@/components/control/GoalDraftReview";
import { writeGoalBriefId } from "@/lib/control/goalProjectStore";

export const GOAL_ANALYSIS_KEY = "pi-ceo.control.goal-analysis";

export interface StoredGoalAnalysis {
  project_id: string;
  project_title: string;
  goal: string;
  acceptance: string;
  analysis: AnalysisPayload;
}

function ready(payload: StoredGoalAnalysis | null): payload is StoredGoalAnalysis {
  return Boolean(
    payload?.project_id.trim()
    && payload.analysis?.tickets?.length,
  );
}

export function readGoalAnalysis(): StoredGoalAnalysis | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.sessionStorage.getItem(GOAL_ANALYSIS_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredGoalAnalysis;
    return ready(parsed) ? parsed : null;
  } catch {
    return null;
  }
}

export function writeGoalAnalysis(payload: StoredGoalAnalysis | null): void {
  if (typeof window === "undefined") return;
  try {
    if (!ready(payload)) {
      window.sessionStorage.removeItem(GOAL_ANALYSIS_KEY);
      return;
    }
    window.sessionStorage.setItem(GOAL_ANALYSIS_KEY, JSON.stringify(payload));
    writeGoalBriefId(payload.project_id);
  } catch {
    return;
  }
}
