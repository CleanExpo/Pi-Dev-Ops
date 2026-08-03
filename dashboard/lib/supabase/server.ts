// lib/supabase/server.ts — server-side Supabase clients for API routes + Server Components
// Uses @supabase/ssr for cookie-aware auth; keeps legacy sync API for existing callers.
import { createServerClient as createSSRServerClient } from "@supabase/ssr";
import { createClient } from "@supabase/supabase-js";

/**
 * createServerClient() — service-role admin client (sync, backward-compatible).
 * Used by existing API routes (api/analyze, api/sessions, lib/supabase/settings, etc.).
 * Bypasses Row Level Security — never expose to browser.
 */
export function createServerClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL;
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY;
  if (!url || !key) {
    throw new Error(
      "Missing Supabase env vars: NEXT_PUBLIC_SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY"
    );
  }
  return createClient(url, key, { auth: { persistSession: false } });
}

/**
 * createAdminClient() — alias for createServerClient().
 * Preferred name in new code to clarify privilege level.
 */
export const createAdminClient = createServerClient;

