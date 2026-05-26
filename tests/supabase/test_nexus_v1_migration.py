"""Static-parse tests for supabase/migrations/20260601_nexus_v1.sql.

These tests do NOT connect to a database — they parse the SQL file and
assert structural invariants. Applying the migration to prod Supabase is
gated on operator approval per OPERATOR MODE + Nexus pitch §11.

Invariants checked:
  - Exactly 8 expected tables are created
  - Every table has `enable row level security`
  - Every table has at least one RLS policy
  - nexus_audit has the append-only triple policy (tenant_read + no_update + no_delete)
  - All foreign keys resolve to expected target tables
  - Rollback section in file header lists tables in correct reverse order
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATION_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "supabase"
    / "migrations"
    / "20260601_nexus_v1.sql"
)

EXPECTED_TABLES = (
    "clients",
    "client_workspaces",
    "client_projects",
    "client_channels",
    "client_loops",
    "approvals",
    "outcomes",
    "nexus_audit",
)


@pytest.fixture(scope="module")
def sql() -> str:
    return MIGRATION_PATH.read_text()


# ============================================================
# File exists + non-trivial
# ============================================================


def test_migration_file_exists(sql: str):
    assert MIGRATION_PATH.exists()
    assert len(sql) > 1000  # not a stub


def test_header_carries_spec_reference(sql: str):
    assert "Nexus v1" in sql
    assert "03-nexus-autonomous-onboarding-and-growth-os-v1.md" in sql


# ============================================================
# All 8 tables created
# ============================================================


@pytest.mark.parametrize("table", EXPECTED_TABLES)
def test_table_create_present(sql: str, table: str):
    pattern = re.compile(
        rf"create\s+table\s+if\s+not\s+exists\s+public\.{re.escape(table)}\b",
        re.IGNORECASE,
    )
    assert pattern.search(sql), f"missing CREATE TABLE for {table}"


def test_no_unexpected_tables_created(sql: str):
    matches = re.findall(
        r"create\s+table\s+if\s+not\s+exists\s+public\.(\w+)\b",
        sql,
        re.IGNORECASE,
    )
    assert set(matches) == set(EXPECTED_TABLES), (
        f"unexpected tables {set(matches) - set(EXPECTED_TABLES)} or "
        f"missing {set(EXPECTED_TABLES) - set(matches)}"
    )


# ============================================================
# RLS enabled on every table
# ============================================================


@pytest.mark.parametrize("table", EXPECTED_TABLES)
def test_rls_enabled(sql: str, table: str):
    pattern = re.compile(
        rf"alter\s+table\s+public\.{re.escape(table)}\s+enable\s+row\s+level\s+security",
        re.IGNORECASE,
    )
    assert pattern.search(sql), f"RLS not enabled on {table}"


# ============================================================
# Every table has at least one policy
# ============================================================


@pytest.mark.parametrize("table", EXPECTED_TABLES)
def test_at_least_one_policy(sql: str, table: str):
    pattern = re.compile(
        rf"create\s+policy\s+\w+\s+on\s+public\.{re.escape(table)}\b",
        re.IGNORECASE,
    )
    assert pattern.search(sql), f"no RLS policy for {table}"


# ============================================================
# nexus_audit append-only triple
# ============================================================


def test_nexus_audit_has_read_policy(sql: str):
    assert re.search(
        r"create\s+policy\s+tenant_read_nexus_audit\s+on\s+public\.nexus_audit\s+for\s+select",
        sql,
        re.IGNORECASE,
    )


def test_nexus_audit_no_update_policy(sql: str):
    pattern = re.compile(
        r"create\s+policy\s+nexus_audit_no_update\s+on\s+public\.nexus_audit\s+"
        r"for\s+update\s+using\s+\(\s*false\s*\)",
        re.IGNORECASE,
    )
    assert pattern.search(sql), "missing nexus_audit_no_update policy"


def test_nexus_audit_no_delete_policy(sql: str):
    pattern = re.compile(
        r"create\s+policy\s+nexus_audit_no_delete\s+on\s+public\.nexus_audit\s+"
        r"for\s+delete\s+using\s+\(\s*false\s*\)",
        re.IGNORECASE,
    )
    assert pattern.search(sql), "missing nexus_audit_no_delete policy"


# ============================================================
# Foreign keys resolve to expected targets
# ============================================================


EXPECTED_FKS = (
    ("client_workspaces", "client_id", "clients"),
    ("client_projects", "workspace_id", "client_workspaces"),
    ("client_channels", "workspace_id", "client_workspaces"),
    ("client_loops", "workspace_id", "client_workspaces"),
    ("approvals", "workspace_id", "client_workspaces"),
    ("outcomes", "workspace_id", "client_workspaces"),
    ("outcomes", "project_id", "client_projects"),
    ("nexus_audit", "approval_id", "approvals"),
    ("nexus_audit", "outcomes_link", "outcomes"),
)


@pytest.mark.parametrize("table,column,target", EXPECTED_FKS)
def test_foreign_key_present(sql: str, table: str, column: str, target: str):
    # Capture the body of the table's CREATE TABLE between parens; check FK there
    table_block_re = re.compile(
        rf"create\s+table\s+if\s+not\s+exists\s+public\.{re.escape(table)}\s*\((.*?)^\)",
        re.IGNORECASE | re.DOTALL | re.MULTILINE,
    )
    m = table_block_re.search(sql)
    assert m, f"could not locate CREATE TABLE block for {table}"
    body = m.group(1)
    fk_pattern = re.compile(
        rf"\b{re.escape(column)}\b\s+\S+\s+(?:not\s+null\s+)?references\s+public\.{re.escape(target)}\b",
        re.IGNORECASE | re.DOTALL,
    )
    assert fk_pattern.search(body), (
        f"FK {table}.{column} -> {target} not found in table body"
    )


# ============================================================
# Status / kind enum constraints
# ============================================================


def test_clients_status_enum(sql: str):
    # Verify every required client status is in the CHECK constraint
    expected_states = (
        "intake", "qualified", "workspace_created",
        "wired", "in_loop", "paused", "off_boarded",
    )
    for state in expected_states:
        assert f"'{state}'" in sql, f"client status {state} missing from CHECK"


def test_channel_kinds_enum(sql: str):
    for kind in ("telegram_chat", "telegram_bot", "slack", "email"):
        assert f"'{kind}'" in sql


def test_loop_kinds_enum(sql: str):
    for kind in ("discovery", "content", "kpi", "geo", "support", "compliance"):
        assert f"'{kind}'" in sql


def test_outcome_sources_enum(sql: str):
    for source in ("stripe", "vercel", "posthog", "sentry", "linear", "manual"):
        assert f"'{source}'" in sql


def test_approval_status_enum(sql: str):
    for status in ("pending", "approved", "denied", "auto-denied", "expired"):
        assert f"'{status}'" in sql


# ============================================================
# Rollback section in header
# ============================================================


def test_rollback_section_present(sql: str):
    # Header should list drop-table statements in reverse dependency order
    assert "Rollback" in sql
    # nexus_audit must be dropped before approvals (FK dependency)
    audit_idx = sql.find("drop table if exists public.nexus_audit")
    approvals_idx = sql.find("drop table if exists public.approvals")
    assert audit_idx > 0 and approvals_idx > 0
    assert audit_idx < approvals_idx, (
        "nexus_audit must be dropped before approvals (FK target)"
    )


def test_rollback_lists_all_tables(sql: str):
    # Extract the comment block and verify every expected table appears
    for table in EXPECTED_TABLES:
        assert f"drop table if exists public.{table}" in sql, (
            f"rollback missing drop for {table}"
        )
