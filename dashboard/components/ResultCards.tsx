// components/ResultCards.tsx — Right panel: summary cards that populate as phases complete

"use client";

import type { AnalysisResult } from "@/lib/types";

const ZTE_LABELS: Record<number, string> = {
  1: "IN THE LOOP",
  2: "OUT OF LOOP",
  3: "ZERO TOUCH",
};

function Bar({ value, max = 10 }: { value: number; max?: number }) {
  const pct = Math.round((value / max) * 10);
  return (
    <span className="font-mono text-[11px]">
      <span style={{ color: "#E8751A" }}>{"█".repeat(pct)}</span>
      <span style={{ color: "#222" }}>{"░".repeat(10 - pct)}</span>
      <span className="text-[#666]"> {value}/{max}</span>
    </span>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ borderBottom: "1px solid #1A1A1A" }}>
      <div className="px-3 py-1.5" style={{ borderBottom: "1px solid #111" }}>
        <span className="font-mono text-[10px] text-[#666] uppercase tracking-widest">
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
    <div className="overflow-y-auto" style={{ background: "#0F0F0F" }}>
      {/* Tech Stack */}
      {result.techStack && (
        <Section title="tech stack">
          <div className="flex flex-wrap gap-1.5">
            {result.techStack.map((t) => (
              <span
                key={t}
                className="font-mono text-[10px] px-2 py-0.5"
                style={{ background: "#1A1A1A", color: "#F0EDE8" }}
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
                    <span className="font-mono text-[10px] text-[#888]">{lang}</span>
                    <span className="font-mono text-[10px] text-[#444]">{loc.toLocaleString()}L</span>
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
                <div className="flex items-center justify-between mb-0.5">
                  <span className="font-mono text-[10px] text-[#666]">{label as string}</span>
                </div>
                <Bar value={val as number} />
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* ZTE Maturity */}
      {result.zteScore !== undefined && (
        <Section title="zte maturity">
          <div className="flex items-baseline gap-3 mb-2">
            <span className="font-display text-3xl" style={{ color: "#E8751A" }}>
              L{result.zteLevel}
            </span>
            <div>
              <div className="font-mono text-[11px] text-[#F0EDE8]">
                {ZTE_LABELS[result.zteLevel ?? 1]}
              </div>
              <div className="font-mono text-[9px] text-[#555]">
                {result.zteScore}/60
              </div>
            </div>
          </div>
          {result.leveragePoints && (
            <div className="space-y-0.5">
              {result.leveragePoints.slice(0, 6).map((lp) => (
                <div key={lp.id} className="flex items-center gap-2">
                  <span className="font-mono text-[9px] text-[#444] w-4 text-right">{lp.id}</span>
                  <span className="font-mono text-[9px] text-[#666] flex-1 truncate">{lp.name}</span>
                  <span
                    className="font-mono text-[9px]"
                    style={{ color: lp.score >= 4 ? "#4CAF82" : lp.score >= 3 ? "#FFD166" : "#EF4444" }}
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
                  <span className="font-mono text-[10px] text-[#F0EDE8]">
                    S{s.id}: {s.name}
                  </span>
                  <span className="font-mono text-[9px] text-[#555]">{s.duration}</span>
                </div>
                <div className="space-y-0.5">
                  {s.items.slice(0, 3).map((item, i) => (
                    <div key={i} className="flex items-center gap-1.5">
                      <span
                        className="font-mono text-[9px] w-4 text-center"
                        style={{ color: item.size === "S" ? "#4CAF82" : item.size === "M" ? "#FFD166" : "#EF4444" }}
                      >
                        {item.size}
                      </span>
                      <span className="font-mono text-[9px] text-[#666] truncate">{item.title}</span>
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
          <p className="font-body text-[11px] text-[#888] leading-relaxed mb-2">
            {result.executiveSummary.slice(0, 300)}
            {result.executiveSummary.length > 300 ? "…" : ""}
          </p>
          {result.nextActions && (
            <div className="space-y-1">
              {result.nextActions.slice(0, 3).map((a, i) => (
                <div key={i} className="flex items-start gap-1.5">
                  <span className="font-mono text-[9px] text-[#E8751A] mt-0.5">{i + 1}.</span>
                  <span className="font-mono text-[9px] text-[#666]">{a}</span>
                </div>
              ))}
            </div>
          )}
        </Section>
      )}

      {/* Empty state */}
      {!result.techStack && !result.quality && (
        <div className="px-3 py-8 text-center">
          <p className="font-mono text-[10px] text-[#333]">
            Results populate as phases complete.
          </p>
        </div>
      )}
    </div>
  );
}
