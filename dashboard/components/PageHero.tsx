// components/PageHero.tsx — compact top bar (Linear/Vercel aesthetic)
import React from "react";

interface PageHeroProps {
  /** Page title */
  title: string;
  /** Optional one-line descriptor */
  subtitle?: string;
  /** Optional right-side slot (status badge, action button, etc.) */
  right?: React.ReactNode;
  /** Compact single-row mode (default: false) */
  compact?: boolean;
}

export default function PageHero({ title, subtitle, right, compact = false }: PageHeroProps) {
  return (
    <div
      className="relative shrink-0 flex items-center justify-between overflow-hidden px-4"
      style={{
        height: compact ? "52px" : "64px",
        borderBottom: "1px solid var(--border)",
        background: "var(--background)",
      }}
    >
      {/* Left: title + optional subtitle */}
      <div className="flex flex-col justify-center gap-0.5">
        <h1
          className="text-lg font-semibold leading-none"
          style={{ color: "var(--text)" }}
        >
          {title}
        </h1>
        {subtitle && (
          <p
            className="text-xs leading-none"
            style={{ color: "var(--text-dim)" }}
          >
            {subtitle}
          </p>
        )}
      </div>

      {/* Right slot */}
      {right && (
        <div className="flex items-center gap-2 shrink-0 ml-4">
          {right}
        </div>
      )}
    </div>
  );
}
