// Spec: ~/2nd Brain/2nd Brain/Wiki/aip-first-slice-schema.md § 1 "Ontology primitives".
// These four base concepts (Entity, Property, Relationship, Action) are the entire
// vocabulary the AIP exposes. Every higher-order type composes from them.

export interface Entity<TKind extends string = string, TProps = unknown> {
  uri: string; // aip://unite-group/{kind}/{id}
  kind: TKind; // discriminator
  id: string; // ULID, stable across renames
  properties: TProps;
  created_at: string;
  updated_at: string;
  source: SourceRef;
}

export type Property =
  | { kind: "string"; value: string }
  | { kind: "number"; value: number }
  | { kind: "boolean"; value: boolean }
  | { kind: "json"; value: unknown }
  | { kind: "datetime"; value: string }
  | { kind: "embedding"; value: number[]; dim: 1536 }
  | { kind: "ref"; value: string };

export interface Relationship<TKind extends string = string, TProps = unknown> {
  uri: string;
  kind: TKind;
  from_uri: string;
  to_uri: string;
  cardinality: "1:1" | "N:1" | "1:N" | "N:N";
  properties?: TProps;
  created_at: string;
}

export interface Action<TName extends string, TParams, TResult> {
  name: TName;
  params: TParams;
  permission: string; // dot-namespaced gate, e.g. "workspace.secrets.rotate"
  execute: (ctx: ActionContext, p: TParams) => Promise<TResult>;
  audit_fields: AuditMeta;
}

export interface SourceRef {
  origin: "wiki" | "audit" | "mcp" | "manual" | "agent";
  ref: string;
  ingested_at: string;
}

// ActionContext + AuditMeta are referenced by `Action` above. The schema page names
// them in the primitive surface but does not spell out their interior. Day-3 wires
// the action runtime and will refine these; Day-1 keeps the shape minimal so the
// types compile without baking premature assumptions into the public API.
export interface ActionContext {
  actor: string; // e.g. "agent://pi-ceo/margot", "user:<uuid>"
  permission_claims: readonly string[]; // e.g. ["workspace.secrets.rotate"]
  idempotency_key?: string;
  started_at: string;
}

export interface AuditMeta {
  before_hash?: string;
  after_hash?: string;
  affected_uris: readonly string[];
}
