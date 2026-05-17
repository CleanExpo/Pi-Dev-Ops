# ElevenLabs Margot Voice Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the v0 "Talk to Margot" path where Phill speaks inside Unite CRM, ElevenLabs supplies the voice shell, Pi-CEO/Margot normalizes and gates the instruction, Unite CRM stores the task/session first, and Hermes Kanban receives the execution card.

**Architecture:** Unite CRM owns the authenticated UI and CRM records. Pi-CEO owns the ElevenLabs post-call webhook, transcript normalization, routing/risk classification, CRM write orchestration, local fallback, and Hermes Kanban handoff. ElevenLabs is intentionally replaceable: it provides signed voice sessions and post-call transcript webhooks only.

**Tech Stack:** FastAPI + Pydantic + pytest in `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops`; Next.js 15 + React 18 + Supabase service client + Jest/ts-jest in `/Users/phill-mac/pi-seo-workspace/unite-group`; ElevenLabs signed URL + post-call webhook APIs; existing `swarm.kanban_adapter`.

---

## Current Evidence

- Design spec: `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/docs/superpowers/specs/2026-05-17-elevenlabs-margot-voice-agent-design.md`
- Pi-CEO has existing authenticated Margot routes in `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/app/server/routes/margot.py`.
- Pi-CEO already has Hermes Kanban adapter + tests in `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/swarm/kanban_adapter.py` and `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/tests/test_kanban_adapter.py`.
- Unite CRM command center shell is `/Users/phill-mac/pi-seo-workspace/unite-group/src/components/command-center/CommandCenterShell.tsx`.
- Unite CRM admin API pattern is `/Users/phill-mac/pi-seo-workspace/unite-group/src/lib/security/require-admin.ts`.
- Unite CRM generated Supabase types already include `voice_command_sessions`, `voice_command_audit`, and `tasks`.
- Official ElevenLabs docs checked on 2026-05-17:
  - Widget embed and signed/public widget options: `https://elevenlabs.io/docs/eleven-agents/customization/widget`
  - Signed URL authentication: `https://elevenlabs.io/docs/eleven-agents/customization/authentication`
  - Signed URL API: `https://elevenlabs.io/docs/conversational-ai/api-reference/conversations/get-signed-url`
  - Post-call webhooks and HMAC validation: `https://elevenlabs.io/docs/eleven-agents/workflows/post-call-webhooks`

## File Map

### Pi-CEO

| File | Status | Purpose |
|---|---|---|
| `app/server/margot_voice_packet.py` | Create | Pure packet extraction, route classification, approval gates, redaction, fallback persistence |
| `app/server/routes/elevenlabs.py` | Create | ElevenLabs post-call webhook endpoint |
| `app/server/main.py` | Modify | Register `elevenlabs.router` |
| `swarm/kanban_adapter.py` | Modify | Add optional `board` argument without changing existing default behavior |
| `tests/test_margot_voice_packet.py` | Create | Pure unit tests for packet logic |
| `tests/test_elevenlabs_margot_voice_route.py` | Create | FastAPI route tests for auth, webhook processing, CRM fallback, Kanban handoff |
| `tests/test_kanban_adapter.py` | Modify | Add board-aware argv regression test |

### Unite CRM

| File | Status | Purpose |
|---|---|---|
| `src/app/api/pi-ceo/margot-voice/signed-url/route.ts` | Create | Phill-only server route that returns short-lived ElevenLabs signed URL |
| `src/app/api/pi-ceo/margot-voice/task/route.ts` | Create | Server-to-server CRM task/session creation endpoint for Pi-CEO |
| `src/components/command-center/voice/MargotVoicePanel.tsx` | Create | CRM-side "Talk to Margot" panel |
| `src/components/command-center/CommandCenterShell.tsx` | Modify | Add the voice panel to the command-center right rail |
| `src/lib/ratelimit.ts` | Modify | Add rate limit presets for signed-url and task creation routes |
| `tests/integration/api/margot-voice-signed-url.test.ts` | Create | Signed URL route tests |
| `tests/integration/api/margot-voice-task.test.ts` | Create | CRM task route tests |

## Required Environment

Pi-CEO:

```bash
ELEVENLABS_API_KEY=<stored in 1Password/env, never committed>
ELEVENLABS_WEBHOOK_SECRET=<post-call webhook secret>
UNITE_CRM_API_URL=https://unite-group.in
UNITE_CRM_INGEST_TOKEN=<server-to-server token stored in 1Password/env>
HERMES_KANBAN_BOARD=unite-group-portfolio-ops
```

Unite CRM:

```bash
ELEVENLABS_API_KEY=<stored in 1Password/env, never exposed client-side>
ELEVENLABS_MARGOT_AGENT_ID=<agent id>
UNITE_CRM_INGEST_TOKEN=<same server-to-server token as Pi-CEO>
UNITE_CRM_ORG_ID=<org uuid for voice_command_sessions>
UNITE_CRM_WORKSPACE_ID=<workspace uuid for tasks>
```

No `.env*` files are read or edited by this plan.

## Safety Gates

- ElevenLabs has no business authority; it never receives CRM write secrets or routing authority.
- The CRM widget is visible only inside authenticated Unite CRM pages.
- Signed URL route is admin-gated and rate-limited.
- Pi-CEO webhook validates `ElevenLabs-Signature` before processing.
- Low-risk clear tasks may auto-create CRM + Kanban records.
- Production deploy, spend, publishing, credential, endpoint, workflow routing, external commitment, strategic/company direction, ambiguous classification, and low confidence always require approval.
- If CRM or Kanban write fails, Pi-CEO writes `.harness/margot/voice/<packet_id>.json` and reports `YELLOW`.
- No secret values are written to packets, reports, logs, specs, tests, or Kanban bodies.

---

## Task 1: Pi-CEO Voice Packet Contract

**Files:**
- Create: `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/tests/test_margot_voice_packet.py`
- Create: `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/app/server/margot_voice_packet.py`

- [x] **Step 1: Write failing tests**

Create `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/tests/test_margot_voice_packet.py`:

```python
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server.margot_voice_packet import (
    build_packet_from_elevenlabs_event,
    classify_route,
    persist_fallback_packet,
    redact_secret_like_values,
)


def _event(message: str, *, summary: str = "Captured portfolio task.") -> dict:
    return {
        "type": "post_call_transcription",
        "event_timestamp": 1789459200,
        "data": {
            "agent_id": "agent_margot",
            "agent_name": "Margot",
            "conversation_id": "conv_123",
            "status": "done",
            "user_id": "phill",
            "transcript": [
                {"role": "agent", "message": "How can I help?"},
                {"role": "user", "message": message},
            ],
            "analysis": {"transcript_summary": summary, "call_successful": "success"},
            "conversation_initiation_client_data": {
                "dynamic_variables": {
                    "crm_user_id": "crm-user-1",
                    "crm_user_email": "phill.mcgurk@gmail.com",
                }
            },
        },
    }


def test_low_risk_portfolio_task_routes_to_unite_crm():
    decision = classify_route("Create a portfolio task to update the Unite CRM dashboard copy")
    assert decision.route == "unite_crm"
    assert decision.business_context == "unite-group"
    assert decision.risk_level == "low"
    assert decision.approval_required is False


def test_marketing_request_routes_to_synthex_after_crm_anchor():
    decision = classify_route("Ask Synthex to prepare a LinkedIn launch campaign")
    assert decision.route == "synthex"
    assert decision.business_context == "synthex"
    assert decision.risk_level == "low"
    assert decision.approval_required is False


def test_deploy_spend_credentials_require_approval():
    decision = classify_route("Deploy production and increase ad spend with the API key")
    assert decision.route == "approval_required"
    assert decision.risk_level == "high"
    assert decision.approval_required is True
    assert "production" in decision.approval_reason
    assert "spend" in decision.approval_reason
    assert "credential" in decision.approval_reason


def test_build_packet_extracts_transcript_summary_and_actions():
    packet = build_packet_from_elevenlabs_event(_event("Create a low risk CRM task"))
    assert packet.source == "elevenlabs_voice"
    assert packet.speaker == "phill"
    assert packet.conversation_id == "conv_123"
    assert "Create a low risk CRM task" in packet.transcript_text
    assert packet.summary == "Captured portfolio task."
    assert packet.actions[0]["type"] == "create_crm_task"
    assert packet.approval_required is False


def test_redaction_removes_secret_like_values():
    text = "Use sk-abc123456789 and Bearer tokenhere and postgres://user:pass@host/db"
    clean = redact_secret_like_values(text)
    assert "sk-abc" not in clean
    assert "Bearer tokenhere" not in clean
    assert "postgres://" not in clean
    assert "[REDACTED]" in clean


def test_fallback_packet_is_written_atomically(tmp_path):
    packet = build_packet_from_elevenlabs_event(_event("Create a CRM task"))
    path = persist_fallback_packet(packet, root=tmp_path)
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["packet_id"] == packet.packet_id
    assert data["sync_status"] == "fallback"
```

