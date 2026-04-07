// app/api/analyze/route.ts — SSE stream: 8 analysis phases with Supabase persistence

export const maxDuration = 300; // Vercel Pro: 5-minute max
export const dynamic = "force-dynamic";

import { NextRequest } from "next/server";
import {
  makeOctokit, parseRepoUrl, getDefaultBranch,
  createBranch, fetchRepoContext, pushFile, createPR,
} from "@/lib/github";
import { makeClient, buildContext, runPhase, getAnalysisMode } from "@/lib/claude";
import { PHASES, PHASE_PROMPTS, applyPhaseResult } from "@/lib/phases";
import { getSettings } from "@/lib/supabase/settings";
import { createServerClient } from "@/lib/supabase/server";
import type { TermLine, PhaseStatus, AnalysisResult } from "@/lib/types";

function sseEncode(event: string, data: unknown): Uint8Array {
  return new TextEncoder().encode(`event: ${event}\ndata: ${JSON.stringify(data)}\n\n`);
}

function sanitizeRepoUrl(url: string): string {
  const trimmed = url.trim().replace(/^(?:https?:\/\/)?(?:www\.)?/, "https://");
  if (!/^https:\/\/github\.com\/[\w.-]+\/[\w.-]+/.test(trimmed))
    throw new Error("Invalid GitHub repository URL");
  return trimmed;
}

