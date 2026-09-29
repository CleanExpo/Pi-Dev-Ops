/**
 * WP-05 — the YouTube intent catalogue lives on the local mesh machine. On a deployed
 * host its state file is absent; that must read as "not available on this host", never
 * as a live zero, a raw ENOENT with a server path, or a link to localhost.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IntentCatalogTile } from "@/components/command-centre/youtube-intent/IntentCatalogTile";
import { INTENT_ABSENT_MESSAGE, loadIntentState } from "@/lib/command-centre/youtube-intent-state";

afterEach(() => {
  vi.unstubAllGlobals();
  cleanup();
});

const STATE = JSON.stringify({
  updated_at: "2026-09-28T00:00:00Z",
  videos: [
    { video_key: "a", status: "accepted", watch_count_window: 3 },
    { video_key: "b", status: "excluded" },
  ],
  topics: [{ topic: "restoration", frequency_score: 1, confidence: 0.9 }],
});

function missing(): Promise<string> {
  return Promise.reject(Object.assign(new Error("ENOENT: /var/task/.harness/x"), { code: "ENOENT" }));
}

describe("loadIntentState", () => {
  it("summarises a present catalogue and hides the localhost board in production", async () => {
    const out = await loadIntentState(async () => STATE, true);
    expect(out.kind).toBe("ok");
    if (out.kind !== "ok") return;
    expect(out.summary.acceptedCount).toBe(1);
    expect(out.summary.excludedCount).toBe(1);
    expect(out.summary.boardUrl).toBeNull();
  });

  it("links the local board outside production", async () => {
    const out = await loadIntentState(async () => STATE, false);
    expect(out.kind === "ok" && out.summary.boardUrl).toBe("http://localhost:7119");
  });

  it("reports a missing file as absent, not as an error carrying a server path", async () => {
    expect(await loadIntentState(missing, true)).toEqual({ kind: "absent" });
  });

  it("reports unreadable JSON as an error without echoing file contents or paths", async () => {
    const out = await loadIntentState(async () => "{nope", true);
    expect(out.kind).toBe("error");
    expect(out.kind === "error" && out.message).not.toMatch(/\/|ENOENT/);
  });
});

describe("IntentCatalogTile", () => {
  it("does not claim live data when the catalogue is not on this host", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            available: false,
            warning: INTENT_ABSENT_MESSAGE,
            updatedAt: null,
            acceptedCount: 0,
            excludedCount: 0,
            topics: [],
            boardUrl: null,
          }),
          { status: 200, headers: { "Content-Type": "application/json" } },
        ),
      ),
    );
    render(<IntentCatalogTile />);
    await waitFor(() => expect(screen.getByText(INTENT_ABSENT_MESSAGE)).toBeTruthy());
    expect(screen.queryByLabelText(/Source: live/)).toBeNull();
    expect(screen.queryByText(/Open Excalidraw board/)).toBeNull();
  });
});
