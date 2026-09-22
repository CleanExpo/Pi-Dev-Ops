"use client";

import { useEffect, useState } from "react";
import type { FlowBoardPayload } from "@/lib/control/flowBoard";
import { emptyFlowBoard, parseFlowBoardPayload } from "@/lib/control/flowBoard";

const COLUMNS: Array<{ key: keyof FlowBoardPayload["columns"]; title: string }> = [
  { key: "shipped", title: "Shipped today" },
  { key: "audit", title: "In audit / with Rana" },
  { key: "phill", title: "Awaiting Phill" },
  { key: "aging", title: "Aging" },
];

export default function FlowBoard() {
  const [board, setBoard] = useState<FlowBoardPayload>(() => emptyFlowBoard("Loading…", false));

  useEffect(() => {
    let live = true;
    void fetch("/api/flow-board", { cache: "no-store" })
      .then(async (res) => {
        if (!res.ok) return emptyFlowBoard(`HTTP ${res.status}`, false);
        const parsed = parseFlowBoardPayload(await res.json());
        return parsed ?? emptyFlowBoard("Flow board payload was not a board", false);
      })
      .then((next) => {
        if (live) setBoard(next);
      })
      .catch(() => {
        if (live) setBoard(emptyFlowBoard("GitHub unavailable", false));
      });
    return () => {
      live = false;
    };
  }, []);

  return (
    <section aria-label="Flow board" className="rounded-lg border p-4" style={{ borderColor: "var(--border)", background: "var(--panel)" }}>
      <div className="flex items-baseline justify-between gap-3 mb-3">
        <h2 className="text-sm font-semibold" style={{ color: "var(--text)" }}>
          Flow lanes
        </h2>
        <span className="text-[10px] font-mono" style={{ color: "var(--text-dim)" }}>
          {board.ok ? `checked ${board.checked_at.slice(11, 16)}` : board.error}
        </span>
      </div>
      <p className="text-xs mb-3" style={{ color: "var(--text-muted)" }}>
        FLOW ships with three receipts. ENGINEER waits on Rana. FOUNDER waits on Phill.
        Nothing stays in a sandbox past day 7.
      </p>
      {board.awaiting_phill_long ? (
        <p className="text-xs mb-3" style={{ color: "var(--error)" }}>
          Awaiting Phill is long — the system is failing, not Phill.
        </p>
      ) : null}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-3">
        {COLUMNS.map((col) => (
          <div key={col.key}>
            <div className="text-[10px] uppercase tracking-widest mb-2" style={{ color: "var(--text-dim)" }}>
              {col.title} · {board.columns[col.key].length}
            </div>
            {board.columns[col.key].length === 0 ? (
              <p className="text-xs" style={{ color: "var(--text-dim)" }}>
                {board.ok ? "None." : "—"}
              </p>
            ) : (
              <ul className="flex flex-col gap-1.5">
                {board.columns[col.key].map((row) => (
                  <li key={row.id} className="text-xs">
                    {row.url === "#" ? (
                      <span style={{ color: "var(--text-muted)" }}>{row.id}</span>
                    ) : (
                      <a href={row.url} className="hover:underline" rel="noopener noreferrer" target="_blank" style={{ color: "var(--accent)" }}>
                        {row.id}
                      </a>
                    )}
                    <span style={{ color: "var(--text-muted)" }}>
                      {" "}
                      · {row.lane} · day {row.ageDays}
                      {row.tone === "kill" ? " · kill or lane" : ""}
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}
