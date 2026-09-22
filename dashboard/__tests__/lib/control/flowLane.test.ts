import { describe, expect, it } from "vitest";
import { agingTone, classifyLane, flowBoardColumn } from "@/lib/control/flowLane";
import { assembleFlowBoard, isSafePullUrl, parseFlowBoardPayload, rowFromPull } from "@/lib/control/flowBoard";

describe("UNI-2639 flow lanes", () => {
  it("gives FOUNDER to lanes.yml and never lets a flow label drop an engineer path", () => {
    expect(classifyLane([".github/lanes.yml"], [])).toBe("founder");
    expect(classifyLane(["app/server/auth.py"], ["lane:flow"])).toBe("engineer");
    expect(classifyLane(["dashboard/components/control/GoalTicketForm.tsx"], [])).toBe("flow");
    expect(classifyLane(["readme.md"], ["lane:founder"])).toBe("founder");
    expect(classifyLane([], [])).toBe("unclassified");
    expect(classifyLane(["app/server/auth.py"], ["lane:flow"])).toBe("engineer");
    expect(classifyLane([], [], { founderPaths: [], founderLabels: [], engineerPaths: [], engineerLabels: [] }))
      .toBe("unclassified");
    expect(classifyLane(["../app/server/auth.py"], [])).toBe("unclassified");
    expect(classifyLane(["/etc/passwd"], ["lane:flow<script>"])).toBe("unclassified");
  });

  it("ages red from day 5 and kill-or-lane from day 7", () => {
    expect(agingTone(4)).toBe("watch");
    expect(agingTone(5)).toBe("red");
    expect(agingTone(7)).toBe("kill");
  });

  it("puts founder without founder-go in Awaiting Phill", () => {
    expect(flowBoardColumn({
      lane: "founder",
      mergedToday: false,
      auditGreen: false,
      founderGo: false,
      ageDays: 1,
    })).toBe("phill");
    expect(flowBoardColumn({
      lane: "flow",
      mergedToday: false,
      auditGreen: false,
      founderGo: false,
      ageDays: 6,
    })).toBe("aging");
  });

  it("assembles four columns and flags a long Phill queue as a system fail", () => {
    const now = Date.parse("2026-09-22T00:00:00Z");
    const rows = [1, 2, 3].map((n) => rowFromPull({
      id: `PR-${n}`,
      title: `Founder item ${n}`,
      url: "https://example.invalid",
      paths: [".github/lanes.yml"],
      labels: [],
      createdAt: "2026-09-21T00:00:00Z",
      mergedToday: false,
      auditGreen: false,
      nowMs: now,
    }));
    const board = assembleFlowBoard(rows, null);
    expect(board.columns.phill).toHaveLength(3);
    expect(board.awaiting_phill_long).toBe(true);
    expect(assembleFlowBoard([], "GitHub unavailable").ok).toBe(false);
    expect(isSafePullUrl("https://evil.example/phish")).toBe(false);
    expect(isSafePullUrl("https://github.com/CleanExpo/Pi-Dev-Ops/pull/1")).toBe(true);
    expect(isSafePullUrl("https://user:pass@github.com/CleanExpo/Pi-Dev-Ops/pull/1")).toBe(false);
    expect(isSafePullUrl("https://github.com/CleanExpo/../evil/pull/1")).toBe(false);
    expect(parseFlowBoardPayload({ ok: true })).toBeNull();
    expect(parseFlowBoardPayload({
      ok: true,
      checked_at: "2026-09-22T00:00:00Z",
      error: null,
      columns: {
        shipped: [{ id: "PR-1", title: "<x>", url: "https://evil.example", lane: "unclassified", column: "shipped", ageDays: 0, tone: "ok", receipts: "x" }],
        audit: [],
        phill: [],
        aging: [],
      },
    })?.columns.shipped).toHaveLength(0);
    expect(agingTone(Number.NaN)).toBe("kill");
    expect(rowFromPull({
      id: "PR-9",
      title: "Thin",
      url: "https://evil.example",
      paths: [],
      labels: [],
      createdAt: "not-a-date",
      mergedToday: true,
      auditGreen: true,
      nowMs: Date.parse("2026-09-22T00:00:00Z"),
    }).lane).toBe("unclassified");
  });
});
