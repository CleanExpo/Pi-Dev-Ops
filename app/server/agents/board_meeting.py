"""
board_meeting.py — Board Meeting Gap Audit

Compares the Pi-CEO spec against actual source code and raises Linear tickets
for any discrepancies found. Uses claude_agent_sdk (TAO_USE_AGENT_SDK=1) or
falls back to the claude CLI subprocess.

Usage:
    python -m app.server.agents.board_meeting [--dry-run] [--cycle N]
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import subprocess
import time
import urllib.request
from datetime import datetime, timezone
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


# ── Gap audit constants ───────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parents[3]  # Pi-Dev-Ops/
_HARNESS_ROOT = _REPO_ROOT / ".harness"
_LINEAR_API_URL = "https://api.linear.app/graphql"
_LINEAR_TEAM_ID = "a8a52f07-63cf-4ece-9ad2-3e3bd3c15673"
_LINEAR_PROJECT_ID = "f45212be-3259-4bfb-89b1-54c122c939a7"

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

def _run_prompt_via_sdk(prompt: str, model: str = "claude-sonnet-4-6", timeout: int = 120) -> str:
    """Run a single-shot prompt via claude_agent_sdk and return the text response.

    Falls back silently to empty string on any SDK error so the caller can
    fall through to the subprocess path.
    """
    try:
        from claude_agent_sdk import AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, ResultMessage, TextBlock
    except ImportError:
        log.warning("claude_agent_sdk not installed — falling back to subprocess")
        return ""

    async def _run() -> str:
        options = ClaudeAgentOptions(model=model, max_turns=1)
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


# ── Claude CLI call ───────────────────────────────────────────────────────────

def _call_claude_for_discrepancies(
    spec_claims: list[str],
    audit_target: dict[str, Any],
    file_contents: dict[str, str],
) -> list[dict[str, Any]]:
    """Call the claude CLI to compare spec claims against actual source files.

    Returns a list of discrepancy dicts: {severity, claim, reality, file, recommendation}.
    """
    claims_block = "\n".join(f"- {c}" for c in spec_claims[:40])
    files_block = "\n\n".join(
        f"=== FILE: {path} ===\n{content[:6000]}"
        for path, content in file_contents.items()
    )

    prompt = f"""You are auditing a project spec against actual source code.

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

    use_sdk = os.environ.get("TAO_USE_AGENT_SDK", "0") == "1"
    raw = ""
    if use_sdk:
        raw = _run_prompt_via_sdk(prompt, model="claude-sonnet-4-6", timeout=120)
        if not raw:
            log.info("SDK returned empty — retrying via subprocess for category=%s", audit_target["category"])

    if not raw:
        cmd = [config.CLAUDE_CMD, *config.CLAUDE_EXTRA_FLAGS, "-p", prompt,
               "--output-format", "text", "--model", "claude-sonnet-4-6"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,
        )
        raw = result.stdout.strip()

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

def run_gap_audit_phase(dry_run: bool = False) -> dict[str, Any]:
    """Phase 6 — LIVE CODE GAP AUDIT.

    1. Reads spec.md for capability claims.
    2. For each audit target, reads the relevant source files.
    3. Calls claude CLI to compare claims vs code.
    4. Buckets discrepancies into critical / high / low.
    5. Auto-creates Linear tickets for critical and high gaps.
    6. Saves output to .harness/board-meetings/{date}-gap-audit.json.

    Returns the structured audit result dict.
    """
    log.info("Starting Phase 6 — LIVE CODE GAP AUDIT")
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
            items = _call_claude_for_discrepancies(spec_claims, target, file_contents)
            log.info("category=%s discrepancies=%d", target["category"], len(items))
            all_discrepancies.extend(items)
        except subprocess.TimeoutExpired:
            log.warning("claude CLI timed out for category=%s", target["category"])
        except FileNotFoundError:
            log.error("claude CLI not found — is it on PATH?")
            break
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


def main() -> None:
    """CLI entry point — run the gap audit."""
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    parser = argparse.ArgumentParser(description="Run Pi-CEO board meeting gap audit")
    parser.add_argument("--dry-run", action="store_true", help="Skip Linear ticket creation")
    parser.add_argument("--cycle", type=int, help="Override cycle number (unused, reserved)")
    args = parser.parse_args()

    audit = run_gap_audit_phase(dry_run=args.dry_run)
    print(json.dumps(audit, indent=2, ensure_ascii=False))
    audit.get("summary", {})
    for sev in ("critical", "high"):
        for item in audit.get(sev, []):
            log.info("[%s] %s — %s", sev.upper(), item.get("category"), item.get("recommendation"))


if __name__ == "__main__":
    main()
