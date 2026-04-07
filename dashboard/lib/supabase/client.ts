// lib/supabase/client.ts — anon client for browser components (obeys RLS)
import { createClient, SupabaseClient } from "@supabase/supabase-js";

let _client: SupabaseClient | null = null;

export function createBrowserClient(): SupabaseClient {
  if (!_client) {
    const url = process.env.NEXT_PUBLIC_SUPABASE_URL!;
    // Support both old anon key and new publishable key formats
    const key = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY
             ?? process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_DEFAULT_KEY!;
    _client = createClient(url, key);
  }
  return _client;
}
