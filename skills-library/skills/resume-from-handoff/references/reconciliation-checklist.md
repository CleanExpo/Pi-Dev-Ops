# Resume Reconciliation Checklist

Use this checklist before resuming work from a handoff. Phases 1–3 are read-only.

## Must verify (read-only) before resuming

- [ ] The input is a recognisable `session-handoff` report.
- [ ] The handoff's branch exists and is checked out (or can be).
- [ ] The claimed shipped commits exist (`git cat-file -t <sha>`).
- [ ] The "what shipped" / "key files" exist with the claimed status.
- [ ] The working tree is clean/dirty as the handoff's running state implies.
- [ ] The open PR/issue is in the stated state (open / merged / closed).
- [ ] Re-runnable verification commands pass (or are honestly marked NOT CHECKED).

## Reconciliation verdict

Choose one:

- **MATCH** — repo matches the handoff; resume directly.
- **MINOR DRIFT** — small, non-conflicting changes since the handoff; resume with noted adjustments.
- **MATERIAL DRIFT** — significant divergence; do not resume blindly. Surface and confirm.
- **CANNOT RESUME** — branch/commits missing, or the work is obsolete. Stop and ask.

## Stop conditions — do NOT resume; surface and ask

- The handoff's branch or claimed commits are missing.
- The working tree has conflicting uncommitted changes.
- The PR was already merged/closed in a way that obsoletes the work.
- The handoff's "first command to run" would now be destructive or wrong.

## Must not happen

- Do not edit, commit, push, deploy, or migrate before Phase 2 verification completes.
- Do not claim verification passed unless it was actually run.
- Do not redo work the handoff lists under "Do not redo".
- Do not resume on MATERIAL DRIFT or CANNOT RESUME without user confirmation.
