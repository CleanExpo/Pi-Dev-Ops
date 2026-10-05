/**
 * GoalProjectPicker — the brief list must show real briefs, an explicit
 * empty note, or an explicit load failure. Never a silent empty select.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import GoalProjectPicker, { type GoalProject } from "@/components/control/GoalProjectPicker";
import { BRIEFS_EMPTY_NOTE, BRIEFS_LOAD_FAIL_NOTE } from "@/lib/control/goalCopy";
import { fetchProxyJSON } from "@/lib/pi-ceo-fetch";

vi.mock("@/lib/pi-ceo-fetch", () => ({
  fetchProxyJSON: vi.fn(),
}));

const mockedProxy = vi.mocked(fetchProxyJSON);

function brief(overrides: Partial<GoalProject> = {}): GoalProject {
  return {
    id: "brief-carpet",
    title: "Carpet Cleaning Hub",
    description: "Booking site for carpet cleaners",
    audience: "Suburban home owners",
    problem: "",
    users: "",
    outcomes: "",
    constraints: "",
    out_of_scope: "",
    ...overrides,
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderPicker(selectedId = "") {
  const onSelect = vi.fn();
  const onClear = vi.fn();
  render(
    <GoalProjectPicker selectedId={selectedId} disabled={false} onSelect={onSelect} onClear={onClear} />,
  );
  return { onSelect, onClear };
}

beforeEach(() => {
  mockedProxy.mockReset();
  window.localStorage.clear();
  window.sessionStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
  cleanup();
});

describe("GoalProjectPicker", () => {
  it("LOADED: lists each brief from /api/goal-projects and describes the selected one", async () => {
    mockedProxy.mockResolvedValue({ projects: [brief()] });
    const { onSelect } = renderPicker("brief-carpet");

    expect(await screen.findByRole("option", { name: "Carpet Cleaning Hub" })).toBeTruthy();
    expect(mockedProxy).toHaveBeenCalledWith("/api/goal-projects");
    expect(screen.getByText(/Booking site for carpet cleaners/)).toBeTruthy();
    expect(screen.getByText(/Audience: Suburban home owners/)).toBeTruthy();
    expect(screen.queryByText("Loading project briefs…")).toBeNull();
    expect(screen.queryByText(BRIEFS_EMPTY_NOTE)).toBeNull();
    expect(screen.queryByText(BRIEFS_LOAD_FAIL_NOTE)).toBeNull();
    await waitFor(() => expect(onSelect).toHaveBeenCalledWith(expect.objectContaining({ id: "brief-carpet" })));
  });

  it("EMPTY: a genuine empty list shows the empty note, not the failure note", async () => {
    mockedProxy.mockResolvedValue({ projects: [] });
    renderPicker();

    expect(await screen.findByText(BRIEFS_EMPTY_NOTE)).toBeTruthy();
    expect(screen.queryByText(BRIEFS_LOAD_FAIL_NOTE)).toBeNull();
    expect(screen.queryByText("Loading project briefs…")).toBeNull();
  });

  it("ERROR: backend unreachable (proxy returns null) shows the failure note and Try again", async () => {
    mockedProxy.mockResolvedValue(null);
    renderPicker();

    expect(await screen.findByText(BRIEFS_LOAD_FAIL_NOTE)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Try again" })).toBeTruthy();
    expect(screen.queryByText("Loading project briefs…")).toBeNull();
    expect(screen.queryByText(BRIEFS_EMPTY_NOTE)).toBeNull();
  });

  it("ERROR: a 500-shaped body without `projects` is a failure, not an empty list", async () => {
    mockedProxy.mockResolvedValue({ detail: { hint: "database down" } });
    renderPicker();

    expect(await screen.findByText(BRIEFS_LOAD_FAIL_NOTE)).toBeTruthy();
    expect(screen.queryByText(BRIEFS_EMPTY_NOTE)).toBeNull();
  });

  it("ERROR: a rejected read shows the failure note, and Try again reloads the list", async () => {
    mockedProxy.mockRejectedValueOnce(new Error("network"));
    renderPicker();

    const retry = await screen.findByRole("button", { name: "Try again" });
    expect(screen.getByText(BRIEFS_LOAD_FAIL_NOTE)).toBeTruthy();

    mockedProxy.mockResolvedValueOnce({ projects: [brief()] });
    fireEvent.click(retry);
    expect(await screen.findByRole("option", { name: "Carpet Cleaning Hub" })).toBeTruthy();
    expect(screen.queryByText(BRIEFS_LOAD_FAIL_NOTE)).toBeNull();
    expect(mockedProxy).toHaveBeenCalledTimes(2);
  });

  it("WRITE: Save brief POSTs the draft and selects the created brief", async () => {
    mockedProxy.mockResolvedValueOnce({ projects: [] });
    const created = brief({ id: "brief-new", title: "Window Washing Pro" });
    const fetchMock = vi.fn(async () => jsonResponse({ project: created }));
    vi.stubGlobal("fetch", fetchMock);
    mockedProxy.mockResolvedValueOnce({ projects: [created] });
    const { onSelect } = renderPicker();

    await screen.findByText(BRIEFS_EMPTY_NOTE);
    fireEvent.click(screen.getByRole("button", { name: "Create brief" }));
    const [title, description, audience] = screen.getAllByRole("textbox");
    fireEvent.change(title, { target: { value: "Window Washing Pro" } });
    fireEvent.change(description, { target: { value: "Quotes and bookings for window washers" } });
    fireEvent.change(audience, { target: { value: "Small commercial landlords" } });
    fireEvent.click(screen.getByRole("button", { name: "Save brief" }));

    await waitFor(() => expect(onSelect).toHaveBeenCalledWith(created));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("/api/pi-ceo/api/goal-projects");
    expect(init.method).toBe("POST");
    expect(JSON.parse(String(init.body))).toMatchObject({ title: "Window Washing Pro" });
    expect(await screen.findByRole("option", { name: "Window Washing Pro" })).toBeTruthy();
  });
});
