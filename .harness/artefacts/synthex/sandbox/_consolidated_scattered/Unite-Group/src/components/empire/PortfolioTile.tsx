"use client";

import * as React from "react";
import type { BrandConfig } from "@/types/brand-config";
import {
  SpotlightCard,
  SpotlightCardHeader,
  SpotlightCardTitle,
  SpotlightCardDescription,
  SpotlightCardContent,
} from "@/components/ui/spotlight-card";

// ─── Status model ────────────────────────────────────────────────────────────

/** Operational status of a portfolio business / system. */
export type PortfolioStatus = "operational" | "building" | "degraded" | "down";

/**
 * Status-to-tone mapping (Nexus UI Gun-Metal palette). Centralised here so
 * Command Center cards, client-portal tiles, and future surfaces share one
 * source of truth.
 *
 * - operational → green-400 (#1fc76e)
 * - building    → orange-400 (#e07020)
 * - degraded    → orange-400 with reduced alpha (amber feel)
 * - down        → red-500 (Candy Red, #b30000)
 */
const STATUS_SPOTLIGHT: Record<PortfolioStatus, string> = {
  operational: "rgba(31, 199, 110, 0.30)",
  building: "rgba(224, 112, 32, 0.32)",
  degraded: "rgba(224, 112, 32, 0.22)",
  down: "rgba(179, 0, 0, 0.35)",
};

const STATUS_LABEL: Record<PortfolioStatus, string> = {
  operational: "Operational",
  building: "Building",
  degraded: "Degraded",
  down: "Down",
};

function isHex(v: unknown): v is string {
  return typeof v === "string" && /^#[0-9a-fA-F]{6}$/.test(v);
}

function hexToRgba(hex: string, alpha: number): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

// ─── Props ───────────────────────────────────────────────────────────────────

interface PortfolioTileProps extends React.HTMLAttributes<HTMLDivElement> {
  /** Tile title — typically the business / portfolio brand name. */
  title: string;
  /** Optional short description below the title. */
  description?: string;
  /** Operational status — drives the spotlight tone. */
  status?: PortfolioStatus;
  /** Stable identity for asset paths + analytics. Pass the brand / client slug. */
  brandSlug?: string;
  /**
   * Already-resolved BrandConfig (loaded server-side via `getBrandConfig`).
   * When present, `brand.primary_color` OVERRIDES the status tone — used on
   * per-brand portfolio + client-portal pages. Omit on the Nexus UI Command
   * Center to keep the unified Gun-Metal + Candy-Red palette.
   */
  brand?: Partial<BrandConfig>;
  /** Tile body content. */
  children?: React.ReactNode;
}

// ─── Wrapper ─────────────────────────────────────────────────────────────────

/**
 * PortfolioTile — Nexus-UI-first SpotlightCard wrapper for portfolio business
 * tiles, system-health cards, and client-portal summary blocks. Encapsulates
 * the status → spotlight-tone logic that was previously inlined on the
 * Empire Command Center page.
 *
 * Scope: defaults to the Nexus UI Gun-Metal + Candy-Red palette. Pass `brand`
 * to override with a per-brand primary colour on portfolio / client surfaces.
 *
 * @example
 * <PortfolioTile title="Synthex" status="building" description="3 in-flight">
 *   <div>Body content</div>
 * </PortfolioTile>
 *
 * @example
 * // Per-brand override on a client portal page
 * <PortfolioTile title={client.company_name} brand={client.brand_config} brandSlug={client.slug}>
 *   ...
 * </PortfolioTile>
 */
export function PortfolioTile({
  title,
  description,
  status = "operational",
  brandSlug,
  brand,
  children,
  className,
  ...rest
}: PortfolioTileProps) {
  // brandSlug currently informational — referenced for stable identity / future
  // asset-path resolution. Listed here so TS doesn't flag it as unused.
  void brandSlug;

  const spotlightColor =
    brand && isHex(brand.primary_color ?? undefined)
      ? hexToRgba(brand.primary_color as string, 0.3)
      : STATUS_SPOTLIGHT[status];

  return (
    <SpotlightCard
      spotlightColor={spotlightColor}
      borderRadius={10}
      className={className}
      style={{ background: "var(--surface-1)", height: "100%", ...rest.style }}
      {...rest}
    >
      <SpotlightCardHeader>
        <SpotlightCardTitle className="!text-base">{title}</SpotlightCardTitle>
        {description !== undefined && (
          <SpotlightCardDescription>
            {description}
            {status !== "operational" ? ` · ${STATUS_LABEL[status].toLowerCase()}` : ""}
          </SpotlightCardDescription>
        )}
      </SpotlightCardHeader>
      {children !== undefined && <SpotlightCardContent>{children}</SpotlightCardContent>}
    </SpotlightCard>
  );
}

export { STATUS_SPOTLIGHT, STATUS_LABEL };
