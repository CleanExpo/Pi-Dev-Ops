// components/PhaseTracker.tsx — Dense phase status table

"use client";

import type { Phase } from "@/lib/types";

const STATUS_COLOR = {
  pending: "#777",
  running: "#E8751A",
  done:    "#4CAF82",
  error:   "#EF4444",
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
    <div style={{ borderBottom: "1px solid #252525" }}>
      <div className="px-3 py-1.5" style={{ borderBottom: "1px solid #252525" }}>
        <span className="font-mono text-[10px] text-[#999] uppercase tracking-widest">phases</span>
      </div>
      <table className="w-full">
        <thead>
          <tr style={{ borderBottom: "1px solid #1E1E1E" }}>
            {["#", "PHASE", "SKILL", "STATUS"].map((h) => (
              <th
                key={h}
                className="font-mono text-[9px] text-[#888] uppercase text-left px-3 py-1"
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
                borderBottom: "1px solid #1E1E1E",
                background: p.status === "running" ? "rgba(232,117,26,0.07)" : "transparent",
              }}
            >
              <td className="font-mono text-[10px] text-[#888] px-3 py-1.5">
                {p.id}
              </td>
              <td
                className="font-mono text-[11px] px-3 py-1.5"
                style={{ color: p.status === "running" ? "#E8751A" : p.status === "done" ? "#F0EDE8" : "#999" }}
              >
                {p.name}
              </td>
              <td className="font-mono text-[9px] text-[#777] px-3 py-1.5 hidden sm:table-cell">
                {p.skill.split("+")[0].trim()}
              </td>
              <td className="px-3 py-1.5">
                <span
                  className="font-mono text-[11px]"
                  style={{ color: STATUS_COLOR[p.status] }}
                >
                  {STATUS_CHAR[p.status]}{" "}
                  <span className="text-[9px] uppercase tracking-wider">
                    {p.status}
                  </span>
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
