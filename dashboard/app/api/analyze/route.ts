// app/api/analyze/route.ts — SSE stream: runs all 8 analysis phases and pushes results to GitHub

export const maxDuration = 300; // Vercel Pro: 5-minute max
export const dynamic = "force-dynamic";

import { NextRequest } from "next/server";
import {
  makeOctokit,
  parseRepoUrl,
  getDefaultBranch,
  createBranch,
  fetchRepoContext,
  pushFile,
  createPR,
} from "@/lib/github";
import { makeClient, buildContext, runPhase, getAnalysisMode } from "@/lib/claude";
import {
  PHASES,
  PHASE_PROMPTS,
  applyPhaseResult,
} from "@/lib/phases";
import type { TermLine, PhaseStatus, AnalysisResult } from "@/lib/types";

function sseEncode(event: string, data: unknown): Uint8Array {
  const payload = `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
  return new TextEncoder().encode(payload);
}

function sanitizeRepoUrl(url: string): string {
  // Accept https://github.com/owner/repo or github.com/owner/repo
  const trimmed = url.trim().replace(/^(?:https?:\/\/)?(?:www\.)?/, "https://");
  if (!/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+/.test(trimmed)) {
    throw new Error("Invalid GitHub repository URL");
  }
  return trimmed;
}

export async function GET(req: NextRequest) {
  const url = new URL(req.url);
  const rawRepo = url.searchParams.get("repo") ?? "";
  const ghToken = url.searchParams.get("token") || process.env.GITHUB_TOKEN || "";

  const encoder = new TextEncoder();
  const stream = new ReadableStream({
    async start(controller) {
      const send = (event: string, data: unknown) => {
        try { controller.enqueue(sseEncode(event, data)); } catch { /* closed */ }
      };
      const line = (type: TermLine["type"], text: string) =>
        send("line", { type, text, ts: Date.now() / 1000 } satisfies TermLine);

      try {
        // ── Validate inputs ───────────────────────────────────────
        const repoUrl = sanitizeRepoUrl(rawRepo);
        const { owner, repo } = parseRepoUrl(repoUrl);

        if (!ghToken) throw new Error("GitHub token required — set GITHUB_TOKEN env var or pass ?token=");
        const octokit = makeOctokit(ghToken);
        const claude = makeClient();

        const mode = getAnalysisMode();
        line("system", `PI CEO — CODE ANALYSIS ENGINE`);
        line("system", `Repo:  ${owner}/${repo}`);
        line("system", `Mode:  ${mode === "cli" ? "Claude Max (CLI)" : "Anthropic API"}`);
        line("system", `Time:  ${new Date().toISOString()}`);
        line("system", "");

        // ── Create analysis branch ────────────────────────────────
        const defaultBranch = await getDefaultBranch(octokit, owner, repo);
        const branchName = `pidev/analysis-${new Date().toISOString().slice(0, 10).replace(/-/g, "")}`;
        line("system", `Creating branch: ${branchName}`);
        await createBranch(octokit, owner, repo, branchName, defaultBranch);
        send("branch", { branch: branchName });
        line("success", `Branch ready: ${branchName}`);
        line("system", "");

        // ── Fetch repo context ────────────────────────────────────
        line("phase", "FETCHING REPO CONTEXT...");
        const files = await fetchRepoContext(octokit, owner, repo, defaultBranch);
        line("system", `  Fetched ${files.length} files`);
        const context = buildContext(files);
        line("system", `  Context: ${Math.round(context.length / 1000)}KB`);
        line("system", "");

        // ── Run 8 phases ─────────────────────────────────────────
        let result: Partial<AnalysisResult> = { repoUrl, repoName: repo, branch: branchName };
        const model = process.env.ANALYSIS_MODEL ?? "claude-sonnet-4-6";

        for (const phase of PHASES.slice(0, 7)) {
          send("phase_update", { phaseId: phase.id, status: "running" satisfies PhaseStatus });
          line("phase", `[${phase.id}/8] ${phase.name}`);
          line("system", `  Skill: ${phase.skill}`);

          const prompt = PHASE_PROMPTS[phase.id];
          let phaseOutput = "";

          try {
            phaseOutput = await runPhase(claude, model, prompt, context, (chunk) => {
              // Stream Claude's output line by line
              const lines = chunk.split("\n");
              for (const l of lines) {
                if (l.trim()) line("agent", `  ${l}`);
              }
            });
          } catch (err) {
            line("error", `  Phase ${phase.id} failed: ${err instanceof Error ? err.message : "unknown"}`);
            send("phase_update", { phaseId: phase.id, status: "error" satisfies PhaseStatus });
            continue;
          }

          result = applyPhaseResult(result, phase.id, phaseOutput);
          send("result_update", { field: "partial", value: result });
          send("phase_update", { phaseId: phase.id, status: "done" satisfies PhaseStatus });
          line("success", `  Phase ${phase.id} complete`);
          line("system", "");

          // Persist phase output to GitHub
          const fileName = `.harness/phase${phase.id}-${phase.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.json`;
          await pushFile(octokit, owner, repo, branchName, fileName, phaseOutput,
            `audit: phase ${phase.id} — ${phase.name}`).catch(() => {});
        }

        // ── Phase 8: Commit final harness files and push ─────────
        send("phase_update", { phaseId: 8, status: "running" satisfies PhaseStatus });
        line("phase", "[8/8] COMMIT & PREVIEW");

        const specMd = buildSpecMd(result, repo, branchName);
        const execSummaryMd = buildExecSummary(result);
        const featureListJson = JSON.stringify(
          (result.sprints ?? []).flatMap((s) => s.items.map((i, idx) => ({
            id: `F${String(s.id * 100 + idx).padStart(3, "0")}`,
            title: i.title, sprint: s.id, size: i.size, priority: i.priority, status: "planned",
          }))),
          null, 2
        );

        await Promise.allSettled([
          pushFile(octokit, owner, repo, branchName, ".harness/spec.md", specMd, "audit: spec.md"),
          pushFile(octokit, owner, repo, branchName, ".harness/executive-summary.md", execSummaryMd, "audit: executive-summary.md"),
          pushFile(octokit, owner, repo, branchName, ".harness/feature_list.json", featureListJson, "audit: feature_list.json"),
        ]);

        line("success", "  Harness files committed");

        // ── Create PR ────────────────────────────────────────────
        const prUrl = await createPR(
          octokit, owner, repo, branchName, defaultBranch,
          `audit: Pi CEO full analysis — ${repo}`,
          `## Pi CEO Analysis\n\nBranch: \`${branchName}\`\n\nAll 8 analysis phases complete. Review \`.harness/\` for full results.`
        ).catch(() => null);

        send("phase_update", { phaseId: 8, status: "done" satisfies PhaseStatus });
        line("success", `  PR created: ${prUrl ?? "(create manually)"}`);
        line("system", "");
        line("phase", "=== ANALYSIS COMPLETE ===");

        send("done", {
          sessionId: `${owner}-${repo}-${Date.now()}`,
          branch: branchName,
          prUrl,
          result,
        });

      } catch (err) {
        const msg = err instanceof Error ? err.message : "Unknown error";
        send("line", { type: "error", text: `✗ ${msg}`, ts: Date.now() / 1000 });
        send("error", { message: msg });
      } finally {
        controller.close();
      }
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream",
      "Cache-Control": "no-cache, no-transform",
      "X-Accel-Buffering": "no",
      Connection: "keep-alive",
    },
  });
}

