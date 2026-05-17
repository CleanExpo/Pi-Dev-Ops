"""Plaud Actions — sub-project 2 of 3. Reads ingested wiki/plaud/ pages, extracts
action items via Anthropic Haiku 4.5, files Linear tickets, posts ONE Telegram
digest per cron batch. Spec: docs/superpowers/specs/2026-05-17-plaud-actions-design.md
"""
from __future__ import annotations

import json
import logging
import os
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple, Optional

# Local import: linear_helpers lives in the same scripts/ directory
sys.path.insert(0, str(Path(__file__).parent))
from linear_helpers import create_linear_issue, TicketRef


log = logging.getLogger("plaud_actions")

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
ANTHROPIC_MODEL = "claude-haiku-4-5"

PROMPT_TEMPLATE = (Path(__file__).parent / "prompts" / "action_extraction.md").read_text()

PROJECTS_JSON = Path(__file__).resolve().parent.parent / ".harness" / "projects.json"
DEFAULT_PORTFOLIO_ID = "pi-dev-ops"  # fallback when LLM picks unknown


# ── Dataclasses ────────────────────────────────────────────────────────────

@dataclass
class Action:
    title: str
    description: str
    priority: int = 3  # Linear: 0=None, 1=Urgent, 2=High, 3=Normal, 4=Low


@dataclass
class ActionExtraction:
    portfolio: str
    confidence: float
    reasoning: str
    actions: list[Action] = field(default_factory=list)


@dataclass
class BatchResult:
    plaud_id: str
    title: str
    wiki_path: str
    portfolio: str
    tickets: list[TicketRef] = field(default_factory=list)
    status: str = "ok"  # ok | partial | no_actions | parse_failed | skipped


class LinearRoute(NamedTuple):
    team_id: str
    project_id: str
    status: str  # matched | fallback_unknown | fallback_low_confidence


# ── Portfolio routing ──────────────────────────────────────────────────────

def resolve_linear_route(portfolio: str, *, projects_json_path: Path = PROJECTS_JSON) -> LinearRoute:
    """Look up team_id + project_id for a portfolio. Falls back to pi-dev-ops if
    portfolio is unknown or not in the registry. Raises if the registry itself is
    missing or doesn't contain the pi-dev-ops fallback entry."""
    data = json.loads(projects_json_path.read_text())
    projects = {p["id"]: p for p in data.get("projects", [])}

    if portfolio in projects:
        p = projects[portfolio]
        return LinearRoute(
            team_id=p["linear_team_id"],
            project_id=p["linear_project_id"],
            status="matched",
        )

    default = projects.get(DEFAULT_PORTFOLIO_ID)
    if not default:
        raise RuntimeError(
            f"projects.json missing default portfolio '{DEFAULT_PORTFOLIO_ID}'"
        )
    return LinearRoute(
        team_id=default["linear_team_id"],
        project_id=default["linear_project_id"],
        status="fallback_unknown",
    )


# ── Anthropic Messages API ─────────────────────────────────────────────────

import time

_REPORT_ACTIONS_TOOL = {
    "name": "report_actions",
    "description": "Report the portfolio classification and extracted action items.",
    "input_schema": {
        "type": "object",
        "properties": {
            "portfolio": {
                "type": "string",
                "enum": ["pi-dev-ops", "restoreassist", "disaster-recovery",
                         "dr-nrpg", "nrpg-onboarding", "synthex", "unite-group",
                         "nodejs-starter", "oh-my-codex", "ccw-crm", "carsi", "unknown"],
            },
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "reasoning": {"type": "string"},
            "actions": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "title": {"type": "string"},
                        "description": {"type": "string"},
                        "priority": {"type": "integer", "minimum": 0, "maximum": 4},
                    },
                    "required": ["title", "description", "priority"],
                },
            },
        },
        "required": ["portfolio", "confidence", "reasoning", "actions"],
    },
}


class _AuthError:
    """Sentinel returned when Anthropic auth fails — caller DMs once and skips."""
    pass


def extract_actions(*, page_md: str, anthropic_api_key: str):
    """Call Anthropic Messages API with tool-use forcing report_actions. Returns
    ActionExtraction on success, _AuthError on 401, None on parse / rate-limit /
    other failures. Retries once on 429."""
    if not anthropic_api_key:
        log.warning("extract_actions: ANTHROPIC_API_KEY missing")
        return _AuthError()

    body = {
        "model": ANTHROPIC_MODEL,
        "max_tokens": 2048,
        "system": PROMPT_TEMPLATE,
        "messages": [{"role": "user", "content": page_md}],
        "tools": [_REPORT_ACTIONS_TOOL],
        "tool_choice": {"type": "tool", "name": "report_actions"},
    }
    payload = json.dumps(body).encode()
    headers = {
        "x-api-key": anthropic_api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }

    data = None
    for attempt in range(2):
        req = urllib.request.Request(ANTHROPIC_API_URL, data=payload,
                                     headers=headers, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode())
            break
        except urllib.error.HTTPError as e:
            if e.code == 401:
                log.warning("extract_actions: Anthropic 401 auth failed")
                return _AuthError()
            if e.code == 429 and attempt == 0:
                log.warning("extract_actions: 429 rate-limited, sleeping 30s before retry")
                time.sleep(30)
                continue
            log.warning("extract_actions: Anthropic HTTP %d: %s", e.code, e.reason)
            return None
        except (urllib.error.URLError, json.JSONDecodeError, OSError) as e:
            log.warning("extract_actions: transport error: %s", e)
            return None

    if data is None:
        return None

    # Walk content blocks looking for tool_use
    for block in data.get("content", []):
        if block.get("type") == "tool_use" and block.get("name") == "report_actions":
            inp = block.get("input", {})
            return ActionExtraction(
                portfolio=inp.get("portfolio", "unknown"),
                confidence=float(inp.get("confidence", 0.0)),
                reasoning=inp.get("reasoning", ""),
                actions=[
                    Action(title=a["title"], description=a["description"],
                           priority=a.get("priority", 3))
                    for a in inp.get("actions", [])
                ],
            )

    log.warning("extract_actions: no tool_use block in response: %s",
                json.dumps(data)[:500])
    return None


