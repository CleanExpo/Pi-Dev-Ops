import type { Action } from "@/lib/markdown-composer";

export interface SynthesisSidebarProps {
  topics: string[];
  actions: Action[];
  synthesisPaused: boolean;
}

const PRIORITY_LABEL: Record<number, string> = {
  0: "",
  1: "URGENT",
  2: "HIGH",
  3: "",
  4: "LOW",
};

export function SynthesisSidebar({
  topics,
  actions,
  synthesisPaused,
}: SynthesisSidebarProps) {
  return (
    <aside className="flex h-full flex-col gap-4">
      <section className="rounded-lg border border-hairline bg-surface p-6">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="text-xs font-medium uppercase tracking-[0.1em] text-ink-muted">
            Topics Discussed
          </h2>
          {synthesisPaused && (
            <span className="rounded-full border border-accent/40 px-2 py-0.5 text-[10px] uppercase tracking-wider text-accent">
              synthesis paused
            </span>
          )}
        </div>
        {topics.length === 0 ? (
          <p className="text-sm italic text-ink-muted">None yet.</p>
        ) : (
          <ul className="space-y-2">
            {topics.map((t, i) => (
              <li key={i} className="text-sm text-ink">
                <span className="text-ink-muted">•</span> {t}
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="flex-1 rounded-lg border border-hairline bg-surface p-6">
        <h2 className="mb-3 text-xs font-medium uppercase tracking-[0.1em] text-ink-muted">
          Action Items
        </h2>
        {actions.length === 0 ? (
          <p className="text-sm italic text-ink-muted">None yet.</p>
        ) : (
          <ul className="space-y-3">
            {actions.map((a, i) => (
              <li key={i} className="text-sm text-ink">
                <div className="flex items-start gap-2">
                  <span className="mt-0.5 text-accent">▸</span>
                  <div className="flex-1">
                    <div className="font-medium">{a.title}</div>
                    {a.description && (
                      <div className="mt-0.5 text-ink-muted">{a.description}</div>
                    )}
                    {PRIORITY_LABEL[a.priority] && (
                      <span className="mt-1 inline-block text-[10px] uppercase tracking-wider text-accent">
                        {PRIORITY_LABEL[a.priority]}
                      </span>
                    )}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        )}
      </section>
    </aside>
  );
}
