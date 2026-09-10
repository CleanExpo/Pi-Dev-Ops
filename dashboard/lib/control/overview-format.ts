// Presentation helpers for the CEO Command Centre overview.
//
// Extracted from app/(main)/overview/page.tsx when that file was edited, per
// the CLAUDE.md file-length convention: the page is over the 300-line
// convention and grandfathered, so touching it means extracting rather than
// adding. Pure formatting — no state, no fetching, no React.

export function formatUptime(s: number): string {
  if (s < 60) return `${s}s`;
  if (s < 3600) return `${Math.floor(s / 60)}m`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m`;
  return `${Math.floor(s / 86400)}d ${Math.floor((s % 86400) / 3600)}h`;
}

export function repoShort(repo: string): string {
  try {
    const parts = new URL(repo).pathname.replace(/^\//, "").split("/");
    return parts.slice(0, 2).join("/");
  } catch {
    return repo.replace(/^https?:\/\/[^/]+\//, "").slice(0, 40);
  }
}

export function skillFromPhase(phase?: string): string {
  if (!phase) return "Initialising";
  const map: Record<string, string> = {
    clone: "Checkout",
    build: "Code Review",
    scan: "Security Scan",
    test: "QA",
    evaluate: "ZTE Eval",
    ship: "Deploy",
    push: "Git Push",
  };
  for (const [key, label] of Object.entries(map)) {
    if (phase.toLowerCase().includes(key)) return label;
  }
  return phase;
}

export function statusDot(status: string): string {
  if (["cloning", "building", "evaluating"].includes(status)) return "var(--accent)";
  if (status === "complete" || status === "done") return "var(--success)";
  if (status === "failed" || status === "error") return "var(--error)";
  return "var(--text-dim)";
}
