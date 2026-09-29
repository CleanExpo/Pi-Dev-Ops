import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup, fireEvent, waitFor } from "@testing-library/react";
import IdeaPipelinePanel from "@/components/control/IdeaPipelinePanel";
import { canAuthorizeGo, disposeFeedback } from "@/lib/control/idea-pipeline";

function packet(overrides: Record<string, unknown> = {}) {
  return {
    idea_id: "idea-abc123def456",
    text: "Teach shop owners to film short self-paced lessons.",
    source: "phill",
    status: "awaiting_dispose",
    verdict: null,
    recommended_verdict: "PROMOTE",
    go_at: null,
    executed: false,
    north_star_fit: { label: "strong", score: 0.75, rationale: "Matched teach, owners." },
    effort_vs_impact: { effort: "medium", impact: "high", rationale: "Fit is high." },
    directive: { label: "Self-paced learning, not a live class", rationale: "Serves learning." },
    displacement: { would_displace: "This week's Board slot", rationale: "No rival." },
    judge: { score: 78, decision: "APPROVE_EXPERIMENT" },
    spm: {
      problem: "Teach shop owners",
      desired_outcome: "One-word dispose",
      out_of_scope: "Auto-starting the machine spec pipeline or any paid fallback.",
    },
    ...overrides,
  };
}

function snapshot(overrides: Record<string, unknown> = {}) {
  return {
    snapshot: {
      intake: "IDEAS.md",
      north_star: "empower small business owners to grow, self-paced, all learning styles",
      awaiting: 1,
      packet: packet(),
      verdicts: ["BACKLOG", "KILL", "PARK", "PROMOTE"],
      go_required: true,
      executed: false,
      ...overrides,
    },
  };
}

function mockFetch(handler: (url: string, init?: RequestInit) => unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      const payload = handler(url, init);
      return new Response(JSON.stringify(payload), { status: 200 });
    }),
  );
}

describe("Idea pipeline Board packet", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    cleanup();
  });

  it("LOADED: renders a waiting packet and the four dispose words", async () => {
    mockFetch(() => snapshot());
    render(<IdeaPipelinePanel />);
    fireEvent.click(await screen.findByText(/Board packet · awaiting_dispose/));
    expect(await screen.findByText(/Teach shop owners/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "PROMOTE" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "BACKLOG" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "PARK" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "KILL" })).toBeTruthy();
    expect((screen.getByRole("button", { name: "GO" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("EMPTY: empty intake shows the direct idea composer", async () => {
    mockFetch(() => snapshot({ awaiting: 0, packet: null }));
    render(<IdeaPipelinePanel />);
    expect(await screen.findByText("0 waiting for a decision")).toBeTruthy();
    expect(screen.getByRole("textbox", { name: "New idea" })).toBeTruthy();
  });

  it("ERROR: a failed read says the pipeline could not be read, not that nothing is waiting", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(JSON.stringify({ error: "down" }), { status: 502 })));
    render(<IdeaPipelinePanel />);
    expect(await screen.findByText("Mission Control could not read the idea pipeline.")).toBeTruthy();
    expect(screen.queryByText(/waiting for a decision/)).toBeNull();
  });

  it("PROMOTE then GO updates the screen and does not claim a start", async () => {
    let current = snapshot();
    mockFetch((url, init) => {
      if (url.includes("/dispose") && init?.method === "POST") {
        current = snapshot({
          packet: packet({ status: "disposed", verdict: "PROMOTE" }),
          awaiting: 0,
        });
        return { packet: current.snapshot.packet, executed: false };
      }
      if (url.includes("/go") && init?.method === "POST") {
        current = snapshot({
          packet: packet({
            status: "disposed",
            verdict: "PROMOTE",
            go_at: "2026-09-13T00:00:00Z",
          }),
          awaiting: 0,
        });
        return { packet: current.snapshot.packet, executed: false, go: true };
      }
      return current;
    });
    render(<IdeaPipelinePanel />);
    fireEvent.click(await screen.findByText(/Board packet · awaiting_dispose/));
    await screen.findByText(/Teach shop owners/);
    fireEvent.click(screen.getByRole("button", { name: "PROMOTE" }));
    expect(await screen.findByText(/Nothing has started/)).toBeTruthy();
    const go = screen.getByRole("button", { name: "GO" }) as HTMLButtonElement;
    await waitFor(() => expect(go.disabled).toBe(false));
    fireEvent.click(go);
    expect(await screen.findByText(/GO is on the record/)).toBeTruthy();
    expect(screen.queryByText(/build started/i)).toBeNull();
  });

  it("submits an idea through the existing intake and clears the composer", async () => {
    let current = snapshot({ awaiting: 0, packet: null });
    const requests: { url: string; init?: RequestInit }[] = [];
    mockFetch((url, init) => {
      if (url.endsWith("/intake") && init?.method === "POST") {
        requests.push({ url, init });
        current = snapshot();
        return { packet: current.snapshot.packet };
      }
      return current;
    });
    render(<IdeaPipelinePanel />);
    fireEvent.change(screen.getByRole("textbox", { name: "New idea" }), { target: { value: "Add a project evidence view" } });
    fireEvent.click(screen.getByRole("button", { name: /Drop idea/ }));
    await waitFor(() => expect(requests).toHaveLength(1));
    expect(requests[0].url).toBe("/api/pi-ceo/api/idea-pipeline/intake");
    expect(JSON.parse(String(requests[0].init?.body))).toEqual({ text: "Add a project evidence view", source: "phill" });
    expect(await screen.findByText("Idea captured. Board packet is ready.")).toBeTruthy();
    expect((screen.getByRole("textbox", { name: "New idea" }) as HTMLTextAreaElement).value).toBe("");
  });
});

describe("idea-pipeline helpers", () => {
  it("checks 1,000 varied Board packets before enabling GO", () => {
    const verdicts = ["PROMOTE", "BACKLOG", "PARK", "KILL", null];
    for (let index = 0; index < 1000; index++) {
      const verdict = verdicts[index % verdicts.length];
      const go_at = index % 2 ? null : `2026-09-29T00:${String(index % 60).padStart(2, "0")}:00Z`;
      const candidate = packet({ idea_id: `idea-${index}`, verdict, go_at });
      expect(canAuthorizeGo(candidate)).toBe(verdict === "PROMOTE" && !go_at);
    }
  });

  it("GO is only legal after PROMOTE", () => {
    expect(canAuthorizeGo(packet({ verdict: "PROMOTE" }))).toBe(true);
    expect(canAuthorizeGo(packet({ verdict: "KILL" }))).toBe(false);
    expect(canAuthorizeGo(packet({ verdict: "PROMOTE", go_at: "now" }))).toBe(false);
    expect(disposeFeedback("PROMOTE")).toMatch(/Nothing has started/);
    expect(disposeFeedback("KILL")).toMatch(/KILL/);
  });
});
