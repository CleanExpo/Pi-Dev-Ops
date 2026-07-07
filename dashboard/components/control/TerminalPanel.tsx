// TerminalPanel.tsx — Mission Control live tmux pane view (RA-7012).
// Read-only. Polls /api/pi-ceo/api/terminal/sessions (5s) for the fleet and
// /api/pi-ceo/api/terminal/tail (3s) for the selected session's redacted pane.
// Write verbs (send/open/close) go through the gated tmux_writer, never this UI.
"use client";

import { useCallback, useEffect, useState } from "react";

interface Pane {
  id?: string;
  title?: string;
}
interface Window {
  id?: string;
  name?: string;
  panes?: Pane[];
}
interface Session {
  name: string;
  windows?: Window[];
  attached?: boolean;
}
interface SessionsResp {
  sessions?: Session[];
  error?: string;
}
interface TailResp {
  session?: string;
  lines?: string[];
  error?: string;
}

const SESSIONS_MS = 5000;
const TAIL_MS = 3000;

export default function TerminalPanel() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [lines, setLines] = useState<string[]>([]);
  const [err, setErr] = useState<string | null>(null);
  const [fresh, setFresh] = useState<boolean>(false);

  const fetchJson = useCallback(async <T,>(path: string): Promise<T | null> => {
    try {
      const r = await fetch(path, { credentials: "include", cache: "no-store" });
      if (!r.ok) {
        setErr(`HTTP ${r.status}`);
        return null;
      }
      return (await r.json()) as T;
    } catch (e) {
      setErr(String(e));
      return null;
    }
  }, []);

  // Poll the session list.
  useEffect(() => {
    let mounted = true;
    const tick = async () => {
      const j = await fetchJson<SessionsResp>("/api/pi-ceo/api/terminal/sessions");
      if (!mounted || !j) return;
      const list = j.sessions ?? [];
      setSessions(list);
      if (j.error) setErr(j.error);
      else setErr(null);
      // auto-select the first session once, if none chosen
      setSelected((cur) => cur ?? (list[0]?.name ?? null));
    };
    tick();
    const id = setInterval(tick, SESSIONS_MS);
    return () => {
      mounted = false;
      clearInterval(id);
    };
  }, [fetchJson]);

  // Poll the selected session's pane tail.
  useEffect(() => {
    if (!selected) return;
    let mounted = true;
    const tick = async () => {
      const j = await fetchJson<TailResp>(
        `/api/pi-ceo/api/terminal/tail?session=${encodeURIComponent(selected)}&lines=200`,
      );
      if (!mounted || !j) return;
      setLines(j.lines ?? []);
      if (j.error) {
        setErr(j.error);
        setFresh(false);
      } else {
        setErr(null);
        setFresh(true);
      }
    };
    tick();
    const id = setInterval(tick, TAIL_MS);
    return () => {
      mounted = false;
      clearInterval(id);
      setFresh(false);
    };
  }, [selected, fetchJson]);

  return (
    <section
      className="rounded-lg border border-neutral-800 bg-neutral-950 p-4"
      aria-label="Terminal fleet"
    >
      <div className="mb-3 flex items-center justify-between">
        <h2 className="text-sm font-semibold text-neutral-200">Terminal fleet</h2>
        <span
          className={`text-xs ${fresh ? "text-emerald-400" : "text-neutral-500"}`}
          title="live pane freshness"
        >
          {fresh ? "● live" : "○ idle"}
        </span>
      </div>

      {sessions.length === 0 ? (
        <p className="text-xs text-neutral-500">
          {err ? `No sessions — ${err}` : "No tmux sessions on this node."}
        </p>
      ) : (
        <>
          <div className="mb-3 flex flex-wrap gap-2">
            {sessions.map((s) => (
              <button
                key={s.name}
                onClick={() => {
                  setSelected(s.name);
                  setLines([]);
                }}
                className={`rounded px-2 py-1 text-xs ${
                  selected === s.name
                    ? "bg-emerald-700 text-white"
                    : "bg-neutral-800 text-neutral-300 hover:bg-neutral-700"
                }`}
              >
                {s.name}
                {s.attached ? " ●" : ""}
              </button>
            ))}
          </div>

          <pre className="max-h-72 overflow-auto rounded bg-black p-3 font-mono text-xs leading-relaxed text-neutral-300">
            {lines.length ? lines.join("\n") : "  (waiting for pane output…)"}
          </pre>
        </>
      )}
      {err && sessions.length > 0 ? (
        <p className="mt-2 text-xs text-amber-500">{err}</p>
      ) : null}
    </section>
  );
}
