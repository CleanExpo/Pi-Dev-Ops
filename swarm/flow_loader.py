"""
swarm/flow_loader.py — RA-1839: Discover + register declarative flows.

Reads YAML/JSON files from Pi-Dev-Ops/flows/ and validates them against
flow_engine.validate_flow(). Registers flows by trigger type:
  * manual → callable via execute_flow(name, ctx)
  * telegram_command → CoS routes the command
  * cron → register with cron scheduler (deferred to caller)
  * webhook → declared, route added to webhooks.py separately

YAML support is optional — if PyYAML is not installed, only JSON files load.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.flow_loader")

_FLOWS: dict[str, dict[str, Any]] = {}

try:
    import yaml  # type: ignore
    _YAML_OK = True
except Exception:
    _YAML_OK = False


def _flows_dir() -> Path:
    root = Path(__file__).resolve().parents[1]
    p = root / "flows"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _parse_file(path: Path) -> dict[str, Any] | None:
    try:
        text = path.read_text(encoding="utf-8")
    except Exception as exc:
        log.warning("flow file unreadable %s: %s", path, exc)
        return None
    try:
        if path.suffix in (".yaml", ".yml"):
            if not _YAML_OK:
                log.info("skipping %s (PyYAML not installed)", path.name)
                return None
            obj = yaml.safe_load(text)
        else:
            obj = json.loads(text)
    except Exception as exc:
        log.warning("flow parse error in %s: %s", path, exc)
        return None
    return obj.get("flow") if isinstance(obj, dict) and "flow" in obj else obj


def discover() -> dict[str, dict[str, Any]]:
    """Re-scan Pi-Dev-Ops/flows/. Returns {name: flow_dict} of valid flows."""
    from . import flow_engine  # circular-import safe at function level

    out: dict[str, dict[str, Any]] = {}
    d = _flows_dir()
    for p in sorted(d.glob("*")):
        if p.suffix not in (".yaml", ".yml", ".json"):
            continue
        flow = _parse_file(p)
        if not flow:
            continue
        errors = flow_engine.validate_flow(flow)
        if errors:
            log.warning("flow %s rejected: %s", p.name, errors)
            continue
        name = flow["name"]
        if name in out:
            log.warning("duplicate flow name %s in %s; skipping", name, p.name)
            continue
        out[name] = flow

    _FLOWS.clear()
    _FLOWS.update(out)
    log.info("discovered %d flow(s): %s", len(out), list(out.keys()))
    return out


def get(name: str) -> dict[str, Any] | None:
    return _FLOWS.get(name)


def list_flows() -> list[str]:
    return sorted(_FLOWS.keys())


__all__ = ["discover", "get", "list_flows"]
