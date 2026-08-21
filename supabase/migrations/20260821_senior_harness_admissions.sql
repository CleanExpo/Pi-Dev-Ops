-- Senior Harness admission authority store (enforce v1).
--
-- Prerequisites: NOLOGIN group roles `senior_harness_issuer` and
-- `senior_harness_consumer` must be provisioned before this migration. Login
-- identities receive membership outside this migration. The issuer role owns
-- parent reservation/child derivation/lifecycle operations; the consumer role
-- can only atomically consume a child and assert its active session binding.
-- Neither role receives direct table access.
BEGIN;

CREATE SCHEMA IF NOT EXISTS private;
REVOKE ALL ON SCHEMA private FROM PUBLIC;

DO $roles$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'senior_harness_issuer') THEN
    RAISE EXCEPTION 'required role senior_harness_issuer is not provisioned';
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'senior_harness_consumer') THEN
    RAISE EXCEPTION 'required role senior_harness_consumer is not provisioned';
  END IF;
END
$roles$;

CREATE TABLE IF NOT EXISTS private.senior_harness_admissions (
  admission_id UUID PRIMARY KEY,
  admission_ref TEXT NOT NULL UNIQUE
    CHECK (
      length(admission_ref) <= 512
      AND admission_ref ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]*$'
    ),
  parent_admission_id UUID REFERENCES private.senior_harness_admissions(admission_id),
  parent_ref TEXT
    CHECK (
      parent_ref IS NULL
      OR (
        length(parent_ref) <= 512
        AND parent_ref ~ '^[A-Za-z0-9][A-Za-z0-9._:/-]*$'
      )
    ),
  admission_kind TEXT NOT NULL CHECK (admission_kind IN ('parent', 'child')),
  claim_schema_version TEXT NOT NULL CHECK (claim_schema_version = '1.0'),
  state TEXT NOT NULL DEFAULT 'reserved'
    CHECK (state IN ('reserved', 'consumed', 'released', 'revoked', 'expired')),

  -- Immutable signed target shared by a parent and all of its children.
  source_kind TEXT NOT NULL CHECK (source_kind <> ''),
  source_id TEXT NOT NULL CHECK (source_id <> ''),
  source_version TEXT NOT NULL CHECK (source_version <> ''),
  repository TEXT NOT NULL CHECK (repository <> ''),
  objective_digest TEXT NOT NULL CHECK (objective_digest ~ '^sha256:[0-9a-f]{64}$'),
  scope_digest TEXT NOT NULL CHECK (scope_digest ~ '^sha256:[0-9a-f]{64}$'),
  task_id TEXT NOT NULL CHECK (task_id <> ''),
  plan_id TEXT NOT NULL CHECK (plan_id <> ''),
  base_sha TEXT NOT NULL CHECK (base_sha ~ '^[0-9a-f]{40}([0-9a-f]{24})?$'),

  -- A parent reserves the common target. A child adds one exact Unlazy leaf.
  node_id TEXT,
  reservation_ref TEXT,
  worker_id TEXT,
  worker_context_id TEXT,
  session_id TEXT,
  node_contract_digest TEXT,

  audience TEXT NOT NULL CHECK (audience <> ''),
  issued_at TIMESTAMPTZ NOT NULL,
  expires_at TIMESTAMPTZ NOT NULL CHECK (expires_at > issued_at),
  signer_key_id TEXT NOT NULL
    CHECK (signer_key_id ~ '^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$'),
  claim_digest TEXT NOT NULL UNIQUE CHECK (claim_digest ~ '^sha256:[0-9a-f]{64}$'),
  signature BYTEA NOT NULL CHECK (octet_length(signature) = 64),

  -- Mutable lifecycle facts. They are never part of the signed target.
  consumption_session_id TEXT,
  consumed_at TIMESTAMPTZ,
  released_at TIMESTAMPTZ,
  revoked_at TIMESTAMPTZ,
  expired_at TIMESTAMPTZ,
  terminal_reason TEXT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),

  CONSTRAINT senior_harness_admissions_lineage_ck CHECK (
    (admission_kind = 'parent'
      AND parent_admission_id IS NULL
      AND parent_ref IS NULL
      AND node_id IS NULL
      AND reservation_ref IS NULL
      AND worker_id IS NULL
      AND worker_context_id IS NULL
      AND session_id IS NULL
      AND node_contract_digest ~ '^sha256:[0-9a-f]{64}$')
    OR
    (admission_kind = 'child'
      AND parent_admission_id IS NOT NULL
      AND parent_ref IS NOT NULL AND parent_ref <> ''
      AND node_id IS NOT NULL AND node_id <> ''
      AND reservation_ref IS NOT NULL AND reservation_ref <> ''
      AND worker_id IS NOT NULL AND worker_id <> ''
      AND worker_context_id IS NOT NULL AND worker_context_id <> ''
      AND session_id IS NOT NULL AND session_id <> ''
      AND node_contract_digest ~ '^sha256:[0-9a-f]{64}$')
  ),
  CONSTRAINT senior_harness_admissions_lifecycle_ck CHECK (
    (state = 'reserved'
      AND consumption_session_id IS NULL
      AND consumed_at IS NULL
      AND released_at IS NULL
      AND revoked_at IS NULL
      AND expired_at IS NULL)
    OR
    (state = 'consumed'
      AND admission_kind = 'child'
      AND consumption_session_id IS NOT NULL
      AND consumed_at IS NOT NULL
      AND released_at IS NULL
      AND revoked_at IS NULL
      AND expired_at IS NULL)
    OR
    (state = 'released'
      AND released_at IS NOT NULL
      AND revoked_at IS NULL
      AND expired_at IS NULL)
    OR
    (state = 'revoked'
      AND revoked_at IS NOT NULL
      AND expired_at IS NULL)
    OR
    (state = 'expired'
      AND expired_at IS NOT NULL)
  )
);

