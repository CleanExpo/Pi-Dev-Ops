import { describe, expect, it } from "vitest";
import {
  MIN_BRIEF,
  draftReady,
  meetsMin,
  readyToAnalyze,
  readyToCreate,
  readyToFile,
  remainingHint,
  ticketsToFile,
} from "@/lib/control/goalBrief";

describe("Goal brief rules", () => {
  it("matches the server eight-character minimum", () => {
    expect(MIN_BRIEF).toBe(8);
    expect(meetsMin("1234567")).toBe(false);
    expect(meetsMin("12345678")).toBe(true);
    expect(meetsMin("  12345678")).toBe(true);
  });

  it("blocks Analyze until goal, acceptance, and a project are ready", () => {
    expect(readyToAnalyze("short", "acceptance long enough", "p1")).toBe(false);
    expect(readyToAnalyze("goal long enough", "short", "p1")).toBe(false);
    expect(readyToAnalyze("goal long enough", "acceptance long enough", "")).toBe(false);
    expect(readyToAnalyze("goal long enough", "acceptance long enough", "p1")).toBe(true);
  });

  it("blocks Save until title, description, and audience are ready", () => {
    expect(readyToCreate({ title: "short", description: "description long", audience: "audience long" })).toBe(false);
    expect(readyToCreate({
      title: "title long",
      description: "description long",
      audience: "audience long",
    })).toBe(true);
  });

  it("tells the operator how many characters remain", () => {
    expect(remainingHint("", "Goal")).toBe("Goal");
    expect(remainingHint("abcd", "Goal")).toBe("Goal · 4 more");
    expect(remainingHint("abcdefgh", "Goal")).toBe("Goal");
  });

  it("blocks File until every selected draft meets the server minimum", () => {
    const short = {
      title: "Saved looks persist after refresh",
      goal: "short",
      acceptance: "acceptance long enough",
      selected: true,
    };
    const ready = {
      title: "Saved looks persist after refresh",
      goal: "goal long enough",
      acceptance: "acceptance long enough",
      selected: true,
    };
    expect(draftReady(short)).toBe(false);
    expect(readyToFile([short])).toBe(false);
    expect(readyToFile([ready])).toBe(true);
  });

  it("skips selected drafts that already have a Linear id", () => {
    const tickets = [
      { title: "First ticket lands", selected: true, landed_identifier: "RA-8001" },
      { title: "Second ticket fails", selected: true, landed_identifier: "" },
    ];
    const left = ticketsToFile(tickets, [
      { identifier: "RA-8001", title: "First ticket lands" },
    ]);
    expect(left.map((ticket) => ticket.title)).toEqual(["Second ticket fails"]);
  });
});
