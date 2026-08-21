"""Contract and real PostgreSQL tests for Senior Harness admissions."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
MIGRATION = ROOT / "supabase/migrations/20260821_senior_harness_admissions.sql"
HARNESS = ROOT / "scripts/test_senior_harness_admission_migration.py"


@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRATION.read_text()


def test_private_table_and_closed_lifecycle(sql: str) -> None:
    assert "CREATE TABLE IF NOT EXISTS private.senior_harness_admissions" in sql
    assert "'parent', 'child'" in sql
    assert "admission_ref TEXT NOT NULL UNIQUE" in sql
    assert "claim_schema_version TEXT NOT NULL" in sql
    for state in ("reserved", "consumed", "released", "revoked", "expired"):
        assert f"'{state}'" in sql
    assert "ENABLE ROW LEVEL SECURITY" in sql


def test_signed_target_is_immutable(sql: str) -> None:
    assert "senior_harness_guard_admission_update" in sql
    assert "signed admission target is immutable" in sql
    for field in (
        "admission_ref",
        "parent_ref",
        "claim_schema_version",
        "source_kind",
        "source_id",
        "source_version",
        "repository",
        "objective_digest",
        "scope_digest",
        "task_id",
        "plan_id",
        "node_id",
        "reservation_ref",
        "worker_id",
        "worker_context_id",
        "session_id",
        "base_sha",
        "node_contract_digest",
        "audience",
        "claim_digest",
        "signer_key_id",
        "signature",
    ):
        assert f"NEW.{field}" in sql
        assert f"OLD.{field}" in sql


def test_digests_preserve_signed_sha256_representation(sql: str) -> None:
    for field in (
        "objective_digest",
        "scope_digest",
        "node_contract_digest",
        "claim_digest",
    ):
        assert f"{field} ~ '^sha256:[0-9a-f]{{64}}$'" in sql


def test_child_audience_is_worker_context_specific(sql: str) -> None:
    assert "v_parent.audience || ':worker:' || p_worker_context_id" in sql


@pytest.mark.parametrize(
    "function_name",
    (
        "senior_harness_reserve_parent",
        "senior_harness_derive_child",
        "senior_harness_consume_child",
        "senior_harness_release_admission",
        "senior_harness_revoke_admission",
        "senior_harness_assert_active",
        "senior_harness_expire_admissions",
    ),
)
def test_atomic_function_surface_exists(sql: str, function_name: str) -> None:
    assert re.search(
        rf"CREATE OR REPLACE FUNCTION private\.{function_name}\s*\(",
        sql,
        re.IGNORECASE,
    )
    assert re.search(
        rf"REVOKE ALL ON FUNCTION private\.{function_name}\s*\(",
        sql,
        re.IGNORECASE,
    )


def test_consume_uses_one_conditional_update_and_locks_parent(sql: str) -> None:
    match = re.search(
        r"CREATE OR REPLACE FUNCTION private\.senior_harness_consume_child\(.*?\n\$function\$;",
        sql,
        re.DOTALL,
    )
    assert match
    body = match.group(0)
    assert body.count("UPDATE private.senior_harness_admissions AS child") == 1
    assert "FOR SHARE" in body
    assert "child.state = 'reserved'" in body
    assert "parent.state = 'reserved'" in body
    assert "child.expires_at > clock_timestamp()" in body
    assert "parent.expires_at > clock_timestamp()" in body
    for comparison in (
        "child.admission_ref = p_admission_ref",
        "child.parent_ref = p_parent_ref",
        "child.claim_schema_version = '1.0'",
        "child.claim_digest = p_claim_digest",
        "child.source_kind = p_source_kind",
        "child.source_id = p_source_id",
        "child.source_version = p_source_version",
        "child.repository = p_repository",
        "child.objective_digest = p_objective_digest",
        "child.scope_digest = p_scope_digest",
        "child.task_id = p_task_id",
        "child.plan_id = p_plan_id",
        "child.node_id = p_node_id",
        "child.reservation_ref = p_reservation_ref",
        "child.worker_id = p_worker_id",
        "child.worker_context_id = p_worker_context_id",
        "child.session_id = p_session_id",
        "child.base_sha = p_base_sha",
        "child.node_contract_digest = p_node_contract_digest",
        "child.audience = p_audience",
        "child.issued_at = p_issued_at",
        "child.expires_at = p_expires_at",
        "child.signer_key_id = p_signer_key_id",
        "child.signature = p_signature",
    ):
        assert comparison in body
    assert "WHEN unique_violation THEN" in body


@pytest.mark.parametrize(
    "function_name",
    (
        "senior_harness_reserve_parent",
        "senior_harness_derive_child",
        "senior_harness_consume_child",
        "senior_harness_assert_active",
        "senior_harness_release_admission",
        "senior_harness_revoke_admission",
    ),
)
def test_public_postgrest_wrappers_are_security_invoker(sql: str, function_name: str) -> None:
    match = re.search(
        rf"CREATE OR REPLACE FUNCTION public\.{function_name}\(.*?\n\$wrapper\$;",
        sql,
        re.DOTALL,
    )
    assert match
    assert "SECURITY INVOKER" in match.group(0)
    assert re.search(
        rf"REVOKE ALL ON FUNCTION public\.{function_name}\(",
        sql,
    )


def test_partial_uniqueness_covers_live_parent_child_and_session(sql: str) -> None:
    indexes = re.findall(
        r"CREATE UNIQUE INDEX(?: IF NOT EXISTS)? (\w+).*?\n\s*WHERE (.*?);",
        sql,
        re.DOTALL | re.IGNORECASE,
    )
    by_name = {name: predicate for name, predicate in indexes}
    assert "senior_harness_one_live_parent_target_idx" in by_name
    assert "state = 'reserved'" in by_name["senior_harness_one_live_parent_target_idx"]
    assert "senior_harness_one_live_child_leaf_idx" in by_name
    assert "'reserved', 'consumed'" in by_name["senior_harness_one_live_child_leaf_idx"]
    assert "senior_harness_one_consumption_session_idx" in by_name
    session_predicate = by_name["senior_harness_one_consumption_session_idx"]
    assert "state = 'consumed'" in session_predicate
    assert "consumption_session_id IS NOT NULL" in session_predicate
    assert "DROP INDEX IF EXISTS private.senior_harness_one_consumption_session_idx" in sql


def test_least_privilege_grants_are_split(sql: str) -> None:
    assert "REVOKE ALL ON TABLE private.senior_harness_admissions" in sql
    assert "FROM PUBLIC, senior_harness_issuer, senior_harness_consumer" in sql
    grants: dict[str, set[str]] = {
        "senior_harness_issuer": set(),
        "senior_harness_consumer": set(),
    }
    for function_name, role in re.findall(
        r"GRANT EXECUTE ON FUNCTION private\.(\w+)\(.*?\)\s+TO (senior_harness_(?:issuer|consumer));",
        sql,
        re.DOTALL,
    ):
        grants[role].add(function_name)
    assert grants["senior_harness_issuer"] == {
        "senior_harness_expire_admissions",
        "senior_harness_reserve_parent",
        "senior_harness_derive_child",
        "senior_harness_release_admission",
        "senior_harness_revoke_admission",
    }
    assert grants["senior_harness_consumer"] == {
        "senior_harness_consume_child",
        "senior_harness_assert_active",
    }


def _local_postgres_15_available() -> bool:
    if shutil.which("psql") is None:
        return False
    probe = subprocess.run(
        [
            "psql",
            "-X",
            "-h",
            "/tmp",
            "-p",
            "5432",
            "-d",
            "postgres",
            "-Atqc",
            "SELECT current_setting('server_version_num');",
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    return probe.returncode == 0 and probe.stdout.strip().startswith("15")


@pytest.mark.skipif(
    not _local_postgres_15_available(),
    reason="credential-free local PostgreSQL 15 sandbox is not available at /tmp:5432",
)
def test_real_postgres_idempotence_atomicity_and_security() -> None:
    result = subprocess.run(
        [sys.executable, str(HARNESS)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout
    assert "FIXTURE real_ed25519_envelopes=true canonical_https_repository=true" in result.stdout
    assert "ASSERT two_concurrent_consumes_one_winner=PASS" in result.stdout
    assert "ASSERT same_session_different_child_denied_without_error=PASS" in result.stdout
    assert "ASSERT terminal_row_preserves_session_audit=PASS" in result.stdout
    assert "ASSERT fresh_child_same_session_consumes_after_terminal_predecessor=PASS" in result.stdout
    assert "ASSERT public_wrapper_public_execute_revoked=PASS" in result.stdout
    assert "ASSERT signed_target_immutable=PASS" in result.stdout
    assert "RESULT senior_harness_admission_migration PASS" in result.stdout
