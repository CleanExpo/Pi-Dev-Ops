"""
board_meeting.py — Board Meeting Gap Audit

Compares the Pi-CEO spec against actual source code and raises Linear tickets
for any discrepancies found. Runs via claude_agent_sdk exclusively
(SDK-only mandate, RA-1094B).

Usage:
    python -m app.server.agents.board_meeting [--dry-run] [--cycle N]
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.server import config


log = logging.getLogger("pi-ceo.agents.board-meeting")

ANTI_RUSH_PROTOCOL = """
## EXECUTION DISCIPLINE (NON-NEGOTIABLE)

PACE: Thoroughness over speed. Every task gets the time it needs.
- Before writing ANY code: read the existing codebase in the target area FIRST.
- Before proposing ANY architecture: read existing docs/architecture/ FIRST.
- Before ANY content: check memory for prior patterns FIRST.
- NEVER generate placeholder/TODO code. Every function is complete or not written.
- NEVER skip error handling, loading states, edge cases, or types.
- If unsure about requirements, ASK via ceo_report tool — do not assume.

QUALITY OVER QUANTITY:
- Fewer files with complete, tested code > many files with gaps.
- One fully working feature > three half-working features.
- Ask: "Would I ship this to a paying customer right now?" If no, keep working.
"""

BOARD_MEETING_SYSTEM = f"""You are the Senior Project Manager for Pi-CEO, running an autonomous board meeting.

{ANTI_RUSH_PROTOCOL}

## BOARD MEETING PROTOCOL

You run a structured 6-phase board deliberation:

Phase 1 — STATUS: Read the current Linear board state (all issues, their statuses).
Phase 2 — LINEAR REVIEW: Analyze what was completed, what is blocked, what is next.
Phase 3 — SWOT: Identify Strengths, Weaknesses, Opportunities, Threats for the project.
Phase 4 — SPRINT RECOMMENDATIONS: Propose the next sprint's priorities with rationale.
Phase 5 — SAVE MINUTES: Write structured board meeting minutes.
Phase 6 — UPDATE LINEAR: Create any new tickets identified during deliberation.

## OUTPUT FORMAT

Write board meeting minutes in markdown with:
- Date, cycle number, attendees (agent personas)
- Decisions made (with vote counts)
- Action items with owners and deadlines
- Risk register updates
- Next meeting trigger

## RULES

- Source decisions from actual project data, not assumptions
- Reference specific ticket IDs (RA-xxx) and file paths
- Zero filler language: no delve/tapestry/landscape/leverage/robust/seamless
- Every recommendation must have a concrete rationale
"""


# ── RA-609: Prior context loaders ────────────────────────────────────────────

def _read_prior_minutes(n: int = 2) -> str:
    """
    RA-609 — Read the last N board meeting minutes from .harness/board-meetings/.

    Returns a formatted string ready to inject into the board meeting system prompt.
    Skips gap-audit JSON files — only reads the -board-minutes.md files.
    """
    meetings_dir = _HARNESS_ROOT / "board-meetings"
    if not meetings_dir.exists():
        return ""

    minute_files = sorted(
        [f for f in meetings_dir.glob("*-board-minutes.md") if f.is_file()],
        key=lambda f: f.name,
        reverse=True,
    )[:n]

    if not minute_files:
        return ""

    sections: list[str] = []
    for f in reversed(minute_files):  # chronological order
        try:
            content = f.read_text(encoding="utf-8")[:4000]  # cap at 4k chars per meeting
            sections.append(f"### Prior Minutes: {f.stem}\n\n{content}")
        except Exception as exc:
            log.warning("Could not read board minutes %s: %s", f.name, exc)

    if not sections:
        return ""

    return (
        "\n\n## PRIOR BOARD MEETING MINUTES (last 2 cycles)\n\n"
        "Use these to maintain continuity — reference prior decisions, track action item completion.\n\n"
        + "\n\n---\n\n".join(sections)
    )


def _read_latest_anthropic_docs() -> str:
    """
    RA-609 — Read the most recent Anthropic docs snapshot from .harness/anthropic-docs/.

    Returns a formatted summary (capped at 6k chars) for injection into board context.
    Enables the board agent to cite current Anthropic capabilities + release notes.
    """
    docs_root = _HARNESS_ROOT / "anthropic-docs"
    if not docs_root.exists():
        return ""

    # Find the most recent dated directory (YYYY-MM-DD format)
    dated_dirs = sorted(
        [d for d in docs_root.iterdir() if d.is_dir() and d.name[:4].isdigit()],
        reverse=True,
    )
    if not dated_dirs:
        return ""

    latest_dir = dated_dirs[0]
    doc_files = sorted(latest_dir.glob("*.md"))[:5]  # read up to 5 doc files

    if not doc_files:
        return ""

    sections: list[str] = []
    total_chars = 0
    _CAP = 6000

    for f in doc_files:
        if total_chars >= _CAP:
            break
        try:
            content = f.read_text(encoding="utf-8")
            remaining = _CAP - total_chars
            sections.append(f"**{f.stem}**\n{content[:remaining]}")
            total_chars += min(len(content), remaining)
        except Exception as exc:
            log.warning("Could not read anthropic-docs file %s: %s", f.name, exc)

    if not sections:
        return ""

    return (
        f"\n\n## ANTHROPIC INTELLIGENCE SNAPSHOT ({latest_dir.name})\n\n"
        "Reference this when evaluating model capabilities, API changes, or new tooling.\n\n"
        + "\n\n".join(sections)
    )


def _read_zte_reality_status() -> str:
    """
    RA-608 — Read the ZTE reality-check status file if a stall is active.
    Injects a warning into board context so the agent acknowledges the stall.
    """
    status_file = _HARNESS_ROOT / "zte-reality-status.json"
    if not status_file.exists():
        return ""
    try:
        import json as _j
        status = _j.loads(status_file.read_text())
        if not status.get("stalled"):
            return ""
        stall_h = status.get("stall_h", 0)
        urgent = status.get("urgent_todo", 0)
        return (
            f"\n\n## ⚠️ ZTE REALITY CHECK — PIPELINE STALLED ({stall_h:.0f}h)\n\n"
            f"In Progress: **0** | Urgent/High Todo: **{urgent}**\n\n"
            f"The pipeline has been stalled for {stall_h:.0f} hours. This MUST be addressed "
            f"in Phase 4 (Sprint Recommendations) — identify the root cause and propose "
            f"a specific unblocking action."
        )
    except Exception:
        return ""


def _read_morning_intel() -> str:
    """
    RA-845 — Read today's AI platform intelligence from .harness/morning-intel/.

    Written by n8n at 11:45 AM AEST daily (Anthropic + OpenAI + xAI/Grok updates).
    Falls back to yesterday's file if today's hasn't arrived yet.
    Capped at 4k chars. Returns empty string if no file found.
    """
    from datetime import datetime, timezone, timedelta
    import json as _j

    intel_dir = _HARNESS_ROOT / "morning-intel"
    if not intel_dir.exists():
        return ""

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    yesterday = (datetime.now(timezone.utc) - timedelta(days=1)).strftime("%Y-%m-%d")

    intel_file = intel_dir / f"{today}.json"
    if not intel_file.exists():
        intel_file = intel_dir / f"{yesterday}.json"
    if not intel_file.exists():
        return ""

    try:
        data = _j.loads(intel_file.read_text())
    except Exception as exc:
        log.warning("Could not read morning intel %s: %s", intel_file.name, exc)
        return ""

    date_label = data.get("date", intel_file.stem)
    flags: list[str] = data.get("flags", [])
    critical_flags = [f for f in flags if "🔴" in f or "CRITICAL" in f.upper()]

    sections: list[str] = [f"## MORNING AI PLATFORM INTELLIGENCE — {date_label}\n"]

    if critical_flags:
        sections.append("### 🔴 CRITICAL FLAGS (address in Phase 1 STATUS)\n")
        sections.extend(f"- {f}" for f in critical_flags)
        sections.append("")

    for platform in ("anthropic", "openai", "xai"):
        content = (data.get(platform) or "").strip()
        if content:
            label = {"anthropic": "Anthropic / Claude", "openai": "OpenAI", "xai": "xAI / Grok"}[platform]
            sections.append(f"### {label}\n{content}\n")

    non_critical = [f for f in flags if f not in critical_flags]
    if non_critical:
        sections.append("### Other Flags\n")
        sections.extend(f"- {f}" for f in non_critical)

    result = "\n".join(sections)
    _CAP = 4000
    if len(result) > _CAP:
        result = result[:_CAP] + "\n\n_(truncated — full file in .harness/morning-intel/)_"

    return result


# ── Gap audit constants ───────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parents[3]  # Pi-Dev-Ops/
_HARNESS_ROOT = _REPO_ROOT / ".harness"
_LINEAR_API_URL = "https://api.linear.app/graphql"
_LINEAR_TEAM_ID = config.LINEAR_TEAM_ID
_LINEAR_PROJECT_ID = config.LINEAR_PROJECT_ID

# Maps a spec claim category to the source file(s) to audit against.
_AUDIT_TARGETS: list[dict[str, Any]] = [
    {
        "category": "multi-branch reads",
        "claim": "spec claims GitHub integration reads branches",
        "files": ["dashboard/lib/github.ts"],
        "probe": "multi-branch iteration or comparison logic (e.g. loop over branches, compare two branches)",
    },
    {
        "category": "Linear two-way sync",
        "claim": "spec claims Linear two-way sync — webhook triggers builds AND state updates flow back to Linear",
        "files": ["app/server/webhook.py", "app/server/main.py"],
        "probe": "outbound Linear API calls that update issue state (linear_update_issue or issueUpdate mutation called from Python)",
    },
    {
        "category": "Telegram commands",
        "claim": "spec/MCP describe Telegram bot commands (/start, /help, /build)",
        "files": ["dashboard/app/api/telegram/route.ts"],
        "probe": "/start, /help, or other slash command handlers",
    },
    {
        "category": "E2E and integration test coverage",
        "claim": "spec marks test coverage as ✅ Complete (22-check smoke test suite)",
        "files": ["tests/test_auth.py", "tests/test_webhook.py", "scripts/smoke_test.py"],
        "probe": "E2E or integration tests covering the full build pipeline (sessions, evaluator, push)",
    },
    {
        "category": "build log SSE streaming",
        "claim": "spec implies build logs stream to browser in real time",
        "files": ["app/server/sessions.py", "app/server/main.py"],
        "probe": "SSE (Server-Sent Events) endpoint that pipes session.output_lines — distinct from WebSocket /ws/build/{sid}",
    },
]


# ── Linear helpers ────────────────────────────────────────────────────────────

def _linear_gql(query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
    """Execute a Linear GraphQL query. Returns the `data` key of the response."""
    api_key = os.environ.get("LINEAR_API_KEY", "")
    if not api_key:
        raise RuntimeError("LINEAR_API_KEY env var not set")
    body = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        _LINEAR_API_URL,
        data=body,
        headers={
            "Content-Type": "application/json",
            "Authorization": api_key,
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        payload = json.loads(resp.read())
    if "errors" in payload:
        raise RuntimeError(f"Linear API error: {payload['errors']}")
    return payload["data"]


def _linear_create_issue(title: str, description: str, priority: int) -> str:
    """Create a Linear issue. Returns the issue identifier (e.g. RA-500)."""
    data = _linear_gql(
        """
        mutation CreateIssue($input: IssueCreateInput!) {
          issueCreate(input: $input) {
            success
            issue { identifier url }
          }
        }
        """,
        {
            "input": {
                "title": title,
                "description": description,
                "teamId": _LINEAR_TEAM_ID,
                "projectId": _LINEAR_PROJECT_ID,
                "priority": priority,
            }
        },
    )
    return data["issueCreate"]["issue"]["identifier"]


# ── Spec claim extraction ─────────────────────────────────────────────────────

_CLAIM_PATTERN = re.compile(
    r"(?:✅|Complete|RESOLVED|implemented|wired).*",
    re.IGNORECASE,
)


def _extract_spec_claims(spec_text: str) -> list[str]:
    """Return every line from spec.md that contains a capability claim marker."""
    claims: list[str] = []
    for line in spec_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if re.search(r"✅|RESOLVED|wired\b|implemented\b", stripped, re.IGNORECASE):
            claims.append(stripped[:300])
    return claims


# ── Claude SDK helper ────────────────────────────────────────────────────────

def _run_prompt_via_sdk(
    prompt: str,
    model: str = "claude-sonnet-4-6",
    timeout: int = 120,
    thinking: str = "adaptive",
) -> str:
    """Run a single-shot prompt via claude_agent_sdk and return the text response.

    thinking: "adaptive" (default), "enabled" (8k budget for deep analysis), "disabled".
    Falls back silently to empty string on any SDK error so the caller can
    fall through to the subprocess path.
    """
    try:
        from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, TextBlock
        from claude_agent_sdk.types import (
            ThinkingConfigAdaptive, ThinkingConfigEnabled, ThinkingConfigDisabled,
            HookMatcher, PreToolUseHookInput, PostToolUseHookInput,
        )
    except ImportError:
        log.warning("claude_agent_sdk not installed — falling back to subprocess")
        return ""

    # RA-1420 — pop ANTHROPIC_API_KEY if empty OR an OAuth token. sk-ant-oat01-*
    # tokens belong in ~/.claude/ keychain OAuth, not the env var. When set as env,
    # the bundled CLI rejects them with "Invalid API key · Fix external API key".
    _k = os.environ.get("ANTHROPIC_API_KEY", "")
    if _k == "" or _k.startswith("sk-ant-oat01-"):
        os.environ.pop("ANTHROPIC_API_KEY", None)

    # RA-659 — build thinking config
    if thinking == "adaptive":
        _thinking_cfg = ThinkingConfigAdaptive(type="adaptive")
    elif thinking == "enabled":
        _thinking_cfg = ThinkingConfigEnabled(type="enabled", budget_tokens=8000)
    else:
        _thinking_cfg = ThinkingConfigDisabled(type="disabled")

    # RA-662 — SDK hooks for board meeting observability
    _tool_timers: dict[str, float] = {}

    async def _on_pre_tool(hook_input: PreToolUseHookInput) -> None:
        _tool_timers[hook_input.tool_use_id] = time.monotonic()
        log.debug("board_meeting tool_start tool=%s id=%s", hook_input.tool_name, hook_input.tool_use_id)

    async def _on_post_tool(hook_input: PostToolUseHookInput) -> None:
        elapsed = time.monotonic() - _tool_timers.pop(hook_input.tool_use_id, time.monotonic())
        log.info(
            "board_meeting tool_done tool=%s id=%s latency_ms=%d",
            hook_input.tool_name, hook_input.tool_use_id, int(elapsed * 1000),
        )

    async def _run() -> str:
        hooks = {
            "PreToolUse": [HookMatcher(hooks=[_on_pre_tool])],
            "PostToolUse": [HookMatcher(hooks=[_on_post_tool])],
        }
        options = ClaudeAgentOptions(model=model, max_turns=1, thinking=_thinking_cfg, hooks=hooks, permission_mode="bypassPermissions")
        client = ClaudeSDKClient(options)
        text_parts: list[str] = []
        try:
            await client.connect()
            await client.query(prompt)
            async for msg in client.receive_messages():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            text_parts.append(block.text)
                elif isinstance(msg, ResultMessage):
                    break
        finally:
            await client.disconnect()
        return "".join(text_parts)

    try:
        return asyncio.run(asyncio.wait_for(_run(), timeout=timeout))
    except Exception as exc:
        log.warning("claude_agent_sdk call failed: %s — falling back to subprocess", exc)
        return ""


def _run_prompt_with_cache(
    system_text: str,
    user_content: str,
    model: str = "claude-sonnet-4-6",
    timeout: int = 120,
) -> str:
    """RA-655 — Run a single-shot prompt via direct Anthropic API with prompt caching.

    Passes system_text as a single cached content block (ephemeral TTL). Across the 5
    audit category calls in run_gap_audit_phase(), the shared board context (prior minutes
    + anthropic-docs) hits the cache on calls 2-5, reducing cost ~70%.

    RA-1009 — caching is only active when ENABLE_PROMPT_CACHING_1H=1. When disabled,
    returns empty string immediately so the caller falls through to SDK/subprocess.

    Returns response text, or empty string on any error so caller falls back.
    """
    if not config.ENABLE_PROMPT_CACHING_1H:
        return ""

    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not api_key:
        return ""

    try:
        import anthropic as _anthropic  # noqa: PLC0415
    except ImportError:
        log.warning("anthropic package not installed — skipping cached board prompt path")
        return ""

    system_blocks = [
        {
            "type": "text",
            "text": system_text,
            "cache_control": {"type": "ephemeral"},
        }
    ]

    try:
        client = _anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model=model,
            max_tokens=2048,
            system=system_blocks,
            messages=[{"role": "user", "content": user_content}],
            timeout=timeout,
        )
        text = message.content[0].text if message.content else ""
        usage = message.usage
        log.info(
            "board-cache input=%d cache_write=%d cache_read=%d output=%d",
            getattr(usage, "input_tokens", 0),
            getattr(usage, "cache_creation_input_tokens", 0),
            getattr(usage, "cache_read_input_tokens", 0),
            getattr(usage, "output_tokens", 0),
        )
        return text
    except Exception as exc:
        log.warning("board-cache failed: %s — will fall back to SDK/subprocess", exc)
        return ""


# ── Claude CLI call ───────────────────────────────────────────────────────────

def _call_claude_for_discrepancies(
    spec_claims: list[str],
    audit_target: dict[str, Any],
    file_contents: dict[str, str],
    system_prompt: str | None = None,
) -> list[dict[str, Any]]:
    """Call the claude CLI to compare spec claims against actual source files.
    If system_prompt is provided (RA-609 enriched context), it is prepended to the prompt.

    Returns a list of discrepancy dicts: {severity, claim, reality, file, recommendation}.
    """
    claims_block = "\n".join(f"- {c}" for c in spec_claims[:40])
    files_block = "\n\n".join(
        f"=== FILE: {path} ===\n{content[:6000]}"
        for path, content in file_contents.items()
    )

    # RA-609 — prepend enriched board context if provided
    context_header = ""
    if system_prompt and len(system_prompt) > len(BOARD_MEETING_SYSTEM):
        # Include the context delta (prior minutes + anthropic-docs) but not the full protocol
        # to keep the audit prompt focused
        extra = system_prompt[len(BOARD_MEETING_SYSTEM):].strip()
        if extra:
            context_header = f"{extra}\n\n---\n\n"

    prompt = f"""{context_header}You are auditing a project spec against actual source code.

