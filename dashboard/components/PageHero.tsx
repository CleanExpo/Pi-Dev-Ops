// components/PageHero.tsx — cinematic page header that bridges landing → app
// Carries the "PI CEO" visual identity (Bebas Neue, orange accent, film-grain warmth)
// into every interior page — keeping the user in the same design world.
import React from "react";

interface PageHeroProps {
  /** Page title — displayed in Bebas Neue, all caps */
  title: string;
  /** Optional one-line descriptor in Barlow Condensed */
  subtitle?: string;
  /** Optional right-side slot (status badge, action button, etc.) */
  right?: React.ReactNode;
  /** Compact single-row mode for tight pages (default: false) */
  compact?: boolean;
}

export default function PageHero({ title, subtitle, right, compact = false }: PageHeroProps) {
  return (
    <div
      className="relative shrink-0 flex items-end justify-between overflow-hidden"
      style={{
        padding: compact ? "8px 16px 8px" : "18px 20px 12px",
        borderBottom: "1px solid var(--c-border)",
        background: "linear-gradient(135deg, rgba(232,117,26,0.05) 0%, transparent 60%), var(--c-bg)",
        minHeight: compact ? "44px" : "64px",
      }}
    >
      {/* ── Ambient warm glow top-left ── */}
      <div
        aria-hidden
        style={{
          position: "absolute",
          inset: 0,
          background: "radial-gradient(ellipse at 0% 50%, rgba(232,117,26,0.06) 0%, transparent 55%)",
          pointerEvents: "none",
        }}
      />

      {/* ── Left: title stack ── */}
      <div className="relative flex flex-col gap-0.5">
        <div className="flex items-baseline gap-3">
          {/* Orange π left-anchor */}
          <span
            className="font-mono leading-none"
            style={{ color: "var(--c-orange)", fontSize: compact ? "11px" : "13px", letterSpacing: "0.2em" }}
          >
            π
          </span>

          {/* Page title in Bebas Neue */}
          <h1
            className="font-display leading-none"
            style={{
              fontSize: compact ? "clamp(18px, 4vw, 28px)" : "clamp(24px, 5vw, 40px)",
              color: "var(--c-text)",
              letterSpacing: "0.08em",
            }}
          >
            {title}
          </h1>
        </div>

        {subtitle && (
          <p
            className="font-condensed"
            style={{
              fontSize: "10px",
              color: "var(--c-chrome)",
              letterSpacing: "0.25em",
              textTransform: "uppercase",
              paddingLeft: compact ? "20px" : "24px",
            }}
          >
            {subtitle}
          </p>
        )}
      </div>

      {/* ── Right slot ── */}
      {right && (
        <div className="relative flex items-center gap-2 shrink-0 ml-4">
          {right}
        </div>
      )}

      {/* ── Orange accent underline ── */}
      <div
        aria-hidden
        style={{
          position: "absolute",
          bottom: 0,
          left: 0,
          right: 0,
          height: "1px",
          background: "linear-gradient(to right, var(--c-orange), rgba(232,117,26,0.2) 40%, transparent 70%)",
        }}
      />
    </div>
  );
}
