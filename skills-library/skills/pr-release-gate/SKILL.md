---
name: pr-release-gate
description: Use before any git push, pull-request creation or ready-for-review action, including autonomous loops and follow-up fixes.
allowed-tools: Read, Grep, Glob, Bash
---

# PR release gate

Opening a PR is a release boundary, not a progress update. Never push or open a PR merely
because implementation stopped.

## Gate

1. **Refresh.** Fetch the target branch. Start from current `origin/main`; never reuse a
   closed, merged or superseded PR branch. Check existing open and closed PRs for the head
   branch before creating another.
   **Complete when:** the base SHA and branch history are current and recorded.

2. **Prove a real delta.** Do not trust GitHub's three-dot display or a whole-tree comparison
   on a branch that is behind. Enumerate paths changed by the branch since its merge base, then
   compare each candidate path's final blob with current `origin/main`. At least one must differ.
   If all candidate blobs already exist on `main`, there is no content to review and no PR may
   open. Confirm the remaining diff contains only the requested coherent change.
   **Complete when:** a non-empty, scoped content delta exists.

3. **Provision, then test the exact commit.** Commit the candidate, leave the worktree clean,
   then establish every generated artefact those checks read — a shell's inherited environment
   is not the one CI measures, and a stale artefact makes the gate report the environment
   instead of the candidate:

   ```bash
   python3 ~/.claude/skills/pr-release-gate/scripts/pr_release_gate.py provision
   ```

   It asserts the repo's declared Node version and refuses a mismatch rather than switching it,
   installs with the package manager the repo declares carrying its own CI's flags, runs the
   generated-artefact steps the repo declares (`prisma generate` for a schema), and builds
   every `file:`-linked package whose output a compiler resolves — each discovered by parsing
   the repository, none of it hardcoded. A provisioning step that fails blocks; it never warns.
   Then run the repository's complete relevant definition of done: type-check, lint, tests,
   build and project guards. Fix failures and repeat, at most three test-fix cycles before
   reporting blocked. CI after opening a PR does not replace this step; the step 6 recorder
   provisions again before it binds any exit code to the head.
   **Complete when:** provisioning exits zero and every required local command exits zero on
   the candidate HEAD.

   **Then mirror GitHub, not a subset of it** (founder, 19/09/2026, after #782 reached him red
   behind "26/26 green"): `python3 scripts/ci_mirror.py --repo <worktree>` runs every step of
   every `pull_request` workflow whose paths match the change, with `services:` containers
   started in Docker. A step that cannot run locally FAILs unless it is exempted with a reason
   in the repo's `.github/ci-mirror.exempt.json` or `ci-mirror-exempt/<owner>__<repo>.json`.
   `issue` runs it and binds the PASS into the receipt, `verify` refuses a receipt without it,
   and `gh pr ready` is refused until GitHub's own checks on the head are all green. Phill gets
   a PR link only after that, never while checks are pending.

4. **Independent review.** Dispatch a second reviewer — fresh context, never the implementing
   agent or its subagents. **Codex is one option, not the requirement.** Pick in this order:

   1. **OpenRouter swarm** — `scripts/swarm_review.py`, three finders proposing and a filter
      adjudicating. Non-Anthropic, so it gives real model diversity, and it is **$0.00**.
      Measured on `swarm_bench_corpus.json` (142 models, four real defects):
      `nemotron-3.5-lightning:free` scored **4/4** and was the fastest in the field,
      outscoring `claude-opus-5` (2/4), `openai/gpt-5` (3/4) and `grok-4.6` (2/4). Frontier
      badge did not predict defect detection. **Chunk the diff** — see the caveat below.
   2. **A second Max-plan CLI** — a different vendor's subscription reviewer, no metered spend.
   3. **Codex** — only when 1 and 2 are unavailable or have disagreed. It is metered, so it is
      the expensive option, not the default one.

   Codex being unavailable is **not** a reason to stop. It was treated as one on 2026-08-18,
   which blocked a release for a day while the free swarm sat unused in this very directory.

   **Two rules for any reviewer, from measured failures:**
   - **Chunk under the context budget and check coverage.** `swarm_review.py` silently
     truncated a 283,638-char diff to 90,000 — 30 of 87 files reviewed, the security file not
     among them, `0 findings` reported. Fixed to warn, but always compare files-reviewed
     against `git diff --name-only`.
   - **Prove the reviewer can fail before quoting its pass.** Plant a real defect in the same
     content type and confirm it fires. Four such controls (TypeScript, `.mjs`, markdown,
     Python) took minutes and are what makes a clean verdict evidence rather than silence.

   Use the brief template in
   [`references/reviewer-brief.md`](references/reviewer-brief.md) — the brief carries only
   what varies (SHAs, scope, budget, known facts); the template carries the report contract
   and the review rubric, including the mutation-control requirement.
   **Complete when:** the reviewer writes a SHA-bound report matching
   [`references/reviewer-report-schema.md`](references/reviewer-report-schema.md).

