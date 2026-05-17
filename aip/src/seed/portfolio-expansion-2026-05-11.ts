// Seed script for AIP portfolio expansion (2026-05-11).
// Extends the Day-1 audit seed (audit-2026-05-11.ts) from RestoreAssist-only to
// all 6 portfolio businesses. Emits idempotent INSERT statements for
// PortfolioService + VercelProject entities and the
// PortfolioService.deploysTo.VercelProject + VercelProject.ownedBy.GoogleIdentity
// edges. The Day-1 contactIdentity entity is the migration target for every
// Vercel project (Unite-Group team migration completed 2026-05-11).
//
// Spec source: Wiki/businesses-overview.md (the consolidated portfolio overview).
//
// HONESTY GUARDRAILS:
//   - PortfolioService rows: brand_name, status, wiki_page_path all come from the
//     Wiki business pages (dr-nrpg.md, carsi.md, ccw.md, synthex.md, unite-crm.md,
//     unite-hub-vision.md). current_git_sha comes from `git rev-parse HEAD` of the
//     active local clone for each repo (verified 2026-05-11).
//   - VercelProject rows: vercel_project_id + slug verified via
//     `vercel project inspect <slug> --scope unite-group` (2026-05-11).
//     team_id = "unite-group" for all (Unite-Group team is the only Vercel team
//     after the 2026-05-11 migration).
//   - GcpProject + OAuthClient entries are NOT created here. None of the new
//     businesses have a verifiable GCP project owned by contact@unite-group.in
//     (gcloud IAM block, same as the Day-1 audit). Google Sign-In env vars exist
//     on synthex/carsi/unite-group Vercel projects (GOOGLE_CLIENT_ID seen via
//     `vercel env ls`) but the values are encrypted and cannot be pulled from
//     the CLI in this session. Leaving these as TODO is honest; do NOT fabricate.
//   - DR and NRPG modelled as two distinct PortfolioServices per Wiki guidance
//     ("Two live products sharing the same monorepo"). Both share the same
//     current_git_sha because they deploy from the same CleanExpo/DR-NRPG repo
//     to two separate Vercel projects (disaster-recovery + dr-nrpg-platform).
//
// Usage: `pnpm tsx src/seed/portfolio-expansion-2026-05-11.ts > expansion.sql`

import {
  googleIdentityUri,
  portfolioServiceUri,
  vercelProjectUri,
} from "../types/entities.js";
import type {
  PortfolioServiceProps,
  PortfolioServiceSlug,
  VercelProjectProps,
} from "../types/entities.js";
import type { SourceRef } from "../types/primitives.js";

// ---------------------------------------------------------------------------
// Source ref — everything in this seed traces back to the portfolio overview
// wiki page + the Pi-Dev-Ops HEAD at the moment of emission.
// ---------------------------------------------------------------------------

const AUDIT_SOURCE: SourceRef = {
  origin: "wiki",
  ref: "Wiki/businesses-overview.md@pi-dev-ops:0eb405fb642c814c98f8b879ca350ecd25af7c77",
  ingested_at: "2026-05-11T00:00:00Z",
};

// ---------------------------------------------------------------------------
// Reuse: the Day-1 audit already seeded the contact@unite-group.in workspace
// identity. Every new Vercel project ownedBy edge points at that URI; we do
// not re-insert the entity row here (the existing INSERT is idempotent via
// on conflict do nothing, and we have no new properties to assert).
// ---------------------------------------------------------------------------

const CONTACT_IDENTITY_URI: string = googleIdentityUri("contact-unite-group-in");

// ---------------------------------------------------------------------------
// Seed shape (mirrors audit-2026-05-11.ts).
// ---------------------------------------------------------------------------

interface SeedEntity<TKind extends string, TProps> {
  uri: string;
  kind: TKind;
  id: string;
  properties: TProps;
  source: SourceRef;
}

interface SeedRelationship {
  uri: string;
  kind: string;
  from_uri: string;
  to_uri: string;
  cardinality: "1:1" | "N:1" | "1:N" | "N:N";
  properties: Record<string, unknown>;
}

function relUri(kind: string, fromId: string, toId: string): string {
  return `aip://unite-group/Relationship/${kind}/${fromId}__${toId}`;
}

// ---------------------------------------------------------------------------
// Per-business definitions.
// Each entry assembles the PortfolioService + (optional) VercelProject + edges.
// ---------------------------------------------------------------------------

