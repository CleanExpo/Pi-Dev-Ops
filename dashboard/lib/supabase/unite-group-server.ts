// lib/supabase/unite-group-server.ts — service-role client for the Unite-Group
// production Supabase project (lksfwktwtmyznckodsau).
//
// This is a DIFFERENT Supabase project from the one lib/supabase/server.ts reaches
// (zbryrmxmgfmslqzizsto, Pi CEO's own project). wiki_pages lives in Unite-Group
// prod, not in Pi CEO's project — docs/PLAN-option-b-migration-scope-2026-08-01.md
// assumed it was "already reachable from this app", but no client anywhere in
// this app ever pointed at it. The wiki-graph route and page were calling
// lib/supabase/server.ts's Pi-CEO-scoped client instead, so every wiki_pages read
// hit the wrong project's PostgREST endpoint and got a 404 back — surfaced to
// callers as a 500 with no indication the project itself was wrong.
//
// Bypasses Row Level Security; never expose to the browser.
import { createClient } from "@supabase/supabase-js";

/** Canonical names plus the Railway aliases already set in production. */
const URL_KEYS = ["SUPABASE_UNITE_GROUP_URL", "UGO_SUPABASE_URL"] as const;
const KEY_KEYS = [
  "SUPABASE_UNITE_GROUP_SERVICE_KEY",
  "UGO_SUPABASE_SERVICE_KEY",
] as const;

/** Same project the wiki writer (`scripts/sync_wiki_to_supabase.py`) already hardcodes. */
export const UNITE_GROUP_SUPABASE_URL =
  "https://lksfwktwtmyznckodsau.supabase.co";

function firstEnv(names: readonly string[]): string | undefined {
  for (const name of names) {
    const value = process.env[name]?.trim();
    if (value) return value;
  }
  return undefined;
}

/**
 * Which credential the client still needs, by NAME — never by value.
 *
 * The URL has a public default (the writer and this reader share one project),
 * so only a missing service-role key is an unconfigured deployment. Names are
 * safe to return; values are never read here.
 */
export function missingUniteGroupEnv(): string[] {
  return firstEnv(KEY_KEYS) ? [] : ["SUPABASE_UNITE_GROUP_SERVICE_KEY"];
}

export function uniteGroupUrl(): string {
  return firstEnv(URL_KEYS) ?? UNITE_GROUP_SUPABASE_URL;
}

export function createUniteGroupServerClient() {
  const missing = missingUniteGroupEnv();
  if (missing.length > 0) {
    throw new Error(`Missing Supabase env vars: ${missing.join(" and ")}`);
  }
  return createClient(uniteGroupUrl(), firstEnv(KEY_KEYS) as string, {
    auth: { persistSession: false },
  });
}
