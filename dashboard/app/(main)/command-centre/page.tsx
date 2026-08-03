// app/(main)/command-centre/page.tsx — command-centre index.
//
// NEW IN THE TARGET, not ported. The source's deck index lives at
// /founder/command-centre and carries the full calm-cockpit shell plus tiles for
// nine decks. Porting it would drag in the founder layout and six capabilities
// that have not been migrated yet, so this is a deliberately small index over the
// capabilities that actually exist here.
//
// It grows as capabilities land. A link is added only when its route exists —
// the route-existence check in __tests__/command-centre-readonly.test.ts fails
// the suite otherwise, so a link to an unbuilt deck cannot ship.
//
// READ-ONLY. No data access, no writes.

import Link from "next/link";

export const dynamic = "force-dynamic";

const DECKS = [
  {
    href: "/command-centre/hermes",
    name: "Hermes",
    blurb: "Hermes v0.16 surface release — module list, read-only.",
  },
  {
    href: "/command-centre/knowledge",
    name: "Knowledge",
    blurb: "Wiki knowledge base and capability bus.",
  },
  {
    href: "/command-centre/providers",
    name: "Providers",
    blurb: "Provider usage and quota signals. Read-only — no accounts, no testing.",
  },
  {
    href: "/command-centre/wiki-graph",
    name: "Wiki Graph",
    blurb: "The knowledge base as an interactive force-directed graph.",
  },
];

export default function CommandCentreIndex() {
  return (
    <div className="p-6 max-w-3xl">
      <h1 className="text-xl font-semibold mb-1" style={{ color: "var(--text)" }}>
        Command Centre
      </h1>
      <p className="text-sm mb-6" style={{ color: "var(--text-muted)" }}>
        Capabilities migrated into this dashboard. Decks appear here as they land.
      </p>

      <ul className="flex flex-col gap-2">
        {DECKS.map((d) => (
          <li key={d.href}>
            <Link
              href={d.href}
              className="block rounded-md px-4 py-3 transition-colors"
              style={{ background: "var(--panel)", border: "1px solid var(--border)" }}
            >
              <span className="text-sm font-medium" style={{ color: "var(--text)" }}>
                {d.name}
              </span>
              <span className="block text-xs mt-0.5" style={{ color: "var(--text-muted)" }}>
                {d.blurb}
              </span>
            </Link>
          </li>
        ))}
      </ul>

      <p className="text-xs mt-6" style={{ color: "var(--text-dim)" }}>
        Not yet migrated: operations, portfolio, operator gateway, studio.
      </p>
    </div>
  );
}
