"""
swarm/margot_tools.py — RA-1839: Margot bridge as flow tools.

Wraps Margot's MCP tools (deep_research, deep_research_max,
check_research, corpus_status, image_generate) so flow_engine can
call them via mcp.margot.*.

Two transports supported:
  1. STDIO MCP subprocess (preferred; talks to Margot at ~/.margot/).
     Requires the `mcp` Python package OR a tiny vendored JSON-RPC client.
  2. Direct Gemini API (fallback). Replicates Margot's deep_research()
     behaviour but without the corpus grounding. Uses GEMINI_API_KEY
     env var — never reads ~/.margot/gemini-api-key.txt directly.

This module ships the contract + the auto-detection of which transport
is available. It does NOT include the Gemini SDK — that lands when
GEMINI_API_KEY is configured server-side.

Tools registered with flow_engine:
  * mcp.margot.deep_research(topic, use_corpus?)              [sync]
  * mcp.margot.deep_research_max(topic, use_corpus?)          [async, returns interaction_id]
  * mcp.margot.check_research(interaction_id)                 [sync poll]
  * mcp.margot.corpus_status()                                [sync]
  * mcp.margot.image_generate(prompt, aspect_ratio?, image_size?)  [sync]

In-flight async pattern (matches margot-bridge SKILL.md):
  * .harness/swarm/margot_inflight.jsonl tracks dispatched
    interaction_ids. CoS / Dispatcher polls on next cycle.
  * Bridge persists with timestamp + originating_session_id.
  * When status flips to complete, fan out to Scribe.

Safety bindings — same as margot-bridge SKILL.md:
  * Never print or log the API key.
  * Kill-switch behaviour: in-flight interaction_ids persist; not cancelled.
  * Corpus exposure: caller's responsibility to redact via pii-redactor
    before any send.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

log = logging.getLogger("swarm.margot_tools")

MARGOT_SERVER_PATH = Path(os.environ.get(
    "MARGOT_SERVER_PATH",
    str(Path.home() / ".margot" / "margot-deep-research" / "server.py"),
))
MARGOT_INFLIGHT_LOG = Path(__file__).resolve().parents[1] / ".harness" / "swarm" / "margot_inflight.jsonl"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _kill_switch_active() -> bool:
    return os.environ.get("TAO_SWARM_ENABLED", "0") != "1"


def _transport_available() -> str | None:
    """Detect which transport is reachable. Returns 'stdio' / 'gemini' / None."""
    if MARGOT_SERVER_PATH.exists() and shutil.which("python3"):
        # Try the stdio-MCP path. We don't actually connect here — that's
        # done lazily on the first call to avoid spawning a subprocess
        # at module import time.
        return "stdio"
    if os.environ.get("GEMINI_API_KEY"):
        return "gemini"
    return None


def _record_inflight(record: dict[str, Any]) -> None:
    MARGOT_INFLIGHT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with MARGOT_INFLIGHT_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


# ── Public flow tools ────────────────────────────────────────────────────────


def deep_research(topic: str, use_corpus: bool = False, **_: Any) -> dict[str, Any]:
    """Sync research call. Returns {summary, status} or {error}."""
    transport = _transport_available()
    if transport is None:
        return {
            "error": "margot_unreachable",
            "fix": "Either ensure ~/.margot/margot-deep-research/server.py is present "
                   "OR set GEMINI_API_KEY in the Pi-CEO server env. See "
                   "Pi-Dev-Ops/skills/margot-bridge/SKILL.md → Prerequisites.",
        }

    if transport == "stdio":
        # Lazy import to avoid hard-fail at import time on systems without `mcp`
        return _call_stdio_mcp("deep_research",
                              {"topic": topic, "use_corpus": use_corpus})

    # Gemini direct path — placeholder until Gemini SDK is wired
    return {
        "error": "gemini_direct_not_wired",
        "topic": topic,
        "next": "Install google-generativeai + restart Pi-CEO server "
                "to enable the Gemini fallback.",
    }


def deep_research_max(topic: str, use_corpus: bool = False,
                      originating_session_id: str | None = None,
                      **_: Any) -> dict[str, Any]:
    """Async deep research. Returns {interaction_id, status='dispatched'}.

    Caller does NOT block. CoS / Dispatcher polls margot_inflight.jsonl
    on the next cycle and calls check_research() when ready.
    """
    transport = _transport_available()
    if transport is None:
        return {"error": "margot_unreachable",
                "fix": "see margot-bridge SKILL.md → Prerequisites"}

    if transport == "stdio":
        result = _call_stdio_mcp(
            "deep_research_max",
            {"topic": topic, "use_corpus": use_corpus},
        )
        interaction_id = result.get("interaction_id") or uuid.uuid4().hex[:16]
        _record_inflight({
            "ts": _now_iso(),
            "interaction_id": interaction_id,
            "topic": topic,
            "originating_session_id": originating_session_id,
            "status": "dispatched",
        })
        return {
            "interaction_id": interaction_id,
            "status": "dispatched",
            "dispatched_at": _now_iso(),
            "originating_session_id": originating_session_id,
        }

    return {"error": "gemini_direct_not_wired"}


def check_research(interaction_id: str, **_: Any) -> dict[str, Any]:
    """Poll a previously-dispatched interaction. Returns status + body when done."""
    transport = _transport_available()
    if transport is None:
        return {"error": "margot_unreachable"}
    if transport == "stdio":
        return _call_stdio_mcp("check_research", {"interaction_id": interaction_id})
    return {"error": "gemini_direct_not_wired"}


def corpus_status(**_: Any) -> dict[str, Any]:
    """Diagnostic — returns Margot's configured models + corpus path."""
    transport = _transport_available()
    if transport is None:
        return {
            "error": "margot_unreachable",
            "transport_attempted": None,
            "fix": "see margot-bridge SKILL.md → Prerequisites",
        }
    if transport == "stdio":
        return _call_stdio_mcp("corpus_status", {})
    return {"transport": "gemini",
            "text_model": os.environ.get("GEMINI_TEXT_MODEL", "gemini-3.1-pro-preview-customtools")}


