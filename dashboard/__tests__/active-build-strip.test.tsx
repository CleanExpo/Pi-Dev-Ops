/**
 * ActiveBuildStrip — accessibility of a running build (RA-7843).
 *
 * The live suite's axe scan failed every Control page while a build ran:
 * aria-prohibited-attr on the pulsing dot (span[aria-label="building"]) and
 * the progress bar (div[aria-label="Sandbox verify — 14%"]). aria-label is
 * not allowed on an element with no role. The strip only renders while a
 * build is active, which is why it passed on quiet runs.
 */
import { cleanup, render, screen } from "@testing-library/react";
import axe from "axe-core";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const fetchProxyJSON = vi.fn<(path: string) => Promise<unknown>>();

vi.mock("@/lib/pi-ceo-fetch", () => ({
  fetchProxyJSON: (path: string) => fetchProxyJSON(path),
}));

import ActiveBuildStrip from "@/components/control/ActiveBuildStrip";

function session(status: string) {
  return {
    id: "sess-1",
    repo: "https://github.com/CleanExpo/Pi-Dev-Ops",
    status,
    lines: 10,
    last_phase: "sandbox",
    files_modified: 0,
    retry_count: 0,
    evaluator_score: null,
    evaluator_status: null,
    started: Date.now() / 1000 - 60,
  };
}

async function prohibitedAttrViolations(container: HTMLElement) {
  const result = await axe.run(container, { runOnly: ["aria-prohibited-attr"] });
  return result.violations.flatMap((v) => v.nodes.map((n) => n.html));
}

beforeEach(() => fetchProxyJSON.mockReset());
afterEach(() => cleanup());

describe("ActiveBuildStrip accessibility", () => {
  it("a determinate build has no prohibited aria-label and reports its progress", async () => {
    fetchProxyJSON.mockResolvedValue([session("evaluating")]);
    const { container } = render(<ActiveBuildStrip />);
    const bar = await screen.findByRole("progressbar");
    expect(bar.getAttribute("aria-valuenow")).toBe("14");
    expect(bar.getAttribute("aria-valuetext")).toMatch(/14%/);
    expect(await prohibitedAttrViolations(container)).toEqual([]);
  });

  it("an indeterminate build is a progressbar with no value", async () => {
    fetchProxyJSON.mockResolvedValue([session("building")]);
    const { container } = render(<ActiveBuildStrip />);
    const bar = await screen.findByRole("progressbar");
    expect(bar.hasAttribute("aria-valuenow")).toBe(false);
    expect(await prohibitedAttrViolations(container)).toEqual([]);
  });
});
