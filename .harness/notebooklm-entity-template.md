# NotebookLM Entity Template

**Version:** 1.0  
**Designed for:** One-day entity replication  
**Target:** Any new entity onboarded to Pi-CEO  
**Ratified:** Sprint 13 — April 2026 (RA-829)

---

## 1. Notebook Structure Template

### Required Sources (Minimum Viable Set)
Every entity notebook must include at minimum:

| # | Source Type | Format | Description |
|---|-------------|--------|-------------|
| 1 | Architecture doc | Markdown/PDF | System overview, tech stack, deployment |
| 2 | Linear project export | PDF/text | Current sprint, backlog, recent decisions |
| 3 | README.md (primary repo) | Markdown | Project purpose, setup, conventions |
| 4 | ZTE score history | JSON/text | Health trajectory, current score |
| 5 | Known risks / ESCALATION.md | Markdown | Active incidents, known failure modes |

### Recommended Sources (Enriched Set)
| # | Source Type | Format | Description |
|---|-------------|--------|-------------|
| 6 | CLAUDE.md | Markdown | AI session conventions |
| 7 | Recent board deliberations | Markdown | Strategic decisions, board directives |
| 8 | Sprint handoff docs | Markdown | Completed work, pending queue |
| 9 | Security audit results | Markdown | CVE counts, remediation status |
| 10 | Business charter | Markdown | Entity purpose, target market, revenue |

---

## 2. Standard 10-Query Acceptance Test

Run these queries after notebook creation. All 10 must return coherent, entity-specific answers:

1. What are the top 3 risks for this entity right now?
2. What work is currently in progress and what is blocked?
3. What is the current health / ZTE score and trajectory?
4. What are the most recent completed milestones?
5. What are the next priority actions (this week)?
6. What dependencies or external blockers exist?
7. What integrations does this entity use (APIs, services, tools)?
8. What is the deployment topology (where does it run)?
9. What are the known failure modes and how are they detected?
10. What would a new developer need to know in the first hour?

**Acceptance threshold:** 8/10 answers rated ≥7/10 quality by the reviewing human.

---

## 3. Claude Skills Configuration

Each entity gets a dedicated skill set in `~/.hermes/skills/` (or `skills/` in the repo):

```yaml
# ~/.hermes/config.yaml (entity-specific section)
entity_skills:
  - name: entity-overview
    description: "High-level summary of {entity} purpose, stack, and status"
  - name: entity-risks  
    description: "Current top-3 risks for {entity} with mitigation status"
  - name: entity-sprint
    description: "Current sprint plan, in-progress work, and blockers for {entity}"
```

Skill files live at `skills/{entity-slug}/SKILL.md`. Template:

```markdown
---
name: {entity-slug}
description: "{Entity name} — {one-line purpose}. Apply when answering questions about this entity."
---

# {Entity Name} Context

## What it is
{2-3 sentence description}

## Current status
{ZTE score, health, active sprint}

## Top risks
{Top 3 from latest board meeting}

## Key files
{List of critical files with one-line descriptions}
```

---

## 4. n8n Workflow Template

Export from the RestoreAssist instance (RA-825) and import. Core workflow:

```
[RSS/webhook trigger] → [filter by entity] → [Google Doc append] → [NotebookLM refresh trigger]
```

Configuration per entity:
- `ENTITY_NAME`: entity slug (e.g. `synthex`)
- `NOTEBOOK_ID`: from `.harness/notebooklm-registry.json`
- `GOOGLE_DOC_ID`: dedicated Google Doc for update aggregation
- `FILTER_KEYWORDS`: entity-specific keywords for RSS filtering

---

## 5. Supabase Schema (Per Entity)

No separate schema — all entities share the existing tables. Entity filtering uses:

- `gate_checks.session_id` prefix convention: `{entity}-{timestamp}`
- `build_episodes.repo_url` for per-entity episode history
- `alert_escalations.project_id` = entity slug

---

## 6. Step-by-Step Replication Checklist

**Target time: 1 working day (8 hours)**

### Hour 1 — Source Document Gathering (1h)
- [ ] Export Linear project to PDF (Settings → Export)
- [ ] Download README.md from primary GitHub repo
- [ ] Copy CLAUDE.md / architecture doc
- [ ] Export latest ZTE score JSON
- [ ] Copy ESCALATION.md or equivalent risk doc

### Hour 2 — NotebookLM Setup (1h)
- [ ] Create new notebook in NotebookLM
- [ ] Upload all 5 required sources
- [ ] Wait for indexing (~10 min)
- [ ] Run acceptance test (10 standard queries)
- [ ] Record notebook ID in `.harness/notebooklm-registry.json`

### Hour 3 — Claude Skills (1h)
- [ ] Create `skills/{entity-slug}/` directory
- [ ] Write `SKILL.md` from template above
- [ ] Test skill load in a Claude session: `hermes skills -g {entity-slug}`

### Hours 4-5 — n8n Workflow (2h)
- [ ] Import workflow template from RestoreAssist export
- [ ] Configure entity-specific variables
- [ ] Test trigger manually
- [ ] Verify Google Doc receives test entry
- [ ] Verify NotebookLM refresh fires

### Hour 6 — Supabase Wiring (1h)
- [ ] Verify `gate_checks` write works for entity sessions
- [ ] Confirm `build_episodes` captures entity repo URL
- [ ] Test Telegram alert fires correctly

### Hours 7-8 — Acceptance & Documentation (2h)
- [ ] Re-run 10 acceptance queries on NotebookLM
- [ ] Update `.harness/notebooklm-registry.json` with notebook ID and status=active
- [ ] Create entity entry in `.harness/projects.json`
- [ ] Mark Linear ticket Done

---

## Notes

- This template was designed from the RestoreAssist onboarding (RA-822). Update it after each new entity is onboarded.
- The 8-hour estimate assumes sources exist. Add 4 hours if documentation needs writing first.
- Board review of this template: Enhancement Review Board 6 May 2026 (RA-949).
