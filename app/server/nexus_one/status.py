"""Read-only Nexus One synthetic status. Never a health or ship signal.

Inspects mounted paths to decide ``registered``. The status endpoint itself
does not count: operators must be able to read ``registered=false``.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .types import LINEAGE

STATUS_PATH = "/api/nexus-one/status"
LIVE_PATH_PREFIX = "/api/nexus-one"
HEALTHY_KEYS = ("ok", "green", "healthy", "ready", "shipped")


def _join_path(prefix: str, path: str) -> str:
    if not prefix:
        return path
    if not path:
        return prefix
    return prefix.rstrip("/") + "/" + path.lstrip("/")


def collect_route_paths(router: Any) -> tuple[str, ...]:
    """Collect mounted paths, including FastAPI included routers."""
    found: list[str] = []
    seen: set[int] = set()
    _walk_router(router, "", found, seen)
    return tuple(found)


def _walk_router(
    node: Any, prefix: str, found: list[str], seen: set[int]
) -> None:
    ident = id(node)
    if ident in seen:
        return
    seen.add(ident)
    # FastAPI 0.141 stores include_router as _IncludedRouter (no .path).
    original = getattr(node, "original_router", None)
    if original is not None and original is not node:
        ctx = getattr(node, "include_context", None)
        extra = getattr(ctx, "prefix", "") or ""
        _walk_router(original, _join_path(prefix, extra) if extra else prefix, found, seen)
        return
    routes = getattr(node, "routes", None)
    if routes is None:
        nested = getattr(node, "router", None)
        if nested is not None and nested is not node:
            _walk_router(nested, prefix, found, seen)
        return
    for route in routes:
        _walk_route(route, node, prefix, found, seen)


def _walk_route(
    route: Any, node: Any, prefix: str, found: list[str], seen: set[int]
) -> None:
    path = getattr(route, "path", None)
    combined = _join_path(prefix, path) if isinstance(path, str) and path else prefix
    if combined:
        found.append(combined)
    child = getattr(route, "app", None)
    if child is not None and child is not node and not callable(child):
        _walk_router(child, combined or prefix, found, seen)
    included = getattr(route, "original_router", None) or getattr(route, "router", None)
    if included is not None and included is not node:
        ctx = getattr(route, "include_context", None)
        extra = getattr(ctx, "prefix", "") or ""
        _walk_router(included, _join_path(prefix, extra) if extra else prefix, found, seen)


def live_router_registered(paths: Iterable[str]) -> bool:
    """True only when a non-status ``/api/nexus-one/*`` route is mounted."""
    for raw in paths:
        path = (raw or "").rstrip("/") or "/"
        if path.startswith(LIVE_PATH_PREFIX) and path != STATUS_PATH:
            return True
    return False


def synthetic_status(*, registered: bool) -> dict[str, Any]:
    """Fail-closed operator payload. Unregistered must never look healthy."""
    return {
        "lineage": LINEAGE,
        "excluded_from_real_acceptance": True,
        "registered": bool(registered),
        "ready": False,
        "shipped": False,
        "worker_enrolled": False,
        "max_subscription_only": True,
        "windows_policy": "review_only",
    }


def status_payload_for_app(app: Any) -> dict[str, Any]:
    return synthetic_status(registered=live_router_registered(collect_route_paths(app)))


def healthy_bits_on(payload: dict[str, Any]) -> tuple[str, ...]:
    return tuple(key for key in HEALTHY_KEYS if payload.get(key) is True)
