export interface PhaseMetric {
  duration_s: number;
  cost_usd: number | null;
}

const PHASES = ["clone", "analyze", "claude_check", "sandbox", "generator", "evaluator", "push"];
const PHASE_LABELS = ["Clone", "Analyze", "Check", "Sandbox", "Generate", "Evaluate", "Push"];
const EVAL_COLOR: Record<string, string> = {
  passed: "#4ADE80",
  warned: "#FFD166",
  pending: "var(--text-dim)",
};

export function PhaseBar({
  lastPhase,
  status,
  phaseMetrics,
}: {
  lastPhase: string;
  status: string;
  phaseMetrics: Record<string, PhaseMetric>;
}) {
  const doneIdx = PHASES.indexOf(lastPhase);
  const isRunning = ["cloning", "building", "evaluating"].includes(status);
  return (
    <div className="flex gap-1 mt-1.5 flex-wrap">
      {PHASES.map((p, i) => {
        const done = doneIdx >= i;
        const active = isRunning && doneIdx + 1 === i;
        const metric = phaseMetrics[p];
        const cost = metric && typeof metric.cost_usd === "number" && Number.isFinite(metric.cost_usd) && metric.cost_usd >= 0
          ? metric.cost_usd : null;
        return (
          <div key={p} className="flex items-center gap-0.5">
            <div
              title={PHASE_LABELS[i]}
              className="h-1 w-8 rounded-sm"
              style={{
                background: done ? "#4ADE80" : active ? "var(--accent)" : "var(--border)",
                opacity: done || active ? 1 : 0.4,
              }}
            />
            {metric && (
              <span
                className="font-mono text-[9px]"
                style={{ color: "var(--text-dim)" }}
                title={`${PHASE_LABELS[i]}: ${metric.duration_s}s · ${cost === null ? "cost unknown" : `reported usage $${cost.toFixed(4)} (billing unverified)`}`}
              >
                {metric.duration_s}s · {cost === null ? "cost unknown" : `reported $${cost.toFixed(2)}`}
              </span>
            )}
          </div>
        );
      })}
    </div>
  );
}

export function ScoreBadge({ score, evalStatus }: { score: number | null; evalStatus: string }) {
  if (score === null) return null;
  const color = score >= 8 ? "#4ADE80" : score >= 6 ? "#FFD166" : "#F87171";
  return (
    <span
      className="font-mono text-[10px] px-1.5 py-0.5 rounded"
      style={{ background: "var(--panel)", color, border: `1px solid ${EVAL_COLOR[evalStatus] ?? "var(--border)"}` }}
    >
      {score.toFixed(1)}/10
    </span>
  );
}
