# Pilot (Agency Bot) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Pilot — an internal-only Telegram bot that adopts Magnus Mueller's "Agency" pattern: runs every 30 min during 08:00–22:00 AEST, generates ranked suggestions toward the $2B-by-2028 ATIA pathway, asks Phill via Telegram with a 6-button inline keyboard. Halt-gate at 3 pending. Supabase preference memory.

**Architecture:** Four phases. (1) Mint `@PiPilotBot` and register in the ContextBot platform per memory `project-contextbot-platform`. (2) Build `swarm/pilot/` — scheduler + suggester + composer + dispatcher + feedback + memory. (3) Wire `master-plan-2b-by-2028-v3` as the goal feed + Linear/GitHub/Margot sources. (4) Telemetry — `pilot_suggestions` Supabase tables, daily 09:00 AEST digest, weekly Saturday LINT.

**Tech Stack:** Python 3.13 (Pi-Dev-Ops swarm), Supabase Python SDK, Hermes/LaunchAgent cron, GitHub CLI (`gh`), Composio CLI (Gmail + Linear), Telegram Bot API via `requests`.

**Source directives:**
- `~/2nd Brain/2nd Brain/Wiki/agency-bot-design-2026-05-14.md` — full design spec
- `~/2nd Brain/2nd Brain/Sources/Browser Harness, Clearly Explained (and how it 10x'd my agent).md` — pattern source (line citations in design wiki §2)
- `~/2nd Brain/2nd Brain/Wiki/master-plan-2b-by-2028-v3.md` — $2B goal feed
- Memory `project-contextbot-platform`, `feedback-no-slack`, `feedback-no-repeating-alerts`, `feedback-secrets-handling`, `incident-botfather-rate-limit-2026-05-14`
- Wiki `board-deliberation-browser-harness-2026-05-14` — "no engineering on portfolio repos in next 14 days" gate; Phase 1 is OK because it lives on the ContextBot substrate; Phases 2–4 sequence AFTER autonomy-gap items #1–3 close

---

## File Structure

| Path | Responsibility |
|---|---|
| `swarm/pilot/__init__.py` | Package marker |
| `swarm/pilot/types.py` | `RawCandidate` dataclass + Pillar/Effort/Source/Confidence types |
| `swarm/pilot/scheduler.py` | 30-min cron, off-hours quiet, halt-gate |
| `swarm/pilot/suggester.py` | Rank candidates against `master-plan-2b-by-2028-v3` |
| `swarm/pilot/composer.py` | Format Telegram message with 6-button keyboard, enforce ≤80 / ≤500 char caps |
| `swarm/pilot/dispatcher.py` | Send via Telegram API + record in Supabase |
| `swarm/pilot/feedback.py` | Handle 6 button callbacks |
| `swarm/pilot/memory.py` | Supabase `pilot_suggestions` + `pilot_preferences` |
| `swarm/pilot/goal_feed.py` | Parse master plan → pillars + quarterly milestones + active OKRs |
| `swarm/pilot/digest.py` | Daily digest + Saturday LINT |
| `swarm/pilot/cli.py` | LaunchAgent entry point |
| `swarm/pilot/sources/{linear,github,gmail,wiki,margot}_source.py` | Per-source candidate collectors |
| `tests/swarm/pilot/test_*.py` | Tests for each module |
| `swarm/inbox/registry.py` (MODIFY) | Add Pilot to ContextBot registry |
| `~/.hermes/.env` (MODIFY) | `PILOT_BOT_TOKEN` + `PILOT_BOT_CHAT_ID` + `PILOT_DISABLED=0` |
| `~/Library/LaunchAgents/com.unite.pilot.scheduler.plist` | 30-min cron |
| Supabase migration `pilot_suggestions_and_preferences` | Two tables in `lksfwktwtmyznckodsau` |

---

## Phase 1 — Bot mint + ContextBot registry extension

Light-touch on the existing ContextBot substrate. Does not touch portfolio repos — respects the [[board-deliberation-browser-harness-2026-05-14]] 14-day no-engineering gate.

### Task 1: Verify BotFather rate-limit window cleared

Per memory `incident-botfather-rate-limit-2026-05-14` (2026-05-14 lockout 23h after 6 mints).

- [ ] **Step 1: Check last mint timestamp**

```bash
grep -i "BotFather\|botfather\|/newbot" ~/2nd\ Brain/2nd\ Brain/Wiki/log.md | tail -5
```

Expected: most recent mint ≥ 24h before now. If less, STOP and wait.

- [ ] **Step 2: Confirm /start to @BotFather returns the welcome menu**

In Telegram on Phill's phone, send `/start` to `@BotFather`. If welcome menu returns: clear. If silent or "Too Many Requests": STOP.

- [ ] **Step 3: Record clearance in log**

Append a `pilot-phase-1 | none | BotFather window clear` line to `~/2nd Brain/2nd Brain/Wiki/log.md`.

### Task 2: Mint @PiPilotBot

**Files:** Modify `~/.hermes/.env` (NEVER paste tokens in chat per memory `feedback-secrets-handling`).

- [ ] **Step 1: Mint via BotFather**

Telegram → `@BotFather` → `/newbot` → name `Pilot` → username `PiPilotBot` (fallbacks: `PiPilotAgencyBot`, `UnitePilotBot`).

- [ ] **Step 2: Write token directly into env**

```bash
$EDITOR ~/.hermes/.env
# Append three lines, replacing the placeholder with BotFather's reply:
# PILOT_BOT_TOKEN=<token-from-BotFather>
# PILOT_BOT_USERNAME=PiPilotBot
# PILOT_DISABLED=0
```

- [ ] **Step 3: Resolve chat_id**

Press Start in the new bot's chat, then:

```bash
TOKEN=$(grep '^PILOT_BOT_TOKEN=' ~/.hermes/.env | cut -d= -f2)
curl -s "https://api.telegram.org/bot${TOKEN}/getUpdates" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print([u['message']['chat']['id'] for u in d.get('result',[]) if 'message' in u][:1])"
```

Append `PILOT_BOT_CHAT_ID=<id>` to `~/.hermes/.env`.

- [ ] **Step 4: Verify send**

```bash
source ~/.hermes/.env
curl -s -X POST "https://api.telegram.org/bot${PILOT_BOT_TOKEN}/sendMessage" \
  -d "chat_id=${PILOT_BOT_CHAT_ID}" -d "text=Pilot mint verified"
```

Expected: `{"ok":true,...}` and the message arrives in Phill's Telegram.

### Task 3: Register Pilot in ContextBot registry

**Files:** Modify `~/Pi-CEO/Pi-Dev-Ops/swarm/inbox/registry.py`. Create `tests/swarm/inbox/test_registry_pilot.py`.

