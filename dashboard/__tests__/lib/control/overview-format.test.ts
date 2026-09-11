import { describe, expect, it } from "vitest";
import {
  OVERVIEW_QUICK_LINKS,
  claudeCliChip,
  overviewLede,
  overviewServiceRows,
  serviceMark,
  swarmChip,
} from "@/lib/control/overview-format";

describe("Overview honesty", () => {
  it("does not call Swarm Active when the backend only said ok", () => {
    expect(swarmChip({}).label).toBe("—");
    expect(swarmChip({ status: "ok" } as { swarm_enabled?: boolean }).label).toBe("—");
    expect(swarmChip({ swarm_enabled: true }).label).toBe("Active");
    expect(swarmChip({ swarm_enabled: false }).label).toBe("Off");
    expect(overviewLede({ status: "ok" } as { uptime_s?: number })).toContain("unknown");
    expect(overviewLede(null)).toContain("not a live reading");
    expect(claudeCliChip({}).color).toContain("text-dim");
  });

  it("marks missing service flags as unknown, not failed", () => {
    expect(serviceMark(undefined)).toBe("unknown");
    expect(serviceMark(false)).toBe("off");
    expect(overviewServiceRows(null).every((row) => row.mark === "unknown")).toBe(true);
    expect(overviewServiceRows({ claude_cli: true, anthropic_key: false })[0]?.mark).toBe("ok");
    expect(overviewServiceRows({ claude_cli: true, anthropic_key: false })[1]?.mark).toBe("off");
  });

  it("points quick actions at Goal and Build, not the old Dashboard analysis path", () => {
    expect(OVERVIEW_QUICK_LINKS.map((item) => item.href)).toEqual([
      "/control/goal",
      "/control/build",
      "/builds",
      "/history",
    ]);
  });
});
