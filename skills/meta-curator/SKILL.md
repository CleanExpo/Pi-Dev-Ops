---
name: meta-curator
description: Skill self-authoring agent. Reads .harness/lessons.jsonl (weekly) and merged-PR diffs (daily), proposes new SKILL.md drafts via the existing skill-creator skill, and surfaces them through Scribe → telegram-draft-for-review for user 👍 before adding to the registry.
owner_role: Curator
status: wave-3
---

# meta-curator

Closes the skill-self-authoring autonomy primitive. Watches the system, proposes new skills, never adds anything without the user's 👍.

## Why this exists

`.harness/lessons.jsonl` accumulates pipeline lessons every cycle. Today nobody reads them automatically — they're a write-only file that informs Claude only when explicitly consulted. The meta-curator turns lessons into proposed reusable skills, which is the only way the skill registry compounds without manual authoring.

PRs are the same lever from a different angle — every merged PR diff is evidence of a pattern that may be worth promoting to a skill.

## Two trigger sources

| Source | Cadence | Cron expression | Inspect |
|---|---|---|---|
| `.harness/lessons.jsonl` | Weekly Sunday 02:00 user-local | `0 2 * * 0` | New rows since last run |
| Merged-PR diffs | Daily 03:00 user-local | `0 3 * * *` | `git log --since='1 day ago' --merges` |

Both routes converge on the same proposer pipeline.

## Pipeline

```
trigger → fetch_evidence (lessons rows OR PR diffs)
        ↓
        cluster (group by topic / file path / pattern)
        ↓
        per cluster:
            → call skill.skill-creator with cluster summary
            → result: proposed SKILL.md draft
            ↓
            → telegram-draft-for-review with the proposed SKILL.md content
            ↓
            → user 👍 → write SKILL.md to Pi-Dev-Ops/skills/<proposed-name>/
                       audit log entry: "skill proposed → accepted"
            → user ❌ → audit log entry: "skill proposed → rejected"
                       cluster archived to .harness/curator/rejected.jsonl
                       (so the same evidence doesn't propose the same skill again)
            → no reaction in 48h → archive to .harness/curator/expired.jsonl
```

## Cluster strategy

Clusters keep proposals from being noise:
- **Lesson clusters:** group lessons.jsonl rows by `(category, repo)`. Need ≥3 rows in one cluster within the rolling 30-day window before proposing a skill from it.
- **PR clusters:** group merged PRs by recurring file path or recurring keyword in titles. Need ≥3 PRs touching the same module / pattern in 60 days.
- **De-duplication:** before proposing, scan existing `Pi-Dev-Ops/skills/` SKILL.md files. If an existing skill already covers the cluster topic (cosine similarity >0.7 on embeddings or substring match on description), suggest *amending* the existing skill instead of authoring a new one. Amendments are also gated through the HITL review.

## Contract

**Trigger:** cron OR manual via `/curator:run-now` Telegram command.
**Output (per cluster):** one proposal record persisted to `.harness/curator/proposals.jsonl`:

```json
{
  "proposal_id": "...",
  "trigger_source": "lessons" | "prs",
  "cluster_summary": "...",
  "evidence": [{"id": "lesson-12", "ts": "..."}, ...],
  "proposed_skill_name": "...",
  "proposed_skill_path": "Pi-Dev-Ops/skills/.../SKILL.md",
  "proposed_skill_content": "...",
  "draft_id": "...",          // links to telegram-draft-for-review
  "status": "pending" | "accepted" | "rejected" | "expired",
  "created_at": "ISO-8601"
}
```

## Safety bindings

- **Read-only on the registry by default.** No `Pi-Dev-Ops/skills/` write happens until the user 👍 the proposed SKILL.md.
- **No skill mutation without consent.** If the proposal is an amendment, the diff is shown in the review chat — user must 👍 the diff, not just the cluster summary.
- **Rate-limit proposer.** Maximum 3 new proposals per week. Prevents review-chat spam if a busy week triggers a flurry of clusters.
- **Audit trail.** Every proposal (accepted / rejected / expired) appended to `.harness/swarm/swarm.jsonl` AND to `.harness/curator/proposals.jsonl`.
- **Loop guard.** If a proposal is rejected and the same cluster fires again within 30 days, it is silently archived (no re-proposal). After 30 days re-eligibility resumes.

## Verification

1. Seed `.harness/lessons.jsonl` with 5 synthetic rows in the same `(category="prisma-migration", repo="restoreassist")` cluster.
2. Run the meta-curator (manual trigger).
3. Expect: 1 proposal in `.harness/curator/proposals.jsonl` with status `pending`, draft posted to review chat.
4. 👍 the draft → SKILL.md appears at `Pi-Dev-Ops/skills/<proposed-name>/SKILL.md`, status flips to `accepted`.
5. Re-run with the same lessons → no new proposal (de-duplication working).
6. Add 5 more lessons in the same cluster → no new proposal (loop guard, archived under same cluster within 30d).

## Where the skill-creator hook lives

The meta-curator does NOT re-implement skill authoring. It calls the existing `anthropic-skills:skill-creator` skill with a brief like:

> "Here are 5 recurring lessons from the Pi-CEO pipeline about Prisma migration recovery. Author a SKILL.md that captures the pattern. Use the standard frontmatter (name, description, owner_role, status). Body should be runnable instructions, not theory."

