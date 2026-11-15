"""RA-8100 B5e: the outside-field inventory as DATA, and the completeness test that keeps it whole.

Each row is (source, field, domain, null, empty, reason, tick):
- ``null``: what a null or absent value MEANS: ``fail`` (the read raises ``reason``), ``ok`` (accepted;
  the meaning is in FIELD-INVENTORY-B5e.md) or ``missing:<code>`` (``MissingCommit``, spec row 4);
- ``empty``: the empty string: ``fail``, ``ok``, or ``null`` (means the same as null);
- ``reason``: the reason code every other out-of-domain value must raise;
- ``tick``: a bad value could make a record look healthier, so a tick-level row exists for it.
The completeness test parses the collector sources and fails when a field is read that has no row.
"""
from __future__ import annotations

import ast
import re

from _delivery_reconcile_support import REPO_ROOT

INVENTORY: list[tuple[str, str, str, str, str, str, bool]] = [
    ("pulls_list", "number", "posint", "fail", "fail", "malformed_pull", False),
    ("pulls_list", "state", "enum", "fail", "fail", "malformed_pull", True),
    ("pulls_list", "merged", "bool", "ok", "fail", "malformed_pull", True),
    ("pulls_list", "draft", "bool", "fail", "fail", "malformed_pull", True),
    ("pulls_list", "created_at", "timestamp", "fail", "fail", "malformed_pull", True),
    ("pulls_list", "head", "object", "ok", "fail", "malformed_pull", True),
    ("pulls_list", "head.sha", "sha", "ok", "null", "malformed_sha", True),
    ("pulls_list", "user", "object", "ok", "fail", "malformed_pull", False),
    ("pulls_list", "user.login", "login", "fail", "fail", "malformed_pull", False),
    ("pulls_list", "user.type", "enum", "fail", "fail", "malformed_pull", True),
    ("pull", "number", "posint", "fail", "fail", "pull_mismatch", False),
    ("pull", "state", "enum", "fail", "fail", "malformed_pull", True),
    ("pull", "merged", "bool", "fail", "fail", "malformed_pull", True),
    ("pull", "merged_at", "timestamp", "ok", "fail", "malformed_pull", False),
    ("pull", "draft", "bool", "fail", "fail", "malformed_pull", True),
    ("pull", "created_at", "timestamp", "fail", "fail", "malformed_pull", True),
    ("pull", "head", "object", "missing:empty_head", "fail", "malformed_pull", True),
    ("pull", "head.sha", "sha", "missing:empty_head", "null", "malformed_sha", True),
    ("pull", "user", "object", "ok", "fail", "malformed_pull", False),
    ("pull", "user.login", "login", "fail", "fail", "malformed_pull", False),
    ("pull", "user.type", "enum", "fail", "fail", "malformed_pull", False),
    ("pull_merged", "merge_commit_sha", "sha", "missing:no_merge_sha", "null", "malformed_sha", True),
    ("pull_merged", "merged_at", "timestamp", "fail", "fail", "malformed_pull", True),
    ("commit", "sha", "sha", "fail", "fail", "commit_mismatch", False),
    ("check_runs", "check_runs", "list", "fail", "fail", "malformed_list", False),
    ("check_runs", "total_count", "count", "fail", "fail", "malformed_list", True),
    ("check_run", "id", "posint", "fail", "fail", "malformed_check_run", False),
    ("check_run", "status", "enum", "fail", "fail", "malformed_check_run", True),
    ("check_run", "conclusion", "enum", "ok", "fail", "malformed_check_run", True),
    ("check_run", "completed_at", "timestamp", "ok", "fail", "malformed_check_run", True),
    ("status", "state", "enum", "fail", "fail", "malformed_status", True),
    ("status", "total_count", "count", "fail", "fail", "malformed_status", True),
    ("review", "id", "posint", "fail", "fail", "malformed_review", False),
    ("review", "user", "object", "fail", "fail", "malformed_review", False),
    ("review", "user.login", "login", "fail", "fail", "malformed_review", True),
    ("review", "user.type", "enum", "fail", "fail", "malformed_review", False),
    ("review", "state", "enum", "fail", "fail", "malformed_review", True),
    ("review", "commit_id", "sha", "ok", "fail", "malformed_review", True),
    ("review", "submitted_at", "timestamp", "fail", "fail", "malformed_review", True),
    ("compare", "status", "enum", "fail", "fail", "malformed_compare", True),
    ("linear_page", "project", "object", "fail", "fail", "malformed_page", False),
    ("linear_page", "project.issues", "object", "fail", "fail", "malformed_page", False),
    ("linear_page", "project.issues.nodes", "list", "fail", "fail", "malformed_page", False),
    ("linear_page", "project.issues.pageInfo.hasNextPage", "bool", "fail", "fail", "malformed_page", False),
    ("linear_page", "project.issues.pageInfo.endCursor", "text", "fail", "fail", "malformed_page", False),
    ("linear_issue", "id", "node_id", "fail", "fail", "malformed_page", False),
    ("linear_issue", "identifier", "linear_id", "fail", "fail", "malformed_page", False),
    ("linear_issue", "state", "object", "fail", "fail", "malformed_page", True),
    ("linear_issue", "state.type", "enum", "fail", "fail", "malformed_page", True),
    ("linear_issue", "startedAt", "timestamp", "ok", "fail", "bad_timestamp", True),
    ("linear_issue", "completedAt", "timestamp", "ok", "fail", "bad_timestamp", True),
    ("linear_issue", "assignee", "object", "ok", "fail", "malformed_page", True),
    ("linear_issue", "assignee.name", "text", "ok", "fail", "malformed_page", True),
    ("linear_links", "description", "text_any", "ok", "ok", "links_incomplete", True),
    ("linear_links", "attachments", "object", "fail", "fail", "links_incomplete", False),
    ("linear_links", "attachments.pageInfo.hasNextPage", "bool", "fail", "fail", "links_incomplete", False),
    ("linear_links", "attachments.nodes", "list", "fail", "fail", "links_incomplete", False),
    ("linear_links", "attachments.nodes.url", "text_any", "ok", "ok", "links_incomplete", True),
    ("vercel", "deployments", "list", "fail", "fail", "malformed_deployments", False),
    ("vercel", "state", "enum", "fail", "fail", "malformed_deployments", True),
    ("vercel", "created", "posint", "fail", "fail", "malformed_deployments", True),
    ("vercel", "target", "text", "ok", "fail", "malformed_deployments", True),
    ("vercel", "meta", "object", "ok", "fail", "malformed_deployments", True),
    ("vercel", "meta.githubCommitSha", "sha", "ok", "fail", "malformed_deployments", True),
    ("env", "RAILWAY_GIT_COMMIT_SHA", "sha", "fail", "fail", "no_revision", False),
    ("env", "BUILD_REVISION", "sha", "fail", "fail", "no_revision", False),
]

