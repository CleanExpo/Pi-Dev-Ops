import React from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
vi.mock("@/components/Terminal", () => ({ default: () => <div>Session logs</div> }));
vi.mock("@/components/control/ProjectSelector", () => ({ useActiveProject: () => ({ project_id: "project", repo: "org/project" }) }));
import BuildForm from "@/components/control/BuildForm";

class MockEventSource {
  static instances: MockEventSource[] = [];
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  close = vi.fn(); addEventListener = vi.fn();
  constructor(public url: string) { MockEventSource.instances.push(this); }
}
const reply = (data: unknown, ok = true) => ({ ok, headers: new Headers(), json: async () => data });
let fetcher: ReturnType<typeof vi.fn>;
beforeEach(() => {
  MockEventSource.instances = [];
  vi.stubGlobal("EventSource", MockEventSource);
  fetcher = vi.fn(async (url: string) => url.endsWith("/build") ? reply({ session_id: "build-123", status: "created" }) : url.endsWith("/kill") ? reply({ ok: true }) : reply([{ id: "build-123", status: "building" }]));
  vi.stubGlobal("fetch", fetcher);
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); vi.useRealTimers(); });
async function launch() {
  render(<BuildForm />);
  fireEvent.change(screen.getByLabelText("Build brief"), { target: { value: "Repair the billing report" } });
  fireEvent.click(screen.getByRole("button", { name: /run$/i }));
  await act(async () => {});
}
describe("Mission Control build launch", () => {
  it("shows the selected repository and submits the brief to the existing build API", async () => {
    await launch();
    expect(screen.getByLabelText("Repository URL")).toHaveValue("https://github.com/org/project");
    expect(fetcher).toHaveBeenCalledWith("/api/pi-ceo/api/build", expect.objectContaining({ method: "POST", body: JSON.stringify({ repo_url: "https://github.com/org/project", brief: "Repair the billing report" }) }));
    expect(MockEventSource.instances[0]?.url).toContain("/api/pi-ceo/api/sessions/build-123/logs");
    expect(MockEventSource.instances.every(s => !s.url.includes("/api/analyze"))).toBe(true);
  });
  it("never relaunches a build after its log stream disconnects", async () => {
    await launch();
    act(() => MockEventSource.instances[0]?.onerror?.());
    expect(fetcher.mock.calls.filter(([url]) => url.endsWith("/build"))).toHaveLength(1);
  });
  it("requires a valid receipt before claiming the build started", async () => {
    fetcher.mockResolvedValue(reply({}));
    await launch();
    expect(await screen.findByText(/receipt|session.*missing|invalid.*session/i)).toBeInTheDocument();
    expect(MockEventSource.instances).toHaveLength(0);
  });
  it("surfaces a policy-blocked backend session", async () => {
    fetcher.mockImplementation(async (url: string) => url.endsWith("/build") ? reply({ session_id: "build-123", status: "created" }) : reply([{ id: "build-123", status: "blocked" }]));
    await launch();
    expect(await screen.findByText(/session.*blocked/i)).toBeInTheDocument();
  });
  it("keeps a proxy fallback unknown and does not relaunch", async () => {
    fetcher.mockImplementation(async (url: string) => url.endsWith("/build")
      ? reply({ session_id: "build-123", status: "created" })
      : { ok: true, headers: new Headers({ "X-Upstream-Status": "502" }), json: async () => [] });
    await launch();
    expect(await screen.findByText(/Session status unavailable/)).toBeInTheDocument();
    expect(fetcher.mock.calls.filter(([url]) => url.endsWith("/build"))).toHaveLength(1);
  });
  it("Stop requests cancellation of the backend session", async () => {
    await launch();
    fireEvent.click(screen.getByRole("button", { name: /stop$/i }));
    await waitFor(() => expect(fetcher).toHaveBeenCalledWith("/api/pi-ceo/api/sessions/build-123/kill", expect.objectContaining({ method: "POST" })));
  });
});