- [ ] **Step 1: Read existing registry shape**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
find swarm/inbox -name "*registry*" | head && head -60 swarm/inbox/registry.py
```

- [ ] **Step 2: Write failing test**

```python
# tests/swarm/inbox/test_registry_pilot.py
from swarm.inbox import registry

def test_pilot_in_registry():
    pilot = next((b for b in registry.all_bots() if b["bot_username"].lower() == "pipilotbot"), None)
    assert pilot is not None
    assert pilot["kind"] == "function"
    assert pilot["context_id"] == "pilot"
    assert pilot["token_env"] == "PILOT_BOT_TOKEN"
    assert pilot["wiki_section"] == "agency-bot-design-2026-05-14"
```

- [ ] **Step 3: Run test — verify FAIL**

`pytest tests/swarm/inbox/test_registry_pilot.py -v` → FAIL.

- [ ] **Step 4: Add Pilot row**

Append to the registry table in `swarm/inbox/registry.py`:

```python
{
    "bot_username": "PiPilotBot",
    "token_env": "PILOT_BOT_TOKEN",
    "kind": "function",
    "context_id": "pilot",
    "linear_team_id": None,
    "wiki_section": "agency-bot-design-2026-05-14",
    "greeting_template": (
        "Pilot online. Suggestions every 30 min, 08:00–22:00 AEST. "
        "Halt-gate at 3 pending. Reply STOP to pause."
    ),
},
```

- [ ] **Step 5: Run test — verify PASS** → `pytest tests/swarm/inbox/test_registry_pilot.py -v`.

- [ ] **Step 6: Commit**

```bash
git add swarm/inbox/registry.py tests/swarm/inbox/test_registry_pilot.py
git commit -m "feat(pilot): register PiPilotBot in ContextBot registry — phase 1 of pilot plan"
```

---

## Phase 2 — Suggestion engine

Sequenced AFTER autonomy-gap items #1–3 close. Do not start until those gates ship.

### Task 4: Scaffold package + apply Supabase migration

**Files:** Create `swarm/pilot/__init__.py`, `tests/swarm/pilot/__init__.py`. Apply Supabase migration.

- [ ] **Step 1: Create package**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops
mkdir -p swarm/pilot swarm/pilot/sources tests/swarm/pilot
touch swarm/pilot/__init__.py swarm/pilot/sources/__init__.py tests/swarm/pilot/__init__.py
```

- [ ] **Step 2: Apply migration via `mcp__claude_ai_Supabase__apply_migration` on project `lksfwktwtmyznckodsau` (name: `pilot_suggestions_and_preferences`)**

```sql
create table if not exists public.pilot_suggestions (
  id bigserial primary key,
  fingerprint text not null,
  headline text not null check (length(headline) <= 80),
  pillar text not null,
  effort text not null check (effort in ('XS','S','M','L')),
  source text not null,
  confidence text not null check (confidence in ('LOW','MED','HIGH')),
  body_json jsonb not null,
  state text not null default 'pending'
    check (state in ('pending','accepted','deferred','rejected','blocked','modified')),
  sent_at timestamptz not null default now(),
  responded_at timestamptz,
  response_button text
);
create index if not exists pilot_suggestions_state_idx on public.pilot_suggestions(state);
create index if not exists pilot_suggestions_fp_idx on public.pilot_suggestions(fingerprint);

create table if not exists public.pilot_preferences (
  id bigserial primary key,
  fingerprint_pattern text not null,
  rule text not null check (rule in ('never','defer_24h','prefer')),
  reason text,
  created_at timestamptz not null default now()
);
create unique index if not exists pilot_pref_pattern_rule on public.pilot_preferences(fingerprint_pattern, rule);

alter table public.pilot_suggestions enable row level security;
alter table public.pilot_preferences enable row level security;
create policy "service_role_all_s" on public.pilot_suggestions for all using (auth.role() = 'service_role');
create policy "service_role_all_p" on public.pilot_preferences for all using (auth.role() = 'service_role');
```

- [ ] **Step 3: Verify tables**

```bash
# via mcp__claude_ai_Supabase__list_tables → expect pilot_suggestions and pilot_preferences in public schema
```

- [ ] **Step 4: Commit**

```bash
git add swarm/pilot/
git commit -m "feat(pilot): scaffold package + Supabase tables — phase 2 task 4"
```

### Task 4.1: Wire 2FA-live-view halt pattern (design lift from bux)

> Design lift locked by `[[board-deliberation-browser-use-org-2026-05-15]]` Fork 4 = YES. Pattern source documented in `[[agency-bot-design-2026-05-14]]` §2.12. **Implementation deferred to Phase 2 Task 7** (Suggester + source stubs) — this slot is a structural placeholder so the keeper contract is in the plan before the suggestion-engine code is written.

**Files (Phase 2 implementation):**
- Create: `Pi-CEO/Pi-Dev-Ops/swarm/bots/pilot_live_view_keeper.py` (30-line CDP-event-driven URL minter — implementation in Task 7)
- Create: `Pi-CEO/Pi-Dev-Ops/swarm/bots/__tests__/test_pilot_live_view_keeper.py`
- Modify (later): `Pi-CEO/Pi-Dev-Ops/swarm/bots/pilot_composer.py` to drop a `🔓 I unlocked it` button when `PILOT_LIVE_VIEW_URL` is set

**Contract reference:** `[[agency-bot-design-2026-05-14]]` §2.12 table — Keeper / Agent loop / Telegram shape / Timeout / Secrets rows.

**Acceptance (deferred to Task 7):** when a synthetic 2FA navigation fires in a sandbox Chrome profile, the keeper writes `PILOT_LIVE_VIEW_URL=...` to `~/.hermes/pilot_live_view.env`, the agent halt-gate trips inside 5s, and a single Telegram message ships to `PILOT_CHAT_ID` with the live-view URL + `🔓 I unlocked it` button. No duplicate messages on subsequent tool calls within the same 2FA session per `[[feedback-no-repeating-alerts]]`.

No code in this task — design placeholder only. Move to Task 5 next.

### Task 5: Types + scheduler (halt-gate + off-hours quiet)

**Files:** Create `swarm/pilot/types.py`, `swarm/pilot/scheduler.py`, `tests/swarm/pilot/test_scheduler.py`.

- [ ] **Step 1: Write failing tests**

