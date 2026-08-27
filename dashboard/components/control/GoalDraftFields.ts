export interface DraftTicket {
  title: string;
  goal: string;
  acceptance: string;
  rationale: string;
  context: string;
  user_story: string;
  current_behaviour: string;
  expected_behaviour: string;
  technical_requirements: string;
  edge_cases: string;
  testing: string;
  dependencies: string;
  ticket_id: string;
  priority: string;
  summary: string;
  scope: string;
  user_flow: string;
  technical_flow: string;
  examples: string;
  implementation_notes: string;
  risks: string;
  review: string;
  ui_ux: string;
  data_state: string;
  affected_surfaces: string;
  tasks: string;
  sub_tasks: string;
  sub_tasks_json: string;
  scenarios: string;
  junior_notes: string;
  selected: boolean;
}

export const DRAFT_AREAS: Array<{ key: keyof DraftTicket; label: string; rows: number }> = [
  { key: "summary", label: "Summary", rows: 2 },
  { key: "context", label: "Context", rows: 3 },
  { key: "user_story", label: "User story", rows: 2 },
  { key: "current_behaviour", label: "Current behaviour", rows: 3 },
  { key: "expected_behaviour", label: "Expected behaviour", rows: 3 },
  { key: "scope", label: "Scope", rows: 3 },
  { key: "affected_surfaces", label: "Affected surfaces", rows: 2 },
  { key: "technical_requirements", label: "Technical requirements", rows: 4 },
  { key: "implementation_notes", label: "Implementation notes", rows: 3 },
  { key: "ui_ux", label: "UI / UX", rows: 3 },
  { key: "data_state", label: "Data / state", rows: 3 },
  { key: "user_flow", label: "User flow", rows: 4 },
  { key: "technical_flow", label: "Technical flow", rows: 4 },
  { key: "examples", label: "Examples", rows: 3 },
  { key: "tasks", label: "Tasks", rows: 3 },
  { key: "sub_tasks", label: "Sub-tasks", rows: 5 },
  { key: "scenarios", label: "Scenarios", rows: 3 },
  { key: "junior_notes", label: "Junior notes", rows: 3 },
  { key: "acceptance", label: "Acceptance criteria", rows: 4 },
  { key: "edge_cases", label: "Edge cases", rows: 3 },
  { key: "testing", label: "Testing", rows: 3 },
  { key: "dependencies", label: "Dependencies", rows: 2 },
  { key: "risks", label: "Risks", rows: 2 },
  { key: "review", label: "Review", rows: 3 },
  { key: "rationale", label: "Why this ticket", rows: 2 },
];

export const ALWAYS_SHOW: Array<keyof DraftTicket> = [
  "expected_behaviour",
  "acceptance",
  "tasks",
  "sub_tasks",
  "scenarios",
];

export const BLANK_DRAFT: Omit<DraftTicket, "selected"> = {
  title: "",
  goal: "",
  acceptance: "",
  rationale: "",
  context: "",
  user_story: "",
  current_behaviour: "",
  expected_behaviour: "",
  technical_requirements: "",
  edge_cases: "",
  testing: "",
  dependencies: "",
  ticket_id: "",
  priority: "",
  summary: "",
  scope: "",
  user_flow: "",
  technical_flow: "",
  examples: "",
  implementation_notes: "",
  risks: "",
  review: "",
  ui_ux: "",
  data_state: "",
  affected_surfaces: "",
  tasks: "",
  sub_tasks: "",
  sub_tasks_json: "",
  scenarios: "",
  junior_notes: "",
};

export function draftsFromAnalyze(raw: Array<Partial<DraftTicket>>): DraftTicket[] {
  return raw.flatMap((t) => {
    const expected = (t.expected_behaviour || t.goal || "").trim();
    const acceptance = (t.acceptance || "").trim();
    const title = (t.title || "").trim();
    if (!title || !expected || !acceptance) return [];
    const next: DraftTicket = { ...BLANK_DRAFT, selected: true };
    (Object.keys(BLANK_DRAFT) as Array<keyof typeof BLANK_DRAFT>).forEach((key) => {
      const value = t[key];
      next[key] = typeof value === "string" ? value : BLANK_DRAFT[key];
    });
    next.title = title;
    next.goal = expected;
    next.expected_behaviour = expected;
    next.acceptance = acceptance;
    next.selected = true;
    return [next];
  });
}

export function filePayloadFromDraft(
  t: DraftTicket,
  sanitize: (value: string) => string,
): Record<string, string> {
  const s = (value: string) => sanitize(value.trim());
  return {
    title: s(t.title),
    goal: s(t.goal || t.expected_behaviour),
    acceptance: s(t.acceptance),
    rationale: s(t.rationale),
    context: s(t.context),
    user_story: s(t.user_story),
    current_behaviour: s(t.current_behaviour),
    expected_behaviour: s(t.expected_behaviour),
    technical_requirements: s(t.technical_requirements),
    edge_cases: s(t.edge_cases),
    testing: s(t.testing),
    dependencies: s(t.dependencies),
    ticket_id: s(t.ticket_id),
    priority: s(t.priority),
    summary: s(t.summary),
    scope: s(t.scope),
    user_flow: s(t.user_flow),
    technical_flow: s(t.technical_flow),
    examples: s(t.examples),
    implementation_notes: s(t.implementation_notes),
    risks: s(t.risks),
    review: s(t.review),
    ui_ux: s(t.ui_ux),
    data_state: s(t.data_state),
    affected_surfaces: s(t.affected_surfaces),
    tasks: s(t.tasks),
    sub_tasks: s(t.sub_tasks),
    sub_tasks_json: s(t.sub_tasks_json),
    scenarios: s(t.scenarios),
    junior_notes: s(t.junior_notes),
  };
}