# Which outside sources each collector function reads. A function missing here fails the walk.
FUNC_SOURCES: dict[str, set[str]] = {
    "_issue_page": {"linear_page", "linear_issue"}, "_node_ok": {"linear_issue"}, "fetch_missions": {"linear_issue"},
    "vercel_latest_ready": {"vercel"}, "own_revision": {"env"},
    "_page": {"check_runs"}, "_author": {"pull", "review"}, "_pull_common": {"pull"}, "_head": {"pull"},
    "open_prs": {"pulls_list"}, "_open_item": {"pulls_list"}, "_pull_facts": {"pull", "pull_merged"}, "_check_run": {"check_run"},
    "_review": {"review"}, "_commit": {"commit"}, "_status": {"status"}, "compare_status": {"compare"},
    "pr_evidence": {"check_runs", "check_run", "review", "pull"}, "linear_links": {"linear_links"},
}
# Reads of the registry entry or of the collector's own facts dict: not outside answers.
INTERNAL = {
    ("load_registry", "projects"), ("load_registry", "id"), ("load_registry", "repo"),
    ("load_registry", "linear_project_id"), ("load_registry", "linear_team_id"),
    ("fetch_missions", "repo"), ("fetch_missions", "linear_project_id"),
    ("vercel_latest_ready", "vercel_project_id"), ("vercel_latest_ready", "vercel_team_id"),
    ("vercel_latest_ready", "repo"), ("pr_evidence", "state"), ("pr_evidence", "merge_sha"),
    ("pr_evidence", "head_sha"), ("pr_evidence", "check_runs"), ("pr_evidence", "status"),
    ("pr_evidence", "reviews"),
}
COLLECTORS = ("delivery_collect", "delivery_collect_github", "delivery_collect_fields")
QUERIED_UNREAD = {"createdAt"}  # in the Linear query, read nowhere downstream (recorded, not validated)
GRAPHQL_WORDS = {"first"}