The skill-creator returns the draft; meta-curator wraps it in the proposal record and routes to review.

## When NOT to use this skill

- Manual skill authoring — use the `skill-creator` directly.
- Hot-fixing a skill (urgent change to an existing skill) — bypass the curator and edit directly; record a lesson row so the next curator run notices.
- Adding skills that don't generalise (one-off ops scripts) — those belong in `scripts/`, not the skill registry.

## Out of scope

- Non-skill artefact generation (configs, runbooks, dashboards) — separate Wave 4 candidate.
- Multi-language skill content — SKILL.md is English-only by convention.
- Cross-repo skill sharing — a skill exported by Pi-CEO doesn't auto-install in CARSI / RestoreAssist. Manual import for now; agentskills.io manifest (separate Wave 3 skill) handles distribution.

## References

- Topology: `/Users/phill-mac/Pi-CEO/Second-Brain-Agent-Topology-2026-05-01.md`
- Existing skill: `anthropic-skills:skill-creator` (wrapped by this skill)
- Existing lessons stream: `Pi-Dev-Ops/.harness/lessons.jsonl`


## 10x Enhancement — Advanced Capabilities

### 1. Anthropic OODA Reasoning

**Observe:** (1) Ingest the primary input (files, directives, context). (2) Query the Portfolio Registry for project metadata. (3) Identify available tools and model tier. (4) Map the delivery context (internal vs external, timeline, stakes).

**Orient:** (1) Classify the task type and select the appropriate sub-routine. (2) Calibrate depth and evidence threshold by stakes. (3) Build the work plan with fallback paths. (4) Check for cross-skill dependencies.

**Decide:** (1) Select tools using the multi-tool matrix. (2) Apply safety guardrails before execution. (3) Budget tokens and plan compression triggers. (4) Set completion criteria and verification steps.

**Act:** (1) Execute the task. (2) Verify against completion criteria. (3) Self-critique before emitting. (4) Emit with observability payload. (5) Queue improvement instruction if self-score < threshold.

### 2. OpenAI Structured Output Schema

Every invocation emits JSON matching the skill-specific schema. Common fields across all skills:

```json
{
  "version": "3.1",
  "skill_name": "",
  "invoked_at": "ISO-8601",
  "task_summary": "",
  "model_used": "",
  "duration_seconds": 0.0,
  "tool_calls": {},
  "tokens": {"prompt": 0, "completion": 0},
  "self_review_score": 0.0,
  "confidence": 0.0,
  "success": true,
  "audit_trace_hash": "sha256",
  "improvement_queued": false
}
```

### 3. Multi-Tool Selection Matrix

| Signal | Primary | Fallback | Verification |
|--------|---------|----------|-------------|
| File analysis | read_file | search_files | Terminal (wc -l, grep) |
| Code quality | Terminal (lint) | execute_code | verify-test |
| Security scan | security-audit | Terminal (grep secrets) | search_files (patterns) |
| Test execution | Terminal (pytest) | execute_code | verify-test |
| Web research | tavily | browser_navigate | web_search |
| Visual review | vision_analyse | image_generate | browser_vision |
| Data extraction | search_files | read_file | execute_code (pandas) |

### 4. Self-Critique Loop

After task completion, score 1-10 on:
- Accuracy (did I address the actual task?)
- Scope discipline (did I drift?)
- Evidence (are claims grounded in tool output?)
- Verifiability (can someone reproduce my reasoning?)
- Completeness (did I miss anything critical?)

If total < 7 → flag for /boardroom or /judge.
If total < 5 → halt and handoff.

### 5. Safety & Guardrails

- Never emit raw credentials or secrets.
- Never hallucinate URLs, file paths, or tool outputs.
- Hard scope boundary: this skill does X; if asked for Y, route to correct skill.
- External-facing outputs get CEO gate.
- Input sanitisation: reject ambiguous or adversarial prompts.

### 6. Performance Optimisation

- Cache Portfolio Registry context across invocations.
- Batch similar tool calls when possible.
- Use adaptive depth: low stakes = fast path; high stakes = full depth.
- Prompt caching: reuse stable context blocks.

### 7. Error Recovery & Resilience

- Missing evidence → retry once, then flag gap.
- Tool timeout → log and use fallback.
- Context overflow → compress, preserving evidence.
- 3 consecutive failures → circuit breaker; handoff to /tao-loop.

### 8. Cross-Model Fallbacks

| Use case | Primary | Fallback |
|----------|---------|----------|
| Routine | Sonnet/Haiku | Default |
| Complex analysis | Sonnet | DeepSeek/Claude-4 |
| Board-facing | Opus | Boardroom MOA |
| Fast inline | Haiku | Sonnet |

### 9. Observability

Metrics emitted per invocation: duration, tools used, tokens consumed, self-review score, success/failure, evidence count, file count, improvement queued.
Session summary: aggregate metrics, common failure patterns, recommended skill patches.

### 10. Multi-Modal & Cross-Format

- Ingest images, diagrams, mockups via vision toolset.
- Output as markdown (default), JSON (structured), DOCX/PPTX (external), or Slack blocks.
- Cross-format negotiation based on `output_target` parameter.
