import { describe, expect, it } from "vitest";
import { errorMessage, failedTitle, filedTickets } from "@/lib/control/goalErrors";

const TICKET = {
  identifier: "RA-8001",
  url: "https://linear.app/unite-group/issue/RA-8001",
  title: "Saved looks persist",
  state: "Backlog",
  labels: ["pi-dev:source"],
};

describe("Goal error parsers", () => {
  it("reads filed tickets from a FastAPI detail wrapper", () => {
    expect(filedTickets({ detail: { filed: [TICKET] } })).toEqual([TICKET]);
    expect(filedTickets({ filed: [TICKET] })).toEqual([TICKET]);
    expect(filedTickets({ tickets: [TICKET] })).toEqual([TICKET]);
  });

  it("drops tickets that have no identifier or url", () => {
    expect(filedTickets({
      filed: [{ identifier: "", url: "", title: "x", state: "", labels: [] }],
    })).toEqual([]);
  });

  it("names the ticket that failed after a partial write", () => {
    const body = { hint: "Linear write failed.", detail: { failed_title: "Child B" } };
    expect(failedTitle(body)).toBe("Child B");
    expect(errorMessage(body, 502)).toBe('Linear write failed. Stopped at “Child B”.');
  });
});
