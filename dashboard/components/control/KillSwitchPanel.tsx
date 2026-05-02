// components/control/KillSwitchPanel.tsx — RA-1839
//
// Small status panel + Halt/Resume controls for the swarm kill-switch.
// Polls /api/kill-switch?op=status every 10 s; renders a modal for the
// 2-of-N + 2FA approval flow when the user clicks Halt or Resume.
//
// Drop into any page that already imports GlassCard. Sized for the
// existing /control sidebar grid.

"use client";

import { useEffect, useState, useCallback } from "react";

interface KillSwitchStatus {
  swarm_enabled_env?: boolean;
  kill_switch_active?: boolean;
  escalation_lock_active?: boolean;
  panic_count_last_hour?: number;
  approver_allowlist?: string[];
  approver_totp_configured?: string[];
  error?: string;
}

type Mode = "idle" | "halt" | "resume";

const POLL_MS = 10_000;

export default function KillSwitchPanel() {
  const [status, setStatus] = useState<KillSwitchStatus | null>(null);
  const [mode, setMode] = useState<Mode>("idle");
  const [busy, setBusy] = useState<boolean>(false);
  const [actionError, setActionError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      const r = await fetch("/api/kill-switch?op=status", { cache: "no-store" });
      const data = await r.json().catch(() => ({}));
      setStatus(data);
    } catch (exc) {
      setStatus({ error: String(exc) });
    }
  }, []);

  useEffect(() => {
    refresh();
    const t = setInterval(refresh, POLL_MS);
    return () => clearInterval(t);
  }, [refresh]);

  const onAfterAction = async () => {
    setMode("idle");
    setBusy(false);
    setActionError(null);
    await refresh();
  };

  const headline =
    status?.kill_switch_active
      ? { dot: "red" as const, label: "HALTED" }
      : status?.swarm_enabled_env
        ? { dot: "green" as const, label: "RUNNING" }
        : { dot: "dim" as const, label: "DISABLED" };

  return (
    <div
      className="rounded border p-3 text-xs"
      style={{
        background: "var(--surface)",
        borderColor: "var(--border)",
        color: "var(--text)",
      }}
    >
      <div className="flex items-center justify-between mb-2">
        <span className="text-[11px] uppercase tracking-wider"
              style={{ color: "var(--text-dim)" }}>
          Kill Switch
        </span>
        <Dot color={headline.dot} />
      </div>

      <Row label="State" value={headline.label} />
      <Row
        label="Escalation lock"
        value={status?.escalation_lock_active ? "LOCKED" : "no"}
        emphasis={status?.escalation_lock_active}
      />
      <Row
        label="Panics last hour"
        value={String(status?.panic_count_last_hour ?? "—")}
        emphasis={(status?.panic_count_last_hour ?? 0) >= 3}
      />
      <Row
        label="Approvers w/ TOTP"
        value={`${status?.approver_totp_configured?.length ?? 0} / ${status?.approver_allowlist?.length ?? 0}`}
      />

      <div className="mt-3 flex gap-2">
        {!status?.kill_switch_active ? (
          <button
            type="button"
            disabled={busy}
            onClick={() => setMode("halt")}
            className="flex-1 rounded border py-1 text-xs"
            style={{
              borderColor: "var(--error)",
              color: "var(--error)",
              opacity: busy ? 0.5 : 1,
            }}
          >
            Halt swarm
          </button>
        ) : (
          <button
            type="button"
            disabled={busy}
            onClick={() => setMode("resume")}
            className="flex-1 rounded border py-1 text-xs"
            style={{
              borderColor: "var(--success)",
              color: "var(--success)",
              opacity: busy ? 0.5 : 1,
            }}
          >
            Resume swarm
          </button>
        )}
      </div>

      {status?.error && (
        <p className="mt-2 text-[10px]" style={{ color: "var(--error)" }}>
          {status.error}
        </p>
      )}

      {mode === "halt" && (
        <KillModal
          status={status}
          busy={busy}
          setBusy={setBusy}
          actionError={actionError}
          setActionError={setActionError}
          onClose={() => setMode("idle")}
          onSuccess={onAfterAction}
        />
      )}
      {mode === "resume" && (
        <ResumeModal
          status={status}
          busy={busy}
          setBusy={setBusy}
          actionError={actionError}
          setActionError={setActionError}
          onClose={() => setMode("idle")}
          onSuccess={onAfterAction}
        />
      )}
    </div>
  );
}

// ── Row + Dot helpers ────────────────────────────────────────────────────────

