# ElevenLabs Margot Voice Agent Design Spec

**Date:** 2026-05-17
**Owner:** Phill McGurk / Unite-Group
**Status:** Approved design, awaiting written-spec review

## Purpose

Build the first back-and-forth voice interface for the Unite-Group operating system: a logged-in Unite CRM widget where Phill speaks to Margot, Margot captures the instruction, Pi-CEO/Margot applies the operating logic, and the result becomes durable CRM/Kanban/evidence state.

ElevenLabs provides the human-like voice experience. Pi-CEO/Margot owns the decision logic. Unite CRM remains the source of truth.

## Locked Decisions

- Approach: **ElevenLabs Voice Shell + Pi-CEO/Margot Brain**.
- First surface: **Unite-Group CRM "Talk to Margot" widget**.
- v0 access: **Phill only, authenticated Unite CRM session required**.
- v0 autonomy: **low-risk auto-create**, designed to grow toward higher autonomy after evidence proves classification quality.
- Margot voice persona: **calm executive operator**.
- First workflow: **Voice -> Margot structured brief -> Unite CRM task -> Pi-CEO/Hermes Kanban card**.
- Post-call handling: **auto-save transcript, summary, proposed actions, and approval requests**.
- ElevenLabs role: **voice UX only**; it does not own business routing, CRM policy, Synthex routing, Kanban policy, or approval gates.

## Non-Negotiable Boundaries

- Unite-Group / Unite CRM is the source of truth for tasks, decisions, approvals, and portfolio state.
- Pi-CEO/Margot owns the routing and decision logic.
- ElevenLabs handles live speech, turn-taking, voice, widget, and post-call transcript delivery.
- Hermes/Pi-CEO Kanban coordinates execution after CRM-first persistence.
- Synthex receives work only when the classifier identifies marketing/campaign work.
- Phill retains final authority for production deploys, spend, publishing, credential changes, endpoint/workflow changes, external commitments, high-risk code, and strategic/company-direction changes.
- No public widget in v0.
- No raw secrets in prompts, logs, transcripts, screenshots, webhook payload logs, or evidence files.

## Core Flow

```text
Phill speaks in Unite CRM
  -> ElevenLabs voice widget captures the conversation
  -> ElevenLabs sends transcript and call metadata by post-call webhook
  -> Pi-CEO/Margot normalizes the transcript into a structured brief
  -> Unite CRM task is created first
  -> Pi-CEO/Hermes Kanban card is created from the CRM task
  -> Gated actions wait for Phill approval
  -> Transcript, summary, actions, and evidence sync to 2nd Brain
```

Default Margot approval phrase:

> "I've captured that. I recommend routing this to Unite CRM as a portfolio task and creating a Pi-CEO Kanban card. Do you approve?"

## Permissions Model

### Allowed Automatically In v0

- Save transcript.
- Save summary.
- Create low-risk Unite CRM task.
- Create low-risk Pi-CEO/Hermes Kanban card.
- Route clearly classified marketing work to the Synthex queue.
- Route clearly classified portfolio/product/repo work to the relevant execution queue.
- Create a local fallback packet when CRM, Linear, or Kanban writes fail.

### Approval Required

- Production deploy.
- Paid spend.
- Publishing.
- Credential access or credential change.
- Strategic or company-direction change.
- Endpoint or workflow-routing change.
- External commitment.
- High-risk code or security-sensitive work.
- Ambiguous classification.
- Low transcript confidence.

## Data Contract

Every voice session produces one durable packet:

```json
{
  "source": "elevenlabs_voice",
  "speaker": "phill",
  "crm_user_id": "authenticated_user_id",
  "conversation_id": "elevenlabs_conversation_id",
  "transcript_ref": "stored_transcript_path_or_id",
  "summary": "short executive summary",
  "requested_outcome": "what Phill wants done",
  "business_context": "Unite-Group | Synthex | RestoreAssist | DR-NRPG | CCW | CARSI | other",
  "route": "unite_crm | synthex | pi_ceo | repo_execution | approval_required",
  "risk_level": "low | medium | high",
  "actions": [
    {
      "type": "create_crm_task",
      "status": "auto_created | approval_required | blocked",
      "evidence_ref": "path_or_id"
    }
  ],
  "approval_required": true,
  "approval_reason": "production, spend, credential, strategy, publishing, uncertain classification, or low confidence"
}
```

The stored implementation can add fields, but it must preserve these semantics.

## Components

### 1. ElevenLabs Agent Configuration

The ElevenLabs agent is configured as Margot's voice shell:

- Voice persona: calm executive operator.
- Primary instruction: capture Phill's intent, confirm important actions, and avoid making business decisions itself.
- Tool posture: only call Pi-CEO/Margot intake endpoints or produce post-call transcripts.
- User scope: authenticated Phill-only CRM context.
- Data retention: transcript must be exportable to Pi-CEO/2nd Brain; audio retention follows the smallest practical retention window unless Phill explicitly chooses long-term audio storage.

