/**
 * RA-7898 — leaving a board cancels its shared requests, and a curator list
 * whose counts contradict its rows is a failed read.
 */
import { afterEach, describe, expect, it, vi } from "vitest";

import { readCurator } from "@/lib/boards/sources/feeds-direct";
import { installFetchTap } from "@/lib/boards/sources/fetch-tap";
import { serve, signal, without } from "./boards-feed-fixtures";

afterEach(() => vi.unstubAllGlobals());

describe("fetch tap lifecycle", () => {
  it("the last uninstall aborts a pending shared request; a remount starts clean", async () => {
    const network = vi.fn((_u: string, _i?: RequestInit) => new Promise<Response>(() => {}));
    vi.stubGlobal("fetch", network);
    const uninstall = installFetchTap();
    const first = window.fetch("/api/command-centre/provider-usage");
    first.catch(() => undefined);
    uninstall();
    expect(network.mock.calls[0][1]?.signal?.aborted).toBe(true);
    await expect(first).rejects.toBeDefined();
    const again = installFetchTap();
    void window.fetch("/api/command-centre/provider-usage").catch(() => undefined);
    expect(network).toHaveBeenCalledTimes(2);
    expect(network.mock.calls[1][1]?.signal?.aborted).toBe(false);
    again();
  });
});

const ROW = { ts: "2026-10-04T00:00:00Z", proposal_id: "p1", status: "pending", proposed_skill_name: "retry" };
const LIST = { total: 1, returned: 1, by_status: { pending: 1 }, proposals: [ROW] };

describe("curator counts and rows agree", () => {
  it("a consistent list is live", async () => { serve(LIST); expect((await readCurator(signal)).kind).toBe("live"); });
  it("an empty consistent list is live", async () => {
    serve({ total: 0, returned: 0, by_status: {}, proposals: [] });
    expect((await readCurator(signal)).kind).toBe("live");
  });
  it.each([
    ["a row without status", { ...LIST, proposals: [without(ROW, "status")] }],
    ["a row without proposal_id", { ...LIST, proposals: [without(ROW, "proposal_id")] }],
    ["no total", without(LIST, "total")],
    ["no returned", without(LIST, "returned")],
    ["1 pending beside an empty list", { total: 1, returned: 0, by_status: { pending: 1 }, proposals: [] }],
    ["returned not matching the rows", { ...LIST, returned: 2 }],
    ["a pending count not matching total", { ...LIST, by_status: { pending: 3 } }],
  ])("%s is unreachable", async (_k, body) => {
    serve(body);
    expect((await readCurator(signal)).kind).toBe("unreachable");
  });
  it("more than the limit pending returns the first ten and is live", async () => {
    const rows = Array.from({ length: 10 }, (_, i) => ({ ...ROW, proposal_id: `p${i}` }));
    serve({ total: 12, returned: 10, by_status: { pending: 12 }, proposals: rows });
    expect((await readCurator(signal)).kind).toBe("live");
  });
});
