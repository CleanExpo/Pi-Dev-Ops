// app/(main)/settings/page.tsx — Pi CEO settings: credentials, models, webhooks, cron
import { getSettings } from "@/lib/supabase/settings";
import SettingsForm from "@/components/SettingsForm";

export default async function SettingsPage() {
  const settings = await getSettings();

  const masked = {
    github_token:      settings.githubToken      ? "••••••••" : "",
    anthropic_api_key: settings.anthropicApiKey  ? "••••••••" : "",
    analysis_model:    settings.analysisModel,
    webhook_secret:    settings.webhookSecret     ? "••••••••" : "",
    cron_repos:        settings.cronRepos.join("\n"),
    github_token_set:      !!settings.githubToken,
    anthropic_api_key_set: !!settings.anthropicApiKey,
    webhook_secret_set:    !!settings.webhookSecret,
  };

  return (
    <div className="flex flex-col flex-1 overflow-y-auto" style={{ background: "#0A0A0A" }}>
      {/* Header */}
      <div className="px-6 py-4 shrink-0" style={{ borderBottom: "1px solid #2A2727" }}>
        <h1 className="font-mono text-[11px] uppercase tracking-widest" style={{ color: "#C8C5C0" }}>
          Configuration
        </h1>
        <p className="font-mono text-[10px] mt-1" style={{ color: "#888480" }}>
          Credentials are stored in Supabase and never exposed to the browser.
        </p>
      </div>

      <SettingsForm initial={masked} />
    </div>
  );
}
