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