-- One live parent may reserve an exact common target. Expiry is materialized by
-- the functions below before another reservation is attempted.
CREATE UNIQUE INDEX IF NOT EXISTS senior_harness_one_live_parent_target_idx
  ON private.senior_harness_admissions (
    source_kind, source_id, source_version, repository,
    objective_digest, scope_digest, task_id, plan_id, base_sha, audience
  )
  WHERE admission_kind = 'parent' AND state = 'reserved';

-- A leaf/reservation stays exclusive from derivation through active execution.
CREATE UNIQUE INDEX IF NOT EXISTS senior_harness_one_live_child_leaf_idx
  ON private.senior_harness_admissions (
    parent_admission_id, node_id, reservation_ref, worker_context_id, audience
  )
  WHERE admission_kind = 'child' AND state IN ('reserved', 'consumed');

-- A Pi-CEO session can hold only one active consumed lease. Terminal rows keep
-- their consumption_session_id for audit, while an explicitly reissued child
-- may resume the same session after the prior lease is revoked or expired.
-- Drop/recreate is deliberate: IF NOT EXISTS cannot repair the former broader
-- predicate on databases that already applied an earlier migration draft.
DROP INDEX IF EXISTS private.senior_harness_one_consumption_session_idx;
CREATE UNIQUE INDEX senior_harness_one_consumption_session_idx
  ON private.senior_harness_admissions (consumption_session_id)
  WHERE state = 'consumed' AND consumption_session_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS senior_harness_parent_children_idx
  ON private.senior_harness_admissions (parent_admission_id, state);
CREATE INDEX IF NOT EXISTS senior_harness_expiry_idx
  ON private.senior_harness_admissions (expires_at)
  WHERE state IN ('reserved', 'consumed');

ALTER TABLE private.senior_harness_admissions ENABLE ROW LEVEL SECURITY;

CREATE OR REPLACE FUNCTION private.senior_harness_guard_admission_update()
RETURNS TRIGGER
LANGUAGE plpgsql
SET search_path = pg_catalog, private
AS $function$
BEGIN
  IF ROW(
    NEW.admission_id, NEW.admission_ref, NEW.parent_admission_id, NEW.parent_ref,
    NEW.admission_kind, NEW.claim_schema_version,
    NEW.source_kind, NEW.source_id, NEW.source_version, NEW.repository,
    NEW.objective_digest, NEW.scope_digest, NEW.task_id, NEW.plan_id, NEW.base_sha,
    NEW.node_id, NEW.reservation_ref, NEW.worker_id, NEW.worker_context_id,
    NEW.session_id, NEW.node_contract_digest, NEW.audience, NEW.issued_at, NEW.expires_at,
    NEW.signer_key_id, NEW.claim_digest, NEW.signature, NEW.created_at
  ) IS DISTINCT FROM ROW(
    OLD.admission_id, OLD.admission_ref, OLD.parent_admission_id, OLD.parent_ref,
    OLD.admission_kind, OLD.claim_schema_version,
    OLD.source_kind, OLD.source_id, OLD.source_version, OLD.repository,
    OLD.objective_digest, OLD.scope_digest, OLD.task_id, OLD.plan_id, OLD.base_sha,
    OLD.node_id, OLD.reservation_ref, OLD.worker_id, OLD.worker_context_id,
    OLD.session_id, OLD.node_contract_digest, OLD.audience, OLD.issued_at, OLD.expires_at,
    OLD.signer_key_id, OLD.claim_digest, OLD.signature, OLD.created_at
  ) THEN
    RAISE EXCEPTION 'signed admission target is immutable' USING ERRCODE = '22000';
  END IF;

  IF OLD.state IN ('released', 'revoked', 'expired') AND NEW.state <> OLD.state THEN
    RAISE EXCEPTION 'terminal admission state cannot transition' USING ERRCODE = '22000';
  END IF;
  IF OLD.state = 'consumed' AND NEW.state NOT IN ('consumed', 'released', 'revoked', 'expired') THEN
    RAISE EXCEPTION 'consumed admission cannot reactivate' USING ERRCODE = '22000';
  END IF;
  IF OLD.state = 'reserved' AND NEW.state NOT IN ('reserved', 'consumed', 'released', 'revoked', 'expired') THEN
    RAISE EXCEPTION 'invalid admission state transition' USING ERRCODE = '22000';
  END IF;
  IF NEW.state = OLD.state
     AND ROW(
       NEW.consumption_session_id, NEW.consumed_at, NEW.released_at,
       NEW.revoked_at, NEW.expired_at, NEW.terminal_reason
     ) IS DISTINCT FROM ROW(
       OLD.consumption_session_id, OLD.consumed_at, OLD.released_at,
       OLD.revoked_at, OLD.expired_at, OLD.terminal_reason
     ) THEN
    RAISE EXCEPTION 'admission lifecycle facts are append-only' USING ERRCODE = '22000';
  END IF;
  IF (OLD.consumption_session_id IS NOT NULL
        AND NEW.consumption_session_id IS DISTINCT FROM OLD.consumption_session_id)
     OR (OLD.consumed_at IS NOT NULL AND NEW.consumed_at IS DISTINCT FROM OLD.consumed_at)
     OR (OLD.released_at IS NOT NULL AND NEW.released_at IS DISTINCT FROM OLD.released_at)
     OR (OLD.revoked_at IS NOT NULL AND NEW.revoked_at IS DISTINCT FROM OLD.revoked_at)
     OR (OLD.expired_at IS NOT NULL AND NEW.expired_at IS DISTINCT FROM OLD.expired_at) THEN
    RAISE EXCEPTION 'established admission lifecycle facts are immutable' USING ERRCODE = '22000';
  END IF;

  NEW.updated_at := clock_timestamp();
  RETURN NEW;