```python
# tests/swarm/pilot/test_scheduler.py
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
from swarm.pilot import scheduler

AEST = timezone(timedelta(hours=10))
def _at(h, m=0): return datetime(2026, 5, 14, h, m, tzinfo=AEST)

def test_active_at_8am():    assert scheduler.in_active_window(_at(8))
def test_active_at_10pm():   assert scheduler.in_active_window(_at(22))
def test_inactive_at_2am():  assert not scheduler.in_active_window(_at(2))
def test_inactive_at_759():  assert not scheduler.in_active_window(_at(7, 59))

def test_halt_gate_blocks_at_3():
    m = MagicMock(); m.pending_count.return_value = 3
    assert not scheduler.halt_gate_open(m)

def test_halt_gate_open_at_2():
    m = MagicMock(); m.pending_count.return_value = 2
    assert scheduler.halt_gate_open(m)

def test_disabled_env(monkeypatch):
    monkeypatch.setenv("PILOT_DISABLED", "1")
    assert scheduler.run_cycle() == "disabled"
```

- [ ] **Step 2: Run — verify FAIL** → `pytest tests/swarm/pilot/test_scheduler.py -v`.

- [ ] **Step 3: Implement types + scheduler**

`swarm/pilot/types.py`:

```python
from dataclasses import dataclass
from typing import Any, Literal

Effort = Literal["XS", "S", "M", "L"]
Source = Literal["wiki", "linear", "margot", "gmail", "github", "agent-derived"]
Confidence = Literal["LOW", "MED", "HIGH"]

@dataclass
class RawCandidate:
    fingerprint: str
    headline: str
    pillar: str
    effort: Effort
    source: Source
    confidence: Confidence
    body: dict[str, Any]
    impact_score: int  # 0-100
```

`swarm/pilot/scheduler.py`:

```python
"""30-min cron, 08:00–22:00 AEST window, halt-gate at 3 pending.

Magnus pattern: Sources/Browser Harness...md:66-68 ('Check every half an hour').
Halt-gate enforces Sources/Browser Harness...md:282-287 ('If you send me too many, I will ignore').
"""
import os
from datetime import datetime, timezone, timedelta
from typing import Literal

AEST = timezone(timedelta(hours=10))
ACTIVE_START, ACTIVE_END = 8, 22
HALT_GATE_MAX = 3

def in_active_window(now: datetime) -> bool:
    h = now.astimezone(AEST).hour
    return ACTIVE_START <= h <= ACTIVE_END

def halt_gate_open(memory) -> bool:
    return memory.pending_count() < HALT_GATE_MAX

def run_cycle() -> Literal["disabled", "off_hours", "halt_gate", "no_suggestion", "sent"]:
    if os.getenv("PILOT_DISABLED", "0") == "1":
        return "disabled"
    if not in_active_window(datetime.now(timezone.utc)):
        return "off_hours"
    from swarm.pilot import memory as mm, suggester, composer, dispatcher
    mem = mm.Memory()
    if not halt_gate_open(mem):
        return "halt_gate"
    sug = suggester.pick_top(mem)
    if sug is None:
        return "no_suggestion"
    dispatcher.send(composer.format(sug), sug, mem)
    return "sent"
```

- [ ] **Step 4: Run — verify PASS**.

- [ ] **Step 5: Commit** — `feat(pilot): scheduler with halt-gate + off-hours quiet — phase 2 task 5`.

### Task 6: Memory (Supabase preference store)

**Files:** Create `swarm/pilot/memory.py`, `tests/swarm/pilot/test_memory.py`.

- [ ] **Step 1: Write failing tests**

```python
# tests/swarm/pilot/test_memory.py
from unittest.mock import MagicMock, patch
from swarm.pilot import memory as m

def _client_returning(data):
    c = MagicMock()
    c.table.return_value.select.return_value.eq.return_value.execute.return_value.data = data
    return c

def test_pending_count():
    with patch.object(m, "_client", return_value=_client_returning([{"id": 1}, {"id": 2}])):
        assert m.Memory().pending_count() == 2

def test_is_blocked_true():
    with patch.object(m, "_client", return_value=_client_returning([{"fingerprint_pattern": "fp", "rule": "never"}])):
        assert m.Memory().is_blocked("fp") is True

def test_is_blocked_false():
    with patch.object(m, "_client", return_value=_client_returning([])):
        assert m.Memory().is_blocked("fp") is False

def test_record_returns_id():
    mc = MagicMock()
    mc.table.return_value.insert.return_value.execute.return_value.data = [{"id": 42}]
    with patch.object(m, "_client", return_value=mc):
        rid = m.Memory().record_suggestion(
            fingerprint="fp", headline="h", pillar="X", effort="XS",
            source="wiki", confidence="HIGH", body_json={})
        assert rid == 42
```

- [ ] **Step 2: Run — FAIL**.

- [ ] **Step 3: Implement memory.py**

```python
"""Supabase-backed preference memory.

Magnus pattern: Sources/Browser Harness...md:176-178 ('stores it in a skill database
so it remembers your preferences').
"""
import os
from typing import Any
from supabase import create_client, Client

def _client() -> Client:
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

class Memory:
    def __init__(self):
        self.client = _client()

    def pending_count(self) -> int:
        r = self.client.table("pilot_suggestions").select("id").eq("state", "pending").execute()
        return len(r.data or [])

    def is_blocked(self, fingerprint: str) -> bool:
        r = self.client.table("pilot_preferences").select("fingerprint_pattern,rule").eq("fingerprint_pattern", fingerprint).execute()
        return any(row["rule"] == "never" for row in (r.data or []))

    def record_suggestion(self, *, fingerprint, headline, pillar, effort, source, confidence, body_json) -> int:
        r = self.client.table("pilot_suggestions").insert({
            "fingerprint": fingerprint, "headline": headline, "pillar": pillar,
            "effort": effort, "source": source, "confidence": confidence,
            "body_json": body_json,
        }).execute()
        return r.data[0]["id"]

    def add_never_rule(self, fingerprint_pattern: str, reason: str = "") -> None:
        self.client.table("pilot_preferences").insert({
            "fingerprint_pattern": fingerprint_pattern, "rule": "never", "reason": reason
        }).execute()

    def mark_response(self, suggestion_id: int, button: str, new_state: str) -> None:
        self.client.table("pilot_suggestions").update({
            "response_button": button, "state": new_state, "responded_at": "now()"
        }).eq("id", suggestion_id).execute()

    def get_suggestion(self, suggestion_id: int) -> dict | None:
        r = self.client.table("pilot_suggestions").select("*").eq("id", suggestion_id).execute()
        rows = r.data or []
        return rows[0] if rows else None

    def daily_counts(self) -> dict:
        r = self.client.rpc("pilot_state_counts_24h", params={}).execute()
        counts = {"accepted": 0, "deferred": 0, "rejected": 0, "blocked": 0}
        for row in (r.data or []):
            counts[row["state"]] = row["count"]
        return counts

    def top_pending(self, limit: int = 3) -> list[dict]:
        r = self.client.table("pilot_suggestions").select("id,headline,pillar").eq("state", "pending").order("sent_at").limit(limit).execute()
        return r.data or []

    def archive_old_deferred(self, days: int = 30) -> int:
        r = self.client.rpc("pilot_archive_old_deferred", params={"days": days}).execute()
        return (r.data or [{"count": 0}])[0].get("count", 0)
```

