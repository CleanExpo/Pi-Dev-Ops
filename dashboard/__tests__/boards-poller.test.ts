/**
 * RA-7898 T2 — the shared poller contract (docs/specs/modular-boards.md §3.1-3.2).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { activeFeedIds, getSnapshot, refresh, resetSources, subscribe } from "@/lib/boards/sources/poller";
import type { FeedDef, FeedRead } from "@/lib/boards/sources/types";

function def(read: FeedDef<unknown>["read"], intervalMs = 1_000): FeedDef<unknown> {
  return { id: "t", url: "/t", intervalMs, read };
}
const live = (value: unknown = 1): FeedRead<unknown> => ({ kind: "live", value });

beforeEach(() => vi.useFakeTimers());
afterEach(() => { resetSources(); vi.useRealTimers(); });

describe("shared poller", () => {
  it("first subscriber starts with one read; a second shares it; one read per interval", async () => {
    const read = vi.fn(async () => live());
    const d = def(read);
    const off1 = subscribe(d, () => {});
    const off2 = subscribe(d, () => {});
    await vi.advanceTimersByTimeAsync(0);
    expect(read).toHaveBeenCalledTimes(1);
    await vi.advanceTimersByTimeAsync(3_000);
    expect(read).toHaveBeenCalledTimes(4);
    off1(); off2();
  });

  it("the last unsubscribe stops the timer", async () => {
    const read = vi.fn(async () => live());
    const off = subscribe(def(read), () => {});
    await vi.advanceTimersByTimeAsync(0);
    off();
    await Promise.resolve();
    expect(activeFeedIds()).toEqual([]);
    await vi.advanceTimersByTimeAsync(5_000);
    expect(read).toHaveBeenCalledTimes(1);
  });

  it("a tick that lands while a read is in flight is skipped, not queued", async () => {
    let release: () => void = () => {};
    const read = vi.fn(() => new Promise<FeedRead<unknown>>((res) => { release = () => res(live()); }));
    subscribe(def(read, 1_000), () => {});
    await vi.advanceTimersByTimeAsync(2_500);
    expect(read).toHaveBeenCalledTimes(1);
    release();
    await vi.advanceTimersByTimeAsync(1_000);
    expect(read).toHaveBeenCalledTimes(2);
  });

  it("a read is aborted at 10 s and counts as failed", async () => {
    const read = vi.fn((signal: AbortSignal) => new Promise<FeedRead<unknown>>((res) => {
      signal.addEventListener("abort", () => res({ kind: "unreachable", value: null, reason: "aborted" }));
    }));
    subscribe(def(read, 60_000), () => {});
    await vi.advanceTimersByTimeAsync(10_000);
    expect(getSnapshot("t")?.state).toBe("unreachable");
  });

  it("refresh() makes one read and adds no timer", async () => {
    const read = vi.fn(async () => live());
    subscribe(def(read, 60_000), () => {});
    await vi.advanceTimersByTimeAsync(0);
    await refresh("t");
    expect(read).toHaveBeenCalledTimes(2);
    expect(vi.getTimerCount()).toBe(1);
  });

  it("states: loading → live → stale on failure after good data → unreachable without it", async () => {
    let next: FeedRead<unknown> = live();
    subscribe(def(async () => next), () => {});
    expect(getSnapshot("t")?.state).toBe("loading");
    await vi.advanceTimersByTimeAsync(0);
    expect(getSnapshot("t")?.state).toBe("live");
    next = { kind: "unreachable", value: null, reason: "down" };
    await vi.advanceTimersByTimeAsync(1_000);
    expect(getSnapshot("t")).toMatchObject({ state: "stale", reason: "down", lastGood: 1 });
    resetSources();
    subscribe(def(async () => next), () => {});
    await vi.advanceTimersByTimeAsync(0);
    expect(getSnapshot("t")?.state).toBe("unreachable");
  });

  it("no_source is reported as such", async () => {
    subscribe(def(async () => ({ kind: "no_source", value: null, reason: "not configured" })), () => {});
    await vi.advanceTimersByTimeAsync(0);
    expect(getSnapshot("t")?.state).toBe("no_source");
  });

  it("an old server timestamp is stale even when the read succeeded", async () => {
    vi.setSystemTime(new Date("2026-10-03T00:01:00Z"));
    subscribe(def(async () => ({ kind: "live", value: 1, serverTs: "2026-10-03T00:00:00Z" })), () => {});
    await vi.advanceTimersByTimeAsync(0);
    expect(getSnapshot("t")?.state).toBe("stale");
  });

  it("a live feed whose reads hang turns stale after 3 × interval", async () => {
    let hang = false;
    const read = vi.fn((signal: AbortSignal) => hang
      ? new Promise<FeedRead<unknown>>((res) => signal.addEventListener("abort", () => res({ kind: "unreachable", value: null })))
      : Promise.resolve(live()));
    subscribe(def(read, 5_000), () => {});
    await vi.advanceTimersByTimeAsync(0);
    hang = true;
    await vi.advanceTimersByTimeAsync(9_000);
    expect(getSnapshot("t")?.state).toBe("live");
    await vi.advanceTimersByTimeAsync(11_000);
    expect(getSnapshot("t")?.state).toBe("stale");
  });

  it("in development, an unsubscribe followed at once by a resubscribe keeps the same poller (no second read)", async () => {
    vi.stubEnv("NODE_ENV", "development");
    const read = vi.fn(async () => live());
    const d = def(read);
    const off = subscribe(d, () => {});
    off();
    subscribe(d, () => {});
    await vi.advanceTimersByTimeAsync(0);
    expect(read).toHaveBeenCalledTimes(1);
    vi.unstubAllEnvs();
  });

  it("outside development, an unmount stops at once so a remount reads fresh", async () => {
    const read = vi.fn(async () => live());
    const d = def(read);
    const off = subscribe(d, () => {});
    await vi.advanceTimersByTimeAsync(0);
    off();
    subscribe(d, () => {});
    await vi.advanceTimersByTimeAsync(0);
    expect(read).toHaveBeenCalledTimes(2);
  });

  it("resetSources() stops everything", async () => {
    subscribe(def(async () => live()), () => {});
    resetSources();
    expect(activeFeedIds()).toEqual([]);
    expect(getSnapshot("t")).toBeNull();
  });
});