END
$function$;

DROP TRIGGER IF EXISTS senior_harness_guard_admission_update
  ON private.senior_harness_admissions;
CREATE TRIGGER senior_harness_guard_admission_update
BEFORE UPDATE ON private.senior_harness_admissions
FOR EACH ROW EXECUTE FUNCTION private.senior_harness_guard_admission_update();

CREATE OR REPLACE FUNCTION private.senior_harness_expire_admissions(
  p_parent_ref TEXT DEFAULT NULL
)
RETURNS BIGINT
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, private
AS $function$
DECLARE
  v_parent_id UUID;
  v_children BIGINT := 0;
  v_parents BIGINT := 0;
BEGIN
  -- A parent's expiry invalidates every active descendant even when a child's
  -- own TTL extends further. Lock parent-before-child to share one ordering
  -- with consume, release, and revoke and avoid lifecycle deadlocks.
  FOR v_parent_id IN
    SELECT parent.admission_id
      FROM private.senior_harness_admissions AS parent
     WHERE parent.admission_kind = 'parent'
       AND parent.state = 'reserved'
       AND parent.expires_at <= clock_timestamp()
       AND (p_parent_ref IS NULL OR parent.admission_ref = p_parent_ref)
     ORDER BY parent.admission_id
     FOR UPDATE
  LOOP
    UPDATE private.senior_harness_admissions AS child
       SET state = 'expired',
           expired_at = clock_timestamp(),
           terminal_reason = 'parent_ttl_expired'
     WHERE child.parent_admission_id = v_parent_id
       AND child.state IN ('reserved', 'consumed');
    GET DIAGNOSTICS v_parents = ROW_COUNT;
    v_children := v_children + v_parents;

    UPDATE private.senior_harness_admissions AS parent
       SET state = 'expired',
           expired_at = clock_timestamp(),
           terminal_reason = 'ttl_expired'
     WHERE parent.admission_id = v_parent_id
       AND parent.state = 'reserved';
    GET DIAGNOSTICS v_parents = ROW_COUNT;
    v_children := v_children + v_parents;
  END LOOP;

  -- Materialize child TTLs under parents that remain active. This statement
  -- does not later acquire a parent lock, preserving parent-before-child order.
  UPDATE private.senior_harness_admissions AS child
     SET state = 'expired',
         expired_at = clock_timestamp(),
         terminal_reason = 'ttl_expired'
    FROM private.senior_harness_admissions AS parent
   WHERE child.parent_admission_id = parent.admission_id
     AND child.admission_kind = 'child'
     AND child.state IN ('reserved', 'consumed')
     AND child.expires_at <= clock_timestamp()
     AND parent.admission_kind = 'parent'
     AND parent.state = 'reserved'
     AND parent.expires_at > clock_timestamp()
     AND (p_parent_ref IS NULL OR parent.admission_ref = p_parent_ref);
  GET DIAGNOSTICS v_parents = ROW_COUNT;
  RETURN v_children + v_parents;
END
$function$;