AUDIT CATEGORY: {audit_target['category']}
WHAT THE SPEC CLAIMS: {audit_target['claim']}
PROBE — look specifically for: {audit_target['probe']}

RELEVANT SPEC CLAIMS (lines containing ✅ / Complete / RESOLVED / implemented / wired):
{claims_block}

ACTUAL SOURCE FILES:
{files_block}

TASK:
Compare the spec claims against the actual code. Identify every discrepancy where the spec says something is complete/implemented but the code does not actually implement it, or implements it differently.

OUTPUT FORMAT (strict JSON array, no markdown, no explanation outside the array):
[
  {{
    "severity": "critical|high|low",
    "claim": "exact text of the spec claim",
    "reality": "what the code actually does or lacks",
    "file": "the most relevant file path",
    "recommendation": "concrete fix in one sentence"
  }}
]

If there are no discrepancies, output: []
Output ONLY the JSON array.
"""

    # RA-1094B — SDK-only mandate: subprocess fallback removed.
    raw = ""

    # RA-655 — prefer cached direct API path when system_prompt + ANTHROPIC_API_KEY available
    if system_prompt and os.environ.get("ANTHROPIC_API_KEY", ""):
        # Build the audit-only prompt (no context_header — that's the system message)
        audit_only_prompt = f"""You are auditing a project spec against actual source code.

AUDIT CATEGORY: {audit_target['category']}
WHAT THE SPEC CLAIMS: {audit_target['claim']}
PROBE — look specifically for: {audit_target['probe']}

RELEVANT SPEC CLAIMS (lines containing ✅ / Complete / RESOLVED / implemented / wired):
{claims_block}

ACTUAL SOURCE FILES:
{files_block}

TASK:
Compare the spec claims against the actual code. Identify every discrepancy where the spec says something is complete/implemented but the code does not actually implement it, or implements it differently.

OUTPUT FORMAT (strict JSON array, no markdown, no explanation outside the array):
[
  {{
    "severity": "critical|high|low",
    "claim": "exact text of the spec claim",
    "reality": "what the code actually does or lacks",
    "file": "the most relevant file path",
    "recommendation": "concrete fix in one sentence"
  }}
]

