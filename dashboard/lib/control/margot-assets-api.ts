// Fetch + formatting helpers for the Margot assets panel.
//
// Extracted from components/control/MargotAssetsPanel.tsx when that file was
// edited, per the CLAUDE.md file-length convention: the panel is over the
// 300-line convention and grandfathered, so touching it means extracting
// rather than adding.

import { fetchProxy } from "@/lib/pi-ceo-fetch";

export function fmtAge(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  if (Number.isNaN(ms)) return "?";
  if (ms < 60_000) return `${Math.floor(ms / 1_000)}s ago`;
  if (ms < 3_600_000) return `${Math.floor(ms / 60_000)}m ago`;
  return `${Math.floor(ms / 3_600_000)}h ago`;
}

/**
 * GET a Margot assets endpoint, always returning an object — the panel renders
 * `error` when present rather than branching on a thrown exception.
 *
 * A proxy fallback used to arrive here as an ordinary 200 body and be rendered
 * as asset data. It now lands in the error branch. See lib/pi-ceo-fetch.ts.
 */
export async function getJSON<T>(path: string): Promise<T> {
  const r = await fetchProxy<T & { error?: string; detail?: string }>(
    path, { credentials: "include", cache: "no-store" },
  );
  if (!r.ok) {
    const error = r.reason === "unreachable"
      ? "Pi-CEO backend unreachable"
      : `HTTP ${r.upstreamStatus ?? "error"}`;
    return { error } as T;
  }
  const body = r.data;
  return (body.error ? body : { ...body, error: body.detail }) as T;
}
