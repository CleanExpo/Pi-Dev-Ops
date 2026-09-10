// Client-side proposal validation and API error shaping for the spec pipeline.
//
// Extracted from components/control/SpecPipelinePanel.tsx when that file was
// edited, per the CLAUDE.md file-length convention: the panel is over the
// 300-line convention and grandfathered, so touching it means extracting
// rather than adding. Pure functions — no state, no fetching, no React.

const BARE_TYPE_TOKENS = new Set([
  "str", "int", "bool", "float", "dict", "list", "tuple", "none", "any",
]);

export function validateProposalClient(text: string): string | null {
  const proposal = text.trim();
  if (proposal.length < 10) {
    return "Proposal must be at least 10 characters";
  }
  if (BARE_TYPE_TOKENS.has(proposal.toLowerCase())) {
    return `Rejected before submit: bare type token "${proposal}"`;
  }
  if (/<[A-Za-z][\w\s-]*>/.test(proposal)) {
    return "Rejected before submit: angle-bracket placeholder detected";
  }
  return null;
}

export function formatApiError(data: unknown, fallback: string): string {
  if (!data || typeof data !== "object" || !("detail" in data)) return fallback;
  const detail = (data as { detail?: unknown }).detail;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: string }).msg);
        }
        return String(item);
      })
      .join("; ");
  }
  return fallback;
}