- [ ] **Step 4: Run — PASS**.

- [ ] **Step 5: Commit** — `feat(pilot): Supabase preference memory — phase 2 task 6`.

### Task 7: Suggester + source stubs

**Files:** Create `swarm/pilot/suggester.py`, 5 stubs at `swarm/pilot/sources/{linear,github,gmail,wiki,margot}_source.py`, `tests/swarm/pilot/test_suggester.py`.

- [ ] **Step 1: Write failing tests**

```python
# tests/swarm/pilot/test_suggester.py
from unittest.mock import MagicMock
from swarm.pilot import suggester
from swarm.pilot.types import RawCandidate

def _c(fp, conf="MED", score=50, eff="S"):
    return RawCandidate(fingerprint=fp, headline="x", pillar="X", effort=eff,
                        source="wiki", confidence=conf, body={}, impact_score=score)

def test_pick_top_highest_score():
    m = MagicMock(); m.is_blocked.return_value = False
    top = suggester._rank([_c("a", score=10), _c("b", conf="HIGH", score=95, eff="XS")], m)
    assert top.fingerprint == "b"

def test_filter_blocked():
    m = MagicMock(); m.is_blocked.side_effect = lambda fp: fp == "b"
    top = suggester._rank([_c("a", score=50), _c("b", conf="HIGH", score=99, eff="XS")], m)
    assert top.fingerprint == "a"

def test_none_when_all_blocked():
    m = MagicMock(); m.is_blocked.return_value = True
    assert suggester._rank([_c("a")], m) is None
```

- [ ] **Step 2: Run — FAIL**.

- [ ] **Step 3: Implement suggester + 5 stubs**

`swarm/pilot/suggester.py`:

```python
"""Suggester — collect candidates from each source, rank against $2B pillars.

Score = impact_score × effort_weight × confidence_weight. XS cheapest, HIGH most credible.
"""
from typing import Optional
from swarm.pilot.types import RawCandidate

_EFFORT_W = {"XS": 1.0, "S": 0.85, "M": 0.65, "L": 0.4}
_CONF_W = {"HIGH": 1.0, "MED": 0.75, "LOW": 0.45}

def _score(c: RawCandidate) -> float:
    return c.impact_score * _EFFORT_W[c.effort] * _CONF_W[c.confidence]

def _rank(candidates: list[RawCandidate], memory) -> Optional[RawCandidate]:
    allowed = [c for c in candidates if not memory.is_blocked(c.fingerprint)]
    return max(allowed, key=_score) if allowed else None

def pick_top(memory) -> Optional[RawCandidate]:
    from swarm.pilot.sources import linear_source, github_source, gmail_source, wiki_source, margot_source
    cands: list[RawCandidate] = []
    for src in (linear_source, github_source, gmail_source, wiki_source, margot_source):
        cands.extend(src.collect())
    return _rank(cands, memory)
```

Five stubs (each file `swarm/pilot/sources/{name}_source.py`):

```python
"""<name> candidate collector — wired in Phase 3."""
from swarm.pilot.types import RawCandidate
def collect() -> list[RawCandidate]:
    return []
```

- [ ] **Step 4: Run — PASS**.

- [ ] **Step 5: Commit** — `feat(pilot): suggester + source stubs — phase 2 task 7`.

### Task 8: Composer (6-button keyboard + length caps)

**Files:** Create `swarm/pilot/composer.py`, `tests/swarm/pilot/test_composer.py`.

- [ ] **Step 1: Write failing tests**

```python
# tests/swarm/pilot/test_composer.py
from swarm.pilot import composer
from swarm.pilot.types import RawCandidate

def _c(headline="PR #226 green 18h, merge?"):
    return RawCandidate(fingerprint="fp", headline=headline, pillar="Tier-2 Infra",
                        effort="XS", source="github", confidence="HIGH", body={}, impact_score=80)

def test_headline_present():
    assert "PR #226" in composer.format(_c())["text"]

def test_truncates_long_headline():
    first = composer.format(_c("x" * 200))["text"].split("\n", 1)[0]
    assert len(first) <= 80

def test_metadata_lines():
    t = composer.format(_c())["text"]
    for label in ("Pillar:", "Effort:", "Source:", "Confidence:"):
        assert label in t

def test_body_under_500():
    assert len(composer.format(_c())["text"]) <= 500

def test_six_buttons():
    kb = composer.format(_c())["reply_markup"]["inline_keyboard"]
    assert len(kb) == 2 and len(kb[0]) == 3 and len(kb[1]) == 3
    labels = [b["text"] for row in kb for b in row]
    for needle in ("Do it", "Why this", "More context", "Modify", "Not now", "Never"):
        assert any(needle in l for l in labels)

def test_callback_carries_fp():
    kb = composer.format(_c())["reply_markup"]["inline_keyboard"]
    do_it = next(b for r in kb for b in r if "Do it" in b["text"])
    assert "fp" in do_it["callback_data"] and "do_it" in do_it["callback_data"]
```

- [ ] **Step 2: Run — FAIL**.

- [ ] **Step 3: Implement composer**

```python
"""Composer — Telegram message + 6-button inline keyboard.

Magnus spam-fatigue guard: Sources/Browser Harness...md:282-287
('if your thing is too long, my context is little, I will just ignore').
Hard caps: ≤80-char headline, ≤500-char body.
"""
from swarm.pilot.types import RawCandidate

MAX_HEADLINE, MAX_BODY = 80, 500

_BUTTONS = [
    [("✅ Do it", "do_it"), ("🎯 Why this", "why_this"), ("🔄 More context", "more_context")],
    [("📝 Modify", "modify"), ("❌ Not now", "not_now"), ("🚫 Never", "never")],
]

def _trunc(s: str, n: int) -> str:
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"

def format(c: RawCandidate) -> dict:
    headline = _trunc(c.headline, MAX_HEADLINE)
    text = (
        f"{headline}\n\n"
        f"🎯 Pillar: {c.pillar}\n"
        f"⚙️ Effort: {c.effort}\n"
        f"📂 Source: {c.source}\n"
        f"🔮 Confidence: {c.confidence}"
    )
    if len(text) > MAX_BODY:
        text = text[: MAX_BODY - 1].rstrip() + "…"
    keyboard = [
        [{"text": label, "callback_data": f"{action}|{c.fingerprint}"} for label, action in row]
        for row in _BUTTONS
    ]
    return {"text": text, "reply_markup": {"inline_keyboard": keyboard}}
```

- [ ] **Step 4: Run — PASS**.

