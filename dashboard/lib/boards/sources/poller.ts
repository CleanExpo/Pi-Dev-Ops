// RA-7898 — one shared, reference-counted poller per feed.
//
// The first subscriber starts the feed (an immediate read, then one timer at
// the feed's interval); later subscribers share it; the last unsubscribe stops
// it. N modules on one feed therefore make ONE request per interval
// (docs/specs/modular-boards.md §3.1). `resetSources()` is the test hook, in the
// pattern of `_resetWallCache()` in lib/wall/source.ts.

import { staleAfterMs, toEpochMs, type FeedDef, type FeedRead, type SourceSnapshot, type SourceState } from "./types";

const REQUEST_TIMEOUT_MS = 10_000;

interface Entry {
  def: FeedDef<unknown>;
  snapshot: SourceSnapshot<unknown>;
  listeners: Set<() => void>;
  timer: ReturnType<typeof setInterval> | null;
  controller: AbortController | null;
  pending: boolean;
  generation: number;
}

const entries = new Map<string, Entry>();

export function emptySnapshot<T>(id: string): SourceSnapshot<T> {
  return {
    id, state: "loading", seq: 0, value: null, lastGood: null, reason: null,
    httpStatus: null, fetchedAt: null, lastGoodAt: null, serverTs: null,
  };
}

function entryFor(def: FeedDef<unknown>): Entry {
  let entry = entries.get(def.id);
  if (!entry) {
    entry = {
      def, snapshot: emptySnapshot(def.id), listeners: new Set(),
      timer: null, controller: null, pending: false, generation: 0,
    };
    entries.set(def.id, entry);
  }
  return entry;
}

function emit(entry: Entry, next: SourceSnapshot<unknown>): void {
  entry.snapshot = next;
  for (const listener of [...entry.listeners]) listener();
}

/** State for a finished read, given what came before (spec §3.2). */
export function nextState(
  read: FeedRead<unknown>, hadGood: boolean, serverTs: number | null, now: number, intervalMs: number,
): SourceState {
  if (read.kind === "no_source") return "no_source";
  if (read.kind === "unreachable") return hadGood ? "stale" : "unreachable";
  if (serverTs !== null && now - serverTs > staleAfterMs(intervalMs)) return "stale";
  return "live";
}

function applyRead(entry: Entry, read: FeedRead<unknown>): void {
  const now = Date.now();
  const prev = entry.snapshot;
  const live = read.kind === "live";
  const serverTs = live ? toEpochMs(read.serverTs ?? null) : prev.serverTs;
  const state = nextState(read, prev.lastGood !== null, live ? serverTs : null, now, entry.def.intervalMs);
  emit(entry, {
    id: prev.id,
    state,
    seq: prev.seq + 1,
    value: read.value,
    lastGood: live ? read.value : prev.lastGood,
    reason: live ? null : read.reason ?? null,
    httpStatus: read.httpStatus ?? null,
    fetchedAt: now,
    lastGoodAt: live ? now : prev.lastGoodAt,
    serverTs,
  });
}

/** A live feed whose last good read has aged past its stale age turns stale. */
function ageCheck(entry: Entry): void {
  const snap = entry.snapshot;
  if (snap.state !== "live" || snap.lastGoodAt === null) return;
  const reference = snap.serverTs ?? snap.lastGoodAt;
  if (Date.now() - reference > staleAfterMs(entry.def.intervalMs)) emit(entry, { ...snap, state: "stale" });
}

async function readOnce(entry: Entry): Promise<void> {
  if (entry.pending) return;
  entry.pending = true;
  const generation = entry.generation;
  const controller = new AbortController();
  entry.controller = controller;
  // The timeout settles the read even when a reader ignores the abort signal,
  // so one hung request can never block the feed's later ticks.
  let timeout: ReturnType<typeof setTimeout> | undefined;
  const timedOut = new Promise<FeedRead<unknown>>((resolve) => {
    timeout = setTimeout(() => {
      controller.abort();
      resolve({ kind: "unreachable", value: null, reason: `no answer within ${REQUEST_TIMEOUT_MS / 1000} s` });
    }, REQUEST_TIMEOUT_MS);
  });
  try {
    const read = await Promise.race([entry.def.read(controller.signal), timedOut]);
    if (generation === entry.generation) applyRead(entry, read);
  } finally {
    clearTimeout(timeout);
    if (generation === entry.generation) {
      entry.pending = false;
      entry.controller = null;
    }
  }
}

function tick(entry: Entry): void {
  ageCheck(entry);
  void readOnce(entry);
}

function start(entry: Entry): void {
  entry.generation += 1;
  entry.pending = false;
  entry.snapshot = emptySnapshot(entry.def.id);
  void readOnce(entry);
  entry.timer = setInterval(() => tick(entry), entry.def.intervalMs);
}

function stop(entry: Entry): void {
  if (entry.timer !== null) clearInterval(entry.timer);
  entry.timer = null;
  entry.controller?.abort();
  entry.controller = null;
  entry.pending = false;
  entry.generation += 1;
}

/** Subscribe to a feed. Returns the unsubscribe function. */
export function subscribe(def: FeedDef<unknown>, listener: () => void): () => void {
  const entry = entryFor(def);
  entry.listeners.add(listener);
  if (entry.listeners.size === 1 && entry.timer === null) start(entry);
  return () => {
    entry.listeners.delete(listener);
    if (entry.listeners.size > 0) return;
    // In development, React mounts every component twice (unsubscribe and
    // resubscribe in one go); stopping on the next microtask keeps that from
    // making a second request. Everywhere else an unmount stops at once, so a
    // fresh mount always starts with a fresh read.
    if (process.env.NODE_ENV === "development") queueMicrotask(() => { if (entry.listeners.size === 0) stop(entry); });
    else stop(entry);
  };
}

export function getSnapshot(id: string): SourceSnapshot<unknown> | null {
  return entries.get(id)?.snapshot ?? null;
}

/** One immediate read, e.g. after an action's write succeeded. Never adds a timer. */
export async function refresh(id: string): Promise<void> {
  const entry = entries.get(id);
  if (!entry || entry.timer === null) return;
  await readOnce(entry);
}

/** Feed a read observed elsewhere (the request-sharing tap) into a running feed. */
export function publish(id: string, read: FeedRead<unknown>): void {
  const entry = entries.get(id);
  if (entry && entry.timer !== null) applyRead(entry, read);
}

/** Test hook: stop every poller and drop every cache. */
export function resetSources(): void {
  for (const entry of entries.values()) {
    stop(entry);
    entry.listeners.clear();
  }
  entries.clear();
}

/** Diagnostics for tests: how many feeds are currently polling. */
export function activeFeedIds(): string[] {
  return [...entries.values()].filter((e) => e.timer !== null).map((e) => e.def.id);
}
