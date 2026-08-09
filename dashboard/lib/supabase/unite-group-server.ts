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

export function createUniteGroupServerClient() {
  const url = process.env.SUPABASE_UNITE_GROUP_URL;
  const key = process.env.SUPABASE_UNITE_GROUP_SERVICE_KEY;
  if (!url || !key) {
    throw new Error(
      "Missing Supabase env vars: SUPABASE_UNITE_GROUP_URL and SUPABASE_UNITE_GROUP_SERVICE_KEY"
    );
  }
  return createClient(url, key, { auth: { persistSession: false } });
}