- [x] **Step 2: Run tests and confirm failure**

Run:

```bash
cd /Users/phill-mac/Pi-CEO/Pi-Dev-Ops
python -m pytest tests/test_margot_voice_packet.py -q
```

Expected: fails with `ModuleNotFoundError: No module named 'app.server.margot_voice_packet'`.

- [x] **Step 3: Implement packet module**

Create `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/app/server/margot_voice_packet.py`:

```python
"""Margot voice packet normalization for ElevenLabs post-call webhooks."""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FALLBACK_ROOT = Path(".harness/margot/voice")

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{8,}", re.I),
    re.compile(r"postgres://\S+", re.I),
    re.compile(r"SUPABASE_[A-Z0-9_]+\s*=\s*\S+", re.I),
]

HIGH_RISK_KEYWORDS = {
    "production": "production",
    "deploy": "production",
    "publish": "publishing",
    "spend": "spend",
    "ads": "spend",
    "ad budget": "spend",
    "credential": "credential",
    "password": "credential",
    "api key": "credential",
    "secret": "credential",
    "endpoint": "endpoint",
    "workflow": "workflow routing",
    "company direction": "strategy",
    "strategy": "strategy",
    "external commitment": "external commitment",
}

MARKETING_KEYWORDS = {
    "campaign",
    "linkedin",
    "seo",
    "marketing",
    "ad copy",
    "campaign copy",
    "marketing copy",
    "ad creative",
    "content calendar",
    "brand voice",
}

REPO_KEYWORDS = {
    "restoreassist": "restoreassist",
    "ato": "ato",
    "dr-nrpg": "dr-nrpg",
    "nrpg": "dr-nrpg",
    "ccw": "ccw",
    "carsi": "carsi",
    "disaster recovery": "disaster-recovery",
}


@dataclass
class RouteDecision:
    route: str
    business_context: str
    risk_level: str
    approval_required: bool
    approval_reason: str = ""


@dataclass
class VoicePacket:
    packet_id: str
    source: str
    speaker: str
    crm_user_id: str
    crm_user_email: str
    conversation_id: str
    transcript_text: str
    summary: str
    requested_outcome: str
    business_context: str
    route: str
    risk_level: str
    approval_required: bool
    approval_reason: str
    actions: list[dict[str, Any]] = field(default_factory=list)
    evidence_refs: dict[str, str] = field(default_factory=dict)
    sync_status: str = "new"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def redact_secret_like_values(text: str) -> str:
    clean = text or ""
    for pattern in SECRET_PATTERNS:
        clean = pattern.sub("[REDACTED]", clean)
    return clean


def _safe_text(value: Any) -> str:
    return redact_secret_like_values(str(value or "").strip())


def classify_route(transcript_text: str) -> RouteDecision:
    text = transcript_text.lower()
    reasons = sorted({label for key, label in HIGH_RISK_KEYWORDS.items() if key in text})
    if reasons:
        return RouteDecision(
            route="approval_required",
            business_context="unite-group",
            risk_level="high",
            approval_required=True,
            approval_reason=", ".join(reasons),
        )
    if any(key in text for key in MARKETING_KEYWORDS):
        return RouteDecision(
            route="synthex",
            business_context="synthex",
            risk_level="low",
            approval_required=False,
        )
    for key, context in REPO_KEYWORDS.items():
        if key in text:
            return RouteDecision(
                route="repo_execution",
                business_context=context,
                risk_level="low",
                approval_required=False,
            )
    return RouteDecision(
        route="unite_crm",
        business_context="unite-group",
        risk_level="low",
        approval_required=False,
    )


def _transcript_text(event: dict[str, Any]) -> str:
    transcript = ((event.get("data") or {}).get("transcript") or [])
    lines: list[str] = []
    for item in transcript:
        role = _safe_text(item.get("role"))
        message = _safe_text(item.get("message"))
        if message:
            lines.append(f"{role}: {message}" if role else message)
    return "\n".join(lines).strip()


def _dynamic_vars(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get("data") or {}
    init = data.get("conversation_initiation_client_data") or {}
    return init.get("dynamic_variables") or {}


def _packet_id(conversation_id: str, transcript_text: str) -> str:
    raw = f"{conversation_id}:{transcript_text}".encode("utf-8")
    return "voice_" + hashlib.sha256(raw).hexdigest()[:16]


def build_packet_from_elevenlabs_event(event: dict[str, Any]) -> VoicePacket:
    data = event.get("data") or {}
    dynamic = _dynamic_vars(event)
    conversation_id = _safe_text(data.get("conversation_id"))
    transcript_text = _transcript_text(event)
    analysis = data.get("analysis") or {}
    summary = _safe_text(analysis.get("transcript_summary")) or transcript_text[:240]
    decision = classify_route(transcript_text)
    packet_id = _packet_id(conversation_id, transcript_text)
    action_status = "approval_required" if decision.approval_required else "pending"
    action_type = "request_approval" if decision.approval_required else "create_crm_task"
    return VoicePacket(
        packet_id=packet_id,
        source="elevenlabs_voice",
        speaker="phill",
        crm_user_id=_safe_text(dynamic.get("crm_user_id")),
        crm_user_email=_safe_text(dynamic.get("crm_user_email")),
        conversation_id=conversation_id,
        transcript_text=transcript_text,
        summary=summary,
        requested_outcome=summary,
        business_context=decision.business_context,
        route=decision.route,
        risk_level=decision.risk_level,
        approval_required=decision.approval_required,
        approval_reason=decision.approval_reason,
        actions=[{"type": action_type, "status": action_status, "evidence_ref": ""}],
        evidence_refs={"elevenlabs_conversation_id": conversation_id},
    )


def packet_to_dict(packet: VoicePacket) -> dict[str, Any]:
    return asdict(packet)


def persist_fallback_packet(packet: VoicePacket, *, root: Path = FALLBACK_ROOT) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    packet.sync_status = "fallback"
    final = root / f"{packet.packet_id}.json"
    payload = json.dumps(packet_to_dict(packet), indent=2, sort_keys=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=root, prefix=".tmp-", suffix=".json") as fh:
        fh.write(payload)
        tmp = Path(fh.name)
    tmp.replace(final)
    return final
```

- [x] **Step 4: Verify tests pass**

Run:

```bash
cd /Users/phill-mac/Pi-CEO/Pi-Dev-Ops
python -m pytest tests/test_margot_voice_packet.py -q
```

Expected: all tests pass.

- [x] **Step 5: Commit**

Run:

```bash
cd /Users/phill-mac/Pi-CEO/Pi-Dev-Ops
git add app/server/margot_voice_packet.py tests/test_margot_voice_packet.py
git commit -m "feat: add margot voice packet contract"
```

