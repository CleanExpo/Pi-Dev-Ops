// RA-7898 — request-sharing tap (docs/specs/modular-boards.md §4.1).
//
// ProviderUsageCockpit and WikiGraphTile are provenance-baselined and call the
// global `fetch` themselves, so they cannot read the shared sources. While a
// board page is mounted, this tap wraps `window.fetch` for exactly two GET
// paths: a matching request joins one in flight, or gets a clone of a response
// younger than the feed's interval minus 1 s; otherwise it goes to the network.
// The shared source reads through the same global `fetch`, so its read and the
// component's coalesce into one network request per interval, and the frame
// shows the state of the very response the component rendered. Any other
// request passes straight through, untouched.

import { FEEDS } from "./feeds";

export const TAPPED_FEEDS = ["provider-usage", "wiki-graph"] as const;

interface Slot { at: number; response: Response }

function pathOf(input: RequestInfo | URL): string | null {
  try {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    const url = new URL(raw, "http://local.invalid");
    return url.pathname;
  } catch {
    return null;
  }
}

function methodOf(input: RequestInfo | URL, init?: RequestInit): string {
  if (init?.method) return init.method.toUpperCase();
  return typeof input === "object" && "method" in input ? input.method.toUpperCase() : "GET";
}

let installs = 0;
let original: typeof fetch | null = null;

/** Install the tap; returns the uninstall function. Nested installs share one wrapper. */
export function installFetchTap(): () => void {
  if (typeof window === "undefined") return () => {};
  installs += 1;
  if (installs === 1) {
    const real = window.fetch;
    original = real;
    const routes = new Map(TAPPED_FEEDS.map((id) => [new URL(FEEDS.get(id)!.url, "http://local.invalid").pathname, id]));
    const inflight = new Map<string, Promise<Response>>();
    const recent = new Map<string, Slot>();
    window.fetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const path = pathOf(input);
      const feedId = path ? routes.get(path) : undefined;
      if (!path || !feedId || methodOf(input, init) !== "GET") return real(input, init);
      const ttl = FEEDS.get(feedId)!.intervalMs - 1_000;
      const slot = recent.get(path);
      if (slot && Date.now() - slot.at < ttl) return Promise.resolve(slot.response.clone());
      const pending = inflight.get(path);
      if (pending) return pending.then((r) => r.clone());
      const request = real(path, { cache: "no-store" }).then((response) => {
        recent.set(path, { at: Date.now(), response: response.clone() });
        return response;
      }).finally(() => inflight.delete(path));
      inflight.set(path, request);
      return request.then((r) => r.clone());
    };
  }
  return () => {
    installs -= 1;
    if (installs === 0 && original) {
      window.fetch = original;
      original = null;
    }
  };
}
