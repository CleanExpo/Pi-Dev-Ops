// lib/supabase/settings.ts — server-side helper to read app settings from Supabase
// Falls back to process.env so existing Vercel env vars keep working during migration

import { createServerClient } from "./server";

export interface AppSettings {
  githubToken:       string;
  anthropicApiKey:   string;
  analysisModel:     string;
  webhookSecret:     string;
  cronRepos:         string[];
  vercelToken:       string;
  telegramBotToken:  string;
  telegramChatId:    string;
  linearApiKey:      string;
}

const DEFAULTS: AppSettings = {
  githubToken:      process.env.GITHUB_TOKEN        ?? "",
  anthropicApiKey:  process.env.ANTHROPIC_API_KEY   ?? "",
  analysisModel:    process.env.ANALYSIS_MODEL      ?? "claude-sonnet-4-6",
  webhookSecret:    process.env.WEBHOOK_SECRET      ?? "",
  cronRepos:        [],
  vercelToken:      process.env.VERCEL_TOKEN        ?? "",
  telegramBotToken: process.env.TELEGRAM_BOT_TOKEN  ?? "",
  telegramChatId:   process.env.TELEGRAM_CHAT_ID    ?? "",
  linearApiKey:     process.env.LINEAR_API_KEY      ?? "",
};

const KEY_MAP: Record<string, keyof AppSettings> = {
  github_token:       "githubToken",
  anthropic_api_key:  "anthropicApiKey",
  analysis_model:     "analysisModel",
  webhook_secret:     "webhookSecret",
  cron_repos:         "cronRepos",
  vercel_token:       "vercelToken",
  telegram_bot_token: "telegramBotToken",
  telegram_chat_id:   "telegramChatId",
  linear_api_key:     "linearApiKey",
};

export async function getSettings(): Promise<AppSettings> {
  try {
    const supabase = createServerClient();
    const { data, error } = await supabase
      .from("settings")
      .select("key, value");

    if (error || !data) return DEFAULTS;

    const settings = { ...DEFAULTS };
    for (const row of data) {
      const field = KEY_MAP[row.key];
      if (!field || !row.value) continue;
      if (field === "cronRepos") {
        try { (settings as Record<string, unknown>)[field] = JSON.parse(row.value); } catch { /* keep default */ }
      } else {
        (settings as Record<string, unknown>)[field] = row.value;
      }
    }
    return settings;
  } catch {
    // Supabase not configured yet — fall back to env vars
    return DEFAULTS;
  }
}

export async function upsertSetting(key: string, value: string): Promise<void> {
  const supabase = createServerClient();
  await supabase
    .from("settings")
    .upsert({ key, value, updated_at: new Date().toISOString() }, { onConflict: "key" });
}