def image_generate(prompt: str, aspect_ratio: str = "1:1",
                  image_size: str = "1024x1024",
                  reference_image_path: str | None = None,
                  **_: Any) -> dict[str, Any]:
    """Synchronous image generation."""
    transport = _transport_available()
    if transport is None:
        return {"error": "margot_unreachable"}
    if transport == "stdio":
        args = {"prompt": prompt, "aspect_ratio": aspect_ratio,
                "image_size": image_size}
        if reference_image_path:
            args["reference_image_path"] = reference_image_path
        return _call_stdio_mcp("image_generate", args)
    return {"error": "gemini_direct_not_wired"}


# ── RA-2002: Margot → Linear ideas bridge ────────────────────────────────────
#
# Captures a Telegram-side idea as a Linear Backlog ticket so ideation isn't
# lost when the chat scrolls. Defaults to project="Pi - Dev -Ops" (RestoreAssist
# team) and label="margot-idea" so the curator + backlog poller can route them.
#
# Auth: LINEAR_API_KEY env var. Fail-soft if missing — returns
# {"error": "no_api_key"} so handle_turn can include a one-line note in the
# Telegram reply rather than crashing.


_LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"
# Label name used for every Margot-captured idea. Created on first call if
# missing (idempotent — Linear's labelCreate is a no-op when the name + team
# tuple already exists, so we resolve-or-create).
MARGOT_IDEA_LABEL = "margot-idea"
# Default project when the LLM doesn't specify one — Pi-Dev-Ops backlog
# (RestoreAssist team) is where ideas land for triage by the curator.
MARGOT_DEFAULT_PROJECT = "Pi - Dev -Ops"
MARGOT_DEFAULT_TEAM = "RestoreAssist"


def _linear_gql(query: str, variables: dict[str, Any] | None = None,
                *, timeout_s: int = 15) -> dict[str, Any]:
    """Issue a Linear GraphQL query with auth. Returns parsed JSON or {'error': ...}."""
    import urllib.request as _ureq  # noqa: PLC0415

    key = os.environ.get("LINEAR_API_KEY", "").strip()
    if not key:
        return {"error": "no_api_key"}
    payload = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
    req = _ureq.Request(
        _LINEAR_GRAPHQL_URL, data=payload, method="POST",
        headers={"Content-Type": "application/json", "Authorization": key},
    )
    try:
        with _ureq.urlopen(req, timeout=timeout_s) as resp:
            return json.loads(resp.read())
    except Exception as exc:  # noqa: BLE001
        log.warning("Linear GraphQL error: %s", exc)
        return {"error": "request_failed", "exception": repr(exc)}


def _resolve_team_id(team_name: str) -> str | None:
    """Look up a team UUID by name or key (e.g. 'RestoreAssist' or 'RA')."""
    res = _linear_gql("query { teams(first: 100) { nodes { id key name } } }")
    if "error" in res:
        return None
    for t in res.get("data", {}).get("teams", {}).get("nodes", []):
        if (t.get("name", "").lower() == team_name.lower() or
                t.get("key", "").lower() == team_name.lower()):
            return t["id"]
    return None


