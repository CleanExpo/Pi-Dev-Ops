// components/SettingsForm.tsx — client form for Pi CEO settings
"use client";

import { useState } from "react";

interface InitialSettings {
  github_token:           string;
  anthropic_api_key:      string;
  analysis_model:         string;
  webhook_secret:         string;
  cron_repos:             string;
  vercel_token:           string;
  telegram_bot_token:     string;
  telegram_chat_id:       string;
  linear_api_key:         string;
  github_token_set:       boolean;
  anthropic_api_key_set:  boolean;
  webhook_secret_set:     boolean;
  vercel_token_set:       boolean;
  telegram_bot_token_set: boolean;
  linear_api_key_set:     boolean;
}

const MODELS = [
  "claude-opus-4-5-20250514",
  "claude-sonnet-4-5-20250929",
  "claude-sonnet-4-6",
  "claude-haiku-4-5",
];

function Badge({ set }: { set: boolean }) {
  return (
    <span className="font-mono text-[10px] ml-2" style={{ color: set ? "#4ADE80" : "#F87171" }}>
      {set ? "● SET" : "○ NOT SET"}
    </span>
  );
}

function Field({ label, children, hint }: { label: React.ReactNode; children: React.ReactNode; hint?: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
        {label}
      </label>
      {children}
      {hint && <p className="font-mono text-[10px]" style={{ color: "var(--text-dim)" }}>{hint}</p>}
    </div>
  );
}

const inputBaseStyle: React.CSSProperties = {
  background: "var(--panel)",
  color: "var(--text)",
  border: "1px solid var(--border)",
  padding: "10px 12px",
  fontFamily: "monospace",
  fontSize: "13px",
  outline: "none",
  width: "100%",
  minHeight: "44px",
};