5. **Drain findings.** P0/P1 block release: fix, rerun every affected gate, new commit, new
   SHA back to the reviewer — a PASS for an older SHA is invalid. If the reviewer is
   unavailable or crashes, queue the work and stop; never self-certify. P2 findings do not
   block (founder stopping rule, 03/08/2026): file each as a tracked ticket; the reviewer
   records them as documented warnings outside `blocking_findings`.
   **Complete when:** the exact final HEAD has `PASS` with zero unresolved P0/P1 blockers
   and every documented P2 carries a ticket reference.

6. **Issue the receipt.** Run the bundled recorder with all required test commands. It
   executes the commands and binds their exit codes plus the independent report to the exact
   HEAD and base:

   ```bash
   python3 ~/.claude/skills/pr-release-gate/scripts/pr_release_gate.py issue \
     --primary-agent <claude|codex> \
     --review-report <absolute-review-report.json> \
     --test '<repo type-check command>' \
     --test '<repo lint command>' \
     --test '<repo test command>'
   ```

   `--primary-agent` is the agent releasing the change, and the report's `implementation_agent`
   must equal it — for a Dependabot or other bot-authored PR too, or `issue` refuses with
   "review implementation_agent does not match primary". The brief template carries that slot.

   `issue` copies the reviewer's report into `~/.local/state/pr-release-gate/reviews/`
   keyed by head SHA before it signs the receipt (RA-7534). The disposable review
   worktree from step 4 is safe to remove immediately after this step — the receipt no
   longer points back into it, so cleanup can never invalidate a receipt that already
   issued clean.

   **Complete when:** `verify` returns `PR_RELEASE_GATE_PASS`.

7. **Release through the correct lane.** Push the final tip, **wait until GitHub itself has
   run that exact SHA green** (the workflows run on `push` to any branch), then open one
   draft PR with a non-empty body containing the SHA, exact commands/results and reviewer
   identity. The hook refuses `gh pr create` before that, and names a job GitHub never
   started (runner offline, billing) separately from one that ran and failed: from 13/09 to
   25/09/2026 GitHub started no job at all on skills-library, every PR showed red, and seven
   merged untested. Where `main` requires the `nexus/release-receipt` status (Unite-Group
   since 27/09/2026, and CleanExpo/skills-library: #59 stayed BLOCKED until attest ran), run
   `pr_release_gate.py attest --repo-path <worktree>` after the push: it re-verifies the
   receipt, refuses unless the branch head GitHub reports is the receipted head, and posts the
   status on that one SHA. The branch read is the local branch's `origin` upstream when one is
   configured, else the local branch name. It refuses to run with any `GIT_*` variable other
   than `GIT_EDITOR`/`GIT_PAGER`/`GIT_ASKPASS`, or `GH_HOST`/`GH_REPO`, set. GitHub's "Update
   branch" button makes a new head and voids the receipt and the review; strict status checks
   are off on these repos, so tell the founder not to click it once a receipt exists. Do not add commits after opening. Keep it draft until fresh remote checks
   for that exact SHA are green; `gh pr ready --undo` (back to draft) is always allowed. Who merges — the human default and the `UG-AUTONOMY-001` exception with its full
   conditions — is defined in [`references/merge-lanes.md`](references/merge-lanes.md).
   **Complete when:** one evidence-backed PR awaits its lane's merge actor.

   Run each release action as one direct command with the tool working directory set to the
   target repository. Do not chain `cd`, `pushd`, conditionals, pipes, newlines or multiple
   PR actions. Put multiline PR text in a body file.

   **Reporting rule (founder, 25/09/2026, binding).** "Green" in any message to Phill means
   GitHub's checks on the exact pushed head, nothing else. A local run is "local checks pass",
   never "green". Every status report names three things: the PR's draft or ready state as
   GitHub shows it, the pushed head SHA, and GitHub's result for that SHA. Name any unpushed
   commit as unpushed. Twice on 25/09 the local mirror passed while GitHub failed the same head.

## Absolute stops

- No exemptions for docs, tests, dependency bumps, urgency or "small" changes.
- No CodeRabbit/status badge may substitute for the independent SHA-bound report.
- No stale/superseded branch, stale receipt, dirty tree, empty effective diff, failed/skipped
  gate or unresolved P0/P1 finding.
- No `--no-verify`, force push or human-override variable by an agent.
- No compound or directory-changing shell command at the release boundary.
- Related changes update one existing branch/PR; they do not create a stream of replacement PRs.
- Never author, edit or reformat the reviewer's report file — reviewer authorship is the
  evidence; a mis-shaped report goes back to the reviewer with the recorder's error text.
