# Capability Intelligence Loop Activation

Date: 2026-06-16
Owner: Pi-CEO / Unite-Group command-center

This runbook commits the capability intelligence loop to the five activation steps needed to move from safe dry-run automation to a live operating loop.

## Current State

- `scripts/run_capability_loop.py` researches external AI capability sources, writes Obsidian/2nd-brain artifacts, and validates CRM intake proposals.
- `scripts/capability_crm_import.py` validates the manifest or CRM JSONL bridge and can post blocked proposals to Unite-Group CRM.
- `.harness/cron-triggers.json` schedules `capability-loop-daily-0530`.
- CRM posting remains opt-in through `--post` or `UNITE_CRM_CAPABILITY_POST=1`.

## Five Activation Commitments

### 1. Enable CRM posting deliberately

Gate: do not enable broad CRM posting until one controlled import succeeds.

Command shape:

```bash
python3 scripts/capability_crm_import.py \
  /Users/phillmcgurk/2nd-brain/Outcomes/capability-scout/2026-06-16-capability-scout.json \
  --crm-url http://localhost:3000/api/command-center/control-panel/capability-intake \
  --json
```

Acceptance:

- Dry-run returns `ok: true`.
- `proposal_count` matches the manifest `crm_task_count`.
- Every proposal is `status: blocked`.
- Every proposal includes `capability-scout`, `approval-required`, and `hermes-intake` tags.

### 2. Run one sandbox CRM import

Gate: import a single top candidate first, not the whole feed.

Acceptance:

- Unite-Group CRM creates or dedupes exactly one blocked task.
- The CRM task has `assignee_name: Phill approval`.
- The CRM task has `obsidian_path` pointing to the matching 2nd-brain source note.
- Re-running the same import returns the existing task instead of inserting a duplicate.

### 3. Wire Hermes consumption

Gate: Hermes may consume only approved or blocked-intake task packets; it must not install, execute, or ship a capability from scout output alone.

Acceptance:

- Hermes reads CRM sync packets by `obsidian_path`.
- `hermes_lane` routes to the intended lane: `engineering`, `research-ops`, `content-systems`, or `watchlist`.
- Hermes creates or updates a Kanban card with the CRM task id.
- CRM remains the source of truth for status.

### 4. Add read-back validation

Gate: every scheduled run must prove the full path, not just produce files.

Acceptance:

- Brain report exists.
- Manifest parses.
- CRM intake JSONL parses.
- CRM task exists for posted proposals.
- Hermes sync packet exists for CRM tasks due for execution.
- Failures are reported as validation failures, not silent partial success.

### 5. Tighten scout quality

Gate: high scores require explicit AI/capability evidence, not only project or stack keyword overlap.

Acceptance:

- A candidate cannot score high from generic words such as `python`, `crm`, or `workflow` alone.
- Source-level fetch errors are reported in the manifest.
- Repeated discoveries use a stable idempotency key.
- Candidates below the action threshold remain watchlist-only.

## Default Safe Run

```bash
python3 scripts/run_capability_loop.py \
  --limit 40 \
  --min-score 45 \
  --brain-root /Users/phillmcgurk/2nd-brain \
  --json
```

This writes Brain artifacts and validates CRM intake without posting to CRM.

## Live Posting Run

Use only after the one-candidate sandbox import passes.

```bash
UNITE_CRM_CAPABILITY_POST=1 \
python3 scripts/run_capability_loop.py \
  --limit 40 \
  --min-score 45 \
  --brain-root /Users/phillmcgurk/2nd-brain \
  --json
```

The CRM bearer is read from `UNITE_CRM_ADMIN_TOKEN` by default. Do not place tokens in repo files.

## Rollback

- Disable the scheduled trigger by setting `enabled: false` on `capability-loop-daily-0530`.
- Keep generated 2nd-brain artifacts for audit unless they contain incorrect source data.
- Do not delete CRM tasks; close or cancel them through the command-center so the approval trail remains visible.
