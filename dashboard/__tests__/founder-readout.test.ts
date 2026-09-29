import { expect, it } from "vitest";
import { founderReadout } from "@/lib/control/founder-readout";

const NOW = Date.parse("2026-09-29T13:00:00Z");

it("answers from fresh observations while keeping shipment unverified", () => {
  const answers = founderReadout({
    ts: "2026-09-29T12:59:30Z",
    active_sessions: [{ id: "run-1", repo: "RestoreAssist" }],
    queue: { next_issue_id: "RA-42", next_issue_title: "Repair dispatch" },
    observability: { actions: [{ component: "supabase", observed: true, ok: false, status: "red", next_action: "Restore the read." }] },
    idea_pipeline: { awaiting: 2 },
    recent_completions: [{ id: "run-2", pr_url: "https://github.com/CleanExpo/Pi-Dev-Ops/pull/1" }],
  }, NOW);
  expect(answers.map((row) => row.question)).toEqual([
    "Where are we?", "What matters now?", "What is hard?", "What needs Phill's decision?", "What was truly shipped?",
  ]);
  expect(answers[0].answer).toContain("1 active Pi build session");
  expect(answers[1].answer).toContain("RA-42");
  expect(answers[2].answer).toContain("supabase: red");
  expect(answers[3].answer).toContain("2 ideas await");
  expect(answers[4].answer).toMatch(/^Unknown/);
  expect(answers.every((row) => row.href && row.source)).toBe(true);
});

it("marks unavailable, stale and incomplete signals unknown", () => {
  for (const live of [null, { ts: "2026-09-29T12:57:00Z", active_sessions: [{ id: "old" }] }, { ts: "2026-09-29T12:59:30Z", active_sessions: [] }]) {
    const answers = founderReadout(live, NOW);
    if (!live || live.ts !== "2026-09-29T12:59:30Z") {
      expect(answers.every((row) => row.answer.startsWith("Unknown"))).toBe(true);
    } else {
      expect(answers[0].answer).toContain("0 active Pi build sessions observed");
      expect(answers.slice(1).every((row) => row.answer.startsWith("Unknown"))).toBe(true);
    }
  }
});
