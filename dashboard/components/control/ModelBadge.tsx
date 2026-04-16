// components/control/ModelBadge.tsx — Panel 2: model + ZTE score + SDK mode (RA-1092)
"use client";

import { useEffect, useState } from "react";

interface ZteData {
  score: number;
  model: string;
  model_id: string;
  sdk_mode: boolean;
  source: "backend" | "harness" | "default";
}

function scoreColour(score: number): string {
  if (score >= 90) return "var(--success)";
  if (score >= 70) return "var(--warning)";
  return "var(--error)";
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

      <div className="flex-1 overflow-auto p-4 space-y-4">
        {loading && (
          <p className="text-xs" style={{ color: "var(--text-dim)" }}>
            Loading…
          </p>
        )}

        {error && !loading && (
          <p className="text-xs" style={{ color: "var(--error)" }}>
            {error}
          </p>
        )}

        {data && !loading && (
          <>
            <div>
              <div className="text-[11px] mb-1" style={{ color: "var(--text-dim)" }}>
                Current model
              </div>
              <div className="flex items-baseline gap-2">
                <span className="text-lg font-semibold" style={{ color: "var(--text)" }}>
                  {data.model}
                </span>
                <span className="text-[10px] font-mono" style={{ color: "var(--text-dim)" }}>
                  {data.model_id}
                </span>
              </div>
            </div>

            <div className="pt-3" style={{ borderTop: "1px solid var(--border)" }}>
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-[11px]" style={{ color: "var(--text-dim)" }}>
                  ZTE v2 score
                </span>
                <span
                  className="text-lg font-mono font-semibold"
                  style={{ color: scoreColour(data.score) }}
                >
                  {data.score}
                  <span className="text-xs" style={{ color: "var(--text-dim)" }}>
                    /100
                  </span>
                </span>
              </div>
              <div
                className="w-full h-1.5 rounded-full overflow-hidden"
                style={{ background: "var(--border)" }}
                role="progressbar"
                aria-valuenow={data.score}
                aria-valuemin={0}
                aria-valuemax={100}
              >
                <div
                  className="h-full transition-all"
                  style={{ width: `${Math.max(0, Math.min(100, data.score))}%`, background: scoreColour(data.score) }}
                />
              </div>
            </div>

            <div className="pt-3" style={{ borderTop: "1px solid var(--border)" }}>
              <div className="text-[11px] mb-1" style={{ color: "var(--text-dim)" }}>
                SDK mode
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs font-mono" style={{ color: "var(--text)" }}>
                  TAO_USE_AGENT_SDK={data.sdk_mode ? "1" : "0"}
                </span>
                <span
                  className="text-xs"
                  style={{ color: data.sdk_mode ? "var(--success)" : "var(--text-dim)" }}
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
