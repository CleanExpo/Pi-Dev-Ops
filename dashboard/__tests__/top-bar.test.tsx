/**
 * TopBar model chip — loaded, empty and error states (AAA check 7, MC-00).
 * The chip reads /api/zte. It used to start as a hard-coded "claude-opus-5"
 * and keep it when the read failed, showing an unobserved model as active.
 */
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/control/ProjectSelector", () => ({ default: () => null }));
vi.mock("@/components/ThemeToggle", () => ({ default: () => null }));

import TopBar from "@/components/control/TopBar";

function serve(body: unknown, status = 200) {
  vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify(body), { status })));
}

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

describe("TopBar", () => {
  it("LOADED: the chip names the model the backend observed", async () => {
    serve({ model: "Sonnet", model_id: "claude-sonnet-x" });
    render(<TopBar />);
    const chip = await screen.findByText("Sonnet");
    expect(chip.getAttribute("title")).toBe("Active model: Sonnet");
  });

  it("EMPTY: no observed model reads 'model unknown', never a default name", async () => {
    serve({ model: null, model_id: null });
    render(<TopBar />);
    await waitFor(() => expect(fetch).toHaveBeenCalledWith("/api/zte"));
    expect(await screen.findByText("model unknown")).toBeTruthy();
    expect(screen.queryByText("claude-opus-5")).toBeNull();
  });

  it("ERROR: a non-OK response leaves the model unknown", async () => {
    serve({ error: "down" }, 503);
    render(<TopBar />);
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect((await screen.findByText("model unknown")).getAttribute("title")).toBe("Active model not observed");
  });

  it("ERROR: a rejected fetch leaves the model unknown", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => { throw new Error("offline"); }));
    render(<TopBar />);
    await waitFor(() => expect(fetch).toHaveBeenCalled());
    expect(await screen.findByText("model unknown")).toBeTruthy();
    expect(screen.queryByText("claude-opus-5")).toBeNull();
  });
});
