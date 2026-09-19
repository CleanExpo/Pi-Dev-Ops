"""Authenticated health evidence; liveness status stays independent of readiness."""
import os
import re


def add_health_evidence(payload: dict) -> None:
    from .session_sdk import generation_readiness

    revision = os.environ.get("RAILWAY_GIT_COMMIT_SHA") or os.environ.get("BUILD_REVISION", "")
    payload["revision"] = revision.lower() if re.fullmatch(r"[0-9a-fA-F]{40}", revision) else None
    payload["generation"] = generation_readiness()
    payload["model_documentation"] = _documentation()
    payload["notebooklm"] = _notebooklm()


def _documentation() -> dict:
    try:
        from .agents.anthropic_intel_refresh import read_documentation_status
        status = read_documentation_status()
        result = {key: status[key] for key in ("status", "sources", "model_registry_verified")
                  if key in status}
        result["upgrade_candidate_count"] = len(status.get("upgrade_candidates", []))
        return result
    except Exception:
        return {"status": "unverified", "sources": [], "model_registry_verified": False}


def _notebooklm() -> dict:
    try:
        from .agents.notebooklm_refresh import get_notebooklm_freshness_summary
        return get_notebooklm_freshness_summary()
    except Exception:
        return {"notebooks_tracked": 0, "stale_count_24h": 0, "stale_count_7d": 0, "summary": []}