interface PortfolioInput {
  readonly slug: PortfolioServiceSlug;
  readonly brand_name: string;
  readonly wiki_page_path: string;
  readonly status: PortfolioServiceProps["status"];
  readonly current_git_sha: string | null;
  // VercelProject — null if no deployed Vercel project exists.
  readonly vercel: {
    readonly id: string; // matches Vercel slug
    readonly vercel_project_id: string;
    readonly framework: string;
  } | null;
}

const PORTFOLIOS: readonly PortfolioInput[] = [
  // -- Disaster Recovery (DR) -----------------------------------------------
  // Wiki: dr-nrpg.md. CleanExpo/DR-NRPG monorepo (apps/nrpg-web + apps/backend).
  // Production: disasterrecovery.com.au. Deploys to Vercel project
  // "disaster-recovery" (verified via `vercel project inspect`).
  {
    slug: "dr",
    brand_name: "Disaster Recovery",
    wiki_page_path: "Wiki/dr-nrpg.md",
    status: "active",
    current_git_sha: "38649b6cffbddd3206c64694e9a5b4ae8efde207", // CleanExpo/DR-NRPG HEAD 2026-05-11
    vercel: {
      id: "disaster-recovery",
      vercel_project_id: "prj_dvNqTXXZxYENjFozhFnqIO72ABhW",
      framework: "nextjs",
    },
  },
  // -- NRPG (National Restoration Practitioners Group) ----------------------
  // Same CleanExpo/DR-NRPG monorepo, separate Vercel project
  // "dr-nrpg-platform" (verified 2026-05-11). Wiki treats DR + NRPG as two
  // products sharing one monorepo, so we model two PortfolioServices that
  // happen to share current_git_sha.
  {
    slug: "nrpg",
    brand_name: "NRPG (National Restoration Practitioners Group)",
    wiki_page_path: "Wiki/dr-nrpg.md",
    status: "active",
    current_git_sha: "38649b6cffbddd3206c64694e9a5b4ae8efde207", // shared with dr — same monorepo
    vercel: {
      id: "dr-nrpg-platform",
      vercel_project_id: "prj_15zLJSeVhpqXcWf1s2U1fHdIHOtw",
      framework: "nextjs",
    },
  },
  // -- CARSI (LMS) ----------------------------------------------------------
  // Wiki: carsi.md. CleanExpo/CARSI repo. Production: carsi.com.au.
  // Note: wiki claims primary deployment is DigitalOcean App Platform, but
  // a Vercel project ("carsi-web", prod URL carsi.com.au) is also live and
  // verified. Seeding the Vercel side; DigitalOcean is out of scope for the
  // current ontology (no DoApp entity kind defined).
  {
    slug: "carsi",
    brand_name: "CARSI",
    wiki_page_path: "Wiki/carsi.md",
    status: "active",
    current_git_sha: "fe3bf5ef7d8c1e8350b35e29b5b2e830d3189147", // CleanExpo/CARSI HEAD 2026-05-11
    vercel: {
      id: "carsi-web",
      vercel_project_id: "prj_hIQAdXiHQGGec6nNKEGzn7SyMh9p",
      framework: "nextjs",
    },
  },
  // -- CCW (Carpet Cleaners Warehouse) — paying client ----------------------
  // Wiki: ccw.md. The product they pay for is the CleanExpo/CCW-CRM SaaS
  // (`ccw-online-erp` package). CCW themselves are an external company; the
  // PortfolioService entity here represents the CCW-CRM deployment they pay
  // for, not the CCW e-commerce site. Vercel project: ccw-crm-web.
  {
    slug: "ccw",
    brand_name: "CCW-Online ERP (CCW deployment)",
    wiki_page_path: "Wiki/ccw.md",
    status: "active",
    current_git_sha: "71633322d12d87da5dcb610669c765daeb07c496", // CleanExpo/CCW-CRM HEAD 2026-05-11
    vercel: {
      id: "ccw-crm-web",
      vercel_project_id: "prj_oTCifkMVqP1NFoTJFBv6u82JmBYd",
      framework: "nextjs",
    },
  },
  // -- Synthex --------------------------------------------------------------
  // Wiki: synthex.md. CleanExpo/Synthex repo. Production: synthex.social.
  {
    slug: "synthex",
    brand_name: "Synthex",
    wiki_page_path: "Wiki/synthex.md",
    status: "active",
    current_git_sha: "c81e5cae68c8fc9f2814a5845b2ed3b8b5168d4a", // CleanExpo/Synthex HEAD 2026-05-11
    vercel: {
      id: "synthex",
      vercel_project_id: "prj_gbQmHn6quoHgG3AswRrDoUlYaF40",
      framework: "other", // Vercel reports "Other" preset (custom build cmd, Prisma + webpack)
    },
  },
  // -- Unite-Group Hub ------------------------------------------------------
  // Wiki: unite-hub-vision.md is the CEO command center spec; unite-crm.md
  // documents the CRM product. The "unite" PortfolioService slug here refers
  // to the hub at unite-group.in (Vercel project "unite-group"), which is the
  // CEO portfolio-health dashboard, not the CCW-CRM product.
  {
    slug: "unite",
    brand_name: "Unite-Group Hub",
    wiki_page_path: "Wiki/unite-hub-vision.md",
    status: "active",
    current_git_sha: "29ab44f41b7a00f5f309ce102a7616b872790cbb", // CleanExpo/unite-group HEAD 2026-05-11
    vercel: {
      id: "unite-group",
      vercel_project_id: "prj_IfUuJNLjXTE8VXqEGwLAleIGhiA0",
      framework: "nextjs",
    },
  },
];

