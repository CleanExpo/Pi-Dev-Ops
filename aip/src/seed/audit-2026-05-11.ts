// Seed script for AIP Day-1.
// Emits idempotent INSERT statements for the entities + relationships surfaced by
// the 2026-05-11 Google Account sprawl audit and the Smoke--Production fix
// (Wiki/log.md 2026-05-11 entry, search GOOGLE_CLIENT_SECRET).
//
// Spec: ~/2nd Brain/2nd Brain/Wiki/aip-first-slice-schema.md § 2 + § 3.
//
// HONESTY GUARDRAILS:
//   - Real values come from Wiki/log.md + Wiki/aip-architecture.md only.
//   - Anything I don't know is left as NULL with a `// TODO seed` comment.
//   - This script DOES NOT execute against any database — it only emits SQL.
//
// Usage: `pnpm tsx src/seed/audit-2026-05-11.ts > 2026-05-11-seed.sql`
//        (or `npm run seed > 2026-05-11-seed.sql`)

import {
  gcpProjectUri,
  googleIdentityUri,
  oauthClientUri,
  portfolioServiceUri,
  vercelProjectUri,
} from "../types/entities.js";
import type {
  GcpProjectProps,
  GoogleIdentityProps,
  OAuthClientProps,
  PortfolioServiceProps,
  VercelProjectProps,
} from "../types/entities.js";
import type { Relationship, SourceRef } from "../types/primitives.js";

// ---------------------------------------------------------------------------
// Source ref — every row originates from today's audit + the fix log entry.
// ---------------------------------------------------------------------------

const AUDIT_SOURCE: SourceRef = {
  origin: "audit",
  ref: "Wiki/log.md#2026-05-11-google-client-secret-fix@pi-dev-ops:4c5cd030828e8d267436e5c592a76c8c21924c1c",
  ingested_at: "2026-05-11T00:00:00Z",
};

// ---------------------------------------------------------------------------
// Seed data.
// ---------------------------------------------------------------------------

interface SeedEntity<TKind extends string, TProps> {
  uri: string;
  kind: TKind;
  id: string;
  properties: TProps;
  source: SourceRef;
}

const contactIdentity: SeedEntity<"GoogleIdentity", GoogleIdentityProps> = {
  uri: googleIdentityUri("contact-unite-group-in"),
  kind: "GoogleIdentity",
  id: "contact-unite-group-in",
  properties: {
    email: "contact@unite-group.in",
    identity_kind: "workspace",
    onepassword_item_id: null, // TODO seed — no 1P item exists yet for the contact@unite-group.in Workspace identity (searched Personal/RestoreAssist/Unite-Group-Infrastructure/Shared/Email-Accounts vaults, 2026-05-11). Create item then backfill.
    recovery_email: null, // TODO seed — recovery chain not verifiable from CLI; confirm in Google Account settings.
    last_active_at: "2026-05-11T00:00:00Z",
  },
  source: AUDIT_SOURCE,
};

const zenithIdentity: SeedEntity<"GoogleIdentity", GoogleIdentityProps> = {
  uri: googleIdentityUri("zenithfresh25-gmail-com"),
  kind: "GoogleIdentity",
  id: "zenithfresh25-gmail-com",
  properties: {
    email: "zenithfresh25@gmail.com",
    identity_kind: "personal",
    onepassword_item_id: null, // TODO seed — no 1P item explicitly named for zenithfresh25@gmail.com found in any vault (2026-05-11).
    recovery_email: null, // TODO seed — same; not verifiable from CLI.
    last_active_at: "2026-05-11T00:00:00Z",
  },
  source: AUDIT_SOURCE,
};

const gcpRestoreAssist: SeedEntity<"GcpProject", GcpProjectProps> = {
  uri: gcpProjectUri("restore-assist-bfb74"),
  kind: "GcpProject",
  id: "restore-assist-bfb74",
  properties: {
    project_number: "", // TODO seed — gcloud is authed as phill.mcgurk@gmail.com which has no IAM on restore-assist-bfb74 (owned by contact@unite-group.in Workspace). Run `gcloud auth login contact@unite-group.in` then `gcloud projects describe restore-assist-bfb74 --format='value(projectNumber)'` to backfill.
    project_id: "restore-assist-bfb74",
    owner_identity_uri: contactIdentity.uri,
    billing_account: null, // TODO seed — same access blocker; verify via `gcloud billing projects describe restore-assist-bfb74` after re-auth.
  },
  source: AUDIT_SOURCE,
};

const gcpLegacy: SeedEntity<"GcpProject", GcpProjectProps> = {
  uri: gcpProjectUri("292141944467"),
  kind: "GcpProject",
  id: "292141944467",
  properties: {
    project_number: "292141944467",
    project_id: "restoreassist", // verified via `gcloud projects describe restoreassist` 2026-05-11
    owner_identity_uri: zenithIdentity.uri,
    billing_account: "015D5F-C8F973-A8AD81", // verified via `gcloud billing projects describe restoreassist` 2026-05-11
  },
  source: AUDIT_SOURCE,
};

