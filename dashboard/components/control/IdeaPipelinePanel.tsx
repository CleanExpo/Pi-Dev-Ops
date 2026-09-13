// IdeaPipelinePanel — UNI-2633 one-screen Board packet on the daily window.
"use client";

import { useCallback, useEffect, useState } from "react";
import { fetchProxyJSON } from "@/lib/pi-ceo-fetch";
import {
  IDEA_VERDICTS,
  canAuthorizeGo,
  disposeFeedback,
  type IdeaPacket,
  type IdeaPipelinePayload,
  type IdeaVerdict,
} from "@/lib/control/idea-pipeline";

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

  const refresh = useCallback(async () => {
    const data = await fetchProxyJSON<IdeaPipelinePayload>(API, {
      credentials: "include",
      cache: "no-store",
    });
    if (!data) {
      setError("Mission Control could not read the idea pipeline.");
      return;
    }
    setPayload(data);
    setError(null);
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const packet: IdeaPacket | null = payload?.snapshot.packet ?? null;

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
      className="rounded-lg border border-slate-700/50 bg-slate-900/50 p-4"
      aria-label="Board idea packet"
    >
      <header className="mb-3 flex items-baseline justify-between gap-3">
        <div>
          <h2 className="text-lg font-semibold text-slate-100">Board packet</h2>
          <p className="text-xs text-text-muted">
            Drop a short idea. Dispose with one word. Nothing starts without GO.
          </p>
        </div>
        <span className="text-xs text-text-muted tabular-nums">
          {payload ? `${payload.snapshot.awaiting} waiting` : "…"}
        </span>
      </header>

      <label className="block text-xs text-text-muted" htmlFor="idea-intake">
        New idea
      </label>
      <textarea
        id="idea-intake"
        className="mt-1 w-full rounded border border-slate-700 bg-slate-950 p-2 text-sm text-slate-100"
        rows={3}
        value={draft}
        disabled={busy}
        placeholder="One to three sentences. No formatting needed."
        onChange={(event) => setDraft(event.target.value)}
      />
      <button
        type="button"
        className="mt-2 rounded bg-slate-100 px-3 py-1.5 text-sm font-medium text-slate-900 disabled:opacity-50"
        disabled={busy}
        onClick={() => void dropIdea()}
      >
        Drop idea
      </button>

      <div className="mt-3 min-h-[1.25rem] text-sm" aria-live="polite">
        {error ? <p className="text-rose-300">{error}</p> : null}
        {notice && !error ? <p className="text-emerald-300">{notice}</p> : null}
      </div>

      {!packet ? (
        <p className="mt-2 text-sm text-text-muted">
          No idea waiting. Drop one above or add a line to IDEAS.md.
        </p>
      ) : (
        <div className="mt-3 grid gap-3">
          <Field label="Idea" value={packet.text} />
          <Field
            label="North Star fit"
            value={`${packet.north_star_fit.label} · ${packet.north_star_fit.rationale}`}
          />
          <Field
            label="Effort vs impact"
            value={`${packet.effort_vs_impact.effort} effort / ${packet.effort_vs_impact.impact} impact. ${packet.effort_vs_impact.rationale}`}
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
            value={`${packet.recommended_verdict} · Judge ${packet.judge.score} ${packet.judge.decision}`}
          />
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
      )}
    </section>
  );
}
