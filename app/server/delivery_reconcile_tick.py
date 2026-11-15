"""RA-8100 delivery reconcile: one read-only tick (lease, load, registry, key, gather, merge, save).

Never raises; every failure is a returned state. Nothing here writes to an outside service:
the only write is the local state file, atomically, under a non-blocking lease. The Linear
key is read only when the tick runs, never logged and never stored.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import delivery_collect as collect
from . import delivery_reconcile as reconcile
from . import delivery_reconcile_gather as gather
from . import delivery_reconcile_store as store

logger = logging.getLogger("pi-ceo.delivery_reconcile")


def _paths(path: str | os.PathLike[str] | None) -> tuple[Path, Path]:
    if path is None:
        return Path(reconcile.STATE_FILE), Path(reconcile.LOCK_FILE)
    return Path(path), Path(str(path) + ".lock")


def _api_key() -> str:
    """LINEAR_API_KEY from the environment, else from config (imported only then)."""
    key = os.environ.get("LINEAR_API_KEY") or ""
    if not key.strip():
        from . import config

        key = getattr(config, "LINEAR_API_KEY", "") or ""
    return key.strip() if isinstance(key, str) else ""


def _read(state: dict[str, Any], now: datetime, summary: dict[str, Any],
          proof: dict[str, Any]) -> tuple[list, list, bool]:
    """Registry, key and gather. A failed step is recorded in ``summary["error"]``; nothing is dropped."""
    try:
        registry = collect.load_registry()
    except collect.RegistryError:
        summary["error"] = "registry_unreadable"
        return [], [], False
    summary["skipped_repos"] = list(registry.skipped_repos)
    summary["unqueryable_projects"] = list(registry.unqueryable_projects)
    api_key = _api_key()
    if not api_key:
        summary["error"] = "no_linear_key"
        return [], [], False
    try:
        return gather.gather(state, registry, api_key, now, summary, proof)
    except Exception as exc:  # noqa: BLE001 — recorded by type name only
        summary["error"] = f"gather_failed_{type(exc).__name__}"
        summary["not_refreshed_ids"] = []
        proof.update(whole=set(), scope=None)  # nothing was proven
        return [], [], False


def _merge(state: dict[str, Any], records: list, findings: list, now: datetime,
           complete: bool, summary: dict[str, Any], proof: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    try:
        return store.apply_tick(state, records, findings, now.timestamp(), complete,
                                whole=proof.get("whole") or (), scope=proof.get("scope"))
    except store.StoreError as exc:
        summary["error"], summary["complete"] = f"merge_failed_{exc}", False
        return store.apply_tick(state, [], [], now.timestamp(), False)


def _locked(now: datetime, state_path: Path) -> dict[str, Any]:
    """The tick body, under the lease."""
    try:
        state = store.load(state_path)
    except store.StoreError:
        return {"error": "state_unreadable", "complete": False, "persisted": False}
    summary = gather.new_summary(now)
    proof: dict[str, Any] = {"whole": set(), "scope": None}  # filled only by a gather that ran
    records, findings, complete = _read(state, now, summary, proof)
    summary["complete"] = bool(complete)
    new_state, new_keys = _merge(state, records, findings, now, bool(complete), summary, proof)
    new_state["summary"] = summary
    persisted = store.save(state_path, new_state)
    reconcile.record_save(persisted)
    out = {**summary, "persisted": persisted, "new_alerts": len(new_keys)}
    logger.info("Delivery reconcile tick: %s", json.dumps(out, sort_keys=True, default=str))
    return out


def run_tick(now: datetime | None = None, path: str | os.PathLike[str] | None = None) -> dict[str, Any]:
    """One reconcile tick. ``path`` overrides the state file; the lock is then ``path + ".lock"``."""
    try:
        when = now if now is not None else datetime.now(timezone.utc)
        if when.tzinfo is None:
            when = when.replace(tzinfo=timezone.utc)
        state_path, lock_path = _paths(path)
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with store.lease(lock_path) as granted:
            if not granted:
                return {"skipped": "lease_held"}
            return _locked(when, state_path)
    except Exception as exc:  # noqa: BLE001 — recorded by type name only
        return {"error": f"tick_failed_{type(exc).__name__}", "complete": False, "persisted": False}
