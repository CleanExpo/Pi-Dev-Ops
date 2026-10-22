// What a Mission Control project card may say about its project.
//
// Every field is a value, a genuine empty, or `unavailable` with a reason. A
// failed read is never shown as 0 open PRs, a passing build or a current scan.

export type Field<T> = { status: "ok"; value: T } | { status: "unavailable"; reason: string };

export interface PullsValue {
  count: number;
  /** True when GitHub returned a full page, so the real count may be higher. */
  capped: boolean;
}

export type CiState = "success" | "failure" | "error" | "pending" | "expected" | "none";

export interface CiValue {
  branch: string;
  sha: string;
  state: CiState;
}

/** /api/flow-board?repo= card fields. */
export interface RepoTruth {
  repo: string;
  checked_at: string;
  pull_requests: Field<PullsValue>;
  ci: Field<CiValue>;
}

/** The last deployment_health scan, as app/server/scan_summary.py records it. */
export interface DeployCheck {
  finished_at: string | null;
  error: string;
  findings: Array<{ severity: string; title: string }>;
}

const CI_STATES: readonly CiState[] = ["success", "failure", "error", "pending", "expected", "none"];

export function unavailableTruth(repo: string, reason: string): RepoTruth {
  const down = { status: "unavailable" as const, reason };
  return { repo, checked_at: new Date().toISOString(), pull_requests: down, ci: down };
}

function record(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value) ? (value as Record<string, unknown>) : null;
}

function parseField<T>(raw: unknown, parseValue: (v: Record<string, unknown>) => T | null): Field<T> | null {
  const field = record(raw);
  if (field?.status === "unavailable" && typeof field.reason === "string") return { status: "unavailable", reason: field.reason };
  const value = field?.status === "ok" ? record(field.value) : null;
  const parsed = value ? parseValue(value) : null;
  return parsed === null ? null : { status: "ok", value: parsed };
}

const parsePulls = (v: Record<string, unknown>): PullsValue | null =>
  Number.isInteger(v.count) && (v.count as number) >= 0 && typeof v.capped === "boolean"
    ? { count: v.count as number, capped: v.capped } : null;

const parseCi = (v: Record<string, unknown>): CiValue | null =>
  typeof v.branch === "string" && typeof v.sha === "string" && CI_STATES.includes(v.state as CiState)
    ? { branch: v.branch, sha: v.sha, state: v.state as CiState } : null;

/** Null when the payload is not card truth at all (the caller shows UNAVAILABLE). */
export function parseRepoTruth(raw: unknown): RepoTruth | null {
  const body = record(raw);
  if (!body || typeof body.repo !== "string" || typeof body.checked_at !== "string") return null;
  const pulls = parseField(body.pull_requests, parsePulls);
  const ci = parseField(body.ci, parseCi);
  return pulls && ci ? { repo: body.repo, checked_at: body.checked_at, pull_requests: pulls, ci } : null;
}

/** "3h ago", "2d ago"; null when the stamp is missing or unparseable. */
export function ageLabel(iso: string | null | undefined, nowMs: number): string | null {
  const at = iso ? Date.parse(iso) : Number.NaN;
  if (Number.isNaN(at)) return null;
  const minutes = Math.max(0, Math.floor((nowMs - at) / 60_000));
  if (minutes < 60) return `${minutes}m ago`;
  if (minutes < 1440) return `${Math.floor(minutes / 60)}h ago`;
  return `${Math.floor(minutes / 1440)}d ago`;
}

export function deployCheckOf(raw: unknown): DeployCheck | null {
  const check = record(raw);
  if (!check) return null;
  const findings = Array.isArray(check.findings) ? check.findings.map(record).filter((f) => f !== null) : [];
  return {
    finished_at: typeof check.finished_at === "string" ? check.finished_at : null,
    error: typeof check.error === "string" ? check.error : "",
    findings: findings.map((f) => ({ severity: String(f.severity ?? ""), title: String(f.title ?? "") })),
  };
}