---

## Task 2: Unite CRM Signed URL Route

**Files:**
- Create: `/Users/phill-mac/pi-seo-workspace/unite-group/tests/integration/api/margot-voice-signed-url.test.ts`
- Create: `/Users/phill-mac/pi-seo-workspace/unite-group/src/app/api/pi-ceo/margot-voice/signed-url/route.ts`
- Modify: `/Users/phill-mac/pi-seo-workspace/unite-group/src/lib/ratelimit.ts`

- [x] **Step 1: Write failing route tests**

Create `/Users/phill-mac/pi-seo-workspace/unite-group/tests/integration/api/margot-voice-signed-url.test.ts`:

```ts
jest.mock('@/lib/security/require-admin', () => ({
  requireAdmin: jest.fn(),
}));

import { NextResponse } from 'next/server';
import { GET } from '@/app/api/pi-ceo/margot-voice/signed-url/route';
import { requireAdmin } from '@/lib/security/require-admin';

const mockedRequireAdmin = requireAdmin as jest.Mock;

function req() {
  return new Request('https://unite-group.in/api/pi-ceo/margot-voice/signed-url', {
    headers: { 'x-forwarded-for': '127.0.0.1' },
  }) as any;
}

describe('GET /api/pi-ceo/margot-voice/signed-url', () => {
  const oldEnv = process.env;

  beforeEach(() => {
    jest.resetAllMocks();
    process.env = {
      ...oldEnv,
      ELEVENLABS_API_KEY: 'xi-test',
      ELEVENLABS_MARGOT_AGENT_ID: 'agent_test',
    };
    mockedRequireAdmin.mockResolvedValue({ ok: true, actorEmail: 'phill.mcgurk@gmail.com' });
  });

  afterEach(() => {
    process.env = oldEnv;
    jest.restoreAllMocks();
  });

  it('returns 401/403 response from admin gate', async () => {
    mockedRequireAdmin.mockResolvedValue(NextResponse.json({ error: 'unauthorized' }, { status: 401 }));
    const res = await GET(req());
    expect(res.status).toBe(401);
  });

  it('fails closed when env is missing', async () => {
    delete process.env.ELEVENLABS_API_KEY;
    const res = await GET(req());
    expect(res.status).toBe(503);
    expect(await res.json()).toEqual({ error: 'elevenlabs_not_configured' });
  });

  it('returns a signed url without exposing the api key', async () => {
    global.fetch = jest.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ signed_url: 'wss://api.elevenlabs.io/v1/convai/conversation?conversation_signature=abc' }),
    }) as any;

    const res = await GET(req());
    expect(res.status).toBe(200);
    const body = await res.json();
    expect(body.signed_url).toContain('conversation_signature=abc');
    expect(JSON.stringify(body)).not.toContain('xi-test');
    expect(global.fetch).toHaveBeenCalledWith(
      'https://api.elevenlabs.io/v1/convai/conversation/get-signed-url?agent_id=agent_test&include_conversation_id=true',
      expect.objectContaining({
        method: 'GET',
        headers: { 'xi-api-key': 'xi-test' },
      }),
    );
  });
});
```

- [x] **Step 2: Run tests and confirm failure**

Run:

```bash
cd /Users/phill-mac/pi-seo-workspace/unite-group
npm run test:all -- tests/integration/api/margot-voice-signed-url.test.ts --runInBand
```

Expected: fails because the route file does not exist.

- [x] **Step 3: Add rate limit presets**

Modify `/Users/phill-mac/pi-seo-workspace/unite-group/src/lib/ratelimit.ts` inside `RATE_LIMITS`:

```ts
  margotVoiceSignedUrl: { limit: 20, windowMs: 60_000 },
  margotVoiceTaskCreate: { limit: 30, windowMs: 60_000 },
```

- [x] **Step 4: Create signed URL route**

Create `/Users/phill-mac/pi-seo-workspace/unite-group/src/app/api/pi-ceo/margot-voice/signed-url/route.ts`:

```ts
import { NextRequest, NextResponse } from 'next/server';
import { requireAdmin } from '@/lib/security/require-admin';
import { rateLimit, RATE_LIMITS } from '@/lib/ratelimit';

const ELEVENLABS_SIGNED_URL_ENDPOINT =
  'https://api.elevenlabs.io/v1/convai/conversation/get-signed-url';

export const dynamic = 'force-dynamic';

export async function GET(req: NextRequest) {
  const gate = await rateLimit(req, {
    key: 'margot-voice-signed-url',
    ...RATE_LIMITS.margotVoiceSignedUrl,
  });
  if (!gate.ok) {
    return NextResponse.json(
      { error: 'rate_limited', retry_after_ms: gate.retryAfterMs },
      { status: 429 },
    );
  }

  const admin = await requireAdmin(req);
  if (admin instanceof NextResponse) return admin;

  const apiKey = process.env.ELEVENLABS_API_KEY?.trim();
  const agentId = process.env.ELEVENLABS_MARGOT_AGENT_ID?.trim();
  if (!apiKey || !agentId) {
    return NextResponse.json({ error: 'elevenlabs_not_configured' }, { status: 503 });
  }

  const url = new URL(ELEVENLABS_SIGNED_URL_ENDPOINT);
  url.searchParams.set('agent_id', agentId);
  url.searchParams.set('include_conversation_id', 'true');

  try {
    const upstream = await fetch(url.toString(), {
      method: 'GET',
      headers: { 'xi-api-key': apiKey },
      cache: 'no-store',
      signal: AbortSignal.timeout(8000),
    });
    if (!upstream.ok) {
      return NextResponse.json({ error: 'elevenlabs_signed_url_failed' }, { status: 502 });
    }
    const data = await upstream.json();
    return NextResponse.json(
      {
        signed_url: data.signed_url,
        actor_email: admin.actorEmail,
        expires_in_seconds: 900,
      },
      { headers: { 'Cache-Control': 'no-store' } },
    );
  } catch {
    return NextResponse.json({ error: 'elevenlabs_unreachable' }, { status: 502 });
  }
}
```

- [x] **Step 5: Verify tests pass**

Run:

```bash
cd /Users/phill-mac/pi-seo-workspace/unite-group
npm run test:all -- tests/integration/api/margot-voice-signed-url.test.ts --runInBand
```

Expected: all tests pass.

- [x] **Step 6: Commit**

Run:

```bash
cd /Users/phill-mac/pi-seo-workspace/unite-group
git add src/lib/ratelimit.ts src/app/api/pi-ceo/margot-voice/signed-url/route.ts tests/integration/api/margot-voice-signed-url.test.ts
git commit -m "feat: add margot voice signed url route"
```

Completed:
- Unite CRM commit: `efe81b2 feat: add margot voice signed url route`
- Focused test: `npm run test:all -- tests/integration/api/margot-voice-signed-url.test.ts --runInBand` -> 3 passed
- Type check: `npm run type-check -- --pretty false` -> exit 0
- Targeted lint: `npx eslint src/app/api/pi-ceo/margot-voice/signed-url/route.ts tests/integration/api/margot-voice-signed-url.test.ts --max-warnings=0` -> exit 0
- Whole-repo lint: `npm run lint -- --max-warnings=0` -> blocked by 485 inherited warnings, 0 errors

---

## Task 3: Unite CRM Task Creation Route

**Files:**
- Create: `/Users/phill-mac/pi-seo-workspace/unite-group/tests/integration/api/margot-voice-task.test.ts`
- Create: `/Users/phill-mac/pi-seo-workspace/unite-group/src/app/api/pi-ceo/margot-voice/task/route.ts`

- [x] **Step 1: Write failing tests**

Create `/Users/phill-mac/pi-seo-workspace/unite-group/tests/integration/api/margot-voice-task.test.ts`:

