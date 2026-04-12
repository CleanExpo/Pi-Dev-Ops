// lib/supabase/client.ts — browser Supabase client
// Uses @supabase/ssr for proper cookie-based auth in Next.js App Router.
// Falls back to the plain JS client if SSR package is unavailable.
"use client";
import { createBrowserClient as createSSRBrowserClient } from "@supabase/ssr";

export function createBrowserClient() {
  const url = process.env.NEXT_PUBLIC_SUPABASE_URL!;
  // Support both anon key formats
  const key = (process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
            ?? process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_DEFAULT_KEY)!;
  return createSSRBrowserClient(url, key);
}
