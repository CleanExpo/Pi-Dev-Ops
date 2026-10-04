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

import { useLayoutEffect } from "react";

import { FEEDS } from "./feeds";

export const TAPPED_FEEDS = ["provider-usage", "wiki-graph"] as const;

interface Cached { at: number; status: number; statusText: string; headers: [string, string][]; body: string }

/** A shared wire request is cut off here, so one hung request cannot hold the path for good. */
export const TAP_TIMEOUT_MS = 10_000;

interface Flight { promise: Promise<Cached>; controller: AbortController; waiters: number }

function callerSignal(input: RequestInfo | URL, init?: RequestInit): AbortSignal | undefined {
  if (init?.signal) return init.signal;
  return typeof Request !== "undefined" && input instanceof Request ? input.signal : undefined;
}

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
    const inflight = new Map<string, Flight>();
    const recent = new Map<string, Cached>();
    window.fetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
      const url = urlOf(input);
      const feedId = url && url.origin === window.location.origin ? routes.get(url.href) : undefined;
      if (!url || !feedId || methodOf(input, init) !== "GET") return real(input, init);
      const ttl = (FEEDS.get(feedId)?.intervalMs ?? 0) - 1_000;
      const hit = recent.get(url.href);
      if (hit && Date.now() - hit.at < ttl) return Promise.resolve(rebuild(hit));
      let flight = inflight.get(url.href);
      if (!flight) {
        // The read is shared, so it runs on its own controller, not any one
        // caller's signal. It is aborted when the last waiter leaves or at
        // TAP_TIMEOUT_MS, and leaves the in-flight map either way, even if the
        // network ignores the abort.
        const controller = new AbortController();
        const { signal: _signal, ...rest } = init ?? {};
        const timer = setTimeout(() => controller.abort(new DOMException("shared request timed out", "TimeoutError")), TAP_TIMEOUT_MS);
        const aborted = new Promise<never>((_, reject) => {
          controller.signal.addEventListener("abort", () => reject(controller.signal.reason), { once: true });
        });
        const promise = Promise.race([real(input, { ...rest, signal: controller.signal }), aborted])
          .then(snapshot).then((c) => { recent.set(url.href, c); return c; })
          .finally(() => { clearTimeout(timer); if (inflight.get(url.href)?.promise === promise) inflight.delete(url.href); });
        promise.catch(() => undefined);
        flight = { promise, controller, waiters: 0 };
        inflight.set(url.href, flight);
      }
      const shared = flight;
      const signal = callerSignal(input, init);
      shared.waiters += 1;
      return new Promise<Response>((resolve, reject) => {
        let left = false;
        const leave = () => {
          if (left) return false;
          left = true;
          signal?.removeEventListener("abort", onAbort);
          shared.waiters -= 1;
          return true;
        };
        // One caller aborting rejects only its own promise; the last one out cancels the wire request.
        function onAbort() {
          if (!leave()) return;
          if (shared.waiters === 0) shared.controller.abort(signal?.reason);
          reject(signal?.reason ?? new DOMException("The operation was aborted.", "AbortError"));
        }
        if (signal?.aborted) { onAbort(); return; }
        signal?.addEventListener("abort", onAbort);
        shared.promise.then((c) => { if (leave()) resolve(rebuild(c)); }, (e) => { if (leave()) reject(e); });
      });
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

/**
 * Install the tap for a board page. A layout effect runs before any child's
 * passive effect, so the tap is in place before the modules' first reads.
 */
export function useFetchTap(): void {
  useLayoutEffect(() => installFetchTap(), []);
}
