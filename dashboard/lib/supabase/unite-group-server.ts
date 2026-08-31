// lib/supabase/unite-group-server.ts — service-role client for the Unite-Group
// production Supabase project (lksfwktwtmyznckodsau).
//
// This is a DIFFERENT Supabase project from the one lib/supabase/server.ts reaches
// (zbryrmxmgfmslqzizsto, Pi CEO's own project). wiki_pages lives in Unite-Group
// prod, not in Pi CEO's project — docs/PLAN-option-b-migration-scope-2026-08-01.md
// assumed it was "already reachable from Pi-Dev-Ops", but no client anywhere in
// this app ever pointed at it. The wiki-graph route and page were calling
// lib/supabase/server.ts's Pi-CEO-scoped client instead, so every wiki_pages read
// hit the wrong project's PostgREST endpoint and got a 404 back — surfaced to
// callers as a 500 with no indication the project itself was wrong.
//
// Bypasses Row Level Security; never expose to the browser.
import { createClient } from "@supabase/supabase-js";

/** The env vars this client requires. One list, so the check and the error cannot drift. */
const REQUIRED_ENV = [
  "SUPABASE_UNITE_GROUP_URL",
  "SUPABASE_UNITE_GROUP_SERVICE_KEY",
] as const;

/**
 * Which of this client's env vars are unset, by NAME — never by value.
 *
 * Exists so a caller can tell "this deployment was never configured" apart from
 * "the query failed" WITHOUT parsing an exception message. Today those are the
 * same opaque 500: the wiki-graph route's catch-all deliberately swallows every
 * message because a driver error can carry a connection string, so the one
 * failure an operator can actually act on is indistinguishable from the ones
 * they cannot.
 *
 * Variable NAMES are safe to return and safe to put in a response body — they
 * are already in this file, in the deploy config, and in
 * docs/runbooks/fleet-operations.md. Values are never read here, only tested for
 * presence, so nothing this returns can carry a credential.
 */
export function missingUniteGroupEnv(): string[] {
  return REQUIRED_ENV.filter((name) => !process.env[name]);
}

export function createUniteGroupServerClient() {
  const missing = missingUniteGroupEnv();
  if (missing.length > 0) {
    // Names only, and only the ones actually absent.
    throw new Error(`Missing Supabase env vars: ${missing.join(" and ")}`);
  }
  return createClient(
    process.env.SUPABASE_UNITE_GROUP_URL as string,
    process.env.SUPABASE_UNITE_GROUP_SERVICE_KEY as string,
    { auth: { persistSession: false } }
  );
}
