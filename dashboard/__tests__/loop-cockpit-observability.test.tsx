// Loop Cockpit — the "Needs me" list against the real observability payload.
//
// Defect F: `observability.actions` was typed `string[]` and each entry pushed
// straight into a rendered `{n.text}`. The backend sends OBJECTS
// (app/server/routes/mission_control.py builds {component, status, owner,
// severity, next_action, evidence_required, detail}), so React receives an
// object as a child and throws. The list that exists to tell the founder what
// needs him is the thing that breaks.
//
// Written to FAIL against the pre-fix page.

import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, cleanup } from "@testing-library/react";
import LoopCockpit from "@/app/(main)/loop/page";

/** One action, exactly as mission_control.py emits it. */
const ACTION = {
  component: "supabase",
  status: "red",
  ok: false,
  observed: true,
  owner: "Data/CRM operator",
  severity: "high",
  next_action: "Restore the Supabase logging probe",
  evidence_required: ["a successful write followed by a read-back"],
  detail: null,
};

function mockBackend() {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const body = url.includes("/api/mission-control/live")
        ? {
            ts: new Date().toISOString(),
            throughput: { hourly: Array.from({ length: 24 }, () => 0) },
            active_sessions: [],
            recent_completions: [],
            queue: { urgent: 0, high: 0, next_issue_id: null },
            observability: {
              fully_observed: false,
              degraded_components: ["supabase"],
              actions: [ACTION],
            },
          }
        : null;
      // Every other endpoint returns 404 so the page's fail-soft path is exercised.
      return body
        ? new Response(JSON.stringify(body), { status: 200 })
        : new Response("nope", { status: 404 });
    }),
  );
}

describe("Loop Cockpit — observability actions", () => {
  beforeEach(mockBackend);
  afterEach(() => {
    vi.unstubAllGlobals();
    cleanup();
  });

  it("renders each action's next_action instead of throwing on an object child", async () => {
    render(<LoopCockpit />);
    expect(await screen.findByText(/Restore the Supabase logging probe/)).toBeTruthy();
  });

  it("names the component and its owner, so the item is actionable", async () => {
    render(<LoopCockpit />);
    const row = await screen.findByText(/Restore the Supabase logging probe/);
    expect(row.textContent).toContain("supabase");
    expect(row.textContent).toContain("Data/CRM operator");
  });
});