CREATE OR REPLACE FUNCTION private.senior_harness_reserve_parent(
  p_admission_id UUID,
  p_admission_ref TEXT,
  p_source_kind TEXT,
  p_source_id TEXT,
  p_source_version TEXT,
  p_repository TEXT,
  p_objective_digest TEXT,
  p_scope_digest TEXT,
  p_task_id TEXT,
  p_plan_id TEXT,
  p_base_sha TEXT,
  p_node_contract_digest TEXT,
  p_audience TEXT,
  p_issued_at TIMESTAMPTZ,
  p_expires_at TIMESTAMPTZ,
  p_signer_key_id TEXT,
  p_claim_digest TEXT,
  p_signature BYTEA
)
RETURNS TABLE(admission_ref TEXT, state TEXT, expires_at TIMESTAMPTZ)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, private
AS $function$
BEGIN
  IF p_expires_at <= clock_timestamp() OR p_expires_at <= p_issued_at THEN
    RETURN;
  END IF;

  PERFORM private.senior_harness_expire_admissions(NULL::TEXT);

  RETURN QUERY
  INSERT INTO private.senior_harness_admissions (
    admission_id, admission_ref, admission_kind, claim_schema_version,
    source_kind, source_id, source_version, repository, objective_digest,
    scope_digest, task_id, plan_id, base_sha, node_contract_digest, audience,
    issued_at, expires_at, signer_key_id, claim_digest, signature
  ) VALUES (
    p_admission_id, p_admission_ref, 'parent', '1.0', p_source_kind,
    p_source_id, p_source_version, p_repository, p_objective_digest,
    p_scope_digest, p_task_id, p_plan_id, p_base_sha, p_node_contract_digest,
    p_audience, p_issued_at, p_expires_at, p_signer_key_id,
    p_claim_digest, p_signature
  )
  ON CONFLICT DO NOTHING
  RETURNING senior_harness_admissions.admission_ref,
            senior_harness_admissions.state,
            senior_harness_admissions.expires_at;
END
$function$;

CREATE OR REPLACE FUNCTION private.senior_harness_derive_child(
  p_parent_ref TEXT,
  p_admission_id UUID,
  p_admission_ref TEXT,
  p_node_id TEXT,
  p_reservation_ref TEXT,
  p_worker_id TEXT,
  p_worker_context_id TEXT,
  p_session_id TEXT,
  p_node_contract_digest TEXT,
  p_audience TEXT,
  p_issued_at TIMESTAMPTZ,
  p_expires_at TIMESTAMPTZ,
  p_signer_key_id TEXT,
  p_claim_digest TEXT,
  p_signature BYTEA
)
RETURNS TABLE(admission_ref TEXT, state TEXT, expires_at TIMESTAMPTZ)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, private
AS $function$
DECLARE
  v_parent private.senior_harness_admissions%ROWTYPE;
BEGIN
  SELECT parent.* INTO v_parent
    FROM private.senior_harness_admissions AS parent
   WHERE parent.admission_ref = p_parent_ref
     AND parent.admission_kind = 'parent'
   FOR UPDATE;

  IF NOT FOUND THEN
    RETURN;
  END IF;

  PERFORM private.senior_harness_expire_admissions(p_parent_ref);

  IF v_parent.state <> 'reserved'
     OR v_parent.expires_at <= clock_timestamp()
     OR p_expires_at <= clock_timestamp()
     OR p_expires_at <= p_issued_at
     OR p_expires_at > v_parent.expires_at
     OR p_issued_at < v_parent.issued_at
     OR p_audience <> v_parent.audience || ':worker:' || p_worker_context_id THEN
    RETURN;
  END IF;

  RETURN QUERY
  INSERT INTO private.senior_harness_admissions (
    admission_id, admission_ref, parent_admission_id, parent_ref,
    admission_kind, claim_schema_version,
    source_kind, source_id, source_version, repository,
    objective_digest, scope_digest, task_id, plan_id, base_sha,
    node_id, reservation_ref, worker_id, worker_context_id, session_id,
    node_contract_digest, audience, issued_at, expires_at,
    signer_key_id, claim_digest, signature
  ) VALUES (
    p_admission_id, p_admission_ref, v_parent.admission_id,
    v_parent.admission_ref, 'child', '1.0',
    v_parent.source_kind, v_parent.source_id, v_parent.source_version,
    v_parent.repository, v_parent.objective_digest, v_parent.scope_digest,
    v_parent.task_id, v_parent.plan_id, v_parent.base_sha,
    p_node_id, p_reservation_ref, p_worker_id, p_worker_context_id, p_session_id,
    p_node_contract_digest, p_audience, p_issued_at, p_expires_at,
    p_signer_key_id, p_claim_digest, p_signature
  )
  ON CONFLICT DO NOTHING
  RETURNING senior_harness_admissions.admission_ref,
            senior_harness_admissions.state,
            senior_harness_admissions.expires_at;
END
$function$;

