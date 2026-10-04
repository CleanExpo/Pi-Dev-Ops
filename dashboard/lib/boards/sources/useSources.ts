"use client";
// RA-7898 — subscribe to several feeds at once (a module may name more than one).

import { useCallback, useRef, useSyncExternalStore } from "react";

import { feed } from "./feeds";
import { emptySnapshot, getSnapshot, subscribe } from "./poller";
import type { SourceSnapshot } from "./types";

type Snaps = readonly SourceSnapshot<unknown>[];

/** Snapshots for `ids`, in order. Stable identity until one of them changes. */
export function useSources(ids: readonly string[]): Snaps {
  const key = ids.join("|");
  const cache = useRef<{ key: string; snaps: Snaps } | null>(null);
  const placeholders = useRef<Map<string, SourceSnapshot<unknown>>>(new Map());

  const sub = useCallback((listener: () => void) => {
    const offs = key.split("|").filter(Boolean).map((id) => subscribe(feed(id), listener));
    return () => offs.forEach((off) => off());
  }, [key]);

  const placeholder = useCallback((id: string) => {
    let snap = placeholders.current.get(id);
    if (!snap) {
      snap = emptySnapshot(id);
      placeholders.current.set(id, snap);
    }
    return snap;
  }, []);

  const get = useCallback((): Snaps => {
    const next = key.split("|").filter(Boolean).map((id) => getSnapshot(id) ?? placeholder(id));
    const prev = cache.current;
    if (prev && prev.key === key && prev.snaps.length === next.length && prev.snaps.every((s, i) => s === next[i])) {
      return prev.snaps;
    }
    cache.current = { key, snaps: next };
    return next;
  }, [key, placeholder]);

  return useSyncExternalStore(sub, get, get);
}
