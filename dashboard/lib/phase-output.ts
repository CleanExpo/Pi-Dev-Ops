/** Runtime validation of the JSON contracts requested by PHASE_PROMPTS. */
import { tryParseJson } from "./phases";

type Validator = (value: unknown) => boolean;
type Fields = Record<string, Validator>;
const record = (value: unknown): value is Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value);
const text: Validator = value => typeof value === "string" && value.trim().length > 0;
const boolean: Validator = value => typeof value === "boolean";
const range = (min: number, max: number): Validator => value =>
  typeof value === "number" && Number.isFinite(value) && value >= min && value <= max;
const integer = (min: number, max = Number.MAX_SAFE_INTEGER): Validator => value =>
  typeof value === "number" && Number.isSafeInteger(value) && value >= min && value <= max;
const oneOf = (...values: string[]): Validator => value => typeof value === "string" && values.includes(value);
const arrayOf = (item: Validator): Validator => value => Array.isArray(value) && value.every(item);
const strings = arrayOf(text);
const object = (fields: Fields): Validator => value => record(value) &&
  Object.entries(fields).every(([key, validate]) => Object.hasOwn(value, key) && validate(value[key]));

// An empty result list is valid (e.g. no issues or no justified sprint work).
// Its elements, when present, must still have the complete requested shape.
const scores = object({ completeness: range(1, 10), correctness: range(1, 10),
  codeQuality: range(1, 10), documentation: range(1, 10) });
const issue = object({ severity: oneOf("critical", "high", "medium", "low"), file: text,
  line: value => value === null || integer(1)(value), description: text });
const sprintItem = object({ title: text, size: oneOf("S", "M", "L"), priority: oneOf("P1", "P2", "P3"),
  piter: object({ problem: text, impact: text, result: text }) });
const sprint = object({ id: integer(1), name: text, duration: text, goal: text, items: arrayOf(sprintItem) });
const leveragePoint = object({ id: integer(1, 12), name: text, score: range(1, 5) });
const leveragePoints: Validator = value => Array.isArray(value) && value.length === 12 &&
  value.every(leveragePoint) && new Set(value.map(point => point.id)).size === 12;

const schemas: Record<number, Validator> = {
  1: object({
    totalFiles: integer(0), languages: value => record(value) && Object.values(value).every(integer(0)),
    topFiles: strings, frameworks: strings, entryPoints: strings, testFiles: integer(0),
    testCoveragePresent: boolean, ciCdConfig: strings, dockerPresent: boolean, envExamplePresent: boolean,
    packageManagers: strings, totalDependencies: integer(0), missingCriticalFiles: strings,
    architecturePattern: oneOf("monolith", "microservices", "serverless", "fullstack", "library", "cli", "other"),
  }),
  2: object({
    techStack: strings, pattern: oneOf("monolith", "microservices", "serverless", "MVC", "event-driven", "other"),
    components: arrayOf(object({ name: text, responsibility: text, file: text })),
    entryPoints: strings, keyDependencies: strings, dataFlow: text, externalIntegrations: strings,
    securitySurface: strings, designPatterns: strings, couplingConcerns: strings, architectureNotes: text,
  }),
  3: object({ scores, issues: arrayOf(issue), missingTests: strings, securityConcerns: strings, positives: strings }),
  4: object({
    projectPurpose: text, targetUsers: strings, businessLogic: text,
    currentState: oneOf("production-ready", "beta", "alpha", "prototype"),
    bigThree: object({ model: text, prompt: text, context: text }), keyInsights: strings,
    deploymentTopology: text, dataModels: strings,
  }),
  5: object({ zteLevel: integer(1, 4), zteScore: range(12, 60), leveragePoints,
    productionGaps: strings, loadRisks: strings, topThreeROI: strings }),
  6: object({ sprints: arrayOf(sprint), deferredItems: strings,
    featureList: arrayOf(object({ id: text, title: text, sprint: integer(1), status: oneOf("planned") })) }),
  7: object({ headline: text, currentState: text, strengths: strings, weaknesses: strings, risks: strings,
    opportunities: strings, executiveSummary: text,
    nextActions: arrayOf(object({ action: text, why: text, effort: oneOf("S", "M", "L"), owner: oneOf("human", "agent", "both") })) }),
};

/** Phase 8 publishes validated phase 1-7 results; it has no model output. */
export function isPhaseOutputValid(phaseId: number, output: string): boolean {
  return schemas[phaseId]?.(tryParseJson<unknown>(output)) ?? false;
}
