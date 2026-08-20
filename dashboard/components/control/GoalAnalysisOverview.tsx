"use client";

import styles from "./control-deck.module.css";

export interface GoalAnalysisBlock {
  summary?: string;
  user_problem?: string;
  desired_outcome?: string;
  acceptance_interpretation?: string;
  current_behaviour?: string;
  identified_gaps?: unknown;
  existing_functionality_to_reuse?: unknown;
  scope?: { included?: unknown; excluded?: unknown };
  repo_limitations?: unknown;
  implementation_strategy?: string;
  overall_risk?: string;
}

export interface FlowBlock {
  diagram?: string;
  happy_path?: unknown;
  failure_paths?: unknown;
  steps?: unknown;
}

export interface OrderStep {
  ticket?: string;
  reason?: string;
}

export interface FinalReviewBlock {
  acceptance_coverage?: string;
  missing_requirements?: unknown;
  unnecessary_scope?: unknown;
  key_unknowns?: unknown;
  main_risks?: unknown;
  smallest_viable_path?: string;
}

export interface AnalysisOverview {
  summary: string;
  split_reason: string;
  code_inspected: boolean;
  code_limitation: string;
  goal_analysis?: GoalAnalysisBlock;
  user_flow?: FlowBlock;
  technical_flow?: FlowBlock;
  implementation_order?: OrderStep[];
  final_review?: FinalReviewBlock;
}

function asLines(value: unknown): string {
  if (value == null || value === "") return "";
  if (Array.isArray(value)) {
    return value.map((item) => asLines(item)).filter(Boolean).join("\n");
  }
  if (typeof value === "object") {
    return Object.entries(value as Record<string, unknown>)
      .map(([key, val]) => {
        const body = asLines(val);
        return body ? `${key}: ${body}` : "";
      })
      .filter(Boolean)
      .join("\n");
  }
  return String(value).trim();
}

function Block({ title, body, pre }: { title: string; body: string; pre?: boolean }) {
  if (!body) return null;
  return (
    <section className={styles.card}>
      <div className={styles.fieldLabel}>{title}</div>
      {pre ? (
        <pre className={styles.diagram}>{body}</pre>
      ) : (
        <p className="mt-2 text-[14px] leading-relaxed whitespace-pre-wrap" style={{ color: "var(--text)" }}>
          {body}
        </p>
      )}
    </section>
  );
}

export default function GoalAnalysisOverview({ analysis }: { analysis: AnalysisOverview }) {
  const ga = analysis.goal_analysis || {};
  const userFlow = analysis.user_flow || {};
  const techFlow = analysis.technical_flow || {};
  const review = analysis.final_review || {};
  const order = analysis.implementation_order || [];
  const summary = ga.summary || analysis.summary || "No analysis text returned.";
  const gaps = asLines(ga.identified_gaps);
  const reuse = asLines(ga.existing_functionality_to_reuse);
  const included = asLines(ga.scope?.included);
  const excluded = asLines(ga.scope?.excluded);
  const limits = asLines(ga.repo_limitations);
  const happy = asLines(userFlow.happy_path);
  const fail = asLines(userFlow.failure_paths);
  const steps = asLines(techFlow.steps);
  const orderText = order
    .map((step, i) => {
      const id = step.ticket || `Step ${i + 1}`;
      return step.reason ? `${id}: ${step.reason}` : id;
    })
    .join("\n");

  return (
    <>
      <section className={styles.card}>
        <div className={styles.fieldLabel}>Goal analysis</div>
        <p className="mt-2 text-[14px] leading-relaxed whitespace-pre-wrap" style={{ color: "var(--text)" }}>
          {summary}
        </p>
        {ga.user_problem ? (
          <p className="mt-2 text-[13px] leading-relaxed" style={{ color: "var(--text-muted)" }}>
            {ga.user_problem}
          </p>
        ) : null}
        {ga.desired_outcome ? (
          <p className="mt-2 text-[13px] leading-relaxed" style={{ color: "var(--text)" }}>
            {ga.desired_outcome}
          </p>
        ) : null}
        {ga.overall_risk ? (
          <p className={`${styles.note} mt-2`}>Overall risk: {ga.overall_risk}</p>
        ) : null}
        {!analysis.code_inspected && analysis.code_limitation ? (
          <p className="mt-2 text-[13px]" style={{ color: "var(--warning)" }}>
            {analysis.code_limitation}
          </p>
        ) : (
          <p className={`${styles.note} mt-2`}>Repo excerpt was used. Paths still need a human check.</p>
        )}
      </section>

      <Block title="Current behaviour" body={ga.current_behaviour || ""} />
      <Block title="Acceptance interpretation" body={ga.acceptance_interpretation || ""} />
      <Block title="Gaps" body={gaps} />
      <Block title="Reuse" body={reuse} />
      <Block title="Included" body={included} />
      <Block title="Not included" body={excluded} />
      <Block title="Repo limitations" body={limits} />
      <Block title="Implementation strategy" body={ga.implementation_strategy || ""} />

      <section className={styles.card}>
        <div className={styles.fieldLabel}>Implementation breakdown</div>
        <p className="mt-2 text-[14px] leading-relaxed whitespace-pre-wrap" style={{ color: "var(--text)" }}>
          {analysis.split_reason || "Split reason was not returned."}
        </p>
      </section>

      <Block title="User flow" body={userFlow.diagram || ""} pre />
      <Block title="Happy path" body={happy} />
      <Block title="Failure paths" body={fail} />
      <Block title="Technical flow" body={techFlow.diagram || ""} pre />
      <Block title="Technical steps" body={steps} />
      <Block title="Implementation order" body={orderText} />
      <Block title="Acceptance coverage" body={review.acceptance_coverage || ""} />
      <Block title="Missing requirements" body={asLines(review.missing_requirements)} />
      <Block title="Unnecessary scope" body={asLines(review.unnecessary_scope)} />
      <Block title="Unknowns" body={asLines(review.key_unknowns)} />
      <Block title="Main risks" body={asLines(review.main_risks)} />
      <Block title="Smallest viable path" body={review.smallest_viable_path || ""} />
    </>
  );
}
