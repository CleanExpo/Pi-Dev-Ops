import { describe, it, expect } from "vitest";
import { composeMeetingMarkdown, type MeetingState } from "../markdown-composer";

const baseState: MeetingState = {
  meetingId: "abc-123",
  title: "Acme Q2 Pricing",
  startedAt: "2026-05-17T14:32:00+10:00",
  endedAt: "2026-05-17T15:31:42+10:00",
  brand: "unite-group",
  transcript: [
    { timestamp: "14:28", speaker: "A", text: "we've got the new pricing tiers..." },
    { timestamp: "14:30", speaker: "B", text: "what about the inventory sync?" },
  ],
  topics: ["Q2 pricing tiers", "Inventory sync"],
  actions: [
    { title: "Send pricing proposal", description: "by Friday", owner: "Phill", priority: 2 },
  ],
};

describe("composeMeetingMarkdown", () => {
  it("starts with frontmatter delimiter", () => {
    const md = composeMeetingMarkdown(baseState);
    expect(md.startsWith("---\n")).toBe(true);
  });

  it("includes meeting_id in frontmatter", () => {
    const md = composeMeetingMarkdown(baseState);
    expect(md).toContain("meeting_id: abc-123");
  });

  it("includes duration_human", () => {
    const md = composeMeetingMarkdown(baseState);
    expect(md).toContain("duration_human: 59m42s");
  });

  it("renders title as H1", () => {
    const md = composeMeetingMarkdown(baseState);
    expect(md).toContain("# Acme Q2 Pricing — 2026-05-17");
  });

  it("renders Topics section", () => {
    const md = composeMeetingMarkdown(baseState);
    expect(md).toContain("## Topics Discussed");
    expect(md).toContain("- Q2 pricing tiers");
    expect(md).toContain("- Inventory sync");
  });

  it("renders Action Items section with owner", () => {
    const md = composeMeetingMarkdown(baseState);
    expect(md).toContain("## Action Items");
    expect(md).toContain("- [ ] Send pricing proposal — by Friday — Phill");
  });

  it("renders Transcript section with timestamps", () => {
    const md = composeMeetingMarkdown(baseState);
    expect(md).toContain("## Transcript");
    expect(md).toContain("[14:28] Speaker A: we've got the new pricing tiers...");
  });

  it("handles empty topics + actions gracefully", () => {
    const md = composeMeetingMarkdown({ ...baseState, topics: [], actions: [] });
    expect(md).toContain("## Topics Discussed");
    expect(md).toContain("_(none)_");
  });

  it("uses 'Meeting' title fallback when title is empty", () => {
    const md = composeMeetingMarkdown({ ...baseState, title: "" });
    expect(md).toContain("# Meeting — 2026-05-17");
  });
});
