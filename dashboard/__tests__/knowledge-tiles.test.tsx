/**
 * Knowledge deck tiles — loaded, empty and error states (AAA check 7, MC-15).
 * Both tiles fetch on mount. This file imports two listed panels, so each
 * describe block names its panel: the check-7 scorer counts a test for a
 * panel only when its describe/title names it.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { IntentCatalogTile } from "@/components/command-centre/youtube-intent/IntentCatalogTile";
import { WikiGraphTile } from "@/components/command-centre/wiki-graph/WikiGraphTile";

function serve(body: unknown, status = 200) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status })));
}
function reject(message: string) {
  vi.stubGlobal("fetch", vi.fn(async () => { throw new Error(message); }));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("WikiGraphTile", () => {
  it("LOADED: shows the page and link counts", async () => {
    serve({ pageCount: 42, edgeCount: 97, lastSync: "2026-09-29T00:00:00Z" });
    render(<WikiGraphTile />);
    expect(await screen.findByText("42")).toBeTruthy();
    expect(screen.getByText("97")).toBeTruthy();
  });

  it("EMPTY: an unsynced wiki reads zero pages and zero links", async () => {
    serve({ pageCount: 0, edgeCount: 0, lastSync: null });
    render(<WikiGraphTile />);
    expect(await screen.findByText(/links in the knowledge base/)).toBeTruthy();
    expect(screen.getAllByText("0")).toHaveLength(2);
  });

  it("ERROR: a non-OK response says the graph could not load", async () => {
    serve({ error: "down" }, 503);
    render(<WikiGraphTile />);
    expect(await screen.findByText("Could not load wiki graph: HTTP 503")).toBeTruthy();
    expect(screen.queryByText(/links in the knowledge base/)).toBeNull();
  });

  it("ERROR: a rejected fetch shows its message", async () => {
    reject("offline");
    render(<WikiGraphTile />);
    expect(await screen.findByText("Could not load wiki graph: offline")).toBeTruthy();
  });
});

describe("IntentCatalogTile", () => {
  it("LOADED: shows signal counts and the top topics", async () => {
    serve({ updatedAt: "2026-09-29", acceptedCount: 12, excludedCount: 3, boardUrl: null, available: true,
      topics: [{ topic: "pricing", frequency_score: 3 }, { topic: "hiring", frequency_score: 2 }] });
    render(<IntentCatalogTile />);
    expect(await screen.findByText("12")).toBeTruthy();
    expect(screen.getByText("Top topics: pricing, hiring")).toBeTruthy();
  });

  it("EMPTY: a catalogue not on this host shows its warning, not zero counts", async () => {
    serve({ updatedAt: null, acceptedCount: 0, excludedCount: 0, topics: [], boardUrl: null,
      available: false, warning: "Not available on this host." });
    render(<IntentCatalogTile />);
    expect(await screen.findByText("Not available on this host.")).toBeTruthy();
    expect(screen.queryByText(/strategic signals/)).toBeNull();
    expect(screen.getByText("Top topics: none yet")).toBeTruthy();
  });

  it("ERROR: a non-OK response says the catalogue could not load", async () => {
    serve({ error: "boom" }, 500);
    render(<IntentCatalogTile />);
    expect(await screen.findByText("Could not load intent catalog: HTTP 500")).toBeTruthy();
    expect(screen.queryByText(/strategic signals/)).toBeNull();
  });

  it("ERROR: a rejected fetch shows its message", async () => {
    reject("offline");
    render(<IntentCatalogTile />);
    expect(await screen.findByText("Could not load intent catalog: offline")).toBeTruthy();
  });
});
