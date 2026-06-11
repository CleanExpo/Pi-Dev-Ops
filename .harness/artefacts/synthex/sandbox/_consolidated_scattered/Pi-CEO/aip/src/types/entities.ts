// Spec: ~/2nd Brain/2nd Brain/Wiki/aip-first-slice-schema.md § 2 "First-slice entity types".
// Discriminated union over the 5 first-slice entity kinds, plus URI helpers that
// emit the locked URI scheme aip://unite-group/{kind}/{id} (see § "Architectural
// decisions").

import type { Entity } from "./primitives.js";

// --- URI helpers -------------------------------------------------------------

const TENANT = "unite-group";

function buildUri(kind: string, id: string): string {
  return `aip://${TENANT}/${kind}/${id}`;
}

export function googleIdentityUri(id: string): string {
  return buildUri("GoogleIdentity", id);
}

export function gcpProjectUri(id: string): string {
  return buildUri("GcpProject", id);
}

export function vercelProjectUri(id: string): string {
  return buildUri("VercelProject", id);
}

export function oauthClientUri(id: string): string {
  return buildUri("OAuthClient", id);
}

export function portfolioServiceUri(id: string): string {
  return buildUri("PortfolioService", id);
}

// --- GoogleIdentity ----------------------------------------------------------

export type GoogleIdentityKind = "workspace" | "personal" | "service";

export interface GoogleIdentityProps {
  email: string;
  identity_kind: GoogleIdentityKind;
  onepassword_item_id?: string | null;
  recovery_email?: string | null;
  last_active_at?: string | null;
}

export type GoogleIdentityEntity = Entity<"GoogleIdentity", GoogleIdentityProps>;

// --- GcpProject --------------------------------------------------------------

export interface GcpProjectProps {
  project_number: string;
  project_id: string;
  owner_identity_uri: string; // aip://unite-group/GoogleIdentity/{id}
  billing_account?: string | null;
}

export type GcpProjectEntity = Entity<"GcpProject", GcpProjectProps>;

// --- VercelProject -----------------------------------------------------------

export interface VercelProjectProps {
  vercel_project_id: string;
  slug: string;
  team_id: string;
  current_git_sha?: string | null;
  framework: string;
}

export type VercelProjectEntity = Entity<"VercelProject", VercelProjectProps>;

// --- OAuthClient -------------------------------------------------------------

export type OAuthClientStatus = "active" | "rotating" | "revoked";

export interface OAuthClientProps {
  client_id: string;
  secret_rotated_at?: string | null;
  authorized_origins: readonly string[];
  authorized_redirect_uris: readonly string[];
  status: OAuthClientStatus;
  gcp_project_uri: string; // aip://unite-group/GcpProject/{id}
}

export type OAuthClientEntity = Entity<"OAuthClient", OAuthClientProps>;

// --- PortfolioService --------------------------------------------------------

export type PortfolioServiceSlug =
  | "dr"
  | "nrpg"
  | "carsi"
  | "ccw"
  | "synthex"
  | "unite"
  | "ra";

export type PortfolioServiceStatus = "active" | "paused" | "deprecated";

export interface PortfolioServiceProps {
  slug: PortfolioServiceSlug;
  brand_name: string;
  current_git_sha?: string | null;
  status: PortfolioServiceStatus;
  wiki_page_path?: string | null;
}

export type PortfolioServiceEntity = Entity<
  "PortfolioService",
  PortfolioServiceProps
>;

// --- Discriminated union -----------------------------------------------------

export type AnyEntity =
  | GoogleIdentityEntity
  | GcpProjectEntity
  | VercelProjectEntity
  | OAuthClientEntity
  | PortfolioServiceEntity;
