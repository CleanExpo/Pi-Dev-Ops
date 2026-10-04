// RA-7898 — request-sharing tap (docs/specs/modular-boards.md §4.1).
//
// ProviderUsageCockpit and WikiGraphTile are provenance-baselined and call the
// global `fetch` themselves, so they cannot read the shared sources. While a
// board page is mounted, this tap wraps `window.fetch` for exactly two
// same-origin GET paths: a matching request joins one in flight, or gets a
// fresh Response rebuilt from a body younger than the feed's interval minus
// 1 s; otherwise it goes to the network with the caller's own arguments. The
// shared source reads through the same global `fetch`, so its read and the
// component's coalesce into one request per interval, and the frame shows the
// state of the very response the component rendered. Any other request passes
// straight through, untouched.

import { FEEDS } from "./feeds";

export const TAPPED_FEEDS = ["provider-usage", "wiki-graph"] as const;
/** Matches the poller's own 10 s bound on a read. */
export const SHARED_TIMEOUT_MS = 10_000;

interface Cached { at: number; status: number; statusText: string; headers: [string, string][]; body: string }

function urlOf(input: RequestInfo | URL): URL | null {
  try {
    const raw = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
    return new URL(raw, window.location.href);
  } catch {
    return null;
  }
}

function methodOf(input: RequestInfo | URL, init?: RequestInit): string {
  if (init?.method) return init.method.toUpperCase();
  return typeof input === "object" && "method" in input ? input.method.toUpperCase() : "GET";
}

const rebuild = (c: Cached) => new Response(c.body, { status: c.status, statusText: c.statusText, headers: c.headers });

async function snapshot(res: Response): Promise<Cached> {
  return { at: Date.now(), status: res.status, statusText: res.statusText, headers: [...res.headers.entries()], body: await res.text() };
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
    const routes = new Map<string, string>();
    for (const id of TAPPED_FEEDS) {
      const def = FEEDS.get(id);
      if (def) routes.set(new URL(def.url, window.location.href).href, id);
    }
    const inflight = new Map<string, Promise<Cached>>();
    const recent = new Map<string, Cached>();
    window.fetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const url = urlOf(input);
      const feedId = url && url.origin === window.location.origin ? routes.get(url.href) : undefined;
      if (!url || !feedId || methodOf(input, init) !== "GET") return real(input, init);
      const ttl = (FEEDS.get(feedId)?.intervalMs ?? 0) - 1_000;
      const hit = recent.get(url.href);
      if (hit && Date.now() - hit.at < ttl) return Promise.resolve(rebuild(hit));
      let pending = inflight.get(url.href);
      if (!pending) {
        // The caller's own arguments, minus its abort signal: the read is shared,
        // so one caller unmounting must not cancel it for the others. The tap's
        // own signal drops a request that never answers, so later reads are
        // never stuck joining it.
        const { signal: _signal, ...rest } = init ?? {};
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), SHARED_TIMEOUT_MS);
        pending = real(input, { ...rest, signal: controller.signal }).then(snapshot).then((c) => { recent.set(url.href, c); return c; })
          .finally(() => { clearTimeout(timer); inflight.delete(url.href); });
        inflight.set(url.href, pending);
      }
      return pending.then(rebuild);
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
