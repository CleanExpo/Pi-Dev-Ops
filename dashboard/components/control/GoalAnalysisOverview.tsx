"use client";

import styles from "./control-deck.module.css";

export interface GoalAnalysisBlock {
  summary?: string;
  problem?: string;
  user_problem?: string;
  users?: unknown;
  desired_outcome?: string;
  acceptance_summary?: string;
  acceptance_interpretation?: string;
  current_behaviour?: string;
  new_work?: unknown;
  identified_gaps?: unknown;
  existing_functionality?: unknown;
  existing_functionality_to_reuse?: unknown;
  scope?: { included?: unknown; excluded?: unknown };
  unknowns?: unknown;
  repo_limitations?: unknown;
  implementation_strategy?: string;
  risk?: string;
  overall_risk?: string;
}

export interface FlowBlock {
  summary?: string;
  diagram?: string;
  happy_path?: unknown;
  failure_paths?: unknown;
  edge_cases?: unknown;
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
  unknowns?: unknown;
  key_unknowns?: unknown;
  main_risks?: unknown;
  smallest_viable_path?: string;
}

export interface AnalysisOverview {
  summary: string;
  split_reason: string;
  code_inspected: boolean;
  code_limitation: string;
  fallback?: boolean;
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
  const summary = (ga.summary || "").trim() || analysis.summary || "No analysis text returned.";
  const problem = String(ga.user_problem || ga.problem || "").trim();
  const risk = String(ga.overall_risk || ga.risk || "").trim();
  const users = asLines(ga.users);
  const gaps = asLines(ga.identified_gaps || ga.new_work);
  const reuse = asLines(ga.existing_functionality_to_reuse || ga.existing_functionality);
  const included = asLines(ga.scope?.included);
  const excluded = asLines(ga.scope?.excluded);
  const limits = asLines(ga.repo_limitations || ga.unknowns);
  const happy = asLines(userFlow.happy_path);
  const fail = asLines(userFlow.failure_paths);
  const flowEdges = asLines(userFlow.edge_cases);
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
        {problem ? (
          <p className="mt-2 text-[13px] leading-relaxed" style={{ color: "var(--text-muted)" }}>
            {problem}
          </p>
        ) : null}
        {ga.desired_outcome ? (
          <p className="mt-2 text-[13px] leading-relaxed" style={{ color: "var(--text)" }}>
            {ga.desired_outcome}
          </p>
        ) : null}
        {risk ? (
          <p className={`${styles.note} mt-2`}>Overall risk: {risk}</p>
        ) : null}
        {analysis.fallback ? (
          <p className="mt-2 text-[13px]" style={{ color: "var(--warning)" }}>
            This is a fallback draft. The analyzer did not return a completed plan.
          </p>
        ) : null}
        {analysis.code_limitation ? (
          <p className={`${styles.note} mt-2`}>{analysis.code_limitation}</p>
        ) : (
          <p className={`${styles.note} mt-2`}>Tickets are grounded in the selected project brief, not a repository.</p>
        )}
      </section>

      <Block title="Current behaviour" body={ga.current_behaviour || ""} />
      <Block title="Users" body={users} />
      <Block
        title="Acceptance interpretation"
        body={String(ga.acceptance_interpretation || ga.acceptance_summary || "")}
      />
      <Block title="New work" body={gaps} />
      <Block title="Reuse" body={reuse} />
      <Block title="Included" body={included} />
      <Block title="Not included" body={excluded} />
      <Block title="Unknowns" body={limits} />
      <Block title="Implementation strategy" body={ga.implementation_strategy || ""} />

      <section className={styles.card}>
        <div className={styles.fieldLabel}>Implementation breakdown</div>
        <p className="mt-2 text-[14px] leading-relaxed whitespace-pre-wrap" style={{ color: "var(--text)" }}>
          {analysis.split_reason || ga.implementation_strategy || "Implementation strategy was not returned."}
        </p>
      </section>

      <Block title="User flow" body={String(userFlow.summary || userFlow.diagram || "")} pre={Boolean(userFlow.diagram)} />
      <Block title="Happy path" body={happy} />
      <Block title="Failure paths" body={fail} />
      <Block title="User-flow edge cases" body={flowEdges} />
      <Block title="Technical flow" body={techFlow.diagram || ""} pre />
      <Block title="Technical steps" body={steps} />
      <Block title="Implementation order" body={orderText} />
      <Block title="Acceptance coverage" body={review.acceptance_coverage || ""} />
      <Block title="Missing requirements" body={asLines(review.missing_requirements)} />
      <Block title="Unnecessary scope" body={asLines(review.unnecessary_scope)} />
      <Block title="Review unknowns" body={asLines(review.unknowns || review.key_unknowns)} />
      <Block title="Main risks" body={asLines(review.main_risks)} />
      <Block title="Smallest viable path" body={review.smallest_viable_path || ""} />
    </>
  );
}
