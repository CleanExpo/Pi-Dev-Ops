// app/(main)/command-centre/providers/page.tsx
//
// Provider usage cockpit (capability 4, read-only half).
//
// REBUILT, NOT PORTED. The source page composes three tiles — ProviderAccountsTile,
// ProviderUsageCockpit and CostAllocationTile. Only the usage cockpit is ported here, so a
// verbatim port would import two components this app deliberately does not have. Written
// fresh over what exists, the same way the command-centre index was.
//
// What is deliberately absent, and why it is absent rather than disabled:
//   · account management (KI-007) — credential custody is deferred until per-capability
//     tokens exist. Today it would put provider keys behind one shared secret with no
//     scoping, no audit and no identity to attribute a read to.
//   · "test provider" (KI-006) — its whole function is to spend. There is no version of it
//     that is a button with a gate.
// Neither is stubbed. A control that renders while doing nothing misrepresents the surface,
// which is the KI-002/KI-005 rule.

export const dynamic = "force-dynamic";

import Link from "next/link";
import { ProviderUsageCockpit } from "@/components/command-centre/provider-usage/ProviderUsageCockpit";

export default function ProvidersPage() {
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        minHeight: "100vh",
        background: "#fffdf7",
        color: "#14241b",
        padding: "1.25rem 1.5rem",
        gap: "1rem",
        fontFamily:
          "var(--font-chakra), var(--font-geist-sans), system-ui, sans-serif",
      }}
    >
      <header style={{ display: "flex", flexDirection: "column", gap: 2 }}>
        <Link
          href="/command-centre"
          style={{
            fontSize: 11,
            color: "rgba(21,128,61,0.7)",
            textDecoration: "none",
          }}
        >
          &larr; Command Deck
        </Link>
        <h1
          style={{
            fontSize: "1.4rem",
            fontWeight: 600,
            letterSpacing: "-0.01em",
            color: "#15803d",
            margin: 0,
          }}
        >
          Providers
        </h1>
        <p style={{ fontSize: 12, color: "#5a6b62", margin: "2px 0 0" }}>
          Usage and quota signals, derived from which provider keys are present in the
          environment. Metadata only &mdash; no key is read, and nothing here can spend.
        </p>
      </header>

      <ProviderUsageCockpit />

      <footer
        style={{
          marginTop: "auto",
          paddingTop: "1rem",
          fontSize: 11,
          color: "#5a6b62",
          borderTop: "1px solid rgba(45,187,87,0.20)",
        }}
      >
        Account management and provider testing are not available in this dashboard.
        Account management waits on per-capability tokens (KI-007); provider testing is a
        spend path and is not built here (KI-006). Both live in the source app.
      </footer>
    </div>
  );
}