If there are no discrepancies, output: []
Output ONLY the JSON array.
"""
        raw = _run_prompt_with_cache(
            system_text=system_prompt,
            user_content=audit_only_prompt,
            model="claude-sonnet-4-6",
            timeout=120,
        )
        if not raw:
            log.info("board-cache returned empty — falling back for category=%s", audit_target["category"])

    if not raw:
        raw = _run_prompt_via_sdk(prompt, model="claude-sonnet-4-6", timeout=120)
        if not raw:
            log.info("SDK returned empty for category=%s", audit_target["category"])

    if not raw:
        log.warning("claude returned empty output for category=%s", audit_target["category"])
        return []

    # Strip markdown code fences if present
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.MULTILINE)
    raw = re.sub(r"\s*```$", "", raw, flags=re.MULTILINE)
    raw = raw.strip()

    # Extract the JSON array
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    if not match:
        log.warning("No JSON array found in claude output for category=%s; raw=%s", audit_target["category"], raw[:200])
        return []

    try:
        items = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        log.warning("JSON parse error for category=%s: %s", audit_target["category"], exc)
        return []

    if not isinstance(items, list):
        return []

    validated: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        validated.append(
            {
                "severity": str(item.get("severity", "low")).lower(),
                "claim": str(item.get("claim", "")),
                "reality": str(item.get("reality", "")),
                "file": str(item.get("file", audit_target["files"][0])),
                "recommendation": str(item.get("recommendation", "")),
                "category": audit_target["category"],
            }
        )
    return validated


# ── Main gap audit phase ──────────────────────────────────────────────────────

def build_board_system_prompt() -> str:
    """
    RA-609 / RA-845 — Build the full board meeting system prompt with injected context:
      - Core BOARD_MEETING_SYSTEM protocol
      - ZTE reality-check stall warning (if pipeline is stalled)
      - Prior board meeting minutes (last 2 cycles)
      - Latest Anthropic intelligence snapshot
      - Morning AI platform intelligence (Anthropic + OpenAI + xAI/Grok, written by n8n at 11:45 AM)

    Call this instead of using BOARD_MEETING_SYSTEM directly so every
    board meeting cycle has full continuity context.
    """
    parts = [BOARD_MEETING_SYSTEM]

    zte_warning = _read_zte_reality_status()
    if zte_warning:
        log.warning("Board context: ZTE stall warning injected into system prompt")
        parts.append(zte_warning)

    prior_minutes = _read_prior_minutes(n=2)
    if prior_minutes:
        log.info("Board context: injected prior minutes from last 2 cycles")
        parts.append(prior_minutes)
    else:
        log.info("Board context: no prior minutes found in .harness/board-meetings/")

    anthropic_docs = _read_latest_anthropic_docs()
    if anthropic_docs:
        log.info("Board context: injected Anthropic intelligence snapshot")
        parts.append(anthropic_docs)
    else:
        log.info("Board context: no Anthropic docs snapshot found in .harness/anthropic-docs/")

    morning_intel = _read_morning_intel()
    if morning_intel:
        log.info("Board context: injected morning AI platform intelligence (RA-845)")
        parts.append(morning_intel)
    else:
        log.info("Board context: no morning intel found in .harness/morning-intel/ (n8n not yet run?)")

    return "\n".join(parts)


def run_gap_audit_phase(dry_run: bool = False) -> dict[str, Any]:
    """Phase 6 — LIVE CODE GAP AUDIT.

    1. Reads spec.md for capability claims.
    2. For each audit target, reads the relevant source files.
    3. Calls claude CLI to compare claims vs code (with full board context injected).
    4. Buckets discrepancies into critical / high / low.
    5. Auto-creates Linear tickets for critical and high gaps.
    6. Saves output to .harness/board-meetings/{date}-gap-audit.json.

    Returns the structured audit result dict.
    """
    log.info("Starting Phase 6 — LIVE CODE GAP AUDIT")

    # RA-609 — build enriched system prompt with prior minutes + anthropic-docs
    enriched_system = build_board_system_prompt()
    if len(enriched_system) > len(BOARD_MEETING_SYSTEM):
        log.info(
            "Board context enriched: +%d chars (prior minutes + anthropic-docs injected)",
            len(enriched_system) - len(BOARD_MEETING_SYSTEM),
        )
    start = time.monotonic()

    # 1. Read spec.md
    spec_path = _HARNESS_ROOT / "spec.md"
    if not spec_path.exists():
        log.warning("spec.md not found at %s — skipping gap audit", spec_path)
        return {"error": "spec.md not found", "critical": [], "high": [], "low": []}

    spec_text = spec_path.read_text(encoding="utf-8")
    spec_claims = _extract_spec_claims(spec_text)
    log.info("Extracted %d capability claims from spec.md", len(spec_claims))

    all_discrepancies: list[dict[str, Any]] = []

    # 2–3. For each audit target: read files, call claude
    for target in _AUDIT_TARGETS:
        log.info("Auditing category: %s", target["category"])
        file_contents: dict[str, str] = {}

        for rel_path in target["files"]:
            abs_path = _REPO_ROOT / rel_path
            if abs_path.exists():
                try:
                    file_contents[rel_path] = abs_path.read_text(encoding="utf-8")
                except Exception as exc:
                    log.warning("Could not read %s: %s", abs_path, exc)
                    file_contents[rel_path] = f"[read error: {exc}]"
            else:
                file_contents[rel_path] = "[file not found]"
                log.warning("Audit target file not found: %s", abs_path)

        if dry_run:
            log.info("DRY RUN — skipping claude call for category=%s", target["category"])
            continue

        try:
            items = _call_claude_for_discrepancies(
                spec_claims, target, file_contents, system_prompt=enriched_system
            )
            log.info("category=%s discrepancies=%d", target["category"], len(items))
            all_discrepancies.extend(items)
        except Exception as exc:
            log.warning("Gap audit error for category=%s: %s", target["category"], exc)

    # 4. Bucket by severity
    result: dict[str, Any] = {"critical": [], "high": [], "low": []}
    for item in all_discrepancies:
        sev = item.get("severity", "low")
        bucket = sev if sev in result else "low"
        result[bucket].append(item)

    result["summary"] = {
        "total_discrepancies": len(all_discrepancies),
        "critical_count": len(result["critical"]),
        "high_count": len(result["high"]),
        "low_count": len(result["low"]),
        "duration_s": round(time.monotonic() - start, 1),
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "spec_claims_scanned": len(spec_claims),
        "dry_run": dry_run,
    }

    # 5. Auto-create Linear tickets for critical and high gaps
    linear_api_key = os.environ.get("LINEAR_API_KEY", "")
    tickets_created: list[str] = []

    if linear_api_key and not dry_run:
        for sev, priority in (("critical", 1), ("high", 2)):
            for item in result[sev]:
                title = f"[GAP-AUDIT] {item['category']}: {item['claim'][:80]}"
                description = (
                    f"**Gap detected by board meeting gap audit**\n\n"
                    f"**Spec claim:** {item['claim']}\n\n"
                    f"**Reality:** {item['reality']}\n\n"
                    f"**Relevant file:** `{item['file']}`\n\n"
                    f"**Recommendation:** {item['recommendation']}\n\n"
                    f"_Auto-created by board_meeting.py gap audit — "
                    f"{datetime.now(timezone.utc).strftime('%Y-%m-%d')}_"
                )
                try:
                    identifier = _linear_create_issue(title, description, priority)
                    tickets_created.append(identifier)
                    log.info("Created Linear ticket %s for %s gap: %s", identifier, sev, item["category"])
                except Exception as exc:
                    log.warning("Failed to create Linear ticket for %s gap: %s", sev, exc)
    elif not linear_api_key:
        log.warning("LINEAR_API_KEY not set — skipping auto-ticket creation")

    result["summary"]["linear_tickets_created"] = tickets_created

    # 6. Save output to .harness/board-meetings/{date}-gap-audit.json
    board_meetings_dir = _HARNESS_ROOT / "board-meetings"
    board_meetings_dir.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    output_path = board_meetings_dir / f"{date_str}-gap-audit.json"
    output_path.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    log.info(
        "Gap audit saved to %s | critical=%d high=%d low=%d tickets=%d",
        output_path,
        len(result["critical"]),
        len(result["high"]),
        len(result["low"]),
        len(tickets_created),
    )

    return result


# ── RA-658: lessons.jsonl reader ──────────────────────────────────────────────

def _read_lessons(n: int = 20) -> str:
    """Read the last N entries from lessons.jsonl, formatted for board context."""
    path = _HARNESS_ROOT / "lessons.jsonl"
    if not path.exists():
        return ""
    try:
        lines = [ln.strip() for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        recent = lines[-n:]
        if not recent:
            return ""
        entries: list[str] = []
        for line in recent:
            try:
                entry = json.loads(line)
                entries.append(
                    f"[{entry.get('severity', 'info').upper()}] "
                    f"{entry.get('source', '?')}/{entry.get('category', '?')}: "
                    f"{entry.get('lesson', '')}"
                )
            except json.JSONDecodeError:
                entries.append(line[:200])
        return (
            f"\n\n## OPERATIONAL INTELLIGENCE (last {len(entries)} lessons)\n\n"
            + "\n".join(f"- {e}" for e in entries)
        )
    except Exception as exc:
        log.warning("Could not read lessons.jsonl: %s", exc)
        return ""


# ── RA-686: CEO Board Personas ───────────────────────────────────────────────

CEO_BOARD_PERSONAS = {
    "CEO": (
        "Strategic Operator. Focus: execution velocity, founder leverage, system ROI. "
        "Asks: Is this the highest-leverage use of current capacity? "
        "Bias toward ruthless prioritisation and shipping."
    ),
    "Revenue": (
        "Revenue Officer. Focus: client outcomes, monetisation, deal risk. "
        "Asks: Does this move money or protect existing revenue? "
        "Bias toward client-facing impact and commercial reality."
    ),
    "Product Strategist": (
        "Product lead. Focus: user needs, product-market fit, feature value. "
        "Asks: Do real users need this, and will they pay for it? "
        "Bias toward validated demand over internal assumptions."
    ),
    "Technical Architect": (
        "Senior architect. Focus: architecture integrity, tech debt, maintainability. "
        "Asks: Can we maintain, extend, and trust this system? "
        "Bias toward simplicity, reliability, and long-term code health."
    ),
    "Contrarian": (
        "Devil's advocate. Focus: challenge every assumption and recommendation. "
        "Asks: What are we getting wrong? What is the failure mode nobody is naming? "
        "Bias toward surfacing uncomfortable truths before they become crises."
    ),
    "Compounder": (
        "Long-term value thinker. Focus: compound returns, moats, durability. "
        "Asks: Does this compound over time or depreciate? Will we regret prioritising this in 6 months? "
        "Bias toward actions that build lasting capability, not one-off wins."
    ),
    "Custom Oracle": (
        "Domain expert: Australian B2B SaaS, insurance-linked compliance, restoration industry. "
        "Asks: Is this commercially safe for clients operating in regulated environments? "
        "Bias toward risk management — a security incident in this space is a termination event."
    ),
    "Market Strategist": (
        "Market positioning lead. Focus: competitive differentiation, timing, external signals. "
        "Asks: What does the market signal, and are we positioned to capitalise on it? "
        "Bias toward external validation over internal conviction."
    ),
    "Moonshot": (
        "Ceiling thinker. Focus: productisation ceiling, 10x framing, founder OS vision. "
        "Asks: What becomes possible if this system actually works at scale? "
        "Bias toward the largest viable ambition — challenges the team to see the ceiling."
    ),
}


# ── RA-1972: Phase 2.4 — Research Brief (evidence before debate) ─────────────

# RA-1974 — Margot deep-research mode selector. Set TAO_BOARD_RESEARCH_MODE
# in env to one of:
#   fast   (default) — RA-1972 path: 180s WebSearch + WebFetch subagent
#   hybrid           — fast this cycle + dispatch Margot for next cycle's harvest
#   deep             — Margot only; this cycle has no fresh research; next cycle harvests
_VALID_RESEARCH_MODES = {"fast", "hybrid", "deep"}


def _resolve_board_research_mode() -> str:
    """Read + validate TAO_BOARD_RESEARCH_MODE env. Invalid → fast + warn."""
    mode = (os.environ.get("TAO_BOARD_RESEARCH_MODE") or "fast").lower().strip()
    if mode not in _VALID_RESEARCH_MODES:
        log.warning(
            "TAO_BOARD_RESEARCH_MODE=%r invalid (expect one of %s) — defaulting to 'fast'",
            mode, sorted(_VALID_RESEARCH_MODES),
        )
        return "fast"
    return mode


def _run_research_via_sdk(
    prompt: str,
    *,
    model: str = "claude-sonnet-4-6",
    timeout: int = 180,
    max_turns: int = 10,
) -> str:
    """RA-1972 — Sibling of _run_prompt_via_sdk that allows WebSearch + WebFetch tools.

    The base _run_prompt_via_sdk hard-codes max_turns=1 and exposes no allowed_tools,
    which is correct for single-shot persona-debate calls. Research needs multi-turn
    tool use: search → fetch → maybe search again → answer. This helper opens that
    door without mutating the existing helper's signature.

    Returns the model's final text response (concatenated TextBlocks across all
    turns). Empty string on any SDK failure — caller treats that as
    `research_required: false` with `failure_reason` populated.
    """
    try:
        from claude_agent_sdk import (
            AssistantMessage,
            ClaudeAgentOptions,
            ClaudeSDKClient,
            ResultMessage,
            TextBlock,
        )
        from claude_agent_sdk.types import ThinkingConfigAdaptive
    except ImportError:
        log.warning("claude_agent_sdk not installed — research phase unavailable")
        return ""

    # RA-1420 hygiene — same env handling as _run_prompt_via_sdk
    _k = os.environ.get("ANTHROPIC_API_KEY", "")
    if _k == "" or _k.startswith("sk-ant-oat01-"):
        os.environ.pop("ANTHROPIC_API_KEY", None)

    async def _run() -> str:
        options = ClaudeAgentOptions(
            model=model,
            max_turns=max_turns,
            thinking=ThinkingConfigAdaptive(type="adaptive"),
            allowed_tools=["WebSearch", "WebFetch"],
            permission_mode="bypassPermissions",
        )
        client = ClaudeSDKClient(options)
        text_parts: list[str] = []
        try:
            await client.connect()
            await client.query(prompt)
            async for msg in client.receive_messages():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            text_parts.append(block.text)
                elif isinstance(msg, ResultMessage):
                    break
        finally:
            await client.disconnect()
        return "".join(text_parts)

    try:
        return asyncio.run(asyncio.wait_for(_run(), timeout=timeout))
    except Exception as exc:
        log.warning("research SDK call failed: %s", exc)
        return ""


def _extract_json_object(text: str) -> dict[str, Any] | None:
    """Pull the first balanced JSON object out of a model response.

    Models often wrap JSON in ```json fences or precede it with prose. This walks the
    string, finds the first `{`, then matches braces (respecting strings) until balance
    hits zero. Returns the parsed dict, or None if no valid JSON object found.
    """
    if not text:
        return None
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\" and in_str:
            escape = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[start : i + 1])
                except json.JSONDecodeError:
                    return None
    return None


def _validate_research_brief(brief: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    """Enforce contract: every finding has ≥1 source URL with fetched-date.

    Drops malformed findings into open_questions. Returns (cleaned_brief, warnings).
    """
    warnings: list[str] = []
    findings_in = brief.get("findings", []) or []
    cleaned_findings: list[dict[str, Any]] = []
    promoted_to_open: list[str] = list(brief.get("open_questions", []) or [])

    for idx, f in enumerate(findings_in):
        if not isinstance(f, dict):
            warnings.append(f"finding #{idx} not a dict — dropped")
            continue
        sources = f.get("sources", []) or []
        valid_sources = [
            s for s in sources
            if isinstance(s, dict) and s.get("url") and s.get("fetched")
        ]
        if not valid_sources:
            q = str(f.get("question", "")) or f"finding #{idx}"
            promoted_to_open.append(f"{q} (claim had no cited source)")
            warnings.append(f"finding #{idx} dropped — no cited source with fetched-date")
            continue
        f["sources"] = valid_sources
        if f.get("confidence") not in ("high", "medium", "low"):
            f["confidence"] = "low"
        cleaned_findings.append(f)

    brief["findings"] = cleaned_findings
    brief["open_questions"] = promoted_to_open
    if not cleaned_findings and not promoted_to_open:
        brief["research_required"] = False
        brief["failure_reason"] = "no findings survived validation"
    return brief, warnings


def _render_findings_block(findings: list[dict[str, Any]], opens: list[str], header: str) -> str:
    """Shared renderer for a single findings + opens section. Used by both the
    current-cycle brief and the prior-cycle Margot harvest."""
    parts = [header]
    for i, f in enumerate(findings or [], start=1):
        conf = f.get("confidence", "low").upper()
        parts.append(f"\n**Finding #{i}** [{conf}] — _{f.get('question', '')}_")
        parts.append(f"\n  {f.get('claim', '')}")
        for s in f.get("sources", []):
            url = s.get("url", "")
            title = s.get("title", url)
            fetched = s.get("fetched", "")
            parts.append(f"\n  - [{title}]({url}) (fetched {fetched})")
    if opens:
        parts.append("\n\n**Open questions** (research could not resolve):")
        for q in opens:
            parts.append(f"\n  - {q}")
    return "".join(parts)


def _format_research_brief_for_personas(brief: dict[str, Any]) -> str:
    """Render the research brief as a markdown block ready to inject into the
    persona-debate user_content. Returns empty string if research_required is False
    AND no prior_deep_research is attached."""
    has_prior = bool(brief.get("prior_deep_research"))
    if not brief.get("research_required") and not has_prior:
        reason = brief.get("failure_reason") or "brief was self-contained"
        return (
            "\n\n## RESEARCH BRIEF (Phase 2.4)\n\n"
            f"_Stage skipped — {reason}._ Personas argue from priors only this cycle.\n"
        )

    out: list[str] = ["\n\n## RESEARCH BRIEF (Phase 2.4)"]

    # RA-1974 — prior-cycle Margot harvest, if present, is rendered first so
    # personas see the deep evidence before the (often shallower) current-cycle
    # fast research.
    if has_prior:
        prior = brief["prior_deep_research"]
        if isinstance(prior, dict):
            prior = [prior]
        for p in prior:
            mode = p.get("mode", "margot")
            dispatched = p.get("dispatched_at", "?")
            completed = p.get("completed_at", "?")
            header = (
                f"\n\n### DEEP RESEARCH ({mode}, dispatched {dispatched}, completed {completed})\n"
                "_Note: this research was dispatched at the prior monthly cycle. "
                "Some claims may have moved on; weight accordingly._\n"
            )
            out.append(_render_findings_block(
                p.get("findings", []), p.get("open_questions", []), header,
            ))

    if brief.get("research_required"):
        cost = brief.get("cost_seconds", "?")
        mode = brief.get("mode", "fast")
        header = f"\n\n### CURRENT-CYCLE RESEARCH ({mode}, {cost}s)\n"
        out.append(_render_findings_block(
            brief.get("findings", []), brief.get("open_questions", []), header,
        ))
    elif brief.get("failure_reason"):
        # Current cycle has no fresh research but prior was harvested — note it
        out.append(
            f"\n\n_Current cycle: {brief['failure_reason']}._\n"
        )

    out.append(
        "\n\n_Personas: cite findings by `#N` when your position depends on a fact. "
        "The Contrarian MUST flag at least one open question or low-confidence claim._"
    )
    return "".join(out)


