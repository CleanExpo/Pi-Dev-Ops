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

/**
 * createCookieServerClient() — cookie-aware SSR client for Server Components
 * and API Routes that need to read/write Supabase auth state from request cookies.
 * Uses @supabase/ssr — call this in new Server Components, not in existing API routes.
 */
export async function createCookieServerClient() {
  const { cookies } = await import("next/headers");
  const cookieStore = await cookies();
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL!;
  const key = (process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
            ?? process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_DEFAULT_KEY)!;

  return createSSRServerClient(url, key, {
    cookies: {
      getAll() {
        return cookieStore.getAll();
      },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options)
          );
        } catch {
          // Called from Server Component — cookies can't be mutated here.
          // Middleware handles token refresh.
        }
      },
    },
  });
}
