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
        // This page is light and sits outside the command-deck scope that defines
        // the --cc-* inks, so SourceBadge and the cockpit fell back to pale dark-theme
        // colours (#cfe0ec: 1.32:1 on this ground, RA-7843). Set them for this ground.
        ["--cc-ink" as string]: "#14241b",
        ["--cc-ink-dim" as string]: "#5a6b62",
        ["--cc-ink-hush" as string]: "#6b7280",
        ["--cc-signal-text" as string]: "#15803d",
        // Usage bars: --cc-signal is the warning fill (unset here, so near-limit and
        // blocked bars were transparent) and --cc-track a pale track every fill clears
        // at >= 3:1 (ink 13.1, dim 4.6, signal 4.1, hush 3.9). The pale track is 1.2:1 on
        // this ground, so --cc-track-edge outlines it at 4.8:1 (WCAG 1.4.11). Bugbot, #836.
        ["--cc-signal" as string]: "#15803d",
        ["--cc-track" as string]: "#e5e7eb",
        ["--cc-track-edge" as string]: "#6b7280",
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
            color: "#15803d", // 4.93:1 on #fffdf7 (70% alpha was 2.88:1, RA-7843)
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
