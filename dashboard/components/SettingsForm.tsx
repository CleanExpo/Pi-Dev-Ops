// components/SettingsForm.tsx — client form for Pi CEO settings
"use client";

import { useState } from "react";

interface InitialSettings {
  github_token:          string;
  anthropic_api_key:     string;
  analysis_model:        string;
  webhook_secret:        string;
  cron_repos:            string;
  github_token_set:      boolean;
  anthropic_api_key_set: boolean;
  webhook_secret_set:    boolean;
}

const MODELS = [
  "claude-opus-4-5-20250514",
  "claude-sonnet-4-5-20250929",
  "claude-sonnet-4-6",
  "claude-haiku-4-5",
];

function Badge({ set }: { set: boolean }) {
  return (
    <span className="font-mono text-[8px] ml-2" style={{ color: set ? "#4ADE80" : "#F87171" }}>
      {set ? "● SET" : "○ NOT SET"}
    </span>
  );
}

function Field({ label, children, hint }: { label: React.ReactNode; children: React.ReactNode; hint?: string }) {
  return (
    <div className="flex flex-col gap-1.5">
      <label className="font-mono text-[9px] uppercase tracking-widest" style={{ color: "#C8C5C0" }}>
        {label}
      </label>
      {children}
      {hint && <p className="font-mono text-[8px]" style={{ color: "#888480" }}>{hint}</p>}
    </div>
  );
}

const inputStyle = {
  background: "#141414",
  color: "#F0EDE8",
  border: "1px solid #3A3632",
  padding: "6px 10px",
  fontFamily: "monospace",
  fontSize: "11px",
  outline: "none",
  width: "100%",
};

export default function SettingsForm({ initial }: { initial: InitialSettings }) {
  const [form, setForm] = useState({
    github_token:      "",
    anthropic_api_key: "",
    analysis_model:    initial.analysis_model,
    webhook_secret:    "",
    cron_repos:        initial.cron_repos,
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
      if (form.github_token)      payload.github_token      = form.github_token;
      if (form.anthropic_api_key) payload.anthropic_api_key = form.anthropic_api_key;
      if (form.analysis_model)    payload.analysis_model    = form.analysis_model;
      if (form.webhook_secret)    payload.webhook_secret    = form.webhook_secret;
      if (form.cron_repos)        payload.cron_repos        = JSON.stringify(
        form.cron_repos.split("\n").map((r) => r.trim()).filter(Boolean)
      );

      const res = await fetch("/api/settings", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setSaved(true);
      // Clear secret fields after save
      setForm((f) => ({ ...f, github_token: "", anthropic_api_key: "", webhook_secret: "" }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="flex flex-col gap-0 max-w-2xl mx-auto w-full px-6 py-6">

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
            style={inputStyle}
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
            style={inputStyle}
          />
        </Field>
      </Section>

      {/* ── Model Selection ───────────────────────────────────── */}
      <Section title="Model">
        <Field label="Analysis Model" hint="Used for all 8 analysis phases">
          <select
            value={form.analysis_model}
            onChange={(e) => set("analysis_model", e.target.value)}
            style={{ ...inputStyle, cursor: "pointer" }}
          >
            {MODELS.map((m) => (
              <option key={m} value={m} style={{ background: "#141414" }}>{m}</option>
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
            style={inputStyle}
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
            style={{ ...inputStyle, resize: "vertical" }}
          />
        </Field>
      </Section>

      {/* ── Save bar ─────────────────────────────────────────── */}
      {error && (
        <p className="font-mono text-[10px] mt-2" style={{ color: "#F87171" }}>✗ {error}</p>
      )}

      <div className="flex items-center gap-4 mt-6">
        <button
          onClick={save}
          disabled={saving}
          className="font-mono text-[11px] px-6 py-2 disabled:opacity-40 transition-opacity"
          style={{ background: "#E8751A", color: "#FFFFFF", fontWeight: 700, letterSpacing: "0.1em" }}
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
      <div className="mb-4 pb-2" style={{ borderBottom: "1px solid #2A2727" }}>
        <span className="font-mono text-[9px] uppercase tracking-widest" style={{ color: "#E8751A" }}>
          {title}
        </span>
      </div>
      <div className="flex flex-col gap-5">{children}</div>
    </div>
  );
}

