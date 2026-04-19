"""
test_notebooklm_registry.py — Acceptance tests for .harness/notebooklm-registry.json.

Covers:
  - Registry loads as valid JSON
  - Exactly 3 active notebooks with required fields
  - Exactly 1 pending_creation notebook with source_doc + blocked_until
  - pending_creation acceptance_criteria specifies structured delta report
  - source_doc file exists on disk for pending_creation entry
  - standard_queries list has exactly 10 entries (entity template spec)
  - Active notebook IDs are non-empty UUIDs (not "TBD")
  - Structured delta query: filter notebooks by status returns correct subsets
"""
import json
import os
import re
from pathlib import Path

import pytest

HARNESS_DIR = Path(__file__).resolve().parent.parent / ".harness"
REGISTRY_PATH = HARNESS_DIR / "notebooklm-registry.json"

REQUIRED_ACTIVE_FIELDS = {
    "id", "entity", "name", "purpose", "sources",
    "status", "created_at", "acceptance_criteria", "linked_issue",
}
REQUIRED_PENDING_FIELDS = {
    "id", "entity", "name", "purpose", "sources",
    "status", "blocked_until", "prepared_at", "source_doc",
    "acceptance_criteria", "linked_issue",
}
UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


@pytest.fixture(scope="module")
def registry() -> dict:
    assert REGISTRY_PATH.exists(), f"Registry missing: {REGISTRY_PATH}"
    data = json.loads(REGISTRY_PATH.read_text())
    return data


@pytest.fixture(scope="module")
def active_notebooks(registry) -> list:
    return [nb for nb in registry["notebooks"] if nb["status"] == "active"]


@pytest.fixture(scope="module")
def pending_notebooks(registry) -> list:
    return [nb for nb in registry["notebooks"] if nb["status"] == "pending_creation"]


# ── Registry structure ────────────────────────────────────────────────────────

def test_registry_has_version(registry):
    assert "version" in registry


def test_registry_has_notebooks_list(registry):
    assert isinstance(registry.get("notebooks"), list)


def test_registry_has_standard_queries(registry):
    queries = registry.get("standard_queries", [])
    assert len(queries) == 10, (
        f"standard_queries must have exactly 10 entries (entity template spec); got {len(queries)}"
    )


# ── Active notebooks ──────────────────────────────────────────────────────────

def test_exactly_three_active_notebooks(active_notebooks):
    assert len(active_notebooks) == 3, (
        f"Expected 3 active notebooks, found {len(active_notebooks)}"
    )


def test_active_notebooks_have_required_fields(active_notebooks):
    for nb in active_notebooks:
        missing = REQUIRED_ACTIVE_FIELDS - nb.keys()
        assert not missing, (
            f"Notebook '{nb.get('entity')}' missing fields: {missing}"
        )


def test_active_notebook_ids_are_uuids(active_notebooks):
    for nb in active_notebooks:
        assert UUID_RE.match(nb["id"]), (
            f"Notebook '{nb.get('entity')}' has non-UUID id: '{nb['id']}'"
        )


def test_active_notebooks_have_non_empty_sources(active_notebooks):
    for nb in active_notebooks:
        assert isinstance(nb["sources"], list) and len(nb["sources"]) > 0, (
            f"Notebook '{nb.get('entity')}' has empty sources list"
        )


def test_active_notebooks_have_linked_issues(active_notebooks):
    for nb in active_notebooks:
        assert nb["linked_issue"].startswith("RA-"), (
            f"Notebook '{nb.get('entity')}' linked_issue must be RA-xxx format"
        )


# ── Pending-creation notebook ─────────────────────────────────────────────────

def test_exactly_one_pending_creation_notebook(pending_notebooks):
    assert len(pending_notebooks) == 1, (
        f"Expected 1 pending_creation notebook, found {len(pending_notebooks)}"
    )


def test_pending_notebook_has_required_fields(pending_notebooks):
    nb = pending_notebooks[0]
    missing = REQUIRED_PENDING_FIELDS - nb.keys()
    assert not missing, (
        f"pending_creation notebook '{nb.get('entity')}' missing fields: {missing}"
    )


def test_pending_notebook_acceptance_criteria_specifies_structured_delta(pending_notebooks):
    """The Intel notebook acceptance criteria must reference the structured delta report (RA-830)."""
    nb = pending_notebooks[0]
    criteria = nb.get("acceptance_criteria", "")
    assert "structured delta" in criteria.lower(), (
        f"pending_creation acceptance_criteria must include 'structured delta'; got: '{criteria}'"
    )


def test_pending_notebook_source_doc_exists(pending_notebooks):
    """The source_doc referenced by the pending notebook must exist on disk."""
    nb = pending_notebooks[0]
    source_doc = nb.get("source_doc", "")
    assert source_doc, "pending_creation notebook must have a non-empty source_doc field"
    full_path = Path(__file__).resolve().parent.parent / source_doc
    assert full_path.exists(), (
        f"source_doc '{source_doc}' referenced in registry does not exist at {full_path}"
    )


def test_pending_notebook_has_blocked_until(pending_notebooks):
    nb = pending_notebooks[0]
    blocked_until = nb.get("blocked_until", "")
    assert blocked_until, "pending_creation notebook must declare blocked_until date"


# ── Structured delta query (filter by status) ─────────────────────────────────

def test_filter_active_returns_only_active(registry):
    """Querying notebooks by status='active' returns only active entries."""
    result = [nb for nb in registry["notebooks"] if nb["status"] == "active"]
    assert all(nb["status"] == "active" for nb in result)
    assert len(result) == 3


def test_filter_pending_creation_returns_intel_notebook(registry):
    """Querying notebooks by status='pending_creation' returns the Intel entry."""
    result = [nb for nb in registry["notebooks"] if nb["status"] == "pending_creation"]
    assert len(result) == 1
    assert result[0]["entity"] == "Intel"


def test_structured_delta_query_format(pending_notebooks):
    """
    Structured delta query spec: the pending_creation notebook must have all fields
    needed to generate a delta report for RA-830 after the conference (22-24 Apr 2026).

    Required fields for delta report generation:
      - acceptance_criteria: defines the query to run
      - source_doc: pre-conference context document
      - linked_issue: RA-828 (where the delta report is attached)
      - blocked_until: gate date before the conference ends
    """
    nb = pending_notebooks[0]
    delta_fields = {"acceptance_criteria", "source_doc", "linked_issue", "blocked_until"}
    present = {f for f in delta_fields if nb.get(f)}
    assert present == delta_fields, (
        f"Structured delta report requires all of {delta_fields}; missing: {delta_fields - present}"
    )