# ── RA-1974: Margot deep-research wiring ─────────────────────────────────────

def _margot_kill_switch_active() -> bool:
    """Margot is gated on TAO_SWARM_ENABLED=1 (project-wide kill switch)."""
    return os.environ.get("TAO_SWARM_ENABLED", "0") != "1"


def _board_originating_session_id(cycle: int, date_str: str) -> str:
    """Stable tag for inflight entries we own. Filtered on harvest."""
    return f"board_meeting:{cycle}:{date_str}"


def _dispatch_margot_for_next_cycle(
    topic: str, *, cycle: int, date_str: str, use_corpus: bool = True,
) -> dict[str, Any] | None:
    """Fire-and-forget dispatch to Margot's deep_research_max.

    Returns the dispatch dict (`{interaction_id, status, dispatched_at, ...}`)
    on success, or None on any failure (kill switch, Margot unreachable, exception).
    margot_tools already records the inflight entry; no extra disk write here.
    """
    if _margot_kill_switch_active():
        log.info("Margot dispatch skipped — TAO_SWARM_ENABLED=0 (kill switch)")
        return None
    try:
        from swarm.margot_tools import deep_research_max  # local import; optional dep
    except ImportError as exc:
        log.warning("Margot dispatch skipped — swarm.margot_tools import failed: %s", exc)
        return None
    try:
        result = deep_research_max(
            topic=topic,
            use_corpus=use_corpus,
            originating_session_id=_board_originating_session_id(cycle, date_str),
        )
        if isinstance(result, dict) and result.get("error"):
            log.warning("Margot dispatch returned error: %s", result.get("error"))
            return None
        log.info(
            "Margot dispatched: interaction_id=%s cycle=%s",
            result.get("interaction_id"), cycle,
        )
        return result
    except Exception as exc:  # pragma: no cover — defensive
        log.warning("Margot dispatch raised: %s", exc)
        return None


def _normalize_margot_to_research_brief(
    margot_result: dict[str, Any],
    *,
    questions: list[str] | None = None,
    dispatched_at: str | None = None,
    completed_at: str | None = None,
) -> dict[str, Any]:
    """Transform Margot's check_research output into the RA-1972 brief contract.

    Margot returns a markdown report + citations list. We split the report into
    findings using the input questions as anchors (heuristic: a section header
    matching or containing a question maps that question to the surrounding
    claim text). Surplus questions → open_questions.

    Always passes through _validate_research_brief, so sourceless findings get
    promoted to open_questions automatically.
    """
    questions = questions or []
    report = (
        margot_result.get("report")
        or margot_result.get("text")
        or margot_result.get("summary")
        or margot_result.get("content")
        or ""
    )
    citations = margot_result.get("citations") or margot_result.get("sources") or []

    # Build a single shared sources[] from Margot citations
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    sources: list[dict[str, Any]] = []
    for c in citations:
        if not isinstance(c, dict):
            continue
        url = c.get("url") or c.get("uri") or c.get("link")
        if not url:
            continue
        sources.append({
            "url": url,
            "title": c.get("title") or url,
            "fetched": c.get("fetched") or completed_at or today,
            "excerpt": (c.get("excerpt") or c.get("snippet") or "")[:200],
        })

    # Heuristic question-to-section split. Margot tends to use ## or ### headers
    # that paraphrase or quote the question. We slice the report on header lines
    # and assign each slice to the closest-matching question.
    findings: list[dict[str, Any]] = []
    open_questions: list[str] = []
    if report and questions:
        # Split on markdown headers (## or ### at line start)
        sections = re.split(r"\n(?=#{2,3} )", "\n" + report)
        sections = [s.strip() for s in sections if s.strip()]
        used_questions: set[int] = set()
        for sec in sections:
            best_idx = -1
            best_score = 0
            for i, q in enumerate(questions):
                if i in used_questions:
                    continue
                # Score = count of question keywords (≥4 chars) appearing in section header line
                first_line = sec.split("\n", 1)[0].lower()
                keywords = [w for w in re.findall(r"\w+", q.lower()) if len(w) >= 4]
                score = sum(1 for k in keywords if k in first_line)
                if score > best_score:
                    best_score = score
                    best_idx = i
            if best_idx >= 0 and best_score >= 1:
                used_questions.add(best_idx)
                # Strip the header line from the claim
                _, _, claim_body = sec.partition("\n")
                findings.append({
                    "question": questions[best_idx],
                    "claim": (claim_body.strip() or sec)[:500],
                    "confidence": "high",
                    "sources": list(sources),  # all Margot citations attach to every finding
                })
        for i, q in enumerate(questions):
            if i not in used_questions:
                open_questions.append(f"{q} (Margot report did not address)")
    elif report and not questions:
        # No questions provided; emit one wholesale finding
        findings.append({
            "question": "Margot deep-research synthesis",
            "claim": report[:500],
            "confidence": "high",
            "sources": list(sources),
        })

    brief = {
        "research_required": True,
        "mode": "margot",
        "questions": list(questions),
        "findings": findings,
        "open_questions": open_questions,
        "dispatched_at": dispatched_at,
        "completed_at": completed_at or datetime.now(timezone.utc).isoformat(),
        "cost_seconds": None,
        "failure_reason": None,
    }
    if dispatched_at and completed_at:
        try:
            d = datetime.fromisoformat(dispatched_at.replace("Z", "+00:00"))
            c = datetime.fromisoformat(completed_at.replace("Z", "+00:00"))
            brief["cost_seconds"] = round((c - d).total_seconds(), 1)
        except Exception:
            pass

    cleaned, warnings = _validate_research_brief(brief)
    if warnings:
        log.warning("Margot brief validation warnings: %s", "; ".join(warnings))
    return cleaned