def segments(sources: set[str]) -> set[str]:
    return {part for src, fld, *_ in INVENTORY if src in sources for part in fld.split(".")}


def reads(source: str) -> list[tuple[str, str]]:
    """(enclosing function, name) for every ``.get("x")``, ``["x"]`` and ``identity=``/``key=`` constant."""
    out: list[tuple[str, str]] = []
    for fn in [n for n in ast.walk(ast.parse(source)) if isinstance(n, ast.FunctionDef)]:
        for node in ast.walk(fn):
            const = None
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "get" \
                    and node.args:
                const = node.args[0]
            elif isinstance(node, ast.Subscript):
                const = node.slice
            elif isinstance(node, ast.keyword) and node.arg in ("identity", "key"):
                const = node.value
            if isinstance(const, ast.Constant) and isinstance(const.value, str):
                out.append((fn.name, const.value))
    return out


def unlisted(pairs: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Every read that is neither internal nor a segment of an inventory field of its function's sources."""
    return [(fn, name) for fn, name in pairs if (fn, name) not in INTERNAL
            and (fn not in FUNC_SOURCES or name not in segments(FUNC_SOURCES[fn]))]


def query_words(query: str) -> set[str]:
    """Field names asked for in each Linear issue node."""
    return set(re.findall(r"[A-Za-z]+", query[query.index("nodes {"):]))


def test_every_collector_read_has_an_inventory_row() -> None:
    for module in COLLECTORS:
        source = (REPO_ROOT / f"app/server/{module}.py").read_text(encoding="utf-8")
        assert unlisted(reads(source)) == [], module


def test_every_linear_field_queried_has_a_row() -> None:
    from app.server import delivery_collect as dc

    known = segments({"linear_page", "linear_issue", "linear_links"}) | QUERIED_UNREAD | GRAPHQL_WORDS
    assert query_words(dc._MISSIONS_QUERY) - known == set()


def test_negative_control_the_walk_catches_a_field_with_no_row() -> None:
    """The walk is a control only if it fails: a new read, an unmapped function, a new queried field."""
    planted = ('def _pull_common(pr):\n    return pr.get("auto_merge"), pr["head"]\n'
               'def _new_reader(x):\n    return x.get("sha")\n'
               'def _paged(r):\n    return f(identity="node_id")\n')
    assert unlisted(reads(planted)) == [("_pull_common", "auto_merge"), ("_new_reader", "sha"),
                                        ("_paged", "node_id")]
    known = segments({"linear_issue", "linear_links"}) | QUERIED_UNREAD | GRAPHQL_WORDS
    assert query_words("nodes { id priority }") - known == {"priority"}


def test_inventory_rows_are_well_formed() -> None:
    keys = [(src, fld) for src, fld, *_ in INVENTORY]
    assert len(keys) == len(set(keys))
    for _, _, domain, null, empty, reason, tick in INVENTORY:
        assert domain in {"sha", "timestamp", "enum", "posint", "count", "bool", "login", "linear_id", "node_id",
                          "text", "text_any", "object", "list"}
        assert null in ("fail", "ok") or null.startswith("missing:")
        assert empty in ("fail", "ok", "null") and reason and isinstance(tick, bool)
