// lib/claude.ts — Anthropic SDK wrapper for streaming phase analysis

import Anthropic from "@anthropic-ai/sdk";
import type { RepoFile } from "./github";

export function makeClient() {
  const key = process.env.ANTHROPIC_API_KEY;
  if (!key) throw new Error("ANTHROPIC_API_KEY not set");
  return new Anthropic({ apiKey: key });
}

// Build compressed repo context string for injection into phase prompts
export function buildContext(files: RepoFile[]): string {
  const sections = files.map((f) =>
    `=== FILE: ${f.path} ===\n${f.content}\n`
  );
  return sections.join("\n");
}

const SYSTEM = `You are Pi CEO — a senior engineering team compressed into one AI system.
You analyse GitHub repositories through the TAO (Tiered Agent Orchestrator) framework.
You use the following skills: tier-architect, tier-orchestrator, tier-worker, tier-evaluator,
context-compressor, agentic-review, zte-maturity, leverage-audit, piter-framework, ceo-mode.

Rules:
- Be specific. Cite actual file names and line numbers.
- Output structured data in JSON when the phase requires it.
- Be direct. No filler. Every word earns its place.`;

export type PhaseStreamCallback = (chunk: string) => void;

export async function runPhase(
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

export async function chatWithClaude(
  client: Anthropic,
  model: string,
  messages: Array<{ role: "user" | "assistant"; content: string }>,
  systemContext: string
): Promise<string> {
  const response = await client.messages.create({
    model,
    max_tokens: 2048,
    system: `${SYSTEM}\n\nCurrent session context:\n${systemContext}`,
    messages,
  });

  const block = response.content[0];
  return block.type === "text" ? block.text : "";
}
