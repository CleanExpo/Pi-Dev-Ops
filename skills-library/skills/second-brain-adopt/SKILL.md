---
name: second-brain-adopt
description: Use when a project, repo, or knowledge bot (CARSI, RestoreAssist, CCW-ERP, MARGOT, any client brain) needs its knowledge tree brought under the Second-Brain Standard — the user says "adopt the standard", "index this knowledge tree / docs", "put X under the second brain", "apply brain.js to", or nexus routes a knowledge-base-adoption need.
allowed-tools: Read, Grep, Glob, LS, Bash, Edit, Write
---

# second-brain-adopt — put a knowledge tree under the Second-Brain Standard

Applies the estate standard (truthful index → deterministic retrieval → prove-it gate)
to one repo's knowledge tree, safely, and ships it through the PR lane. Doctrine:
vault `Wiki/second-brain-standard.md`. Mechanics SSOT: the adoption kit at
`~/2nd Brain/2nd Brain/_system/ADOPTION.md` (okf-index.py + brain.js + bench format)
— read it first; this skill does not restate its commands.

**Scope guard:** the kit is proven on markdown file trees only. If the target's
knowledge lives in a database or vector store, STOP after Step 1 and report "adapter
needed — principles apply, tools don't". Do not force it.

## Step 1 — Preflight (safety before any write)

1. **Canonical checkout only.** Resolve via
   `node "$HOME/2nd Brain/2nd Brain/_system/brain.js" find "canonical checkout <project>"`
   — never a worktree, runner clone, or stale copy.
2. **Hands-off gates.** Honour standing memories before writing: Synthex = no writes;
   MARGOT = hands-off until handback; CCW-CRM = wait for `feat/margot-p0` handback;
   DR/NRPG = Windows machine, not this Mac. A blocked target → report, don't write.
3. **Autogit + churn check.** If `.autogit.json` mode is `auto`, writes auto-ship —
   proceed only via a `feat/*`-exempt branch or accept shipping consciously. Never
   index machine-generated md (harness logs, build output): permanent churn, zero
   retrieval value.
4. **Tree state.** Note dirty/untracked files; you will touch none of them except
   untracked files the new index references (Step 3).

**Done when:** target path is canonical, no hands-off gate applies, the knowledge tree
is human-authored markdown, and the write surface is understood.

## Step 2 — Apply the kit

Run the kit's adoption steps 1–3 against the tree (generate indexes, `check` must exit
0, smoke a real `find`). Regenerate rather than hand-fix wherever the index carries the
`okf:generated` marker; hand-authored indexes get surgical line edits only.

**Done when:** `brain.js check --root <tree>` exits 0 and a smoke question answers from
one file.

## Step 3 — Orphans and secrets

If the generated index references untracked files: secret-scan them
(`sk-ant|sk-proj|AIza|ghp_|xox[bp]-|-----BEGIN|Bearer `). Clean → include them in the
commit (an index must never point at files the remote doesn't have). Dirty → exclude
the file, regenerate the index without it, and flag for rotation.

**Done when:** every file the index references will exist on the remote, secret-scanned.

## Step 4 — Prove it

Write `<tree>/brain-bench.json`: 5 real questions from THIS project with
`expect_file_contains` each. `brain.js bench` logic must pass 5/5 opening one file per
question — keep optimising (descriptions, index lines) until it does. Keep the file
committed so anyone can rerun the gate.

**Done when:** 5/5 pass, benchmark committed.

## Step 5 — Route and ship (PR lane, always)

1. Add the routing note to the repo's `CLAUDE.md`: check the index first, open files
   second; on a miss — Grep, then ADD the missing index line.
2. Branch (`docs/okf-index-layer`), commit only the index files + routing note +
   benchmark (+ Step-3 orphans), push, open a PR stating what was verified.
   **Never** push the default branch directly and **never** self-merge — both are
   classifier-gated by design; the human merges.

**Done when:** PR is open with CI running and the working tree is back on the
default branch, clean.

## Step 6 — Write-back

Add/update the target's row in the rollout map (`Wiki/second-brain-standard.md`), write
one Outcome note in the vault, commit brain-1. New durable lesson → memory (update, not
duplicate).

**Done when:** rollout map + Outcome committed; a future session can see this
adoption's state without re-discovering it.
