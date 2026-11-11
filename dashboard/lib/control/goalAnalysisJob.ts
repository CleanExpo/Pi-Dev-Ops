/**
 * Submit-then-check goal analysis (UNI-3306, grill 14 Q5/Q6).
 *
 * The server answers POST /api/goal-ticket/analyze with 202 and a job record when
 * GOAL_ANALYZE_ASYNC is on. The dashboard then reads GET /api/goal-ticket/analyze/<id>
 * until the job is finished or failed.
 *
 * A failed read is never a status. The proxy turns a failed GET into HTTP 200
 * `{ error }` with the real code in X-Upstream-Status, so only a well-formed job
 * record for the same id counts as an answer; anything else is a failed check.
 */

export type JobStatus = "queued" | "running" | "finished" | "failed" | "interrupted";

export interface AnalysisJob {
  id: string;
  status: JobStatus;
  attempt?: number | null;
  retry_count?: number | null;
  result?: unknown;
  failure_reason?: string | null;
  last_progress_at?: string | null;
  /** Seconds since last progress, on the database clock at the time of the read. */
  last_progress_age_s?: number | null;
  /** Seconds since started_at (created_at while queued), on the database clock. */
  elapsed_s?: number | null;
}

/**
 * Browser time (Date.now()) at which the job last made progress, for a read received
 * at `receivedAt`. Uses the server-computed age, so a job that was already stalled
 * when first seen shows as stalled at once and browser clock offset does not matter.
 * Without an age it keeps `previous` unless last_progress_at changed.
 */
export function progressSeenAt(
  job: AnalysisJob,
  receivedAt: number,
  previous: { value: string | null; at: number } | null,
): { value: string | null; at: number } {
  const value = job.last_progress_at ?? null;
  const age = job.last_progress_age_s;
  if (typeof age === "number" && Number.isFinite(age) && age >= 0) {
    return { value, at: receivedAt - age * 1000 };
  }
  if (previous && previous.value === value) return previous;
  return { value, at: receivedAt };
}

const STATUSES: ReadonlySet<string> = new Set(["queued", "running", "finished", "failed", "interrupted"]);

/** Normal gap between checks. */
export const POLL_MS = 3_000;
/** Gaps after 1, 2, 3 and 4+ failed checks in a row. */
export const BACKOFF_MS: readonly number[] = [3_000, 6_000, 12_000, 30_000];
/** A running job with no progress for longer than the claim (60 s) is shown as stalled. */
export const STALL_MS = 60_000;

export const UNREACHABLE = "Can't reach the server, retrying";

export function isAnalysisJob(value: unknown): value is AnalysisJob {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return typeof v.id === "string" && v.id !== "" && typeof v.status === "string" && STATUSES.has(v.status);
}

/** Only finished and failed end the checking. An interrupted job is retried or failed by the server. */
export function isFinal(job: AnalysisJob): boolean {
  return job.status === "finished" || job.status === "failed";
}

/** Wait before the next check: POLL_MS normally, growing gaps after failed checks. */
export function nextCheckMs(failuresInARow: number): number {
  if (failuresInARow <= 0) return POLL_MS;
  return BACKOFF_MS[Math.min(failuresInARow, BACKOFF_MS.length) - 1];
}

/**
 * The status line uses the database age plus browser time since the last read.
 */
export function jobStatusLabel(job: AnalysisJob, msSinceProgress: number): string {
  switch (job.status) {
    case "queued":
      return "Queued, waiting for a server";
    case "running":
      return msSinceProgress > STALL_MS ? "Stalled, recovering" : "Running";
    case "interrupted":
      return (job.retry_count ?? 0) < 1 ? "Interrupted, retrying" : "Interrupted";
    case "finished":
      return "Finished";
    case "failed":
      return "Failed";
  }
}

export type CheckOutcome =
  | { kind: "job"; job: AnalysisJob }
  | { kind: "retry" }
  | { kind: "stop"; message: string };

/**
 * Classify one status read. A 4xx (from the response or the proxy's
 * X-Upstream-Status) stops checking: the job is gone or checking is switched off.
 * Everything else that is not a job record for `jobId` is a failed check to retry.
 */
export function classifyCheck(jobId: string, httpStatus: number, upstreamStatus: string | null, body: unknown): CheckOutcome {
  const upstream = upstreamStatus ? Number(upstreamStatus) : NaN;
  const code = Number.isFinite(upstream) ? upstream : httpStatus;
  if (code >= 400 && code < 500 && code !== 408 && code !== 429) {
    return {
      kind: "stop",
      message: `The analysis job can no longer be read (HTTP ${code}). Linear was not written. Analyze again.`,
    };
  }
  if (httpStatus >= 200 && httpStatus < 300 && Number.isNaN(upstream) && isAnalysisJob(body) && body.id === jobId) {
    return { kind: "job", job: body };
  }
  return { kind: "retry" };
}

/**
 * Resolve after `ms`, but never while the tab is hidden: a hidden tab waits until
 * it is shown, then resolves at once. Showing a hidden tab also cuts a wait short.
 */
export function waitForNextCheck(ms: number, doc: Document = document): Promise<void> {
  return new Promise((resolve) => {
    let done = false;
    const finish = () => {
      if (done) return;
      done = true;
      clearTimeout(timer);
      doc.removeEventListener("visibilitychange", onVisibility);
      resolve();
    };
    const onVisibility = () => {
      if (!doc.hidden) finish();
    };
    const timer = setTimeout(() => {
      if (!doc.hidden) finish();
    }, ms);
    doc.addEventListener("visibilitychange", onVisibility);
  });
}

/** A one-time key for one Analyze click (8 to 200 characters, per the job table). */
export function newIdempotencyKey(): string {
  const c = globalThis.crypto;
  if (c && typeof c.randomUUID === "function") return `dash-${c.randomUUID()}`;
  return `dash-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
}

export function statusPath(jobId: string): string {
  return `/api/pi-ceo/api/goal-ticket/analyze/${encodeURIComponent(jobId)}`;
}