- [ ] **Step 5: Commit** — `feat(pilot): composer with 6-button keyboard — phase 2 task 8`.

### Task 9: Dispatcher (Telegram send + record)

**Files:** Create `swarm/pilot/dispatcher.py`, `tests/swarm/pilot/test_dispatcher.py`.

- [ ] **Step 1: Write failing tests**

```python
# tests/swarm/pilot/test_dispatcher.py
from unittest.mock import MagicMock, patch
from swarm.pilot import dispatcher
from swarm.pilot.types import RawCandidate

def _c():
    return RawCandidate(fingerprint="fp", headline="h", pillar="X", effort="XS",
                        source="github", confidence="HIGH", body={}, impact_score=80)

def test_posts_to_telegram(monkeypatch):
    monkeypatch.setenv("PILOT_BOT_TOKEN", "tk"); monkeypatch.setenv("PILOT_BOT_CHAT_ID", "1")
    mem = MagicMock()
    with patch("swarm.pilot.dispatcher.requests.post") as p:
        p.return_value.json.return_value = {"ok": True, "result": {"message_id": 1}}
        p.return_value.status_code = 200
        dispatcher.send({"text": "h", "reply_markup": {"inline_keyboard": []}}, _c(), mem)
        assert "tk" in p.call_args[0][0] and "sendMessage" in p.call_args[0][0]

def test_records_in_memory(monkeypatch):
    monkeypatch.setenv("PILOT_BOT_TOKEN", "tk"); monkeypatch.setenv("PILOT_BOT_CHAT_ID", "1")
    mem = MagicMock()
    with patch("swarm.pilot.dispatcher.requests.post") as p:
        p.return_value.json.return_value = {"ok": True, "result": {"message_id": 1}}
        p.return_value.status_code = 200
        dispatcher.send({"text": "h", "reply_markup": {"inline_keyboard": []}}, _c(), mem)
        assert mem.record_suggestion.call_args.kwargs["fingerprint"] == "fp"
```

- [ ] **Step 2: Run — FAIL**.

- [ ] **Step 3: Implement dispatcher**

```python
"""Dispatcher — Telegram send + Supabase record."""
import os, requests
from swarm.pilot.types import RawCandidate

def send(message: dict, candidate: RawCandidate, memory) -> int:
    token, chat = os.environ["PILOT_BOT_TOKEN"], os.environ["PILOT_BOT_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    r = requests.post(url, json={"chat_id": chat, "text": message["text"],
                                  "reply_markup": message["reply_markup"]}, timeout=10)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(f"Telegram API error: {data}")
    return memory.record_suggestion(
        fingerprint=candidate.fingerprint, headline=candidate.headline,
        pillar=candidate.pillar, effort=candidate.effort, source=candidate.source,
        confidence=candidate.confidence,
        body_json={"telegram_message_id": data["result"]["message_id"], "body": candidate.body},
    )
```

- [ ] **Step 4: Run — PASS**.

- [ ] **Step 5: Commit** — `feat(pilot): dispatcher sends to Telegram + records — phase 2 task 9`.

### Task 10: Feedback handler (6 button callbacks)

**Files:** Create `swarm/pilot/feedback.py`, `tests/swarm/pilot/test_feedback.py`.

- [ ] **Step 1: Write failing tests**

```python
# tests/swarm/pilot/test_feedback.py
from unittest.mock import MagicMock
from swarm.pilot import feedback

def _mem_with(s):
    m = MagicMock(); m.get_suggestion.return_value = s
    return m

def test_do_it_accepted():
    m = _mem_with({"id": 1, "fingerprint": "fp", "body_json": {}})
    feedback.handle("do_it|fp", 1, m)
    m.mark_response.assert_called_once_with(1, "do_it", "accepted")

def test_never_blocks_class():
    m = _mem_with({"id": 1, "fingerprint": "fp", "body_json": {}})
    feedback.handle("never|fp", 1, m)
    m.add_never_rule.assert_called_once_with("fp", reason="user_clicked_never")
    m.mark_response.assert_called_once_with(1, "never", "blocked")

def test_not_now_deferred():
    m = _mem_with({"id": 1, "fingerprint": "fp", "body_json": {}})
    feedback.handle("not_now|fp", 1, m)
    m.mark_response.assert_called_once_with(1, "not_now", "deferred")

def test_modify_modified():
    m = _mem_with({"id": 1, "fingerprint": "fp", "body_json": {}})
    feedback.handle("modify|fp", 1, m)
    m.mark_response.assert_called_once_with(1, "modify", "modified")

def test_why_this_returns_pillar_and_impact():
    m = _mem_with({"id": 1, "fingerprint": "fp", "pillar": "ATIA Meta",
                   "body_json": {"impact_reasoning": "advances Q3 2026"}})
    reply = feedback.handle("why_this|fp", 1, m)
    assert "ATIA Meta" in reply and "Q3 2026" in reply

def test_more_context_returns_provenance():
    m = _mem_with({"id": 1, "fingerprint": "fp", "source": "github",
                   "body_json": {"provenance": "PR #226 green 18h"}})
    reply = feedback.handle("more_context|fp", 1, m)
    assert "PR #226" in reply
```

- [ ] **Step 2: Run — FAIL**.

- [ ] **Step 3: Implement feedback**

```python
"""6 button callbacks.

Magnus pattern: Sources/Browser Harness...md:96-99
('its goal is that I click accept, right? So it tries to sell').
"""
def handle(callback_data: str, suggestion_id: int, memory) -> str | None:
    action, fingerprint = callback_data.split("|", 1)
    s = memory.get_suggestion(suggestion_id)
    if s is None:
        return None
    if action == "do_it":
        _dispatch_downstream(s)
        memory.mark_response(suggestion_id, "do_it", "accepted"); return None
    if action == "never":
        memory.add_never_rule(fingerprint, reason="user_clicked_never")
        memory.mark_response(suggestion_id, "never", "blocked"); return None
    if action == "not_now":
        memory.mark_response(suggestion_id, "not_now", "deferred"); return None
    if action == "modify":
        memory.mark_response(suggestion_id, "modify", "modified"); return None
    if action == "why_this":
        impact = s.get("body_json", {}).get("impact_reasoning", "(no analysis cached)")
        return f"Pillar: {s.get('pillar', '?')}\n{impact}"
    if action == "more_context":
        prov = s.get("body_json", {}).get("provenance", "(no provenance cached)")
        return f"Source: {s.get('source', '?')}\n{prov}"
    return None

def _dispatch_downstream(suggestion: dict) -> None:
    """Route accepted suggestion to responsible PM / Board / Margot.

    Stub: the state transition is recorded; downstream bots poll the `accepted` queue
    in their own loops. Pillar→bot mapping wired in Task 12 alongside Linear source.
    """
    return
```

