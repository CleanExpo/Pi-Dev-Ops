# Plaud Actions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship sub-project 2 of 3 — extend the 5-min Plaud cron with LLM-driven action extraction that files Linear tickets in the right portfolio project, and posts ONE Telegram digest per cron batch.

**Architecture:** Inline extension to `scripts/plaud_ingest.py`. New module `scripts/plaud_actions.py` does Anthropic Haiku 4.5 HTTPS call → portfolio routing via `.harness/projects.json` → Linear ticket creation via extracted `scripts/linear_helpers.py` → atomic wiki frontmatter rewrite. Single substrate, single cron, single state file. Source of truth: `docs/superpowers/specs/2026-05-17-plaud-actions-design.md`.

**Tech Stack:** Python 3.11+, `urllib.request` (no new deps — Anthropic + Linear both spoken in HTTP+JSON), `pytest` (already configured), existing `notify_margot` for digest delivery, macOS `launchd` (already running).

**Plan deviation from spec:** Partial-retry behaviour simplified. Spec said "next tick re-runs only the missing actions" but that requires fuzzy title matching (LLM non-deterministic). Implementation marks `action_status: partial` and stops. User can clear `tickets:` from frontmatter to retry the recording entirely. Will note in spec follow-up.

**File map:**

| File | Status | Purpose |
|---|---|---|
| `scripts/linear_helpers.py` | NEW (~70 lines) | Generalised `create_linear_issue(api_key, title, description, team_id, project_id, priority)` — extracted from `process_ideas_inbox.py:49-93`. process_ideas_inbox.py is NOT touched. |
| `scripts/plaud_actions.py` | NEW (~280 lines) | `process()`, `extract_actions()`, `resolve_linear_route()`, `create_linear_tickets()`, `rewrite_frontmatter()`, `build_digest_text()`, `send_batch_digest()` |
| `scripts/prompts/action_extraction.md` | NEW (~80 lines) | System prompt + 3 few-shot examples. Loaded at module import. |
| `tests/test_plaud_actions.py` | NEW (~330 lines, ~21 tests) | All unit tests, urllib stubbed. |
| `tests/test_plaud_actions_live.py` | NEW (~55 lines) | Opt-in via `RUN_PLAUD_LIVE=1`. Real Anthropic + Linear calls. |
| `scripts/plaud_ingest.py` | MODIFY (3 surgical edits, ~25 lines added) | Call `plaud_actions.process()` after `write_page()`; carry `batch_results`; call `send_batch_digest()` post-loop. |

---

## Task 0: Verify env + create Linear test project

**Files:** none (pre-flight)

- [ ] **Step 1: Confirm Anthropic + Linear keys present**

Run:
```bash
grep -E "^(ANTHROPIC_API_KEY|LINEAR_API_KEY)=" ~/.hermes/.env | wc -l
```
Expected: `2`. If `0` or `1`, return `BLOCKED` — user must add the missing key before any further work.

- [ ] **Step 2: Smoke-test Anthropic key**

Run:
```bash
KEY=$(grep '^ANTHROPIC_API_KEY=' ~/.hermes/.env | head -1 | cut -d= -f2-) && curl -sS -X POST https://api.anthropic.com/v1/messages \
  -H "x-api-key: $KEY" -H "anthropic-version: 2023-06-01" -H "content-type: application/json" \
  -d '{"model":"claude-haiku-4-5","max_tokens":50,"messages":[{"role":"user","content":"reply with just OK"}]}' \
  | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("content",[{}])[0].get("text","NO_TEXT"))'
```
Expected: prints `OK` or something near it. If you get `{"type":"error",...}`, return `BLOCKED` with the message.

- [ ] **Step 3: Smoke-test Linear key**

Run:
```bash
KEY=$(grep '^LINEAR_API_KEY=' ~/.hermes/.env | cut -d= -f2-) && curl -sS https://api.linear.app/graphql \
  -H "Authorization: $KEY" -H "Content-Type: application/json" \
  -d '{"query":"{ viewer { id name } }"}' | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d.get("data",{}).get("viewer",{}))'
```
Expected: prints `{'id': '...', 'name': '...'}`. If `errors` key present, return `BLOCKED`.

- [ ] **Step 4: Create a "Plaud Actions Test" project in Linear**

Open Linear in your browser → RestoreAssist team → New Project → name it `Plaud Actions Test`. Copy its UUID from the URL (`linear.app/.../project/<uuid>`).

Add to `~/.hermes/.env`:
```
PLAUD_LIVE_TEST_PROJECT_ID=<uuid-you-just-created>
```

This is OPTIONAL — only needed if you want to run the opt-in live integration test (Task 11). The unit suite (Tasks 1-10) doesn't touch real Linear.

- [ ] **Step 5: No code changes, no commit. Move on.**

---

## Task 1: linear_helpers.py — extracted Linear ticket creation (TDD)

**Files:**
- Create: `scripts/linear_helpers.py`
- Create: `tests/test_linear_helpers.py`

- [ ] **Step 1: Write failing tests**

Create `~/Pi-CEO/Pi-Dev-Ops/tests/test_linear_helpers.py`:
```python
"""Tests for scripts/linear_helpers.py."""
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import linear_helpers


def _mock_response(payload: dict, status: int = 200):
    m = MagicMock()
    m.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    m.__enter__.return_value.status = status
    return m


def test_create_linear_issue_success():
    payload = {"data": {"issueCreate": {"success": True,
        "issue": {"id": "abc-123", "identifier": "CCW-247", "title": "test"}}}}
    with patch("linear_helpers.urllib.request.urlopen", return_value=_mock_response(payload)) as mock_open:
        ref = linear_helpers.create_linear_issue(
            api_key="lin_api_xxx", title="test", description="body",
            team_id="UNI-team", project_id="ccw-proj", priority=3,
        )
    assert ref is not None
    assert ref.identifier == "CCW-247"
    assert ref.id == "abc-123"
    # Inspect the POST body
    req = mock_open.call_args[0][0]
    body = json.loads(req.data.decode())
    assert body["variables"]["input"]["teamId"] == "UNI-team"
    assert body["variables"]["input"]["projectId"] == "ccw-proj"
    assert body["variables"]["input"]["title"] == "test"
    assert body["variables"]["input"]["priority"] == 3


def test_create_linear_issue_truncates_long_title():
    long_title = "x" * 500
    payload = {"data": {"issueCreate": {"success": True,
        "issue": {"id": "i", "identifier": "RA-1", "title": "x" * 250}}}}
    with patch("linear_helpers.urllib.request.urlopen", return_value=_mock_response(payload)) as mock_open:
        linear_helpers.create_linear_issue(api_key="k", title=long_title,
            description="d", team_id="t", project_id="p", priority=3)
    req = mock_open.call_args[0][0]
    body = json.loads(req.data.decode())
    assert len(body["variables"]["input"]["title"]) == 250


def test_create_linear_issue_returns_none_on_graphql_error():
    payload = {"errors": [{"message": "Project not found"}]}
    with patch("linear_helpers.urllib.request.urlopen", return_value=_mock_response(payload)):
        ref = linear_helpers.create_linear_issue(api_key="k", title="t",
            description="d", team_id="t", project_id="p", priority=3)
    assert ref is None


def test_create_linear_issue_returns_none_on_http_error():
    import urllib.error
    with patch("linear_helpers.urllib.request.urlopen",
               side_effect=urllib.error.URLError("network down")):
        ref = linear_helpers.create_linear_issue(api_key="k", title="t",
            description="d", team_id="t", project_id="p", priority=3)
    assert ref is None
```

