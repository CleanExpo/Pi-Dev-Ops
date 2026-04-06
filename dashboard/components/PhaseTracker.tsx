// components/PhaseTracker.tsx — Dense phase status table
"use client";

import type { Phase } from "@/lib/types";

const STATUS_COLOR = {
  pending: "#888480",
  running: "#E8751A",
  done:    "#4ADE80",
  error:   "#F87171",
};

const STATUS_CHAR = {
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
    <div style={{ borderBottom: "1px solid #2A2727" }}>
      <div className="px-3 py-1.5" style={{ borderBottom: "1px solid #2A2727" }}>
        <span className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "#C8C5C0" }}>
          phases
        </span>
      </div>
      <table className="w-full">
        <thead>
          <tr style={{ borderBottom: "1px solid #1E1C1C" }}>
            {["#", "PHASE", "SKILL", "STATUS"].map((h) => (
              <th
                key={h}
                className="font-mono text-[9px] uppercase text-left px-3 py-1"
                style={{ color: "#C8C5C0" }}
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
                borderBottom: "1px solid #1E1C1C",
                background: p.status === "running" ? "rgba(232,117,26,0.07)" : "transparent",
              }}
            >
              <td className="font-mono text-[10px] px-3 py-1.5" style={{ color: "#A8A5A0" }}>
                {p.id}
              </td>
              <td
                className="font-mono text-[11px] px-3 py-1.5"
                style={{
                  color: p.status === "running" ? "#E8751A"
                       : p.status === "done"    ? "#F0EDE8"
                       : p.status === "error"   ? "#F87171"
                       : "#C8C5C0",
                }}
              >
                {p.name}
              </td>
              <td className="font-mono text-[9px] px-3 py-1.5 hidden sm:table-cell" style={{ color: "#A8A5A0" }}>
                {p.skill.split("+")[0].trim()}
              </td>
              <td className="px-3 py-1.5">
                <span className="font-mono text-[11px]" style={{ color: STATUS_COLOR[p.status] }}>
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
