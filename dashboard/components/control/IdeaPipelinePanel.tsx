// IdeaPipelinePanel — UNI-2633 one-screen Board packet on the daily window.
"use client";

import { useEffect, useState } from "react";
import { useSource } from "@/lib/boards/sources";
import {
  IDEA_VERDICTS,
  canAuthorizeGo,
  disposeFeedback,
  type IdeaPacket,
  type IdeaPipelinePayload,
  type IdeaVerdict,
} from "@/lib/control/idea-pipeline";
import styles from "./idea-pipeline-panel.module.css";

const API = "/api/idea-pipeline";

async function postJson<T>(path: string, body: object): Promise<T> {
  const res = await fetch(`/api/pi-ceo${path}`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const json = (await res.json().catch(() => ({}))) as T & { detail?: string };
  if (!res.ok) {
    throw new Error(typeof json.detail === "string" ? json.detail : `HTTP ${res.status}`);
  }
  return json;
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-[10px] uppercase tracking-wide text-text-muted">{label}</div>
      <p className="mt-0.5 text-sm text-slate-100">{value}</p>
    </div>
  );
}

export default function IdeaPipelinePanel() {
  const [payload, setPayload] = useState<IdeaPipelinePayload | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  // RA-7898: the idea pipeline is read by the shared poller (60 s); after a
  // write, `refresh()` asks it for one immediate re-read.
  const source = useSource<IdeaPipelinePayload>("idea-pipeline");
  const refresh = source.refresh;
  useEffect(() => {
    if (source.seq === 0) return;
    if (!source.value) {
      setError("Mission Control could not read the idea pipeline.");
      return;
    }
    setPayload(source.value);
    setError(null);
  }, [source.seq, source.value]);

  const packet: IdeaPacket | null = payload?.snapshot.packet ?? null;
  const legacyPacket = Boolean(packet && !packet.north_star_fit.source_revision);

  async function dropIdea() {
    const text = draft.trim();
    if (text.length < 8) {
      setError("One to three sentences. A bit more detail is needed.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await postJson(`${API}/intake`, { text, source: "phill" });
      setDraft("");
      setNotice("Idea captured. Board packet is ready.");
      await refresh();
    } catch (exc) {
      setError(String(exc));
    } finally {
      setBusy(false);
    }
  }

  async function dispose(verdict: IdeaVerdict) {
    if (!packet) return;
    setBusy(true);
    setError(null);
    try {
      await postJson(`${API}/dispose`, { idea_id: packet.idea_id, verdict });
      setNotice(disposeFeedback(verdict));
      await refresh();
    } catch (exc) {
      setError(String(exc));
    } finally {
      setBusy(false);
    }
  }

  async function sayGo() {
    if (!packet) return;
    setBusy(true);
    setError(null);
    try {
      await postJson(`${API}/go`, { idea_id: packet.idea_id });
      setNotice("GO recorded. Nothing has started.");
      await refresh();
    } catch (exc) {
      setError(String(exc));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section
      id="idea-pipeline"
      className={styles.panel}
      aria-label="Idea intake and Board packet"
    >
      <header className={styles.header}>
        <div>
          <h2>Tell Mission Control your idea</h2>
          <p>One inbox for all projects. Choosing a card above does not attach the idea. Nothing starts without your GO.</p>
        </div>
        <span className={styles.count}>
          {payload ? `${payload.snapshot.awaiting} waiting for a decision` : "Board status unknown"}
        </span>
      </header>

      <div className={styles.composer}>
        <label className={styles.srOnly} htmlFor="idea-intake">New idea</label>
        <textarea
          id="idea-intake"
          rows={2}
          value={draft}
          disabled={busy}
          maxLength={2000}
          placeholder="One to three sentences. No formatting needed."
          onChange={(event) => setDraft(event.target.value)}
        />
        <button type="button" disabled={busy} onClick={() => void dropIdea()}>
          {busy ? "Working…" : "Drop idea ↗"}
        </button>
      </div>

      <div className="mt-3 min-h-[1.25rem] text-sm" aria-live="polite">
        {error ? <p className="text-rose-300">{error}</p> : null}
        {notice && !error ? <p className="text-emerald-300">{notice}</p> : null}
      </div>

      {packet ? (
        <details className={styles.packet} open={Boolean(notice)}>
          <summary>Board packet · {packet.status} · {legacyPacket ? "review required" : packet.recommended_verdict}</summary>
          <div className="mt-3 grid gap-3">
          <Field label="Idea" value={packet.text} />
          <Field
            label="North Star fit"
            value={legacyPacket ? "Legacy packet under an earlier North Star. Re-examine before deciding; its old recommendation is not current evidence." : `${packet.north_star_fit.label} · ${packet.north_star_fit.rationale}`}
          />
          <Field
            label="Effort vs impact"
            value={legacyPacket ? "Unknown until re-examined." : `${packet.effort_vs_impact.effort} effort / ${packet.effort_vs_impact.impact} impact. ${packet.effort_vs_impact.rationale}`}
          />
          <Field
            label="Directive"
            value={`${packet.directive.label}. ${packet.directive.rationale}`}
          />
          <Field
            label="Would displace"
            value={packet.displacement.would_displace}
          />
          <Field
            label="Board lean"
            value={legacyPacket ? "Review required under the current North Star." : `${packet.recommended_verdict} · Judge ${packet.judge.decision}. ${packet.judge.note ?? ""}`}
          />
          {packet.plan_packet_md ? (
            <div>
              <div className="text-[10px] uppercase tracking-wide text-text-muted">
                {`gs-autoplan review${packet.linear_id ? ` · ${packet.linear_id}` : ""}`}
              </div>
              <pre className="mt-0.5 max-h-96 overflow-auto whitespace-pre-wrap text-xs text-slate-100">
                {packet.plan_packet_md}
              </pre>
            </div>
          ) : null}
          <p className="text-xs text-text-muted">{packet.spm.out_of_scope}</p>
          <div className="flex flex-wrap gap-2">
            {IDEA_VERDICTS.map((word) => (
              <button
                key={word}
                type="button"
                disabled={busy || packet.status === "disposed"}
                className="rounded border border-slate-500 px-3 py-1.5 text-sm text-slate-100 disabled:opacity-40"
                onClick={() => void dispose(word)}
              >
                {word}
              </button>
            ))}
            <button
              type="button"
              disabled={busy || !canAuthorizeGo(packet)}
              className="rounded bg-amber-300 px-3 py-1.5 text-sm font-semibold text-slate-900 disabled:opacity-40"
              onClick={() => void sayGo()}
            >
              GO
            </button>
          </div>
          {packet.go_at ? (
            <p className="text-sm text-emerald-300">GO is on the record. Nothing has started.</p>
          ) : null}
          </div>
        </details>
      ) : null}
    </section>
  );
}
