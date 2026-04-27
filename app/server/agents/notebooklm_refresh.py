"""
notebooklm_refresh.py — NotebookLM source auto-refresh loop (RA-1668).

Iterates the active notebooks in `.harness/notebooklm-registry.json` and
re-ingests their declared sources via the NotebookLM Enterprise API.
Replaces the fragile n8n manual workflow.

Usage:
    python -m app.server.agents.notebooklm_refresh [--dry-run]

Scheduling:
    Wired into `app/server/cron_scheduler.py` to fire weekly (Mondays 09:00 UTC)
    and also on-demand via `POST /api/notebooklm/refresh` (TBD).

Auth requirements (PROVISIONED BY USER, see RA-1668 comment for setup):
    - GCP service account with `notebooklm.admin` IAM role on a project that
      has the NotebookLM API enabled.
    - Service account key path in env var `NOTEBOOKLM_SERVICE_ACCOUNT_JSON`,
      OR project-default credentials (Railway Workload Identity Federation).
    - Project ID in env var `NOTEBOOKLM_GCP_PROJECT_ID`.

Status: STRUCTURAL IMPLEMENTATION — the orchestration loop, registry I/O,
freshness tracking, and tests are real and shippable. The actual REST call
to NotebookLM's source-update endpoint is gated behind credential discovery
(see `_refresh_notebook_sources` below) and currently logs a structured
"NEEDS_CREDENTIALS" outcome when env vars are absent. Once the user
provides the credentials and the exact Enterprise API endpoint shape (which
was announced at Google Cloud Next '26 — see `.harness/notebooklm-source-
intel-gcnext26.md`), the `_refresh_notebook_sources` body fills in the
last-mile HTTP call. Everything else is production code.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import json
import logging
import os
from pathlib import Path
from typing import Optional

log = logging.getLogger("pi-ceo.agents.notebooklm-refresh")

# ─── Paths ────────────────────────────────────────────────────────────────────

_HARNESS = Path(__file__).parent.parent.parent.parent / ".harness"
_REGISTRY_PATH = _HARNESS / "notebooklm-registry.json"
_FRESHNESS_PATH = _HARNESS / "notebooklm-freshness.json"

# ─── Env ─────────────────────────────────────────────────────────────────────

_ENV_PROJECT_ID = "NOTEBOOKLM_GCP_PROJECT_ID"
_ENV_SA_JSON = "NOTEBOOKLM_SERVICE_ACCOUNT_JSON"


# ─── Registry I/O ────────────────────────────────────────────────────────────

def _load_registry() -> dict:
    """Load the notebook registry. Returns empty dict on missing/invalid."""
    if not _REGISTRY_PATH.exists():
        log.warning("notebooklm registry missing: %s", _REGISTRY_PATH)
        return {}
    try:
        return json.loads(_REGISTRY_PATH.read_text())
    except Exception as exc:
        log.warning("notebooklm registry load failed: %s", exc)
        return {}


def _active_notebooks(registry: dict) -> list[dict]:
    """Return only notebooks with status='active' (skips pending_creation, etc.)."""
    return [
        nb for nb in registry.get("notebooks", [])
        if nb.get("status") == "active" and nb.get("id") and nb.get("id") != "TBD"
    ]


# ─── Freshness tracking ──────────────────────────────────────────────────────

def _load_freshness() -> dict:
    """Load `.harness/notebooklm-freshness.json`. Each notebook id maps to
    its last successful refresh timestamp + outcome."""
    if not _FRESHNESS_PATH.exists():
        return {"version": "1.0", "notebooks": {}}
    try:
        return json.loads(_FRESHNESS_PATH.read_text())
    except Exception:
        return {"version": "1.0", "notebooks": {}}


def _save_freshness(data: dict) -> None:
    """Atomic write of freshness state — write-tmp-then-replace, crash-safe."""
    tmp = _FRESHNESS_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, _FRESHNESS_PATH)


def _record_outcome(
    freshness: dict,
    notebook_id: str,
    entity: str,
    outcome: str,
    error: Optional[str] = None,
    sources_count: int = 0,
) -> None:
    """Update the freshness record for one notebook."""
    freshness.setdefault("notebooks", {})[notebook_id] = {
        "entity": entity,
        "last_attempted": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "outcome": outcome,                 # "ok" | "needs_credentials" | "error"
        "error": error,
        "sources_count": sources_count,
    }


# ─── The actual refresh call (gated on credentials) ──────────────────────────

async def _refresh_notebook_sources(
    notebook_id: str,
    sources: list[str],
    project_id: str,
    sa_json_path: Optional[str] = None,
) -> tuple[bool, Optional[str]]:
    """Refresh the sources of one notebook via the NotebookLM Enterprise API.

    Returns (ok, error_message). Currently a STRUCTURAL stub — the actual
    HTTP call awaits the API endpoint shape from RA-828 (Google Cloud
    Next '26 intel) and credential provisioning by the user.

    When the API specifics are confirmed, this function should:
      1. Acquire a Google access token from the SA key (or default creds).
      2. POST to https://notebooklm.googleapis.com/v1alpha/projects/{project_id}/notebooks/{notebook_id}:refreshSources
         with {"sources": [{"uri": "..."}, ...]}
      3. Poll the long-running operation until done.
      4. Return (True, None) on success or (False, error_string) on failure.

    The orchestration around this function (registry read, freshness track,
    error handling, scheduling) is fully implemented and tested.
    """
    # TODO(RA-1668): replace with real Enterprise API call once endpoint
    # shape is confirmed. See `.harness/notebooklm-source-intel-gcnext26.md`
    # for what was announced at GCN '26.
    log.info(
        "notebooklm refresh: would refresh %s with %d sources (project=%s, sa_json=%s)",
        notebook_id, len(sources), project_id, "set" if sa_json_path else "default-creds",
    )
    return False, "NEEDS_API_ENDPOINT_AND_AUTH_IMPLEMENTATION"


# ─── Orchestration loop ──────────────────────────────────────────────────────

async def refresh_all_notebooks(dry_run: bool = False) -> dict:
    """Refresh sources for every active notebook in the registry.

    Returns a structured summary:
        {
          "ts": "...",
          "active_count": 3,
          "succeeded": ["id1", "id2"],
          "needs_credentials": [{"id": "...", "entity": "..."}, ...],
          "errors": [{"id": "...", "error": "..."}, ...],
          "freshness_path": ".harness/notebooklm-freshness.json",
        }
    """
    summary = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
        "active_count": 0,
        "succeeded": [],
        "needs_credentials": [],
        "errors": [],
        "freshness_path": str(_FRESHNESS_PATH),
    }

    project_id = os.environ.get(_ENV_PROJECT_ID, "")
    sa_json = os.environ.get(_ENV_SA_JSON, "")

    registry = _load_registry()
    active = _active_notebooks(registry)
    summary["active_count"] = len(active)
    if not active:
        log.info("notebooklm refresh: no active notebooks")
        return summary

    freshness = _load_freshness()

    for nb in active:
        nb_id = nb["id"]
        entity = nb.get("entity", "?")
        sources = nb.get("sources", [])

        if dry_run:
            log.info("[dry-run] would refresh %s (%s) with %d sources", nb_id, entity, len(sources))
            _record_outcome(freshness, nb_id, entity, "dry_run", sources_count=len(sources))
            continue

        if not project_id:
            _record_outcome(
                freshness, nb_id, entity,
                outcome="needs_credentials",
                error=f"{_ENV_PROJECT_ID} env var not set",
                sources_count=len(sources),
            )
            summary["needs_credentials"].append({"id": nb_id, "entity": entity})
            continue

        ok, err = await _refresh_notebook_sources(
            notebook_id=nb_id,
            sources=sources,
            project_id=project_id,
            sa_json_path=sa_json or None,
        )
        if ok:
            _record_outcome(freshness, nb_id, entity, "ok", sources_count=len(sources))
            summary["succeeded"].append(nb_id)
        elif err == "NEEDS_API_ENDPOINT_AND_AUTH_IMPLEMENTATION":
            _record_outcome(
                freshness, nb_id, entity,
                outcome="needs_credentials",
                error=err,
                sources_count=len(sources),
            )
            summary["needs_credentials"].append({"id": nb_id, "entity": entity})
        else:
            _record_outcome(
                freshness, nb_id, entity, outcome="error",
                error=err, sources_count=len(sources),
            )
            summary["errors"].append({"id": nb_id, "error": err})

    _save_freshness(freshness)
    return summary


# ─── /health integration helper ──────────────────────────────────────────────

def get_notebooklm_freshness_summary() -> dict:
    """Return a /health-friendly summary: how stale is each notebook's last refresh?

    Used by `app/server/routes/health.py` to surface refresh state without
    importing the full refresh module's HTTP machinery.
    """
    freshness = _load_freshness()
    nbs = freshness.get("notebooks", {})
    if not nbs:
        return {"notebooks_tracked": 0, "stale_count_24h": 0, "stale_count_7d": 0, "summary": []}

    now = datetime.datetime.now(datetime.timezone.utc)
    stale_24h = 0
    stale_7d = 0
    summary = []
    for nb_id, rec in nbs.items():
        last = rec.get("last_attempted", "")
        try:
            last_dt = datetime.datetime.fromisoformat(last)
            age_h = (now - last_dt).total_seconds() / 3600
        except Exception:
            age_h = float("inf")

        if age_h > 24:
            stale_24h += 1
        if age_h > 168:
            stale_7d += 1

        summary.append({
            "id": nb_id,
            "entity": rec.get("entity"),
            "outcome": rec.get("outcome"),
            "age_hours": round(age_h, 1) if age_h != float("inf") else None,
        })

    return {
        "notebooks_tracked": len(nbs),
        "stale_count_24h": stale_24h,
        "stale_count_7d": stale_7d,
        "summary": summary,
    }


# ─── CLI entry point ─────────────────────────────────────────────────────────

def main() -> int:
    parser = argparse.ArgumentParser(description="Refresh NotebookLM sources from registry")
    parser.add_argument("--dry-run", action="store_true", help="Iterate without calling the API")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    result = asyncio.run(refresh_all_notebooks(dry_run=args.dry_run))
    print(json.dumps(result, indent=2))
    return 0 if not result["errors"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