- [ ] **Step 2: Run, expect failure**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops && pytest tests/test_linear_helpers.py -v
```
Expected: `ModuleNotFoundError: No module named 'linear_helpers'`.

- [ ] **Step 3: Implement**

Create `~/Pi-CEO/Pi-Dev-Ops/scripts/linear_helpers.py`:
```python
"""Shared Linear GraphQL helpers. Extracted from scripts/process_ideas_inbox.py:49-93
to support both the existing ideas-inbox flow and the new plaud-actions flow.

process_ideas_inbox.py is NOT modified — it keeps its own copy of the function
to avoid coupling unrelated work. Both call sites talk to the same Linear API
and behave identically; this module is the canonical pattern for new callers.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Optional

log = logging.getLogger("linear_helpers")

LINEAR_API_URL = "https://api.linear.app/graphql"
ISSUE_CREATE_MUTATION = """
mutation IssueCreate($input: IssueCreateInput!) {
  issueCreate(input: $input) {
    success
    issue { id identifier title url }
  }
}
"""


@dataclass
class TicketRef:
    """A reference to a successfully created Linear ticket."""
    id: str            # Linear internal UUID
    identifier: str    # human-readable, e.g. "CCW-247"
    url: str = ""      # canonical Linear URL (may be empty for older API responses)


def create_linear_issue(
    *,
    api_key: str,
    title: str,
    description: str,
    team_id: str,
    project_id: str,
    priority: int = 3,
) -> Optional[TicketRef]:
    """POST to Linear GraphQL to create an issue. Returns TicketRef or None.

    priority: Linear scale — 0=None, 1=Urgent, 2=High, 3=Normal, 4=Low.
    title is truncated to 250 chars (Linear's cap).
    """
    variables = {"input": {
        "teamId": team_id,
        "projectId": project_id,
        "title": title[:250],
        "description": description,
        "priority": priority,
    }}
    payload = json.dumps({"query": ISSUE_CREATE_MUTATION, "variables": variables}).encode()

    req = urllib.request.Request(
        LINEAR_API_URL,
        data=payload,
        headers={"Authorization": api_key, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except (urllib.error.URLError, json.JSONDecodeError, OSError) as exc:
        log.warning("create_linear_issue HTTP failure: %s", exc)
        return None

    if "errors" in data:
        log.warning("create_linear_issue GraphQL errors: %s", data["errors"])
        return None

    result = data.get("data", {}).get("issueCreate", {}) or {}
    if not result.get("success"):
        log.warning("create_linear_issue not successful: %s", result)
        return None

    issue = result.get("issue") or {}
    return TicketRef(
        id=issue.get("id", ""),
        identifier=issue.get("identifier", ""),
        url=issue.get("url", ""),
    )
```

- [ ] **Step 4: Tests pass**

```bash
pytest tests/test_linear_helpers.py -v
```
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add scripts/linear_helpers.py tests/test_linear_helpers.py
git commit -m "feat(linear-helpers): extracted shared create_linear_issue (Task 1)"
```

---

## Task 2: Prompt template (data file, no tests)

**Files:**
- Create: `scripts/prompts/action_extraction.md`

- [ ] **Step 1: Create the prompts directory + file**

```bash
mkdir -p ~/Pi-CEO/Pi-Dev-Ops/scripts/prompts
```

Create `~/Pi-CEO/Pi-Dev-Ops/scripts/prompts/action_extraction.md`:
```markdown
# Action Extraction System Prompt

You are an action-extraction analyst for Phill McGurk's portfolio. Phill records voice notes and meetings via a Plaud NotePin throughout his day, covering 7 portfolio businesses + agency work. Your job is to (a) decide which portfolio the recording is about, and (b) extract any concrete action items.

## Portfolios

Choose exactly ONE of these `id` values (or `"unknown"`):

- `pi-dev-ops` — internal autonomous agent platform; the meta-system
- `restoreassist` — iOS app for restoration industry (TestFlight → App Store)
- `disaster-recovery` — Disaster Recovery client website
- `dr-nrpg` — National Restoration Practitioners Group operations platform
- `nrpg-onboarding` — NRPG contractor onboarding framework
- `synthex` — marketing-automation SaaS; internal + external (CCW uses it)
- `unite-group` — Unite-Group umbrella / Nexus product
- `nodejs-starter` — internal repo
- `oh-my-codex` — internal repo
- `ccw-crm` — Carpet Cleaners Warehouse CRM (the company's first paying external client)
- `carsi` — Compliance delivery product (IICRC CEC quizzes)
- `unknown` — recording is personal, ambient, ambiguous, or covers multiple portfolios with no clear lead

If multiple portfolios are mentioned, pick the most-discussed one. Set `confidence` lower than 0.7 if you're unsure.

## Action items

Extract ONLY concrete commitments — things someone said they (or someone else) would do. Do NOT include vague mentions, philosophical musings, or background context.

Each action has:
- `title`: imperative, under 80 chars ("Follow up with Toby on pricing", "Update CCW Linear with Q2 numbers")
- `description`: 1-3 sentences of context including any specific names, dates, numbers mentioned
- `priority`: Linear scale — 1=urgent (must do this week), 2=high (soon, has deadline), 3=normal (default), 4=low (someday/maybe)

Return zero actions if the recording is a voice memo, stream-of-consciousness, or has no clear commitments.

## Output format

You MUST use the `report_actions` tool to return your analysis. Do not respond with prose.

## Examples

### Example 1: Clear meeting

Recording: "Just got off a call with Toby at CCW. We agreed I'll send him the new pricing tier proposal by Friday. He's going to check his Q2 commit numbers and update them in Linear by end of next week. We also need to schedule a review for the week of May 26."

Expected output:
```json
{
  "portfolio": "ccw-crm",
  "confidence": 0.95,
  "reasoning": "Direct mention of CCW + Toby, clear three-action commitment",
  "actions": [
    {"title": "Send Toby the new pricing tier proposal", "description": "By Friday. Came out of CCW pricing call today.", "priority": 2},
    {"title": "Update CCW Linear with Q2 commit numbers", "description": "Toby committed to this by end of next week.", "priority": 3},
    {"title": "Schedule CCW review for week of 26 May", "description": "Agreed during pricing call.", "priority": 4}
  ]
}
```

### Example 2: Voice memo, no actions

Recording: "I've been thinking about how to position Synthex. Maybe the agency angle is the right one, but I'm not sure if that competes with what we're trying to do with the marketing playbook. Need to think about this more."

Expected output:
```json
{
  "portfolio": "synthex",
  "confidence": 0.85,
  "reasoning": "Thinking-out-loud about Synthex positioning; no commitments made",
  "actions": []
}
```

### Example 3: Mixed portfolios, route to dominant

Recording: "Quick note — Sarah from RestoreAssist needs the new compliance UI by next Tuesday. Also reminder to update the Synthex landing page copy. And I should send John the IICRC content draft."

Expected output:
```json
{
  "portfolio": "restoreassist",
  "confidence": 0.6,
  "reasoning": "RestoreAssist mentioned first with the firmest deadline; CARSI and Synthex mentioned but secondary",
  "actions": [
    {"title": "Send RestoreAssist compliance UI to Sarah", "description": "Sarah from RA needs it by next Tuesday.", "priority": 2},
    {"title": "Update Synthex landing page copy", "description": "No deadline given.", "priority": 3},
    {"title": "Send John the IICRC content draft", "description": "No deadline; IICRC content programme deliverable.", "priority": 3}
  ]
}
```
```

- [ ] **Step 2: Verify file exists**

```bash
test -f ~/Pi-CEO/Pi-Dev-Ops/scripts/prompts/action_extraction.md && wc -l ~/Pi-CEO/Pi-Dev-Ops/scripts/prompts/action_extraction.md
```
Expected: prints line count (~80).

- [ ] **Step 3: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add scripts/prompts/action_extraction.md
git commit -m "feat(plaud-actions): system prompt template with 3 few-shot examples (Task 2)"
```

---

## Task 3: plaud_actions.py skeleton + dataclasses (TDD)

**Files:**
- Create: `scripts/plaud_actions.py`
- Create: `tests/test_plaud_actions.py`

- [ ] **Step 1: Write failing tests for the dataclass shape**

Create `~/Pi-CEO/Pi-Dev-Ops/tests/test_plaud_actions.py`:
```python
"""Tests for scripts/plaud_actions.py."""
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import plaud_actions


def test_action_dataclass_defaults():
    a = plaud_actions.Action(title="x", description="y", priority=2)
    assert a.title == "x"
    assert a.priority == 2


def test_action_extraction_dataclass():
    ex = plaud_actions.ActionExtraction(
        portfolio="ccw-crm", confidence=0.92,
        reasoning="mentions CCW",
        actions=[plaud_actions.Action(title="t", description="d", priority=3)],
    )
    assert ex.portfolio == "ccw-crm"
    assert len(ex.actions) == 1


def test_batch_result_dataclass():
    br = plaud_actions.BatchResult(
        plaud_id="abc", title="Acme Q2",
        wiki_path="plaud/2026-05-17-acme-q2",
        portfolio="ccw-crm",
        tickets=[],
        status="no_actions",
    )
    assert br.status == "no_actions"


def test_linear_route_namedtuple():
    r = plaud_actions.LinearRoute(team_id="t", project_id="p", status="matched")
    assert r.team_id == "t"
    assert r.status == "matched"
```

- [ ] **Step 2: Run, expect failure**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops && pytest tests/test_plaud_actions.py -v
```
Expected: `ModuleNotFoundError: No module named 'plaud_actions'`.

- [ ] **Step 3: Implement skeleton**

Create `~/Pi-CEO/Pi-Dev-Ops/scripts/plaud_actions.py`:
```python
"""Plaud Actions — sub-project 2 of 3. Reads ingested wiki/plaud/ pages, extracts
action items via Anthropic Haiku 4.5, files Linear tickets, posts ONE Telegram
digest per cron batch. Spec: docs/superpowers/specs/2026-05-17-plaud-actions-design.md
"""
from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import NamedTuple, Optional

# Local helpers — also defined in plaud_ingest.py; re-imported here for testability
# without circular imports. Re-using plaud_ingest's _parse_frontmatter would create
# a circular dep; this module owns its own copy of a smaller frontmatter reader.

import sys
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
```

- [ ] **Step 4: Tests pass**

```bash
pytest tests/test_plaud_actions.py -v
```
Expected: `4 passed`.

- [ ] **Step 5: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add scripts/plaud_actions.py tests/test_plaud_actions.py
git commit -m "feat(plaud-actions): module skeleton + dataclasses (Task 3)"
```

---

## Task 4: resolve_linear_route (TDD)

**Files:**
- Modify: `scripts/plaud_actions.py`
- Modify: `tests/test_plaud_actions.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plaud_actions.py`:
```python
def test_resolve_linear_route_known_portfolio(tmp_path):
    pj = tmp_path / "projects.json"
    pj.write_text(json.dumps({"projects": [
        {"id": "ccw-crm", "linear_team_id": "uni-team-uuid", "linear_project_id": "ccw-proj-uuid"},
        {"id": "pi-dev-ops", "linear_team_id": "ra-team-uuid", "linear_project_id": "pidev-proj-uuid"},
    ]}))
    r = plaud_actions.resolve_linear_route("ccw-crm", projects_json_path=pj)
    assert r.team_id == "uni-team-uuid"
    assert r.project_id == "ccw-proj-uuid"
    assert r.status == "matched"


def test_resolve_linear_route_unknown_falls_back_to_pi_dev_ops(tmp_path):
    pj = tmp_path / "projects.json"
    pj.write_text(json.dumps({"projects": [
        {"id": "pi-dev-ops", "linear_team_id": "ra-team-uuid", "linear_project_id": "pidev-proj-uuid"},
    ]}))
    r = plaud_actions.resolve_linear_route("unknown", projects_json_path=pj)
    assert r.team_id == "ra-team-uuid"
    assert r.project_id == "pidev-proj-uuid"
    assert r.status == "fallback_unknown"


def test_resolve_linear_route_missing_portfolio_falls_back(tmp_path):
    """Portfolio not in projects.json → fallback to pi-dev-ops (not crash)."""
    pj = tmp_path / "projects.json"
    pj.write_text(json.dumps({"projects": [
        {"id": "pi-dev-ops", "linear_team_id": "ra", "linear_project_id": "pi"},
    ]}))
    r = plaud_actions.resolve_linear_route("imaginary-portfolio", projects_json_path=pj)
    assert r.status == "fallback_unknown"


def test_resolve_linear_route_missing_projects_json_raises(tmp_path):
    pj = tmp_path / "does_not_exist.json"
    try:
        plaud_actions.resolve_linear_route("ccw-crm", projects_json_path=pj)
        assert False, "expected FileNotFoundError"
    except FileNotFoundError:
        pass


def test_resolve_linear_route_no_default_in_registry_raises(tmp_path):
    """If pi-dev-ops itself is missing from projects.json, raise."""
    pj = tmp_path / "projects.json"
    pj.write_text(json.dumps({"projects": [
        {"id": "ccw-crm", "linear_team_id": "u", "linear_project_id": "c"},
    ]}))
    try:
        plaud_actions.resolve_linear_route("unknown", projects_json_path=pj)
        assert False, "expected RuntimeError"
    except RuntimeError as e:
        assert "pi-dev-ops" in str(e).lower()
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_plaud_actions.py -k resolve_linear -v
```
Expected: 5 failures (`AttributeError: resolve_linear_route`).

- [ ] **Step 3: Implement**

Append to `scripts/plaud_actions.py`:
```python
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
```

- [ ] **Step 4: Tests pass**

```bash
pytest tests/test_plaud_actions.py -v
```
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add scripts/plaud_actions.py tests/test_plaud_actions.py
git commit -m "feat(plaud-actions): resolve_linear_route with pi-dev-ops fallback (Task 4)"
```

---

## Task 5: extract_actions — Anthropic Messages API call (TDD)

**Files:**
- Modify: `scripts/plaud_actions.py`
- Modify: `tests/test_plaud_actions.py`

The Anthropic Messages API + tool-use is the structured-output pattern. We define a tool named `report_actions` whose input schema matches `ActionExtraction`, force the model to use it (`tool_choice`), and read the structured input from the response.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plaud_actions.py`:
```python
def _anthropic_tool_use_response(portfolio, confidence, reasoning, actions):
    """Build a mock Anthropic Messages API response with a tool_use block."""
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "content": [{
            "type": "tool_use",
            "id": "toolu_1",
            "name": "report_actions",
            "input": {
                "portfolio": portfolio,
                "confidence": confidence,
                "reasoning": reasoning,
                "actions": actions,
            }
        }],
        "stop_reason": "tool_use",
    }


def _anthropic_mock_urlopen(payload, status=200):
    m = MagicMock()
    m.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    m.__enter__.return_value.status = status
    return m


def test_extract_actions_meeting_yields_actions():
    response = _anthropic_tool_use_response(
        portfolio="ccw-crm", confidence=0.92, reasoning="Mentions CCW",
        actions=[
            {"title": "Follow up Toby", "description": "by Friday", "priority": 2},
            {"title": "Update Q2 numbers", "description": "in Linear", "priority": 3},
        ],
    )
    with patch("plaud_actions.urllib.request.urlopen",
               return_value=_anthropic_mock_urlopen(response)):
        ex = plaud_actions.extract_actions(
            page_md="dummy meeting content",
            anthropic_api_key="sk-ant-test",
        )
    assert ex is not None
    assert ex.portfolio == "ccw-crm"
    assert len(ex.actions) == 2
    assert ex.actions[0].title == "Follow up Toby"
    assert ex.actions[0].priority == 2


def test_extract_actions_voice_memo_zero_actions():
    response = _anthropic_tool_use_response(
        portfolio="synthex", confidence=0.85,
        reasoning="Thinking out loud", actions=[],
    )
    with patch("plaud_actions.urllib.request.urlopen",
               return_value=_anthropic_mock_urlopen(response)):
        ex = plaud_actions.extract_actions(page_md="rambling memo",
            anthropic_api_key="sk-ant-test")
    assert ex is not None
    assert ex.actions == []


def test_extract_actions_no_tool_use_in_response_returns_none():
    response = {"content": [{"type": "text", "text": "I refuse to answer"}]}
    with patch("plaud_actions.urllib.request.urlopen",
               return_value=_anthropic_mock_urlopen(response)):
        ex = plaud_actions.extract_actions(page_md="x", anthropic_api_key="k")
    assert ex is None


def test_extract_actions_http_401_returns_auth_error():
    """401 returns the sentinel _AuthError class so caller can DM and skip."""
    import urllib.error
    err = urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)
    with patch("plaud_actions.urllib.request.urlopen", side_effect=err):
        ex = plaud_actions.extract_actions(page_md="x", anthropic_api_key="k")
    assert isinstance(ex, plaud_actions._AuthError)


def test_extract_actions_http_429_retries_once_then_succeeds():
    import urllib.error
    err = urllib.error.HTTPError("url", 429, "Too Many", {}, None)
    success = _anthropic_tool_use_response("synthex", 0.9, "", [])
    side_effects = [err, _anthropic_mock_urlopen(success)]
    with patch("plaud_actions.urllib.request.urlopen", side_effect=side_effects), \
         patch("plaud_actions.time.sleep") as mock_sleep:
        ex = plaud_actions.extract_actions(page_md="x", anthropic_api_key="k")
    assert ex is not None
    mock_sleep.assert_called_once()


def test_extract_actions_http_429_twice_returns_none():
    import urllib.error
    err = urllib.error.HTTPError("url", 429, "Too Many", {}, None)
    with patch("plaud_actions.urllib.request.urlopen", side_effect=err), \
         patch("plaud_actions.time.sleep"):
        ex = plaud_actions.extract_actions(page_md="x", anthropic_api_key="k")
    assert ex is None


def test_extract_actions_low_confidence_routes_unknown_via_caller():
    """extract_actions itself doesn't reroute on low confidence — that happens in process().
    This test just confirms low confidence is preserved in the returned object."""
    response = _anthropic_tool_use_response(
        portfolio="unknown", confidence=0.3,
        reasoning="Ambiguous", actions=[
            {"title": "Some action", "description": "x", "priority": 3},
        ],
    )
    with patch("plaud_actions.urllib.request.urlopen",
               return_value=_anthropic_mock_urlopen(response)):
        ex = plaud_actions.extract_actions(page_md="x", anthropic_api_key="k")
    assert ex.portfolio == "unknown"
    assert ex.confidence == 0.3
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_plaud_actions.py -k extract_actions -v
```
Expected: 7 failures.

- [ ] **Step 3: Implement**

Append to `scripts/plaud_actions.py`:
```python
import time

# Tool-use schema for structured output. Mirrors the ActionExtraction dataclass.
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


def extract_actions(*, page_md: str, anthropic_api_key: str) -> Optional["ActionExtraction | _AuthError"]:
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
    else:
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
```

- [ ] **Step 4: Tests pass**

```bash
pytest tests/test_plaud_actions.py -v
```
Expected: 16 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add scripts/plaud_actions.py tests/test_plaud_actions.py
git commit -m "feat(plaud-actions): Anthropic Messages API extraction with tool-use (Task 5)"
```

---

## Task 6: create_linear_tickets — batch wrapper with backlink (TDD)

**Files:**
- Modify: `scripts/plaud_actions.py`
- Modify: `tests/test_plaud_actions.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plaud_actions.py`:
```python
def test_create_linear_tickets_happy_path():
    actions = [
        plaud_actions.Action(title="Action 1", description="desc 1", priority=2),
        plaud_actions.Action(title="Action 2", description="desc 2", priority=3),
    ]
    # Mock linear_helpers.create_linear_issue to return a TicketRef each time
    refs = [
        plaud_actions.TicketRef(id="i1", identifier="CCW-247", url="u1"),
        plaud_actions.TicketRef(id="i2", identifier="CCW-248", url="u2"),
    ]
    with patch("plaud_actions.create_linear_issue", side_effect=refs):
        result = plaud_actions.create_linear_tickets(
            actions=actions, team_id="t", project_id="p",
            wiki_link="https://wiki/plaud/x.md",
            linear_api_key="lin_api_xxx",
        )
    assert len(result) == 2
    assert result[0].identifier == "CCW-247"


def test_create_linear_tickets_partial_failure():
    """2nd call returns None → only 1 TicketRef in result."""
    actions = [
        plaud_actions.Action(title="A", description="d1", priority=3),
        plaud_actions.Action(title="B", description="d2", priority=3),
        plaud_actions.Action(title="C", description="d3", priority=3),
    ]
    side_effects = [
        plaud_actions.TicketRef(id="i1", identifier="X-1", url=""),
        None,  # second one fails
        plaud_actions.TicketRef(id="i3", identifier="X-3", url=""),
    ]
    with patch("plaud_actions.create_linear_issue", side_effect=side_effects):
        result = plaud_actions.create_linear_tickets(
            actions=actions, team_id="t", project_id="p",
            wiki_link="https://wiki/p", linear_api_key="k",
        )
    assert len(result) == 2
    assert [r.identifier for r in result] == ["X-1", "X-3"]


def test_create_linear_tickets_appends_wiki_backlink_to_description():
    """Description sent to Linear must include 'Source: [...](wiki_link)' suffix."""
    actions = [plaud_actions.Action(title="A", description="original body", priority=3)]
    seen_descriptions: list[str] = []
    def fake_create(**kw):
        seen_descriptions.append(kw["description"])
        return plaud_actions.TicketRef(id="i", identifier="X-1", url="")

    with patch("plaud_actions.create_linear_issue", side_effect=fake_create):
        plaud_actions.create_linear_tickets(
            actions=actions, team_id="t", project_id="p",
            wiki_link="https://wiki/plaud/test-slug.md", linear_api_key="k",
        )
    assert "original body" in seen_descriptions[0]
    assert "https://wiki/plaud/test-slug.md" in seen_descriptions[0]
    assert "Source" in seen_descriptions[0]
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_plaud_actions.py -k create_linear_tickets -v
```
Expected: 3 failures.

- [ ] **Step 3: Implement**

Append to `scripts/plaud_actions.py`:
```python
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
```

- [ ] **Step 4: Tests pass**

```bash
pytest tests/test_plaud_actions.py -v
```
Expected: 19 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add scripts/plaud_actions.py tests/test_plaud_actions.py
git commit -m "feat(plaud-actions): create_linear_tickets batch with wiki backlink (Task 6)"
```

---

## Task 7: rewrite_frontmatter — atomic page update (TDD)

**Files:**
- Modify: `scripts/plaud_actions.py`
- Modify: `tests/test_plaud_actions.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plaud_actions.py`:
```python
def test_rewrite_frontmatter_adds_new_keys(tmp_path):
    page = tmp_path / "p.md"
    page.write_text(
        "---\n"
        "type: plaud-recording\n"
        "plaud_id: abc\n"
        "duration_human: 5m12s\n"
        "---\n"
        "\n# Title\n\nBody.\n"
    )
    plaud_actions.rewrite_frontmatter(page, {
        "tickets": ["CCW-247", "CCW-248"],
        "action_portfolio": "ccw-crm",
        "action_status": "ok",
    })
    text = page.read_text()
    assert "tickets: [CCW-247, CCW-248]" in text
    assert "action_portfolio: ccw-crm" in text
    assert "action_status: ok" in text
    # Original keys preserved
    assert "plaud_id: abc" in text
    assert "duration_human: 5m12s" in text
    # Body preserved
    assert "# Title" in text
    assert "Body." in text


def test_rewrite_frontmatter_updates_existing_keys(tmp_path):
    page = tmp_path / "p.md"
    page.write_text(
        "---\n"
        "type: plaud-recording\n"
        "action_status: partial\n"
        "---\n"
        "\nBody.\n"
    )
    plaud_actions.rewrite_frontmatter(page, {"action_status": "ok"})
    text = page.read_text()
    assert "action_status: ok" in text
    assert "action_status: partial" not in text


def test_rewrite_frontmatter_atomic_no_tmp_leftover(tmp_path):
    page = tmp_path / "p.md"
    page.write_text("---\ntype: plaud-recording\n---\n\nBody.\n")
    plaud_actions.rewrite_frontmatter(page, {"action_status": "ok"})
    assert not list(tmp_path.glob("*.tmp"))


def test_rewrite_frontmatter_no_frontmatter_raises(tmp_path):
    page = tmp_path / "p.md"
    page.write_text("# Just markdown, no frontmatter\n")
    try:
        plaud_actions.rewrite_frontmatter(page, {"x": "y"})
        assert False, "expected ValueError"
    except ValueError:
        pass


def test_read_frontmatter_tickets_returns_existing(tmp_path):
    page = tmp_path / "p.md"
    page.write_text(
        "---\n"
        "type: plaud-recording\n"
        "tickets: [CCW-247, CCW-248]\n"
        "action_status: ok\n"
        "---\n"
        "\nBody.\n"
    )
    fm = plaud_actions.read_frontmatter(page)
    assert fm.get("tickets") == "[CCW-247, CCW-248]"  # raw string; caller parses
    assert fm.get("action_status") == "ok"


def test_read_frontmatter_no_frontmatter_returns_empty(tmp_path):
    page = tmp_path / "p.md"
    page.write_text("# No frontmatter\n")
    assert plaud_actions.read_frontmatter(page) == {}
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_plaud_actions.py -k "frontmatter" -v
```
Expected: 6 failures.

- [ ] **Step 3: Implement**

Append to `scripts/plaud_actions.py`:
```python
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

    # Preserve original key order, update in place
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

    # Append any updates keys that weren't present
    for k, v in updates.items():
        if k not in existing_keys:
            new_lines.append(f"{k}: {_serialize_yaml_value(v)}")

    body = text[end:]  # starts with '\n---\n'
    rebuilt = "---\n" + "\n".join(new_lines) + body

    tmp = page_path.with_suffix(page_path.suffix + ".tmp")
    tmp.write_text(rebuilt)
    os.replace(tmp, page_path)
```

- [ ] **Step 4: Tests pass**

```bash
pytest tests/test_plaud_actions.py -v
```
Expected: 25 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add scripts/plaud_actions.py tests/test_plaud_actions.py
git commit -m "feat(plaud-actions): atomic frontmatter rewrite + read helpers (Task 7)"
```

---

## Task 8: build_digest_text (TDD)

**Files:**
- Modify: `scripts/plaud_actions.py`
- Modify: `tests/test_plaud_actions.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plaud_actions.py`:
```python
def test_build_digest_single_recording_with_actions():
    br = plaud_actions.BatchResult(
        plaud_id="abc", title="Acme Q2 Pricing",
        wiki_path="plaud/2026-05-17-acme-q2-pricing",
        portfolio="ccw-crm",
        tickets=[
            plaud_actions.TicketRef(id="i1", identifier="CCW-247", url="https://linear.app/u/CCW-247"),
            plaud_actions.TicketRef(id="i2", identifier="CCW-248", url="https://linear.app/u/CCW-248"),
        ],
        status="ok",
    )
    text = plaud_actions.build_digest_text([br])
    assert text is not None
    assert "Acme Q2 Pricing" in text
    assert "ccw-crm" in text or "CCW" in text
    assert "CCW-247" in text
    assert "CCW-248" in text
    assert "plaud/2026-05-17-acme-q2-pricing" in text


def test_build_digest_mixed_batch():
    brs = [
        plaud_actions.BatchResult(plaud_id="a", title="Meeting A",
            wiki_path="plaud/a", portfolio="ccw-crm",
            tickets=[plaud_actions.TicketRef("i", "CCW-1", "")],
            status="ok"),
        plaud_actions.BatchResult(plaud_id="b", title="Voice memo",
            wiki_path="plaud/b", portfolio="synthex",
            tickets=[], status="no_actions"),
    ]
    text = plaud_actions.build_digest_text(brs)
    assert "Meeting A" in text
    assert "Voice memo" in text
    assert "no actions" in text.lower() or "0 tickets" in text.lower()


def test_build_digest_all_zero_returns_none():
    brs = [
        plaud_actions.BatchResult(plaud_id="a", title="t1",
            wiki_path="p1", portfolio="x", tickets=[], status="no_actions"),
        plaud_actions.BatchResult(plaud_id="b", title="t2",
            wiki_path="p2", portfolio="y", tickets=[], status="no_actions"),
    ]
    assert plaud_actions.build_digest_text(brs) is None


def test_build_digest_empty_list_returns_none():
    assert plaud_actions.build_digest_text([]) is None


def test_build_digest_partial_shows_partial_marker():
    br = plaud_actions.BatchResult(plaud_id="a", title="Partial meeting",
        wiki_path="plaud/x", portfolio="ccw-crm",
        tickets=[plaud_actions.TicketRef("i", "CCW-1", "")],
        status="partial")
    text = plaud_actions.build_digest_text([br])
    assert "partial" in text.lower() or "⚠" in text
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_plaud_actions.py -k build_digest -v
```
Expected: 5 failures.

- [ ] **Step 3: Implement**

Append to `scripts/plaud_actions.py`:
```python
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
```

- [ ] **Step 4: Tests pass**

```bash
pytest tests/test_plaud_actions.py -v
```
Expected: 30 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add scripts/plaud_actions.py tests/test_plaud_actions.py
git commit -m "feat(plaud-actions): build_digest_text composer (Task 8)"
```

---

## Task 9: process() — orchestrator with all error paths (TDD)

**Files:**
- Modify: `scripts/plaud_actions.py`
- Modify: `tests/test_plaud_actions.py`

This is the biggest task — wires extraction, routing, ticket creation, frontmatter rewrite, idempotency check, kill-switch, and poison-pill guard.

- [ ] **Step 1: Write failing tests**

First, add `import pytest` near the top of `tests/test_plaud_actions.py` (after the existing `from unittest.mock` import) — needed for the `@pytest.fixture` decorator below.

Then append:
```python
def _make_cfg(tmp_path, **overrides):
    """Build a minimal config-shaped object the orchestrator needs.
    We don't import the real IngestConfig — we mirror only what process() touches."""
    from types import SimpleNamespace
    pj = tmp_path / "projects.json"
    if not pj.exists():
        pj.write_text(json.dumps({"projects": [
            {"id": "pi-dev-ops", "linear_team_id": "ra-team", "linear_project_id": "pi-proj"},
            {"id": "ccw-crm", "linear_team_id": "uni-team", "linear_project_id": "ccw-proj"},
        ]}))
    state_path = tmp_path / "state.json"
    if not state_path.exists():
        state_path.write_text(json.dumps({"action_status_by_id": {}}))
    cfg = SimpleNamespace(
        state_path=state_path,
        projects_json_path=pj,
        wiki_dir=tmp_path / "Wiki",
        anthropic_api_key="sk-ant-test",
        linear_api_key="lin_api_test",
        bot_token="bot",
        chat_id="chat",
        notify_fn=lambda **k: None,
    )
    cfg.wiki_dir.mkdir(parents=True, exist_ok=True)
    (cfg.wiki_dir / "plaud").mkdir(exist_ok=True)
    return overrides_apply(cfg, overrides)


def overrides_apply(cfg, overrides):
    for k, v in overrides.items():
        setattr(cfg, k, v)
    return cfg


def _write_page(page_path, plaud_id="abc", title="Test", extra_fm: dict | None = None):
    fm_lines = [
        "type: plaud-recording",
        f"plaud_id: {plaud_id}",
        "duration_human: 5m12s",
    ]
    if extra_fm:
        for k, v in extra_fm.items():
            fm_lines.append(f"{k}: {plaud_actions._serialize_yaml_value(v)}")
    text = "---\n" + "\n".join(fm_lines) + "\n---\n\n" + f"# {title}\n\nBody.\n"
    page_path.write_text(text)
    return page_path


@pytest.fixture(autouse=True)
def _no_kill_switch(monkeypatch):
    monkeypatch.delenv("PLAUD_ACTIONS_ENABLED", raising=False)


def test_process_skips_page_with_existing_tickets(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    page = _write_page(cfg.wiki_dir / "plaud" / "p.md",
                       extra_fm={"tickets": ["CCW-1", "CCW-2"], "action_status": "ok"})

    extract_called = MagicMock()
    monkeypatch.setattr(plaud_actions, "extract_actions", extract_called)

    batch_results: list = []
    plaud_actions.process(
        plaud_id="abc", page_path=page,
        file_meta={"name": "x", "duration": 0},
        batch_results=batch_results, cfg=cfg,
    )
    extract_called.assert_not_called()
    assert len(batch_results) == 1
    assert batch_results[0].status == "skipped"


def test_process_skips_when_kill_switch_off(tmp_path, monkeypatch):
    monkeypatch.setenv("PLAUD_ACTIONS_ENABLED", "0")
    cfg = _make_cfg(tmp_path)
    page = _write_page(cfg.wiki_dir / "plaud" / "p.md")

    extract_called = MagicMock()
    monkeypatch.setattr(plaud_actions, "extract_actions", extract_called)

    batch_results: list = []
    plaud_actions.process(plaud_id="abc", page_path=page,
        file_meta={"name": "x", "duration": 0},
        batch_results=batch_results, cfg=cfg)
    extract_called.assert_not_called()


def test_process_happy_path_writes_frontmatter_and_files_tickets(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    page = _write_page(cfg.wiki_dir / "plaud" / "p.md", plaud_id="abc", title="Acme")

    monkeypatch.setattr(plaud_actions, "extract_actions",
        lambda **kw: plaud_actions.ActionExtraction(
            portfolio="ccw-crm", confidence=0.9, reasoning="ccw",
            actions=[plaud_actions.Action("Follow up", "by Friday", 2)]))
    monkeypatch.setattr(plaud_actions, "create_linear_issue",
        lambda **kw: plaud_actions.TicketRef(id="i1", identifier="CCW-247", url="u"))

    batch_results: list = []
    plaud_actions.process(plaud_id="abc", page_path=page,
        file_meta={"name": "Acme", "duration": 312000},
        batch_results=batch_results, cfg=cfg)

    assert len(batch_results) == 1
    assert batch_results[0].status == "ok"
    assert batch_results[0].tickets[0].identifier == "CCW-247"
    fm = plaud_actions.read_frontmatter(page)
    assert "CCW-247" in fm.get("tickets", "")
    assert fm.get("action_portfolio") == "ccw-crm"
    assert fm.get("action_status") == "ok"


def test_process_partial_failure_marks_partial(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    page = _write_page(cfg.wiki_dir / "plaud" / "p.md")

    monkeypatch.setattr(plaud_actions, "extract_actions",
        lambda **kw: plaud_actions.ActionExtraction(
            portfolio="ccw-crm", confidence=0.9, reasoning="",
            actions=[plaud_actions.Action(f"A{i}", "d", 3) for i in range(3)]))
    # 2nd of 3 linear calls returns None
    side = [plaud_actions.TicketRef("i1", "X-1", ""), None,
            plaud_actions.TicketRef("i3", "X-3", "")]
    monkeypatch.setattr(plaud_actions, "create_linear_issue", lambda **kw: side.pop(0))

    batch_results: list = []
    plaud_actions.process(plaud_id="abc", page_path=page,
        file_meta={"name": "x", "duration": 0},
        batch_results=batch_results, cfg=cfg)

    assert batch_results[0].status == "partial"
    assert len(batch_results[0].tickets) == 2
    fm = plaud_actions.read_frontmatter(page)
    assert fm.get("action_status") == "partial"


def test_process_no_actions_marks_no_actions(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    page = _write_page(cfg.wiki_dir / "plaud" / "p.md")

    monkeypatch.setattr(plaud_actions, "extract_actions",
        lambda **kw: plaud_actions.ActionExtraction(
            portfolio="synthex", confidence=0.8, reasoning="memo", actions=[]))
    create_called = MagicMock()
    monkeypatch.setattr(plaud_actions, "create_linear_issue", create_called)

    batch_results: list = []
    plaud_actions.process(plaud_id="abc", page_path=page,
        file_meta={"name": "x", "duration": 0},
        batch_results=batch_results, cfg=cfg)

    assert batch_results[0].status == "no_actions"
    create_called.assert_not_called()
    # No tickets frontmatter on no-action pages
    fm = plaud_actions.read_frontmatter(page)
    assert "tickets" not in fm
    # But action_portfolio + action_status ARE recorded so we don't re-extract next tick
    assert fm.get("action_status") == "no_actions"
    assert fm.get("action_portfolio") == "synthex"


def test_process_low_confidence_routes_to_pi_dev_ops(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    page = _write_page(cfg.wiki_dir / "plaud" / "p.md")

    monkeypatch.setattr(plaud_actions, "extract_actions",
        lambda **kw: plaud_actions.ActionExtraction(
            portfolio="ccw-crm", confidence=0.3, reasoning="uncertain",
            actions=[plaud_actions.Action("A", "d", 3)]))
    seen_proj = []
    def fake_create(**kw):
        seen_proj.append(kw["project_id"])
        return plaud_actions.TicketRef("i", "X-1", "")
    monkeypatch.setattr(plaud_actions, "create_linear_issue", fake_create)

    batch_results: list = []
    plaud_actions.process(plaud_id="abc", page_path=page,
        file_meta={"name": "x", "duration": 0},
        batch_results=batch_results, cfg=cfg)

    assert seen_proj == ["pi-proj"]
    assert batch_results[0].portfolio == "pi-dev-ops"  # rerouted from low confidence


def test_process_auth_error_no_frontmatter_change(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    page = _write_page(cfg.wiki_dir / "plaud" / "p.md")

    monkeypatch.setattr(plaud_actions, "extract_actions",
        lambda **kw: plaud_actions._AuthError())

    batch_results: list = []
    plaud_actions.process(plaud_id="abc", page_path=page,
        file_meta={"name": "x", "duration": 0},
        batch_results=batch_results, cfg=cfg)

    # No tickets, no frontmatter changes — recording stays retry-able
    fm = plaud_actions.read_frontmatter(page)
    assert "tickets" not in fm
    assert "action_status" not in fm
    assert batch_results[0].status == "skipped"


def test_process_parse_failure_increments_state_attempts(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    page = _write_page(cfg.wiki_dir / "plaud" / "p.md")

    monkeypatch.setattr(plaud_actions, "extract_actions", lambda **kw: None)

    batch_results: list = []
    plaud_actions.process(plaud_id="abc-parsefail", page_path=page,
        file_meta={"name": "x", "duration": 0},
        batch_results=batch_results, cfg=cfg)

    state = json.loads(cfg.state_path.read_text())
    assert state["action_status_by_id"]["abc-parsefail"]["attempts"] == 1


def test_process_skips_after_3_parse_failures(tmp_path, monkeypatch):
    cfg = _make_cfg(tmp_path)
    cfg.state_path.write_text(json.dumps({"action_status_by_id": {
        "abc-poison": {"status": "parse_failed", "attempts": 3, "last_error": ""},
    }}))
    page = _write_page(cfg.wiki_dir / "plaud" / "p.md")

    extract_called = MagicMock()
    monkeypatch.setattr(plaud_actions, "extract_actions", extract_called)

    batch_results: list = []
    plaud_actions.process(plaud_id="abc-poison", page_path=page,
        file_meta={"name": "x", "duration": 0},
        batch_results=batch_results, cfg=cfg)

    extract_called.assert_not_called()
    assert batch_results[0].status == "parse_failed"
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_plaud_actions.py -k process -v 2>&1 | tail -20
```
Expected: 9 failures (`AttributeError: process`).

- [ ] **Step 3: Implement**

Append to `scripts/plaud_actions.py`:
```python
_LOW_CONFIDENCE_THRESHOLD = 0.5
_MAX_PARSE_ATTEMPTS = 3


def _wiki_link_for_page(page_path: Path, wiki_dir: Path) -> str:
    """Build a relative wiki link like 'plaud/2026-05-17-foo.md'."""
    try:
        rel = page_path.relative_to(wiki_dir)
    except ValueError:
        rel = page_path
    return str(rel)


def _load_state(state_path: Path) -> dict:
    if not state_path.exists():
        return {"action_status_by_id": {}}
    try:
        data = json.loads(state_path.read_text())
        data.setdefault("action_status_by_id", {})
        return data
    except (json.JSONDecodeError, OSError):
        return {"action_status_by_id": {}}


def _save_state(state_path: Path, state: dict) -> None:
    state_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_path.with_suffix(state_path.suffix + ".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    os.replace(tmp, state_path)


def process(
    *,
    plaud_id: str,
    page_path: Path,
    file_meta: dict,
    batch_results: list[BatchResult],
    cfg,  # duck-typed: state_path, projects_json_path, wiki_dir, anthropic_api_key,
          #            linear_api_key, notify_fn, bot_token, chat_id
) -> None:
    """Process one ingested wiki page: extract actions, file tickets, rewrite
    frontmatter, append to batch_results. Never raises (caller wraps anyway,
    but we are defensive)."""

    title = file_meta.get("name", plaud_id)
    wiki_link = _wiki_link_for_page(page_path, cfg.wiki_dir)

    # Kill switch — env override
    if os.environ.get("PLAUD_ACTIONS_ENABLED", "1") == "0":
        batch_results.append(BatchResult(
            plaud_id=plaud_id, title=title, wiki_path=wiki_link,
            portfolio="", status="skipped",
        ))
        return

    # Idempotency check — already has tickets?
    fm = read_frontmatter(page_path)
    if "tickets" in fm:
        batch_results.append(BatchResult(
            plaud_id=plaud_id, title=title, wiki_path=wiki_link,
            portfolio=fm.get("action_portfolio", ""), status="skipped",
        ))
        return

    # Poison-pill guard — 3 consecutive parse failures
    state = _load_state(cfg.state_path)
    prior = state["action_status_by_id"].get(plaud_id, {})
    if prior.get("attempts", 0) >= _MAX_PARSE_ATTEMPTS:
        batch_results.append(BatchResult(
            plaud_id=plaud_id, title=title, wiki_path=wiki_link,
            portfolio="", status="parse_failed",
        ))
        return

    # Extract
    page_md = page_path.read_text()
    ex = extract_actions(page_md=page_md, anthropic_api_key=cfg.anthropic_api_key)

    if isinstance(ex, _AuthError):
        batch_results.append(BatchResult(
            plaud_id=plaud_id, title=title, wiki_path=wiki_link,
            portfolio="", status="skipped",
        ))
        return

    if ex is None:
        # Parse / transport failure — increment attempt counter
        attempts = prior.get("attempts", 0) + 1
        state["action_status_by_id"][plaud_id] = {
            "status": "parse_failed" if attempts >= _MAX_PARSE_ATTEMPTS else "parsing",
            "attempts": attempts,
            "last_error": "extract_actions returned None",
        }
        _save_state(cfg.state_path, state)
        # If we just hit the cap, mark the page so future runs short-circuit
        if attempts >= _MAX_PARSE_ATTEMPTS:
            try:
                rewrite_frontmatter(page_path, {"action_status": "parse_failed"})
            except ValueError:
                pass
        batch_results.append(BatchResult(
            plaud_id=plaud_id, title=title, wiki_path=wiki_link,
            portfolio="", status="parse_failed" if attempts >= _MAX_PARSE_ATTEMPTS else "skipped",
        ))
        return

    # Route — low confidence or unknown → fallback to pi-dev-ops
    portfolio = ex.portfolio
    if ex.confidence < _LOW_CONFIDENCE_THRESHOLD or portfolio == "unknown":
        portfolio = DEFAULT_PORTFOLIO_ID
    route = resolve_linear_route(portfolio, projects_json_path=cfg.projects_json_path)

    # No actions extracted — record and exit clean
    if not ex.actions:
        rewrite_frontmatter(page_path, {
            "action_portfolio": ex.portfolio,
            "action_status": "no_actions",
        })
        batch_results.append(BatchResult(
            plaud_id=plaud_id, title=title, wiki_path=wiki_link,
            portfolio=ex.portfolio, status="no_actions",
        ))
        return

    # File tickets
    tickets = create_linear_tickets(
        actions=ex.actions, team_id=route.team_id, project_id=route.project_id,
        wiki_link=wiki_link, linear_api_key=cfg.linear_api_key,
    )
    status = "ok" if len(tickets) == len(ex.actions) else "partial"

    # Persist results to frontmatter (only succeeded ticket IDs)
    rewrite_frontmatter(page_path, {
        "tickets": [t.identifier for t in tickets],
        "action_portfolio": portfolio,
        "action_status": status,
    })

    batch_results.append(BatchResult(
        plaud_id=plaud_id, title=title, wiki_path=wiki_link,
        portfolio=portfolio, tickets=tickets, status=status,
    ))
```

- [ ] **Step 4: Tests pass**

```bash
pytest tests/test_plaud_actions.py -v 2>&1 | tail -10
```
Expected: 39 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add scripts/plaud_actions.py tests/test_plaud_actions.py
git commit -m "feat(plaud-actions): process() orchestrator with all error paths (Task 9)"
```

---

## Task 10: send_batch_digest — delivery (TDD)

**Files:**
- Modify: `scripts/plaud_actions.py`
- Modify: `tests/test_plaud_actions.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_plaud_actions.py`:
```python
def test_send_batch_digest_calls_notify_with_built_text(tmp_path):
    from types import SimpleNamespace
    notifs: list = []
    cfg = SimpleNamespace(
        bot_token="t", chat_id="c",
        notify_fn=lambda **k: notifs.append(k),
    )
    brs = [plaud_actions.BatchResult(
        plaud_id="a", title="Meeting", wiki_path="plaud/a",
        portfolio="ccw-crm",
        tickets=[plaud_actions.TicketRef("i", "CCW-1", "")],
        status="ok")]
    plaud_actions.send_batch_digest(cfg, brs)
    assert len(notifs) == 1
    assert "Meeting" in notifs[0]["text"]
    assert "CCW-1" in notifs[0]["text"]


def test_send_batch_digest_silent_when_no_tickets(tmp_path):
    from types import SimpleNamespace
    notifs: list = []
    cfg = SimpleNamespace(
        bot_token="t", chat_id="c",
        notify_fn=lambda **k: notifs.append(k),
    )
    brs = [plaud_actions.BatchResult(plaud_id="a", title="t",
        wiki_path="p", portfolio="x", tickets=[], status="no_actions")]
    plaud_actions.send_batch_digest(cfg, brs)
    assert notifs == []


def test_send_batch_digest_empty_list_silent(tmp_path):
    from types import SimpleNamespace
    notifs: list = []
    cfg = SimpleNamespace(
        bot_token="t", chat_id="c",
        notify_fn=lambda **k: notifs.append(k),
    )
    plaud_actions.send_batch_digest(cfg, [])
    assert notifs == []
```

- [ ] **Step 2: Run, expect failure**

```bash
pytest tests/test_plaud_actions.py -k send_batch_digest -v
```
Expected: 3 failures.

- [ ] **Step 3: Implement**

Append to `scripts/plaud_actions.py`:
```python
def send_batch_digest(cfg, batch_results: list[BatchResult]) -> None:
    """Compose and send ONE Telegram DM covering the whole batch. Silent when
    no tickets were filed. Uses cfg.notify_fn — same callable used by
    plaud_ingest.notify_margot."""
    text = build_digest_text(batch_results)
    if text is None:
        return
    cfg.notify_fn(bot_token=cfg.bot_token, chat_id=cfg.chat_id, text=text)
```

- [ ] **Step 4: Tests pass**

```bash
pytest tests/test_plaud_actions.py -v 2>&1 | tail -5
```
Expected: 42 passed.

- [ ] **Step 5: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add scripts/plaud_actions.py tests/test_plaud_actions.py
git commit -m "feat(plaud-actions): send_batch_digest delivery (Task 10)"
```

---

## Task 11: Wire into plaud_ingest.py — 3 surgical edits

**Files:**
- Modify: `scripts/plaud_ingest.py`

This is integration. Three small edits.

- [ ] **Step 1: Add the import at the top of plaud_ingest.py**

Open `~/Pi-CEO/Pi-Dev-Ops/scripts/plaud_ingest.py`. Below the existing `from contextlib import asynccontextmanager` line near the connect_real_plaud section (or wherever module-level imports cluster), append:

```python
import plaud_actions
```

(`scripts/` is on `sys.path` per the existing module pattern — `plaud_actions.py` lives next to `plaud_ingest.py`, no path manipulation needed.)

Verify by running:
```bash
python3 -c "import sys; sys.path.insert(0, '/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/scripts'); import plaud_ingest; print('OK')"
```
Expected: `OK`. If `ModuleNotFoundError: plaud_actions`, the import path is wrong — fix before continuing.

- [ ] **Step 2: Wire IngestConfig to carry the new fields**

Find the `@dataclass class IngestConfig:` block in `plaud_ingest.py`. Add three new fields at the bottom:
```python
    anthropic_api_key: str = ""
    linear_api_key: str = ""
    projects_json_path: Path = Path.home() / "Pi-CEO" / "Pi-Dev-Ops" / ".harness" / "projects.json"
```

Then find `_build_default_config` and add to the `IngestConfig(...)` call:
```python
        anthropic_api_key=env.get("ANTHROPIC_API_KEY", ""),
        linear_api_key=env.get("LINEAR_API_KEY", ""),
```

- [ ] **Step 3: Add the per-recording call**

In `_ingest_one`, after the existing `for i, segs in enumerate(parts, start=1):` loop that calls `write_page`, BEFORE the function returns, add:

```python
    # Sub-project 2: action extraction + Linear filing (env-gated)
    if written and os.environ.get("PLAUD_ACTIONS_ENABLED", "1") != "0":
        try:
            plaud_actions.process(
                plaud_id=plaud_id,
                page_path=written[0],
                file_meta=file_meta,
                batch_results=cfg.batch_results,
                cfg=cfg,
            )
        except Exception as e:
            log.warning("plaud_actions.process raised for %s: %s", plaud_id, e)
```

(`cfg.batch_results` is added next — see Step 4.)

- [ ] **Step 4: Pass batch_results through run_once**

In `run_once`, near the top of the lock block where state/now_iso are initialized, add:
```python
        cfg.batch_results = []
```

Then AFTER the for-f-in-new_files loop completes, BEFORE the existing `regenerate_plaud_index` line, add:
```python
        # Sub-project 2: one Telegram digest per cron batch
        if cfg.batch_results and os.environ.get("PLAUD_ACTIONS_ENABLED", "1") != "0":
            try:
                plaud_actions.send_batch_digest(cfg, cfg.batch_results)
            except Exception as e:
                log.warning("send_batch_digest raised: %s", e)
```

Result dict gains two fields. Replace:
```python
        return {"ingested": ingested, "deferred": deferred, "status": "ok", "error": None}
```
with:
```python
        tickets_total = sum(len(br.tickets) for br in cfg.batch_results)
        portfolios = sorted({br.portfolio for br in cfg.batch_results if br.portfolio})
        return {
            "ingested": ingested, "deferred": deferred,
            "tickets_created": tickets_total,
            "portfolios_touched": portfolios,
            "status": "ok", "error": None,
        }
```

- [ ] **Step 5: Sanity check — existing tests still pass**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops && pytest tests/test_plaud_ingest.py tests/test_plaud_actions.py -q 2>&1 | tail -5
```
Expected: 83 passed (41 from plaud_ingest + 42 from plaud_actions).

If existing tests fail because IngestConfig has new required fields, you missed the default values in Step 2. Re-read Step 2 — every new field has a default.

- [ ] **Step 6: Smoke test — dry run**

```bash
PLAUD_ACTIONS_ENABLED=0 python3 ~/Pi-CEO/Pi-Dev-Ops/scripts/plaud_ingest.py --dry-run 2>&1 | tail -3
```
Expected: prints a JSON result line with `"tickets_created": 0, "portfolios_touched": []`. Confirms the module loads, the new fields show up, and the kill switch works.

- [ ] **Step 7: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add scripts/plaud_ingest.py
git commit -m "feat(plaud-ingest): wire plaud_actions into the ingest cron (Task 11)"
```

---

## Task 12: Live integration test (opt-in)

**Files:**
- Create: `tests/test_plaud_actions_live.py`

- [ ] **Step 1: Write the live test**

Create `~/Pi-CEO/Pi-Dev-Ops/tests/test_plaud_actions_live.py`:
```python
"""Live integration test — calls REAL Anthropic + REAL Linear. Opt-in via
RUN_PLAUD_LIVE=1. Requires ANTHROPIC_API_KEY + LINEAR_API_KEY +
PLAUD_LIVE_TEST_PROJECT_ID env vars to be set. Files ONE ticket to the
designated test project; ticket is NOT archived (no archive support in
linear_helpers); user clears it periodically.
"""
import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import plaud_actions


def _load_env(path: Path) -> dict:
    env: dict = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        env[k.strip()] = v.strip().strip("'\"")
    return env


TEST_PAGE = """---
type: plaud-recording
plaud_id: live-test
duration_human: 1m00s
---

# Live test recording — please ignore

Quick note: Sarah from RestoreAssist needs the new compliance UI by next
Tuesday. Also, send John the IICRC content draft.
"""


@pytest.mark.skipif(os.environ.get("RUN_PLAUD_LIVE") != "1",
                    reason="set RUN_PLAUD_LIVE=1 to run live Anthropic + Linear test")
def test_live_extract_and_file_one_ticket(tmp_path):
    env = _load_env(Path.home() / ".hermes" / ".env")
    anthropic_key = env.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
    linear_key = env.get("LINEAR_API_KEY") or os.environ.get("LINEAR_API_KEY")
    test_project_id = env.get("PLAUD_LIVE_TEST_PROJECT_ID") or os.environ.get("PLAUD_LIVE_TEST_PROJECT_ID")

    assert anthropic_key, "ANTHROPIC_API_KEY not in ~/.hermes/.env"
    assert linear_key, "LINEAR_API_KEY not in ~/.hermes/.env"
    assert test_project_id, "PLAUD_LIVE_TEST_PROJECT_ID not set (create Plaud Actions Test project in Linear, paste UUID)"

    # Step 1 — Anthropic extraction
    ex = plaud_actions.extract_actions(page_md=TEST_PAGE, anthropic_api_key=anthropic_key)
    assert isinstance(ex, plaud_actions.ActionExtraction), \
        f"expected ActionExtraction, got {type(ex).__name__}"
    assert ex.portfolio in {"restoreassist", "carsi", "unknown", "pi-dev-ops"}, \
        f"unexpected portfolio: {ex.portfolio}"
    assert 0.0 <= ex.confidence <= 1.0
    assert len(ex.actions) >= 1, "expected at least one action from the test page"

    # Step 2 — File ONE Linear ticket (the first action) into the test project
    from linear_helpers import create_linear_issue
    ref = create_linear_issue(
        api_key=linear_key,
        title=f"[live-test] {ex.actions[0].title}",
        description=f"{ex.actions[0].description}\n\n---\n_Created by plaud-actions live test._",
        team_id="a8a52f07-63cf-4ece-9ad2-3e3bd3c15673",  # RA team
        project_id=test_project_id,
        priority=4,  # Low — this is a test ticket
    )
    assert ref is not None, "Linear create_issue returned None — check key + project_id"
    assert ref.identifier  # e.g. "RA-2401"
    print(f"\nCreated test ticket: {ref.identifier} ({ref.url})")
    print(f"REMINDER: delete this ticket manually in Linear when convenient.")
```

- [ ] **Step 2: Run the unit suite (should still pass)**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops && pytest tests/test_plaud_actions.py tests/test_plaud_actions_live.py -q 2>&1 | tail -5
```
Expected: 42 passed, 1 skipped (live test gated).

- [ ] **Step 3: Run the live test (requires env config)**

```bash
RUN_PLAUD_LIVE=1 pytest tests/test_plaud_actions_live.py -v -s 2>&1 | tail -15
```
Expected: `1 passed`. Test prints "Created test ticket: RA-XXXX" — go delete it in Linear UI when convenient.

If the test fails on `ACTIONS_extracted < 1`, the prompt may need tuning — adjust the example in `scripts/prompts/action_extraction.md` and re-run. Don't change the assertion to make a test pass.

- [ ] **Step 4: Commit**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
git add tests/test_plaud_actions_live.py
git commit -m "test(plaud-actions): live integration test gated by RUN_PLAUD_LIVE=1 (Task 12)"
```

---

## Post-implementation acceptance checklist

Once all 12 tasks are merged, work through these against the running system:

- [ ] Reload LaunchAgent: `launchctl bootout gui/501/com.phillmcgurk.plaud-ingest && launchctl bootstrap gui/501 ~/Library/LaunchAgents/com.phillmcgurk.plaud-ingest.plist`
- [ ] Kickstart: `launchctl kickstart -k gui/501/com.phillmcgurk.plaud-ingest`
- [ ] Wait 30s, inspect: `cat ~/.hermes/logs/plaud-ingest.out` shows `tickets_created` field in JSON
- [ ] Record a meeting-style 60-sec test note with actual action items → wait 10 min after Plaud finishes processing → confirm wiki page has `tickets:` frontmatter + Linear tickets exist + Telegram digest DM received (PiMargot_bot must be `/start`ed)
- [ ] Record a stream-of-consciousness voice memo → wait 10 min → confirm wiki page has `action_status: no_actions` but no `tickets:` field; no Linear tickets; no digest DM
- [ ] Set `PLAUD_ACTIONS_ENABLED=0`, record another → confirm zero action processing; re-enable + kickstart → next tick fills in
- [ ] Re-running on an already-processed wiki page (kickstart twice in a row) does NOT create duplicate tickets
- [ ] Manual frontmatter override: delete `tickets:` line from a wiki page, kickstart → ticket created fresh

When all checked, sub-project 2 is shipped. Sub-project 3 (live in-meeting display) is the remaining work.
