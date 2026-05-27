"""Resolve provider IDs → (workspace_id, workspace_slug).

Phase C / C2. Some provider webhooks don't carry workspace_slug
metadata cleanly — Stripe carries `data.object.customer`, Vercel
carries `payload.project.id`, Linear carries `data.team.key`. This
module maps those provider-side identifiers back to the workspace via
`client_workspaces` columns (`stripe_customer_id`, `vercel_project`,
`linear_team_id`).

Pure-logic: the WorkspaceLookup Protocol is the only I/O surface;
production wires it to a Supabase REST adapter (see WorkspaceLookup
in store_factory follow-up), tests inject a dict.
"""
from __future__ import annotations

from typing import Literal, Protocol

ResolverProvider = Literal["stripe", "vercel", "linear"]


class WorkspaceLookup(Protocol):
    """Single-row read by provider-specific identifier."""
    def by_stripe_customer(self, customer_id: str) -> tuple[str, str] | None: ...
    def by_vercel_project(self, project_id: str) -> tuple[str, str] | None: ...
    def by_linear_team(self, team_key: str) -> tuple[str, str] | None: ...


def resolve_workspace(
    provider: ResolverProvider,
    hint: str | None,
    lookup: WorkspaceLookup,
) -> tuple[str, str] | None:
    """Return (workspace_id, workspace_slug) or None.

    Provider-agnostic facade so parsers can call one function. None
    is returned for ANY ambiguity — callers MUST fall back to
    ParseResult(result='malformed') rather than guess.
    """
    if not hint or not isinstance(hint, str):
        return None
    if provider == "stripe":
        return lookup.by_stripe_customer(hint)
    if provider == "vercel":
        return lookup.by_vercel_project(hint)
    if provider == "linear":
        return lookup.by_linear_team(hint)
    return None


# ============================================================
# In-memory lookup for tests
# ============================================================


class InMemoryWorkspaceLookup:
    """Test stub: feed it dicts in __init__, it just looks them up."""

    def __init__(
        self,
        *,
        stripe: dict[str, tuple[str, str]] | None = None,
        vercel: dict[str, tuple[str, str]] | None = None,
        linear: dict[str, tuple[str, str]] | None = None,
    ) -> None:
        self._stripe = stripe or {}
        self._vercel = vercel or {}
        self._linear = linear or {}

    def by_stripe_customer(self, customer_id: str) -> tuple[str, str] | None:
        return self._stripe.get(customer_id)

    def by_vercel_project(self, project_id: str) -> tuple[str, str] | None:
        return self._vercel.get(project_id)

    def by_linear_team(self, team_key: str) -> tuple[str, str] | None:
        return self._linear.get(team_key)


__all__ = [
    "InMemoryWorkspaceLookup",
    "WorkspaceLookup",
    "resolve_workspace",
]
