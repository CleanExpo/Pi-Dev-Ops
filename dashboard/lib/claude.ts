// lib/claude.ts — Claude client: CLI mode (Max plan) or SDK mode (API key)

import { spawn } from "child_process";
import Anthropic from "@anthropic-ai/sdk";
import type { RepoFile } from "./github";

// ── Mode detection ────────────────────────────────────────────────────────────
// Priority order:
//   1. ANALYSIS_MODE=cli explicitly set → always CLI mode (Claude Max subscription)
//   2. ANALYSIS_MODE=api explicitly set → always API mode
//   3. ANTHROPIC_API_KEY present → API mode (Vercel serverless fallback)
//   4. Fallback → CLI mode (local Claude Max subscription via `claude -p`)
//
// To use Claude Max plan on Vercel:
//   1. Run `claude setup-token` locally → copies a subscription token to clipboard
//   2. Set ANTHROPIC_API_KEY=<token> in Vercel env (replaces pay-per-use API key)
//   3. Set ANALYSIS_MODE=api in Vercel env (explicit, survives future key changes)
export function getAnalysisMode(): "cli" | "api" {
  const explicit = process.env.ANALYSIS_MODE?.trim();
  if (explicit === "cli") return "cli";
  if (explicit === "api") return "api";
  if (process.env.ANTHROPIC_API_KEY?.trim()) return "api";
  return "cli";
}

export function makeClient(apiKey?: string): Anthropic | null {
  const key = (apiKey || (process.env.ANTHROPIC_API_KEY ?? "")).trim();
  if (!key) return null;
  return new Anthropic({ apiKey: key });
}

// ── Context builder ────────────────────────────────────────────────────────────
export function buildContext(files: RepoFile[]): string {
  return files.map((f) => `=== FILE: ${f.path} ===\n${f.content}\n`).join("\n");
}

// ── System prompt ─────────────────────────────────────────────────────────────
export const SYSTEM = `You are Pi CEO — a senior engineering team compressed into one AI system.
You analyse GitHub repositories through the TAO (Tiered Agent Orchestrator) framework.
Skills: tier-architect, tier-orchestrator, tier-worker, tier-evaluator,
context-compressor, agentic-review, zte-maturity, leverage-audit, piter-framework, ceo-mode.

Rules:
- Be specific. Cite actual file names and line numbers.
- Output structured data in JSON when the phase requires it.
- Be direct. No filler. Every word earns its place.`;

export type PhaseStreamCallback = (chunk: string) => void;

// ── RA-928: <think> prefill helpers ───────────────────────────────────────────
// Intelligence-heavy phases (3, 5, 6, 7) inject an assistant-turn prefill so
// Claude reasons in a scratchpad before emitting JSON output.  The prefill
// begins the assistant turn; the model continues from that point, producing
// reasoning content then </think> then the answer.
//
// Because the API returns only the CONTINUATION (not the prefill text itself),
// the streamed output looks like:   <reasoning...>\n</think>\n{...json...}
// stripThinkBlock() removes everything up to and including </think>.

/** Phases that receive a <think> prefill to force scratchpad reasoning. */
export const THINK_PHASE_IDS = new Set([3, 5, 6, 7]);

/**
 * RA-932: Cold-start seeds for think-prefill phases.
 * Prepended to the prompt before extended reasoning activates so the model
 * self-organises into problem-decompose → attempt → verify rather than freeform rambling.
 * Seeding is active when THINK_SEED_ENABLED env var is "1".
 */
export const THINK_SEEDS: Partial<Record<number, string>> = {
  3: "Before analyzing: what patterns or anti-patterns should I look for in this codebase? List them, then analyze.",
  5: "Before scoring: list every requirement from the brief one by one, check each against the diff, then score.",
  6: "Before recommending: categorize improvements by impact (high/medium/low) and effort, then prioritize.",
  7: "Before writing: outline what sections this analysis needs to answer for a technical reader, then write.",
};

/** RA-932: Whether cold-start seeding is active (set THINK_SEED_ENABLED=1). */
export const THINK_SEED_ENABLED =
  typeof process !== "undefined" && process.env.THINK_SEED_ENABLED === "1";

/**
 * Strip the think-block reasoning from a prefilled response before JSON parsing.
 *
 * Handles two forms:
 *   1. Prefill continuation — output starts with reasoning, ends with </think> then answer.
 *   2. Full block — output contains a complete <think>…</think> block.
 */
export function stripThinkBlock(output: string): string {
  // Form 1: prefill continuation — find the first </think> and take everything after
  const closeIdx = output.indexOf("</think>");
  if (closeIdx !== -1) {
    return output.slice(closeIdx + "</think>".length).trim();
  }
  // Form 2: full <think>…</think> block
  return output.replace(/<think>[\s\S]*?<\/think>/g, "").trim();
}

