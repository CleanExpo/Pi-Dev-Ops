/**
 * UNI-3306 step 6 — the status rules for a submitted goal analysis job (grill 14 Q5).
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  POLL_MS,
  STALL_MS,
  classifyCheck,
  isAnalysisJob,
  isFinal,
  jobStatusLabel,
  newIdempotencyKey,
  nextCheckMs,
  statusPath,
  waitForNextCheck,
  type AnalysisJob,
} from "@/lib/control/goalAnalysisJob";

const ID = "0b6c2f8e-6f1e-4d55-9a57-2f3f6b7f1a10";
const job = (over: Partial<AnalysisJob> = {}): AnalysisJob => ({ id: ID, status: "running", retry_count: 0, ...over });

afterEach(() => {
  vi.useRealTimers();
  Object.defineProperty(document, "hidden", { configurable: true, get: () => false });
});

describe("job status rules", () => {
  it("checks every 3 s, and backs off 3, 6, 12, then 30 s after failed checks", () => {
    expect(nextCheckMs(0)).toBe(POLL_MS);
    expect([1, 2, 3, 4, 5, 9].map(nextCheckMs)).toEqual([3_000, 6_000, 12_000, 30_000, 30_000, 30_000]);
  });

  it("ends only on finished or failed; interrupted keeps checking", () => {
    expect(isFinal(job({ status: "finished" }))).toBe(true);
    expect(isFinal(job({ status: "failed" }))).toBe(true);
    expect(isFinal(job({ status: "interrupted" }))).toBe(false);
    expect(isFinal(job({ status: "queued" }))).toBe(false);
    expect(isFinal(job({ status: "running" }))).toBe(false);
  });

  it("labels running as stalled only after more than 60 s without progress", () => {
    expect(jobStatusLabel(job(), STALL_MS)).toBe("Running");
    expect(jobStatusLabel(job(), STALL_MS + 1)).toBe("Stalled, recovering");
  });

  it("labels an interrupted job with a retry left as retrying", () => {
    expect(jobStatusLabel(job({ status: "interrupted", retry_count: 0 }), 0)).toBe("Interrupted, retrying");
    expect(jobStatusLabel(job({ status: "interrupted", retry_count: 1 }), 0)).toBe("Interrupted");
    expect(jobStatusLabel(job({ status: "queued" }), 0)).toBe("Queued, waiting for a server");
  });

  it("accepts only a well-formed job record", () => {
    expect(isAnalysisJob(job())).toBe(true);
    expect(isAnalysisJob({ id: ID, status: "done" })).toBe(false);
    expect(isAnalysisJob({ id: "", status: "running" })).toBe(false);
    expect(isAnalysisJob({ error: "Pi CEO server unreachable" })).toBe(false);
    expect(isAnalysisJob(null)).toBe(false);
  });
});

describe("classifyCheck: a failed read is never a status", () => {
  it("a job record for the same id is an answer", () => {
    expect(classifyCheck(ID, 200, null, job())).toEqual({ kind: "job", job: job() });
  });

  it("the proxy's quiet 200 { error } with a 5xx upstream is a failed check", () => {
    expect(classifyCheck(ID, 200, "502", { error: "Pi CEO server unreachable" }).kind).toBe("retry");
    expect(classifyCheck(ID, 200, "503", job()).kind).toBe("retry");
  });

  it("a different job's record, a server error or an empty body is a failed check", () => {
    expect(classifyCheck(ID, 200, null, job({ id: "other" })).kind).toBe("retry");
    expect(classifyCheck(ID, 500, null, null).kind).toBe("retry");
    expect(classifyCheck(ID, 200, null, null).kind).toBe("retry");
  });

  it("a 4xx (gone or switched off) stops checking with a message; 408 and 429 retry", () => {
    expect(classifyCheck(ID, 200, "404", { error: "not found" }).kind).toBe("stop");
    expect(classifyCheck(ID, 404, null, {}).kind).toBe("stop");
    expect(classifyCheck(ID, 200, "429", {}).kind).toBe("retry");
    expect(classifyCheck(ID, 408, null, {}).kind).toBe("retry");
  });
});

describe("waitForNextCheck: pause while hidden, check at once when shown", () => {
  it("resolves after the gap when the tab is visible", async () => {
    vi.useFakeTimers();
    let done = false;
    void waitForNextCheck(3_000).then(() => (done = true));
    await vi.advanceTimersByTimeAsync(2_999);
    expect(done).toBe(false);
    await vi.advanceTimersByTimeAsync(1);
    expect(done).toBe(true);
  });

  it("does not resolve while hidden, then resolves as soon as the tab is shown", async () => {
    vi.useFakeTimers();
    let hidden = true;
    Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });
    let done = false;
    void waitForNextCheck(3_000).then(() => (done = true));
    await vi.advanceTimersByTimeAsync(120_000);
    expect(done).toBe(false);
    hidden = false;
    document.dispatchEvent(new Event("visibilitychange"));
    await vi.advanceTimersByTimeAsync(0);
    expect(done).toBe(true);
  });
});

describe("request helpers", () => {
  it("makes a one-time key the job table accepts (8 to 200 characters), new each time", () => {
    const a = newIdempotencyKey();
    expect(a.length).toBeGreaterThanOrEqual(8);
    expect(a.length).toBeLessThanOrEqual(200);
    expect(newIdempotencyKey()).not.toBe(a);
  });

  it("builds the proxied status path with the id encoded", () => {
    expect(statusPath(ID)).toBe(`/api/pi-ceo/api/goal-ticket/analyze/${ID}`);
    expect(statusPath("a/../b")).toBe("/api/pi-ceo/api/goal-ticket/analyze/a%2F..%2Fb");
  });
});
