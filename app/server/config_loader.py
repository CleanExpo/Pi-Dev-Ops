"""config_loader.py — one accessor per config file, with absence handled ON PURPOSE.

WHY THIS EXISTS
---------------
`.harness/config.yaml` carried the role->model map. `#607` untracked `.harness/` to repair the
secrets-scanner exclusion premise and took the map with it. `model_policy._load_harness()`
caught the resulting error, logged a warning, and returned `{}` — so every role silently
resolved to the `"sonnet"` default. planner, orchestrator and adversary dropped off opus.

It was invisible for four days. It logged a warning on EVERY load the whole time.

**Logging is not a control.** A warning nobody is watching is indistinguishable from silence.
That is why nothing in this module logs-and-continues.

THE SPLIT
---------
Two kinds of file, two absence behaviours, decided by one question:
*could this file's contents live in code as a specification?*

  SPECIFICATION  the contents ARE a decision (which model a role gets, what the safety rules
                 are). The spec lives HERE, in code. The file, if present, overrides it.
                 Absence is CORRECT, not degraded.

  INSTANCE DATA  the contents describe the world (which projects exist, what is scheduled).
                 No default can be right. Absence is a REAL FAILURE and must stop the process
                 at STARTUP, not at first use — a process that starts and then behaves oddly
                 is the failure mode this module exists to remove.

Never default an EXTERNAL RESOURCE IDENTIFIER. Being wrong about a voice id, a project id or
an API endpoint is invisible in exactly the way the model map was. Those fail loud even when
they sit inside an otherwise specification-shaped file — see `margot_identity()`.

PATHS
-----
`_CONFIG_DIR` is the single place the location is written down. Commit 2 moves these files out
of `.harness/`; that is a one-line change here and nowhere else.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]

# The one place the config location is written down. Commit 2 changes this line and nothing
# else. Exported publicly so consumers that need the DIRECTORY (rather than a named accessor)
# can split their config base away from their runtime-state base — see triage.py.
CONFIG_DIR = REPO_ROOT / "config" / "harness"
_CONFIG_DIR = CONFIG_DIR  # internal alias, kept for readability below

CONFIG_YAML = _CONFIG_DIR / "config.yaml"
PROJECTS_JSON = _CONFIG_DIR / "projects.json"
CRON_TRIGGERS_JSON = _CONFIG_DIR / "cron-triggers.json"
CONTENT_MANIFEST_JSON = _CONFIG_DIR / "content_manifest.json"
PROVISIONED_TOOLS_YAML = _CONFIG_DIR / "provisioned-tools.yaml"
MARGOT_IDENTITY_JSON = _CONFIG_DIR / "margot" / "assets" / "margot_identity.json"
NOTEBOOKLM_REGISTRY_JSON = _CONFIG_DIR / "notebooklm-registry.json"

# The curated starting set of lessons. NOT the runtime store — see lessons._ensure_seeded().
# It gets no accessor here because absence is survivable: an unseeded lesson store is empty,
# which is degraded but not wrong, and the fail-loud treatment below would stop a process over
# something that is genuinely optional.
LESSONS_SEED_JSONL = _CONFIG_DIR / "lessons.seed.jsonl"


class ConfigMissingError(RuntimeError):
    """A required instance-data file is absent. Not recoverable, not defaultable."""


def _fail(path: Path, what: str) -> "ConfigMissingError":
    return ConfigMissingError(
        f"{what} not found at {path}.\n"
        f"  This file is INSTANCE DATA — it describes the world, so no in-code default can be\n"
        f"  correct. Refusing to continue rather than running with an empty value.\n"
        f"  If this is a fresh clone, the file is not in the repository (see #607)."
    )


def _read_json(path: Path, what: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise _fail(path, what) from exc
    except json.JSONDecodeError as exc:
        raise ConfigMissingError(f"{what} at {path} is not valid JSON: {exc}") from exc


def _read_yaml(path: Path, what: str) -> Any:
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except FileNotFoundError as exc:
        raise _fail(path, what) from exc
    except yaml.YAMLError as exc:
        raise ConfigMissingError(f"{what} at {path} is not valid YAML: {exc}") from exc


# ─────────────────────────────────────────────────────────────────────────────
# SPECIFICATION — config.yaml
#
# This IS the harness specification. The role->model map below is the decision;
# the file merely carried it. Absence resolves to exactly this, which is correct.
# ─────────────────────────────────────────────────────────────────────────────
HARNESS_SPEC: dict[str, Any] = {
    "project": "pi-dev-ops",
    "harness_version": 1.3,
    "agents": {
        "planner": {"model": "opus", "temperature": 0.3},
        "orchestrator": {"model": "opus", "temperature": 0.2},
        "generator": {"model": "sonnet", "temperature": 0.2, "sdk": True},
        "evaluator": {"model": "sonnet", "temperature": 0.1, "sdk": True, "parallel": True},
        "adversary": {"model": "opus", "temperature": 0.2, "sdk": True},
        "board": {"model": "sonnet", "temperature": 0.4},
        "monitor": {"model": "haiku", "temperature": 0.1},
    },
    "evaluator_confidence": {"auto_ship_score": 9.5, "auto_ship_pct": 90, "flag_pct": 60},
    "qa": {"max_rounds": 3, "auto_escalate": True},
    "autonomy_budget": {},
    "staleness": {},
    "cron": {},
    "ci": {},
    "sdk": {},
    "observability": {},
    "om1_planner": {},
}

# Cache is keyed on the RESOLVED PATH, not a bare flag.
#
# A path-blind cache is a real bug, not just a test annoyance: whoever holds the first call
# pins the value for the whole process even if the path later changes. It surfaced as
# evals/test_model_policy_golden.py passing alone and failing in the full suite — one test
# overrode planner->haiku and every later reader inherited it. A stale cache that reports a
# model nobody configured is the same class of invisible-wrong as the regression this module
# exists to fix.
_harness_cache: dict[str, Any] | None = None
_harness_cache_key: str | None = None


def _deep_merge(spec: dict, override: dict) -> dict:
    out = dict(spec)
    for k, v in (override or {}).items():
        out[k] = _deep_merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def harness_config(*, refresh: bool = False) -> dict[str, Any]:
    """The harness specification, with the on-disk file overriding it where present.

    SPECIFICATION. A missing file yields HARNESS_SPEC — the correct models, not the weakest.
    A malformed file still raises: unreadable is not the same as absent.
    """
    global _harness_cache, _harness_cache_key
    key = str(CONFIG_YAML)
    if _harness_cache is None or refresh or _harness_cache_key != key:
        if CONFIG_YAML.is_file():
            _harness_cache = _deep_merge(HARNESS_SPEC, _read_yaml(CONFIG_YAML, "harness config"))
        else:
            _harness_cache = dict(HARNESS_SPEC)
        _harness_cache_key = key
    return _harness_cache


def agent_models(*, refresh: bool = False) -> dict[str, Any]:
    """The role -> agent-config map. Never empty; never silently all-sonnet."""
    return harness_config(refresh=refresh).get("agents") or HARNESS_SPEC["agents"]


# ─────────────────────────────────────────────────────────────────────────────
# INSTANCE DATA — absent means stop
# ─────────────────────────────────────────────────────────────────────────────
def projects() -> Any:
    """The project registry. INSTANCE DATA — raises if absent."""
    return _read_json(PROJECTS_JSON, "project registry (projects.json)")


def cron_triggers() -> Any:
    """Scheduled trigger definitions. INSTANCE DATA — raises if absent.

    The previous reader returned `[]` on any error, which reads as 'nothing is scheduled'
    and stops every cron without a single failure anywhere.
    """
    return _read_json(CRON_TRIGGERS_JSON, "cron triggers (cron-triggers.json)")


def content_manifest() -> Any:
    """Content production registry. INSTANCE DATA — raises if absent."""
    return _read_json(CONTENT_MANIFEST_JSON, "content manifest (content_manifest.json)")


def provisioned_tools() -> Any:
    """Provisioned/banned tool lists. INSTANCE DATA — raises if absent.

    Ruled instance data despite being policy-shaped: the file declares
    `source_of_truth: ~/.claude/skills/library/connections.md`, so it is a projection of
    something outside this repo. An in-code copy would be a copy of a copy.
    """
    return _read_yaml(PROVISIONED_TOOLS_YAML, "provisioned tools (provisioned-tools.yaml)")


def notebooklm_registry() -> Any:
    """Which NotebookLM notebooks exist. INSTANCE DATA — raises if absent.

    Declares notebook UUIDs, their sources and their linked issues. No in-code default can
    be right: a made-up UUID points at someone else's notebook or nothing at all, which is
    the "never default an EXTERNAL RESOURCE IDENTIFIER" rule at the top of this module.

    Moved here 2026-08-03. It was the eighth file left behind in `.harness/` by #607, and
    it failed the same way as the other seven — absent from a clean clone, so
    tests/test_notebooklm_registry.py errored at setup on all 16 cases with
    "Registry missing".
    """
    return _read_json(NOTEBOOKLM_REGISTRY_JSON, "NotebookLM registry (notebooklm-registry.json)")


# ─────────────────────────────────────────────────────────────────────────────
# SPLIT FILE — margot_identity.json
# Specification parts default; external resource identifiers do not.
# ─────────────────────────────────────────────────────────────────────────────
MARGOT_SPEC: dict[str, Any] = {
    "base_prompt": "",
    "safety_rules": [],
    "identity": {},
    "variants": {},
}

# Absent from the file => raise. Being wrong about a voice id is invisible.
MARGOT_REQUIRED_KEYS = ("elevenlabs", "projects", "canonical_wiki_page")


def margot_identity() -> dict[str, Any]:
    """Margot identity. SPLIT: spec keys default, external identifiers fail loud."""
    if not MARGOT_IDENTITY_JSON.is_file():
        raise _fail(MARGOT_IDENTITY_JSON, "margot identity (margot_identity.json)")
    data = _read_json(MARGOT_IDENTITY_JSON, "margot identity (margot_identity.json)")
    missing = [k for k in MARGOT_REQUIRED_KEYS if not data.get(k)]
    if missing:
        raise ConfigMissingError(
            f"margot identity at {MARGOT_IDENTITY_JSON} is missing external resource "
            f"identifier(s): {', '.join(missing)}.\n"
            f"  These are never defaulted — a wrong voice id or project id fails invisibly."
        )
    return _deep_merge(MARGOT_SPEC, data)


# ─────────────────────────────────────────────────────────────────────────────
# STARTUP VALIDATOR
# ─────────────────────────────────────────────────────────────────────────────
REQUIRED_AT_STARTUP: tuple[tuple[Path, str], ...] = (
    (PROJECTS_JSON, "projects.json"),
    (CRON_TRIGGERS_JSON, "cron-triggers.json"),
    (CONTENT_MANIFEST_JSON, "content_manifest.json"),
    (PROVISIONED_TOOLS_YAML, "provisioned-tools.yaml"),
    (MARGOT_IDENTITY_JSON, "margot_identity.json"),
    # The registry's runtime consumers are periodic background probes, and they degrade
    # softly on purpose — aborting the health watchdog would take every watchdog scheduled
    # after it down too. That makes STARTUP the only place a missing registry can be caught
    # loudly, which is exactly where this module's docstring says the check belongs.
    (NOTEBOOKLM_REGISTRY_JSON, "notebooklm-registry.json"),
)


def validate_startup() -> None:
    """Raise if any instance-data file is absent. Call at process start, not at first use.

    Deliberately fatal. Every other startup hook in app_factory is 'non-fatal, continue';
    this one is not, because continuing is the defect.
    """
    missing = [name for path, name in REQUIRED_AT_STARTUP if not path.is_file()]
    if missing:
        raise ConfigMissingError(
            "Refusing to start — required instance-data file(s) absent: "
            + ", ".join(missing)
            + f"\n  Looked in {_CONFIG_DIR}.\n"
            "  These describe the world and cannot be defaulted. Starting without them means\n"
            "  running with empty schedules, no projects and no content registry while\n"
            "  reporting healthy."
        )
    # Existence is not enough for the NotebookLM registry: a malformed file passes the
    # is_file() sweep above, and every runtime consumer of the registry then degrades
    # softly by design — so boot is the only loud moment. Parse it here; _read_json
    # raises ConfigMissingError naming the file and the JSON error.
    notebooklm_registry()
