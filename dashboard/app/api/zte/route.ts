// app/api/zte/route.ts — ZTE v2 score + SDK mode badge (RA-1092)
// Prefers RAILWAY_URL backend; falls back to parsing .harness/leverage-audit.md
// if present; otherwise returns a sensible default.

import { readFile } from "node:fs/promises";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

interface ZteResponse {
  score: number;
  model: string;
  model_id: string;
  sdk_mode: boolean;
  source: "backend" | "harness" | "default";
}

const DEFAULT_MODEL = "Opus 4.7";
const DEFAULT_MODEL_ID = "claude-opus-4-7";

async function fromBackend(): Promise<Partial<ZteResponse> | null> {
  const base = process.env.RAILWAY_URL ?? process.env.PI_CEO_URL;
  if (!base) return null;

  const url = `${base.replace(/\/$/, "")}/api/zte/score`;
  try {
    const res = await fetch(url, {
      signal: AbortSignal.timeout(5_000),
      headers: process.env.PI_CEO_PASSWORD
        ? { Authorization: `Bearer ${process.env.PI_CEO_PASSWORD}` }
        : {},
    });
    if (!res.ok) return null;
    const raw = (await res.json()) as Record<string, unknown>;
    const score = Number(raw.score ?? raw.zte_score ?? NaN);
    if (!Number.isFinite(score)) return null;
    return { score };
  } catch {
    return null;
  }
}

async function fromHarness(): Promise<number | null> {
  // Only consult filesystem when an explicit absolute path is provided via env.
  // This avoids dragging the whole project into the NFT trace on Vercel.
  const explicit = process.env.HARNESS_AUDIT_PATH;
  if (!explicit) return null;
  const candidates = [explicit];
  for (const p of candidates) {
    try {
      const text = await readFile(p, "utf-8");
      const m = text.match(/(?:ZTE[^0-9]{0,20}|score[^0-9]{0,10})(\d{1,3})\s*\/\s*100/i);
      if (m) {
        const n = Number(m[1]);
        if (Number.isFinite(n) && n >= 0 && n <= 100) return n;
      }
    } catch {
      // file not present — try next
    }
  }
  return null;
}

export async function GET(): Promise<Response> {
  const sdkMode = process.env.TAO_USE_AGENT_SDK === "1";

  const backend = await fromBackend();
  if (backend?.score !== undefined) {
    return Response.json(
      {
        score: backend.score,
        model: DEFAULT_MODEL,
        model_id: DEFAULT_MODEL_ID,
        sdk_mode: sdkMode,
        source: "backend",
      } satisfies ZteResponse,
      { headers: { "Cache-Control": "no-store" } },
    );
  }

  const harness = await fromHarness();
  if (harness !== null) {
    return Response.json(
      {
        score: harness,
        model: DEFAULT_MODEL,
        model_id: DEFAULT_MODEL_ID,
        sdk_mode: sdkMode,
        source: "harness",
      } satisfies ZteResponse,
      { headers: { "Cache-Control": "no-store" } },
    );
  }

  return Response.json(
    {
      score: 85,
      model: DEFAULT_MODEL,
      model_id: DEFAULT_MODEL_ID,
      sdk_mode: sdkMode,
      source: "default",
    } satisfies ZteResponse,
    { headers: { "Cache-Control": "no-store" } },
  );
}
