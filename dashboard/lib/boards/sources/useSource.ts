"use client";
// RA-7898 — React binding for the shared pollers.

import { useCallback, useSyncExternalStore } from "react";

import { feed } from "./feeds";
import { emptySnapshot, getSnapshot, refresh, subscribe } from "./poller";
import type { SourceSnapshot } from "./types";

const SERVER_SNAPSHOTS = new Map<string, SourceSnapshot<unknown>>();

function serverSnapshot(id: string): SourceSnapshot<unknown> {
  let snap = SERVER_SNAPSHOTS.get(id);
  if (!snap) {
    snap = emptySnapshot(id);
    SERVER_SNAPSHOTS.set(id, snap);
  }
  return snap;
}

export interface UseSource<T> extends SourceSnapshot<T> {
  /** One immediate re-read, e.g. after a write succeeded. */
  refresh: () => Promise<void>;
}

/** Subscribe to one feed. N callers share one poller and one request per interval. */
export function useSource<T>(id: string): UseSource<T> {
  const sub = useCallback((listener: () => void) => subscribe(feed(id), listener), [id]);
  const get = useCallback(() => getSnapshot(id) ?? serverSnapshot(id), [id]);
  const snap = useSyncExternalStore(sub, get, () => serverSnapshot(id)) as SourceSnapshot<T>;
  const again = useCallback(() => refresh(id), [id]);
  return { ...snap, refresh: again };
}
