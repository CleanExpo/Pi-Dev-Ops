export const STAGES = [
  "spark",
  "grill",
  "shape",
  "spec",
  "bet",
  "graduated",
] as const;

export type Stage = (typeof STAGES)[number];

export interface EvidenceItem {
  kind: string;
  tag: "human";
}

export interface DecisionRecord {
  verdict: "go" | "no-go";
  reason: string;
}

export interface Placecard {
  id: string;
  title: string;
  blurb: string;
  stage: Stage;
  answers: {
    customer: string;
    metric: string;
    problem: string;
  };
  appetite: string;
  fences: string[];
  schemaLines: string[];
  gherkin: string[];
  evidence: EvidenceItem[];
  sketchSaved: boolean;
  goalArmed: boolean;
  promises: string[];
  decision: DecisionRecord | null;
  moves: string[];
}

export interface GateItem {
  id: string;
  label: string;
  satisfied: (card: Placecard) => boolean;
}

export const GATES: Record<Stage, readonly GateItem[]> = {
  spark: [],
  grill: [
    { id: "customer", label: "customer named", satisfied: (c) => Boolean(c.answers.customer.trim()) },
    { id: "metric", label: "metric named", satisfied: (c) => Boolean(c.answers.metric.trim()) },
    { id: "problem", label: "problem named", satisfied: (c) => Boolean(c.answers.problem.trim()) },
  ],
  shape: [
    { id: "appetite", label: "appetite set", satisfied: (c) => Boolean(c.appetite) },
    { id: "fence", label: "fence logged", satisfied: (c) => c.fences.length > 0 },
  ],
  spec: [
    { id: "schema", label: "schema line", satisfied: (c) => c.schemaLines.length > 0 },
    { id: "gherkin", label: "3 Gherkin scenarios", satisfied: (c) => c.gherkin.length >= 3 },
  ],
  bet: [
    {
      id: "goal",
      label: "goal card armed, promises logged",
      satisfied: (c) => c.goalArmed && c.promises.length > 0,
    },
  ],
  graduated: [],
};

export function seedCard(): Placecard {
  return {
    id: "c1",
    title: "Job photos reach the file",
    blurb: "Photos taken on site never leave the tech's phone.",
    stage: "spark",
    answers: { customer: "", metric: "", problem: "" },
    appetite: "",
    fences: [],
    schemaLines: [],
    gherkin: [],
    evidence: [],
    sketchSaved: false,
    goalArmed: false,
    promises: [],
    decision: null,
    moves: [],
  };
}

export function remainingGates(card: Placecard): GateItem[] {
  return GATES[card.stage].filter((gate) => !gate.satisfied(card));
}

export function nextStage(stage: Stage): Stage | null {
  const index = STAGES.indexOf(stage);
  if (index < 0 || index >= STAGES.length - 1) return null;
  return STAGES[index + 1];
}

export function canAdvance(card: Placecard): boolean {
  return remainingGates(card).length === 0 && nextStage(card.stage) !== null;
}

export function advanceLabel(card: Placecard): string {
  const left = remainingGates(card).length;
  if (left === 1) return "Advance (1 item left)";
  if (left > 1) return `Advance (${left} items left)`;
  const next = nextStage(card.stage);
  return next ? `Advance to ${next}` : "Graduated";
}

export function applyAdvance(card: Placecard): Placecard {
  if (!canAdvance(card)) return card;
  const next = nextStage(card.stage);
  if (!next) return card;
  return {
    ...card,
    stage: next,
    moves: [...card.moves, `${card.stage} → ${next}`],
  };
}

export function applySketchSave(card: Placecard): Placecard {
  if (card.sketchSaved) return card;
  return {
    ...card,
    sketchSaved: true,
    evidence: [...card.evidence, { kind: "excalidraw_scene", tag: "human" }],
  };
}

export function applyDecision(card: Placecard, go: boolean, reason: string): Placecard {
  const trimmed = reason.trim();
  if (!trimmed) return card;
  const verdict: DecisionRecord["verdict"] = go ? "go" : "no-go";
  const decided: Placecard = {
    ...card,
    decision: { verdict, reason: trimmed },
  };
  if (!go || card.stage !== "bet") return decided;
  if (card.moves.some((row) => row.includes("bet → graduated"))) return decided;
  return {
    ...decided,
    stage: "graduated",
    moves: [...card.moves, "bet → graduated"],
  };
}

export function appendUnique(list: string[], value: string): string[] {
  const trimmed = value.trim();
  if (!trimmed) return list;
  return [...list, trimmed];
}
