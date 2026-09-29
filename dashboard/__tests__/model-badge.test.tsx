/**
 * ModelBadge — loaded, empty and error states (AAA check 7, MC-04).
 * It reads /api/zte directly with fetch; "empty" is a successful read where
 * the backend has observed no score and no model yet.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ModelBadge from "@/components/control/ModelBadge";

function serve(body: unknown, status = 200) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status })));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("ModelBadge", () => {
  it("LOADED: shows the observed model, its score and the SDK mode", async () => {
    serve({ score: 92, model: "Sonnet", model_id: "claude-sonnet-x", sdk_mode: true, source: "backend" });
    render(<ModelBadge />);
    expect(await screen.findByText("Sonnet")).toBeTruthy();
    expect(screen.getByText("claude-sonnet-x")).toBeTruthy();
    expect(screen.getByText("Excellent")).toBeTruthy();
    expect(screen.getByText("Reported enabled")).toBeTruthy();
    expect(screen.queryByText("Loading…")).toBeNull();
  });

  it("EMPTY: nothing observed says so instead of inventing a score", async () => {
    serve({ score: null, model: null, model_id: null, sdk_mode: null, source: "unavailable" });
    render(<ModelBadge />);
    expect(await screen.findByText("Model identity is unverified")).toBeTruthy();
    expect(screen.getAllByText("Not observed").length).toBe(3);
    expect(screen.queryByText("Excellent")).toBeNull();
  });

  it("ERROR: a non-OK response shows the status, not stale data", async () => {
    serve({ error: "boom" }, 503);
    render(<ModelBadge />);
    expect(await screen.findByText("HTTP 503")).toBeTruthy();
    expect(screen.queryByText("Observed model")).toBeNull();
  });

  it("ERROR: a rejected fetch shows its message", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("network down"); }));
    render(<ModelBadge />);
    expect(await screen.findByText("network down")).toBeTruthy();
    expect(screen.queryByText("Loading…")).toBeNull();
  });
});