function Row({ label, value, emphasis }:
              { label: string; value: string; emphasis?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-2 py-0.5">
      <span className="text-[10px] leading-none"
            style={{ color: "var(--text-dim)" }}>
        {label}
      </span>
      <span className="text-[10px] leading-none"
            style={{
              color: emphasis ? "var(--warning)" : "var(--text)",
              fontWeight: emphasis ? 600 : 400,
            }}>
        {value}
      </span>
    </div>
  );
}

function Dot({ color }: { color: "green" | "amber" | "red" | "dim" }) {
  const c =
    color === "green" ? "var(--success)" :
    color === "amber" ? "var(--warning)" :
    color === "red"   ? "var(--error)"   : "var(--text-dim)";
  return (
    <span style={{
      width: 8, height: 8, borderRadius: 4, background: c,
      boxShadow: color === "red" ? `0 0 6px ${c}` : "none",
      display: "inline-block",
    }} />
  );
}

// ── Modals — 2-of-N for halt, single approver for resume ────────────────────

interface ModalProps {
  status: KillSwitchStatus | null;
  busy: boolean;
  setBusy: (b: boolean) => void;
  actionError: string | null;
  setActionError: (e: string | null) => void;
  onClose: () => void;
  onSuccess: () => void;
}

function KillModal(p: ModalProps) {
  const [a1User, setA1User] = useState("");
  const [a1Totp, setA1Totp] = useState("");
  const [a2User, setA2User] = useState("");
  const [a2Totp, setA2Totp] = useState("");
  const [reason, setReason] = useState("");

  const submit = async () => {
    if (a1User === a2User || !a1User || !a2User) {
      p.setActionError("approver1 and approver2 must be different non-empty users");
      return;
    }
    if (!/^\d{6,8}$/.test(a1Totp) || !/^\d{6,8}$/.test(a2Totp)) {
      p.setActionError("TOTP codes must be 6-8 digits");
      return;
    }
    p.setBusy(true);
    p.setActionError(null);
    try {
      const r = await fetch("/api/kill-switch?op=kill", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          approver1_user: a1User,
          approver1_totp: a1Totp,
          approver2_user: a2User,
          approver2_totp: a2Totp,
          reason,
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        p.setActionError(typeof data === "object" ?
                        JSON.stringify(data) : String(data));
        p.setBusy(false);
        return;
      }
      p.onSuccess();
    } catch (exc) {
      p.setActionError(String(exc));
      p.setBusy(false);
    }
  };

  return (
    <ModalShell title="Halt swarm — 2-of-N + 2FA"
                onClose={p.onClose}
                error={p.actionError}>
      <ApproverPicker
        label="Approver 1"
        users={p.status?.approver_totp_configured ?? []}
        user={a1User} onUserChange={setA1User}
        totp={a1Totp} onTotpChange={setA1Totp}
      />
      <ApproverPicker
        label="Approver 2"
        users={p.status?.approver_totp_configured ?? []}
        user={a2User} onUserChange={setA2User}
        totp={a2Totp} onTotpChange={setA2Totp}
      />
      <label className="text-[10px] block mt-2"
             style={{ color: "var(--text-dim)" }}>
        Reason
      </label>
      <input
        type="text"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="incident-12345"
        className="w-full rounded border px-2 py-1 text-xs"
        style={{ borderColor: "var(--border)",
                background: "var(--surface)",
                color: "var(--text)" }}
      />
      <div className="mt-3 flex gap-2 justify-end">
        <button type="button" onClick={p.onClose}
                className="rounded border px-3 py-1 text-xs"
                style={{ borderColor: "var(--border)" }}>
          Cancel
        </button>
        <button type="button" onClick={submit} disabled={p.busy}
                className="rounded border px-3 py-1 text-xs"
                style={{
                  borderColor: "var(--error)",
                  color: "var(--error)",
                  opacity: p.busy ? 0.5 : 1,
                }}>
          {p.busy ? "Halting..." : "Halt swarm"}
        </button>
      </div>
    </ModalShell>
  );
}

