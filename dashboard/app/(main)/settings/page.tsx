// app/(main)/settings/page.tsx — Pi CEO settings: credentials, models, webhooks, cron
import { getSettings } from "@/lib/supabase/settings";
import SettingsForm from "@/components/SettingsForm";

export default async function SettingsPage() {
  const settings = await getSettings();

  const masked = {
    github_token:           settings.githubToken      ? "••••••••" : "",
    anthropic_api_key:      settings.anthropicApiKey  ? "••••••••" : "",
    analysis_model:         settings.analysisModel,
    webhook_secret:         settings.webhookSecret     ? "••••••••" : "",
    cron_repos:             settings.cronRepos.join("\n"),
    vercel_token:           settings.vercelToken       ? "••••••••" : "",
    telegram_bot_token:     settings.telegramBotToken  ? "••••••••" : "",
    telegram_chat_id:       settings.telegramChatId,
    linear_api_key:         settings.linearApiKey      ? "••••••••" : "",
    github_token_set:       !!settings.githubToken,
    anthropic_api_key_set:  !!settings.anthropicApiKey,
    webhook_secret_set:     !!settings.webhookSecret,
    vercel_token_set:       !!settings.vercelToken,
    telegram_bot_token_set: !!settings.telegramBotToken,
    linear_api_key_set:     !!settings.linearApiKey,
  };

  return (
    <div className="flex flex-col flex-1 overflow-y-auto" style={{ background: "var(--background)" }}>
      {/* Header */}
      <div className="px-4 sm:px-6 py-4 shrink-0" style={{ borderBottom: "1px solid var(--border)" }}>
        <h1 className="font-mono text-xs uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
          Configuration
        </h1>
        <p className="font-mono text-[10px] mt-1" style={{ color: "var(--text-dim)" }}>
          Credentials are stored in Supabase and never exposed to the browser.
        </p>
      </div>

      <SettingsForm initial={masked} />
    </div>
  );
}
