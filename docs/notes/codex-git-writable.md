# Codex workspace-write and `.git` — the writable-roots fix

**Filed:** 17/08/2026 · **Status:** recorded, NOT wired into any script
**Verified against:** codex-cli 0.144.6

This is a note, not a change. Nothing in the repo reads it and nothing should until
Codex is actually dispatching reviews again. It exists because the fix is undocumented
and was expensive to find; leaving it in a session transcript means finding it twice.

## The problem

Under `--sandbox workspace-write`, Codex can write the working tree but not `.git`.
Any command that needs to record something — `git commit`, `git stash`, even a
`git worktree` operation that updates administrative files — fails, usually with a
permission error that names a path inside `.git` rather than saying "the sandbox
denied this".

## The fix

`writable_roots` must name **the `.git` path itself**. Naming the repository root is
not enough: the sandbox treats `.git` as a distinct root, so a writable worktree with
a read-only `.git` is the default outcome, not an edge case.

```bash
codex exec --sandbox workspace-write \
  -c "sandbox_workspace_write.writable_roots=[\"$(git rev-parse --absolute-git-dir)\"]" \
  - < brief.txt
```

## Linked worktrees need BOTH paths

This is the part that is easy to get half-right, and half-right fails in a way that
looks like the fix did not work at all.

A linked worktree (anything created by `git worktree add`) has **two** git
directories:

| Command | Returns | What lives there |
|---|---|---|
| `git rev-parse --absolute-git-dir` | `<main>/.git/worktrees/<name>` | this worktree's own HEAD, index, refs |
| `git rev-parse --path-format=absolute --git-common-dir` | `<main>/.git` | the shared object database, packed refs, config |

Both must be in `writable_roots`. Writing a commit touches the per-worktree
administrative directory **and** the shared object store, so granting one and not the
other produces a failure partway through the operation.

```bash
GITDIR=$(git rev-parse --absolute-git-dir)
COMMONDIR=$(git rev-parse --path-format=absolute --git-common-dir)

codex exec --sandbox workspace-write \
  -c "sandbox_workspace_write.writable_roots=[\"$GITDIR\",\"$COMMONDIR\"]" \
  - < brief.txt
```

In a normal (non-linked) checkout the two commands return the same path, so passing
both is harmless and the snippet works everywhere. Do not branch on it.

## What this costs, stated plainly

**A writable `.git` is a writable `.git/hooks`.** Hooks run as ordinary processes
outside the sandbox's supervision — that is the point of a hook. So granting this
grants the sandboxed process a route to execute unsandboxed code on the next git
operation in that repository.

That is an acceptable trade for a *reviewer* that must commit its own report in a
disposable worktree. It is not acceptable as a default for anything that runs against
a checkout someone else will use afterwards. If this is ever wired into a script, the
worktree it points at should be created fresh and destroyed after the run, and nothing
should reuse it.

## Freshness

`writable_roots` and the `.git`-as-separate-root behaviour are **undocumented**. This
was established empirically against **codex-cli 0.144.6** and may change silently on
any upgrade. Re-check after every `codex` version bump: run a sandboxed `git commit`
in a throwaway worktree and confirm it succeeds before trusting a review run that
depends on it.

## Why it is not wired in

Codex is not currently dispatching reviews from this repository. Wiring an
unsandboxed-code-execution path into a script that nothing runs is how a capability
gets forgotten and then rediscovered by an incident. When Codex review dispatch comes
back, this note is the starting point — and the fresh-worktree constraint above is
part of the change, not a footnote to it.
