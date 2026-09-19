/** Liveness, automation configuration and delivery evidence are separate facts. */
export interface OperatorHealth {
  status: string;
  uptime_s?: number;
  sessions?: { active?: number; total?: number; max?: number };
  claude_cli?: boolean;
  linear_key?: boolean;
  vercel_token?: boolean;
  autonomy?: { enabled?: boolean; armed?: boolean; poll_count?: number; seconds_since_last_poll?: number | null };
  disk_free_gb?: number | null;
  swarm_enabled?: boolean;
  swarm_shadow?: boolean;
  model_documentation?: { status: string };
  generation?: { status: "blocked" | "unverified"; blockers: string[] };
}

export interface OperatorSession {
  id: string;
  repo: string;
  status: string;
  started: string | number;
  last_phase?: string;
  evaluator_score?: number;
}

const record = (value: unknown): Record<string, unknown> =>
  value !== null && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
const number = (value: unknown) => typeof value === "number" && Number.isFinite(value) ? value : undefined;
const boolean = (value: unknown) => typeof value === "boolean" ? value : undefined;

export function parseOperatorHealth(value: unknown): OperatorHealth | null {
  const h = record(value);
  if (typeof h.status !== "string" || !h.status) return null;
  const a = record(h.autonomy);
  const s = record(h.sessions);
  const docs = record(h.model_documentation);
  const generation = record(h.generation);
  return {
    status: h.status,
    uptime_s: number(h.uptime_s),
    sessions: h.sessions ? { active: number(s.active), total: number(s.total), max: number(s.max) } : undefined,
    autonomy: h.autonomy ? {
      enabled: boolean(a.enabled), armed: boolean(a.armed), poll_count: number(a.poll_count),
      seconds_since_last_poll: a.seconds_since_last_poll === null ? null : number(a.seconds_since_last_poll),
    } : undefined,
    claude_cli: boolean(h.claude_cli), linear_key: boolean(h.linear_key), vercel_token: boolean(h.vercel_token),
    disk_free_gb: number(h.disk_free_gb), swarm_enabled: boolean(h.swarm_enabled), swarm_shadow: boolean(h.swarm_shadow),
    model_documentation: typeof docs.status === "string" && ["fresh", "stale", "missing", "unverified"].includes(docs.status)
      ? { status: docs.status } : undefined,
    generation: ["blocked", "unverified"].includes(String(generation.status)) ? {
      status: generation.status as "blocked" | "unverified",
      blockers: Array.isArray(generation.blockers) ? generation.blockers.filter((reason): reason is string => typeof reason === "string") : [],
    } : undefined,
  };
}

export function parseOperatorSessions(value: unknown): OperatorSession[] | null {
  if (!Array.isArray(value)) return null;
  const sessions: OperatorSession[] = [];
  for (const item of value) {
    const s = record(item);
    if (typeof s.id !== "string" || typeof s.repo !== "string" || typeof s.status !== "string" ||
        !(typeof s.started === "string" || number(s.started) !== undefined)) return null;
    sessions.push({ id: s.id, repo: s.repo, status: s.status, started: s.started as string | number,
      evaluator_score: number(s.evaluator_score), last_phase: typeof s.last_phase === "string" ? s.last_phase : undefined });
  }
  return sessions;
}

export function sessionTime(started: string | number): number {
  // The session API emits Unix seconds; older snapshots used ISO strings.
  return typeof started === "number" ? started * 1000 : new Date(started).getTime();
}

export function needsAttention(status: string): boolean {
  return ["blocked", "stalled", "failed", "error", "interrupted"].includes(status);
}

export function automationLabel(health: OperatorHealth | null): string {
  if (health?.autonomy?.enabled === false || health?.autonomy?.armed === false) return "Paused";
  if (health?.autonomy?.enabled === true && health.autonomy.armed === true) return "Armed";
  return "Unknown";
}

export function swarmLabel(health: OperatorHealth | null): string {
  if (health?.swarm_enabled === false) return "Off";
  if (health?.swarm_enabled !== true || health.swarm_shadow === undefined) return "Unknown";
  return health.swarm_shadow ? "Shadow" : "Enabled";
}