def _resolve_project_id(team_id: str, project_name: str) -> str | None:
    """Look up a project UUID by name within a team."""
    res = _linear_gql(
        "query($teamId: String!) { team(id: $teamId) { "
        "projects(first: 100) { nodes { id name } } } }",
        {"teamId": team_id},
    )
    if "error" in res:
        return None
    for p in res.get("data", {}).get("team", {}).get("projects", {}).get("nodes", []):
        if p.get("name", "").lower() == project_name.lower():
            return p["id"]
    return None


def _resolve_or_create_label(team_id: str, label_name: str) -> str | None:
    """Find a label by name within a team; create it if missing. Returns UUID."""
    res = _linear_gql(
        "query($teamId: String!) { team(id: $teamId) { "
        "labels(first: 100) { nodes { id name } } } }",
        {"teamId": team_id},
    )
    if "error" not in res:
        for lbl in res.get("data", {}).get("team", {}).get("labels", {}).get("nodes", []):
            if lbl.get("name", "").lower() == label_name.lower():
                return lbl["id"]
    # Not found — create. Color #A78BFA (lavender) chosen in RA-2002 for visual
    # distinction from existing labels.
    create = _linear_gql(
        """
        mutation($input: IssueLabelCreateInput!) {
          issueLabelCreate(input: $input) {
            success issueLabel { id name }
          }
        }
        """,
        {"input": {"name": label_name, "teamId": team_id, "color": "#A78BFA"}},
    )
    if "error" in create:
        return None
    return ((create.get("data") or {}).get("issueLabelCreate") or {}) \
            .get("issueLabel", {}).get("id")


def propose_idea(title: str,
                 description: str = "",
                 *,
                 project: str = MARGOT_DEFAULT_PROJECT,
                 team: str = MARGOT_DEFAULT_TEAM,
                 priority: int = 3,
                 dry_run: bool = False,
                 **_: Any) -> dict[str, Any]:
    """RA-2002 — capture a Telegram-side idea as a Linear Backlog ticket.

    Args:
        title: One-line ticket title. Required, max ~200 chars (Linear caps).
        description: Markdown body. Use to capture the operator's reasoning,
            constraints, and any acceptance hints from the conversation.
        project: Linear project name. Defaults to "Pi - Dev -Ops" so the
            backlog poller (RA-1973) and curator can route the ticket.
        team: Linear team name or key. Defaults to "RestoreAssist" (RA-).
        priority: 0=None, 1=Urgent, 2=High, 3=Medium (default), 4=Low.
        dry_run: When True, returns a synthetic response without touching
            the API. Used by tests + sentinel-verification flows.

    Returns:
        {"status": "created", "id": str, "identifier": str, "url": str,
         "label": str} on success.
        {"error": ...} on failure (auth, team/project/label resolution,
         API error). Never raises — Margot's reply path catches errors and
         informs the user inline.
    """
    if _kill_switch_active() and not dry_run:
        return {"status": "skipped_kill_switch"}

    if dry_run:
        return {
            "status": "dry_run", "title": title, "description": description,
            "project": project, "team": team, "priority": priority,
            "label": MARGOT_IDEA_LABEL,
        }

    if not (title or "").strip():
        return {"error": "title_required"}

    team_id = _resolve_team_id(team)
    if not team_id:
        return {"error": "team_not_found", "team": team}

    project_id = _resolve_project_id(team_id, project) if project else None
    if project and not project_id:
        # Don't fail hard — file the ticket in the team backlog without project.
        # The curator can re-project later.
        log.warning(
            "propose_idea: project %r not found in team %r — filing without project",
            project, team,
        )

    label_id = _resolve_or_create_label(team_id, MARGOT_IDEA_LABEL)

    input_obj: dict[str, Any] = {
        "teamId": team_id, "title": title.strip(), "priority": priority,
    }
    if description:
        # Append an attribution footer so the curator knows the source.
        body = description.strip() + (
            "\n\n---\n_Captured by Margot via RA-2002 ideas bridge._"
        )
        input_obj["description"] = body
    if project_id:
        input_obj["projectId"] = project_id
    if label_id:
        input_obj["labelIds"] = [label_id]

    res = _linear_gql(
        """
        mutation($input: IssueCreateInput!) {
          issueCreate(input: $input) {
            success
            issue { id identifier title url priority }
          }
        }
        """,
        {"input": input_obj},
    )
    if "error" in res:
        return res
    data = (res.get("data") or {}).get("issueCreate", {})
    if not data.get("success"):
        return {"error": "create_failed", "raw": res}
    iss = data["issue"]
    return {
        "status": "created",
        "id": iss["id"], "identifier": iss["identifier"],
        "title": iss["title"], "url": iss["url"], "priority": iss["priority"],
        "label": MARGOT_IDEA_LABEL if label_id else None,
    }


