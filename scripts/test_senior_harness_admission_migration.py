#!/usr/bin/env python3
"""Verify Senior Harness admissions against local PostgreSQL 15 at /tmp:5432.

The script creates and destroys one uniquely named database. It never reads
credentials or connects over TCP. The two fixed NOLOGIN group roles required
by the migration are created under a host-local lock and removed afterward
when this script created them.
"""

from __future__ import annotations

import concurrent.futures
import base64
import copy
import fcntl
import getpass
import importlib.util
import os
import re
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "supabase/migrations/20260821_senior_harness_admissions.sql"
PGHOST = "/tmp"
PGPORT = "5432"
PGUSER = getpass.getuser()
LOCK_PATH = Path("/tmp/senior-harness-admission-migration-test.lock")
ROLES = ("senior_harness_issuer", "senior_harness_consumer")

PARENT_1 = "00000000-0000-4000-8000-000000000001"
CHILD_1 = "00000000-0000-4000-8000-000000000101"
PARENT_2 = "00000000-0000-4000-8000-000000000002"
CHILD_2 = "00000000-0000-4000-8000-000000000102"
PARENT_3 = "00000000-0000-4000-8000-000000000003"
CHILD_3 = "00000000-0000-4000-8000-000000000103"
PARENT_4 = "00000000-0000-4000-8000-000000000004"
CHILD_4 = "00000000-0000-4000-8000-000000000104"
PARENT_5 = "00000000-0000-4000-8000-000000000005"
CHILD_5 = "00000000-0000-4000-8000-000000000105"
PARENT_REF_1 = "parent-1"
CHILD_REF_1 = "child-1"
PARENT_REF_2 = "parent-2"
CHILD_REF_2 = "child-2"
PARENT_REF_3 = "parent-3"
CHILD_REF_3 = "child-3"
PARENT_REF_4 = "parent-4"
CHILD_REF_4 = "child-4"
PARENT_REF_5 = "parent-resume"
CHILD_REF_5 = "child-resume"

ENVELOPES: dict[str, dict[str, Any]] = {}