function buildSpecMd(r: Partial<AnalysisResult>, repo: string, branch: string): string {
  return `# Pi CEO Analysis — ${repo}

Branch: \`${branch}\`
Date: ${new Date().toISOString().slice(0, 10)}

## Tech Stack
${(r.techStack ?? []).join(", ")}

## Quality Scores
| Dimension | Score |
|-----------|-------|
| Completeness | ${r.quality?.completeness ?? "?"}/10 |
| Correctness | ${r.quality?.correctness ?? "?"}/10 |
| Code Quality | ${r.quality?.codeQuality ?? "?"}/10 |
| Documentation | ${r.quality?.documentation ?? "?"}/10 |

## ZTE Maturity
Level ${r.zteLevel ?? "?"} — Score: ${r.zteScore ?? "?"}/60

## Sprint Plan
${(r.sprints ?? []).map((s) => `### Sprint ${s.id}: ${s.name} (${s.duration})\n${s.items.map((i) => `- [${i.size}] ${i.title}`).join("\n")}`).join("\n\n")}
`;
}

function buildExecSummary(r: Partial<AnalysisResult>): string {
  return `# Executive Summary

${r.executiveSummary ?? ""}

## Strengths
${(r.strengths ?? []).map((s) => `- ${s}`).join("\n")}

## Weaknesses
${(r.weaknesses ?? []).map((s) => `- ${s}`).join("\n")}

## Next Actions
${(r.nextActions ?? []).map((a, i) => `${i + 1}. ${a}`).join("\n")}
`;
}
