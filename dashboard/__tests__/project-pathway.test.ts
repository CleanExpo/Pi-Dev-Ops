import { expect, it } from "vitest";
import { latestPipelineForRepo, stageEvidence, type PipelineSummary } from "@/lib/control/project-pathway";

it("matches only the same GitHub repository and uses the newest pipeline", () => {
  const entries: PipelineSummary[] = [
    { pipeline_id: "old", repo_url: "https://github.com/CleanExpo/CARSI.git", current_phase: "done", phases_completed: ["ship"], updated_at: "2026-01-01T00:00:00Z" },
    { pipeline_id: "other", repo_url: "https://github.com/Other/CARSI", current_phase: "done", phases_completed: ["ship"], updated_at: "2026-12-01T00:00:00Z" },
    { pipeline_id: "new", repo_url: "git@github.com:CleanExpo/CARSI.git", current_phase: "test", phases_completed: ["spec", "plan"], updated_at: "2026-09-29T00:00:00Z" },
  ];
  const pipeline = latestPipelineForRepo("CleanExpo/CARSI", entries);
  expect(pipeline?.pipeline_id).toBe("new");
  expect(stageEvidence("Discovery", pipeline)).toBe("completed");
  expect(stageEvidence("Release", pipeline)).toBe("unverified");
  expect(stageEvidence("Live", pipeline)).toBe("unverified");
  expect(latestPipelineForRepo("CleanExpo/Unknown", entries)).toBeNull();
});

it("keeps 1,000 varied repository timelines separate and never infers Live", () => {
  for (let index = 0; index < 1000; index++) {
    const name = `Project${index}`;
    const entries: PipelineSummary[] = [
      { pipeline_id: `old-${index}`, repo_url: `https://github.com/CleanExpo/${name}.git`, current_phase: "review", phases_completed: ["spec", "plan", "build"], updated_at: "2026-01-01T00:00:00Z" },
      { pipeline_id: `unrelated-${index}`, repo_url: `https://github.com/Other/${name}`, current_phase: "ship", phases_completed: ["ship"], updated_at: "2026-12-01T00:00:00Z" },
      { pipeline_id: `new-${index}`, repo_url: `git@github.com:CleanExpo/${name}.git`, current_phase: index % 2 ? "test" : "ship", phases_completed: index % 2 ? ["spec", "plan"] : ["spec", "plan", "build", "test", "review", "ship"], updated_at: "2026-09-29T00:00:00Z" },
    ];
    const matched = latestPipelineForRepo(`cleanexpo/${name.toLowerCase()}`, entries);
    expect(matched?.pipeline_id).toBe(`new-${index}`);
    expect(stageEvidence("Live", matched)).toBe("unverified");
    expect(stageEvidence("Release", matched)).toBe(index % 2 ? "unverified" : "completed");
  }
});