// ── CLI mode: spawns claude subprocess (uses Claude Max subscription) ──────────
function runPhaseCLI(
  model: string,
  prompt: string,
  context: string,
  onChunk: PhaseStreamCallback,
  signal?: AbortSignal,
): Promise<string> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) { reject(new Error("Phase aborted before start")); return; }

    const fullPrompt = `${SYSTEM}\n\n${prompt}\n\n---\nREPO CONTEXT:\n${context}`;
    const args = ["-p", fullPrompt, "--model", model, "--output-format", "text"];

    const child = spawn("claude", args, {
      env: { ...process.env },
      shell: false,
    });

    let full = "";
    let stderr = "";

    // Kill subprocess if abort signal fires
    signal?.addEventListener("abort", () => {
      child.kill("SIGTERM");
      reject(new Error("Phase aborted: budget limit reached"));
    }, { once: true });

    child.stdout.on("data", (data: Buffer) => {
      const chunk = data.toString();
      full += chunk;
      onChunk(chunk);
    });

    child.stderr.on("data", (data: Buffer) => {
      stderr += data.toString();
    });

    child.on("close", (code) => {
      if (signal?.aborted) return; // already rejected
      if (code !== 0) {
        reject(new Error(`claude CLI exited with code ${code}: ${stderr.slice(0, 300)}`));
      } else {
        resolve(full);
      }
    });

    child.on("error", (err) => {
      reject(new Error(`Failed to spawn claude CLI: ${err.message}. Is Claude Code installed? Run: npm install -g @anthropic-ai/claude-code`));
    });
  });
}

// ── Transient error detection ─────────────────────────────────────────────────
function isTransient(err: unknown): boolean {
  if (!(err instanceof Error)) return false;
  const msg = err.message.toLowerCase();
  // Anthropic SDK error types + network-level transients
  return (
    msg.includes("overloaded") ||
    msg.includes("rate_limit") ||
    msg.includes("529") ||
    msg.includes("503") ||
    msg.includes("econnreset") ||
    msg.includes("etimedout") ||
    msg.includes("network")
  );
}

// ── SDK mode: Anthropic SDK with ANTHROPIC_API_KEY ────────────────────────────
async function runPhaseSDK(
  client: Anthropic,
  model: string,
  prompt: string,
  context: string,
  onChunk: PhaseStreamCallback,
  signal?: AbortSignal,
  maxTokens = 4096,
  useThinkPrefill = false,
  thinkSeed?: string,
): Promise<string> {
  if (signal?.aborted) throw new Error("Phase aborted before start");

  // RA-932: prepend think seed when enabled (cold-start seeding for structured reasoning)
  const seededPrompt = (thinkSeed && THINK_SEED_ENABLED) ? `${thinkSeed}\n\n${prompt}` : prompt;
  const fullPrompt = `${seededPrompt}\n\n---\nREPO CONTEXT:\n${context}`;

  // RA-928: build message array — add assistant prefill for intelligence phases
  type Message = { role: "user" | "assistant"; content: string };
  const messages: Message[] = [{ role: "user", content: fullPrompt }];
  if (useThinkPrefill) {
    // Prefill the assistant turn to force scratchpad reasoning before JSON output.
    // The model continues from this point; we strip the think block before parsing.
    messages.push({ role: "assistant", content: "<think>\nLet me analyze this systematically:\n" });
  }

  const attempt = async (): Promise<string> => {
    const stream = await client.messages.stream(
      {
        model,
        max_tokens: maxTokens,
        system: SYSTEM,
        messages,
      },
      { signal },
    );

    let full = "";
    for await (const event of stream) {
      if (signal?.aborted) throw new Error("Phase aborted: budget limit reached");
      if (
        event.type === "content_block_delta" &&
        event.delta.type === "text_delta"
      ) {
        const chunk = event.delta.text;
        full += chunk;
        onChunk(chunk);
      }
    }
    // Strip the think block before returning so callers receive clean JSON
    return useThinkPrefill ? stripThinkBlock(full) : full;
  };

  // One retry on transient failures (overloaded, rate-limited, network reset).
  // Hard abort signals are never retried — respect the budget timer.
  try {
    return await attempt();
  } catch (err) {
    if (signal?.aborted || !isTransient(err)) throw err;
    await new Promise((res) => setTimeout(res, 10_000)); // 10s backoff
    if (signal?.aborted) throw new Error("Phase aborted during retry backoff");
    return attempt();
  }
}

// ── Public API ─────────────────────────────────────────────────────────────────
export async function runPhase(
  client: Anthropic | null,
  model: string,
  prompt: string,
  context: string,
  onChunk: PhaseStreamCallback,
  signal?: AbortSignal,
  maxTokens = 4096,
  useThinkPrefill = false,
  thinkSeed?: string,
): Promise<string> {
  if (getAnalysisMode() === "cli") {
    // CLI mode spawns claude subprocess — assistant prefill not supported there.
    // Run normally; the reasoning benefit is API-only.
    return runPhaseCLI(model, prompt, context, onChunk, signal);
  }
  if (!client) throw new Error("SDK client required for api mode");
  return runPhaseSDK(client, model, prompt, context, onChunk, signal, maxTokens, useThinkPrefill, thinkSeed);
}

// ── Chat (always uses SDK for responsiveness) ─────────────────────────────────
export async function chatWithClaude(
  client: Anthropic | null,
  model: string,
  messages: Array<{ role: "user" | "assistant"; content: string }>,
  systemContext: string
): Promise<string> {
  // Chat prefers SDK for speed; falls back to CLI if no API key
  if (client) {
    const response = await client.messages.create({
      model,
      max_tokens: 2048,
      system: `${SYSTEM}\n\nCurrent session context:\n${systemContext}`,
      messages,
    });
    const block = response.content[0];
    return block.type === "text" ? block.text : "";
  }

  // CLI fallback for chat
  const lastMsg = messages[messages.length - 1];
  return runPhaseCLI(model, lastMsg.content, systemContext, () => {});
}
