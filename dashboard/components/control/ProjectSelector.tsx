// components/control/ProjectSelector.tsx — RA-1103 — global active-project picker.
//
// Sits in the TopBar. Reads .harness/projects.json via the existing portfolio
// health endpoint (already auth-gated through the proxy), persists selection
// to localStorage, and emits a CustomEvent('pi-active-project-changed') so
// other components (BuildForm) can react without a React context.
//
// Why localStorage + CustomEvent instead of a context:
// - Adds zero render coupling to the existing tree
// - Survives a tab reload — the Second Brain remembers what you were on
// - The number of subscribers is small (BuildForm today; could grow), so the
//   pub/sub pattern stays tractable

"use client";

import { useEffect, useState } from "react";

interface ProjectOption {
  project_id: string;
  repo: string;
}

const STORAGE_KEY = "pi-active-project";
const EVENT_NAME  = "pi-active-project-changed";

export function getActiveProject(): { project_id: string; repo: string } | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw);
  } catch {
    return null;
  }
}

function setActiveProject(p: { project_id: string; repo: string } | null) {
  if (typeof window === "undefined") return;
  if (p) {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(p));
  } else {
    window.localStorage.removeItem(STORAGE_KEY);
  }
  window.dispatchEvent(new CustomEvent(EVENT_NAME, { detail: p }));
}

export function useActiveProject(): { project_id: string; repo: string } | null {
  const [active, setActive] = useState<{ project_id: string; repo: string } | null>(
    () => getActiveProject(),
  );

  useEffect(() => {
    const onChange = (e: Event) => {
      const detail = (e as CustomEvent).detail as { project_id: string; repo: string } | null;
      setActive(detail);
    };
    window.addEventListener(EVENT_NAME, onChange);
    return () => window.removeEventListener(EVENT_NAME, onChange);
  }, []);

  return active;
}

export default function ProjectSelector() {
  const [projects, setProjects] = useState<ProjectOption[]>([]);
  const [active, setActive] = useState<{ project_id: string; repo: string } | null>(
    () => getActiveProject(),
  );
  const [open, setOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;
    fetch("/api/pi-ceo/api/projects/health")
      .then((r) => (r.ok ? r.json() : []))
      .then((data: Array<{ project_id: string; repo: string }>) => {
        if (cancelled || !Array.isArray(data)) return;
        setProjects(data.map((p) => ({ project_id: p.project_id, repo: p.repo })));
      })
      .catch(() => undefined);
    return () => {
      cancelled = true;
    };
  }, []);

  // Close on outside click — wire up only when open
  useEffect(() => {
    if (!open) return;
    const onClick = () => setOpen(false);
    // Defer registration so the click that opened the menu doesn't immediately close it
    const t = setTimeout(() => window.addEventListener("click", onClick), 0);
    return () => {
      clearTimeout(t);
      window.removeEventListener("click", onClick);
    };
  }, [open]);

  function pick(p: ProjectOption | null) {
    setActive(p);
    setActiveProject(p);
    setOpen(false);
  }

  const label = active?.project_id ?? "all projects";

  return (
    <div className="relative" onClick={(e) => e.stopPropagation()}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="text-[10px] font-mono px-2 py-0.5 rounded inline-flex items-center gap-1.5 hover:opacity-80"
        style={{
          color: active ? "var(--accent)" : "var(--text-muted)",
          background: active ? "var(--accent-subtle)" : "var(--panel-hover)",
          border: `1px solid ${active ? "var(--accent)" : "var(--border)"}33`,
        }}
        aria-haspopup="listbox"
        aria-expanded={open}
        title={active ? `Active project: ${active.repo}` : "Pick an active project"}
      >
        <span aria-hidden="true">▾</span>
        <span className="truncate max-w-[120px]">{label}</span>
      </button>

      {open && (
        <div
          className="absolute right-0 mt-1 w-56 max-h-80 overflow-auto rounded shadow-lg z-50"
          style={{
            background: "var(--panel)",
            border: "1px solid var(--border)",
          }}
          role="listbox"
        >
          <button
            onClick={() => pick(null)}
            className="w-full text-left text-[11px] font-mono px-3 py-1.5 hover:bg-opacity-50"
            style={{
              color: !active ? "var(--accent)" : "var(--text-muted)",
              background: !active ? "var(--accent-subtle)" : "transparent",
            }}
          >
            (clear · all projects)
          </button>
          <div style={{ borderTop: "1px solid var(--border)" }} />
          {projects.map((p) => (
            <button
              key={p.project_id}
              onClick={() => pick(p)}
              className="w-full text-left px-3 py-1.5 hover:bg-opacity-50"
              style={{
                background:
                  active?.project_id === p.project_id
                    ? "var(--accent-subtle)"
                    : "transparent",
              }}
            >
              <div
                className="text-[11px] font-mono"
                style={{
                  color:
                    active?.project_id === p.project_id ? "var(--accent)" : "var(--text)",
                }}
              >
                {p.project_id}
              </div>
              <div
                className="text-[9px] font-mono truncate"
                style={{ color: "var(--text-dim)" }}
              >
                {p.repo}
              </div>
            </button>
          ))}
          {projects.length === 0 && (
            <div className="text-[10px] px-3 py-2" style={{ color: "var(--text-dim)" }}>
              Loading projects…
            </div>
          )}
        </div>
      )}
    </div>
  );
}
