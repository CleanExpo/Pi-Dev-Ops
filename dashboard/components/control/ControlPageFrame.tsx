import type { ReactNode } from "react";

export default function ControlPageFrame({
  title,
  hint,
  children,
}: {
  title: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex-1 overflow-auto p-4 min-h-0">
      <header className="mb-4">
        <h1 className="text-sm font-semibold tracking-tight" style={{ color: "var(--text)" }}>
          {title}
        </h1>
        {hint ? (
          <p className="text-[11px] mt-1 font-mono" style={{ color: "var(--text-muted)" }}>
            {hint}
          </p>
        ) : null}
      </header>
      {children}
    </div>
  );
}