CREATE OR REPLACE FUNCTION private.senior_harness_consume_child(
  p_admission_ref TEXT,
  p_parent_ref TEXT,
  p_claim_digest TEXT,
  p_source_kind TEXT,
  p_source_id TEXT,
  p_source_version TEXT,
  p_repository TEXT,
  p_objective_digest TEXT,
  p_scope_digest TEXT,
  p_task_id TEXT,
  p_plan_id TEXT,
  p_node_id TEXT,
  p_reservation_ref TEXT,
  p_worker_id TEXT,
  p_worker_context_id TEXT,
  p_base_sha TEXT,
  p_node_contract_digest TEXT,
  p_audience TEXT,
  p_issued_at TIMESTAMPTZ,
  p_expires_at TIMESTAMPTZ,
  p_signer_key_id TEXT,
  p_signature BYTEA,
  p_session_id TEXT
)
RETURNS TABLE(admission_ref TEXT, state TEXT, expires_at TIMESTAMPTZ, consumption_session_id TEXT)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, private
AS $function$
DECLARE
  v_parent_id UUID;
BEGIN
  SELECT child.parent_admission_id INTO v_parent_id
    FROM private.senior_harness_admissions AS child
   WHERE child.admission_ref = p_admission_ref
     AND child.admission_kind = 'child';
  IF NOT FOUND OR p_session_id IS NULL OR p_session_id = '' THEN
    RETURN;
  END IF;

  -- Take a shared parent lock before touching a child. Multiple different
  -- children can still consume concurrently, while parent release/revoke waits.
  PERFORM 1
    FROM private.senior_harness_admissions AS parent
   WHERE parent.admission_id = v_parent_id
     AND parent.admission_kind = 'parent'
   FOR SHARE;
  IF NOT FOUND THEN
    RETURN;
  END IF;

  PERFORM private.senior_harness_expire_admissions(
    (SELECT parent.admission_ref
       FROM private.senior_harness_admissions AS parent
      WHERE parent.admission_id = v_parent_id)
  );

  -- This conditional UPDATE is the single-use authority boundary.
  RETURN QUERY
  UPDATE private.senior_harness_admissions AS child
     SET state = 'consumed',
         consumption_session_id = p_session_id,
         consumed_at = clock_timestamp()
   WHERE child.admission_ref = p_admission_ref
     AND child.admission_kind = 'child'
     AND child.claim_schema_version = '1.0'
     AND child.state = 'reserved'
     AND child.expires_at > clock_timestamp()
     AND child.parent_ref = p_parent_ref
     AND child.claim_digest = p_claim_digest
     AND child.source_kind = p_source_kind
     AND child.source_id = p_source_id
     AND child.source_version = p_source_version
     AND child.repository = p_repository
     AND child.objective_digest = p_objective_digest
     AND child.scope_digest = p_scope_digest
     AND child.task_id = p_task_id
     AND child.plan_id = p_plan_id
     AND child.node_id = p_node_id
     AND child.reservation_ref = p_reservation_ref
     AND child.worker_id = p_worker_id
     AND child.worker_context_id = p_worker_context_id
     AND child.session_id = p_session_id
     AND child.base_sha = p_base_sha
     AND child.node_contract_digest = p_node_contract_digest
     AND child.audience = p_audience
     AND child.issued_at = p_issued_at
     AND child.expires_at = p_expires_at
     AND child.signer_key_id = p_signer_key_id
     AND child.signature = p_signature
     AND EXISTS (
       SELECT 1
         FROM private.senior_harness_admissions AS parent
        WHERE parent.admission_id = child.parent_admission_id
          AND parent.admission_id = v_parent_id
          AND parent.admission_ref = p_parent_ref
          AND parent.admission_kind = 'parent'
          AND parent.state = 'reserved'
          AND parent.expires_at > clock_timestamp()
     )
  RETURNING child.admission_ref, child.state, child.expires_at,
            child.consumption_session_id;
EXCEPTION
  -- The session uniqueness index is a second replay boundary. A different
  -- child signed for an already-consumed session is a normal denial, not an
  -- internal database error exposed to the consumer.
  WHEN unique_violation THEN
    RETURN;
END
$function$;

CREATE OR REPLACE FUNCTION private.senior_harness_assert_active(
  p_admission_ref TEXT,
  p_claim_digest TEXT,
  p_consumption_session_id TEXT,
  p_worker_context_id TEXT,
  p_audience TEXT
)
RETURNS TABLE(admission_ref TEXT, state TEXT, expires_at TIMESTAMPTZ, consumption_session_id TEXT)
LANGUAGE sql
STABLE
SECURITY DEFINER
SET search_path = pg_catalog, private
AS $function$
  SELECT child.admission_ref, child.state, child.expires_at,
         child.consumption_session_id
    FROM private.senior_harness_admissions AS child
    JOIN private.senior_harness_admissions AS parent
      ON parent.admission_id = child.parent_admission_id
   WHERE child.admission_ref = p_admission_ref
     AND child.admission_kind = 'child'
     AND child.state = 'consumed'
     AND child.expires_at > clock_timestamp()
     AND child.claim_digest = p_claim_digest
     AND child.consumption_session_id = p_consumption_session_id
     AND child.worker_context_id = p_worker_context_id
     AND child.audience = p_audience
     AND parent.admission_kind = 'parent'
     AND parent.state = 'reserved'
     AND parent.expires_at > clock_timestamp()