def _read_inflight_entries() -> list[dict[str, Any]]:
    """Read margot_inflight.jsonl, return list of dicts (skip malformed lines)."""
    path = _HARNESS_ROOT.parent / "swarm" / ".." / ".harness" / "swarm" / "margot_inflight.jsonl"
    # Resolve to the canonical path used by margot_tools
    path = (_HARNESS_ROOT / "swarm" / "margot_inflight.jsonl").resolve()
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except Exception as exc:
        log.warning("could not read margot_inflight.jsonl: %s", exc)
    return entries


def _write_inflight_entries(entries: list[dict[str, Any]]) -> None:
    """Atomic rewrite of the inflight log (used to mark entries 'harvested')."""
    path = (_HARNESS_ROOT / "swarm" / "margot_inflight.jsonl").resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".jsonl.tmp")
    tmp.write_text(
        "\n".join(json.dumps(e, ensure_ascii=False) for e in entries) + ("\n" if entries else ""),
        encoding="utf-8",
    )
    os.replace(tmp, path)


def _harvest_completed_margot_briefs(max_age_days: int = 32) -> list[dict[str, Any]]:
    """Scan inflight log for completed Margot board-research dispatches.

    Returns a list of normalized briefs (RA-1972 contract shape, with
    `mode: "margot"`). Marks consumed entries `status: "harvested"` and rewrites
    the inflight log atomically. Failed entries are marked
    `status: "harvested:failed"` so they're not re-checked next cycle.
    """
    if _margot_kill_switch_active():
        return []
    try:
        from swarm.margot_tools import check_research
    except ImportError:
        return []

    entries = _read_inflight_entries()
    if not entries:
        return []

    now = datetime.now(timezone.utc)
    cutoff_iso = (now - timedelta(days=max_age_days)).isoformat()
    harvested_briefs: list[dict[str, Any]] = []
    mutated = False

    for entry in entries:
        sid = entry.get("originating_session_id") or ""
        if not sid.startswith("board_meeting:"):
            continue
        if entry.get("status") not in (None, "dispatched"):
            continue  # already harvested or in some other state
        ts = entry.get("ts", "")
        if ts and ts < cutoff_iso:
            entry["status"] = "harvested:expired"
            mutated = True
            continue

        interaction_id = entry.get("interaction_id")
        if not interaction_id:
            continue
        try:
            result = check_research(interaction_id)
        except Exception as exc:
            log.warning("check_research(%s) raised: %s", interaction_id, exc)
            continue

        if not isinstance(result, dict):
            continue
        if result.get("error"):
            log.warning(
                "check_research(%s) returned error: %s",
                interaction_id, result.get("error"),
            )
            continue

        status = (result.get("status") or "").lower()
        if status in ("processing", "dispatched", "pending", "running"):
            continue  # will be harvested next cycle
        if status in ("failed", "error"):
            entry["status"] = "harvested:failed"
            mutated = True
            log.warning(
                "Margot interaction %s failed; marking inflight entry harvested:failed",
                interaction_id,
            )
            continue
        if status not in ("completed", "complete", "done", "success"):
            # Unknown status — leave entry alone, try again next cycle
            log.info("Margot interaction %s has unknown status %r — will retry", interaction_id, status)
            continue

        # Completed — normalize and mark harvested
        # The original questions aren't in the inflight log, but the topic is.
        # We treat the topic as a single-question fallback if no questions were stored.
        questions = entry.get("questions") or [entry.get("topic", "")]
        questions = [q for q in questions if q]
        brief = _normalize_margot_to_research_brief(
            result,
            questions=questions,
            dispatched_at=entry.get("ts"),
            completed_at=result.get("completed_at"),
        )
        brief["interaction_id"] = interaction_id
        harvested_briefs.append(brief)
        entry["status"] = "harvested"
        entry["harvested_at"] = now.isoformat()
        mutated = True

    if mutated:
        try:
            _write_inflight_entries(entries)
        except Exception as exc:  # pragma: no cover
            log.warning("could not rewrite margot_inflight.jsonl: %s", exc)

    return harvested_briefs


# ─────────────────────────────────────────────────────────────────────────────


def _run_fast_research(
    status: dict[str, Any],
    linear: dict[str, Any],
    *,
    timeout: int,
) -> dict[str, Any]:
    """RA-1972 fast-research path, extracted from run_board_research_phase so the
    mode dispatcher in RA-1974 can call it cleanly. Behaviourally identical to
    the prior single-mode implementation.
    """
    start = time.monotonic()

    def _empty(reason: str) -> dict[str, Any]:
        return {
            "research_required": False,
            "questions": [],
            "findings": [],
            "open_questions": [],
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "cost_seconds": round(time.monotonic() - start, 1),
            "failure_reason": reason,
            "mode": "fast",
        }

    # ── Step 1: identify empirical questions ──────────────────────────────────
    urgent_lines = "\n".join(
        f"  - {i.get('id', '?')} [{i.get('state', '?')}] {i.get('title', '')}"
        for i in status.get("urgent_issues", [])[:10]
    ) or "  None"
    zte = status.get("zte_score", "unknown")

    question_prompt = (
        "You are the Senior Project Manager preparing a CEO Board meeting. "
        "Inspect the brief below and decide whether the board needs FRESH external "
        "evidence (web search, public sources) before the personas debate.\n\n"
        "## Intelligence Brief\n"
        f"- ZTE Score: {zte}\n"
        f"- Open Urgent issues: {len(status.get('urgent_issues', []))}\n"
        f"- Open High issues: {linear.get('high_count', 0)}\n"
        f"- Stale items (>3d): {', '.join(linear.get('stale_items', [])) or 'None'}\n"
        "\n## Urgent Issues\n"
        f"{urgent_lines}\n\n"
        "## Decision\n"
        "Return a JSON object — and ONLY a JSON object, no prose — matching:\n"
        '{"questions": ["<sharp empirical question 1>", "..."]}\n\n'
        "RULES:\n"
        "- Empty list `[]` if the brief is purely internal (no competitors, vendors, "
        "regulations, public events, or factual claims that need external verification).\n"
        "- 2-5 questions otherwise. Each question is ONE sentence ending in '?'. "
        "Each must be answerable with a web source. Bad: 'research the market'. "
        'Good: "What did Anthropic ship in the last 30 days that affects the Pi-CEO orchestrator?"\n'
        "- Do NOT ask questions about internal Pi-CEO state — those are answered from priors."
    )

    try:
        q_raw = _run_prompt_via_sdk(question_prompt, timeout=60, thinking="disabled")
    except Exception as exc:  # pragma: no cover — defensive
        log.warning("Phase 2.4 question step raised: %s", exc)
        return _empty(f"question step exception: {exc}")

    q_obj = _extract_json_object(q_raw or "")
    questions = (q_obj or {}).get("questions") or []
    questions = [q for q in questions if isinstance(q, str) and q.strip()]

    if not questions:
        log.info("Phase 2.4 RESEARCH skipped — no empirical questions surfaced")
        return _empty("no empirical questions surfaced from intelligence brief")

    log.info("Phase 2.4 RESEARCH — %d question(s) to investigate", len(questions))

    # ── Step 2: dispatch research subagent ────────────────────────────────────
    questions_block = "\n".join(f"{i+1}. {q}" for i, q in enumerate(questions))
    research_prompt = (
        "You are a research analyst preparing evidence for a strategic board meeting. "
        "Investigate each question below using WebSearch and WebFetch. Return ONE JSON "
        "object — no prose, no fences — matching this schema exactly:\n\n"
        "```\n"
        "{\n"
        '  "research_required": true,\n'
        f'  "questions": {json.dumps(questions)},\n'
        '  "findings": [\n'
        '    {\n'
        '      "question": "<the question this answers>",\n'
        '      "claim": "<one or two sentences stating what you found>",\n'
        '      "confidence": "high" | "medium" | "low",\n'
        '      "sources": [\n'
        '        { "url": "<absolute url>", "title": "<page title>", "fetched": "YYYY-MM-DD", "excerpt": "<≤200 chars>" }\n'
        '      ]\n'
        '    }\n'
        '  ],\n'
        '  "open_questions": ["<questions you could not answer or could not source>"]\n'
        "}\n"
        "```\n\n"
        "## Questions\n"
        f"{questions_block}\n\n"
        "HARD RULES:\n"
        "- Every claim has at least one source with both `url` and `fetched` populated.\n"
        "- If you cannot find a citable source for a question, put the question in "
        "`open_questions` instead of inventing a finding.\n"
        "- `confidence: low` is acceptable; `confidence: high` requires a primary source "
        "(vendor docs, official announcement, regulator filing) — not a third-party blog.\n"
        "- Stop investigating once you have a finding or have exhausted reasonable searches "
        "(3 searches per question max). Time budget is tight."
    )

    research_raw = _run_research_via_sdk(research_prompt, timeout=timeout)
    if not research_raw:
        out = _empty("research subagent returned empty (timeout or SDK failure)")
        out["questions"] = questions
        out["open_questions"] = list(questions)  # personas should know what was unanswered
        return out

    brief = _extract_json_object(research_raw)
    if not isinstance(brief, dict):
        out = _empty("research subagent output was not parseable JSON")
        out["questions"] = questions
        out["open_questions"] = list(questions)
        return out

    brief.setdefault("research_required", True)
    brief.setdefault("questions", questions)
    brief.setdefault("findings", [])
    brief.setdefault("open_questions", [])
    brief["completed_at"] = datetime.now(timezone.utc).isoformat()
    brief["cost_seconds"] = round(time.monotonic() - start, 1)
    brief["failure_reason"] = None
    brief["mode"] = "fast"

    cleaned, warnings = _validate_research_brief(brief)
    if warnings:
        log.warning("Phase 2.4 validation warnings: %s", "; ".join(warnings))

    log.info(
        "Phase 2.4 RESEARCH (fast) complete: %d findings, %d open_questions, %.1fs",
        len(cleaned.get("findings", [])),
        len(cleaned.get("open_questions", [])),
        cleaned["cost_seconds"],
    )
    return cleaned


