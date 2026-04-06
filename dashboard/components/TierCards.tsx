"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Session, Model } from "@/lib/types";
import { TIER_INFO } from "@/lib/types";

const MODELS: Model[] = ["opus", "sonnet", "haiku"];

function TierCard({
  model,
  sessions,
}: {
  model: Model;
  sessions: Session[];
}) {
  const info = TIER_INFO[model];
  const active = sessions.filter(
    (s) => s.status === "building" || s.status === "cloning"
  );
  const completed = sessions.filter((s) => s.status === "complete");
  const failed = sessions.filter((s) =>
    ["failed", "killed"].includes(s.status)
  );
  const isActive = active.length > 0;

  return (
    <div
      className="relative bg-pi-dark-2 border border-pi-border rounded-lg p-5 overflow-hidden transition-all duration-300 hover:border-opacity-60"
      style={
        isActive
          ? { borderColor: info.color + "60", boxShadow: `0 0 24px ${info.color}15` }
          : {}
      }
    >
      {/* Accent line */}
      <div
        className="absolute top-0 left-0 right-0 h-px"
        style={{ background: isActive ? info.color : "#2A2A2A" }}
      />

      {/* Top row */}
      <div className="flex items-start justify-between mb-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <span
              className={`w-2 h-2 rounded-full ${isActive ? "status-dot-active" : ""}`}
              style={{ backgroundColor: isActive ? info.color : "#2A2A2A" }}
            />
            <span
              className="font-bebas text-xl tracking-wider"
              style={{ color: isActive ? info.color : "#F0EDE8" }}
            >
              {info.label}
            </span>
          </div>
          <p className="font-mono text-[10px] text-pi-muted">{info.role}</p>
        </div>
        <span
          className="font-mono text-[9px] px-2 py-1 rounded border"
          style={{
            color: info.color,
            borderColor: info.color + "40",
            backgroundColor: info.color + "10",
          }}
        >
          {info.badge}
        </span>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-2 mt-3">
        {[
          { label: "Active", value: active.length, color: info.color },
          { label: "Done", value: completed.length, color: "#4CAF82" },
          { label: "Failed", value: failed.length, color: "#EF4444" },
        ].map(({ label, value, color }) => (
          <div key={label} className="bg-pi-dark-3 rounded px-2 py-1.5 text-center">
            <div className="font-bebas text-lg" style={{ color }}>
              {value}
            </div>
            <div className="font-mono text-[9px] text-pi-muted uppercase tracking-wider">
              {label}
            </div>
          </div>
        ))}
      </div>

      {/* Active session list */}
      {active.length > 0 && (
        <div className="mt-3 space-y-1">
          {active.slice(0, 2).map((s) => (
            <div
              key={s.id}
              className="flex items-center gap-2 bg-pi-dark-3 rounded px-2 py-1"
            >
              <span
                className="w-1.5 h-1.5 rounded-full status-dot-active"
                style={{ backgroundColor: info.color }}
              />
              <span className="font-mono text-[9px] text-pi-muted truncate flex-1">
                {s.repo.replace(/^https?:\/\//, "").slice(0, 30)}
              </span>
              <span className="font-mono text-[9px]" style={{ color: info.color }}>
                {s.lines}L
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export default function TierCards() {
  const [sessions, setSessions] = useState<Session[]>([]);
  const [lastRefresh, setLastRefresh] = useState(0);

  useEffect(() => {
    function refresh() {
      api
        .sessions()
        .then((s) => {
          setSessions(s);
          setLastRefresh(Date.now());
        })
        .catch(() => {});
    }
    refresh();
    const t = setInterval(refresh, 3000);
    return () => clearInterval(t);
  }, []);

  const ago = lastRefresh ? Math.floor((Date.now() - lastRefresh) / 1000) : null;

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="font-bebas text-xl tracking-widest text-pi-cream/80">
          Tier Status
        </h2>
        <span className="font-mono text-[10px] text-pi-muted">
          {ago !== null ? `Updated ${ago}s ago` : "Loading…"}
        </span>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {MODELS.map((m) => (
          <TierCard key={m} model={m} sessions={sessions} />
        ))}
      </div>
    </div>
  );
}
