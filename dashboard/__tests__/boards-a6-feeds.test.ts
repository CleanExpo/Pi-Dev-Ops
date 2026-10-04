/**
 * RA-7898 A6 — the "existing pages unchanged" spec routes one set of bodies to
 * main and to this branch. A body this branch rejects makes A6 compare an
 * error panel against main's data, so every A6 body must read as live through
 * the same readers the boards run, routed exactly as the spec routes them.
 */
import { afterEach, expect, it, vi } from "vitest";

import { DIRECT_FEEDS } from "@/lib/boards/sources/feeds-direct";
import { PROXY_FEEDS } from "@/lib/boards/sources/feeds-proxy";
import { A6_FEEDS } from "../e2e/a6-feeds";
import { signal } from "./boards-feed-fixtures";

afterEach(() => vi.unstubAllGlobals());

const served = new Set<string>();
function routeLikeA6() {
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const path = new URL(url, "http://dashboard.test").pathname;
    const body = A6_FEEDS[path];
    if (body === undefined) return new Response('{"error":"routed test: not provided"}', { status: 503 });
    served.add(path);
    return new Response(JSON.stringify(body), { status: 200, headers: { "content-type": "application/json" } });
  }));
}

it("every A6 body reads as live on this branch", async () => {
  routeLikeA6();
  const notLive: string[] = [];
  for (const feed of [...DIRECT_FEEDS, ...PROXY_FEEDS]) {
    const before = served.size;
    const read = await feed.read(signal);
    if (served.size > before && read.kind !== "live") notLive.push(`${feed.id}: ${read.kind}`);
  }
  expect(notLive).toEqual([]);
  // Every body was reached by some reader, so none of them went unchecked.
  expect([...served].sort()).toEqual(Object.keys(A6_FEEDS).sort());
});