# ── Stdio MCP transport (lazy) ───────────────────────────────────────────────
# Vendored minimal JSON-RPC over stdio. Avoids hard dependency on the `mcp`
# Python package — Margot's server speaks the standard MCP JSON-RPC protocol.
# This is intentionally minimal; production wiring should swap to the official
# `mcp` client when it's pinned in requirements.txt.


_STDIO_PROCESS: subprocess.Popen | None = None
_STDIO_NEXT_ID = 0


def _start_stdio() -> subprocess.Popen | None:
    global _STDIO_PROCESS
    if _STDIO_PROCESS and _STDIO_PROCESS.poll() is None:
        return _STDIO_PROCESS
    if not MARGOT_SERVER_PATH.exists():
        return None
    try:
        _STDIO_PROCESS = subprocess.Popen(
            ["python3", str(MARGOT_SERVER_PATH)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        # Initialize handshake (best-effort; ignore response shape)
        _send_jsonrpc("initialize", {"protocolVersion": "2024-11-05",
                                     "capabilities": {},
                                     "clientInfo": {"name": "pi-ceo-flow_engine",
                                                    "version": "0.1.0"}})
        _send_jsonrpc("notifications/initialized", {}, notification=True)
    except Exception as exc:
        log.warning("stdio Margot start failed: %s", exc)
        _STDIO_PROCESS = None
    return _STDIO_PROCESS


def _send_jsonrpc(method: str, params: dict[str, Any],
                 notification: bool = False, timeout_s: int = 30) -> dict[str, Any]:
    global _STDIO_NEXT_ID
    if _STDIO_PROCESS is None or _STDIO_PROCESS.poll() is not None:
        return {"error": "stdio_not_started"}

    msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params}
    if not notification:
        _STDIO_NEXT_ID += 1
        msg["id"] = _STDIO_NEXT_ID

    try:
        _STDIO_PROCESS.stdin.write(json.dumps(msg) + "\n")
        _STDIO_PROCESS.stdin.flush()
    except Exception as exc:
        return {"error": "stdio_write_failed", "exception": repr(exc)}

    if notification:
        return {"ok": True}

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        line = _STDIO_PROCESS.stdout.readline()
        if not line:
            time.sleep(0.05)
            continue
        try:
            resp = json.loads(line)
        except Exception:
            continue
        if resp.get("id") == msg.get("id"):
            return resp.get("result") or {"error": resp.get("error")}
    return {"error": "stdio_timeout"}


def _call_stdio_mcp(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
    proc = _start_stdio()
    if proc is None:
        return {"error": "stdio_unavailable"}
    return _send_jsonrpc("tools/call", {"name": tool_name, "arguments": args})


def register_with_flow_engine() -> int:
    """Register all Margot tools with flow_engine.

    Returns the count of registered tools (5 MCP tools + 1 RA-2002 ideas
    bridge = 6).
    """
    from . import flow_engine

    flow_engine.register_tool("mcp.margot.deep_research",
                              lambda **kw: deep_research(**kw))
    flow_engine.register_tool("mcp.margot.deep_research_max",
                              lambda **kw: deep_research_max(**kw))
    flow_engine.register_tool("mcp.margot.check_research",
                              lambda **kw: check_research(**kw))
    flow_engine.register_tool("mcp.margot.corpus_status",
                              lambda **kw: corpus_status(**kw))
    flow_engine.register_tool("mcp.margot.image_generate",
                              lambda **kw: image_generate(**kw))
    flow_engine.register_tool("mcp.margot.propose_idea",
                              lambda **kw: propose_idea(**kw))
    return 6


# Auto-register on import (idempotent)
try:
    register_with_flow_engine()
except Exception as exc:
    log.debug("margot_tools auto-register skipped: %s", exc)


__all__ = [
    "deep_research", "deep_research_max", "check_research",
    "corpus_status", "image_generate", "propose_idea",
    "MARGOT_IDEA_LABEL", "MARGOT_DEFAULT_PROJECT", "MARGOT_DEFAULT_TEAM",
    "register_with_flow_engine",
]