$function$;

CREATE OR REPLACE FUNCTION private.senior_harness_release_admission(
  p_admission_ref TEXT,
  p_reason TEXT
)
RETURNS TABLE(admission_ref TEXT, state TEXT)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, private
AS $function$
DECLARE
  v_kind TEXT;
BEGIN
  SELECT item.admission_kind INTO v_kind
    FROM private.senior_harness_admissions AS item
   WHERE item.admission_ref = p_admission_ref
   FOR UPDATE;
  IF NOT FOUND OR p_reason IS NULL OR p_reason = '' THEN
    RETURN;
  END IF;

  IF v_kind = 'parent' THEN
    UPDATE private.senior_harness_admissions AS child
       SET state = 'revoked',
           revoked_at = clock_timestamp(),
           terminal_reason = 'parent_released:' || p_reason
     WHERE child.parent_ref = p_admission_ref
       AND child.state IN ('reserved', 'consumed');
  END IF;

  RETURN QUERY
  UPDATE private.senior_harness_admissions AS item
     SET state = 'released', released_at = clock_timestamp(), terminal_reason = p_reason
   WHERE item.admission_ref = p_admission_ref
     AND item.state = 'reserved'
  RETURNING item.admission_ref, item.state;
END
$function$;

CREATE OR REPLACE FUNCTION private.senior_harness_revoke_admission(
  p_admission_ref TEXT,
  p_reason TEXT
)
RETURNS TABLE(admission_ref TEXT, state TEXT)
LANGUAGE plpgsql
SECURITY DEFINER
SET search_path = pg_catalog, private
AS $function$
DECLARE
  v_kind TEXT;
BEGIN
  SELECT item.admission_kind INTO v_kind
    FROM private.senior_harness_admissions AS item
   WHERE item.admission_ref = p_admission_ref
   FOR UPDATE;
  IF NOT FOUND OR p_reason IS NULL OR p_reason = '' THEN
    RETURN;
  END IF;

  IF v_kind = 'parent' THEN
    UPDATE private.senior_harness_admissions AS child
       SET state = 'revoked', revoked_at = clock_timestamp(), terminal_reason = p_reason
     WHERE child.parent_ref = p_admission_ref
       AND child.state IN ('reserved', 'consumed');
  END IF;

  RETURN QUERY
  UPDATE private.senior_harness_admissions AS item
     SET state = 'revoked', revoked_at = clock_timestamp(), terminal_reason = p_reason
   WHERE item.admission_ref = p_admission_ref
     AND item.state IN ('reserved', 'consumed')
  RETURNING item.admission_ref, item.state;
END
$function$;

-- PostgREST-facing wrappers deliberately live in `public`, use caller rights,
-- and contain no authority logic. The private SECURITY DEFINER functions above
-- remain the sole mutation boundary.
CREATE OR REPLACE FUNCTION public.senior_harness_reserve_parent(
  p_admission_id UUID,
  p_admission_ref TEXT,
  p_source_kind TEXT,
  p_source_id TEXT,
  p_source_version TEXT,
  p_repository TEXT,
  p_objective_digest TEXT,
  p_scope_digest TEXT,
  p_task_id TEXT,
  p_plan_id TEXT,
  p_base_sha TEXT,
  p_node_contract_digest TEXT,
  p_audience TEXT,
  p_issued_at TIMESTAMPTZ,
  p_expires_at TIMESTAMPTZ,
  p_signer_key_id TEXT,
  p_claim_digest TEXT,
  p_signature BYTEA
)
RETURNS TABLE(admission_ref TEXT, state TEXT, expires_at TIMESTAMPTZ)
LANGUAGE sql
SECURITY INVOKER
SET search_path = pg_catalog, private
AS $wrapper$
  SELECT * FROM private.senior_harness_reserve_parent(
    p_admission_id, p_admission_ref, p_source_kind, p_source_id,
    p_source_version, p_repository, p_objective_digest, p_scope_digest,
    p_task_id, p_plan_id, p_base_sha, p_node_contract_digest, p_audience,
    p_issued_at, p_expires_at, p_signer_key_id, p_claim_digest, p_signature
  )
$wrapper$;

