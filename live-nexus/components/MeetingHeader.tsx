export type MeetingHeaderState =
  | "preflight"
  | "recording"
  | "paused"
  | "reconnecting"
  | "ended";

export interface MeetingHeaderProps {
  state: MeetingHeaderState;
  elapsedSeconds: number;
  clockTime: string; // "14:32"
}

function formatElapsed(s: number): string {
  if (s < 3600) {
    const m = Math.floor(s / 60);
    const sec = s % 60;
    return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
  }
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return `${h}:${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

export function MeetingHeader({ state, elapsedSeconds, clockTime }: MeetingHeaderProps) {
  const dotPaused = state === "ended" || state === "paused";
  return (
    <header className="flex items-center justify-between border-b border-hairline px-6 py-4">
      <div className="flex items-center gap-4">
        <span
          className={`live-dot ${dotPaused ? "live-dot--paused" : ""}`}
          aria-label="recording status"
        />
        <h1 className="font-brand italic text-lg tracking-wide text-ink">
          UNITE GROUP NEXUS
        </h1>
      </div>
      <div className="flex items-center gap-4 font-mono text-sm text-ink-muted tabular-nums">
        <span>{clockTime}</span>
        <span aria-hidden>·</span>
        <span className="text-ink">{formatElapsed(elapsedSeconds)}</span>
      </div>
    </header>
  );
}
