"""Resolve configured GitHub branch checks before authorizing candidate delivery.

API contracts: docs.github.com/en/rest/branches/branch-protection and
/docs.github.com/en/rest/repos/rules#get-rules-for-a-branch. Effective branch
rules include active organization/repository rules, excluding disabled/evaluate.
Unreadable classic protection is ambiguous, including 404, and fails closed.
"""
from __future__ import annotations

from urllib.parse import quote

from .github_ci_evidence import CIVerificationError, all_pages, candidate_evidence, required_result


def _requirement(context, app=None) -> tuple[str, int | None]:
    if not isinstance(context, str) or not context.strip():
        raise CIVerificationError("Required check has no context")
    if app == -1:  # Classic branch protection: any app is explicitly allowed.
        app = None
    if app is not None and (type(app) is not int or app <= 0):
        raise CIVerificationError("Required check has invalid app identity")
    return context, app


def _classic_requirements(protection) -> set:
    if not isinstance(protection, dict) or "required_status_checks" not in protection:
        raise CIVerificationError("Classic branch protection is unknown")
    checks = protection["required_status_checks"]
    if checks is None:
        return set()
    if not isinstance(checks, dict) or not isinstance(checks.get("contexts"), list):
        raise CIVerificationError("Malformed classic required checks")
    bound = checks.get("checks", [])
    if not isinstance(bound, list) or any(not isinstance(row, dict) for row in bound):
        raise CIVerificationError("Malformed app-bound required checks")
    required = {_requirement(row.get("context"), row.get("app_id")) for row in bound}
    bound_names = {context for context, _ in required}
    for context in checks["contexts"]:
        entry = _requirement(context)
        if context not in bound_names:
            required.add(entry)
    return required


def required_contexts(request, repo: str, branch: str = "main") -> frozenset:
    ref = quote(branch, safe="")
    protection = request("GET", f"/repos/{repo}/branches/{ref}/protection")
    required = _classic_requirements(protection)
    for rule in all_pages(request, f"/repos/{repo}/rules/branches/{ref}"):
        if not isinstance(rule.get("type"), str):
            raise CIVerificationError("Malformed effective branch rule")
        if rule["type"] != "required_status_checks":
            continue
        parameters = rule.get("parameters")
        checks = parameters.get("required_status_checks") if isinstance(parameters, dict) else None
        if not isinstance(checks, list) or any(not isinstance(row, dict) for row in checks):
            raise CIVerificationError("Malformed ruleset required checks")
        required.update(_requirement(row.get("context"), row.get("integration_id")) for row in checks)
    if not required:
        raise CIVerificationError("No required CI contexts are configured")
    return frozenset(required)


def verify_pr_head(request, repo: str, number: int, sha: str) -> None:
    detail = request("GET", f"/repos/{repo}/pulls/{number}")
    if not isinstance(detail, dict) or not isinstance(detail.get("head"), dict):
        raise CIVerificationError("PR head could not be verified")
    if detail["head"].get("sha") != sha:
        raise CIVerificationError("PR head no longer matches reviewed candidate")
    base = detail.get("base")
    if not isinstance(base, dict) or base.get("ref") != "main":
        raise CIVerificationError("PR base no longer matches the protected target")


def candidate_snapshot(request, repo: str, number: int, sha: str) -> tuple[str, frozenset]:
    verify_pr_head(request, repo, number, sha)
    required = required_contexts(request, repo)
    runs, statuses = candidate_evidence(request, repo, sha)
    # Re-read both policy and PR after paginated evidence collection. A policy
    # or target change cannot turn an earlier successful snapshot into authority.
    if required_contexts(request, repo) != required:
        raise CIVerificationError("Required CI policy changed during verification")
    verify_pr_head(request, repo, number, sha)
    return required_result(required, runs, statuses), required