```ts
jest.mock('@supabase/supabase-js', () => ({
  createClient: jest.fn(),
}));

import { createClient } from '@supabase/supabase-js';
import { POST } from '@/app/api/pi-ceo/margot-voice/task/route';

const mockedCreateClient = createClient as jest.Mock;

function request(body: unknown, token = 'ingest-test') {
  return new Request('https://unite-group.in/api/pi-ceo/margot-voice/task', {
    method: 'POST',
    headers: {
      authorization: `Bearer ${token}`,
      'content-type': 'application/json',
      'x-forwarded-for': '127.0.0.1',
    },
    body: JSON.stringify(body),
  }) as any;
}

const packet = {
  packet_id: 'voice_abc',
  conversation_id: 'conv_abc',
  crm_user_id: 'crm-user-1',
  crm_user_email: 'phill.mcgurk@gmail.com',
  transcript_text: 'user: Create a low risk Unite CRM portfolio task',
  summary: 'Create a low risk Unite CRM portfolio task',
  requested_outcome: 'Create a low risk Unite CRM portfolio task',
  business_context: 'unite-group',
  route: 'unite_crm',
  risk_level: 'low',
  approval_required: false,
  approval_reason: '',
  actions: [{ type: 'create_crm_task', status: 'pending', evidence_ref: '' }],
  evidence_refs: { elevenlabs_conversation_id: 'conv_abc' },
};

describe('POST /api/pi-ceo/margot-voice/task', () => {
  const oldEnv = process.env;

  beforeEach(() => {
    process.env = {
      ...oldEnv,
      NEXT_PUBLIC_SUPABASE_URL: 'https://example.supabase.co',
      SUPABASE_SERVICE_ROLE_KEY: 'service-role',
      UNITE_CRM_INGEST_TOKEN: 'ingest-test',
      UNITE_CRM_ORG_ID: 'org-1',
      UNITE_CRM_WORKSPACE_ID: 'workspace-1',
    };
    jest.resetAllMocks();
  });

  afterEach(() => {
    process.env = oldEnv;
  });

  it('rejects missing token', async () => {
    const res = await POST(request(packet, 'wrong'));
    expect(res.status).toBe(401);
  });

  it('creates voice session and CRM task', async () => {
    const from = jest.fn((table: string) => {
      if (table === 'voice_command_sessions') {
        return {
          insert: jest.fn().mockReturnValue({
            select: jest.fn().mockReturnValue({
              single: jest.fn().mockResolvedValue({ data: { id: 'voice-session-1' }, error: null }),
            }),
          }),
        };
      }
      if (table === 'tasks') {
        return {
          insert: jest.fn().mockReturnValue({
            select: jest.fn().mockReturnValue({
              single: jest.fn().mockResolvedValue({ data: { id: 'task-1', title: packet.summary }, error: null }),
            }),
          }),
        };
      }
      throw new Error(`unexpected table ${table}`);
    });
    mockedCreateClient.mockReturnValue({ from });

    const res = await POST(request(packet));
    expect(res.status).toBe(200);
    expect(await res.json()).toEqual({
      ok: true,
      crm_session_id: 'voice-session-1',
      crm_task_id: 'task-1',
      task_title: packet.summary,
    });
    expect(from).toHaveBeenCalledWith('voice_command_sessions');
    expect(from).toHaveBeenCalledWith('tasks');
  });

  it('creates approval-needed task when approval is required', async () => {
    const calls: Array<{ table: string; row: any }> = [];
    const from = jest.fn((table: string) => ({
      insert: jest.fn((row: any) => {
        calls.push({ table, row });
        return {
          select: jest.fn().mockReturnValue({
            single: jest.fn().mockResolvedValue({
              data: table === 'tasks'
                ? { id: 'task-approval', title: row.title }
                : { id: 'voice-session-approval' },
              error: null,
            }),
          }),
        };
      }),
    }));
    mockedCreateClient.mockReturnValue({ from });

    const res = await POST(request({ ...packet, approval_required: true, approval_reason: 'production' }));
    expect(res.status).toBe(200);
    const taskCall = calls.find((c) => c.table === 'tasks')!;
    expect(taskCall.row.status).toBe('blocked');
    expect(taskCall.row.priority).toBe('high');
    expect(taskCall.row.tags).toContain('approval-required');
  });
});
```

- [x] **Step 2: Run tests and confirm failure**

Run:

```bash
cd /Users/phill-mac/pi-seo-workspace/unite-group
npm run test:all -- tests/integration/api/margot-voice-task.test.ts --runInBand
```

Expected: fails because the route file does not exist.

- [x] **Step 3: Create task route**

Create `/Users/phill-mac/pi-seo-workspace/unite-group/src/app/api/pi-ceo/margot-voice/task/route.ts`:

```ts
import { NextRequest, NextResponse } from 'next/server';
import { createClient } from '@supabase/supabase-js';
import { rateLimit, RATE_LIMITS } from '@/lib/ratelimit';
import { timingSafeTokenMatch } from '@/lib/security/safe-compare';

export const dynamic = 'force-dynamic';

interface VoicePacket {
  packet_id: string;
  conversation_id: string;
  crm_user_id: string;
  crm_user_email: string;
  transcript_text: string;
  summary: string;
  requested_outcome: string;
  business_context: string;
  route: string;
  risk_level: string;
  approval_required: boolean;
  approval_reason: string;
  actions: Array<Record<string, unknown>>;
  evidence_refs: Record<string, string>;
}

function asString(value: unknown): string {
  return typeof value === 'string' ? value.trim() : '';
}

function validatePacket(value: any): VoicePacket | null {
  if (!value || typeof value !== 'object') return null;
  const packetId = asString(value.packet_id);
  const summary = asString(value.summary);
  const transcript = asString(value.transcript_text);
  if (!packetId || !summary || !transcript) return null;
  return {
    packet_id: packetId,
    conversation_id: asString(value.conversation_id),
    crm_user_id: asString(value.crm_user_id),
    crm_user_email: asString(value.crm_user_email),
    transcript_text: transcript,
    summary: summary.slice(0, 500),
    requested_outcome: asString(value.requested_outcome) || summary,
    business_context: asString(value.business_context) || 'unite-group',
    route: asString(value.route) || 'unite_crm',
    risk_level: asString(value.risk_level) || 'low',
    approval_required: value.approval_required === true,
    approval_reason: asString(value.approval_reason),
    actions: Array.isArray(value.actions) ? value.actions : [],
    evidence_refs: value.evidence_refs && typeof value.evidence_refs === 'object' ? value.evidence_refs : {},
  };
}

export async function POST(req: NextRequest) {
  const gate = await rateLimit(req, {
    key: 'margot-voice-task-create',
    ...RATE_LIMITS.margotVoiceTaskCreate,
  });
  if (!gate.ok) {
    return NextResponse.json(
      { error: 'rate_limited', retry_after_ms: gate.retryAfterMs },
      { status: 429 },
    );
  }

  const bearer = req.headers.get('authorization')?.replace(/^Bearer\s+/, '') ?? null;
  if (!timingSafeTokenMatch(bearer, process.env.UNITE_CRM_INGEST_TOKEN)) {
    return NextResponse.json({ error: 'unauthorized' }, { status: 401 });
  }

  const orgId = process.env.UNITE_CRM_ORG_ID?.trim();
  const workspaceId = process.env.UNITE_CRM_WORKSPACE_ID?.trim();
  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim();
  const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY?.trim();
  if (!orgId || !workspaceId || !supabaseUrl || !serviceKey) {
    return NextResponse.json({ error: 'crm_not_configured' }, { status: 503 });
  }

  let body: unknown;
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: 'invalid_json' }, { status: 400 });
  }

  const packet = validatePacket(body);
  if (!packet) return NextResponse.json({ error: 'invalid_packet' }, { status: 400 });

  const supabase = createClient(supabaseUrl, serviceKey);
  const status = packet.approval_required ? 'blocked' : 'todo';
  const priority = packet.approval_required || packet.risk_level === 'high' ? 'high' : 'normal';
  const tags = [
    'margot-voice',
    packet.business_context,
    packet.route,
    packet.approval_required ? 'approval-required' : 'auto-created',
  ].filter(Boolean);

  const sessionInsert = await supabase
    .from('voice_command_sessions')
    .insert({
      org_id: orgId,
      user_id: packet.crm_user_id || packet.crm_user_email || 'phill',
      transcript: packet.transcript_text,
      parsed_intent: packet,
      status,
      language_code: 'en',
    })
    .select('id')
    .single();

  if (sessionInsert.error || !sessionInsert.data?.id) {
    return NextResponse.json({ error: 'voice_session_insert_failed' }, { status: 500 });
  }

  const description = [
    packet.requested_outcome,
    '',
    `Route: ${packet.route}`,
    `Business context: ${packet.business_context}`,
    `Risk: ${packet.risk_level}`,
    `Approval required: ${packet.approval_required ? 'yes' : 'no'}`,
    packet.approval_reason ? `Approval reason: ${packet.approval_reason}` : '',
    `Voice session: ${sessionInsert.data.id}`,
    `ElevenLabs conversation: ${packet.conversation_id}`,
  ].filter(Boolean).join('\n');

  const taskInsert = await supabase
    .from('tasks')
    .insert({
      workspace_id: workspaceId,
      title: packet.summary,
      description,
      status,
      priority,
      assignee_type: 'agent',
      assignee_name: packet.approval_required ? 'Phill approval' : 'Margot',
      tags,
      position: 0,
      obsidian_path: `voice/${packet.packet_id}`,
    })
    .select('id,title')
    .single();

  if (taskInsert.error || !taskInsert.data?.id) {
    return NextResponse.json({ error: 'crm_task_insert_failed' }, { status: 500 });
  }

  return NextResponse.json(
    {
      ok: true,
      crm_session_id: sessionInsert.data.id,
      crm_task_id: taskInsert.data.id,
      task_title: taskInsert.data.title,
    },
    { headers: { 'Cache-Control': 'no-store' } },
  );
}
```