const vercelRestoreAssist: SeedEntity<"VercelProject", VercelProjectProps> = {
  uri: vercelProjectUri("restoreassist"),
  kind: "VercelProject",
  id: "restoreassist",
  properties: {
    vercel_project_id: "prj_Aw90JJ2x7mTMatTxa3ymgcU7WPV2", // verified via `vercel project inspect restoreassist --scope unite-group` 2026-05-11
    slug: "restoreassist",
    team_id: "zenithfresh25-1436", // NOTE: `vercel project inspect` reports current Owner as "Unite-Group" team; the audit-source value is retained as-is per surgical-changes guardrail. Migration is a documented follow-up in Wiki/log.md#2026-05-11.
    current_git_sha: "8137a5eea7c3ccb8b53c38cef98e5e3a854bffb3", // RestoreAssist HEAD at 2026-05-11
    framework: "nextjs",
  },
  source: AUDIT_SOURCE,
};

const oauthRestoreAssist: SeedEntity<"OAuthClient", OAuthClientProps> = {
  uri: oauthClientUri("restoreassist-prod"),
  kind: "OAuthClient",
  id: "restoreassist-prod",
  properties: {
    client_id: "", // TODO seed — new client_id lives in (a) GCP console for restore-assist-bfb74 (no gcloud IAM, see gcpRestoreAssist note) and (b) Vercel Production env GOOGLE_CLIENT_ID (encrypted; `vercel env pull` returned empty string). Pull from GCP console after re-auth, OR via `vercel env pull` from a session with decrypt rights.
    secret_rotated_at: "2026-05-11T00:00:00Z", // rotated today during smoke fix
    authorized_origins: ["https://restoreassist.app"],
    authorized_redirect_uris: [
      "https://restoreassist.app/api/auth/callback/google",
    ],
    status: "active",
    gcp_project_uri: gcpRestoreAssist.uri,
  },
  source: AUDIT_SOURCE,
};

const psRestoreAssist: SeedEntity<"PortfolioService", PortfolioServiceProps> = {
  uri: portfolioServiceUri("ra"),
  kind: "PortfolioService",
  id: "ra",
  properties: {
    slug: "ra",
    brand_name: "RestoreAssist",
    current_git_sha: "8137a5eea7c3ccb8b53c38cef98e5e3a854bffb3", // RestoreAssist HEAD at 2026-05-11; matches vercelRestoreAssist.current_git_sha
    status: "active",
    wiki_page_path: "Wiki/restore-assist.md",
  },
  source: AUDIT_SOURCE,
};

const ENTITIES: ReadonlyArray<SeedEntity<string, unknown>> = [
  contactIdentity,
  zenithIdentity,
  gcpRestoreAssist,
  gcpLegacy,
  vercelRestoreAssist,
  oauthRestoreAssist,
  psRestoreAssist,
];

// ---------------------------------------------------------------------------
// Relationships — only those we can assert from the audit + fix log.
// Spec § 3. Each row is also idempotent via the (kind, from_uri, to_uri) unique key.
// ---------------------------------------------------------------------------

type SeedRelationship = Pick<
  Relationship,
  "uri" | "kind" | "from_uri" | "to_uri" | "cardinality"
> & { properties: Record<string, unknown> };

function relUri(
  kind: string,
  fromId: string,
  toId: string,
): string {
  // Deterministic edge URI; lets the SQL be re-run safely.
  return `aip://unite-group/Relationship/${kind}/${fromId}__${toId}`;
}