export default function SettingsForm({ initial }: { initial: InitialSettings }) {
  const [form, setForm] = useState({
    github_token:       "",
    anthropic_api_key:  "",
    analysis_model:     initial.analysis_model,
    webhook_secret:     "",
    cron_repos:         initial.cron_repos,
    vercel_token:       "",
    telegram_bot_token: "",
    telegram_chat_id:   initial.telegram_chat_id ?? "",
    linear_api_key:     "",
  });
  const [saving, setSaving] = useState(false);
  const [saved, setSaved]   = useState(false);
  const [error, setError]   = useState("");

  function set(key: string, value: string) {
    setForm((f) => ({ ...f, [key]: value }));
    setSaved(false);
  }

  async function save() {
    setSaving(true);
    setError("");
    try {
      // Only send fields that have values (blank = don't overwrite)
      const payload: Record<string, string> = {};
      if (form.github_token)       payload.github_token       = form.github_token;
      if (form.anthropic_api_key)  payload.anthropic_api_key  = form.anthropic_api_key;
      if (form.analysis_model)     payload.analysis_model     = form.analysis_model;
      if (form.webhook_secret)     payload.webhook_secret     = form.webhook_secret;
      if (form.cron_repos)         payload.cron_repos         = JSON.stringify(
        form.cron_repos.split("\n").map((r) => r.trim()).filter(Boolean)
      );
      if (form.vercel_token)       payload.vercel_token       = form.vercel_token;
      if (form.telegram_bot_token) payload.telegram_bot_token = form.telegram_bot_token;
      if (form.telegram_chat_id)   payload.telegram_chat_id   = form.telegram_chat_id;
      if (form.linear_api_key)     payload.linear_api_key     = form.linear_api_key;

      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setSaved(true);
      // Clear secret fields after save
      setForm((f) => ({ ...f, github_token: "", anthropic_api_key: "", webhook_secret: "", linear_api_key: "" }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-0 w-full max-w-2xl mx-auto px-4 sm:px-6 py-6">

      {/* ── Credentials ───────────────────────────────────────── */}
      <Section title="Credentials">
        <Field
          label={<>GitHub Token <Badge set={initial.github_token_set} /></>}
          hint="ghp_... — needs repo + workflow scopes"
        >
          <input
            type="password"
            value={form.github_token}
            onChange={(e) => set("github_token", e.target.value)}
            placeholder={initial.github_token_set ? "Leave blank to keep existing" : "ghp_..."}
            style={inputBaseStyle}
          />
        </Field>

        <Field
          label={<>Anthropic API Key <Badge set={initial.anthropic_api_key_set} /></>}
          hint="sk-ant-api03-... — used for all analysis phases"
        >
          <input
            type="password"
            value={form.anthropic_api_key}
            onChange={(e) => set("anthropic_api_key", e.target.value)}
            placeholder={initial.anthropic_api_key_set ? "Leave blank to keep existing" : "sk-ant-api03-..."}
            style={inputBaseStyle}
          />
        </Field>
      </Section>

      {/* ── Model Selection ───────────────────────────────────── */}
      <Section title="Model">
        <Field label="Analysis Model" hint="Used for all 8 analysis phases">
          <select
            value={form.analysis_model}
            onChange={(e) => set("analysis_model", e.target.value)}
            style={{ ...inputBaseStyle, cursor: "pointer" }}
          >
            {MODELS.map((m) => (
              <option key={m} value={m} style={{ background: "var(--panel)" }}>{m}</option>
            ))}
          </select>
        </Field>
      </Section>

      {/* ── Webhook ───────────────────────────────────────────── */}
      <Section title="GitHub Webhook">
        <Field
          label={<>Webhook Secret <Badge set={initial.webhook_secret_set} /></>}
          hint="Set this as the secret in your GitHub repo → Settings → Webhooks. Point the webhook at: https://dashboard-unite-group.vercel.app/api/webhook/github"
        >
          <input
            type="password"
            value={form.webhook_secret}
            onChange={(e) => set("webhook_secret", e.target.value)}
            placeholder={initial.webhook_secret_set ? "Leave blank to keep existing" : "your-webhook-secret"}
            style={inputBaseStyle}
          />
        </Field>
      </Section>

      {/* ── Vercel Integration ───────────────────────────────── */}
      <Section title="Vercel Integration">
        <Field
          label={<>Vercel Token <Badge set={initial.vercel_token_set} /></>}
          hint="Enable automatic preview deployments for analysis branches"
        >
          <input
            type="password"
            value={form.vercel_token}
            onChange={(e) => set("vercel_token", e.target.value)}
            placeholder={initial.vercel_token_set ? "Leave blank to keep existing" : "vercel_..."}
            style={inputBaseStyle}
          />
        </Field>
      </Section>

      {/* ── Linear Integration ───────────────────────────────── */}
      <Section title="Linear Integration">
        <Field
          label={<>Linear API Key <Badge set={initial.linear_api_key_set} /></>}
          hint="lin_api_... — used for two-way issue sync, triage tickets, and ship→Done transitions"
        >
          <input
            type="password"
            value={form.linear_api_key}
            onChange={(e) => set("linear_api_key", e.target.value)}
            placeholder={initial.linear_api_key_set ? "Leave blank to keep existing" : "lin_api_..."}
            style={inputBaseStyle}
          />
        </Field>
      </Section>

      {/* ── Telegram Notifications ────────────────────────────── */}
      <Section title="Telegram Notifications">
        <Field
          label={<>Bot Token <Badge set={initial.telegram_bot_token_set} /></>}
          hint="Get from @BotFather — format: 1234567890:AAFN..."
        >
          <input
            type="password"
            value={form.telegram_bot_token}
            onChange={(e) => set("telegram_bot_token", e.target.value)}
            placeholder={initial.telegram_bot_token_set ? "Leave blank to keep existing" : "1234567890:AAFN..."}
            style={inputBaseStyle}
          />
        </Field>
        <Field
          label="Chat ID"
          hint="Your Telegram user or group chat ID (e.g. -1001234567890)"
        >
          <input
            type="text"
            value={form.telegram_chat_id}
            onChange={(e) => set("telegram_chat_id", e.target.value)}
            placeholder="-1001234567890"
            style={inputBaseStyle}
          />
        </Field>
      </Section>

      {/* ── Cron / Scheduled Analysis ─────────────────────────── */}
      <Section title="Scheduled Analysis (Cron)">
        <Field
          label="Repos to analyse weekly"
          hint="One GitHub repo per line in owner/repo format. Analysed every Monday at 09:00 UTC."
        >
          <textarea
            value={form.cron_repos}
            onChange={(e) => set("cron_repos", e.target.value)}
            placeholder={"CleanExpo/Pi-Dev-Ops\nowner/another-repo"}
            rows={4}
            style={{ ...inputBaseStyle, resize: "vertical", minHeight: "88px" }}
          />
        </Field>
      </Section>

      {/* ── Save bar ─────────────────────────────────────────── */}
      {error && (
        <p className="font-mono text-[10px] mt-2" style={{ color: "#F87171" }}>✗ {error}</p>
      )}

      <div className="flex items-center gap-4 mt-6">
        <button
          onClick={() => void save()}
          disabled={saving}
          className="font-mono text-xs px-6 disabled:opacity-40 transition-opacity w-full sm:w-auto"
          style={{
            background: "var(--accent)",
            color: "#FFFFFF",
            fontWeight: 700,
            letterSpacing: "0.1em",
            minHeight: "44px",
          }}
        >
          {saving ? "SAVING…" : "SAVE SETTINGS"}
        </button>
        {saved && (
          <span className="font-mono text-[10px]" style={{ color: "#4ADE80" }}>✓ Saved</span>
        )}
      </div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="mb-8">
      <div className="mb-4 pb-2" style={{ borderBottom: "1px solid var(--border)" }}>
        <span className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "var(--accent)" }}>
          {title}
        </span>
      </div>
      <div className="flex flex-col gap-5">{children}</div>
    </div>
  );
}
