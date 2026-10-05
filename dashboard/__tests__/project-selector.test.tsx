/**
 * ProjectSelector (RA-7844) — the TopBar project menu must show the projects,
 * a loading note while the read is in flight, or an explicit failure. Before
 * the fix a failed read left "Loading projects…" on screen forever.
 */
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import ProjectSelector, { PROJECTS_NONE, PROJECTS_UNAVAILABLE } from "@/components/control/ProjectSelector";
import { fetchProxyJSON } from "@/lib/pi-ceo-fetch";

vi.mock("@/lib/pi-ceo-fetch", () => ({
  fetchProxyJSON: vi.fn(),
}));

const mockedProxy = vi.mocked(fetchProxyJSON);

async function openMenu(): Promise<void> {
  render(<ProjectSelector />);
  await act(async () => {
    await Promise.resolve();
  });
  fireEvent.click(screen.getByRole("button", { name: /all projects/i }));
}

afterEach(() => {
  cleanup();
  mockedProxy.mockReset();
  window.localStorage.clear();
});

describe("ProjectSelector", () => {
  it("ERROR: says the projects are unavailable when the proxy reports an outage", async () => {
    mockedProxy.mockResolvedValue(null);
    await openMenu();
    expect(await screen.findByRole("alert")).toHaveTextContent(PROJECTS_UNAVAILABLE);
    expect(screen.queryByText("Loading projects…")).toBeNull();
  });

  it("ERROR: says the projects are unavailable when the request itself fails", async () => {
    mockedProxy.mockRejectedValue(new TypeError("Failed to fetch"));
    await openMenu();
    expect(await screen.findByRole("alert")).toHaveTextContent(PROJECTS_UNAVAILABLE);
  });

  it("LOADED: lists the projects the source returns", async () => {
    mockedProxy.mockResolvedValue([{ project_id: "pi-dev-ops", repo: "CleanExpo/Pi-Dev-Ops" }]);
    await openMenu();
    expect(await screen.findByText("pi-dev-ops")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("EMPTY: a successful empty read says there are none, not that it is still loading", async () => {
    mockedProxy.mockResolvedValue([]);
    await openMenu();
    expect(await screen.findByRole("status")).toHaveTextContent(PROJECTS_NONE);
    expect(screen.queryByText("Loading projects…")).toBeNull();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows loading, not failure, while the read is still in flight", async () => {
    mockedProxy.mockReturnValue(new Promise(() => undefined));
    await openMenu();
    expect(screen.getByRole("status")).toHaveTextContent("Loading projects…");
    expect(screen.queryByRole("alert")).toBeNull();
  });
});