- [x] **Step 4: Verify tests pass**

Run:

```bash
cd /Users/phill-mac/pi-seo-workspace/unite-group
npm run test:all -- tests/integration/api/margot-voice-task.test.ts --runInBand
```

Expected: all tests pass.

- [x] **Step 5: Commit**

Run:

```bash
cd /Users/phill-mac/pi-seo-workspace/unite-group
git add src/app/api/pi-ceo/margot-voice/task/route.ts tests/integration/api/margot-voice-task.test.ts
git commit -m "feat: add margot voice crm task route"
```

Completed:
- Unite CRM commit: `0c6ab61 feat: add margot voice crm task route`
- Red test: route import failed before implementation because `/api/pi-ceo/margot-voice/task` did not exist
- Focused test: `npm run test:all -- tests/integration/api/margot-voice-task.test.ts --runInBand` -> 3 passed
- Type check: `npm run type-check -- --pretty false` -> exit 0
- Targeted lint: `npx eslint src/app/api/pi-ceo/margot-voice/task/route.ts tests/integration/api/margot-voice-task.test.ts --max-warnings=0` -> exit 0

---

## Task 4: Pi-CEO CRM Client, Kanban Handoff, and Webhook Route

**Files:**
- Modify: `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/tests/test_kanban_adapter.py`
- Modify: `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/swarm/kanban_adapter.py`
- Create: `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/tests/test_elevenlabs_margot_voice_route.py`
- Create: `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/app/server/routes/elevenlabs.py`
- Modify: `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/app/server/main.py`
- Modify: `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/pyproject.toml`

- [x] **Step 1: Add board-aware Kanban adapter test**

Append to `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/tests/test_kanban_adapter.py`:

```python
def test_create_card_with_board_argv_shape(monkeypatch):
    record: list = []
    _patch_run(monkeypatch, rc=0, stdout='{"task_id": "k-board1"}', record=record)
    out = KA.create_card(
        title="voice card",
        body="from crm",
        tenant="pi-ceo",
        board="unite-group-portfolio-ops",
    )
    assert out == "k-board1"
    args, _ = record[0]
    assert args[:4] == ("kanban", "--board", "unite-group-portfolio-ops", "create")
    assert "--json" in args
    assert args[-1] == "voice card"
```

- [x] **Step 2: Run adapter tests and confirm failure**

Run:

```bash
cd /Users/phill-mac/Pi-CEO/Pi-Dev-Ops
python -m pytest tests/test_kanban_adapter.py -q
```

Expected: fails with `TypeError: create_card() got an unexpected keyword argument 'board'`.

- [x] **Step 3: Extend adapter without changing defaults**

Modify `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/swarm/kanban_adapter.py`:

```python
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
    board: str | None = None,
) -> str | None:
    """Create a kanban card. Returns task_id or None on failure."""
    args: list[str] = ["kanban"]
    if board:
        args.extend(["--board", board])
    args.extend(["create", "--json"])
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
        log.warning("kanban_adapter: create succeeded but no task_id parsed: %r", out[:200])
    return task_id
```

- [x] **Step 4: Add ElevenLabs Python dependency**

Modify `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/pyproject.toml` dependencies:

```toml
    "elevenlabs>=2.0",
```

- [x] **Step 5: Write webhook route tests**

Create `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/tests/test_elevenlabs_margot_voice_route.py`:

```python
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _event(message: str = "Create a low risk Unite CRM portfolio task") -> dict:
    return {
        "type": "post_call_transcription",
        "event_timestamp": 1789459200,
        "data": {
            "agent_id": "agent_margot",
            "conversation_id": "conv_route",
            "status": "done",
            "user_id": "phill",
            "transcript": [{"role": "user", "message": message}],
            "analysis": {"transcript_summary": message, "call_successful": "success"},
            "conversation_initiation_client_data": {
                "dynamic_variables": {"crm_user_id": "crm-user-1", "crm_user_email": "phill.mcgurk@gmail.com"}
            },
        },
    }


def _client(monkeypatch, *, construct_event=None, crm_status=200, crm_body=None, kanban_id="k-voice"):
    from app.server.routes import elevenlabs

    monkeypatch.setenv("ELEVENLABS_API_KEY", "xi-test")
    monkeypatch.setenv("ELEVENLABS_WEBHOOK_SECRET", "webhook-secret")
    monkeypatch.setenv("UNITE_CRM_API_URL", "https://unite-group.in")
    monkeypatch.setenv("UNITE_CRM_INGEST_TOKEN", "ingest-test")
    monkeypatch.setenv("HERMES_KANBAN_BOARD", "unite-group-portfolio-ops")
    monkeypatch.setattr(
        elevenlabs,
        "_construct_event",
        construct_event or (lambda raw, sig, secret: json.loads(raw)),
    )

    class FakeResponse:
        status_code = crm_status

        def json(self):
            return crm_body or {"ok": True, "crm_task_id": "task-1", "crm_session_id": "session-1", "task_title": "Task"}

        @property
        def text(self):
            return json.dumps(self.json())

    class FakeHttp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json, headers):
            self.url = url
            self.payload = json
            self.headers = headers
            return FakeResponse()

    fake_http = FakeHttp()
    monkeypatch.setattr(elevenlabs.httpx, "Client", lambda timeout: fake_http)
    monkeypatch.setattr(elevenlabs.kanban_adapter, "create_card", lambda **kwargs: kanban_id)

    app = FastAPI()
    app.include_router(elevenlabs.router)
    return TestClient(app)


def test_webhook_rejects_bad_signature(monkeypatch):
    def explode(raw, sig, secret):
        raise ValueError("invalid")

    client = _client(monkeypatch, construct_event=explode)
    res = client.post(
        "/api/elevenlabs/margot/post-call",
        content=json.dumps(_event()),
        headers={"ElevenLabs-Signature": "bad"},
    )
    assert res.status_code == 401


def test_webhook_creates_crm_task_and_kanban_card(monkeypatch):
    client = _client(monkeypatch)
    res = client.post(
        "/api/elevenlabs/margot/post-call",
        content=json.dumps(_event()),
        headers={"ElevenLabs-Signature": "sig"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "green"
    assert body["crm_task_id"] == "task-1"
    assert body["kanban_task_id"] == "k-voice"
    assert body["fallback_path"] is None


def test_webhook_persists_fallback_when_crm_fails(monkeypatch, tmp_path):
    from app.server.routes import elevenlabs

    monkeypatch.setattr(elevenlabs, "FALLBACK_ROOT", tmp_path)
    client = _client(monkeypatch, crm_status=503, kanban_id="k-fallback")
    res = client.post(
        "/api/elevenlabs/margot/post-call",
        content=json.dumps(_event()),
        headers={"ElevenLabs-Signature": "sig"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "yellow"
    assert body["crm_task_id"] is None
    assert body["kanban_task_id"] == "k-fallback"
    assert Path(body["fallback_path"]).exists()
```

