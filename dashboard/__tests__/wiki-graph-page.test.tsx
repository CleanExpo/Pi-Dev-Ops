/**
 * /command-centre/wiki-graph page — loaded, empty and error states (AAA check 7, MC-18).
 * A server component reading wiki_pages from the Unite-Group Supabase project.
 * The client is replaced, the page and the real graph builder are rendered;
 * the canvas (a browser-only drawing surface) is a stand-in.
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const query = vi.fn();

vi.mock("@/lib/supabase/unite-group-server", () => ({
  createUniteGroupServerClient: () => ({
    from: () => ({ select: () => ({ limit: () => query() }) }),
  }),
}));
vi.mock("@/components/command-centre/wiki-graph/WikiGraphCanvas", () => ({
  WikiGraphCanvas: ({ nodes }: { nodes: unknown[] }) => <div data-testid="canvas">{nodes.length} nodes</div>,
}));

import WikiGraphPage from "@/app/(main)/command-centre/wiki-graph/page";

const row = (id: string, content: string) => ({
  id, title: id, tags: [], content, updated_at: "2026-09-29T00:00:00Z",
});

async function renderPage() {
  render(await WikiGraphPage());
}

afterEach(() => {
  cleanup();
  query.mockReset();
  vi.restoreAllMocks();
});

describe("wiki-graph page", () => {
  it("LOADED: wiki pages render as a graph with page and link counts", async () => {
    query.mockResolvedValue({ data: [row("alpha", "see [[beta]]"), row("beta", "back to [[alpha]]")], error: null });
    await renderPage();
    expect(screen.getByTestId("canvas").textContent).toBe("2 nodes");
    expect(screen.getByText("pages").textContent).toContain("2");
    expect(document.querySelector('[data-mc-data="wiki-graph"]')).not.toBeNull();
  });

  it("EMPTY: zero pages says the wiki is not synced yet", async () => {
    query.mockResolvedValue({ data: [], error: null });
    await renderPage();
    expect(screen.getByText("Wiki not synced")).toBeTruthy();
    expect(screen.queryByTestId("canvas")).toBeNull();
  });

  it("ERROR: a query error says the source did not respond, not that the wiki is empty", async () => {
    query.mockResolvedValue({ data: null, error: { message: "permission denied" } });
    await renderPage();
    expect(screen.getByText("Wiki graph unavailable")).toBeTruthy();
    expect(screen.queryByText("Wiki not synced")).toBeNull();
    expect(document.querySelector("[data-mc-data]")).toBeNull();
  });

  it("ERROR: a thrown client failure is also unavailable", async () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    query.mockRejectedValue(new Error("SUPABASE_UNITE_GROUP_SERVICE_KEY missing"));
    await renderPage();
    expect(screen.getByText("Wiki graph unavailable")).toBeTruthy();
  });
});
