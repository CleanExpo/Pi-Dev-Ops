// components/control/ModelBadge.tsx — Panel 2: model + ZTE score ring + SDK mode (RA-1092)
"use client";

import { useEffect, useState } from "react";
import ProgressRing from "./ProgressRing";

interface ZteData {
  score: number;
  model: string;
  model_id: string;
  sdk_mode: boolean;
  source: "backend" | "harness" | "default";
}

function scoreColour(score: number): string {
  if (score >= 90) return "var(--success)";
  if (score >= 70) return "var(--accent)";
  return "var(--error)";
}

function scoreLabel(score: number): string {
  if (score >= 90) return "Excellent";
  if (score >= 80) return "Strong";
  if (score >= 70) return "Good";
  if (score >= 60) return "Fair";
  return "Needs work";
}

export default function ModelBadge() {
  const [data, setData] = useState<ZteData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      try {
        const res = await fetch("/api/zte");
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const json = (await res.json()) as ZteData;
        if (!cancelled) {
          setData(json);
          setError(null);
        }
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load ZTE score");
      } finally {
        if (!cancelled) setLoading(false);
      }
    }

    void load();
    const t = setInterval(() => void load(), 60_000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  return (
    <section
      className="flex flex-col h-full"
      style={{ background: "var(--panel)", border: "1px solid var(--border)", borderRadius: 8 }}
      aria-label="Model and ZTE score"
    >
      <header
        className="flex items-center justify-between px-4 py-2.5"
        style={{ borderBottom: "1px solid var(--border)" }}
      >
        <h2 className="text-xs font-semibold uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
          Model &amp; ZTE
        </h2>
        {data && (
          <span
            className="text-[10px] font-mono uppercase px-2 py-0.5 rounded"
            style={{
              color: "var(--text-dim)",
              background: "var(--panel-hover)",
              border: "1px solid var(--border)",
            }}
            title={`Source: ${data.source}`}
          >
            {data.source}
          </span>
        )}
      </header>

      <div className="flex-1 overflow-auto p-4 flex flex-col gap-4">
        {loading && (
          <p className="text-xs" style={{ color: "var(--text-dim)" }}>
            Loading…
          </p>
        )}

        {error && !loading && (
          <p className="text-xs font-mono" style={{ color: "var(--error)" }}>
            <span aria-hidden="true">⚠ </span>{error}
          </p>
        )}

        {data && !loading && (
          <>
            {/* Model name with amber left-accent */}
            <div
              className="pl-3 py-1"
              style={{ borderLeft: "3px solid var(--accent)" }}
            >
              <div className="text-[10px] mb-0.5" style={{ color: "var(--text-dim)" }}>
                Active model
              </div>
              <div className="text-base font-semibold leading-tight" style={{ color: "var(--text)" }}>
                {data.model}
              </div>
              <div className="text-[10px] font-mono mt-0.5" style={{ color: "var(--text-muted)" }}>
                {data.model_id}
              </div>
            </div>

            {/* ZTE ring — centred hero */}
            <div className="flex items-center justify-center py-2">
              <div className="flex flex-col items-center gap-2">
                <ProgressRing
                  value={data.score}
                  size={96}
                  strokeWidth={7}
                  colour={scoreColour(data.score)}
                  label={`${data.score}`}
                  sublabel="/100"
                />
                <div className="text-center">
                  <span
                    className="text-[10px] font-semibold uppercase tracking-wide"
                    style={{ color: scoreColour(data.score) }}
                  >
                    {scoreLabel(data.score)}
                  </span>
                  <span className="text-[10px] ml-1" style={{ color: "var(--text-dim)" }}>
                    ZTE v2
                  </span>
                </div>
              </div>
            </div>

            {/* SDK mode */}
            <div
              className="flex items-center justify-between pt-3"
              style={{ borderTop: "1px solid var(--border)" }}
            >
              <span className="text-[11px]" style={{ color: "var(--text-dim)" }}>
                SDK mode
              </span>
              <div className="flex items-center gap-2">
                <span className="text-[11px] font-mono" style={{ color: "var(--text)" }}>
                  TAO_USE_AGENT_SDK={data.sdk_mode ? "1" : "0"}
                </span>
                <span
                  style={{ color: data.sdk_mode ? "var(--success)" : "var(--text-dim)", fontSize: 13 }}
                  aria-hidden="true"
                >
                  {data.sdk_mode ? "✓" : "○"}
                </span>
              </div>
            </div>
          </>
        )}
      </div>
    </section>
  );
}