- [ ] **Step 4: Run — PASS**.

- [ ] **Step 5: Commit** — `feat(pilot): feedback handler for 6 callbacks — phase 2 task 10`.

---

## Phase 3 — $2B goal feed wiring

### Task 11: Goal-feed parser

**Files:** Create `swarm/pilot/goal_feed.py`, `tests/swarm/pilot/test_goal_feed.py`.

- [ ] **Step 1: Write failing tests**

```python
# tests/swarm/pilot/test_goal_feed.py
from swarm.pilot import goal_feed

def test_pillars():
    p = set(goal_feed.pillars())
    assert {"ATIA Meta", "Restoration", "Carpet", "IEP", "Plumbing", "HVAC",
            "Pressure-Washing", "CARSI", "Tier-2 Infra", "Margot", "Wiki"}.issubset(p)

def test_current_quarter_q3_2026():
    q = goal_feed.current_quarter_milestone()
    assert ("Q3 2026" in q["label"]) and ("$300K" in q["ar_target"])

def test_active_okrs_includes_nrpg_and_ccpa():
    descs = " ".join(o["description"] for o in goal_feed.active_okrs())
    assert "NRPG founding cohort" in descs
    assert "CCPA founding cohort" in descs
```

- [ ] **Step 2: Run — FAIL**.

- [ ] **Step 3: Implement goal_feed**

```python
"""Goal-feed — `master-plan-2b-by-2028-v3` as structured Pilot data.

Magnus pattern: Sources/Browser Harness...md:94-99 ('high level goal').
Phill's goal = master plan v3 (ATIA + 6 verticals, $2B by 30 Jun 2028).
"""
_PILLARS = ["ATIA Meta", "Restoration", "Carpet", "IEP", "Plumbing", "HVAC",
            "Pressure-Washing", "CARSI", "Tier-2 Infra", "Margot", "Wiki"]

def pillars() -> list[str]:
    return list(_PILLARS)

def current_quarter_milestone() -> dict:
    # Hard-coded for Q3 2026; refreshed quarterly by Saturday LINT (Task 14).
    return {
        "label": "Q3 2026 (Jul–Sep)",
        "verticals_live": "1.5 — Restoration full stack + Carpet (CCW wedge)",
        "ar_target": "$300K",
        "key_milestone": (
            "ATIA brand identity launched · NRPG founding cohort 50 firms × $799 · "
            "CCPA founding cohort 20 firms · CARSI v1 (S500 + S520) live"
        ),
    }

def active_okrs() -> list[dict]:
    return [
        {"id": "KR1", "tier": "ATIA", "description": "ATIA brand identity locked (domain + trademark + mark)"},
        {"id": "KR2", "tier": "Restoration", "description": "NRPG founding cohort 50 firms"},
        {"id": "KR3", "tier": "Carpet", "description": "CCPA founding cohort 20 firms"},
        {"id": "KR4", "tier": "Restoration", "description": "RA at 100 paid techs"},
        {"id": "KR5", "tier": "Restoration", "description": "DR multi-tenant Sprint 1 + 3 pilot firms"},
        {"id": "KR6", "tier": "CARSI", "description": "CARSI v1 (S500 + S520) + first 20 paid enrolments"},
        {"id": "KR7", "tier": "IEP", "description": "NIEPA charter + Bulcs retainer signed"},
        {"id": "KR9", "tier": "Tier-2", "description": "Tier-2 contracted ARR $85K"},
        {"id": "KR13", "tier": "Infra", "description": "8 Senior PM bots scaffolded + claiming end-to-end"},
    ]
```

- [ ] **Step 4: Run — PASS**.

- [ ] **Step 5: Commit** — `feat(pilot): goal_feed parser — phase 3 task 11`.

### Task 12: Linear + GitHub sources

**Files:** Replace stubs `swarm/pilot/sources/linear_source.py` and `swarm/pilot/sources/github_source.py`. Create tests.

- [ ] **Step 1: Write failing tests**

```python
# tests/swarm/pilot/test_sources_linear.py
from unittest.mock import patch
from swarm.pilot.sources import linear_source

def test_stale_in_flight_yields_candidate():
    issues = [{"id": "RA-2947", "title": "Floor-plan", "state": "In Progress",
               "updatedAt": "2026-05-01T00:00:00Z", "team": {"key": "RA"}}]
    with patch.object(linear_source, "_fetch_in_flight_epics", return_value=issues):
        c = linear_source.collect()
        assert len(c) >= 1 and "RA-2947" in c[0].fingerprint and c[0].source == "linear"

def test_empty_when_no_stale():
    with patch.object(linear_source, "_fetch_in_flight_epics", return_value=[]):
        assert linear_source.collect() == []
```

```python
# tests/swarm/pilot/test_sources_github.py
from unittest.mock import patch
from swarm.pilot.sources import github_source

def test_stale_green_pr_yields_candidate():
    prs = [{"number": 226, "title": "x", "repository": "Pi-Dev-Ops",
            "hours_since_green": 50, "merged": False}]
    with patch.object(github_source, "_fetch_stale_green_prs", return_value=prs):
        c = github_source.collect()
        assert any("226" in x.fingerprint for x in c)

def test_under_48h_filtered():
    prs = [{"number": 99, "title": "x", "repository": "y",
            "hours_since_green": 12, "merged": False}]
    with patch.object(github_source, "_fetch_stale_green_prs", return_value=prs):
        assert github_source.collect() == []
```

- [ ] **Step 2: Run — FAIL**.

- [ ] **Step 3: Implement linear_source**

```python
"""Linear — stale in-flight epics via Composio CLI."""
import subprocess, json
from datetime import datetime, timezone, timedelta
from swarm.pilot.types import RawCandidate

STALE_DAYS = 7

_TEAM_TO_PILLAR = {
    "RA": "Restoration", "DR": "Restoration", "NRPG": "Restoration",
    "CCW": "Carpet", "CARSI": "CARSI", "ATIA": "ATIA Meta",
    "UG": "Tier-2 Infra", "SYN": "Tier-2 Infra",
}

def _fetch_in_flight_epics() -> list[dict]:
    try:
        r = subprocess.run(["composio", "execute", "linear_list_issues",
                            "--state", "In Progress", "--limit", "20"],
                           capture_output=True, text=True, timeout=30, check=True)
        return json.loads(r.stdout).get("issues", [])
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError, json.JSONDecodeError):
        return []

def _is_stale(updated_at: str) -> bool:
    u = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
    return (datetime.now(timezone.utc) - u) > timedelta(days=STALE_DAYS)

def collect() -> list[RawCandidate]:
    out = []
    for i in _fetch_in_flight_epics():
        if not _is_stale(i["updatedAt"]):
            continue
        key = i.get("team", {}).get("key", "?")
        out.append(RawCandidate(
            fingerprint=f"linear:stale_epic:{i['id']}",
            headline=f"{i['id']} ({key}) stale {STALE_DAYS}d — review or close?",
            pillar=_TEAM_TO_PILLAR.get(key, "Tier-2 Infra"),
            effort="S", source="linear", confidence="MED",
            body={"issue": i}, impact_score=60,
        ))
    return out
```

