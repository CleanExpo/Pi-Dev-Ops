/**
 * BuildForm — loaded, empty and error states (AAA check 7, MC-07).
 * The form reads nothing until a build is requested; its data is the session
 * the backend returns. Behaviour around relaunch and cancellation is pinned
 * separately in build-launch.test.tsx.
 */
import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("@/components/Terminal", () => ({ default: () => <div>Session logs</div> }));
vi.mock("@/components/control/ProjectSelector", () => ({
  useActiveProject: () => ({ project_id: "project", repo: "org/project" }),
}));

import BuildForm from "@/components/control/BuildForm";

class MockEventSource {
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  close = vi.fn();
  addEventListener = vi.fn();
  constructor(public url: string) {}
}

const reply = (data: unknown, ok = true) => ({ ok, status: ok ? 200 : 500, headers: new Headers(), json: async () => data });

beforeEach(() => {
  vi.stubGlobal("EventSource", MockEventSource);
});
afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

async function launch() {
  render(<BuildForm />);
  fireEvent.change(screen.getByLabelText("Build brief"), { target: { value: "Repair the billing report" } });
  fireEvent.click(screen.getByRole("button", { name: /run$/i }));
  await act(async () => {});
}

describe("BuildForm", () => {
  it("LOADED: a started build shows its backend session and live status", async () => {
    vi.stubGlobal("fetch", vi.fn(async (url: string) => url.endsWith("/build")
      ? reply({ session_id: "build-123", status: "created" })
      : reply([{ id: "build-123", status: "building" }])));
    await launch();
    expect(await screen.findByText("session build-123")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Builds and evidence/ })).toBeTruthy();
  });

  it("EMPTY: before any build nothing claims to be running", () => {
    vi.stubGlobal("fetch", vi.fn());
    render(<BuildForm />);
    expect(screen.getByLabelText("Build brief")).toBeTruthy();
    expect(screen.queryByText(/^session /)).toBeNull();
    expect(screen.queryByRole("link", { name: /Builds and evidence/ })).toBeNull();
    expect(fetch).not.toHaveBeenCalled();
  });

  it("ERROR: a refused build request says the backend is unavailable and starts nothing", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply({ error: "boom" }, false)));
    await launch();
    expect(await screen.findByText(/Backend request unavailable.*launch was not confirmed/)).toBeTruthy();
    expect(screen.getByText("Launch unconfirmed")).toBeTruthy();
    expect(screen.queryByText(/^session /)).toBeNull();
  });

  it("ERROR: a receipt without a session id is not reported as a started build", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => reply({ status: "created" })));
    await launch();
    expect(await screen.findByText(/Invalid build session receipt/)).toBeTruthy();
    expect(screen.queryByRole("link", { name: /Builds and evidence/ })).toBeNull();
  });
});
