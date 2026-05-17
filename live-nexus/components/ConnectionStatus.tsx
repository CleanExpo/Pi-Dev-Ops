export type ConnectionState = "connected" | "reconnecting" | "error";

export interface ConnectionStatusProps {
  state: ConnectionState;
  message?: string;
}

export function ConnectionStatus({ state, message }: ConnectionStatusProps) {
  if (state === "connected") return null;
  const isError = state === "error";
  return (
    <div
      role="alert"
      className={`fixed left-1/2 top-20 z-50 -translate-x-1/2 rounded-lg border px-4 py-2 text-sm
        ${isError ? "border-accent bg-accent/10 text-ink" : "border-ink-muted bg-surface text-ink-muted"}`}
    >
      {isError ? message ?? "Connection error" : "Reconnecting to transcription service…"}
    </div>
  );
}