def build_signed_envelopes() -> dict[str, dict[str, Any]]:
    """Issue real Ed25519 parent/child envelopes from the production contract."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    path = ROOT / "skills/senior-harness/scripts/admission_authority.py"
    name = "senior_harness_admission_authority_sql_test"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load admission authority: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)

    issued_at = int(time.time())
    authority = module.InMemoryAdmissionAuthority(
        module.generate_private_key(),
        signer_key_id="issuer-key-1",
        audience="pi-ceo/build",
        clock=lambda: issued_at,
    )
    envelopes: dict[str, dict[str, Any]] = {}
    for number, parent_ref in enumerate(
        (PARENT_REF_1, PARENT_REF_2, PARENT_REF_3, PARENT_REF_4, PARENT_REF_5),
        start=1,
    ):
        envelopes[parent_ref] = authority.reserve_parent(
            source_kind="linear",
            source_id=f"RA-900{number - 1}",
            source_version="2026-08-21T00:00:00Z",
            repository="git@GitHub.COM:Unite-Group/Example.git",
            objective="Ship the exact Senior Harness admission target",
            scope={"paths": ["app/**"], "max_files": 5},
            task_id="task-1",
            plan_id="plan-1",
            base_sha="c" * 40,
            node_contract_digest="sha256:" + "d" * 64,
            ttl_seconds=5 if parent_ref == PARENT_REF_4 else 600,
            admission_ref=parent_ref,
        )

    child_specs = (
        (PARENT_REF_1, CHILD_REF_1, "node-1", "reservation-1", "worker-1", "context-1", "session-1"),
        (PARENT_REF_1, "child-session-collision", "node-collision", "reservation-collision", "worker-collision", "context-collision", "session-1"),
        (PARENT_REF_1, "child-shared-audience-denied", "node-audience", "reservation-audience", "worker-audience", "context-audience", "session-audience"),
        (PARENT_REF_2, CHILD_REF_2, "node-2", "reservation-2", "worker-2", "context-2", "session-2"),
        (PARENT_REF_2, "new-child-after-revoke", "node-after-revoke", "reservation-after-revoke", "worker-after-revoke", "context-after-revoke", "session-after-revoke"),
        (PARENT_REF_3, CHILD_REF_3, "node-1", "reservation-1", "worker-1", "context-1", "session-3"),
        (PARENT_REF_3, "child-parent-release", "node-parent-release", "reservation-parent-release", "worker-1", "context-parent-release", "session-parent-release"),
        (PARENT_REF_4, CHILD_REF_4, "node-1", "reservation-1", "worker-1", "context-1", "session-4"),
        (PARENT_REF_5, CHILD_REF_5, "node-resume", "reservation-resume", "worker-resume", "context-resume", "session-1"),
    )
    for parent_ref, child_ref, node, reservation, worker, context, session in child_specs:
        envelopes[child_ref] = authority.derive_child(
            parent_ref,
            node_id=node,
            reservation_ref=reservation,
            worker_id=worker,
            worker_context_id=context,
            session_id=session,
            node_contract_digest="sha256:" + "e" * 64,
            ttl_seconds=5 if parent_ref == PARENT_REF_4 else 500,
            admission_ref=child_ref,
        )

    if envelopes[CHILD_REF_1]["claim"]["repository"] != "https://github.com/unite-group/example":
        raise AssertionError("issuer did not produce the canonical HTTPS repository")
    print("FIXTURE real_ed25519_envelopes=true canonical_https_repository=true")
    return envelopes


def pg_env() -> dict[str, str]:
    """Return an explicit credential-free local socket environment."""
    return {
        "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
        "LC_ALL": "C",
        "PGHOST": PGHOST,
        "PGPORT": PGPORT,
        "PGUSER": PGUSER,
    }


def run(
    args: list[str],
    *,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        check=check,
        env=pg_env(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def psql(database: str, statement: str, *, check: bool = True) -> subprocess.CompletedProcess[str]:
    return run(
        ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-At", "-d", database, "-c", statement],
        check=check,
    )


def scalar(database: str, statement: str) -> str:
    lines = psql(database, statement).stdout.strip().splitlines()
    return lines[-1] if lines else ""


def expect(actual: str, expected: str, label: str) -> None:
    if actual != expected:
        raise AssertionError(f"{label}: expected {expected!r}, got {actual!r}")
    print(f"ASSERT {label}=PASS value={actual!r}")


def expect_denied(database: str, statement: str, label: str) -> None:
    result = psql(database, statement, check=False)
    if result.returncode == 0:
        raise AssertionError(f"{label}: operation unexpectedly succeeded")
    if "permission denied" not in result.stdout.lower():
        raise AssertionError(f"{label}: unexpected failure: {result.stdout}")
    print(f"ASSERT {label}=PASS permission_denied")


def _signature_bytes(envelope: dict[str, Any]) -> bytes:
    value = envelope["signature"]
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def reserve_sql(parent_id: str, parent_ref: str) -> str:
    envelope = ENVELOPES[parent_ref]
    claim = envelope["claim"]
    return f"""
      SELECT count(*) FROM public.senior_harness_reserve_parent(
        '{parent_id}', '{claim['admission_ref']}', '{claim['source_kind']}',
        '{claim['source_id']}', '{claim['source_version']}', '{claim['repository']}',
        '{claim['objective_digest']}', '{claim['scope_digest']}', '{claim['task_id']}',
        '{claim['plan_id']}', '{claim['base_sha']}', '{claim['node_contract_digest']}',
        '{claim['audience']}', to_timestamp({claim['issued_at']}),
        to_timestamp({claim['expires_at']}), '{claim['signer_key_id']}',
        '{claim['claim_digest']}', decode('{_signature_bytes(envelope).hex()}', 'hex')
      );
    """


def derive_sql(
    child_id: str,
    child_ref: str,
    *,
    audience: str | None = None,
) -> str:
    envelope = ENVELOPES[child_ref]
    claim = envelope["claim"]
    child_audience = audience or claim["audience"]
    return f"""
      SELECT count(*) FROM public.senior_harness_derive_child(
        '{claim['parent_ref']}', '{child_id}', '{claim['admission_ref']}',
        '{claim['node_id']}', '{claim['reservation_ref']}', '{claim['worker_id']}',
        '{claim['worker_context_id']}', '{claim['session_id']}',
        '{claim['node_contract_digest']}', '{child_audience}',
        to_timestamp({claim['issued_at']}), to_timestamp({claim['expires_at']}),
        '{claim['signer_key_id']}', '{claim['claim_digest']}',
        decode('{_signature_bytes(envelope).hex()}', 'hex')
      );
    """


def consume_sql(
    child_ref: str,
    **overrides: Any,
) -> str:
    envelope = ENVELOPES[child_ref]
    claim = copy.deepcopy(envelope["claim"])
    signature = overrides.pop("signature", _signature_bytes(envelope))
    claim.update(overrides)
    if not isinstance(signature, bytes):
        raise TypeError("signature override must be raw bytes")
    return f"""
      SET ROLE senior_harness_consumer;
      SELECT count(*) FROM public.senior_harness_consume_child(
        '{claim['admission_ref']}', '{claim['parent_ref']}', '{claim['claim_digest']}',
        '{claim['source_kind']}', '{claim['source_id']}', '{claim['source_version']}',
        '{claim['repository']}', '{claim['objective_digest']}', '{claim['scope_digest']}',
        '{claim['task_id']}', '{claim['plan_id']}', '{claim['node_id']}',
        '{claim['reservation_ref']}', '{claim['worker_id']}',
        '{claim['worker_context_id']}', '{claim['base_sha']}',
        '{claim['node_contract_digest']}', '{claim['audience']}',
        to_timestamp({claim['issued_at']}), to_timestamp({claim['expires_at']}),
        '{claim['signer_key_id']}', decode('{signature.hex()}', 'hex'),
        '{claim['session_id']}'
      );
    """


def setup_roles() -> set[str]:
    existing = set(
        filter(
            None,
            scalar(
                "postgres",
                "SELECT coalesce(string_agg(rolname, ',' ORDER BY rolname), '') "
                "FROM pg_roles WHERE rolname IN "
                "('senior_harness_issuer','senior_harness_consumer');",
            ).split(","),
        )
    )
    for role in ROLES:
        if role not in existing:
            psql(
                "postgres",
                f'CREATE ROLE "{role}" NOLOGIN NOSUPERUSER NOCREATEDB '
                "NOCREATEROLE NOINHERIT NOREPLICATION;",
            )
    return existing


def cleanup_roles(existing: set[str]) -> None:
    for role in reversed(ROLES):
        if role not in existing:
            psql("postgres", f'DROP ROLE IF EXISTS "{role}";', check=False)


def assert_server_boundary() -> None:
    result = scalar(
        "postgres",
        "SELECT current_setting('server_version_num') || '|' || "
        "current_setting('port') || '|' || current_setting('unix_socket_directories');",
    )
    version, port, sockets = result.split("|", 2)
    if not (150000 <= int(version) < 160000):
        raise RuntimeError(f"requires PostgreSQL 15, got server_version_num={version}")
    if port != PGPORT or PGHOST not in {part.strip() for part in sockets.split(",")}:
        raise RuntimeError(f"refusing non-sandbox PostgreSQL target: port={port} sockets={sockets}")
    print(f"SANDBOX postgres=15 host={PGHOST} port={PGPORT} production=false")


def apply_migration(database: str, pass_number: int) -> None:
    result = run(
        ["psql", "-X", "-v", "ON_ERROR_STOP=1", "-d", database, "-f", str(MIGRATION)]
    )
    if "senior_harness_admissions migration complete" not in result.stdout:
        raise AssertionError(f"migration completion marker missing on pass {pass_number}")
    print(f"APPLY pass={pass_number} exit=0")


def assert_contract(database: str) -> None:
    expect(
        scalar(database, "SELECT to_regclass('private.senior_harness_admissions') IS NOT NULL;"),
        "t",
        "private_table",
    )
    expect(
        scalar(
            database,
            "SELECT relrowsecurity FROM pg_class WHERE oid = "
            "'private.senior_harness_admissions'::regclass;",
        ),
        "t",
        "rls_enabled",
    )
    expect(
        scalar(
            database,
            "SELECT count(*) FROM pg_indexes WHERE schemaname='private' "
            "AND tablename='senior_harness_admissions' AND indexdef LIKE '% WHERE %';",
        ),
        "4",
        "partial_indexes",
    )
    expect(
        scalar(
            database,
            "SELECT count(*) FROM information_schema.routine_privileges "
            "WHERE specific_schema='public' AND grantee='senior_harness_consumer' "
            "AND routine_name IN ('senior_harness_consume_child','senior_harness_assert_active');",
        ),
        "2",
        "consumer_public_wrapper_grants",
    )
    expect(
        scalar(
            database,
            "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace "
            "WHERE n.nspname='public' AND p.proname LIKE 'senior_harness_%' "
            "AND NOT p.prosecdef;",
        ),
        "6",
        "public_wrappers_are_security_invoker",
    )
    expect(
        scalar(
            database,
            "SELECT count(*) FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace, "
            "LATERAL aclexplode(coalesce(p.proacl, acldefault('f', p.proowner))) acl "
            "WHERE n.nspname='public' AND p.proname LIKE 'senior_harness_%' "
            "AND acl.grantee=0 AND acl.privilege_type='EXECUTE';",
        ),
        "0",
        "public_wrapper_public_execute_revoked",
    )
    expect_denied(
        database,
        "SET ROLE senior_harness_consumer; SELECT count(*) FROM private.senior_harness_admissions;",
        "consumer_no_table_read",
    )
    expect_denied(
        database,
        f"SET ROLE senior_harness_consumer; {reserve_sql(PARENT_1, PARENT_REF_1)}",
        "consumer_cannot_reserve",
    )
    expect_denied(
        database,
        "SET ROLE senior_harness_issuer; "
        + consume_sql(CHILD_REF_1).replace(
            "SET ROLE senior_harness_consumer;", ""
        ),
        "issuer_cannot_consume",
    )


def assert_exact_target_and_race(database: str) -> None:
    expect(
        scalar(
            database,
            f"SET ROLE senior_harness_issuer; {reserve_sql(PARENT_1, PARENT_REF_1)}",
        ),
        "1",
        "reserve_parent",
    )
    expect(
        scalar(
            database,
            "SET ROLE senior_harness_issuer; "
            + derive_sql(
                str(uuid.uuid4()),
                "child-shared-audience-denied",
                audience=ENVELOPES[PARENT_REF_1]["claim"]["audience"],
            ),
        ),
        "0",
        "shared_parent_audience_child_denied",
    )
    expect(
        scalar(
            database,
            f"SET ROLE senior_harness_issuer; {derive_sql(CHILD_1, CHILD_REF_1)}",
        ),
        "1",
        "derive_child",
    )
    expect(
        scalar(
            database,
            "SET ROLE senior_harness_issuer; "
            + derive_sql(str(uuid.uuid4()), "child-session-collision"),
        ),
        "1",
        "derive_same_session_different_child",
    )
    expect(
        scalar(
            database,
            "SELECT admission_ref || '|' || parent_ref || '|' || task_id || '|' || "
            "session_id || '|' || audience FROM private.senior_harness_admissions "
            f"WHERE admission_ref='{CHILD_REF_1}';",
        ),
        "child-1|parent-1|task-1|session-1|pi-ceo/build:worker:context-1",
        "signed_ref_task_session_audience_lineage",
    )
    expect(
        scalar(database, consume_sql(CHILD_REF_1, admission_ref=CHILD_1)),
        "0",
        "internal_uuid_is_not_admission_ref",
    )

    signature = _signature_bytes(ENVELOPES[CHILD_REF_1])
    mutations: list[tuple[str, dict[str, Any]]] = [
        ("parent_ref", {"parent_ref": "another-parent"}),
        ("claim", {"claim_digest": "sha256:" + "9" * 64}),
        ("source_kind", {"source_kind": "github"}),
        ("source_id", {"source_id": "RA-9001"}),
        ("source_version", {"source_version": "changed"}),
        ("repository", {"repository": "https://github.com/unite-group/other"}),
        ("objective", {"objective_digest": "sha256:" + "9" * 64}),
        ("scope", {"scope_digest": "sha256:" + "9" * 64}),
        ("task_id", {"task_id": "task-2"}),
        ("plan", {"plan_id": "plan-2"}),
        ("node", {"node_id": "node-2"}),
        ("reservation", {"reservation_ref": "reservation-2"}),
        ("worker", {"worker_id": "worker-2"}),
        ("context", {"worker_context_id": "context-2"}),
        ("base_sha", {"base_sha": "9" * 40}),
        ("node_contract", {"node_contract_digest": "sha256:" + "9" * 64}),
        ("audience", {"audience": "other-runtime"}),
        ("session", {"session_id": "other-session"}),
        ("issued_at", {"issued_at": ENVELOPES[CHILD_REF_1]["claim"]["issued_at"] + 1}),
        ("expires_at", {"expires_at": ENVELOPES[CHILD_REF_1]["claim"]["expires_at"] + 1}),
        ("signer_key_id", {"signer_key_id": "issuer-key-2"}),
        ("signature", {"signature": bytes([signature[0] ^ 1]) + signature[1:]}),
    ]
    for label, changes in mutations:
        value = scalar(database, consume_sql(CHILD_REF_1, **changes))
        expect(value, "0", f"cross_target_{label}_denied")

    def race(_competitor: str) -> str:
        return scalar(database, consume_sql(CHILD_REF_1))

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(race, ("session-race-a", "session-race-b")))
    expect(",".join(results), "0,1", "two_concurrent_consumes_one_winner")
    expect(
        scalar(database, consume_sql("child-session-collision")),
        "0",
        "same_session_different_child_denied_without_error",
    )
    expect(
        scalar(
            database,
            "SELECT state FROM private.senior_harness_admissions "
            "WHERE admission_ref='child-session-collision';",
        ),
        "reserved",
        "same_session_conflict_preserves_reservation",
    )

    winner = scalar(
        database,
        f"SELECT consumption_session_id FROM private.senior_harness_admissions WHERE admission_ref='{CHILD_REF_1}';",
    )
    expect(
        scalar(
            database,
            "SET ROLE senior_harness_consumer; SELECT count(*) FROM "
            f"public.senior_harness_assert_active('{CHILD_REF_1}', "
            f"'{ENVELOPES[CHILD_REF_1]['claim']['claim_digest']}', '{winner}', "
            f"'{ENVELOPES[CHILD_REF_1]['claim']['worker_context_id']}', "
            f"'{ENVELOPES[CHILD_REF_1]['claim']['audience']}');",
        ),
        "1",
        "active_exact_session",
    )
    expect(
        scalar(
            database,
            "SET ROLE senior_harness_consumer; SELECT count(*) FROM "
            f"public.senior_harness_assert_active('{CHILD_REF_1}', "
            f"'{ENVELOPES[CHILD_REF_1]['claim']['claim_digest']}', 'wrong-session', "
            f"'{ENVELOPES[CHILD_REF_1]['claim']['worker_context_id']}', "
            f"'{ENVELOPES[CHILD_REF_1]['claim']['audience']}');",
        ),
        "0",
        "active_wrong_session_denied",
    )
    expect(scalar(database, consume_sql(CHILD_REF_1)), "0", "replay_denied")
    expect(
        scalar(
            database,
            "SET ROLE senior_harness_issuer; SELECT count(*) FROM "
            f"public.senior_harness_release_admission('{CHILD_REF_1}', 'too_late');",
        ),
        "0",
        "consumed_child_is_terminal_for_release",
    )

    immutable = psql(
        database,
        f"UPDATE private.senior_harness_admissions SET repository='changed' WHERE admission_ref='{CHILD_REF_1}';",
        check=False,
    )
    if immutable.returncode == 0 or "immutable" not in immutable.stdout:
        raise AssertionError(f"immutable target update was not blocked: {immutable.stdout}")
    print("ASSERT signed_target_immutable=PASS")
    lifecycle_rewrite = psql(
        database,
        "UPDATE private.senior_harness_admissions "
        "SET consumption_session_id='rewritten-session' "
        f"WHERE admission_ref='{CHILD_REF_1}';",
        check=False,
    )
    if lifecycle_rewrite.returncode == 0 or not any(
        marker in lifecycle_rewrite.stdout for marker in ("append-only", "immutable")
    ):
        raise AssertionError(
            f"consumption binding rewrite was not blocked: {lifecycle_rewrite.stdout}"
        )
    print("ASSERT consumption_binding_immutable=PASS")

    expect(
        scalar(
            database,
            "SET ROLE senior_harness_issuer; SELECT count(*) FROM "
            f"public.senior_harness_revoke_admission('{CHILD_REF_1}', 'explicit_resume');",
        ),
        "1",
        "revoke_active_child_for_explicit_resume",
    )
    expect(
        scalar(
            database,
            "SELECT state || '|' || consumption_session_id FROM "
            "private.senior_harness_admissions "
            f"WHERE admission_ref='{CHILD_REF_1}';",
        ),
        "revoked|session-1",
        "terminal_row_preserves_session_audit",
    )
    expect(
        scalar(
            database,
            f"SET ROLE senior_harness_issuer; {reserve_sql(PARENT_5, PARENT_REF_5)}",
        ),
        "1",
        "reserve_fresh_resume_parent",
    )
    expect(
        scalar(
            database,
            f"SET ROLE senior_harness_issuer; {derive_sql(CHILD_5, CHILD_REF_5)}",
        ),
        "1",
        "derive_fresh_resume_leaf",
    )
    expect(
        scalar(database, consume_sql(CHILD_REF_5)),
        "1",
        "fresh_child_same_session_consumes_after_terminal_predecessor",
    )


def assert_lifecycle(database: str) -> None:
    expect(
        scalar(
            database,
            f"SET ROLE senior_harness_issuer; {reserve_sql(PARENT_2, PARENT_REF_2)}",
        ),
        "1",
        "reserve_revoke_parent",
    )
    expect(
        scalar(
            database,
            "SET ROLE senior_harness_issuer; "
            + derive_sql(CHILD_2, CHILD_REF_2),
        ),
        "1",
        "derive_revoke_child",
    )
    expect(
        scalar(
            database,
            "SET ROLE senior_harness_issuer; SELECT count(*) FROM "
            f"public.senior_harness_revoke_admission('{PARENT_REF_2}', 'operator_revoke');",
        ),
        "1",
        "revoke_parent",
    )
    expect(
        scalar(
            database,
            f"SELECT string_agg(state, ',' ORDER BY admission_kind) FROM private.senior_harness_admissions WHERE admission_id IN ('{PARENT_2}','{CHILD_2}');",
        ),
        "revoked,revoked",
        "parent_revoke_cascades",
    )
    expect(
        scalar(
            database,
            "SET ROLE senior_harness_issuer; "
            + derive_sql(str(uuid.uuid4()), "new-child-after-revoke"),
        ),
        "0",
        "revoked_parent_cannot_derive",
    )

    expect(
        scalar(
            database,
            f"SET ROLE senior_harness_issuer; {reserve_sql(PARENT_3, PARENT_REF_3)}",
        ),
        "1",
        "reserve_release_parent",
    )
    expect(
        scalar(
            database,
            f"SET ROLE senior_harness_issuer; {derive_sql(CHILD_3, CHILD_REF_3)}",
        ),
        "1",
        "derive_release_child",
    )
    expect(
        scalar(
            database,
            "SET ROLE senior_harness_issuer; SELECT count(*) FROM "
            f"public.senior_harness_release_admission('{CHILD_REF_3}', 'worker_finished');",
        ),
        "1",
        "release_child",
    )
    expect(
        scalar(database, consume_sql(CHILD_REF_3)),
        "0",
        "released_child_cannot_consume",
    )
    expect(
        scalar(
            database,
            "SET ROLE senior_harness_issuer; SELECT count(*) FROM "
            f"public.senior_harness_revoke_admission('{CHILD_REF_3}', 'late_revoke');",
        ),
        "0",
        "released_child_terminal",
    )
    child_after_release_id = str(uuid.uuid4())
    expect(
        scalar(
            database,
            "SET ROLE senior_harness_issuer; "
            + derive_sql(
                child_after_release_id,
                "child-parent-release",
            ),
        ),
        "1",
        "derive_child_before_parent_release",
    )
    expect(
        scalar(
            database,
            "SET ROLE senior_harness_issuer; SELECT count(*) FROM "
            f"public.senior_harness_release_admission('{PARENT_REF_3}', 'operator_cancelled');",
        ),
        "1",
        "release_parent",
    )
    expect(
        scalar(
            database,
            "SELECT state FROM private.senior_harness_admissions "
            "WHERE admission_ref='child-parent-release';",
        ),
        "revoked",
        "released_parent_revokes_active_child",
    )

    expect(
        scalar(
            database,
            f"SET ROLE senior_harness_issuer; {reserve_sql(PARENT_4, PARENT_REF_4)}",
        ),
        "1",
        "reserve_expiring_parent",
    )
    expect(
        scalar(
            database,
            "SET ROLE senior_harness_issuer; "
            + derive_sql(CHILD_4, CHILD_REF_4),
        ),
        "1",
        "derive_expiring_child",
    )
    expiry_delay = max(
        0.0,
        ENVELOPES[PARENT_REF_4]["claim"]["expires_at"] - time.time() + 0.20,
    )
    time.sleep(expiry_delay)
    expect(
        scalar(
            database,
            "SET ROLE senior_harness_issuer; SELECT private.senior_harness_expire_admissions("
            f"'{PARENT_REF_4}');",
        ),
        "2",
        "ttl_materializes_terminal_expiry",
    )
    expect(
        scalar(
            database,
            f"SELECT string_agg(state, ',' ORDER BY admission_kind) FROM private.senior_harness_admissions WHERE admission_id IN ('{PARENT_4}','{CHILD_4}');",
        ),
        "expired,expired",
        "parent_and_child_expired",
    )


def main() -> int:
    global ENVELOPES
    if not MIGRATION.is_file():
        raise RuntimeError(f"missing migration: {MIGRATION}")
    for binary in ("psql", "createdb", "dropdb"):
        if run(["sh", "-c", f"command -v {binary}"], check=False).returncode != 0:
            raise RuntimeError(f"missing PostgreSQL binary: {binary}")
    ENVELOPES = build_signed_envelopes()

    database = f"senior_harness_admission_{os.getpid()}_{uuid.uuid4().hex[:8]}"
    if not re.fullmatch(r"[a-z0-9_]+", database):
        raise RuntimeError("unsafe disposable database name")

    lock_fd = LOCK_PATH.open("a+")
    fcntl.flock(lock_fd.fileno(), fcntl.LOCK_EX)
    roles_before: set[str] = set()
    database_created = False
    try:
        assert_server_boundary()
        roles_before = setup_roles()
        run(["createdb", "--template=template0", database])
        database_created = True
        print(f"DATABASE {database} disposable=true")

        apply_migration(database, 1)
        apply_migration(database, 2)
        assert_contract(database)
        assert_exact_target_and_race(database)
        assert_lifecycle(database)
    finally:
        if database_created:
            run(["dropdb", "--if-exists", database], check=False)
        cleanup_roles(roles_before)
        fcntl.flock(lock_fd.fileno(), fcntl.LOCK_UN)
        lock_fd.close()

    print("RESULT senior_harness_admission_migration PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