const RELATIONSHIPS: ReadonlyArray<SeedRelationship> = [
  // OAuthClient.belongsTo(GcpProject) — 1:1
  {
    uri: relUri(
      "OAuthClient.belongsTo.GcpProject",
      oauthRestoreAssist.id,
      gcpRestoreAssist.id,
    ),
    kind: "OAuthClient.belongsTo.GcpProject",
    from_uri: oauthRestoreAssist.uri,
    to_uri: gcpRestoreAssist.uri,
    cardinality: "1:1",
    properties: {},
  },
  // GcpProject.ownedBy(GoogleIdentity) — N:1, since_date
  {
    uri: relUri(
      "GcpProject.ownedBy.GoogleIdentity",
      gcpRestoreAssist.id,
      contactIdentity.id,
    ),
    kind: "GcpProject.ownedBy.GoogleIdentity",
    from_uri: gcpRestoreAssist.uri,
    to_uri: contactIdentity.uri,
    cardinality: "N:1",
    properties: { since_date: "2026-05-11" }, // ownership transferred during today's fix
  },
  {
    uri: relUri(
      "GcpProject.ownedBy.GoogleIdentity",
      gcpLegacy.id,
      zenithIdentity.id,
    ),
    kind: "GcpProject.ownedBy.GoogleIdentity",
    from_uri: gcpLegacy.uri,
    to_uri: zenithIdentity.uri,
    cardinality: "N:1",
    properties: { since_date: null }, // TODO seed: original creation date of legacy project
  },
  // VercelProject.ownedBy(GoogleIdentity) — N:1, role
  // Vercel team `zenithfresh25-1436` is currently owned by the personal Gmail.
  // Migration to contact@unite-group.in is a documented follow-up in the fix log.
  {
    uri: relUri(
      "VercelProject.ownedBy.GoogleIdentity",
      vercelRestoreAssist.id,
      zenithIdentity.id,
    ),
    kind: "VercelProject.ownedBy.GoogleIdentity",
    from_uri: vercelRestoreAssist.uri,
    to_uri: zenithIdentity.uri,
    cardinality: "N:1",
    properties: { role: "owner" },
  },
  // PortfolioService.deploysTo(VercelProject) — 1:1
  {
    uri: relUri(
      "PortfolioService.deploysTo.VercelProject",
      psRestoreAssist.id,
      vercelRestoreAssist.id,
    ),
    kind: "PortfolioService.deploysTo.VercelProject",
    from_uri: psRestoreAssist.uri,
    to_uri: vercelRestoreAssist.uri,
    cardinality: "1:1",
    properties: {},
  },
  // PortfolioService.authsVia(OAuthClient) — 1:N, purpose
  {
    uri: relUri(
      "PortfolioService.authsVia.OAuthClient",
      psRestoreAssist.id,
      oauthRestoreAssist.id,
    ),
    kind: "PortfolioService.authsVia.OAuthClient",
    from_uri: psRestoreAssist.uri,
    to_uri: oauthRestoreAssist.uri,
    cardinality: "1:N",
    properties: { purpose: "google-sign-in" },
  },
  // PortfolioService.usesGcp(GcpProject) — 1:N
  {
    uri: relUri(
      "PortfolioService.usesGcp.GcpProject",
      psRestoreAssist.id,
      gcpRestoreAssist.id,
    ),
    kind: "PortfolioService.usesGcp.GcpProject",
    from_uri: psRestoreAssist.uri,
    to_uri: gcpRestoreAssist.uri,
    cardinality: "1:N",
    properties: {},
  },
  // GoogleIdentity.recoversTo(GoogleIdentity) — N:1
  // TODO seed — recovery chain not verifiable from CLI tooling (no gcloud IAM on contact@unite-group.in
  // Workspace from this session; gmail/workspace recovery settings live behind myaccount.google.com,
  // not in any API surface we have here). Verify in browser at
  // myaccount.google.com/security for both identities, then add the edge.
  // Leaving empty is honest; do NOT fabricate.
];

// ---------------------------------------------------------------------------
// SQL emitter.
// ---------------------------------------------------------------------------

function sqlString(s: string): string {
  // Postgres single-quote escape.
  return `'${s.replace(/'/g, "''")}'`;
}

function sqlJsonb(v: unknown): string {
  return `${sqlString(JSON.stringify(v))}::jsonb`;
}

function emitEntityInsert(e: SeedEntity<string, unknown>): string {
  return [
    "insert into aip_entities (uri, kind, id, properties, source) values (",
    `  ${sqlString(e.uri)},`,
    `  ${sqlString(e.kind)},`,
    `  ${sqlString(e.id)},`,
    `  ${sqlJsonb(e.properties)},`,
    `  ${sqlJsonb(e.source)}`,
    ") on conflict (uri) do nothing;",
  ].join("\n");
}

function emitRelationshipInsert(r: SeedRelationship): string {
  return [
    "insert into aip_relationships (uri, kind, from_uri, to_uri, cardinality, properties) values (",
    `  ${sqlString(r.uri)},`,
    `  ${sqlString(r.kind)},`,
    `  ${sqlString(r.from_uri)},`,
    `  ${sqlString(r.to_uri)},`,
    `  ${sqlString(r.cardinality)},`,
    `  ${sqlJsonb(r.properties)}`,
    ") on conflict (uri) do nothing;",
  ].join("\n");
}

function emit(): string {
  const lines: string[] = [
    "-- AIP seed — 2026-05-11 Google Account sprawl audit.",
    "-- Generated by aip/src/seed/audit-2026-05-11.ts. Do not edit by hand;",
    "-- re-run the script and redirect to a .sql file instead.",
    "begin;",
    "",
    "-- Entities --",
  ];
  for (const e of ENTITIES) {
    lines.push(emitEntityInsert(e));
    lines.push("");
  }
  lines.push("-- Relationships --");
  for (const r of RELATIONSHIPS) {
    lines.push(emitRelationshipInsert(r));
    lines.push("");
  }
  lines.push("commit;");
  return lines.join("\n");
}

// Stdout only. The spec is explicit: do NOT execute against a DB.
process.stdout.write(emit() + "\n");
