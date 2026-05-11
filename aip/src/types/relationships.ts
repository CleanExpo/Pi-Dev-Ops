// Spec: ~/2nd Brain/2nd Brain/Wiki/aip-first-slice-schema.md § 3 "Relationships".
// Typed Relationship variants for the 7 first-slice edges. Each variant pins the
// cardinality literal and the edge-property type, so callers can't accidentally
// build an `OAuthClient.belongsTo(GcpProject)` row with the wrong cardinality or
// the wrong props shape.

import type { Relationship } from "./primitives.js";

// 1. OAuthClient.belongsTo(GcpProject) — 1:1, no edge props.
export type OAuthClientBelongsToGcpProject = Relationship<
  "OAuthClient.belongsTo.GcpProject",
  Record<string, never>
> & { cardinality: "1:1" };

// 2. GcpProject.ownedBy(GoogleIdentity) — N:1, edge prop: since_date.
export interface GcpProjectOwnedByGoogleIdentityProps {
  since_date?: string | null;
}
export type GcpProjectOwnedByGoogleIdentity = Relationship<
  "GcpProject.ownedBy.GoogleIdentity",
  GcpProjectOwnedByGoogleIdentityProps
> & { cardinality: "N:1" };

// 3. VercelProject.ownedBy(GoogleIdentity) — N:1, edge prop: role.
export interface VercelProjectOwnedByGoogleIdentityProps {
  role?: string | null;
}
export type VercelProjectOwnedByGoogleIdentity = Relationship<
  "VercelProject.ownedBy.GoogleIdentity",
  VercelProjectOwnedByGoogleIdentityProps
> & { cardinality: "N:1" };

// 4. PortfolioService.deploysTo(VercelProject) — 1:1, no edge props.
export type PortfolioServiceDeploysToVercelProject = Relationship<
  "PortfolioService.deploysTo.VercelProject",
  Record<string, never>
> & { cardinality: "1:1" };

// 5. PortfolioService.authsVia(OAuthClient) — 1:N, edge prop: purpose.
export interface PortfolioServiceAuthsViaOAuthClientProps {
  purpose?: string | null;
}
export type PortfolioServiceAuthsViaOAuthClient = Relationship<
  "PortfolioService.authsVia.OAuthClient",
  PortfolioServiceAuthsViaOAuthClientProps
> & { cardinality: "1:N" };

// 6. PortfolioService.usesGcp(GcpProject) — 1:N, no edge props.
export type PortfolioServiceUsesGcp = Relationship<
  "PortfolioService.usesGcp.GcpProject",
  Record<string, never>
> & { cardinality: "1:N" };

// 7. GoogleIdentity.recoversTo(GoogleIdentity) — N:1, no edge props.
export type GoogleIdentityRecoversToGoogleIdentity = Relationship<
  "GoogleIdentity.recoversTo.GoogleIdentity",
  Record<string, never>
> & { cardinality: "N:1" };

export type AnyRelationship =
  | OAuthClientBelongsToGcpProject
  | GcpProjectOwnedByGoogleIdentity
  | VercelProjectOwnedByGoogleIdentity
  | PortfolioServiceDeploysToVercelProject
  | PortfolioServiceAuthsViaOAuthClient
  | PortfolioServiceUsesGcp
  | GoogleIdentityRecoversToGoogleIdentity;
