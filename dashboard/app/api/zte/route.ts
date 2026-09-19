// app/api/zte/route.ts — ZTE v2 score + SDK mode badge (RA-1092)
// Prefers RAILWAY_URL backend; falls back to parsing .harness/leverage-audit.md
// if present; otherwise returns a sensible default.

import { readFile } from "node:fs/promises";
import { piCeoFetch } from "@/lib/pi-ceo-session";

export const dynamic = "force-dynamic";
export const runtime = "nodejs";

interface ZteResponse {
  score: number | null;
  model: string | null;
  model_id: string | null;
  sdk_mode: boolean | null;
  source: "backend" | "harness" | "unavailable";
}

async function fromBackend(): Promise<Partial<ZteResponse> | null> {
  const base = process.env.RAILWAY_URL ?? process.env.PI_CEO_URL;
  if (!base) return null;

  try {
    // Was `Authorization: Bearer ${PI_CEO_PASSWORD}` — a raw password where upstream requires
    // a signed session token, so this never authenticated and the route silently served
    // source:"default" as though it were a reading. See lib/pi-ceo-session.ts.
    const res = await piCeoFetch("/api/zte/score", {}, 5_000);
    if (!res || !res.ok) return null;
    const raw = (await res.json()) as Record<string, unknown>;
    if (!raw || typeof raw !== "object" || Array.isArray(raw)) return null;
    const score = raw.score ?? raw.zte_score;
    if (typeof score !== "number" || !Number.isFinite(score) || score < 0 || score > 100) return null;
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
  const backend = await fromBackend();
  if (backend?.score !== undefined) {
    return Response.json(
      {
        score: backend.score,
        model: null,
        model_id: null,
        sdk_mode: null,
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
        model: null,
        model_id: null,
        sdk_mode: null,
        source: "harness",
      } satisfies ZteResponse,
      { headers: { "Cache-Control": "no-store" } },
    );
  }

  return Response.json(
    {
      score: null,
      model: null,
      model_id: null,
      sdk_mode: null,
      source: "unavailable",
    } satisfies ZteResponse,
    { headers: { "Cache-Control": "no-store" } },
  );
}
