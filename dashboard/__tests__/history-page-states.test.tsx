/**
 * /history page — a server component reading the sessions table. A query error
 * says "History unavailable", never "No analysis sessions yet.".
 */
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

const query = vi.fn();

vi.mock("@/lib/supabase/server", () => ({
  createServerClient: () => ({
    from: () => ({ select: () => ({ order: () => ({ limit: () => query() }) }) }),
  }),
}));

import HistoryPage from "@/app/(main)/history/page";

async function renderPage() {
  render(await HistoryPage());
}

afterEach(() => {
  cleanup();
  query.mockReset();
});

describe("history page", () => {
  it("ERROR: a query error says history unavailable, not that there are no sessions", async () => {
    query.mockResolvedValue({ data: null, error: { message: "permission denied" } });
    await renderPage();
    expect(screen.getByText("History unavailable: permission denied")).toBeTruthy();
    expect(screen.queryByText("No analysis sessions yet.")).toBeNull();
  });

  it("EMPTY: a successful read with no rows still says no sessions yet", async () => {
    query.mockResolvedValue({ data: [], error: null });
    await renderPage();
    expect(screen.getByText("No analysis sessions yet.")).toBeTruthy();
    expect(screen.queryByText(/History unavailable/)).toBeNull();
  });
});
