// lib/claude.ts — Claude client: CLI mode (Max plan) or SDK mode (API key)

import { spawn } from "child_process";
import Anthropic from "@anthropic-ai/sdk";
import type { RepoFile } from "./github";

// ── Mode detection ────────────────────────────────────────────────────────────
// Priority order:
//   1. ANTHROPIC_API_KEY present → always use API mode (works on Vercel serverless)
//   2. ANALYSIS_MODE=api explicitly set → use API mode
//   3. Fallback → CLI mode (local Claude Max subscription via `claude -p`)
export function getAnalysisMode(): "cli" | "api" {
  if (process.env.ANTHROPIC_API_KEY?.trim()) return "api";
  if (process.env.ANALYSIS_MODE?.trim() === "api") return "api";
  return "cli";
}

export function makeClient(apiKey?: string): Anthropic | null {
  const key = (apiKey || process.env.ANTHROPIC_API_KEY ?? "").trim();
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

// ── CLI mode: spawns claude subprocess (uses Claude Max subscription) ──────────
function runPhaseCLI(
  model: string,
  prompt: string,
  context: string,
  onChunk: PhaseStreamCallback
): Promise<string> {
  return new Promise((resolve, reject) => {
    const fullPrompt = `${SYSTEM}\n\n${prompt}\n\n---\nREPO CONTEXT:\n${context}`;
    const args = ["-p", fullPrompt, "--model", model, "--output-format", "text"];

    const child = spawn("claude", args, {
      env: { ...process.env },
      shell: false,
    });

    let full = "";
    let stderr = "";

    child.stdout.on("data", (data: Buffer) => {
      const chunk = data.toString();
      full += chunk;
      onChunk(chunk);
    });

    child.stderr.on("data", (data: Buffer) => {
      stderr += data.toString();
    });

    child.on("close", (code) => {
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

// ── SDK mode: Anthropic SDK with ANTHROPIC_API_KEY ────────────────────────────
async function runPhaseSDK(
  client: Anthropic,
  model: string,
  prompt: string,
  context: string,
  onChunk: PhaseStreamCallback
): Promise<string> {
  const fullPrompt = `${prompt}\n\n---\nREPO CONTEXT:\n${context}`;

  const stream = await client.messages.stream({
    model,
    max_tokens: 4096,
    system: SYSTEM,
    messages: [{ role: "user", content: fullPrompt }],
  });

  let full = "";
  for await (const event of stream) {
    if (
      event.type === "content_block_delta" &&
      event.delta.type === "text_delta"
    ) {
      const chunk = event.delta.text;
      full += chunk;
      onChunk(chunk);
    }
  }
  return full;
}

// ── Public API ─────────────────────────────────────────────────────────────────
export async function runPhase(
  client: Anthropic | null,
  model: string,
  prompt: string,
  context: string,
  onChunk: PhaseStreamCallback
): Promise<string> {
  if (getAnalysisMode() === "cli") {
    return runPhaseCLI(model, prompt, context, onChunk);
  }
  if (!client) throw new Error("SDK client required for api mode");
  return runPhaseSDK(client, model, prompt, context, onChunk);
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
