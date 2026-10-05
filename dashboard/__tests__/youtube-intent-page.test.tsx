/**
 * /command-centre/youtube-intent page — loaded, empty and error states (AAA check 7, MC-19).
 * A server component: the loader is replaced, the page itself is rendered.
 * "Absent" is the designed state on a deployed host (the catalogue lives on
 * the mesh machine); an unreadable catalogue is an error, never absent.
 */
import { cleanup, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

const loadIntentState = vi.fn();

vi.mock("@/lib/command-centre/youtube-intent-state", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/command-centre/youtube-intent-state")>()),
  loadIntentState: () => loadIntentState(),
}));
vi.mock("@/components/command-centre/DeckThemeShell", () => ({
  DeckThemeShell: ({ children }: { children: ReactNode }) => <div>{children}</div>,
}));

import YouTubeIntentPage from "@/app/(main)/command-centre/youtube-intent/page";

async function renderPage() {
  render(await YouTubeIntentPage());
}

afterEach(() => {
  cleanup();
  loadIntentState.mockReset();
});

describe("youtube-intent page", () => {
  it("LOADED: a present catalogue lists counts and the top strategic selections", async () => {
    loadIntentState.mockResolvedValue({ kind: "ok", summary: {
      updatedAt: "2026-09-29", acceptedCount: 12, excludedCount: 3, boardUrl: null, topics: [],
      topAccepted: [{ video_key: "v1", title: "Pricing strategy", channel: "Founders", watch_count_window: 4, strategic_hits: ["pricing"] }],
      personaTraits: [], verticalPathways: [], wikiPages: [] } });
    await renderPage();
    expect(screen.getByText("Pricing strategy")).toBeTruthy();
    expect(screen.getByText("12")).toBeTruthy();
    expect(document.querySelector('[data-mc-data="intent-signal"]')).not.toBeNull();
  });

  it("EMPTY: an absent catalogue says it is not on this host and marks that honestly", async () => {
    loadIntentState.mockResolvedValue({ kind: "absent" });
    await renderPage();
    const note = screen.getByText(/Not available on this host/);
    expect(note.getAttribute("data-mc-empty")).toMatch(/not deployed to this host/);
    expect(document.querySelector("[data-mc-data]")).toBeNull();
  });

  it("ERROR: an unreadable catalogue shows its message and is not marked as an honest empty", async () => {
    loadIntentState.mockResolvedValue({ kind: "error", message: "Intent catalogue is not valid JSON." });
    await renderPage();
    const note = screen.getByText("Intent catalogue is not valid JSON.");
    expect(note.hasAttribute("data-mc-empty")).toBe(false);
    expect(document.querySelector("[data-mc-data]")).toBeNull();
  });
});