function ResumeModal(p: ModalProps) {
  const [user, setUser] = useState("");
  const [totp, setTotp] = useState("");
  const [reason, setReason] = useState("");
  const [confirmed, setConfirmed] = useState(false);

  const lockActive = p.status?.escalation_lock_active === true;

  const submit = async () => {
    if (!user) {
      p.setActionError("approver user required");
      return;
    }
    if (!/^\d{6,8}$/.test(totp)) {
      p.setActionError("TOTP must be 6-8 digits");
      return;
    }
    if (lockActive && (!confirmed || !reason)) {
      p.setActionError("Escalation lock active — confirm + reason required");
      return;
    }
    p.setBusy(true);
    p.setActionError(null);
    try {
      const r = await fetch("/api/kill-switch?op=resume", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          approver_user: user,
          approver_totp: totp,
          reason,
          confirmed: lockActive ? confirmed : false,
        }),
      });
      const data = await r.json().catch(() => ({}));
      if (!r.ok) {
        p.setActionError(typeof data === "object" ?
                        JSON.stringify(data) : String(data));
        p.setBusy(false);
        return;
      }
      p.onSuccess();
    } catch (exc) {
      p.setActionError(String(exc));
      p.setBusy(false);
    }
  };

  return (
    <ModalShell
      title={lockActive ? "Resume swarm — escalation lock active"
                        : "Resume swarm"}
      onClose={p.onClose}
      error={p.actionError}
    >
      <ApproverPicker
        label="Approver"
        users={p.status?.approver_totp_configured ?? []}
        user={user} onUserChange={setUser}
        totp={totp} onTotpChange={setTotp}
      />
      <label className="text-[10px] block mt-2"
             style={{ color: "var(--text-dim)" }}>
        Reason {lockActive && (
          <span style={{ color: "var(--warning)" }}>(required)</span>
        )}
      </label>
      <input
        type="text"
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="manual recovery complete"
        className="w-full rounded border px-2 py-1 text-xs"
        style={{ borderColor: "var(--border)",
                background: "var(--surface)",
                color: "var(--text)" }}
      />
      {lockActive && (
        <label className="mt-2 flex items-center gap-2 text-[10px]"
               style={{ color: "var(--warning)" }}>
          <input type="checkbox" checked={confirmed}
                 onChange={(e) => setConfirmed(e.target.checked)} />
          I confirm the kill_switch.flag has been manually reviewed
          and is safe to clear.
        </label>
      )}
      <div className="mt-3 flex gap-2 justify-end">
        <button type="button" onClick={p.onClose}
                className="rounded border px-3 py-1 text-xs"
                style={{ borderColor: "var(--border)" }}>
          Cancel
        </button>
        <button type="button" onClick={submit} disabled={p.busy}
                className="rounded border px-3 py-1 text-xs"
                style={{
                  borderColor: "var(--success)",
                  color: "var(--success)",
                  opacity: p.busy ? 0.5 : 1,
                }}>
          {p.busy ? "Resuming..." : "Resume swarm"}
        </button>
      </div>
    </ModalShell>
  );
}

interface ApproverPickerProps {
  label: string;
  users: string[];
  user: string; onUserChange: (u: string) => void;
  totp: string; onTotpChange: (t: string) => void;
}

function ApproverPicker(p: ApproverPickerProps) {
  return (
    <div className="mt-2">
      <label className="text-[10px] block"
             style={{ color: "var(--text-dim)" }}>
        {p.label}
      </label>
      <div className="flex gap-2">
        <select
          value={p.user}
          onChange={(e) => p.onUserChange(e.target.value)}
          className="flex-1 rounded border px-2 py-1 text-xs"
          style={{ borderColor: "var(--border)",
                  background: "var(--surface)",
                  color: "var(--text)" }}
        >
          <option value="">— pick user —</option>
          {p.users.map((u) => (
            <option key={u} value={u}>{u}</option>
          ))}
        </select>
        <input
          type="text"
          inputMode="numeric"
          pattern="\d{6,8}"
          value={p.totp}
          onChange={(e) => p.onTotpChange(
            e.target.value.replace(/\D/g, "").slice(0, 8))}
          placeholder="123456"
          className="w-24 rounded border px-2 py-1 text-xs"
          style={{ borderColor: "var(--border)",
                  background: "var(--surface)",
                  color: "var(--text)" }}
        />
      </div>
    </div>
  );
}

function ModalShell({ title, onClose, error, children }:
                   { title: string; onClose: () => void;
                     error: string | null;
                     children: React.ReactNode }) {
  return (
    <div
      role="dialog"
      aria-modal="true"
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-center justify-center p-4"
      style={{ background: "rgba(0,0,0,0.6)" }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="w-full max-w-sm rounded-lg border p-4"
        style={{ background: "var(--bg)",
                borderColor: "var(--border)",
                color: "var(--text)" }}
      >
        <h3 className="text-sm font-semibold mb-2">{title}</h3>
        {children}
        {error && (
          <p className="mt-2 rounded border px-2 py-1 text-[10px]"
             style={{ borderColor: "var(--error)",
                     color: "var(--error)" }}>
            {error}
          </p>
        )}
      </div>
    </div>
  );
}