def run_board_research_phase(
    status: dict[str, Any],
    linear: dict[str, Any],
    *,
    timeout: int = 180,
    cycle: int = 0,
    mode: str | None = None,
) -> dict[str, Any]:
    """Phase 2.4 — RESEARCH BRIEF orchestrator (RA-1972 + RA-1974).

    Dispatches to one of three modes:
      * fast   (default) — RA-1972 path: 180s WebSearch + WebFetch subagent
      * hybrid           — fast this cycle + dispatch Margot for next cycle
      * deep             — Margot only; this cycle has no fresh research

    On every call: harvest any completed prior-cycle Margot dispatches from
    `.harness/swarm/margot_inflight.jsonl` and prepend them as
    `prior_deep_research`. This is the async-pickup half of the two-cycle pattern.

    Always returns a dict matching the RA-1972 contract (research_required,
    questions, findings, open_questions, completed_at, cost_seconds,
    failure_reason) plus optional `mode` and `prior_deep_research` fields.
    Persisted to `.harness/board-meetings/{date}-research.json`.
    """
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    resolved_mode = (mode or _resolve_board_research_mode()).lower()
    if resolved_mode not in _VALID_RESEARCH_MODES:
        log.warning("Invalid mode %r passed to run_board_research_phase — defaulting to fast", mode)
        resolved_mode = "fast"

    log.info("Phase 2.4 RESEARCH start: mode=%s cycle=%s", resolved_mode, cycle)

    # ── Harvest prior-cycle Margot dispatches ─────────────────────────────────
    prior_deep = _harvest_completed_margot_briefs()
    if prior_deep:
        log.info(
            "Phase 2.4 harvested %d prior-cycle Margot brief(s): interaction_ids=%s",
            len(prior_deep),
            [p.get("interaction_id", "?") for p in prior_deep],
        )

    # ── Run the current cycle's research per mode ─────────────────────────────
    if resolved_mode == "deep":
        # Skip fast research entirely. Dispatch Margot for next cycle.
        topic = _build_margot_topic(status, linear)
        dispatch = _dispatch_margot_for_next_cycle(topic, cycle=cycle, date_str=today)
        current = {
            "research_required": False,
            "mode": "deep",
            "questions": [],
            "findings": [],
            "open_questions": [],
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "cost_seconds": 0.0,
            "failure_reason": (
                f"deep mode — Margot dispatched ({dispatch.get('interaction_id')}), will harvest next cycle"
                if dispatch else
                "deep mode — Margot dispatch failed (kill switch active or Margot unreachable)"
            ),
            "pending_interaction_id": dispatch.get("interaction_id") if dispatch else None,
        }
    else:
        # fast or hybrid — both run fast synchronously
        current = _run_fast_research(status, linear, timeout=timeout)
        if resolved_mode == "hybrid":
            topic = _build_margot_topic(status, linear)
            dispatch = _dispatch_margot_for_next_cycle(topic, cycle=cycle, date_str=today)
            current["mode"] = "hybrid"
            current["next_cycle_dispatch"] = (
                dispatch.get("interaction_id") if dispatch else None
            )

    # Attach harvested briefs (if any)
    if prior_deep:
        current["prior_deep_research"] = prior_deep

    _persist_research_brief(current, today)
    return current


def _build_margot_topic(status: dict[str, Any], linear: dict[str, Any]) -> str:
    """Compose a Margot research brief from the autonomous board's intelligence
    payload. Margot expects a free-text research brief, not a question list."""
    urgent_titles = "; ".join(
        i.get("title", "") for i in status.get("urgent_issues", [])[:8]
    ) or "none"
    return (
        "Strategic intelligence brief for the Pi-CEO autonomous board meeting. "
        f"ZTE score: {status.get('zte_score', 'unknown')}. "
        f"Open Urgent issues ({len(status.get('urgent_issues', []))}): {urgent_titles}. "
        f"Open High issues: {linear.get('high_count', 0)}. "
        f"Stale items: {', '.join(linear.get('stale_items', [])) or 'none'}. "
        "Research the external context the board needs to deliberate effectively: "
        "competitor moves, regulatory changes, vendor announcements, market signals "
        "relevant to the open issues above. Focus on facts the board cannot derive "
        "from internal Pi-CEO state. Cite sources."
    )


