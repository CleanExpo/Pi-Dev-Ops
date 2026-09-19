import type { Octokit } from "@octokit/rest";
import type { AnalysisResult } from "@/lib/types";

/** Fetch a single file from GitHub. Returns empty string if not found. */
export async function fetchGitHubFile(
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

export async function sendTelegramMessage(botToken: string, chatId: string, text: string): Promise<void> {
  try {
    await fetch(`https://api.telegram.org/bot${botToken}/sendMessage`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ chat_id: chatId, text, parse_mode: "Markdown" }),
    });
  } catch { /* non-critical */ }
}

export async function persistRequired(query: PromiseLike<{ error: unknown }>, receipt: string): Promise<void> {
  const result = await query;
  if (result.error) throw new Error(`Could not save ${receipt}`);
}

export function buildSpecMd(r: Partial<AnalysisResult>, repo: string, branch: string): string {
  return `# Pi CEO Analysis — ${repo}\n\nBranch: \`${branch}\`\nDate: ${new Date().toISOString().slice(0, 10)}\n\n## Tech Stack\n${(r.techStack ?? []).join(", ")}\n\n## Quality Scores\n| Dimension | Score |\n|-----------|-------|\n| Completeness | ${r.quality?.completeness ?? "?"}/10 |\n| Correctness | ${r.quality?.correctness ?? "?"}/10 |\n| Code Quality | ${r.quality?.codeQuality ?? "?"}/10 |\n| Documentation | ${r.quality?.documentation ?? "?"}/10 |\n\n## ZTE Maturity\nLevel ${r.zteLevel ?? "?"} — Score: ${r.zteScore ?? "?"}/60\n\n## Sprint Plan\n${(r.sprints ?? []).map((s) => `### Sprint ${s.id}: ${s.name} (${s.duration})\n${s.items.map((i) => `- [${i.size}] ${i.title}`).join("\n")}`).join("\n\n")}\n`;
}

export function buildExecSummary(r: Partial<AnalysisResult>): string {
  return `# Executive Summary\n\n${r.executiveSummary ?? ""}\n\n## Strengths\n${(r.strengths ?? []).map((s) => `- ${s}`).join("\n")}\n\n## Weaknesses\n${(r.weaknesses ?? []).map((s) => `- ${s}`).join("\n")}\n\n## Next Actions\n${(r.nextActions ?? []).map((a, i) => `${i + 1}. ${a}`).join("\n")}\n`;
}
