"use client";
// RA-7898 — second views for Ideas (funnel, inbox) and Kill switch (status
// light, detail). These are read-only: the write controls live only in each
// module's first view, the existing panel.

import type { IdeaPipelinePayload } from "@/lib/control/idea-pipeline";
import { useSource, type KillSwitchStatus } from "@/lib/boards/sources";
import { ideaFunnel, ideaInbox } from "@/lib/boards/views/shapes";
import { Bars, Dot, Nothing, Unexpected } from "./charts";
import styles from "./views.module.css";

function useIdeas() {
  return useSource<IdeaPipelinePayload>("idea-pipeline").value;
}

export function IdeaFunnel() {
  const funnel = ideaFunnel(useIdeas());
  if (!funnel) return <Unexpected what="idea pipeline" />;
  return <Bars max={Math.max(1, funnel[0].count)} bars={funnel.map((s) => ({ label: s.stage, value: s.count }))} />;
}

export function IdeaInbox() {
  const inbox = ideaInbox(useIdeas());
  if (!inbox) return <Unexpected what="idea pipeline" />;
  if (inbox.length === 0) return <Nothing text="No idea is waiting for a decision." />;
  return (
    <div className={styles.rows}>
      {inbox.map((i) => (
        <div key={i.id} className={styles.row}>
          <Dot tone="accent" />
          <span className={styles.truncate} title={i.text}>{i.text}</span>
          <span className={styles.meta}>{i.source}</span>
        </div>
      ))}
    </div>
  );
}

function headline(s: KillSwitchStatus): { tone: "ok" | "bad" | "idle"; title: string; sub: string } {
  if (s.kill_switch_active) return { tone: "bad", title: "Swarm halted", sub: "The kill switch is on." };
  if (s.swarm_enabled_env) return { tone: "ok", title: "Swarm running", sub: "Stop path ready." };
  return { tone: "idle", title: "Swarm disabled", sub: "Not enabled in this environment." };
}

function useKill() {
  return useSource<KillSwitchStatus>("kill-switch").value;
}

export function KillLight() {
  const s = useKill();
  if (!s || s.error) return <Unexpected what="kill switch" />;
  const h = headline(s);
  return (
    <div className={styles.lightRow}>
      <span className={styles.lamp} data-tone={h.tone} aria-hidden><i /></span>
      <div><div className={styles.headline}>{h.title}</div><div className={styles.sub}>{h.sub}</div></div>
    </div>
  );
}

export function KillDetail() {
  const s = useKill();
  if (!s || s.error) return <Unexpected what="kill switch" />;
  return (
    <div>
      <div className={styles.kv}><span>State</span><b>{headline(s).title}</b></div>
      <div className={styles.kv}><span>Escalation lock</span><b>{s.escalation_lock_active ? "Locked" : "No"}</b></div>
      <div className={styles.kv}><span>Panics in the last hour</span><b>{s.panic_count_last_hour ?? "—"}</b></div>
      <div className={styles.kv}><span>Approvers with TOTP</span><b>{s.approver_totp_configured?.length ?? 0} of {s.approver_allowlist?.length ?? 0}</b></div>
      <p className={styles.sub}>To halt or resume, show this module as Controls.</p>
    </div>
  );
}