def _persist_research_brief(brief: dict[str, Any], date_str: str) -> None:
    """Write the research brief to .harness/board-meetings/{date}-research.json.
    Atomic write via .tmp + os.replace per CLAUDE.md persistence convention.
    """
    try:
        out_dir = _HARNESS_ROOT / "board-meetings"
        out_dir.mkdir(parents=True, exist_ok=True)
        out_path = out_dir / f"{date_str}-research.json"
        tmp_path = out_path.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(brief, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp_path, out_path)
    except Exception as exc:  # pragma: no cover — disk failures shouldn't break debate
        log.warning("could not persist research brief: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────


def run_persona_debate_phase(
    system_prompt: str,
    status: dict[str, Any],
    linear: dict[str, Any],
    research: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Phase 2.5 — PERSONA DEBATE (RA-686): 9 CEO Board personas deliberate on the intelligence brief.

    A single SDK/API call generates all 9 persona responses in one structured document.
    The synthesis is then passed to Phase 3 (SWOT) as additional context.

    RA-1972 — `research` is the optional Phase 2.4 output. When present and
    `research_required: true`, the research brief is injected verbatim into the
    user_content and personas are required to cite findings by question number.
    """
    urgent_issues = "\n".join(
        f"  - {i['id']} [{i['state']}] {i['title']}"
        for i in status.get("urgent_issues", [])[:10]
    ) or "  None"

    zte = status.get("zte_score", "unknown")
    zte_v2 = status.get("zte_v2", {})
    v2_line = (
        f"- ZTE v2: {zte_v2['total']}/{zte_v2['max']} [{zte_v2['band']}]\n"
        if zte_v2 else ""
    )

    personas_block = "\n\n".join(
        f"**{name}**: {desc}"
        for name, desc in CEO_BOARD_PERSONAS.items()
    )

    research_block = _format_research_brief_for_personas(research) if research else ""
    research_required = bool(research and research.get("research_required"))
    citation_rule = (
        "Each persona MUST cite at least one Research Brief finding by `#N` when "
        "their position depends on a fact. The Contrarian MUST flag at least one "
        "claim with `confidence: low` or one entry in `open_questions`.\n"
    ) if research_required else ""

    user_content = (
        "Run Phase 2.5 — CEO BOARD PERSONA DEBATE.\n\n"
        "## Intelligence Brief\n"
        f"- ZTE Score (v1): {zte}\n"
        + v2_line
        + f"- Open Urgent issues: {len(status.get('urgent_issues', []))}\n"
        f"- Open High issues: {linear.get('high_count', 0)}\n"
        f"- Stale items (>3d): {', '.join(linear.get('stale_items', [])) or 'None'}\n\n"
        "## Open Urgent Issues\n"
        + urgent_issues
        + research_block
        + "\n\n## Board Personas\n\n"
        + personas_block
        + "\n\n## Instructions\n"
        "Each persona gives their single most important observation or challenge in 2–3 sentences.\n"
        "The Contrarian MUST challenge at least one recommendation from another persona by name.\n"
        + citation_rule
        + "End with a CEO SYNTHESIS (3 sentences): the highest-signal insight from the debate.\n\n"
        "Format strictly as:\n"
        "**CEO:** [2–3 sentences]\n"
        "**Revenue:** [2–3 sentences]\n"
        "**Product Strategist:** [2–3 sentences]\n"
        "**Technical Architect:** [2–3 sentences]\n"
        "**Contrarian:** [2–3 sentences — must name and challenge a specific persona's view]\n"
        "**Compounder:** [2–3 sentences]\n"
        "**Custom Oracle:** [2–3 sentences]\n"
        "**Market Strategist:** [2–3 sentences]\n"
        "**Moonshot:** [2–3 sentences]\n\n"
        "**CEO SYNTHESIS:** [3 sentences integrating the debate into one actionable conclusion]"
    )

    raw = _run_prompt_with_cache(system_text=system_prompt, user_content=user_content, timeout=120)
    if not raw:
        raw = _run_prompt_via_sdk(user_content, timeout=120, thinking="adaptive")

    log.info(
        "Phase 2.5 PERSONA DEBATE complete (%d chars, research_injected=%s)",
        len(raw),
        research_required,
    )
    return {
        "phase": "persona_debate",
        "content": raw,
        "research_injected": research_required,
    }


# ── RA-696: Business Velocity Index ──────────────────────────────────────────

_BVI_HISTORY_FILE = _HARNESS_ROOT / "bvi-history.jsonl"


def _load_prior_bvi() -> dict[str, Any] | None:
    """Return the most recent BVI entry from bvi-history.jsonl, or None."""
    if not _BVI_HISTORY_FILE.exists():
        return None
    entries = []
    for line in _BVI_HISTORY_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return entries[-1] if entries else None


def _count_criticals_resolved(since_iso: str | None = None) -> int:
    """Count Urgent Linear issues moved to Done since the last board meeting."""
    api_key = os.environ.get("LINEAR_API_KEY", "")
    if not api_key:
        return 0
    try:
        filter_extra = ""
        if since_iso:
            filter_extra = f', updatedAt: {{gt: "{since_iso}"}}'
        data = _linear_gql(
            f"""
            query CriticalsDone($teamId: ID!) {{
              issues(filter: {{
                team: {{id: {{eq: $teamId}}}},
                priority: {{eq: 1}},
                state: {{type: {{eq: "completed"}}}}{filter_extra}
              }}, first: 50) {{
                nodes {{ identifier }}
              }}
            }}
            """,
            {"teamId": _LINEAR_TEAM_ID},
        )
        return len(data.get("issues", {}).get("nodes", []))
    except Exception as exc:
        log.warning("BVI criticals_resolved query failed: %s", exc)
        return 0


def _count_portfolio_improved() -> int:
    """
    Count portfolio projects with a positive health delta since last scan.
    Reads scan JSON files from .harness/projects/*/health-score.json
    (or infers from latest scan runs).
    """
    projects_dir = _HARNESS_ROOT / "projects"
    if not projects_dir.exists():
        return 0
    improved = 0
    for project_dir in projects_dir.iterdir():
        if not project_dir.is_dir():
            continue
        score_file = project_dir / "health-score.json"
        if not score_file.exists():
            continue
        try:
            data = json.loads(score_file.read_text(encoding="utf-8"))
            delta = data.get("delta", 0)
            if isinstance(delta, (int, float)) and delta > 0:
                improved += 1
        except Exception:
            pass
    return improved


def _count_marathon_completions() -> int:
    """
    Count shipped features with positive outcome signal (RA-689 feedback loop).
    This is the "features delivered to real users" BVI component.
    """
    try:
        from .feedback_loop import get_feedback_summary as _get_fb
        fb = _get_fb()
        return fb.get("positive", 0) if fb.get("available") else 0
    except Exception:
        return 0


def compute_bvi(cycle: int) -> dict[str, Any]:
    """
    Compute the Business Velocity Index for the current board meeting cycle.
    Returns a BVI entry dict ready to append to bvi-history.jsonl.
    """
    prior = _load_prior_bvi()
    prior_date = prior.get("date") if prior else None

    criticals = _count_criticals_resolved(since_iso=prior_date)
    portfolio = _count_portfolio_improved()
    marathon = _count_marathon_completions()

    # BVI = sum of all three components (equal weight; can be weighted in future)
    bvi_score = criticals + portfolio + marathon

    # RA-1419 — guard against None priors (first cycle, or history written before bvi_score was tracked)
    prior_score = (prior.get("bvi_score") if prior else None) or 0
    delta = bvi_score - prior_score

    entry: dict[str, Any] = {
        "cycle": cycle,
        "date": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "criticals_resolved": criticals,
        "portfolio_projects_improved": portfolio,
        "marathon_completions": marathon,
        "bvi_score": bvi_score,
        "prior_bvi_score": prior_score,
        "delta": delta,
        "notes": "",
    }
    log.info(
        "BVI computed: cycle=%d score=%d (criticals=%d portfolio=%d marathon=%d delta=%+d)",
        cycle, bvi_score, criticals, portfolio, marathon, delta,
    )
    return entry


def record_bvi_entry(entry: dict[str, Any]) -> None:
    """Append a BVI entry to .harness/bvi-history.jsonl (atomic write)."""
    tmp = _BVI_HISTORY_FILE.with_suffix(".tmp")
    existing = ""
    if _BVI_HISTORY_FILE.exists():
        existing = _BVI_HISTORY_FILE.read_text(encoding="utf-8")
    try:
        tmp.write_text(existing + json.dumps(entry) + "\n", encoding="utf-8")
        tmp.replace(_BVI_HISTORY_FILE)
        log.info("BVI entry recorded: cycle=%d score=%d", entry.get("cycle", 0), entry.get("bvi_score", 0))
    except OSError as exc:
        log.warning("Could not write BVI entry: %s", exc)


# ── RA-658: Board Meeting Phases 1–5 ─────────────────────────────────────────

def run_status_phase() -> dict[str, Any]:
    """Phase 1 — STATUS: snapshot ZTE score, cron health, open Urgent issues."""
    status: dict[str, Any] = {"phase": "status", "timestamp": datetime.now(timezone.utc).isoformat()}

    # ZTE score from leverage-audit.md
    leverage_path = _HARNESS_ROOT / "leverage-audit.md"
    if leverage_path.exists():
        content = leverage_path.read_text(encoding="utf-8")[:500]
        match = re.search(r"(?:Score|ZTE)[^\d]*(\d+)\s*/\s*(\d+)", content, re.IGNORECASE)
        if match:
            status["zte_score"] = f"{match.group(1)}/{match.group(2)}"

    # Marathon watchdog health
    watchdog_path = _HARNESS_ROOT / "marathon-watchdog-status.json"
    if watchdog_path.exists():
        try:
            w = json.loads(watchdog_path.read_text(encoding="utf-8"))
            status["cron_health"] = {
                "last_run": w.get("last_run"),
                "status": w.get("status", "unknown"),
                "missed_cycles": w.get("missed_cycles", 0),
            }
        except Exception:
            status["cron_health"] = "parse error"

    # Open Urgent issues from Linear
    try:
        data = _linear_gql(
            """
            query UrgentIssues($teamId: ID!) {
              issues(filter: {
                team: {id: {eq: $teamId}},
                priority: {eq: 1},
                state: {type: {nin: ["completed", "cancelled"]}}
              }, first: 10) {
                nodes { identifier title state { name } }
              }
            }
            """,
            {"teamId": _LINEAR_TEAM_ID},
        )
        status["urgent_issues"] = [
            {"id": n["identifier"], "title": n["title"], "state": n["state"]["name"]}
            for n in data.get("issues", {}).get("nodes", [])
        ]
    except Exception as exc:
        log.warning("Phase 1 Linear query failed: %s", exc)
        status["urgent_issues"] = []

    # ZTE v2 score (RA-672) — compute from live gate_checks + scanner + lessons
    try:
        import sys as _sys
        _scripts_dir = str(_HARNESS_ROOT.parent / "scripts")
        if _scripts_dir not in _sys.path:
            _sys.path.insert(0, _scripts_dir)
        from zte_v2_score import compute_v2_score  # type: ignore[import]
        v2 = compute_v2_score(days=30)
        status["zte_v2"] = {
            "total": v2["v2_total"],
            "max": v2["v2_max"],
            "band": v2["band"],
            "section_c": v2["section_c"]["total"],
            "v1_base": v2["v1_score"],
        }
        log.info("Phase 1 ZTE v2: %d/%d [%s]", v2["v2_total"], v2["v2_max"], v2["band"])
    except Exception as exc:
        log.warning("ZTE v2 score compute failed (non-fatal): %s", exc)

    # RA-696 — BVI: prior cycle summary for delta display
    try:
        prior_bvi = _load_prior_bvi()
        if prior_bvi:
            status["bvi_prior"] = {
                "cycle": prior_bvi.get("cycle"),
                "score": prior_bvi.get("bvi_score", 0),
                "criticals_resolved": prior_bvi.get("criticals_resolved", 0),
                "portfolio_improved": prior_bvi.get("portfolio_projects_improved", 0),
                "marathon_completions": prior_bvi.get("marathon_completions", 0),
            }
        log.info("Phase 1 BVI prior: %s", status.get("bvi_prior", "baseline (no history)"))
    except Exception as exc:
        log.warning("Phase 1 BVI prior load failed (non-fatal): %s", exc)

    # RA-689 — Shipped features performance (outcome feedback loop)
    try:
        from .feedback_loop import get_feedback_summary as _get_feedback_summary
        fb = _get_feedback_summary()
        if fb.get("available"):
            status["shipped_features"] = {
                "total": fb.get("total_shipped", 0),
                "positive": fb.get("positive", 0),
                "negative": fb.get("negative", 0),
                "stale": fb.get("stale", 0),
                "pending_signal": fb.get("pending_signal", 0),
            }
        log.info("Phase 1 shipped features: %s", status.get("shipped_features", "unavailable"))
    except Exception as exc:
        log.warning("Phase 1 feedback summary failed (non-fatal): %s", exc)

    log.info("Phase 1 STATUS: zte=%s urgent=%d",
             status.get("zte_score", "?"), len(status.get("urgent_issues", [])))
    return status


def run_linear_review_phase() -> dict[str, Any]:
    """Phase 2 — LINEAR REVIEW: fetch open Urgent + High issues, surface stale/blocked items."""
    review: dict[str, Any] = {"phase": "linear_review"}
    try:
        data = _linear_gql(
            """
            query OpenIssues($teamId: ID!) {
              issues(filter: {
                team: {id: {eq: $teamId}},
                priority: {in: [1, 2]},
                state: {type: {nin: ["completed", "cancelled"]}}
              }, first: 30, orderBy: updatedAt) {
                nodes {
                  identifier title priority
                  state { name type }
                  assignee { name }
                  updatedAt
                }
              }
            }
            """,
            {"teamId": _LINEAR_TEAM_ID},
        )
        nodes = data.get("issues", {}).get("nodes", [])
        review["issues"] = nodes
        review["urgent_count"] = sum(1 for n in nodes if n.get("priority") == 1)
        review["high_count"] = sum(1 for n in nodes if n.get("priority") == 2)
        review["unassigned"] = [n["identifier"] for n in nodes if not n.get("assignee")]

        now = datetime.now(timezone.utc)
        stale: list[str] = []
        for n in nodes:
            updated = n.get("updatedAt", "")
            if updated:
                try:
                    updated_dt = datetime.fromisoformat(updated.replace("Z", "+00:00"))
                    if (now - updated_dt).days > 3:
                        stale.append(f"{n['identifier']} ({(now - updated_dt).days}d stale)")
                except Exception:
                    pass
        review["stale_items"] = stale
    except Exception as exc:
        log.warning("Phase 2 Linear review failed: %s", exc)
        review["issues"] = []
        review["error"] = str(exc)

    log.info("Phase 2 LINEAR REVIEW: urgent=%d high=%d stale=%d",
             review.get("urgent_count", 0), review.get("high_count", 0),
             len(review.get("stale_items", [])))
    return review


def run_swot_phase(
    system_prompt: str,
    status: dict[str, Any],
    linear: dict[str, Any],
    persona_debate: dict[str, Any] | None = None,
    bvi: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Phase 3 — SWOT: analysis informed by lessons.jsonl + live board context + persona debate + BVI."""
    lessons = _read_lessons(n=20)
    urgent_issues = status.get("urgent_issues", [])
    stale = linear.get("stale_items", [])
    unassigned = linear.get("unassigned", [])

    v2 = status.get("zte_v2", {})
    v2_line = (
        f"- ZTE Score (v2): {v2['total']}/{v2['max']} [{v2['band']}]\n"
        if v2 else ""
    )

    # RA-696 — BVI trend context for SWOT
    bvi_line = ""
    if bvi:
        bvi_score = bvi.get("bvi_score", 0)
        bvi_delta = bvi.get("delta", 0)
        bvi_delta_str = f"+{bvi_delta}" if bvi_delta > 0 else str(bvi_delta)
        bvi_line = (
            f"- BVI (Business Velocity Index): {bvi_score} ({bvi_delta_str} from prior cycle)\n"
            f"  CRITICALs resolved: {bvi.get('criticals_resolved', 0)} | "
            f"Portfolio improved: {bvi.get('portfolio_projects_improved', 0)} | "
            f"MARATHON completions: {bvi.get('marathon_completions', 0)}\n"
        )

    state_section = (
        "## Current State\n"
        f"- ZTE Score (v1): {status.get('zte_score', 'unknown')}\n"
        + v2_line
        + bvi_line
        + f"- Open Urgent issues: {len(urgent_issues)}\n"
        + f"- Open High issues: {linear.get('high_count', 0)}\n"
        + f"- Stale items (>3d unchanged): {', '.join(stale) or 'None'}\n"
        + f"- Unassigned issues: {', '.join(unassigned) or 'None'}\n"
    )

    # RA-686 — inject persona debate synthesis if available
    persona_section = ""
    if persona_debate and persona_debate.get("content"):
        synthesis_match = persona_debate["content"].split("**CEO SYNTHESIS:**")
        synthesis = synthesis_match[-1].strip()[:500] if len(synthesis_match) > 1 else ""
        if synthesis:
            persona_section = f"\n\n## CEO Board Synthesis (from Persona Debate)\n{synthesis}"

    user_content = (
        "Run Phase 3 — SWOT ANALYSIS.\n\n"
        + state_section
        + persona_section
        + lessons
        + "\n\n## Instructions\n"
        "Produce a concise SWOT for Pi-CEO based on the above data, persona synthesis, and lessons.\n"
        "Format:\nSTRENGTHS: (3–5 bullets)\nWEAKNESSES: (3–5 bullets)\n"
        "OPPORTUNITIES: (3–5 bullets)\nTHREATS: (3–5 bullets)\n"
        "Reference specific lesson entries and persona debate points where relevant. No filler language."
    )
    raw = _run_prompt_with_cache(system_text=system_prompt, user_content=user_content, timeout=90)
    if not raw:
        # RA-659: SWOT benefits from deep reasoning — use enabled thinking with 8k budget
        raw = _run_prompt_via_sdk(user_content, timeout=90, thinking="enabled")

    log.info("Phase 3 SWOT complete (%d chars)", len(raw))
    return {"phase": "swot", "content": raw}


def run_sprint_recommendations_phase(
    system_prompt: str,
    swot: dict[str, Any],
    linear: dict[str, Any],
) -> dict[str, Any]:
    """Phase 4 — SPRINT RECOMMENDATIONS: top 3 actionable items with estimates."""
    issue_list = "\n".join(
        f"- {n['identifier']} [{n['state']['name']}] {n['title']}"
        for n in linear.get("issues", [])[:20]
    )
    user_content = (
        "Run Phase 4 — SPRINT RECOMMENDATIONS.\n\n"
        "## SWOT Summary\n"
        + swot.get("content", "(SWOT not available)")[:2000]
        + "\n\n## Open Urgent/High Issues\n"
        + (issue_list or "(no open issues)")
        + "\n\n## Instructions\n"
        "Recommend exactly 3 sprint priorities. For each:\n"
        "1. Reference the specific Linear ticket ID (RA-xxx) if one exists, or propose a title\n"
        "2. One-sentence rationale\n"
        "3. Estimate: XS (<1h) | S (1–2h) | M (2–4h) | L (4–8h) | XL (>8h)\n"
        "4. Expected impact on ZTE score or operational health\n\n"
        "Format:\n"
        "PRIORITY 1: [ticket] — [rationale] — Estimate: [size] — Impact: [impact]\n"
        "PRIORITY 2: ...\nPRIORITY 3: ..."
    )
    raw = _run_prompt_with_cache(system_text=system_prompt, user_content=user_content, timeout=90)
    if not raw:
        # RA-659: Sprint recommendations require trade-off reasoning — use enabled thinking
        raw = _run_prompt_via_sdk(user_content, timeout=90, thinking="enabled")

    log.info("Phase 4 SPRINT RECOMMENDATIONS complete (%d chars)", len(raw))
    return {"phase": "sprint_recommendations", "content": raw}


def save_board_minutes(
    cycle: int,
    status: dict[str, Any],
    linear: dict[str, Any],
    swot: dict[str, Any],
    recommendations: dict[str, Any],
    gap_audit: dict[str, Any],
    persona_debate: dict[str, Any] | None = None,
    bvi: dict[str, Any] | None = None,
    research: dict[str, Any] | None = None,
) -> Path:
    """Phase 5 — SAVE MINUTES: write full board minutes to .harness/board-meetings/."""
    board_dir = _HARNESS_ROOT / "board-meetings"
    board_dir.mkdir(parents=True, exist_ok=True)

    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = board_dir / f"{date_str}-board-minutes.md"

    audit_summary = gap_audit.get("summary", {})
    cron = status.get("cron_health", {})
    cron_status = cron.get("status", "unknown") if isinstance(cron, dict) else str(cron)

    # RA-1972 — Phase 2.4 research brief (if any)
    research_section = (
        [
            "",
            "## Phase 2.4 — RESEARCH BRIEF (RA-1972)",
            _format_research_brief_for_personas(research).lstrip("\n").replace(
                "## RESEARCH BRIEF (Phase 2.4)\n", "", 1
            ).lstrip(),
        ]
        if research else []
    )

    persona_section = (
        ["", "## Phase 2.5 — CEO BOARD PERSONA DEBATE (RA-686)", persona_debate.get("content", "(not available)")]
        if persona_debate else []
    )

    # BVI headline section
    bvi_score = bvi.get("bvi_score", 0) if bvi else 0
    bvi_delta = bvi.get("delta", 0) if bvi else 0
    bvi_delta_str = f"+{bvi_delta}" if bvi_delta > 0 else str(bvi_delta)
    bvi_section = (
        [
            "",
            "## Business Velocity Index (RA-696)",
            f"**BVI: {bvi_score}** ({bvi_delta_str} from prior cycle)",
            f"- CRITICALs resolved: {bvi.get('criticals_resolved', 0)}",
            f"- Portfolio projects improved: {bvi.get('portfolio_projects_improved', 0)}",
            f"- MARATHON completions (positive outcomes): {bvi.get('marathon_completions', 0)}",
            f"- Prior cycle BVI: {bvi.get('prior_bvi_score', 'baseline (first cycle)')}",
        ]
        if bvi else [
            "",
            "## Business Velocity Index (RA-696)",
            "BVI: not computed (first cycle or dry-run)",
        ]
    )

    content = "\n".join([
        f"# Board Meeting Minutes — Cycle {cycle} ({date_str})",
        *bvi_section,
        "",
        "## Attendees",
        "- Pi CEO Autonomous Agent (Orchestrator)",
        "- CEO Board: 9 personas (CEO, Revenue, Product Strategist, Technical Architect,",
        "  Contrarian, Compounder, Custom Oracle, Market Strategist, Moonshot)",
        "- Gap Audit Agent",
        "",
        "## Phase 1 — STATUS",
        f"- ZTE Score (v1): {status.get('zte_score', 'unknown')}",
        *(
            [f"- ZTE Score (v2): {status['zte_v2']['total']}/{status['zte_v2']['max']} [{status['zte_v2']['band']}] (v1 base {status['zte_v2']['v1_base']} + Section C {status['zte_v2']['section_c']}/25)"]
            if "zte_v2" in status else []
        ),
        f"- Urgent Issues: {len(status.get('urgent_issues', []))}",
        f"- Cron Health: {cron_status}",
        *(
            [
                "",
                "### Shipped Features Performance (RA-689)",
                f"- Total shipped: {status['shipped_features']['total']}",
                f"- Positive outcomes: {status['shipped_features']['positive']}",
                f"- Negative outcomes: {status['shipped_features']['negative']}",
                f"- Stale (>30 days, no signal): {status['shipped_features']['stale']}",
                f"- Pending signal: {status['shipped_features']['pending_signal']}",
            ]
            if "shipped_features" in status else []
        ),
        "",
        "## Phase 2 — LINEAR REVIEW",
        f"- Urgent: {linear.get('urgent_count', 0)} | High: {linear.get('high_count', 0)}",
        f"- Stale: {', '.join(linear.get('stale_items', [])) or 'None'}",
        f"- Unassigned: {', '.join(linear.get('unassigned', [])) or 'None'}",
        *research_section,
        *persona_section,
        "",
        "## Phase 3 — SWOT",
        swot.get("content", "(not available)"),
        "",
        "## Phase 4 — SPRINT RECOMMENDATIONS",
        recommendations.get("content", "(not available)"),
        "",
        "## Phase 6 — GAP AUDIT SUMMARY",
        f"- Critical: {audit_summary.get('critical_count', 0)}",
        f"- High: {audit_summary.get('high_count', 0)}",
        f"- Low: {audit_summary.get('low_count', 0)}",
        f"- Tickets created: {', '.join(audit_summary.get('linear_tickets_created', [])) or 'None'}",
        "",
        f"_Generated {datetime.now(timezone.utc).isoformat()}_",
    ])

    out_path.write_text(content, encoding="utf-8")
    log.info("Board minutes saved to %s", out_path)
    return out_path


def run_full_board_meeting(dry_run: bool = False, cycle: int = 0) -> dict[str, Any]:
    """Run all 7 board meeting phases in sequence and save minutes.

    Phase 1   — STATUS (data only)
    Phase 2   — LINEAR REVIEW (data only)
    Phase 2.5 — PERSONA DEBATE — RA-686 (9 CEO Board personas deliberate)
    Phase 3   — SWOT (Claude + lessons.jsonl + persona synthesis)
    Phase 4   — SPRINT RECOMMENDATIONS (Claude)
    Phase 5   — SAVE MINUTES (disk write)
    Phase 6   — GAP AUDIT (Claude × N categories → Linear tickets)
    """
    log.info("=== FULL BOARD MEETING START (cycle=%d dry_run=%s) ===", cycle, dry_run)
    start = time.monotonic()

    system_prompt = build_board_system_prompt()

    status = run_status_phase()
    linear = run_linear_review_phase()
    research = run_board_research_phase(status, linear, cycle=cycle)
    persona_debate = run_persona_debate_phase(system_prompt, status, linear, research=research)
    bvi = compute_bvi(cycle)
    swot = run_swot_phase(system_prompt, status, linear, persona_debate=persona_debate, bvi=bvi)
    recommendations = run_sprint_recommendations_phase(system_prompt, swot, linear)
    gap_audit = run_gap_audit_phase(dry_run=dry_run)

    if not dry_run:
        minutes_path = save_board_minutes(
            cycle, status, linear, swot, recommendations, gap_audit,
            persona_debate=persona_debate,
            bvi=bvi,
            research=research,
        )
        gap_audit["minutes_path"] = str(minutes_path)
        record_bvi_entry(bvi)

    duration = round(time.monotonic() - start, 1)
    log.info("=== FULL BOARD MEETING COMPLETE in %.1fs BVI=%d ===", duration, bvi.get("bvi_score", 0))
    return {
        "status": status,
        "linear_review": linear,
        "research": research,
        "persona_debate": persona_debate,
        "swot": swot,
        "sprint_recommendations": recommendations,
        "gap_audit": gap_audit,
        "bvi": bvi,
        "duration_s": duration,
    }


def main() -> None:
    """CLI entry point — run the gap audit."""
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(description="Run Pi-CEO board meeting")
    parser.add_argument("--dry-run", action="store_true", help="Skip Linear ticket creation and minutes write")
    parser.add_argument("--cycle", type=int, default=0, help="Board cycle number for minutes filename")
    parser.add_argument("--full", action="store_true", help="Run all 6 phases (default: gap audit only)")
    args = parser.parse_args()

    if args.full:
        result = run_full_board_meeting(dry_run=args.dry_run, cycle=args.cycle)
        log.info("%s", json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        audit = run_gap_audit_phase(dry_run=args.dry_run)
        log.info("%s", json.dumps(audit, indent=2, ensure_ascii=False))
        for sev in ("critical", "high"):
            for item in audit.get(sev, []):
                log.info("[%s] %s — %s", sev.upper(), item.get("category"), item.get("recommendation"))


if __name__ == "__main__":
    main()
