// components/PhaseTracker.tsx — phase status table with Zinc tokens
"use client";

import type { Phase } from "@/lib/types";

const STATUS_COLOR: Record<Phase["status"], string> = {
  pending: "var(--text-dim)",
  running: "var(--accent)",
  done:    "var(--success)",
  error:   "var(--error)",
};

const STATUS_CHAR: Record<Phase["status"], string> = {
  pending: "○",
  running: "●",
  done:    "✓",
  error:   "✗",
};

interface Props {
  phases: Phase[];
}

export default function PhaseTracker({ phases }: Props) {
  return (
    <div
      className="rounded-md border border-[var(--border)] overflow-hidden"
      style={{ borderBottom: "1px solid var(--border)" }}
    >
      <div className="px-3 py-2" style={{ borderBottom: "1px solid var(--border)" }}>
        <span
          className="font-geist-mono text-[10px] uppercase tracking-widest"
          style={{ color: "var(--text-muted)" }}
        >
          Phases
        </span>
      </div>
      <table className="w-full">
        <thead>
          <tr style={{ borderBottom: "1px solid var(--border-subtle)" }}>
            {["#", "Phase", "Skill", "Status"].map((h) => (
              <th
                key={h}
                className="font-geist-mono text-[9px] uppercase text-left px-3 py-1.5"
                style={{ color: "var(--text-dim)" }}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {phases.map((p) => (
            <tr
              key={p.id}
              style={{
                borderBottom: "1px solid var(--border-subtle)",
                background: p.status === "running" ? "var(--accent-subtle)" : "transparent",
              }}
            >
              <td
                className="font-geist-mono text-[10px] px-3 py-1.5"
                style={{ color: "var(--text-dim)" }}
              >
                {p.id}
              </td>
              <td
                className="font-geist-mono text-[11px] px-3 py-1.5"
                style={{
                  color: p.status === "running" ? "var(--accent)"
                       : p.status === "done"    ? "var(--text)"
                       : p.status === "error"   ? "var(--error)"
                       : "var(--text-muted)",
                }}
              >
                {p.name}
              </td>
              <td
                className="font-geist-mono text-[9px] px-3 py-1.5 hidden sm:table-cell"
                style={{ color: "var(--text-dim)" }}
              >
                {p.skill.split("+")[0].trim()}
              </td>
              <td className="px-3 py-1.5">
                <span
                  className="font-geist-mono text-[11px]"
                  style={{ color: STATUS_COLOR[p.status] }}
                >
                  {STATUS_CHAR[p.status]}{" "}
                  <span className="text-[9px] uppercase tracking-wider">{p.status}</span>
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
