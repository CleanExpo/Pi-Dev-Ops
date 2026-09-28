/**
 * CuratorProposalsPanel — loaded, empty and error states (RA-1109).
 * A failed read must never render as "No pending proposals".
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import CuratorProposalsPanel from "@/components/control/CuratorProposalsPanel";

afterEach(() => {
  vi.unstubAllGlobals();
  cleanup();
});

const EMPTY_COPY = /No pending proposals/;

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("CuratorProposalsPanel", () => {
  it("LOADED: renders a proposal from the response", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({
          total: 1,
          returned: 1,
          by_status: { pending: 1, accepted: 2, rejected_dup: 3 },
          proposals: [
            {
              proposal_id: "p1",
              ts: new Date().toISOString(),
              proposed_skill_name: "retry-flaky-ci",
              cluster_summary: "Flaky CI retried by hand",
              trigger_source: "lessons",
              evidence_count: 5,
              status: "pending",
            },
          ],
        }),
      ),
    );
    render(<CuratorProposalsPanel />);
    expect(await screen.findByText("retry-flaky-ci")).toBeTruthy();
    expect(screen.getByText("Flaky CI retried by hand")).toBeTruthy();
    expect(screen.getByText("1 pending · 2 accepted · 3 rejected")).toBeTruthy();
    expect(screen.queryByText(EMPTY_COPY)).toBeNull();
  });

  it("EMPTY: shows the explicit no-pending copy", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => jsonResponse({ total: 0, returned: 0, by_status: {}, proposals: [] })),
    );
    render(<CuratorProposalsPanel />);
    expect(await screen.findByText(EMPTY_COPY)).toBeTruthy();
  });

  it("does not claim 'No pending proposals' before the first read answers", () => {
    vi.stubGlobal("fetch", vi.fn(() => new Promise<Response>(() => undefined)));
    render(<CuratorProposalsPanel />);
    expect(screen.queryByText(EMPTY_COPY)).toBeNull();
    expect(screen.getByText(/Loading/)).toBeTruthy();
  });

  it("ERROR: a rejected fetch shows the error", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("network down"); }));
    render(<CuratorProposalsPanel />);
    expect(await screen.findByText(/network down/)).toBeTruthy();
    expect(screen.queryByText(EMPTY_COPY)).toBeNull();
  });

  it("ERROR: the proxy's error field is shown", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse({ error: "upstream unreachable", total: 0, returned: 0, by_status: {}, proposals: [] }),
      ),
    );
    render(<CuratorProposalsPanel />);
    expect(await screen.findByText(/upstream unreachable/)).toBeTruthy();
    expect(screen.queryByText(EMPTY_COPY)).toBeNull();
  });

  it("ERROR: a 500 with a non-JSON body is an error, not an empty list", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => new Response("Internal Server Error", { status: 500 })),
    );
    render(<CuratorProposalsPanel />);
    expect(await screen.findByText(/HTTP 500/)).toBeTruthy();
    expect(screen.queryByText(EMPTY_COPY)).toBeNull();
  });
});