- [x] **Step 6: Run tests and confirm failure**

Run:

```bash
cd /Users/phill-mac/Pi-CEO/Pi-Dev-Ops
python -m pytest tests/test_elevenlabs_margot_voice_route.py tests/test_kanban_adapter.py -q
```

Expected: route import fails until `app/server/routes/elevenlabs.py` exists.

- [x] **Step 7: Create webhook route**

Create `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/app/server/routes/elevenlabs.py`:

```python
"""ElevenLabs post-call webhook routes for Margot voice intake."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app.server.margot_voice_packet import (
    FALLBACK_ROOT,
    VoicePacket,
    build_packet_from_elevenlabs_event,
    packet_to_dict,
    persist_fallback_packet,
)
from swarm import kanban_adapter

log = logging.getLogger("pi-ceo.routes.elevenlabs")
router = APIRouter()


class MargotVoiceWebhookResponse(BaseModel):
    status: str
    packet_id: str
    crm_task_id: str | None
    crm_session_id: str | None
    kanban_task_id: str | None
    fallback_path: str | None
    approval_required: bool
    route: str
    risk_level: str


def _construct_event(raw_body: str, sig_header: str | None, secret: str) -> dict[str, Any]:
    if not sig_header:
        raise ValueError("missing ElevenLabs-Signature")
    from elevenlabs.client import ElevenLabs  # noqa: PLC0415

    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY missing")
    client = ElevenLabs(api_key=api_key)
    event = client.webhooks.construct_event(
        rawBody=raw_body,
        sig_header=sig_header,
        secret=secret,
    )
    if not isinstance(event, dict):
        raise ValueError("ElevenLabs webhook parser did not return a dict")
    return event


def _crm_endpoint() -> tuple[str, str] | None:
    api_url = os.environ.get("UNITE_CRM_API_URL", "").strip().rstrip("/")
    token = os.environ.get("UNITE_CRM_INGEST_TOKEN", "").strip()
    if not api_url or not token:
        return None
    return f"{api_url}/api/pi-ceo/margot-voice/task", token


def _create_crm_task(packet: VoicePacket) -> dict[str, Any] | None:
    endpoint = _crm_endpoint()
    if endpoint is None:
        return None
    url, token = endpoint
    try:
        with httpx.Client(timeout=12.0) as client:
            res = client.post(
                url,
                json=packet_to_dict(packet),
                headers={"Authorization": f"Bearer {token}"},
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("margot voice CRM write failed: %s", exc)
        return None
    if res.status_code >= 400:
        log.warning("margot voice CRM write HTTP %s: %s", res.status_code, res.text[:200])
        return None
    try:
        data = res.json()
    except Exception:
        return None
    return data if data.get("ok") else None


def _kanban_body(packet: VoicePacket, *, crm: dict[str, Any] | None, fallback_path: Path | None) -> str:
    lines = [
        f"Summary: {packet.summary}",
        f"Requested outcome: {packet.requested_outcome}",
        f"Route: {packet.route}",
        f"Business context: {packet.business_context}",
        f"Risk: {packet.risk_level}",
        f"Approval required: {'yes' if packet.approval_required else 'no'}",
    ]
    if packet.approval_reason:
        lines.append(f"Approval reason: {packet.approval_reason}")
    if crm:
        lines.append(f"CRM task: {crm.get('crm_task_id')}")
        lines.append(f"CRM voice session: {crm.get('crm_session_id')}")
    if fallback_path:
        lines.append(f"Fallback packet: {fallback_path}")
    lines.append(f"ElevenLabs conversation: {packet.conversation_id}")
    return "\n".join(lines)


def _create_kanban_card(packet: VoicePacket, *, crm: dict[str, Any] | None, fallback_path: Path | None) -> str | None:
    board = os.environ.get("HERMES_KANBAN_BOARD", "unite-group-portfolio-ops").strip() or None
    title_prefix = "APPROVAL" if packet.approval_required else "VOICE"
    title = f"[{title_prefix}@{packet.business_context}] {packet.summary[:90]}"
    return kanban_adapter.create_card(
        title=title,
        body=_kanban_body(packet, crm=crm, fallback_path=fallback_path),
        tenant="pi-ceo",
        priority=100 if packet.approval_required else 80,
        idempotency_key=packet.packet_id,
        board=board,
        triage=packet.approval_required,
    )


@router.post("/api/elevenlabs/margot/post-call", response_model=MargotVoiceWebhookResponse)
async def margot_post_call(
    request: Request,
    elevenlabs_signature: str | None = Header(default=None, alias="ElevenLabs-Signature"),
) -> MargotVoiceWebhookResponse:
    secret = os.environ.get("ELEVENLABS_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise HTTPException(503, "ELEVENLABS_WEBHOOK_SECRET not configured")

    raw = (await request.body()).decode("utf-8")
    try:
        event = _construct_event(raw, elevenlabs_signature, secret)
    except Exception as exc:
        log.warning("invalid ElevenLabs webhook signature: %s", exc)
        raise HTTPException(401, "invalid ElevenLabs webhook signature") from exc

    if event.get("type") != "post_call_transcription":
        return MargotVoiceWebhookResponse(
            status="ignored",
            packet_id="",
            crm_task_id=None,
            crm_session_id=None,
            kanban_task_id=None,
            fallback_path=None,
            approval_required=False,
            route="ignored",
            risk_level="low",
        )

    packet = build_packet_from_elevenlabs_event(event)
    crm = _create_crm_task(packet)
    fallback_path: Path | None = None
    status = "green"
    if crm is None:
        fallback_path = persist_fallback_packet(packet, root=FALLBACK_ROOT)
        status = "yellow"

    kanban_id = _create_kanban_card(packet, crm=crm, fallback_path=fallback_path)
    if kanban_id is None:
        status = "yellow"

    return MargotVoiceWebhookResponse(
        status=status,
        packet_id=packet.packet_id,
        crm_task_id=str(crm.get("crm_task_id")) if crm else None,
        crm_session_id=str(crm.get("crm_session_id")) if crm else None,
        kanban_task_id=kanban_id,
        fallback_path=str(fallback_path) if fallback_path else None,
        approval_required=packet.approval_required,
        route=packet.route,
        risk_level=packet.risk_level,
    )
```

- [x] **Step 8: Register route**

Modify `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/app/server/main.py`:

```python
from .routes import auth, sessions, webhooks, triggers, scan_monitor, pipeline, utils, telegram_proxy, mission_control, phone, swarm, margot, cost_report, delegate, elevenlabs
```

Add after `app.include_router(margot.router)`:

```python
app.include_router(elevenlabs.router)
```

- [x] **Step 9: Verify backend tests**

Run:

