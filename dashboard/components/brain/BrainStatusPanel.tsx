"use client";

import { useCallback, useState } from "react";
import {
  BRAIN_STATUS,
  type BrainChecklistItem,
  type BrainItemStatus,
  type BrainMilestone,
} from "@/lib/brain-status";

const STATUS_STYLE: Record<BrainItemStatus, { bg: string; fg: string; label: string }> = {
  done: { bg: "color-mix(in srgb, var(--success) 18%, transparent)", fg: "var(--success)", label: "Done" },
  next: { bg: "color-mix(in srgb, var(--accent) 18%, transparent)", fg: "var(--accent)", label: "Do this next" },
  blocked: { bg: "color-mix(in srgb, var(--error) 18%, transparent)", fg: "var(--error)", label: "Blocked" },
  waiting: { bg: "color-mix(in srgb, var(--text-dim) 22%, transparent)", fg: "var(--text-muted)", label: "Waiting" },
};

function Pill({ status }: { status: BrainItemStatus }) {
  const s = STATUS_STYLE[status];
  return (
    <span
      className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded"
      style={{ background: s.bg, color: s.fg }}
    >
      {s.label}
    </span>
  );
}

function CopyBlock({ lines }: { lines: string[] }) {
  const [copied, setCopied] = useState(false);
  const text = lines.join("\n");

  const copy = useCallback(async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      /* clipboard denied */
    }
  }, [text]);

  if (!lines.length) return null;

  return (
    <div className="mt-2 relative">
      <pre
        className="text-xs p-3 rounded overflow-x-auto font-mono"
        style={{
          background: "var(--background)",
          border: "1px solid var(--border)",
          color: "var(--text)",
        }}
      >
        {text}
      </pre>
      <button
        type="button"
        onClick={() => void copy()}
        className="absolute top-2 right-2 text-[10px] font-medium px-2 py-1 rounded"
        style={{
          background: "var(--panel)",
          border: "1px solid var(--border)",
          color: copied ? "var(--success)" : "var(--text-muted)",
        }}
      >
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

function MilestoneCard({ m }: { m: BrainMilestone }) {
  return (
    <article
      className="p-4 rounded-lg flex flex-col gap-2"
      style={{ background: "var(--panel)", border: "1px solid var(--border)" }}
    >
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
          {m.title}
        </h3>
        <Pill status={m.status} />
      </div>
      <p className="text-xs leading-relaxed" style={{ color: "var(--text-muted)" }}>
        {m.summary}
      </p>
    </article>
  );
}

function ChecklistRow({ item }: { item: BrainChecklistItem }) {
  const [open, setOpen] = useState(item.status === "next");

  return (
    <div
      className="rounded-lg overflow-hidden"
      style={{ border: "1px solid var(--border)", background: "var(--panel)" }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <div className="flex items-center gap-3 min-w-0">
          <span
            className="w-2 h-2 rounded-full shrink-0"
            style={{ background: STATUS_STYLE[item.status].fg }}
          />
          <span className="text-sm font-medium truncate" style={{ color: "var(--text)" }}>
            {item.label}
          </span>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Pill status={item.status} />
          <span className="text-xs" style={{ color: "var(--text-dim)" }}>
            {open ? "▾" : "▸"}
          </span>
        </div>
      </button>
      {open && (
        <div className="px-4 pb-4" style={{ borderTop: "1px solid var(--border)" }}>
          {item.detail && (
            <p className="text-xs pt-3 pb-1" style={{ color: "var(--text-muted)" }}>
              {item.detail}
            </p>
          )}
          <CopyBlock lines={item.commands ?? []} />
        </div>
      )}
    </div>
  );
}

export default function BrainStatusPanel() {
  const s = BRAIN_STATUS;
  const doneCount = s.milestones.filter((m) => m.status === "done").length;

  return (
    <div className="flex flex-col gap-6 max-w-4xl">
      {/* Hero */}
      <header className="flex flex-col gap-3">
        <div className="flex flex-wrap items-center gap-2">
          <h1 className="text-2xl font-semibold tracking-tight" style={{ color: "var(--text)" }}>
            {s.title}
          </h1>
          <span
            className="text-xs font-mono px-2 py-1 rounded"
            style={{ background: "var(--panel)", border: "1px solid var(--border)", color: "var(--text-muted)" }}
          >
            {s.commit} · {s.branch}
          </span>
        </div>
        <p className="text-base" style={{ color: "var(--text)" }}>
          {s.headline}
        </p>
        <p className="text-sm leading-relaxed" style={{ color: "var(--text-muted)" }}>
          {s.explanation}
        </p>
      </header>

      {/* Progress strip */}
      <div
        className="grid grid-cols-3 gap-3 p-4 rounded-lg"
        style={{ background: "var(--panel)", border: "1px solid var(--border)" }}
      >
        <div>
          <p className="text-[10px] uppercase tracking-widest font-semibold" style={{ color: "var(--text-dim)" }}>
            Milestones done
          </p>
          <p className="text-2xl font-semibold mt-1" style={{ color: "var(--success)" }}>
            {doneCount}/{s.milestones.length}
          </p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-widest font-semibold" style={{ color: "var(--text-dim)" }}>
            Tests (PC)
          </p>
          <p className="text-sm font-mono mt-2" style={{ color: "var(--text)" }}>
            {s.testsExpected}
          </p>
        </div>
        <div>
          <p className="text-[10px] uppercase tracking-widest font-semibold" style={{ color: "var(--text-dim)" }}>
            PR
          </p>
          <a
            href={s.prUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-sm mt-2 inline-block underline"
            style={{ color: "var(--accent)" }}
          >
            Open on GitHub
          </a>
        </div>
      </div>

      {/* Flow diagram — plain text, always visible */}
      <section
        className="p-4 rounded-lg"
        style={{ background: "var(--panel)", border: "1px solid var(--border)" }}
      >
        <h2 className="text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: "var(--text-muted)" }}>
          The loop
        </h2>
        <ol className="text-sm space-y-1 font-mono" style={{ color: "var(--text)" }}>
          <li>1. Question</li>
          <li>2. wiki-query (check wiki first)</li>
          <li>3. Collectors (CMO / CFO / Margot)</li>
          <li>4. Analyst grades → Wiki/analyst/</li>
          <li>5. wiki-ingest + wiki_sync → Supabase</li>
          <li>6. Next question starts smarter</li>
        </ol>
      </section>

      {/* Milestones grid */}
      <section>
        <h2 className="text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: "var(--text-muted)" }}>
          Where each machine stands
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
          {s.milestones.map((m) => (
            <MilestoneCard key={m.id} m={m} />
          ))}
        </div>
      </section>

      {/* Action checklist */}
      <section>
        <h2 className="text-xs font-semibold uppercase tracking-widest mb-3" style={{ color: "var(--text-muted)" }}>
          Step-by-step — expand each row, copy commands
        </h2>
        <div className="flex flex-col gap-2">
          {s.checklist.map((item) => (
            <ChecklistRow key={item.id} item={item} />
          ))}
        </div>
      </section>

      <p className="text-xs" style={{ color: "var(--text-dim)" }}>
        Last updated {s.updated}. This page is the status board — not the chat thread.
      </p>
    </div>
  );
}