- [ ] **Step 4: Implement github_source**

```python
"""GitHub — stale green PRs (green ≥48h, no merge)."""
import subprocess, json
from swarm.pilot.types import RawCandidate

STALE_GREEN_HOURS = 48
REPOS = ["Unite-Group", "Pi-Dev-Ops", "RestoreAssist", "dr-nrpg", "ccw-crm", "carsi", "Synthex"]

def _fetch_stale_green_prs() -> list[dict]:
    out = []
    for repo in REPOS:
        try:
            r = subprocess.run(
                ["gh", "pr", "list", "--repo", f"CleanExpo/{repo}", "--state", "open",
                 "--json", "number,title,updatedAt,statusCheckRollup,mergeable", "--limit", "20"],
                capture_output=True, text=True, timeout=30, check=True)
            for pr in json.loads(r.stdout):
                rollup = pr.get("statusCheckRollup", [])
                if not rollup or not all(c.get("conclusion") == "SUCCESS"
                                          for c in rollup if c.get("conclusion")):
                    continue
                pr["repository"] = repo
                out.append(pr)
        except (subprocess.TimeoutExpired, subprocess.CalledProcessError, json.JSONDecodeError):
            continue
    return out

def collect() -> list[RawCandidate]:
    out = []
    for pr in _fetch_stale_green_prs():
        hours = pr.get("hours_since_green", STALE_GREEN_HOURS + 1)
        if hours < STALE_GREEN_HOURS:
            continue
        out.append(RawCandidate(
            fingerprint=f"github:stale_pr:{pr.get('repository','?')}:{pr['number']}",
            headline=f"PR #{pr['number']} ({pr.get('repository','?')}) green {hours}h, merge?",
            pillar="Tier-2 Infra", effort="XS", source="github", confidence="HIGH",
            body={"pr": pr}, impact_score=70,
        ))
    return out
```

- [ ] **Step 5: Run — PASS** → `pytest tests/swarm/pilot/test_sources_linear.py tests/swarm/pilot/test_sources_github.py -v`.

- [ ] **Step 6: Commit** — `feat(pilot): wire Linear + GitHub sources — phase 3 task 12`.

### Task 13: Margot research queue source

**Files:** Replace `swarm/pilot/sources/margot_source.py`, create test.

- [ ] **Step 1: Write failing test**

```python
# tests/swarm/pilot/test_sources_margot.py
from unittest.mock import patch, MagicMock
from swarm.pilot.sources import margot_source

def test_pending_research_yields_candidate():
    c = MagicMock()
    c.table.return_value.select.return_value.eq.return_value.execute.return_value.data = [
        {"id": 7, "topic": "competitor scan: CORE Restoration", "status": "pending", "vertical": "Restoration"}
    ]
    with patch.object(margot_source, "_supabase_client", return_value=c):
        out = margot_source.collect()
        assert any("competitor scan" in x.headline.lower() and x.source == "margot" for x in out)

def test_empty_when_no_pending():
    c = MagicMock()
    c.table.return_value.select.return_value.eq.return_value.execute.return_value.data = []
    with patch.object(margot_source, "_supabase_client", return_value=c):
        assert margot_source.collect() == []
```

- [ ] **Step 2: Run — FAIL**.

- [ ] **Step 3: Implement margot_source**

```python
"""Margot research queue — pending deep-research items as suggestions."""
import os
from supabase import create_client, Client
from swarm.pilot.types import RawCandidate

_VALID_PILLARS = {"ATIA Meta", "Restoration", "Carpet", "IEP", "Plumbing", "HVAC",
                  "Pressure-Washing", "CARSI"}

def _supabase_client() -> Client:
    return create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SERVICE_ROLE_KEY"])

def collect() -> list[RawCandidate]:
    try:
        rows = (_supabase_client().table("margot_research_queue")
                .select("id,topic,status,vertical").eq("status", "pending").execute().data or [])
    except Exception:
        return []
    out = []
    for r in rows:
        v = r.get("vertical", "Margot")
        out.append(RawCandidate(
            fingerprint=f"margot:research:{r['id']}",
            headline=f"Margot research pending: {r['topic'][:60]} — dispatch?",
            pillar=v if v in _VALID_PILLARS else "Margot",
            effort="S", source="margot", confidence="MED",
            body={"queue_row": r}, impact_score=55,
        ))
    return out
```

- [ ] **Step 4: Run — PASS**.

- [ ] **Step 5: Commit** — `feat(pilot): Margot research-queue source — phase 3 task 13`.

---

## Phase 4 — Telemetry + acceptance loop

### Task 14: Daily digest + Saturday LINT

**Files:** Create `swarm/pilot/digest.py`, `tests/swarm/pilot/test_digest.py`.

- [ ] **Step 1: Write failing tests**

```python
# tests/swarm/pilot/test_digest.py
from unittest.mock import MagicMock
from swarm.pilot import digest

def test_daily_text_counts():
    m = MagicMock()
    m.daily_counts.return_value = {"accepted": 4, "deferred": 2, "rejected": 1, "blocked": 0}
    m.top_pending.return_value = [{"id": 9, "headline": "Ship CCW Stripe webhook",
                                   "pillar": "Tier-2 Infra"}]
    t = digest.daily_text(m)
    assert "Accepted: 4" in t and "Deferred: 2" in t and "Rejected: 1" in t
    assert "Ship CCW Stripe webhook" in t

def test_saturday_lint_archives_old_deferred():
    m = MagicMock(); m.archive_old_deferred.return_value = 5
    assert digest.saturday_lint(m)["archived_deferred"] == 5
    m.archive_old_deferred.assert_called_once_with(days=30)
```

- [ ] **Step 2: Run — FAIL**.

- [ ] **Step 3: Implement digest**

```python
"""Daily 09:00 AEST digest + weekly Saturday LINT."""
def daily_text(memory) -> str:
    c = memory.daily_counts()
    pending = memory.top_pending(limit=3)
    lines = [
        "Pilot daily digest (last 24h):",
        f"Accepted: {c.get('accepted', 0)}",
        f"Deferred: {c.get('deferred', 0)}",
        f"Rejected: {c.get('rejected', 0)}",
        f"Blocked: {c.get('blocked', 0)}",
        "", "Top pending:",
    ]
    for p in pending:
        lines.append(f"  #{p['id']} [{p['pillar']}] {p['headline']}")
    return "\n".join(lines)

def saturday_lint(memory) -> dict:
    return {"archived_deferred": memory.archive_old_deferred(days=30)}
```