```bash
cd /Users/phill-mac/Pi-CEO/Pi-Dev-Ops
python -m pytest tests/test_margot_voice_packet.py tests/test_elevenlabs_margot_voice_route.py tests/test_kanban_adapter.py -q
python -c "from app.server.main import app; print(type(app))"
```

Expected: tests pass and import command prints `<class 'fastapi.applications.FastAPI'>`.

- [x] **Step 10: Commit**

Run:

```bash
cd /Users/phill-mac/Pi-CEO/Pi-Dev-Ops
git add pyproject.toml app/server/routes/elevenlabs.py app/server/main.py swarm/kanban_adapter.py tests/test_elevenlabs_margot_voice_route.py tests/test_kanban_adapter.py
git commit -m "feat: add elevenlabs margot voice webhook"
```

Completed:
- Pi-CEO commit: `0eff8a3 feat: add elevenlabs margot voice webhook`
- Red adapter test: `create_card() got an unexpected keyword argument 'board'`
- Red route test: `ImportError: cannot import name 'elevenlabs'`
- Backend tests: `python -m pytest tests/test_margot_voice_packet.py tests/test_elevenlabs_margot_voice_route.py tests/test_kanban_adapter.py -q` -> 25 passed
- Import check: `python -c "from app.server.main import app; print(type(app))"` -> `<class 'fastapi.applications.FastAPI'>`
- Lockfile: `uv lock` resolved `elevenlabs v2.47.0`

---

## Task 5: Unite CRM Margot Voice Panel

**Files:**
- Create: `/Users/phill-mac/pi-seo-workspace/unite-group/src/components/command-center/voice/MargotVoicePanel.tsx`
- Modify: `/Users/phill-mac/pi-seo-workspace/unite-group/src/components/command-center/CommandCenterShell.tsx`

- [x] **Step 1: Create voice panel component**

Create `/Users/phill-mac/pi-seo-workspace/unite-group/src/components/command-center/voice/MargotVoicePanel.tsx`:

```tsx
'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';

type VoiceState = 'idle' | 'loading' | 'ready' | 'error';

declare global {
  namespace JSX {
    interface IntrinsicElements {
      'elevenlabs-convai': React.DetailedHTMLProps<React.HTMLAttributes<HTMLElement>, HTMLElement> & {
        'signed-url'?: string;
        variant?: string;
        dismissible?: string;
        'action-text'?: string;
        'start-call-text'?: string;
        'end-call-text'?: string;
        'listening-text'?: string;
        'speaking-text'?: string;
      };
    }
  }
}

export function MargotVoicePanel() {
  const [state, setState] = useState<VoiceState>('idle');
  const [signedUrl, setSignedUrl] = useState('');
  const [error, setError] = useState('');

  const statusLabel = useMemo(() => {
    if (state === 'ready') return 'secure voice ready';
    if (state === 'loading') return 'preparing secure link';
    if (state === 'error') return 'voice unavailable';
    return 'not connected';
  }, [state]);

  useEffect(() => {
    if (document.querySelector('script[data-elevenlabs-convai]')) return;
    const script = document.createElement('script');
    script.src = 'https://unpkg.com/@elevenlabs/convai-widget-embed';
    script.async = true;
    script.type = 'text/javascript';
    script.dataset.elevenlabsConvai = 'true';
    document.body.appendChild(script);
  }, []);

  const prepareSession = useCallback(async () => {
    setState('loading');
    setError('');
    setSignedUrl('');
    try {
      const res = await fetch('/api/pi-ceo/margot-voice/signed-url', { cache: 'no-store' });
      const body = await res.json();
      if (!res.ok || !body.signed_url) {
        throw new Error(body.error || 'signed_url_failed');
      }
      setSignedUrl(body.signed_url);
      setState('ready');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'voice_session_failed');
      setState('error');
    }
  }, []);

  return (
    <section
      className="flex flex-col gap-3 p-5"
      style={{
        background: 'var(--cc-bg-soft)',
        borderBottom: '1px solid var(--cc-grid)',
      }}
      aria-label="Talk to Margot"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <p
            className="font-mono text-[10px] uppercase tracking-[0.22em]"
            style={{ color: 'var(--cc-ink-dim)' }}
          >
            Margot voice
          </p>
          <h2 className="text-sm font-semibold" style={{ color: 'var(--cc-ink)' }}>
            Talk to Margot
          </h2>
        </div>
        <span
          className="font-mono text-[10px] uppercase tracking-[0.16em]"
          style={{ color: state === 'ready' ? 'var(--cc-signal)' : 'var(--cc-ink-hush)' }}
        >
          {statusLabel}
        </span>
      </div>

      <button
        type="button"
        onClick={prepareSession}
        disabled={state === 'loading'}
        className="h-9 px-3 text-xs font-mono uppercase tracking-[0.18em] disabled:opacity-50"
        style={{
          color: 'var(--cc-bg)',
          background: 'var(--cc-signal)',
          border: '1px solid var(--cc-signal)',
        }}
      >
        {state === 'loading' ? 'Preparing' : 'Start secure voice'}
      </button>

      {state === 'error' ? (
        <p className="text-xs" style={{ color: '#f87171' }}>
          {error}
        </p>
      ) : null}

      {signedUrl ? (
        <div className="min-h-[9rem]" style={{ borderTop: '1px solid var(--cc-grid)', paddingTop: '0.75rem' }}>
          <elevenlabs-convai
            signed-url={signedUrl}
            variant="expanded"
            dismissible="false"
            action-text="Talk to Margot"
            start-call-text="Start"
            end-call-text="End"
            listening-text="Listening"
            speaking-text="Margot speaking"
          />
        </div>
      ) : null}
    </section>
  );
}
```

- [x] **Step 2: Add panel to command center shell**

Modify `/Users/phill-mac/pi-seo-workspace/unite-group/src/components/command-center/CommandCenterShell.tsx`:

```tsx
import { MargotVoicePanel } from './voice/MargotVoicePanel';
```

Insert before `<Business360Grid />`:

```tsx
          <MargotVoicePanel />
```

- [x] **Step 3: Run frontend gates**

Run:

```bash
cd /Users/phill-mac/pi-seo-workspace/unite-group
npm run type-check
npm run lint
```

Expected: both pass.

- [x] **Step 4: Commit**

Run:

```bash
cd /Users/phill-mac/pi-seo-workspace/unite-group
git add src/components/command-center/voice/MargotVoicePanel.tsx src/components/command-center/CommandCenterShell.tsx
git commit -m "feat: add margot voice panel to command center"
```

Completed:
- Unite CRM commit: `5efdabd feat: add margot voice panel to command center`
- Type check: `npm run type-check -- --pretty false` -> exit 0
- Targeted lint: `npx eslint src/components/command-center/voice/MargotVoicePanel.tsx src/components/command-center/CommandCenterShell.tsx --max-warnings=0` -> exit 0
- Whole-repo lint: `npm run lint -- --max-warnings=0` -> blocked by 485 inherited warnings, 0 errors

---

## Task 6: End-to-End Local Rehearsal

**Files:**
- Create: `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/margot/voice/rehearsal-2026-05-17.md`

- [x] **Step 1: Start Pi-CEO backend**

Run in tmux pane `pi-ceo-api`:

```bash
cd /Users/phill-mac/Pi-CEO/Pi-Dev-Ops
uvicorn app.server.main:app --host 127.0.0.1 --port 7777
```

Expected: server starts without import errors.

- [x] **Step 2: Start Unite CRM**

Run in tmux pane `unite-crm`:

```bash
cd /Users/phill-mac/pi-seo-workspace/unite-group
npm run dev
```

Expected: Next dev server prints a local URL.

- [ ] **Step 3: Probe signed URL route with browser session**

Blocked: local browser context is not authenticated; `/en/command-center` redirected to `/en/login`. Keep this unchecked until Phill runs the browser click from a logged-in CRM session.