// ---------------------------------------------------------------------------
// Build entity + relationship lists from the inputs.
// ---------------------------------------------------------------------------

const ENTITIES: SeedEntity<string, unknown>[] = [];
const RELATIONSHIPS: SeedRelationship[] = [];

for (const p of PORTFOLIOS) {
  const psProps: PortfolioServiceProps = {
    slug: p.slug,
    brand_name: p.brand_name,
    current_git_sha: p.current_git_sha,
    status: p.status,
    wiki_page_path: p.wiki_page_path,
  };
  const psEntity: SeedEntity<"PortfolioService", PortfolioServiceProps> = {
    uri: portfolioServiceUri(p.slug),
    kind: "PortfolioService",
    id: p.slug,
    properties: psProps,
    source: AUDIT_SOURCE,
  };
  ENTITIES.push(psEntity);

  if (p.vercel === null) {
    // Honest gap — no Vercel project to link.
    continue;
  }

  const vpProps: VercelProjectProps = {
    vercel_project_id: p.vercel.vercel_project_id,
    slug: p.vercel.id,
    team_id: "unite-group",
    current_git_sha: p.current_git_sha,
    framework: p.vercel.framework,
  };
  const vpEntity: SeedEntity<"VercelProject", VercelProjectProps> = {
    uri: vercelProjectUri(p.vercel.id),
    kind: "VercelProject",
    id: p.vercel.id,
    properties: vpProps,
    source: AUDIT_SOURCE,
  };
  ENTITIES.push(vpEntity);

  // PortfolioService.deploysTo.VercelProject — 1:1, no edge props.
  RELATIONSHIPS.push({
    uri: relUri(
      "PortfolioService.deploysTo.VercelProject",
      psEntity.id,
      vpEntity.id,
    ),
    kind: "PortfolioService.deploysTo.VercelProject",
    from_uri: psEntity.uri,
    to_uri: vpEntity.uri,
    cardinality: "1:1",
    properties: {},
  });

  // VercelProject.ownedBy.GoogleIdentity — N:1, role=owner.
  // All Vercel projects are owned by the Unite-Group team (contact@unite-group.in
  // workspace identity) post-migration on 2026-05-11.
  RELATIONSHIPS.push({
    uri: relUri(
      "VercelProject.ownedBy.GoogleIdentity",
      vpEntity.id,
      "contact-unite-group-in",
    ),
    kind: "VercelProject.ownedBy.GoogleIdentity",
    from_uri: vpEntity.uri,
    to_uri: CONTACT_IDENTITY_URI,
    cardinality: "N:1",
    properties: { role: "owner" },
  });
}

// ---------------------------------------------------------------------------
// SQL emitter (copied verbatim from audit-2026-05-11.ts so the two files emit
// identical SQL shapes; both rely on the same idempotency keys in the schema).
// ---------------------------------------------------------------------------

function sqlString(s: string): string {
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
    "-- AIP seed — 2026-05-11 portfolio expansion (all 6 portfolio businesses).",
    "-- Generated by aip/src/seed/portfolio-expansion-2026-05-11.ts.",
    "-- Idempotent; safe to re-run. Do not edit by hand — re-run the script.",
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

process.stdout.write(emit() + "\n");
