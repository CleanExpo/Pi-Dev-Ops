"""swarm/kanban_adapter.py — RA-1865 (Wave 4 B2): Hermes Kanban subprocess adapter.

Resolves blueprint Open Question #5 — agent-to-agent communication ceremony.
Telegram chains for 17 agents are noisy; pure flow_engine state is invisible
to the founder. Kanban is the middle path: visible (queryable) but not noisy.

Architecture:
  Pi-CEO swarm code        ── subprocess ──▶  hermes kanban {create|comment|...}
  ├─ kanban_adapter.py        (this module)        ▲
  ├─ debate_runner.py uses    create_card()         │
  ├─ flow_engine.py uses      add_comment()         │
  └─ six_pager.py reads via   list_open()           │
                                                    │
                                           ~/.hermes/kanban.db (Hermes-managed SQLite)

The adapter does NOT spawn the gateway / daemon / workers. It only writes
cards into the SQLite store; Hermes's own dispatcher decides whether to
claim and run them. For Pi-CEO use, cards are typically just visible state
markers — nobody is meant to "run" a Pi-CEO debate card; it's a notice to
the founder that the debate happened.

Failure mode: if the `hermes` binary isn't on PATH or the call fails,
every adapter function returns ``None`` (or empty list) and logs a
warning. Pi-CEO never crashes a cycle on a Kanban call.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any

log = logging.getLogger("swarm.kanban_adapter")

HERMES_BIN_ENV = "HERMES_BIN"
DEFAULT_HERMES_BIN = "hermes"
HERMES_TIMEOUT_S = 8.0


# ── Data shapes ──────────────────────────────────────────────────────────────


@dataclass
class KanbanCard:
    """Subset of a Hermes kanban task that Pi-CEO cares about."""
    task_id: str
    title: str
    status: str
    assignee: str | None
    tenant: str | None
    parent_ids: list[str]
    body: str | None
    raw: dict[str, Any]


# ── Helpers ──────────────────────────────────────────────────────────────────


def _hermes_bin() -> str | None:
    """Locate the hermes binary; return None if not on PATH."""
    bin_ = os.environ.get(HERMES_BIN_ENV) or DEFAULT_HERMES_BIN
    found = shutil.which(bin_)
    if not found:
        log.debug("kanban_adapter: hermes binary %r not on PATH", bin_)
        return None
    return found


def _run(args: list[str], *, timeout_s: float = HERMES_TIMEOUT_S
         ) -> tuple[int, str, str]:
    """Run `hermes <args>`; return (rc, stdout, stderr). Never raises."""
    binary = _hermes_bin()
    if binary is None:
        return 127, "", "hermes binary not on PATH"
    try:
        result = subprocess.run(  # noqa: S603 — controlled args
            [binary, *args],
            capture_output=True, text=True, timeout=timeout_s,
            check=False,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        log.warning("kanban_adapter: timeout running hermes %s", args)
        return 124, "", "timeout"
    except Exception as exc:  # noqa: BLE001
        log.warning("kanban_adapter: subprocess raised (%s) for %s", exc, args)
        return 1, "", str(exc)


def _parse_create_id(stdout: str) -> str | None:
    """`hermes kanban create --json` returns {"task_id": "k-abc123", ...}."""
    stdout = (stdout or "").strip()
    if not stdout:
        return None
    try:
        obj = json.loads(stdout)
    except Exception:
        # Fall back to non-JSON output if Hermes ever changes its mind
        for tok in stdout.split():
            if tok.startswith("k-"):
                return tok
        return None
    return obj.get("task_id") or obj.get("id")


# ── Public API ──────────────────────────────────────────────────────────────


def create_card(
    *,
    title: str,
    body: str | None = None,
    assignee: str | None = None,
    tenant: str | None = "pi-ceo",
    priority: int | None = None,
    idempotency_key: str | None = None,
    parent_ids: list[str] | None = None,
    skills: list[str] | None = None,
    triage: bool = False,
) -> str | None:
    """Create a kanban card. Returns task_id or None on failure.

    Default tenant is ``pi-ceo`` so Pi-CEO cards don't pollute other Hermes
    profiles' boards.
    """
    args: list[str] = ["kanban", "create", "--json"]
    if body:
        args.extend(["--body", body])
    if assignee:
        args.extend(["--assignee", assignee])
    if tenant:
        args.extend(["--tenant", tenant])
    if priority is not None:
        args.extend(["--priority", str(priority)])
    if idempotency_key:
        args.extend(["--idempotency-key", idempotency_key])
    for parent in parent_ids or []:
        args.extend(["--parent", parent])
    for skill in skills or []:
        args.extend(["--skill", skill])
    if triage:
        args.append("--triage")
    args.append(title)

    rc, out, err = _run(args)
    if rc != 0:
        log.warning("kanban_adapter: create rc=%d err=%s", rc, err.strip())
        return None
    task_id = _parse_create_id(out)
    if task_id is None:
        log.warning("kanban_adapter: create succeeded but no task_id parsed: %r",
                    out[:200])
    return task_id


def add_comment(*, task_id: str, text: str,
                author: str | None = None) -> bool:
    """Append a comment to a kanban card. Returns True on success."""
    args = ["kanban", "comment"]
    if author:
        args.extend(["--author", author])
    args.append(task_id)
    args.append(text)
    rc, _out, err = _run(args)
    if rc != 0:
        log.warning("kanban_adapter: comment rc=%d err=%s", rc, err.strip())
        return False
    return True


def complete_card(*, task_id: str, summary: str | None = None,
                   result: str | None = None) -> bool:
    """Mark a kanban card complete. Returns True on success."""
    args = ["kanban", "complete"]
    if summary:
        args.extend(["--summary", summary])
    if result:
        args.extend(["--result", result])
    args.append(task_id)
    rc, _out, err = _run(args)
    if rc != 0:
        log.warning("kanban_adapter: complete rc=%d err=%s", rc, err.strip())
        return False
    return True


def block_card(*, task_id: str) -> bool:
    rc, _out, err = _run(["kanban", "block", task_id])
    if rc != 0:
        log.warning("kanban_adapter: block rc=%d err=%s", rc, err.strip())
        return False
    return True


def list_open(*, tenant: str | None = "pi-ceo",
              status: str | None = None) -> list[KanbanCard]:
    """List open Pi-CEO kanban cards. Returns [] on failure."""
    args = ["kanban", "list", "--json"]
    if tenant:
        args.extend(["--tenant", tenant])
    if status:
        args.extend(["--status", status])
    rc, out, err = _run(args)
    if rc != 0:
        log.warning("kanban_adapter: list rc=%d err=%s", rc, err.strip())
        return []
    try:
        rows = json.loads(out)
    except Exception as exc:  # noqa: BLE001
        log.warning("kanban_adapter: list output not JSON: %s", exc)
        return []
    if not isinstance(rows, list):
        return []
    out_cards: list[KanbanCard] = []
    for row in rows:
        try:
            out_cards.append(KanbanCard(
                task_id=row.get("task_id") or row.get("id") or "",
                title=row.get("title") or "",
                status=row.get("status") or "",
                assignee=row.get("assignee"),
                tenant=row.get("tenant"),
                parent_ids=list(row.get("parent_ids") or []),
                body=row.get("body"),
                raw=row,
            ))
        except Exception:
            continue
    return out_cards


def emit_debate_card(
    *,
    role: str,
    business_id: str,
    topic: str,
    drafter_artifact: str,
    redteam_artifact: str,
    debate_id: str,
) -> str | None:
    """One-shot helper for the debate runner: create a kanban card with the
    drafter + red-team artifacts pre-baked into the body. Returns task_id.

    Used by run_debate to surface debates to the founder without flooding
    Telegram. Idempotency key is the debate_id so re-runs don't dup.
    """
    body = (
        f"Topic: {topic}\n\n"
        f"### Drafter ({role}) artifact\n\n"
        f"{drafter_artifact}\n\n"
        f"### Red-team critique\n\n"
        f"{redteam_artifact}\n"
    )
    title = f"[{role}@{business_id}] debate — {topic[:80]}"
    return create_card(
        title=title, body=body,
        tenant="pi-ceo", idempotency_key=debate_id,
        skills=["debate-summary"],
    )


__all__ = [
    "KanbanCard",
    "create_card", "add_comment", "complete_card", "block_card",
    "list_open", "emit_debate_card",
]