Open authenticated Unite CRM and click `Start secure voice` in the command center.

Expected:

```text
Panel state changes from not connected -> preparing secure link -> secure voice ready.
No ElevenLabs API key is visible in browser devtools response payload.
```

- [x] **Step 4: Rehearse webhook without live voice**

Run:

```bash
cd /Users/phill-mac/Pi-CEO/Pi-Dev-Ops
python - <<'PY'
import json
from app.server.margot_voice_packet import build_packet_from_elevenlabs_event, persist_fallback_packet
event = {
  "type": "post_call_transcription",
  "event_timestamp": 1789459200,
  "data": {
    "agent_id": "agent_margot",
    "conversation_id": "conv_rehearsal",
    "status": "done",
    "user_id": "phill",
    "transcript": [{"role": "user", "message": "Create a low risk portfolio task for Unite CRM and make a Kanban card."}],
    "analysis": {"transcript_summary": "Create a low risk portfolio task for Unite CRM and make a Kanban card."},
    "conversation_initiation_client_data": {"dynamic_variables": {"crm_user_id": "crm-user-1", "crm_user_email": "phill.mcgurk@gmail.com"}}
  }
}
packet = build_packet_from_elevenlabs_event(event)
path = persist_fallback_packet(packet)
print(json.dumps({"packet_id": packet.packet_id, "route": packet.route, "risk": packet.risk_level, "path": str(path)}, indent=2))
PY
```

Expected: prints packet id, `route` as `unite_crm`, `risk` as `low`, and a fallback JSON path.

- [x] **Step 5: Record rehearsal evidence**

Create `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/.harness/margot/voice/rehearsal-2026-05-17.md`:

```markdown
# Margot Voice v0 Rehearsal

Date: 2026-05-17
Surface: Unite CRM Command Center
Voice shell: ElevenLabs signed URL widget
Decision logic: Pi-CEO/Margot

## Checks

- [ ] Unite CRM signed URL route returned a signed URL without exposing API key
- [ ] Voice panel rendered in Command Center
- [ ] Packet builder classified low-risk CRM task correctly
- [ ] CRM task route created `voice_command_sessions` row
- [ ] CRM task route created `tasks` row
- [ ] Hermes Kanban card created on `unite-group-portfolio-ops`
- [ ] Fallback packet created when CRM/Kanban unavailable
- [ ] No secrets present in browser payloads, packet files, or Kanban body

## Evidence

- Signed URL route result:
- CRM task id:
- CRM voice session id:
- Kanban task id:
- Fallback packet path:
- Test commands:
```

- [x] **Step 6: Run full gates**

Run:

```bash
cd /Users/phill-mac/Pi-CEO/Pi-Dev-Ops
python -m pytest tests/test_margot_voice_packet.py tests/test_elevenlabs_margot_voice_route.py tests/test_kanban_adapter.py -q
python -c "from app.server.main import app; print(type(app))"

cd /Users/phill-mac/pi-seo-workspace/unite-group
npm run test:all -- tests/integration/api/margot-voice-signed-url.test.ts tests/integration/api/margot-voice-task.test.ts --runInBand
npm run type-check
npm run lint
```

Expected: all pass. If repository-wide lint has pre-existing failures, capture exact files and run the narrower lint/type gates for files touched by this plan before marking the task `YELLOW`.

- [x] **Step 7: Commit rehearsal evidence**

Run:

```bash
cd /Users/phill-mac/Pi-CEO/Pi-Dev-Ops
git add .harness/margot/voice/rehearsal-2026-05-17.md
git commit -m "test: capture margot voice rehearsal evidence"
```

Completed:
- Pi-CEO commit: `8b3f2f0 test: capture margot voice rehearsal evidence`
- Rehearsal note: `.harness/margot/voice/rehearsal-2026-05-17.md`
- Fallback packet: `.harness/margot/voice/voice_07317263d968c49f.json`
- Pi-CEO tests/import: 25 passed and FastAPI import succeeded
- Unite CRM API tests: 6 passed
- Unite CRM type-check: exit 0
- Unite CRM lint: exit 0 with 485 inherited warnings
- Local UI: dev server started at `http://localhost:3002`; command center redirected to login

---

## Task 7: Production Readiness Gate

**Files:**
- Update: `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/docs/superpowers/specs/2026-05-17-elevenlabs-margot-voice-agent-design.md`
- Update: `/Users/phill-mac/Pi-CEO/Pi-Dev-Ops/docs/superpowers/plans/2026-05-17-elevenlabs-margot-voice-agent.md`

- [ ] **Step 1: Append implementation evidence to design spec**

Append this section to the design spec after `Acceptance Criteria`:

```markdown
## Implementation Evidence

- Pi-CEO packet tests:
- Pi-CEO webhook tests:
- Kanban adapter board test:
- Unite CRM signed URL tests:
- Unite CRM task route tests:
- Unite CRM type-check:
- Unite CRM lint:
- Manual voice rehearsal:
- Production workflow behavior changed:
```

- [ ] **Step 2: Update this plan checklist**

Mark each completed task checkbox in this file. Keep failed checks unchecked and add a one-line blocker under the relevant task.

- [ ] **Step 3: Final no-secret scan**

Run:

```bash
cd /Users/phill-mac/Pi-CEO/Pi-Dev-Ops
rg -n "sk-|Bearer [A-Za-z0-9._-]{8,}|postgres://|SUPABASE_SERVICE_ROLE_KEY=.*[A-Za-z0-9]" app/server/margot_voice_packet.py app/server/routes/elevenlabs.py tests/test_margot_voice_packet.py tests/test_elevenlabs_margot_voice_route.py docs/superpowers/plans/2026-05-17-elevenlabs-margot-voice-agent.md

cd /Users/phill-mac/pi-seo-workspace/unite-group
rg -n "sk-|Bearer [A-Za-z0-9._-]{8,}|postgres://|SUPABASE_SERVICE_ROLE_KEY=.*[A-Za-z0-9]" src/app/api/pi-ceo/margot-voice src/components/command-center/voice tests/integration/api/margot-voice-*.test.ts
```

Expected: no real secrets. Test literals such as `Bearer tokenhere`, `service-role`, `xi-test`, or `ingest-test` are allowed only inside tests or docs.

- [ ] **Step 4: Final status**

Final status is:

```text
GREEN only if Pi-CEO tests pass, Unite CRM tests pass, type-check passes, lint passes or pre-existing lint failures are isolated, and manual rehearsal evidence exists.
YELLOW if any external dependency is missing but fallback packets and tests are green.
RED if webhook auth, CRM write, Kanban write, or signed URL route fails without fallback.
```

---

## Execution Notes

- Start with Task 1 and Task 2 in parallel only if using separate worktrees because they touch different repos.
- Do not modify `.env*` files.
- Do not apply Supabase migrations directly to production. This plan uses existing typed tables and environment IDs; if a missing table is discovered, pause implementation and use `/Users/phill-mac/pi-seo-workspace/unite-group/scripts/sandbox-wizard.sh` against the sandbox first.
- Do not expose ElevenLabs API keys in the browser. The browser receives only a signed URL.
- Do not give ElevenLabs tool authority to write CRM, Kanban, Synthex, or repo state. Post-call webhook processing remains inside Pi-CEO/Margot.

## Self-Review

- Spec coverage: every locked design decision maps to a task: signed voice session, post-call webhook, Pi-CEO packet logic, CRM-first task/session creation, Synthex routing classification, Kanban card creation, fallback evidence, and command-center UI.
- Placeholder scan: no task uses deferred implementation language; each code-writing step includes concrete files and code.
- Type consistency: packet fields match across Python packet model, CRM task route body, webhook response, and tests.
- Boundary check: Unite CRM remains the CRM source of truth; Synthex is only a route value for marketing work; ElevenLabs remains voice shell only.
