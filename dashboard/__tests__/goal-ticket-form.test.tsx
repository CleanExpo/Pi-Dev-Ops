/**
 * GoalTicketForm — analyze drafts, write to Linear, and every failure
 * surfaces as visible copy rather than a stuck "Analyzing…" button.
 */
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import GoalTicketForm from "@/components/control/GoalTicketForm";
import type { GoalProject } from "@/components/control/GoalProjectPicker";
import { BRIEFS_EMPTY_NOTE } from "@/lib/control/goalCopy";
import { fetchProxyJSON } from "@/lib/pi-ceo-fetch";

vi.mock("@/lib/pi-ceo-fetch", () => ({
  fetchProxyJSON: vi.fn(),
}));

const mockedProxy = vi.mocked(fetchProxyJSON);

const BRIEF: GoalProject = {
  id: "brief-carpet",
  title: "Carpet Cleaning Hub",
  description: "Booking site for carpet cleaners",
  audience: "Suburban home owners",
  problem: "",
  users: "",
  outcomes: "",
  constraints: "",
  out_of_scope: "",
};

const DRAFT = {
  title: "Add a booking calendar page",
  expected_behaviour: "Owners can pick a free slot and book it",
  acceptance: "A stranger opens /book, clicks a free slot and sees a confirmation message",
};

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

type Handler = (url: string, init?: RequestInit) => Response | Promise<Response>;

function stubFetch(handler: Handler) {
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => handler(String(input), init));
  vi.stubGlobal("fetch", fn);
  return fn;
}

async function fillForm() {
  const select = await screen.findByRole("combobox", { name: "Project brief" });
  await screen.findByRole("option", { name: "Carpet Cleaning Hub" });
  fireEvent.change(select, { target: { value: BRIEF.id } });
  fireEvent.change(screen.getByPlaceholderText("What should exist when this is done"), {
    target: { value: "Customers can book a cleaning online" },
  });
  fireEvent.change(screen.getByPlaceholderText("How a stranger can tell this is done"), {
    target: { value: "A stranger opens /book and sees a confirmation after booking" },
  });
}

function callTo(fn: ReturnType<typeof stubFetch>, path: string): RequestInit {
  const call = fn.mock.calls.find(([input]) => String(input) === path);
  expect(call, `expected a fetch to ${path}`).toBeTruthy();
  return (call as [RequestInfo | URL, RequestInit])[1];
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

describe("GoalTicketForm", () => {
  it("LOADED + WRITE: analyze shows drafts, then Write to Linear shows the filed ticket link", async () => {
    mockedProxy.mockResolvedValue({ projects: [BRIEF] });
    const fetchMock = stubFetch((url) => {
      if (url === "/api/pi-ceo/api/goal-ticket/analyze") {
        return jsonResponse({ summary: "One ticket", tickets: [DRAFT], project_title: BRIEF.title });
      }
      if (url === "/api/pi-ceo/api/goal-ticket") {
        return jsonResponse({
          tickets: [
            {
              identifier: "RA-9001",
              url: "https://linear.app/x/issue/RA-9001",
              title: DRAFT.title,
              state: "Backlog",
              labels: [],
            },
          ],
        });
      }
      return jsonResponse({}, 404);
    });
    render(<GoalTicketForm />);
    await fillForm();

    fireEvent.click(screen.getByRole("button", { name: "Analyze goal" }));
    expect(await screen.findByDisplayValue(DRAFT.title)).toBeTruthy();
    expect(screen.getByText("Draft Linear tickets")).toBeTruthy();

    const analyzeInit = callTo(fetchMock, "/api/pi-ceo/api/goal-ticket/analyze");
    expect(analyzeInit.method).toBe("POST");
    expect(JSON.parse(String(analyzeInit.body))).toMatchObject({
      goal: "Customers can book a cleaning online",
      project_id: BRIEF.id,
    });
    expect(fetchMock.mock.calls.some(([u]) => String(u) === "/api/pi-ceo/api/goal-ticket")).toBe(false);

    fireEvent.click(screen.getByRole("button", { name: "Write 1 to Linear" }));
    fireEvent.click(await screen.findByRole("button", { name: "Write to Linear" }));

    const link = await screen.findByRole("link", { name: "RA-9001" });
    expect(link.getAttribute("href")).toBe("https://linear.app/x/issue/RA-9001");
    const fileInit = callTo(fetchMock, "/api/pi-ceo/api/goal-ticket");
    expect(fileInit.method).toBe("POST");
    const body = JSON.parse(String(fileInit.body)) as { approved: boolean; tickets: Array<{ title: string }> };
    expect(body.approved).toBe(true);
    expect(body.tickets.map((t) => t.title)).toEqual([DRAFT.title]);
    expect(screen.queryByDisplayValue(DRAFT.title)).toBeNull();
  });

  it("EMPTY: no briefs shows the empty-brief note and keeps Analyze disabled", async () => {
    mockedProxy.mockResolvedValue({ projects: [] });
    const fetchMock = stubFetch(() => jsonResponse({}, 404));
    render(<GoalTicketForm />);

    expect(await screen.findByText(BRIEFS_EMPTY_NOTE)).toBeTruthy();
    expect(screen.getByText("Select a brief, or press Create brief.")).toBeTruthy();
    const analyze = screen.getByRole("button", { name: "Analyze goal" }) as HTMLButtonElement;
    expect(analyze.disabled).toBe(true);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("EMPTY: analyze returning zero tickets says so instead of showing an empty draft list", async () => {
    mockedProxy.mockResolvedValue({ projects: [BRIEF] });
    stubFetch(() => jsonResponse({ summary: "", tickets: [] }));
    render(<GoalTicketForm />);
    await fillForm();

    fireEvent.click(screen.getByRole("button", { name: "Analyze goal" }));
    expect(await screen.findByText("Analysis returned no tickets.")).toBeTruthy();
    expect(screen.queryByText("Draft Linear tickets")).toBeNull();
    expect(screen.getByRole("button", { name: "Analyze goal" })).toBeTruthy();
  });

  it("ERROR: analyze 500 shows the backend error and the button leaves Analyzing…", async () => {
    mockedProxy.mockResolvedValue({ projects: [BRIEF] });
    stubFetch(() => jsonResponse({ detail: { error: "planner crashed" } }, 500));
    render(<GoalTicketForm />);
    await fillForm();

    fireEvent.click(screen.getByRole("button", { name: "Analyze goal" }));
    expect(await screen.findByText("planner crashed")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Analyzing…" })).toBeNull();
    expect(screen.queryByText("Draft Linear tickets")).toBeNull();
  });

  it("ERROR: analyze fetch rejecting shows the unreachable message", async () => {
    mockedProxy.mockResolvedValue({ projects: [BRIEF] });
    stubFetch(() => {
      throw new Error("network down");
    });
    render(<GoalTicketForm />);
    await fillForm();

    fireEvent.click(screen.getByRole("button", { name: "Analyze goal" }));
    expect(
      await screen.findByText("Network error — Pi CEO backend unreachable. Linear was not written."),
    ).toBeTruthy();
    await waitFor(() => expect(screen.getByRole("button", { name: "Analyze goal" })).toBeTruthy());
  });
});
