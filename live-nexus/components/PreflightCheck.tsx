export type CheckState = "pending" | "ok" | "fail";

export interface PreflightCheckProps {
  mic: CheckState;
  network: CheckState;
  browser: CheckState;
}

function Icon({ state }: { state: CheckState }) {
  if (state === "ok") return <span className="text-accent">✓</span>;
  if (state === "fail") return <span className="text-accent">✗</span>;
  return <span className="text-ink-muted">…</span>;
}

export function PreflightCheck({ mic, network, browser }: PreflightCheckProps) {
  return (
    <ul className="space-y-2 text-sm text-ink-muted">
      <li className="flex items-center gap-3">
        <Icon state={mic} /> <span>Microphone</span>
      </li>
      <li className="flex items-center gap-3">
        <Icon state={network} /> <span>Network — AssemblyAI reachable</span>
      </li>
      <li className="flex items-center gap-3">
        <Icon state={browser} /> <span>Browser supports recording</span>
      </li>
    </ul>
  );
}