### 2. Unite CRM Voice Widget

The CRM embeds the ElevenLabs widget only in authenticated CRM pages available to Phill.

The first UI should show:

- Start voice session.
- Current Margot session state.
- Last captured summary.
- Proposed low-risk actions.
- Approval-required actions.
- Link to evidence packet.

### 3. Pi-CEO/Margot Intake Endpoint

Pi-CEO receives ElevenLabs post-call webhook payloads and converts them into structured packets.

Responsibilities:

- Verify webhook authenticity before processing.
- Normalize transcript into a Margot brief.
- Classify route and risk.
- Create CRM task first when safe.
- Create Pi-CEO/Hermes Kanban card after CRM task exists.
- Create fallback packet when an external write fails.
- Persist evidence references.

### 4. CRM-First Task Creation

Every actionable item is anchored in Unite CRM before execution.

Creation rules:

- Low-risk, clear route: auto-create CRM task.
- Medium/high risk: create approval request, not execution task.
- Ambiguous route: create triage task only.
- Marketing: CRM task first, then Synthex queue reference.
- Product/repo: CRM task first, then project execution queue reference.

### 5. Kanban Creation

Kanban cards are created only after the CRM anchor exists or a local fallback packet exists.

Each Kanban card includes:

- CRM task reference or fallback reference.
- Transcript reference.
- Summary.
- Requested outcome.
- Route.
- Risk level.
- Approval state.
- Evidence requirements.

### 6. Evidence Persistence

Evidence locations:

- Local fallback packets: `.harness/margot/voice/`
- Durable wiki summaries: `~/2nd Brain/2nd Brain/Wiki/`
- Supabase wiki corpus after sync.
- Unite CRM task record once CRM write succeeds.
- Hermes/Pi-CEO Kanban card comment thread.

No `GREEN` status is allowed unless the packet includes concrete evidence references.

## Failure Handling

### ElevenLabs Works, CRM Is Down

- Save local fallback packet.
- Mark sync `YELLOW`.
- Create Kanban fallback card.
- Retry CRM sync through a bounded queued job with one retry per run.

### Transcript Confidence Is Low

- Save transcript.
- Mark packet `YELLOW`.
- Margot asks one clarification before creating execution work.

### Classification Is Ambiguous

- Do not route automatically.
- Create triage task.
- Ask Phill to choose route.

### External Tool Fails

- Retry once.
- Persist failure evidence.
- Continue with local fallback file.
- Do not loop indefinitely.

### Webhook Authentication Fails

- Reject request.
- Persist a redacted security event.
- Do not create CRM or Kanban records.

## Testing Requirements

v0 is `GREEN` only when these checks pass:

- Mock ElevenLabs post-call webhook creates a structured Margot brief.
- Low-risk voice request creates a CRM task packet.
- Same low-risk request creates a Kanban card from the CRM task reference.
- Marketing request routes to Synthex queue only after CRM anchoring.
- Product/repo request routes to the right execution queue only after CRM anchoring.
- Production/spend/credential request is blocked for Phill approval.
- Failed CRM write creates a local fallback packet.
- Failed webhook authentication creates no CRM/Kanban action.
- Transcript, summary, proposed actions, and evidence references are written to durable storage.
- Logs contain no secret values.

## v0 Scope Exclusions

- No public ElevenLabs widget.
- No staff/client access.
- No voice-triggered production deploys.
- No voice-triggered spend or publishing.
- No voice-triggered credential changes.
- No unrestricted live-agent control from voice.
- No voice cloning until consent, disclosure, retention, and brand-risk rules are separately approved.
- No ElevenLabs-owned business routing logic.

## Build Sequence

1. Configure the ElevenLabs agent as voice shell only.
2. Create a local mock webhook fixture before using real ElevenLabs traffic.
3. Implement Pi-CEO/Margot intake normalization.
4. Implement CRM-first packet creation with local fallback.
5. Implement Kanban card creation from CRM/fallback reference.
6. Embed a Phill-only widget in Unite CRM behind existing auth.
7. Add evidence views and approval-required surfaces.
8. Run tests and one full manual voice-session rehearsal before any broader rollout.

## Acceptance Criteria

- Phill can open Unite CRM and start a Margot voice session.
- A voice instruction produces transcript, summary, route, risk, and proposed actions.
- Low-risk work creates CRM task plus Kanban card automatically.
- Gated work creates an approval request and does not execute.
- Marketing work routes to Synthex only after CRM anchoring.
- All records include evidence references.
- If CRM/Linear/Kanban is down, a local fallback packet is written and status is `YELLOW`.
- No secrets are exposed in logs or prompts.
- ElevenLabs is removable as the voice shell without rewriting Pi-CEO/Margot business logic.
