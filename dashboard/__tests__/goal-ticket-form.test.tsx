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

// UNI-3306 step 6 — submit then check (grill 14 Q5/Q6).
describe("GoalTicketForm with async analysis (202 + job)", () => {
  const JOB_ID = "0b6c2f8e-6f1e-4d55-9a57-2f3f6b7f1a10";
  const STATUS_URL = `/api/pi-ceo/api/goal-ticket/analyze/${JOB_ID}`;
  const job = (status: string, extra: Record<string, unknown> = {}) => ({
    id: JOB_ID,
    status,
    attempt: 1,
    retry_count: 0,
    last_progress_at: "2026-11-11T00:00:01+00:00",
    ...extra,
  });
  const FINISHED = job("finished", {
    result: { summary: "One ticket", tickets: [DRAFT], project_title: BRIEF.title, filed: false, fallback: false },
  });

  function quiet(upstream: number): Response {
    return new Response(JSON.stringify({ error: "Pi CEO server unreachable" }), {
      status: 200,
      headers: { "Content-Type": "application/json", "X-Upstream-Status": String(upstream) },
    });
  }

  function statusCalls(fn: ReturnType<typeof stubFetch>): number {
    return fn.mock.calls.filter(([input]) => String(input) === STATUS_URL).length;
  }

  // Fake-clock time of each status check, to measure the gaps between them.
  let checkTimes: number[] = [];

  async function startJob(statuses: Array<() => Response>, submitted: Record<string, unknown> = job("queued")) {
    mockedProxy.mockResolvedValue({ projects: [BRIEF] });
    let i = 0;
    checkTimes = [];
    const fetchMock = stubFetch((url) => {
      if (url === "/api/pi-ceo/api/goal-ticket/analyze") return jsonResponse(submitted, 202);
      if (url === STATUS_URL) {
        checkTimes.push(Date.now());
        return statuses[Math.min(i++, statuses.length - 1)]();
      }
      return jsonResponse({}, 404);
    });
    render(<GoalTicketForm />);
    await fillForm();
    vi.useFakeTimers({ shouldAdvanceTime: true });
    fireEvent.click(screen.getByRole("button", { name: "Analyze goal" }));
    await vi.advanceTimersByTimeAsync(0);
    return fetchMock;
  }

  afterEach(() => {
    vi.useRealTimers();
    Object.defineProperty(document, "hidden", { configurable: true, get: () => false });
  });

  it("checks the job every 3 s and shows the drafts when it finishes; the submit carries a one-time key", async () => {
    const fetchMock = await startJob([() => jsonResponse(job("running")), () => jsonResponse(FINISHED)]);
    const body = JSON.parse(String(callTo(fetchMock, "/api/pi-ceo/api/goal-ticket/analyze").body)) as {
      idempotency_key?: string;
    };
    expect(body.idempotency_key && body.idempotency_key.length >= 8).toBe(true);
    await waitFor(() => expect(screen.getByRole("status").textContent).toMatch(/^Queued, waiting for a server/));
    expect(statusCalls(fetchMock)).toBe(0);

    await vi.advanceTimersByTimeAsync(3_000);
    expect(statusCalls(fetchMock)).toBe(1);
    await waitFor(() => expect(screen.getByRole("status").textContent).toMatch(/^Running · \d+ s elapsed · last progress \d+ s ago/));

    await vi.advanceTimersByTimeAsync(3_000);
    expect(await screen.findByDisplayValue(DRAFT.title)).toBeTruthy();
    await vi.advanceTimersByTimeAsync(30_000);
    expect(statusCalls(fetchMock)).toBe(2);
  });

  it("a failed check shows that the server cannot be reached, never the old status, and backs off", async () => {
    const fetchMock = await startJob([
      () => jsonResponse(job("running")),
      () => quiet(502),
      () => quiet(502),
      () => jsonResponse(job("failed", { failure_reason: "the model call ran past its time budget" })),
    ]);
    await vi.advanceTimersByTimeAsync(3_000);
    await waitFor(() => expect(screen.getByRole("status").textContent).toMatch(/^Running/));
    await vi.advanceTimersByTimeAsync(3_000);
    await waitFor(() => expect(screen.getByRole("status").textContent).toBe("Can't reach the server, retrying"));
    await vi.advanceTimersByTimeAsync(3_000);
    await waitFor(() => expect(statusCalls(fetchMock)).toBe(3));
    expect(screen.getByRole("status").textContent).toBe("Can't reach the server, retrying");
    await vi.advanceTimersByTimeAsync(6_000);
    await waitFor(() => expect(statusCalls(fetchMock)).toBe(4));
    // Gaps: 3 s after a good check, then 3 s after one failed check, 6 s after two.
    const gaps = checkTimes.slice(1).map((t, k) => t - checkTimes[k]);
    expect(gaps.map((g) => Math.round(g / 1000))).toEqual([3, 3, 6]);
    expect(
      await screen.findByText(
        "Analysis failed: the model call ran past its time budget. Linear was not written.",
      ),
    ).toBeTruthy();
  });

  it("a duplicate submit that returns a job already stalled for 3 minutes shows it as stalled at once (review r1 P1)", async () => {
    const stale = job("running", { elapsed_s: 180, last_progress_age_s: 180 });
    await startJob([() => jsonResponse({ ...stale, elapsed_s: 240, last_progress_age_s: 183 })], stale);
    await waitFor(() =>
      expect(screen.getByRole("status").textContent).toMatch(/^Stalled, recovering · 180 s elapsed · last progress 18\d s ago/),
    );
    await vi.advanceTimersByTimeAsync(3_000);
    await waitFor(() => expect(screen.getByRole("status").textContent).toMatch(/^Stalled, recovering · 240 s elapsed · last progress 18\d s ago/));
  });

  it("pauses checking while the tab is hidden and checks at once when it is shown", async () => {
    let hidden = false;
    Object.defineProperty(document, "hidden", { configurable: true, get: () => hidden });
    const fetchMock = await startJob([() => jsonResponse(job("running"))]);
    hidden = true;
    document.dispatchEvent(new Event("visibilitychange"));
    await vi.advanceTimersByTimeAsync(60_000);
    expect(statusCalls(fetchMock)).toBe(0);
    hidden = false;
    document.dispatchEvent(new Event("visibilitychange"));
    await vi.advanceTimersByTimeAsync(0);
    expect(statusCalls(fetchMock)).toBe(1);
  });

  it("stops and says so when the job can no longer be read (4xx)", async () => {
    const fetchMock = await startJob([() => quiet(404)]);
    await vi.advanceTimersByTimeAsync(3_000);
    expect(
      await screen.findByText("The analysis job can no longer be read (HTTP 404). Linear was not written. Analyze again."),
    ).toBeTruthy();
    await vi.advanceTimersByTimeAsync(60_000);
    expect(statusCalls(fetchMock)).toBe(1);
  });
});
