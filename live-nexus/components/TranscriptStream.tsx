"use client";
import { useEffect, useRef } from "react";
import type { TranscriptLine } from "@/lib/markdown-composer";

export interface TranscriptStreamProps {
  lines: TranscriptLine[];
  partial: string;
}

export function TranscriptStream({ lines, partial }: TranscriptStreamProps) {
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [lines, partial]);

  const isEmpty = lines.length === 0 && !partial;

  return (
    <div
      ref={scrollRef}
      className="h-full overflow-y-auto rounded-lg border border-hairline bg-surface p-6 text-ink"
    >
      <div className="mb-4 text-xs uppercase tracking-[0.1em] text-ink-muted">
        Transcript
      </div>
      {isEmpty && <p className="text-ink-muted italic">Listening…</p>}
      <div className="space-y-4">
        {lines.map((line, i) => (
          <div key={i}>
            <div className="mb-1 text-xs uppercase tracking-[0.05em] text-ink-muted">
              [{line.timestamp}] Speaker {line.speaker}
            </div>
            <p className="text-[17px] leading-relaxed">{line.text}</p>
          </div>
        ))}
        {partial && (
          <div>
            <p className="text-[17px] leading-relaxed text-ink-muted">
              {partial}
              <span className="live-cursor" aria-hidden />
            </p>
          </div>
        )}
      </div>
    </div>
  );
}