CREATE OR REPLACE FUNCTION public.senior_harness_derive_child(
  p_parent_ref TEXT,
  p_admission_id UUID,
  p_admission_ref TEXT,
  p_node_id TEXT,
  p_reservation_ref TEXT,
  p_worker_id TEXT,
  p_worker_context_id TEXT,
  p_session_id TEXT,
  p_node_contract_digest TEXT,
  p_audience TEXT,
  p_issued_at TIMESTAMPTZ,
  p_expires_at TIMESTAMPTZ,
  p_signer_key_id TEXT,
  p_claim_digest TEXT,
  p_signature BYTEA
)
RETURNS TABLE(admission_ref TEXT, state TEXT, expires_at TIMESTAMPTZ)
LANGUAGE sql
SECURITY INVOKER
SET search_path = pg_catalog, private
AS $wrapper$
  SELECT * FROM private.senior_harness_derive_child(
    p_parent_ref, p_admission_id, p_admission_ref, p_node_id,
    p_reservation_ref, p_worker_id, p_worker_context_id, p_session_id,
    p_node_contract_digest, p_audience, p_issued_at, p_expires_at,
    p_signer_key_id, p_claim_digest, p_signature
  )
$wrapper$;

CREATE OR REPLACE FUNCTION public.senior_harness_consume_child(
  p_admission_ref TEXT,
  p_parent_ref TEXT,
  p_claim_digest TEXT,
  p_source_kind TEXT,
  p_source_id TEXT,
  p_source_version TEXT,
  p_repository TEXT,
  p_objective_digest TEXT,
  p_scope_digest TEXT,
  p_task_id TEXT,
  p_plan_id TEXT,
  p_node_id TEXT,
  p_reservation_ref TEXT,
  p_worker_id TEXT,
  p_worker_context_id TEXT,
  p_base_sha TEXT,
  p_node_contract_digest TEXT,
  p_audience TEXT,
  p_issued_at TIMESTAMPTZ,
  p_expires_at TIMESTAMPTZ,
  p_signer_key_id TEXT,
  p_signature BYTEA,
  p_session_id TEXT
)
RETURNS TABLE(admission_ref TEXT, state TEXT, expires_at TIMESTAMPTZ, consumption_session_id TEXT)
LANGUAGE sql
SECURITY INVOKER
SET search_path = pg_catalog, private
AS $wrapper$
  SELECT * FROM private.senior_harness_consume_child(
    p_admission_ref, p_parent_ref, p_claim_digest, p_source_kind, p_source_id,
    p_source_version, p_repository, p_objective_digest, p_scope_digest,
    p_task_id, p_plan_id, p_node_id, p_reservation_ref, p_worker_id,
    p_worker_context_id, p_base_sha, p_node_contract_digest, p_audience,
    p_issued_at, p_expires_at, p_signer_key_id, p_signature, p_session_id
  )
$wrapper$;

CREATE OR REPLACE FUNCTION public.senior_harness_assert_active(
  p_admission_ref TEXT,
  p_claim_digest TEXT,
  p_consumption_session_id TEXT,
  p_worker_context_id TEXT,
  p_audience TEXT
)
RETURNS TABLE(admission_ref TEXT, state TEXT, expires_at TIMESTAMPTZ, consumption_session_id TEXT)
LANGUAGE sql
SECURITY INVOKER
SET search_path = pg_catalog, private
AS $wrapper$
  SELECT * FROM private.senior_harness_assert_active(
    p_admission_ref, p_claim_digest, p_consumption_session_id,
    p_worker_context_id, p_audience
  )
$wrapper$;

CREATE OR REPLACE FUNCTION public.senior_harness_release_admission(
  p_admission_ref TEXT,
  p_reason TEXT
)
RETURNS TABLE(admission_ref TEXT, state TEXT)
LANGUAGE sql
SECURITY INVOKER
SET search_path = pg_catalog, private
AS $wrapper$
  SELECT * FROM private.senior_harness_release_admission(p_admission_ref, p_reason)
$wrapper$;

CREATE OR REPLACE FUNCTION public.senior_harness_revoke_admission(
  p_admission_ref TEXT,
  p_reason TEXT
)
RETURNS TABLE(admission_ref TEXT, state TEXT)
LANGUAGE sql
SECURITY INVOKER
SET search_path = pg_catalog, private
AS $wrapper$
  SELECT * FROM private.senior_harness_revoke_admission(p_admission_ref, p_reason)
$wrapper$;

REVOKE ALL ON TABLE private.senior_harness_admissions
  FROM PUBLIC, senior_harness_issuer, senior_harness_consumer;
REVOKE ALL ON FUNCTION private.senior_harness_guard_admission_update()
  FROM PUBLIC;
REVOKE ALL ON FUNCTION private.senior_harness_expire_admissions(TEXT)
  FROM PUBLIC, senior_harness_issuer, senior_harness_consumer;
REVOKE ALL ON FUNCTION private.senior_harness_reserve_parent(
  UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
  TEXT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ, TEXT, TEXT, BYTEA
) FROM PUBLIC, senior_harness_issuer, senior_harness_consumer;
REVOKE ALL ON FUNCTION private.senior_harness_derive_child(
  TEXT, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
  TIMESTAMPTZ, TIMESTAMPTZ, TEXT, TEXT, BYTEA
) FROM PUBLIC, senior_harness_issuer, senior_harness_consumer;
REVOKE ALL ON FUNCTION private.senior_harness_release_admission(TEXT, TEXT)
  FROM PUBLIC, senior_harness_issuer, senior_harness_consumer;
