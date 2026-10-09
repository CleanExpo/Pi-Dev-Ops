# Task, checkpoint and evidence templates

Keep universal instructions limited to identity, authority, source order, protected
boundaries and completion proof. Load the relevant skill and evidence for the task
when needed. These templates supplement existing Judge/SPM/handoff commands.

## Task packet

```text
Outcome: <observable result and user benefit>
Starting state: <repo / branch / exact SHA / dirty paths preserved>
Owner: <one writer for these files or responsibility>
Scope: <allowed paths, exact change, existing capability to reuse>
Evidence to read: <2–5 first-source paths or vendor URLs>
Acceptance: <checks that would detect a wrong implementation>
Runtime contract: <CLI/API, requested model, permissions, working directory>
Budget: <included access only, wall time, output cap, max retries>
Stop: <missing authority, unavailable included route, irreversible action>
Deliver: <changed paths, result, checks, receipt paths, blockers, next action>
```

## Checkpoint before compact or handoff

```text
Outcome reached: <verified result or precise unfinished state>
Current tree: <repo / branch / SHA / dirty file hashes>
Locked decisions: <authority, cost, publication, protected files>
Keep: <facts, evidence, next steps; link long logs>
Do not redo: <completed checks and their exact-tree limits>
Unresolved: <blocker, owner, condition that clears it>
Next command: <first bounded command in the correct working directory>
```

Compaction is an evidence-preservation step. Never summarize away scope, pending
approval, dirty work, failing checks or the source revision. A newer tree invalidates
earlier review/test evidence.

## Execution receipt

```json
{
  "task_id": "fixture-or-ticket-id",
  "source_revision": "exact-sha",
  "substrate": "codex-cli-or-claude-cli-or-api",
  "requested_model": "documented-id-or-alias",
  "observed_model": null,
  "account_access": "verified-included-or-unknown",
  "status": "verified-or-failed-or-blocked",
  "exit_code": null,
  "started_at": "timestamp",
  "finished_at": "timestamp",
  "usage": null,
  "evidence_paths": [],
  "remaining_blocker": "condition-that-clears-it"
}
```

Null means unknown. A requested model, an old status file, a healthy URL, zero exit
status, or a self-scored response does not prove model identity, deployed revision,
quality, usage or completion. Do not store secrets or customer data in the receipt.

## Independent review

```text
Reviewed tree: <SHA plus dirty diff hashes>
Checks rerun: <commands, exit codes, evidence paths>
Adversarial cases: <wrong permission, stale status, invalid output, timeout>
Findings: <path / line / effect / fix>
Decision: <pass for this scope or blocked with recovery criteria>
Runtime/quality claim: <measured comparison or explicitly unproven>
```