export async function GET(req: NextRequest) {
  // Detect trigger source (manual browser, GitHub webhook, or Vercel cron)
  const trigger = req.headers.get("x-webhook-trigger") === "github" ? "webhook"
                : req.headers.get("x-cron-trigger")    === "true"   ? "cron"
                : "manual" as "manual" | "webhook" | "cron";

  const url = new URL(req.url);
  const rawRepo = url.searchParams.get("repo") ?? "";

  // Load settings from Supabase (falls back to process.env)
  const settings = await getSettings();

  const ghToken = settings.githubToken || url.searchParams.get("token") || process.env.GITHUB_TOKEN || "";
  const model   = settings.analysisModel || process.env.ANALYSIS_MODEL || "claude-sonnet-4-6";

  const stream = new ReadableStream({
    async start(controller) {
      const send = (event: string, data: unknown) => {
        try { controller.enqueue(sseEncode(event, data)); } catch { /* closed */ }
      };

      // Supabase client (best-effort — if not configured, analysis still runs)
      let supabase: ReturnType<typeof createServerClient> | null = null;
      try { supabase = createServerClient(); } catch { /* no Supabase config yet */ }

      let lineSeq = 0;
      const sessionId = `${Date.now()}`; // set properly after repo is parsed

      const line = (type: TermLine["type"], text: string) => {
        const termLine: TermLine = { type, text, ts: Date.now() / 1000 };
        send("line", termLine);
        // Persist fire-and-forget
        if (supabase && (controller as unknown as { desiredSize: number | null }).desiredSize !== null) {
          supabase.from("terminal_lines").insert({
            session_id: resolvedSessionId,
            type, text, ts: termLine.ts, seq: lineSeq++,
          }).then(() => {}).catch(() => {});
        }
      };

      let resolvedSessionId = sessionId;

      try {
        // ── Validate ──────────────────────────────────────────────
        const repoUrl = sanitizeRepoUrl(rawRepo);
        const { owner, repo } = parseRepoUrl(repoUrl);
        resolvedSessionId = `${owner}-${repo}-${Date.now()}`;

        if (!ghToken) throw new Error("GitHub token required — add it in Settings or pass ?token=");
        const octokit = makeOctokit(ghToken);
        const claude  = makeClient(settings.anthropicApiKey);

        line("system", "PI CEO — CODE ANALYSIS ENGINE");
        line("system", `Repo:  ${owner}/${repo}`);
        line("system", `Mode:  ${getAnalysisMode() === "cli" ? "Claude Max (CLI)" : "Anthropic API"}`);
        line("system", `Time:  ${new Date().toISOString()}`);
        line("system", `Trigger: ${trigger.toUpperCase()}`);
        line("system", "");

        // ── Persist session start ─────────────────────────────────
        if (supabase) {
          await supabase.from("sessions").insert({
            id: resolvedSessionId, repo_url: repoUrl, repo_name: repo,
            status: "running", trigger,
          }).catch(() => {});

          await supabase.from("phase_states").insert(
            PHASES.map((p) => ({ session_id: resolvedSessionId, phase_id: p.id, status: "pending" }))
          ).catch(() => {});
        }

        // ── Branch ───────────────────────────────────────────────
        const defaultBranch = await getDefaultBranch(octokit, owner, repo);
        const branchName = `pidev/analysis-${new Date().toISOString().slice(0, 10).replace(/-/g, "")}`;
        line("system", `Creating branch: ${branchName}`);
        await createBranch(octokit, owner, repo, branchName, defaultBranch);
        send("branch", { branch: branchName });
        line("success", `Branch ready: ${branchName}`);
        line("system", "");

        // ── Repo context ─────────────────────────────────────────
        line("phase", "FETCHING REPO CONTEXT...");
        const files   = await fetchRepoContext(octokit, owner, repo, defaultBranch);
        const context = buildContext(files);
        line("system", `  Fetched ${files.length} files (${Math.round(context.length / 1000)}KB)`);
        line("system", "");

        // ── Run 7 analysis phases ────────────────────────────────
        let result: Partial<AnalysisResult> = { repoUrl, repoName: repo, branch: branchName };

        for (const phase of PHASES.slice(0, 7)) {
          send("phase_update", { phaseId: phase.id, status: "running" satisfies PhaseStatus });
          if (supabase) {
            supabase.from("phase_states").update({ status: "running", started_at: new Date() })
              .eq("session_id", resolvedSessionId).eq("phase_id", phase.id).then(() => {}).catch(() => {});
          }
          line("phase", `[${phase.id}/8] ${phase.name}`);
          line("system", `  Skill: ${phase.skill}`);

          let phaseOutput = "";
          try {
            phaseOutput = await runPhase(claude, model, PHASE_PROMPTS[phase.id], context, (chunk) => {
              chunk.split("\n").forEach((l) => { if (l.trim()) line("agent", `  ${l}`); });
            });
          } catch (err) {
            line("error", `  Phase ${phase.id} failed: ${err instanceof Error ? err.message : "unknown"}`);
            send("phase_update", { phaseId: phase.id, status: "error" satisfies PhaseStatus });
            if (supabase) {
              supabase.from("phase_states").update({ status: "error", done_at: new Date() })
                .eq("session_id", resolvedSessionId).eq("phase_id", phase.id).then(() => {}).catch(() => {});
            }
            continue;
          }

          result = applyPhaseResult(result, phase.id, phaseOutput);
          send("result_update", { field: "partial", value: result });
          send("phase_update", { phaseId: phase.id, status: "done" satisfies PhaseStatus });
          if (supabase) {
            supabase.from("phase_states").update({ status: "done", done_at: new Date() })
              .eq("session_id", resolvedSessionId).eq("phase_id", phase.id).then(() => {}).catch(() => {});
          }
          line("success", `  Phase ${phase.id} complete`);
          line("system", "");

          // Push phase output to GitHub branch
          const fileName = `.harness/phase${phase.id}-${phase.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.json`;
          await pushFile(octokit, owner, repo, branchName, fileName, phaseOutput,
            `audit: phase ${phase.id} — ${phase.name}`).catch(() => {});
        }

        // ── Phase 8: Commit harness + create PR ──────────────────
        send("phase_update", { phaseId: 8, status: "running" satisfies PhaseStatus });
        line("phase", "[8/8] COMMIT & PREVIEW");

        const specMd        = buildSpecMd(result, repo, branchName);
        const execSummaryMd = buildExecSummary(result);
        const featureListJson = JSON.stringify(
          (result.sprints ?? []).flatMap((s) => s.items.map((i, idx) => ({
            id: `F${String(s.id * 100 + idx).padStart(3, "0")}`,
            title: i.title, sprint: s.id, size: i.size, priority: i.priority, status: "planned",
          }))), null, 2
        );

        await Promise.allSettled([
          pushFile(octokit, owner, repo, branchName, ".harness/spec.md", specMd, "audit: spec.md"),
          pushFile(octokit, owner, repo, branchName, ".harness/executive-summary.md", execSummaryMd, "audit: executive-summary.md"),
          pushFile(octokit, owner, repo, branchName, ".harness/feature_list.json", featureListJson, "audit: feature_list.json"),
        ]);
        line("success", "  Harness files committed");

        const prUrl = await createPR(
          octokit, owner, repo, branchName, defaultBranch,
          `audit: Pi CEO full analysis — ${repo}`,
          `## Pi CEO Analysis\n\nBranch: \`${branchName}\`\n\nAll 8 analysis phases complete.`
        ).catch(() => null);

        send("phase_update", { phaseId: 8, status: "done" satisfies PhaseStatus });
        line("success", `  PR: ${prUrl ?? "(create manually)"}`);
        line("system", "");
        line("phase", "=== ANALYSIS COMPLETE ===");

        // ── Persist session result ────────────────────────────────
        if (supabase) {
          supabase.from("sessions").update({
            status: "done", branch: branchName, pr_url: prUrl,
            completed_at: new Date(), result,
          }).eq("id", resolvedSessionId).then(() => {}).catch(() => {});
        }

        send("done", { sessionId: resolvedSessionId, branch: branchName, prUrl, result });

      } catch (err) {
        const msg = err instanceof Error ? err.message : "Unknown error";
        send("line", { type: "error", text: `✗ ${msg}`, ts: Date.now() / 1000 });
        send("error", { message: msg });
        if (supabase) {
          supabase.from("sessions").update({ status: "error", completed_at: new Date() })
            .eq("id", resolvedSessionId).then(() => {}).catch(() => {});
        }
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
  return `# Pi CEO Analysis — ${repo}\n\nBranch: \`${branch}\`\nDate: ${new Date().toISOString().slice(0, 10)}\n\n## Tech Stack\n${(r.techStack ?? []).join(", ")}\n\n## Quality Scores\n| Dimension | Score |\n|-----------|-------|\n| Completeness | ${r.quality?.completeness ?? "?"}/10 |\n| Correctness | ${r.quality?.correctness ?? "?"}/10 |\n| Code Quality | ${r.quality?.codeQuality ?? "?"}/10 |\n| Documentation | ${r.quality?.documentation ?? "?"}/10 |\n\n## ZTE Maturity\nLevel ${r.zteLevel ?? "?"} — Score: ${r.zteScore ?? "?"}/60\n\n## Sprint Plan\n${(r.sprints ?? []).map((s) => `### Sprint ${s.id}: ${s.name} (${s.duration})\n${s.items.map((i) => `- [${i.size}] ${i.title}`).join("\n")}`).join("\n\n")}\n`;
}

function buildExecSummary(r: Partial<AnalysisResult>): string {
  return `# Executive Summary\n\n${r.executiveSummary ?? ""}\n\n## Strengths\n${(r.strengths ?? []).map((s) => `- ${s}`).join("\n")}\n\n## Weaknesses\n${(r.weaknesses ?? []).map((s) => `- ${s}`).join("\n")}\n\n## Next Actions\n${(r.nextActions ?? []).map((a, i) => `${i + 1}. ${a}`).join("\n")}\n`;
}