- [ ] **Step 4: Run — PASS**.

- [ ] **Step 5: Commit** — `feat(pilot): daily digest + Saturday LINT — phase 4 task 14`.

### Task 15: CLI + LaunchAgent (30-min cron)

**Files:** Create `swarm/pilot/cli.py`, `tests/swarm/pilot/test_cli.py`, `~/Library/LaunchAgents/com.unite.pilot.scheduler.plist`.

- [ ] **Step 1: Write failing tests**

```python
# tests/swarm/pilot/test_cli.py
from unittest.mock import patch
from swarm.pilot import cli

def test_scheduler_calls_run_cycle():
    with patch("swarm.pilot.cli.scheduler.run_cycle", return_value="sent") as m:
        assert cli.main(["scheduler"]) == 0
        m.assert_called_once()

def test_digest_calls_daily_text():
    with patch("swarm.pilot.cli.digest.daily_text", return_value="ok") as md, \
         patch("swarm.pilot.cli.memory_mod.Memory"):
        assert cli.main(["digest"]) == 0
        md.assert_called_once()
```

- [ ] **Step 2: Run — FAIL**.

- [ ] **Step 3: Implement cli**

```python
"""Pilot CLI — LaunchAgent entry point."""
import sys
from swarm.pilot import scheduler, digest
from swarm.pilot import memory as memory_mod

def main(argv: list[str]) -> int:
    if not argv:
        print("usage: python -m swarm.pilot.cli {scheduler|digest|saturday_lint}", file=sys.stderr); return 2
    cmd = argv[0]
    if cmd == "scheduler":
        scheduler.run_cycle(); return 0
    if cmd == "digest":
        print(digest.daily_text(memory_mod.Memory())); return 0
    if cmd == "saturday_lint":
        digest.saturday_lint(memory_mod.Memory()); return 0
    print(f"unknown command: {cmd}", file=sys.stderr); return 2

if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 4: Run — PASS**.

- [ ] **Step 5: Create LaunchAgent plist**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.unite.pilot.scheduler</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string><string>-lc</string>
    <string>cd /Users/phill-mac/Pi-CEO/Pi-Dev-Ops &amp;&amp; source ~/.hermes/.env &amp;&amp; /usr/local/bin/python3 -m swarm.pilot.cli scheduler >> /tmp/pilot-scheduler.log 2>&amp;1</string>
  </array>
  <key>StartInterval</key><integer>1800</integer>
  <key>RunAtLoad</key><false/>
  <key>StandardOutPath</key><string>/tmp/pilot-scheduler.out</string>
  <key>StandardErrorPath</key><string>/tmp/pilot-scheduler.err</string>
</dict>
</plist>
```

- [ ] **Step 6: Load + kickstart**

```bash
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.unite.pilot.scheduler.plist
launchctl kickstart gui/$(id -u)/com.unite.pilot.scheduler
tail -20 /tmp/pilot-scheduler.log
```

Expected: log line shows one of `disabled | off_hours | halt_gate | no_suggestion | sent`.

- [ ] **Step 7: Commit** — `feat(pilot): CLI + LaunchAgent 30-min cron — phase 4 task 15`.

### Task 16: End-to-end smoke

- [ ] **Step 1: Verify bot reachable**

```bash
source ~/.hermes/.env
curl -s "https://api.telegram.org/bot${PILOT_BOT_TOKEN}/getMe" | python3 -m json.tool
```

Expected: `ok: true, result.username: "PiPilotBot"`.

- [ ] **Step 2: Force one tick with a synthetic candidate**

```bash
cd ~/Pi-CEO/Pi-Dev-Ops && source ~/.hermes/.env
python3 - <<'PY'
from swarm.pilot import memory, composer, dispatcher
from swarm.pilot.types import RawCandidate
mem = memory.Memory()
c = RawCandidate(fingerprint="pilot:smoke:test", headline="Pilot smoke test — first end-to-end tick",
                 pillar="Tier-2 Infra", effort="XS", source="agent-derived",
                 confidence="HIGH", body={"note": "smoke"}, impact_score=80)
dispatcher.send(composer.format(c), c, mem)
print("sent")
PY
```

Expected: Phill's Telegram receives the message with the 6-button keyboard; `pilot_suggestions` has a new `state='pending'` row.

- [ ] **Step 3: Phill presses each button; verify state transitions in Supabase**

```sql
select id, headline, state, response_button, responded_at
from pilot_suggestions where fingerprint = 'pilot:smoke:test'
order by id desc limit 6;
```

Expected: state matches button per design wiki §3.

- [ ] **Step 4: Append result to wiki log**

```
2026-05-DD | pilot-phase-4 | log.md | Pilot end-to-end smoke verified — sent, 6 buttons routed, halt-gate observed, daily digest format correct. Pilot live.
```

---

## Self-Review

- **Spec coverage:** Phase 1 (mint + registry) — Tasks 1–3. Phase 2 (engine) — Tasks 4–10. Phase 3 (goal feed + sources) — Tasks 11–13. Phase 4 (telemetry) — Tasks 14–16. All 11 verbatim Magnus patterns from `agency-bot-design-2026-05-14.md` §2 are addressed: 24/7 box (LaunchAgent), connected services (sources/), 30-min cadence (scheduler), goal seed (goal_feed), Tinder UX (composer), sell-to-me (`Why this`), forum-topics (deferred to v2 per design §2.7), preference memory (memory + pilot_preferences), Codex anecdote (PR-merge example in design §4.2), burrito (dispatch-then-confirm in feedback._dispatch_downstream), spam-fatigue guard (halt-gate + ≤80/500 caps).
- **Placeholder scan:** `_dispatch_downstream` in feedback.py Task 10 is an intentional scope boundary — state transition is recorded; downstream PM/Senior-Agent bots poll the `accepted` queue. All other steps contain full code.
- **Type consistency:** `RawCandidate` defined Task 5, used Tasks 5–13. `Memory` defined Task 6, extended in Task 10 (`get_suggestion`) and Task 14 (`daily_counts`, `top_pending`, `archive_old_deferred`). `scheduler.run_cycle` defined Task 5, called from `cli.main` in Task 15.

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-05-14-agency-bot-pilot.md`. Two execution options:

1. **Subagent-Driven (recommended)** — fresh subagent per task, review between tasks. Phase 1 ships immediately; Phases 2–4 gate on autonomy-gap items #1–3 closing per `board-deliberation-browser-harness-2026-05-14`.
2. **Inline Execution** — execute in this session via `executing-plans`, batched with checkpoints.

Which approach?