# ── Linear ticket batch ────────────────────────────────────────────────────

def create_linear_tickets(
    *,
    actions: list[Action],
    team_id: str,
    project_id: str,
    wiki_link: str,
    linear_api_key: str,
) -> list[TicketRef]:
    """File one Linear ticket per Action. Returns the TicketRef for each ticket
    that was created successfully. Failed ones are simply absent — caller
    detects partial success via len(result) < len(actions)."""
    refs: list[TicketRef] = []
    for action in actions:
        description = (
            f"{action.description}\n\n"
            f"---\n"
            f"Source: [{wiki_link.rsplit('/', 1)[-1]}]({wiki_link})"
        )
        ref = create_linear_issue(
            api_key=linear_api_key,
            title=action.title,
            description=description,
            team_id=team_id,
            project_id=project_id,
            priority=action.priority,
        )
        if ref is not None:
            refs.append(ref)
    return refs


# ── Frontmatter read/write ─────────────────────────────────────────────────

def read_frontmatter(page_path: Path) -> dict:
    """Parse YAML-frontmatter from a markdown file. Values are kept as raw strings —
    caller is responsible for any further parsing (e.g. list literals). Returns {}
    if there is no frontmatter block."""
    text = page_path.read_text()
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}
    fm: dict = {}
    for raw in text[4:end].splitlines():
        if ":" not in raw:
            continue
        k, _, v = raw.partition(":")
        fm[k.strip()] = v.strip()
    return fm


def _serialize_yaml_value(value) -> str:
    """Turn a Python value into a YAML inline scalar suitable for frontmatter."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        inner = ", ".join(_serialize_yaml_value(v) for v in value)
        return f"[{inner}]"
    return str(value)


def rewrite_frontmatter(page_path: Path, updates: dict) -> None:
    """Atomically rewrite the frontmatter of a markdown file. Existing keys are
    overwritten by `updates`; new keys are appended. The body is preserved
    verbatim. Raises ValueError if the file has no frontmatter block."""
    text = page_path.read_text()
    if not text.startswith("---\n"):
        raise ValueError(f"no frontmatter in {page_path}")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise ValueError(f"unterminated frontmatter in {page_path}")

    existing_lines = text[4:end].splitlines()
    existing_keys: list[str] = []
    new_lines: list[str] = []
    for raw in existing_lines:
        if ":" not in raw:
            new_lines.append(raw)
            continue
        k = raw.split(":", 1)[0].strip()
        existing_keys.append(k)
        if k in updates:
            new_lines.append(f"{k}: {_serialize_yaml_value(updates[k])}")
        else:
            new_lines.append(raw)

    for k, v in updates.items():
        if k not in existing_keys:
            new_lines.append(f"{k}: {_serialize_yaml_value(v)}")

    body = text[end:]
    rebuilt = "---\n" + "\n".join(new_lines) + body

    tmp = page_path.with_suffix(page_path.suffix + ".tmp")
    tmp.write_text(rebuilt)
    os.replace(tmp, page_path)


# ── Digest composer ────────────────────────────────────────────────────────

def build_digest_text(batch_results: list[BatchResult]) -> Optional[str]:
    """Compose ONE Telegram message body covering an entire cron batch. Returns
    None when no tickets were created across the whole batch (silent run)."""
    if not batch_results:
        return None
    total_tickets = sum(len(br.tickets) for br in batch_results)
    if total_tickets == 0:
        return None

    n = len(batch_results)
    header = f"📼 Processed {n} Plaud recording{'s' if n != 1 else ''}:"
    lines = [header]
    for br in batch_results:
        marker = ""
        if br.status == "partial":
            marker = " ⚠️ partial"
        elif br.status == "parse_failed":
            marker = " ⚠️ parse_failed"
        if not br.tickets:
            lines.append(f"• {br.title} ({br.portfolio}) — no actions extracted")
            continue
        ids = " / ".join(t.identifier for t in br.tickets)
        lines.append(
            f"• {br.title} → {br.portfolio} ({len(br.tickets)} tickets) "
            f"[{ids}]{marker}"
        )
    wiki_paths = " · ".join(br.wiki_path for br in batch_results)
    lines.append(f"📄 wikis: {wiki_paths}")
    return "\n".join(lines)
