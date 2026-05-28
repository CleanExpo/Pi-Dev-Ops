"""Margot router — state machine for inbound partner messages.

Pure logic, no DB / network. Sits between `swarm/inbox/intake_router.py`
(which receives the Telegram update) and `swarm/intake/spm.py`
(which generates the SPM brief once a project is `in_loop`).

State machine (per SPEC.md §1):

    awaiting_project_name  → "What's the project name?"
    awaiting_idea          → "Got it. Tell me about <name>."
    classified             → opens intake_project + advances to in_loop
    in_loop                → forwards to SPM

This module returns `RouterDecision` objects describing what the caller
(PR5 wiring layer) should do — persist, reply, hand off to SPM,
broadcast to other partners, etc. No I/O happens here.

G6 non-happy paths covered:

    * First message contains BOTH name AND idea → skip to `classified`
    * Vague project name ("the thing", < 3 chars, ...) → reject with prompt
    * Duplicate project (slug or fuzzy-name match) → surface match
    * Abandoned thread (>30 days no inbound, status='open') → flagged
      for sweeper to move to `paused_human_review`
    * `/rename <new>` or natural-language rename signal → update name
    * `/start` after thread is mid-flow → confirm continuation
    * Cross-partner takeover (Toby posts to Duncan's thread) → allowed
      per G2 workspace access, message tagged with submitted_by_partner_id

All inbound `submitted_by_partner_id` values MUST already have passed
through `spm.trusted_partner_id_for_inbound` before reaching this
module (SPEC §G3 — partner_id comes from a trusted channel, never
from message body).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Literal, Protocol


# ============================================================
# Data shapes
# ============================================================

MargotState = Literal[
    "awaiting_project_name",
    "awaiting_idea",
    "classified",
    "in_loop",
    "paused_human_review",
]

RouterAction = Literal[
    "reply",                # send a Margot reply, no state change
    "advance_to_idea",      # captured project name, ask for idea
    "create_project",       # have both name + idea, create intake_project
    "forward_to_spm",       # in_loop, hand off to SPM
    "rename_project",       # update intake_projects.name + slug
    "confirm_resume",       # /start mid-flow — ask if continue or fresh
    "pause_for_review",     # abandoned thread → human checkpoint
    "reject",               # vague name, etc. — partner-facing reason
    "surface_duplicate",    # propose continuing existing project
    "noop",                 # nothing to do (e.g. status==shipped)
]


@dataclass(frozen=True)
class InboundMessage:
    """One Telegram message that has already cleared anti-spoofing.

    `submitted_by_partner_id` is the trust-rooted partner id from
    `spm.trusted_partner_id_for_inbound` — never read from the body.
    """
    chat_id: str
    body: str
    submitted_by_partner_id: str
    telegram_user_id: int | None = None
    created_at: str = ""  # ISO 8601


@dataclass(frozen=True)
class ThreadState:
    """Minimal subset of intake_threads + intake_projects the router needs."""
    thread_id: str | None  # None for the very first message
    project_id: str | None
    margot_state: MargotState
    candidate_name: str | None = None  # captured but not yet committed
    candidate_slug: str | None = None
    project_owner_partner_id: str | None = None
    project_name: str | None = None
    project_status: str = "open"  # open | ready_for_production | shipped | paused_human_review
    last_inbound_at: str | None = None  # ISO 8601


@dataclass(frozen=True)
class ProjectSummary:
    """Lightweight existing-project record for duplicate detection."""
    project_id: str
    name: str
    slug: str
    owner_partner_id: str
    status: str = "open"


@dataclass(frozen=True)
class ClassifiedMessage:
    """LLM extraction result for the both-in-one-message G6 path."""
    has_project_name: bool
    project_name: str | None
    has_idea: bool
    idea: str | None
    is_rename_signal: bool = False
    proposed_new_name: str | None = None


@dataclass(frozen=True)
class RouterDecision:
    """What the caller should do next.

    `reply_text` is the founder-voice reply to send via the originating
    partner's bot. Empty string means "no reply" (still possible to
    perform `action`, e.g. forward_to_spm with silent acknowledgement).
    """
    action: RouterAction
    next_state: MargotState
    reply_text: str
    captured_project_name: str | None = None
    captured_project_slug: str | None = None
    duplicate_match: ProjectSummary | None = None
    rename_to: str | None = None
    metadata: dict = field(default_factory=dict)


# ============================================================
# Protocols
# ============================================================

class LLMClient(Protocol):
    """Identical contract to spm.LLMClient — kept duplicated to avoid
    a hard import cycle in PR5 wiring."""
    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 800,
        temperature: float = 0.2,
    ) -> str: ...


class ProjectLookup(Protocol):
    """Caller-supplied lookup used for duplicate detection (G6).

    Implementations live in PR5 (DB-backed) and tests (in-memory).
    """
    def list_open_projects(self, *, workspace_slug: str) -> Iterable[ProjectSummary]: ...


# ============================================================
# Constants
# ============================================================

ABANDONED_THREAD_DAYS = 30
MIN_PROJECT_NAME_CHARS = 3
MAX_PROJECT_NAME_CHARS = 80

VAGUE_NAME_TOKENS = frozenset({
    "the thing", "thing", "stuff", "project", "the project",
    "something", "this", "that", "it", "idea", "the idea",
})

CLASSIFY_SYSTEM_PROMPT = """You are an extraction step for a project intake bot.

