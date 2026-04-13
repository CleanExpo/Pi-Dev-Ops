// app/api/analyze/route.ts — SSE stream: 8 analysis phases with Supabase persistence

export const maxDuration = 300; // Vercel Pro: 5-minute max
export const dynamic = "force-dynamic";

import { NextRequest } from "next/server";
import { Octokit } from "@octokit/rest";
import {
  makeOctokit, parseRepoUrl, getDefaultBranch,
  createBranch, fetchRepoContext, fetchBranchDiffs, pushFile, createPR,
} from "@/lib/github";
import { makeClient, buildContext, runPhase, getAnalysisMode } from "@/lib/claude";
import { PHASES, PHASE_PROMPTS, applyPhaseResult } from "@/lib/phases";

/** Fetch a single file from GitHub. Returns empty string if not found. */
async function fetchGitHubFile(
  octokit: Octokit,
  owner: string,
  repo: string,
  ref: string,
  path: string,
): Promise<string> {
  try {
    const { data } = await octokit.repos.getContent({ owner, repo, path, ref });
    if ("content" in data && typeof data.content === "string") {
      return Buffer.from(data.content, "base64").toString("utf-8");
    }
  } catch { /* file not found or not a file */ }
  return "";
}

/** Parse lessons.jsonl and return the top N most-severe recent lessons as a summary string. */
function buildLessonsSummary(raw: string, topN = 8): string {
  if (!raw.trim()) return "";
  const lessons: Array<{ severity?: string; source?: string; lesson?: string }> = [];
  for (const line of raw.split("\n")) {
    if (!line.trim()) continue;
    try { lessons.push(JSON.parse(line)); } catch { /* skip malformed */ }
  }
  // Sort: error first, then warn, then info
  const rank = (s?: string) => s === "error" ? 0 : s === "warn" ? 1 : 2;
  const top = lessons
    .filter((l) => l.lesson)
    .sort((a, b) => rank(a.severity) - rank(b.severity))
    .slice(0, topN);
  if (!top.length) return "";
  return [
    "=== LESSONS FROM PRIOR RUNS (apply these to improve your analysis) ===",
    ...top.map((l) => `[${l.severity ?? "info"}][${l.source ?? "?"}] ${l.lesson}`),
    "=================================================================",
  ].join("\n");
}
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
  const linearTicket = url.searchParams.get("linear_ticket")?.trim() ?? "";

  // Load settings from Supabase (falls back to process.env)
  const settings = await getSettings();

  const ghToken = settings.githubToken || url.searchParams.get("token") || process.env.GITHUB_TOKEN || "";
  const model   = settings.analysisModel || process.env.ANALYSIS_MODEL || "claude-sonnet-4-6";

  // Per-phase model selection — haiku for simple listing/summarisation tasks,
  // full model (sonnet) for intelligence-heavy phases (quality, ZTE, planning, narrative).
  const PHASE_MODELS: Record<number, string> = {
    1: "claude-haiku-3-5",   // CLONE & INVENTORY — counting and listing files
    2: "claude-haiku-3-5",   // ARCHITECTURE — pattern detection from file structure
    3: model,                // CODE QUALITY — needs intelligence
    4: "claude-haiku-3-5",   // CONTEXT — summarisation task
    5: model,                // GAP ANALYSIS — ZTE scoring needs intelligence
    6: model,                // ENHANCEMENT PLAN — sprint planning
    7: model,                // EXECUTIVE SUMMARY — CEO narrative
  };

  const stream = new ReadableStream({
    async start(controller) {
      const send = (event: string, data: unknown) => {
        try { controller.enqueue(sseEncode(event, data)); } catch { /* closed */ }
      };
      const logError = (ctx: string, err: unknown) => {
        console.error(`[analyze] ${ctx}:`, err instanceof Error ? err.message : err);
      };

      // ── Graceful budget: abort at 240s, hard stop at 260s ────────────────
      // AbortController fires at 240s — kills any in-progress phase cleanly.
      // budgetFired at 260s — prevents new phases from starting.
      // Vercel hard limit is 300s — we're done by ~255s.
      const ABORT_MS  = 240_000;
      const BUDGET_MS = 260_000;
      let budgetFired = false;
      const abortController = new AbortController();
      const abortTimer  = setTimeout(() => abortController.abort(), ABORT_MS);
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
        const _now = new Date();
        const _date = _now.toISOString().slice(0, 10).replace(/-/g, "");
        const _time = _now.toISOString().slice(11, 16).replace(":", "");
        const branchName = linearTicket
          ? `pidev/analysis-${linearTicket.replace(/[^a-zA-Z0-9]/g, "")}-${_date}-${_time}`
          : `pidev/analysis-${_date}-${_time}`;
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

        // ── Feedback loops + Knowledge retention ─────────────────
        // Fetch lessons.jsonl, skill files, and harness evidence docs to enrich
        // intelligence phases. Best-effort: missing files don't block analysis.
        const [lessonsRaw, evalSkill, zteSkill, leverageSkill, ceoSkill,
               leverageAudit, claudeMd, harnessSpec] =
          await Promise.all([
            fetchGitHubFile(octokit, owner, repo, defaultBranch, ".harness/lessons.jsonl"),
            fetchGitHubFile(octokit, owner, repo, defaultBranch, "skills/tier-evaluator/SKILL.md"),
            fetchGitHubFile(octokit, owner, repo, defaultBranch, "skills/zte-maturity/SKILL.md"),
            fetchGitHubFile(octokit, owner, repo, defaultBranch, "skills/leverage-audit/SKILL.md"),
            fetchGitHubFile(octokit, owner, repo, defaultBranch, "skills/ceo-mode/SKILL.md"),
            // Harness evidence docs — critical for accurate ZTE scoring (phase 5)
            fetchGitHubFile(octokit, owner, repo, defaultBranch, ".harness/leverage-audit.md"),
            fetchGitHubFile(octokit, owner, repo, defaultBranch, "CLAUDE.md"),
            fetchGitHubFile(octokit, owner, repo, defaultBranch, ".harness/spec.md"),
          ]);
        const lessonsSummary = buildLessonsSummary(lessonsRaw);
        if (lessonsSummary) line("system", `  Injecting ${lessonsSummary.split("\n").length - 2} lessons into intelligence phases`);
        if (leverageAudit)  line("system", `  Injecting leverage-audit.md into ZTE phase (${Math.round(leverageAudit.length / 1000)}KB evidence)`);
        if (claudeMd)       line("system", `  Injecting CLAUDE.md into architecture + ZTE phases`);

        /** Validates that intelligence-heavy phase output contains required JSON fields. */
        function isPhaseOutputValid(phaseId: number, output: string): boolean {
          if (![3, 5, 6].includes(phaseId)) return true;
          if (phaseId === 3) return output.includes('"completeness"') && output.includes('"correctness"');
          if (phaseId === 5) return output.includes('"leveragePoints"') && output.includes('"zteScore"');
          if (phaseId === 6) return output.includes('"sprints"');
          return true;
        }

        /** Returns context enriched with lessons + skill guides + harness evidence for a given phase. */
        const enrichedContext = (phaseId: number): string => {
          const parts: string[] = [context];
          // CLAUDE.md + spec.md give architecture phases full project context
          if ([2, 5].includes(phaseId) && claudeMd)
            parts.push(`=== CLAUDE.md (architecture, ZTE score, coding conventions) ===\n${claudeMd}`);
          if ([2, 5].includes(phaseId) && harnessSpec)
            parts.push(`=== HARNESS SPEC (.harness/spec.md) ===\n${harnessSpec}`);
          // Lessons injected into intelligence-heavy phases
          if (lessonsSummary && [3, 5, 6, 7].includes(phaseId)) parts.push(lessonsSummary);
          // Skill guides
          if (phaseId === 3 && evalSkill)     parts.push(`=== SKILL GUIDE: TIER-EVALUATOR ===\n${evalSkill}`);
          if (phaseId === 5 && zteSkill)      parts.push(`=== SKILL GUIDE: ZTE-MATURITY ===\n${zteSkill}`);
          if (phaseId === 5 && leverageSkill) parts.push(`=== SKILL GUIDE: LEVERAGE-AUDIT ===\n${leverageSkill}`);
          // leverage-audit.md is the primary ZTE evidence document — inject for phase 5 scoring
          if (phaseId === 5 && leverageAudit)
            parts.push(`=== ZTE EVIDENCE: .harness/leverage-audit.md (operational proof of each dimension) ===\n${leverageAudit}`);
          if (phaseId === 7 && ceoSkill)      parts.push(`=== SKILL GUIDE: CEO-MODE ===\n${ceoSkill}`);
          return parts.join("\n\n");
        };

        // ── Run 7 analysis phases ────────────────────────────────
        let result: Partial<AnalysisResult> = { repoUrl, repoName: repo, branch: branchName };

        for (const phase of PHASES.slice(0, 7)) {
          // Check budget / abort before starting each phase
          if (budgetFired || abortController.signal.aborted) {
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
            phaseOutput = await runPhase(claude, PHASE_MODELS[phase.id] ?? model, PHASE_PROMPTS[phase.id], enrichedContext(phase.id), (chunk) => {
              chunk.split("\n").forEach((l) => { if (l.trim()) line("agent", `  ${l}`); });
            }, abortController.signal);
          } catch (err) {
            const isAbort = abortController.signal.aborted || (err instanceof Error && err.message.includes("aborted"));
            if (isAbort) {
              line("system", `⚠ Phase ${phase.id} cut short — budget limit reached, saving partial results`);
              send("phase_update", { phaseId: phase.id, status: "error" satisfies PhaseStatus });
              break; // exit loop, fall through to send done with partial results
            }
            line("error", `  Phase ${phase.id} failed: ${err instanceof Error ? err.message : "unknown"}`);
            send("phase_update", { phaseId: phase.id, status: "error" satisfies PhaseStatus });
            if (supabase) {
              supabase.from("phase_states").update({ status: "error", done_at: new Date() })
                .eq("session_id", resolvedSessionId).eq("phase_id", phase.id);
            }
            continue;
          }

          // RA-741: Auto-retry once if intelligence-heavy phase output is missing required fields
          if (!isPhaseOutputValid(phase.id, phaseOutput)) {
            line("system", `  ⚠ Phase ${phase.id} output invalid — retrying with guidance`);
            const retryPrompt = `PREVIOUS ATTEMPT RETURNED INVALID OUTPUT — missing required JSON fields.\nFollow the output schema exactly. Return ONLY valid JSON.\n\n${PHASE_PROMPTS[phase.id]}`;
            try {
              phaseOutput = await runPhase(claude, PHASE_MODELS[phase.id] ?? model, retryPrompt, enrichedContext(phase.id), (chunk) => {
                chunk.split("\n").forEach((l) => { if (l.trim()) line("agent", `  ${l}`); });
              }, abortController.signal);
            } catch { /* retry failed — use original output */ }
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

        // RA-743: Post completion comment to Linear ticket (fire-and-forget)
        const linearCommentKey = process.env.LINEAR_API_KEY ?? "";
        if (linearTicket && linearCommentKey && result.zteScore) {
          fetch("https://api.linear.app/graphql", {
            method: "POST",
            headers: { "Content-Type": "application/json", "Authorization": linearCommentKey },
            body: JSON.stringify({
              query: `mutation { commentCreate(input: { issueId: "${linearTicket}", body: "Analysis complete: branch \`${branchName}\` · ZTE ${result.zteScore}/60 L${result.zteLevel ?? "?"} · Correctness ${result.quality?.correctness ?? "?"}/10" }) { success } }`
            }),
          }).catch(() => {});
        }

        // ── Auto-create Linear triage ticket ─────────────────────
        const linearKey = settings.linearApiKey || process.env.LINEAR_API_KEY;
        if (linearKey) {
          try {
            const linearGql = async <T = Record<string, unknown>>(query: string, variables: Record<string, unknown> = {}): Promise<T> => {
              const res = await fetch("https://api.linear.app/graphql", {
                method: "POST",
                headers: { "Content-Type": "application/json", "Authorization": linearKey },
                body: JSON.stringify({ query, variables }),
              });
              const json = await res.json() as { data?: T; errors?: unknown[] };
              if (json.errors) throw new Error(`Linear API error: ${JSON.stringify(json.errors)}`);
              return json.data!;
            };

            // 1. Get all teams in workspace
            const teamsData = await linearGql<{ teams: { nodes: { id: string; name: string }[] } }>(
              `{ teams { nodes { id name } } }`
            );
            if (!teamsData.teams.nodes.length) throw new Error("No Linear teams found");

            // 2. Search for a project whose name matches the repo (case-insensitive partial match)
            const projectsData = await linearGql<{ projects: { nodes: { id: string; name: string; teams: { nodes: { id: string; name: string }[] } }[] } }>(`{
              projects(first: 50) {
                nodes { id name teams { nodes { id name } } }
              }
            }`);

            // Normalise repo name for matching: "Pi-Dev-Ops" → "pidevops"
            const normalise = (s: string) => s.toLowerCase().replace(/[-_\s]/g, "");
            const repoNorm = normalise(repo);
            const matchedProject = projectsData.projects.nodes.find(
              (p) => normalise(p.name).includes(repoNorm) || repoNorm.includes(normalise(p.name))
            ) ?? null;

            // 3. Pick team: prefer project's team, fall back to first workspace team
            const team = matchedProject?.teams.nodes[0] ?? teamsData.teams.nodes[0];
            const projectId = matchedProject?.id ?? null;

            // 4. Find a triage-like workflow state for this team
            const statesData = await linearGql<{ workflowStates: { nodes: { id: string; name: string }[] } }>(`{
              workflowStates(filter: { team: { id: { eq: "${team.id}" } } }) {
                nodes { id name }
              }
            }`);
            const triageState = statesData.workflowStates.nodes.find(
              (s) => /triage|backlog|todo|unstarted/i.test(s.name)
            ) ?? statesData.workflowStates.nodes[0] ?? null;

            // 5. Build rich findings description
            const date = new Date().toISOString().slice(0, 10);

            const qualitySection = result.quality ? [
              "## Quality Scores",
              "| Dimension | Score |",
              "|-----------|-------|",
              `| Completeness  | ${result.quality.completeness ?? "?"}/10 |`,
              `| Correctness   | ${result.quality.correctness ?? "?"}/10 |`,
              `| Code Quality  | ${result.quality.codeQuality ?? "?"}/10 |`,
              `| Documentation | ${result.quality.documentation ?? "?"}/10 |`,
            ].join("\n") : "";

            const leverageSection = result.leveragePoints?.length ? [
              "## Leverage Points (bottom 5 = highest ROI)",
              "| # | Area | Score |",
              "|---|------|-------|",
              ...[...result.leveragePoints]
                .sort((a, b) => a.score - b.score)
                .slice(0, 5)
                .map((lp) => `| ${lp.id} | ${lp.name} | ${lp.score}/5 |`),
            ].join("\n") : "";

            const sprintSection = result.sprints?.length ? [
              "## Sprint Plan",
              ...result.sprints.map((s) =>
                `### Sprint ${s.id}: ${s.name}\n` +
                s.items.map((i) => `- [${i.size}] [${i.priority}] ${i.title}`).join("\n")
              ),
            ].join("\n\n") : "";

            const riskSection = result.risks?.length
              ? `## Risks\n${result.risks.map((r) => `- ${r}`).join("\n")}`
              : "";

            const nextActionsSection = result.nextActions?.length
              ? `## Next Actions\n${result.nextActions.map((a, i) => `${i + 1}. ${a}`).join("\n")}`
              : "";

            const description = [
              `## Pi CEO Analysis — ${repo}`,
              "",
              `**Date:** ${date}  |  **Branch:** \`${branchName}\`  |  **ZTE:** Level ${result.zteLevel ?? "?"} (${result.zteScore ?? "?"}/60)`,
              prUrl ? `**PR:** ${prUrl}` : "",
              matchedProject ? `**Project:** ${matchedProject.name} _(auto-matched)_` : "_No matching Linear project found — created in default team_",
              "",
              result.executiveSummary ? `## Executive Summary\n${result.executiveSummary}` : "",
              qualitySection,
              leverageSection,
              riskSection,
              nextActionsSection,
              sprintSection,
            ].filter(Boolean).join("\n\n");

            // 6. Create the issue
            const issueInput: Record<string, unknown> = {
              title: `[Analysis] ${repo} — ${date}`,
              teamId: team.id,
              description,
              priority: 3, // Normal
            };
            if (triageState) issueInput.stateId = triageState.id;
            if (projectId) issueInput.projectId = projectId;

            const issueData = await linearGql<{ issueCreate: { success: boolean; issue: { id: string; identifier: string; title: string; url: string } } }>(`
              mutation CreateIssue($input: IssueCreateInput!) {
                issueCreate(input: $input) {
                  success
                  issue { id identifier title url }
                }
              }
            `, { input: issueInput });

            const issue = issueData.issueCreate.issue;
            line("success", `  Linear: ${issue.identifier} → ${issue.url}`);
            if (matchedProject) {
              line("success", `  Project: ${matchedProject.name}`);
            }
            // Emit structured event so dashboard can show clickable ticket link
            send("linear_ticket", { url: issue.url, identifier: issue.identifier, id: issue.id });
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
        clearTimeout(abortTimer);
        clearTimeout(budgetTimer);
        clearInterval(keepalive);
        // If budget or abort fired, send partial results + timeout event
        if (budgetFired || abortController.signal.aborted) {
          send("line", { type: "error", text: "⚠ Budget reached — partial results saved. Re-run to complete remaining phases.", ts: Date.now() / 1000 });
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
