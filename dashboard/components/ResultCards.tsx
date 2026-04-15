// components/ResultCards.tsx — Right panel: summary cards populated as phases complete
"use client";

import type { AnalysisResult } from "@/lib/types";

const ZTE_LABELS: Record<number, { label: string; band: string; color: string }> = {
  1: { label: "MANUAL",      band: "12–20",  color: "#F87171" },
  2: { label: "ASSISTED",    band: "21–35",  color: "#FFD166" },
  3: { label: "AUTONOMOUS",  band: "36–48",  color: "#60A5FA" },
  4: { label: "ZERO TOUCH",  band: "49–60",  color: "#4ADE80" },
};

function Bar({ value, max = 10 }: { value: number; max?: number }) {
  const pct = Math.round((value / max) * 10);
  return (
    <span className="font-mono text-[11px]">
      <span style={{ color: "var(--accent)" }}>{"█".repeat(pct)}</span>
      <span style={{ color: "var(--border)" }}>{"░".repeat(10 - pct)}</span>
      <span style={{ color: "var(--text-muted)" }}> {value}/{max}</span>
    </span>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ borderBottom: "1px solid var(--border)" }}>
      <div className="px-3 py-1.5" style={{ borderBottom: "1px solid var(--border-subtle)" }}>
        <span className="font-mono text-[10px] uppercase tracking-widest" style={{ color: "var(--text-muted)" }}>
          {title}
        </span>
      </div>
      <div className="px-3 py-2">{children}</div>
    </div>
  );
}

interface Props {
  result: Partial<AnalysisResult>;
}

export default function ResultCards({ result }: Props) {
  return (
    <div style={{ background: "var(--panel)" }}>
      {/* Tech Stack */}
      {result.techStack && (
        <Section title="tech stack">
          <div className="flex flex-wrap gap-1.5">
            {result.techStack.map((t) => (
              <span
                key={t}
                className="font-mono text-[10px] px-2 py-0.5"
                style={{ background: "var(--background)", color: "var(--text)", border: "1px solid var(--border)" }}
              >
                {t}
              </span>
            ))}
          </div>
          {result.languages && (
            <div className="mt-2 space-y-1">
              {Object.entries(result.languages)
                .sort(([, a], [, b]) => b - a)
                .slice(0, 6)
                .map(([lang, loc]) => (
                  <div key={lang} className="flex items-center justify-between">
                    <span className="font-mono text-[10px]" style={{ color: "var(--text)" }}>{lang}</span>
                    <span className="font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>{loc.toLocaleString()}L</span>
                  </div>
                ))}
            </div>
          )}
        </Section>
      )}

      {/* Quality Scores */}
      {result.quality && (
        <Section title="quality scores">
          <div className="space-y-1.5">
            {[
              ["Completeness", result.quality.completeness],
              ["Correctness",  result.quality.correctness],
              ["Code Quality", result.quality.codeQuality],
              ["Docs",         result.quality.documentation],
            ].map(([label, val]) => (
              <div key={label as string}>
                <span className="font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>{label as string}</span>
                <div className="mt-0.5">
                  <Bar value={val as number} />
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* ZTE Maturity */}
      {result.zteScore !== undefined && (
        <Section title="zte maturity">
          <div className="flex items-baseline gap-3 mb-2">
            <span className="font-display text-3xl" style={{ color: "var(--accent)" }}>
              L{result.zteLevel}
            </span>
            <div>
              <div
                className="font-mono text-[11px]"
                style={{ color: ZTE_LABELS[result.zteLevel ?? 1]?.color ?? "#F0EDE8" }}
              >
                {ZTE_LABELS[result.zteLevel ?? 1]?.label ?? "—"}
              </div>
              <div className="font-mono text-[9px]" style={{ color: "var(--text-muted)" }}>
                {result.zteScore}/60 · band {ZTE_LABELS[result.zteLevel ?? 1]?.band ?? "—"}
              </div>
            </div>
          </div>
          {result.leveragePoints && (
            <div className="space-y-0.5">
              {result.leveragePoints.map((lp) => (
                <div key={lp.id} className="flex items-center gap-2">
                  <span className="font-mono text-[9px] w-4 text-right" style={{ color: "var(--text-muted)" }}>{lp.id}</span>
                  <span className="font-mono text-[9px] flex-1 truncate" style={{ color: "var(--text)" }}>{lp.name}</span>
                  <span
                    className="font-mono text-[9px]"
                    style={{ color: lp.score >= 4 ? "#4ADE80" : lp.score >= 3 ? "#FFD166" : "#F87171" }}
                  >
                    {lp.score}/5
                  </span>
                </div>
              ))}
            </div>
          )}
        </Section>
      )}

      {/* Sprint Plan */}
      {result.sprints && result.sprints.length > 0 && (
        <Section title="sprint plan">
          <div className="space-y-2">
            {result.sprints.slice(0, 3).map((s) => (
              <div key={s.id}>
                <div className="flex items-center justify-between mb-1">
                  <span className="font-mono text-[10px]" style={{ color: "var(--text)" }}>
                    S{s.id}: {s.name}
                  </span>
                  <span className="font-mono text-[9px]" style={{ color: "var(--text-muted)" }}>{s.duration}</span>
                </div>
                <div className="space-y-0.5">
                  {s.items.slice(0, 3).map((item, i) => (
                    <div key={i} className="flex items-center gap-1.5">
                      <span
                        className="font-mono text-[9px] w-4 text-center"
                        style={{ color: item.size === "S" ? "#4ADE80" : item.size === "M" ? "#FFD166" : "#F87171" }}
                      >
                        {item.size}
                      </span>
                      <span className="font-mono text-[9px] truncate" style={{ color: "var(--text)" }}>{item.title}</span>
                    </div>
                  ))}
                </div>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* Executive Summary */}
      {result.executiveSummary && (
        <Section title="exec summary">
          <p className="font-body text-[11px] leading-relaxed mb-2" style={{ color: "var(--text)" }}>
            {result.executiveSummary.slice(0, 300)}
            {result.executiveSummary.length > 300 ? "…" : ""}
          </p>
          {result.nextActions && (
            <div className="space-y-1">
              {result.nextActions.slice(0, 3).map((a, i) => (
                <div key={i} className="flex items-start gap-1.5">
                  <span className="font-mono text-[9px] mt-0.5" style={{ color: "var(--accent)" }}>{i + 1}.</span>
                  <span className="font-mono text-[9px]" style={{ color: "var(--text)" }}>{a}</span>
                </div>
              ))}
            </div>
          )}
        </Section>
      )}

      {/* Empty state */}
      {!result.techStack && !result.quality && (
        <div className="px-3 py-8 text-center">
          <p className="font-mono text-[10px]" style={{ color: "var(--text-muted)" }}>
            Results populate as phases complete.
          </p>
        </div>
      )}
    </div>
  );
}