The user just sent a message to start or continue a project. Decide:
  1. Does the message contain a usable project NAME (short label, e.g. "Synthex Brand Refresh")?
  2. Does it contain a project IDEA (description of what they want to build)?
  3. Is it a rename signal (e.g. "rename to ...", "actually call it ...")?

Respond with STRICT JSON only:
{
  "has_project_name": bool,
  "project_name": string or null,
  "has_idea": bool,
  "idea": string or null,
  "is_rename_signal": bool,
  "proposed_new_name": string or null
}

Rules:
  - A project name MUST be a short label (1-6 words), not a sentence.
  - "build a thing", "the project", "stuff" are NOT usable names — set has_project_name=false.
  - If the user wrote both a name and an idea in one message, populate both.
  - If unsure whether something is a name, prefer has_project_name=false.
  - For is_rename_signal, look for explicit signals: "rename", "call it", "let's call this", "new name".
"""


# ============================================================
# Helpers
# ============================================================

def _slugify(name: str) -> str:
    """ASCII slug — lowercase, alnum and hyphen only."""
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s


def is_vague_name(name: str) -> tuple[bool, str | None]:
    """G6 — return (True, reason) if `name` is too vague to use.

    Reasons are partner-facing prompts.
    """
    if not name:
        return True, "Can you give it a working name? Even a short one works."
    cleaned = name.strip().lower()
    if len(cleaned) < MIN_PROJECT_NAME_CHARS:
        return True, "That name's a bit short — can you give me 3+ characters to work with?"
    if len(cleaned) > MAX_PROJECT_NAME_CHARS:
        return True, "That name's too long for a label — try something under 80 characters."
    if cleaned in VAGUE_NAME_TOKENS:
        return True, "Can you give it a working name? 'The thing' / 'project' is too generic."
    # Multi-word vague phrases — strip punctuation and re-check
    tokens = re.sub(r"[^a-z0-9\s]", "", cleaned).split()
    if tokens and all(t in VAGUE_NAME_TOKENS for t in tokens):
        return True, "Can you give it a working name? That phrase is too generic."
    return False, None


def find_duplicate_project(
    name: str,
    existing: Iterable[ProjectSummary],
) -> ProjectSummary | None:
    """G6 — exact-slug or fuzzy-name match against open projects.

    Fuzzy = case/whitespace/punctuation-insensitive substring or
    Jaccard-token overlap >= 0.6.
    """
    target_slug = _slugify(name)
    target_tokens = set(re.sub(r"[^a-z0-9\s]", "", name.lower()).split())
    if not target_slug or not target_tokens:
        return None

    best: tuple[float, ProjectSummary] | None = None

    for proj in existing:
        if proj.status not in ("open", "ready_for_production"):
            continue
        if proj.slug == target_slug:
            return proj  # exact match — short-circuit
        other_tokens = set(re.sub(r"[^a-z0-9\s]", "", proj.name.lower()).split())
        if not other_tokens:
            continue
        # substring containment
        if target_slug in proj.slug or proj.slug in target_slug:
            score = 0.7
        else:
            inter = len(target_tokens & other_tokens)
            union = len(target_tokens | other_tokens)
            score = inter / union if union else 0.0
        if score >= 0.6 and (best is None or score > best[0]):
            best = (score, proj)

    return best[1] if best else None


def is_thread_abandoned(
    thread: ThreadState,
    *,
    now: datetime,
    threshold_days: int = ABANDONED_THREAD_DAYS,
) -> bool:
    """G6 — open thread with no inbound for > threshold_days."""
    if thread.project_status != "open":
        return False
    if not thread.last_inbound_at:
        return False
    try:
        last = datetime.fromisoformat(thread.last_inbound_at.replace("Z", "+00:00"))
    except ValueError:
        return False
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    return (now - last) > timedelta(days=threshold_days)


# ============================================================
# Slash-command parsing
# ============================================================

_SLASH_RE = re.compile(r"^/(?P<cmd>[a-z_]+)(?:\s+(?P<arg>.*))?$", re.IGNORECASE)


def parse_slash_command(body: str) -> tuple[str | None, str | None]:
    """Return `(command, argument)` or `(None, None)`."""
    if not body:
        return None, None
    stripped = body.strip()
    if not stripped.startswith("/"):
        return None, None
    m = _SLASH_RE.match(stripped)
    if not m:
        return None, None
    cmd = m.group("cmd").lower()
    arg = (m.group("arg") or "").strip()
    return cmd, arg or None


# ============================================================
# LLM extraction (both-name-and-idea, rename signal)
# ============================================================

def _classify_message(body: str, *, llm: LLMClient) -> ClassifiedMessage:
    """Ask the LLM whether the message contains a project name and/or idea."""
    raw = llm.complete(
        system=CLASSIFY_SYSTEM_PROMPT,
        user=body,
        max_tokens=400,
        temperature=0.0,
    )
    # Tolerate chatter around the JSON object
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return ClassifiedMessage(
            has_project_name=False,
            project_name=None,
            has_idea=False,
            idea=None,
        )
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return ClassifiedMessage(
            has_project_name=False,
            project_name=None,
            has_idea=False,
            idea=None,
        )
    return ClassifiedMessage(
        has_project_name=bool(data.get("has_project_name")),
        project_name=data.get("project_name") or None,
        has_idea=bool(data.get("has_idea")),
        idea=data.get("idea") or None,
        is_rename_signal=bool(data.get("is_rename_signal")),
        proposed_new_name=data.get("proposed_new_name") or None,
    )


# ============================================================
# Main routing entry point
# ============================================================

def route_inbound(
    message: InboundMessage,
    thread: ThreadState,
    open_projects: Iterable[ProjectSummary],
    *,
    llm: LLMClient,
    now: datetime | None = None,
) -> RouterDecision:
    """Decide what to do with one inbound message.

    Returns a `RouterDecision`; caller (PR5) executes the side effects.
    """
    now = now or datetime.now(timezone.utc)
    body = (message.body or "").strip()
    cmd, arg = parse_slash_command(body)

    # ── Slash commands ──────────────────────────────────────────────

    if cmd == "start":
        return _handle_start(thread)
    if cmd == "rename":
        return _handle_rename(arg, thread, open_projects)
    if cmd == "resume":
        return _handle_resume(thread)
    if cmd == "cancel":
        return RouterDecision(
            action="reply",
            next_state=thread.margot_state,
            reply_text="A cancellation needs the project creator to sign off — I'll flag it for review.",
        )

    # ── Abandoned thread (G6) ───────────────────────────────────────

    if thread.margot_state in ("in_loop", "classified") and is_thread_abandoned(thread, now=now):
        return RouterDecision(
            action="pause_for_review",
            next_state="paused_human_review",
            reply_text=(
                "Welcome back — this project has been quiet for a while. "
                "I've parked it for a quick human review before we pick it up again. "
                "Use /resume once you're ready to keep going."
            ),
        )

    if thread.margot_state == "paused_human_review":
        return RouterDecision(
            action="reply",
            next_state="paused_human_review",
            reply_text=(
                "This project is paused for human review. Use /resume to restart it."
            ),
        )

    # ── State machine ───────────────────────────────────────────────

    if thread.margot_state == "awaiting_project_name":
        return _handle_awaiting_project_name(body, thread, open_projects, llm=llm)

    if thread.margot_state == "awaiting_idea":
        return _handle_awaiting_idea(body, thread)

    if thread.margot_state in ("classified", "in_loop"):
        return _handle_in_loop(body, thread, llm=llm)

    # Unknown state — fail safe
    return RouterDecision(
        action="noop",
        next_state=thread.margot_state,
        reply_text="",
        metadata={"warning": f"unknown margot_state: {thread.margot_state}"},
    )


# ============================================================
# Per-state handlers
# ============================================================

def _handle_start(thread: ThreadState) -> RouterDecision:
    """`/start` — fresh greeting OR confirm continuation if mid-flow."""
    if thread.thread_id is None or thread.margot_state == "awaiting_project_name":
        return RouterDecision(
            action="reply",
            next_state="awaiting_project_name",
            reply_text=(
                "Hi — I'm Margot. Let's get the basics down first: "
                "what's the project called? (A short working name is fine.)"
            ),
        )
    # Mid-flow → confirm continuation (G6)
    proj_label = thread.project_name or thread.candidate_name or "this project"
    return RouterDecision(
        action="confirm_resume",
        next_state=thread.margot_state,
        reply_text=(
            f"We're already mid-flow on '{proj_label}'. "
            f"Say 'continue' to keep going, or '/cancel' to park it and start fresh."
        ),
    )


def _handle_rename(
    arg: str | None,
    thread: ThreadState,
    open_projects: Iterable[ProjectSummary],
) -> RouterDecision:
    """`/rename <new>` — update project name + slug, preserve history."""
    if not arg:
        return RouterDecision(
            action="reply",
            next_state=thread.margot_state,
            reply_text="What should I call it instead? Use `/rename <new name>`.",
        )
    vague, reason = is_vague_name(arg)
    if vague:
        return RouterDecision(
            action="reject",
            next_state=thread.margot_state,
            reply_text=reason or "Can you give me a less generic name?",
        )
    dup = find_duplicate_project(arg, open_projects)
    if dup and dup.project_id != thread.project_id:
        return RouterDecision(
            action="surface_duplicate",
            next_state=thread.margot_state,
            duplicate_match=dup,
            reply_text=(
                f"Heads up — '{dup.name}' is already open. "
                f"Do you want to merge into that one, or pick a different name?"
            ),
        )
    new_slug = _slugify(arg)
    return RouterDecision(
        action="rename_project",
        next_state=thread.margot_state,
        rename_to=arg,
        captured_project_slug=new_slug,
        reply_text=f"Got it — calling this '{arg}' from here on.",
    )


def _handle_resume(thread: ThreadState) -> RouterDecision:
    if thread.margot_state != "paused_human_review":
        return RouterDecision(
            action="reply",
            next_state=thread.margot_state,
            reply_text="Nothing to resume — this thread isn't paused.",
        )
    return RouterDecision(
        action="reply",
        next_state="in_loop",
        reply_text="Welcome back — picking up where we left off.",
    )


def _handle_awaiting_project_name(
    body: str,
    thread: ThreadState,
    open_projects: Iterable[ProjectSummary],
    *,
    llm: LLMClient,
) -> RouterDecision:
    """First-message handling — may also catch both-name-and-idea (G6)."""
    if not body:
        return RouterDecision(
            action="reply",
            next_state="awaiting_project_name",
            reply_text="What's the project called? A short working name is fine.",
        )

    # Try LLM classification first (covers both-in-one-message path)
    classified = _classify_message(body, llm=llm)

    # Pick the name to validate — LLM extraction if it found one, else
    # the raw body (single-line names like "Synthex Brand Refresh").
    candidate_name = (classified.project_name or body).strip()

    vague, reason = is_vague_name(candidate_name)
    if vague:
        return RouterDecision(
            action="reject",
            next_state="awaiting_project_name",
            reply_text=reason or "Can you give it a working name?",
        )

    # Duplicate check
    dup = find_duplicate_project(candidate_name, open_projects)
    if dup:
        return RouterDecision(
            action="surface_duplicate",
            next_state="awaiting_project_name",
            duplicate_match=dup,
            captured_project_name=candidate_name,
            captured_project_slug=_slugify(candidate_name),
            reply_text=(
                f"Looks like '{dup.name}' is already open — "
                f"want to continue that one, or start a new one anyway?"
            ),
        )

    captured_slug = _slugify(candidate_name)

    # Both-in-one-message — skip awaiting_idea
    if classified.has_idea and classified.idea:
        return RouterDecision(
            action="create_project",
            next_state="in_loop",
            captured_project_name=candidate_name,
            captured_project_slug=captured_slug,
            reply_text=(
                f"Locked in '{candidate_name}'. Let me get the Senior Project Manager "
                "across this — I'll be back shortly with the first read."
            ),
            metadata={"first_idea": classified.idea},
        )

    # Just the name — ask for the idea
    return RouterDecision(
        action="advance_to_idea",
        next_state="awaiting_idea",
        captured_project_name=candidate_name,
        captured_project_slug=captured_slug,
        reply_text=f"Got it — '{candidate_name}'. Tell me about it.",
    )


def _handle_awaiting_idea(body: str, thread: ThreadState) -> RouterDecision:
    if not body:
        return RouterDecision(
            action="reply",
            next_state="awaiting_idea",
            reply_text=f"Tell me about '{thread.candidate_name}' — what's the idea?",
        )
    return RouterDecision(
        action="create_project",
        next_state="in_loop",
        captured_project_name=thread.candidate_name,
        captured_project_slug=thread.candidate_slug,
        reply_text=(
            "Got it — handing this to the Senior Project Manager. "
            "Back shortly with the first read."
        ),
        metadata={"first_idea": body},
    )


def _handle_in_loop(body: str, thread: ThreadState, *, llm: LLMClient) -> RouterDecision:
    """Project exists — forward to SPM, but check for natural-language rename first."""
    classified = _classify_message(body, llm=llm)

    if classified.is_rename_signal and classified.proposed_new_name:
        proposed = classified.proposed_new_name.strip()
        vague, reason = is_vague_name(proposed)
        if vague:
            return RouterDecision(
                action="reject",
                next_state=thread.margot_state,
                reply_text=reason or "That new name's a bit too generic.",
            )
        return RouterDecision(
            action="rename_project",
            next_state=thread.margot_state,
            rename_to=proposed,
            captured_project_slug=_slugify(proposed),
            reply_text=f"Got it — switching the name to '{proposed}'.",
        )

    # Default: forward to SPM
    return RouterDecision(
        action="forward_to_spm",
        next_state="in_loop",
        reply_text="",  # SPM/board reply will follow asynchronously
        metadata={"forwarded_body": body},
    )