REVOKE ALL ON FUNCTION private.senior_harness_revoke_admission(TEXT, TEXT)
  FROM PUBLIC, senior_harness_issuer, senior_harness_consumer;
REVOKE ALL ON FUNCTION private.senior_harness_consume_child(
  TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
  TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
  TIMESTAMPTZ, TIMESTAMPTZ, TEXT, BYTEA, TEXT
) FROM PUBLIC, senior_harness_issuer, senior_harness_consumer;
REVOKE ALL ON FUNCTION private.senior_harness_assert_active(
  TEXT, TEXT, TEXT, TEXT, TEXT
) FROM PUBLIC, senior_harness_issuer, senior_harness_consumer;
REVOKE ALL ON FUNCTION public.senior_harness_reserve_parent(
  UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
  TEXT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ, TEXT, TEXT, BYTEA
) FROM PUBLIC, senior_harness_issuer, senior_harness_consumer;
REVOKE ALL ON FUNCTION public.senior_harness_derive_child(
  TEXT, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
  TIMESTAMPTZ, TIMESTAMPTZ, TEXT, TEXT, BYTEA
) FROM PUBLIC, senior_harness_issuer, senior_harness_consumer;
REVOKE ALL ON FUNCTION public.senior_harness_consume_child(
  TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
  TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
  TIMESTAMPTZ, TIMESTAMPTZ, TEXT, BYTEA, TEXT
) FROM PUBLIC, senior_harness_issuer, senior_harness_consumer;
REVOKE ALL ON FUNCTION public.senior_harness_assert_active(
  TEXT, TEXT, TEXT, TEXT, TEXT
) FROM PUBLIC, senior_harness_issuer, senior_harness_consumer;
REVOKE ALL ON FUNCTION public.senior_harness_release_admission(TEXT, TEXT)
  FROM PUBLIC, senior_harness_issuer, senior_harness_consumer;
REVOKE ALL ON FUNCTION public.senior_harness_revoke_admission(TEXT, TEXT)
  FROM PUBLIC, senior_harness_issuer, senior_harness_consumer;
REVOKE ALL ON SCHEMA private
  FROM senior_harness_issuer, senior_harness_consumer;
GRANT USAGE ON SCHEMA private
  TO senior_harness_issuer, senior_harness_consumer;

GRANT EXECUTE ON FUNCTION private.senior_harness_expire_admissions(TEXT)
  TO senior_harness_issuer;
GRANT EXECUTE ON FUNCTION private.senior_harness_reserve_parent(
  UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
  TEXT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ, TEXT, TEXT, BYTEA
) TO senior_harness_issuer;
GRANT EXECUTE ON FUNCTION private.senior_harness_derive_child(
  TEXT, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
  TIMESTAMPTZ, TIMESTAMPTZ, TEXT, TEXT, BYTEA
) TO senior_harness_issuer;
GRANT EXECUTE ON FUNCTION private.senior_harness_release_admission(TEXT, TEXT)
  TO senior_harness_issuer;
GRANT EXECUTE ON FUNCTION private.senior_harness_revoke_admission(TEXT, TEXT)
  TO senior_harness_issuer;
GRANT EXECUTE ON FUNCTION private.senior_harness_consume_child(
  TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
  TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
  TIMESTAMPTZ, TIMESTAMPTZ, TEXT, BYTEA, TEXT
) TO senior_harness_consumer;
GRANT EXECUTE ON FUNCTION private.senior_harness_assert_active(
  TEXT, TEXT, TEXT, TEXT, TEXT
) TO senior_harness_consumer;

GRANT EXECUTE ON FUNCTION public.senior_harness_reserve_parent(
  UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
  TEXT, TEXT, TEXT, TIMESTAMPTZ, TIMESTAMPTZ, TEXT, TEXT, BYTEA
) TO senior_harness_issuer;
GRANT EXECUTE ON FUNCTION public.senior_harness_derive_child(
  TEXT, UUID, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
  TIMESTAMPTZ, TIMESTAMPTZ, TEXT, TEXT, BYTEA
) TO senior_harness_issuer;
GRANT EXECUTE ON FUNCTION public.senior_harness_release_admission(TEXT, TEXT)
  TO senior_harness_issuer;
GRANT EXECUTE ON FUNCTION public.senior_harness_revoke_admission(TEXT, TEXT)
  TO senior_harness_issuer;
GRANT EXECUTE ON FUNCTION public.senior_harness_consume_child(
  TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
  TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT, TEXT,
  TIMESTAMPTZ, TIMESTAMPTZ, TEXT, BYTEA, TEXT
) TO senior_harness_consumer;
GRANT EXECUTE ON FUNCTION public.senior_harness_assert_active(
  TEXT, TEXT, TEXT, TEXT, TEXT
) TO senior_harness_consumer;

SELECT 'senior_harness_admissions migration complete' AS status;
COMMIT;
