// app/api/analyze/route.ts — SSE stream: 8 analysis phases with Supabase persistence

export const maxDuration = 300; // Vercel Pro: 5-minute max
export const dynamic = "force-dynamic";

import { NextRequest } from "next/server";
import {
  makeOctokit, parseRepoUrl, getDefaultBranch,
  createBranch, fetchRepoContext, fetchBranchDiffs, pushFile, createPR,
} from "@/lib/github";
import { makeClient, buildContext, runPhase, getAnalysisMode } from "@/lib/claude";
import { PHASES, PHASE_PROMPTS, applyPhaseResult } from "@/lib/phases";
import { getSettings } from "@/lib/supabase/settings";
import { createServerClient } from "@/lib/supabase/server";
import { createDeployment, getProjectId } from "@/lib/vercel-api";
import type { TermLine, PhaseStatus, AnalysisResult } from "@/lib/types";

async function sendTelegramMessage(botToken: string, chatId: string, text: string): Promise<void> {
  try {
    await fetch(`https://api.telegram.org/bot${botToken}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text, parse_mode: "Markdown" }),
    });
  } catch { /* non-critical */ }
}

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
      const logError = (ctx: string, err: unknown) => {
        console.error(`[analyze] ${ctx}:`, err instanceof Error ? err.message : err);
      };

      // ── Graceful budget: 270s (30s before Vercel's 300s hard limit) ────────
      // Sends partial results and a timeout event instead of being killed mid-phase.
      const BUDGET_MS = 270_000;
      let budgetFired = false;
      const budgetTimer = setTimeout(() => { budgetFired = true; }, BUDGET_MS);

      // ── Keepalive: comment ping every 15s to prevent proxy buffering ───────
      const keepalive = setInterval(() => {
        try { controller.enqueue(new TextEncoder().encode(": ping\n\n")); } catch { /* closed */ }
      }, 15_000);

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
          void supabase.from("terminal_lines").insert({
            session_id: resolvedSessionId,
            type, text, ts: termLine.ts, seq: lineSeq++,
          });
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
          })

          await supabase.from("phase_states").insert(
            PHASES.map((p) => ({ session_id: resolvedSessionId, phase_id: p.id, status: "pending" }))
          )
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
        line("system", `  Fetched ${files.length} files (${Math.round(JSON.stringify(files).length / 1000)}KB)`);

        const branchFiles = await fetchBranchDiffs(octokit, owner, repo, defaultBranch);
        if (branchFiles.length > 0) {
          files.push(...branchFiles);
          line("system", `  + ${branchFiles.length} files from feature branches`);
        }

        const context = buildContext(files);
        line("system", `  Total context: ${files.length} files (${Math.round(context.length / 1000)}KB)`);
        line("system", "");

        // ── Run 7 analysis phases ────────────────────────────────
        let result: Partial<AnalysisResult> = { repoUrl, repoName: repo, branch: branchName };

        for (const phase of PHASES.slice(0, 7)) {
          // Check budget before starting each phase
          if (budgetFired) {
            line("system", `⚠ Analysis budget reached — skipping phase ${phase.id}+`);
            break;
          }
          send("phase_update", { phaseId: phase.id, status: "running" satisfies PhaseStatus });
          if (supabase) {
            supabase.from("phase_states").update({ status: "running", started_at: new Date() })
              .eq("session_id", resolvedSessionId).eq("phase_id", phase.id);
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
                .eq("session_id", resolvedSessionId).eq("phase_id", phase.id);
            }
            continue;
          }

          result = applyPhaseResult(result, phase.id, phaseOutput);
          send("result_update", { field: "partial", value: result });
          send("phase_update", { phaseId: phase.id, status: "done" satisfies PhaseStatus });
          if (supabase) {
            supabase.from("phase_states").update({ status: "done", done_at: new Date() })
              .eq("session_id", resolvedSessionId).eq("phase_id", phase.id);
          }
          line("success", `  Phase ${phase.id} complete`);
          line("system", "");

          // Push phase output to GitHub branch
          const fileName = `.harness/phase${phase.id}-${phase.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}.json`;
          await pushFile(octokit, owner, repo, branchName, fileName, phaseOutput,
            `audit: phase ${phase.id} — ${phase.name}`)
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

        // ── Auto-create Linear triage ticket ─────────────────────
        const linearKey = settings.linearApiKey || process.env.LINEAR_API_KEY;
        if (linearKey) {
          try {
            const linearGql = async (query: string, variables: Record<string, unknown> = {}) => {
              const res = await fetch("https://api.linear.app/graphql", {
                method: "POST",
                headers: {
                  "Content-Type": "application/json",
                  "Authorization": linearKey,
                },
                body: JSON.stringify({ query, variables }),
              });
              const json = await res.json() as { data?: Record<string, unknown>; errors?: unknown[] };
              if (json.errors) throw new Error(`Linear API error: ${JSON.stringify(json.errors)}`);
              return json.data!;
            };

            // 1. Get team ID
            const teamsData = await linearGql(`{ teams { nodes { id name } } }`) as { teams: { nodes: { id: string; name: string }[] } };
            const team = teamsData.teams.nodes[0];
            if (!team) throw new Error("No Linear team found");

            // 2. Find the "Triage" workflow state for this team
            const statesData = await linearGql(`{
              workflowStates(filter: { team: { id: { eq: "${team.id}" } }, name: { eq: "Triage" } }) {
                nodes { id name }
              }
            }`) as { workflowStates: { nodes: { id: string; name: string }[] } };
            const triageState = statesData.workflowStates.nodes[0] ?? null;

            // 3. Build issue description with PR URL and phase scores
            const date = new Date().toISOString().slice(0, 10);
            const qualityLines = result.quality
              ? [
                  `| Completeness | ${result.quality.completeness ?? "?"}/10 |`,
                  `| Correctness  | ${result.quality.correctness ?? "?"}/10 |`,
                  `| Code Quality | ${result.quality.codeQuality ?? "?"}/10 |`,
                  `| Documentation| ${result.quality.documentation ?? "?"}/10 |`,
                ].join("\n")
              : "_Not scored_";

            const description = [
              `## Pi CEO Analysis — ${repo}`,
              "",
              `**Date:** ${date}`,
              `**Branch:** \`${branchName}\``,
              prUrl ? `**PR:** ${prUrl}` : "",
              "",
              "## Quality Scores",
              "| Dimension | Score |",
              "|-----------|-------|",
              qualityLines,
              "",
              `**ZTE Level:** ${result.zteLevel ?? "?"} — Score: ${result.zteScore ?? "?"}/60`,
              "",
              "## Summary",
              result.executiveSummary ?? "_No summary generated._",
            ].filter((l) => l !== null).join("\n");

            // 4. Create the issue
            const issueInput: Record<string, unknown> = {
              title: `Analysis: ${repo} ${date}`,
              teamId: team.id,
              description,
              priority: 3, // Normal
            };
            if (triageState) issueInput.stateId = triageState.id;

            const issueData = await linearGql(`
              mutation CreateIssue($input: IssueCreateInput!) {
                issueCreate(input: $input) {
                  success
                  issue { id identifier title url state { name } }
                }
              }
            `, { input: issueInput }) as { issueCreate: { success: boolean; issue: { identifier: string; url: string } } };

            const issue = issueData.issueCreate.issue;
            line("success", `  Linear: ${issue.identifier} — ${issue.url}`);
          } catch (err) {
            logError("linear-triage", err);
            // non-fatal — analysis already complete
          }
        }

        // ── Vercel preview deployment (optional) ─────────────────
        let previewUrl: string | null = null;
        if (settings.vercelToken) {
          try {
            line("system", "  Triggering Vercel preview deployment…");
            const projectId = await getProjectId(settings.vercelToken, "pi-dev-ops");
            if (projectId) {
              const deploy = await createDeployment(settings.vercelToken, projectId, branchName);
              if (deploy?.url) {
                previewUrl = `https://${deploy.url}`;
                result = { ...result, previewUrl };
                send("branch", { branch: branchName, previewUrl });
                line("success", `  Preview: ${previewUrl}`);
              }
            }
          } catch (err) {
            logError("vercel-deploy", err);
            line("system", "  Vercel deploy skipped (check token)");
          }
        }

        line("system", "");
        line("phase", "=== ANALYSIS COMPLETE ===");

        // ── Persist session result ────────────────────────────────
        if (supabase) {
          supabase.from("sessions").update({
            status: "done", branch: branchName, pr_url: prUrl,
            completed_at: new Date(), result,
          }).eq("id", resolvedSessionId);
        }

        // ── Telegram notification (optional) ─────────────────────
        if (settings.telegramBotToken && settings.telegramChatId) {
          const zte   = result.zteLevel ? `L${result.zteLevel}` : "?";
          const score = result.zteScore ?? "?";
          const msg   = [
            `✅ *Pi CEO Analysis Complete*`,
            `Repo: \`${repo}\``,
            `Branch: \`${branchName}\``,
            `ZTE: ${zte} (${score}/60)`,
            prUrl      ? `PR: ${prUrl}` : "",
            previewUrl ? `Preview: ${previewUrl}` : "",
          ].filter(Boolean).join("\n");
          void sendTelegramMessage(settings.telegramBotToken, settings.telegramChatId, msg);
        }

        send("done", { sessionId: resolvedSessionId, branch: branchName, prUrl, result });

      } catch (err) {
        const msg = err instanceof Error ? err.message : "Unknown error";
        logError("analysis", err);
        send("line", { type: "error", text: `✗ ${msg}`, ts: Date.now() / 1000 });
        send("error", { message: msg });
        if (supabase) {
          supabase.from("sessions").update({ status: "error", completed_at: new Date() })
            .eq("id", resolvedSessionId);
        }
        // Telegram error notification
        if (settings?.telegramBotToken && settings?.telegramChatId) {
          void sendTelegramMessage(
            settings.telegramBotToken, settings.telegramChatId,
            `❌ *Pi CEO Analysis Failed*\nRepo: \`${rawRepo}\`\nError: ${msg}`
          );
        }
      } finally {
        clearTimeout(budgetTimer);
        clearInterval(keepalive);
        // If budget fired before error, send partial results + timeout event
        if (budgetFired) {
          send("line", { type: "error", text: "⚠ Analysis budget reached (270s). Partial results saved — re-run to complete remaining phases.", ts: Date.now() / 1000 });
          send("timeout", { partial: true });
        }
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
