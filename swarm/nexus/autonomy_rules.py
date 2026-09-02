"""L3 Bash rule table for the autonomy ladder (RA-7387).

Split out of `autonomy_ladder.py` so this table can grow: that file sits on a
361-line size-gate baseline and the repo's rule is to extract when you touch a
baselined file, never to raise its entry. The rules are data; the classifier
that consumes them is not.

WHY THE ALIAS RULE IS HERE. `git -c alias.X='<verb>' X` runs `<verb>` while
keeping every destructive word inside an option VALUE, where the prefix
normaliser in `autonomy_ladder.strip_git_global_opts` cannot reach it:

    strip_git_global_opts("git -c alias.z='reset --hard' z") -> "git --hard' z"

That is not a theoretical shape. It was a LIVE bypass of the always-on
PreToolUse hook (`.claude/settings.json` -> `autonomy_gate.decide` ->
`autonomy_ladder.classify`), which scored the alias form tier 1 while scoring
the direct form tier 3 — so an unattended session could self-authorize a
force-push, a hard reset or a `clean -fdx`.

Defining a git alias is treated as L3 in its own right rather than parsed for
what it carries. An alias is an arbitrary-subcommand escape hatch, so it is
worth exactly as much as the worst thing it can smuggle, and matching the verb
inside the value is the game that produced this bug. Fail closed: the whole
repo contains no legitimate `git -c alias.` outside the test that documented
this gap, so nothing real is being denied.

OUT OF SCOPE, deliberately: persistent `git config alias.x '<verb>'`. It plants
the same hatch, but `git config --get alias.x` is an ordinary read and a rule
broad enough to catch the write would deny the read too. Narrow the write form
separately rather than over-deny here.
"""

from __future__ import annotations

import re

_L3_BASH = [
    # RA-7387: see the module docstring — an alias definition is an
    # arbitrary-subcommand escape hatch, so it carries the worst tier it could.
    # RA-7387: an alias definition is an arbitrary-subcommand escape hatch,
    # so it carries the worst tier it could smuggle. See the module docstring.
    r"\bgit\b[^\n]*\s-c\s+alias\.",
    r"\bgit\s+merge(?![-\w])",                                       # merge; NOT merge-base/-file/-tree
    r"\bgh\s+pr\s+merge\b",                                          # PR merge to base
    r"\bgit\s+push\b[^\n]*\b(origin\s+)?(main|master|prod|production)\b",  # push to main/prod
    r"\bgit\s+push\b[^\n]*--force[^\n]*\b(main|master)\b",           # force-push main
    r"\bvercel\b[^\n]*(--prod|\bpromote\b)",                         # prod deploy / promote
    r"\bvercel\s+deploy\b",                                          # deploy (prod by default)
    r"\bsupabase\s+db\s+push\b",                                     # prod DB migration
    r"\bprisma\s+migrate\s+deploy\b",
    r"\bsupabase\s+migration\s+up\b",
    r"\bgh\s+secret\s+set\b",                                        # secret rotation
    r"\bvercel\s+env\s+(add|rm|remove)\b",                           # env-secret write
    r">>?\s*(?!\S*\.env\.example)\S*\.env(\.[a-z]+)?\b",             # write to a real .env
    r"\bvercel\s+project\s+add\b",                                  # new service
    r"\bsupabase\s+projects?\s+create\b",
    r"\bgh\s+repo\s+create\b",
    r"\bgh\s+api\b[^\n]*branches[^\n]*protection",                  # branch-strategy change
]
L3_BASH_RE = re.compile("|".join(_L3_BASH), re.IGNORECASE)




# ===========================================================================
# SDK-loop destructive denylist (unattended surface).
# The autonomous generator runs default-deny; on top of the shared L3 set above
# it also refuses LOCAL-destructive commands with no undo path (rm -rf, mkfs,
# dd, DROP TABLE, curl|sh, ...). These are tier-L3 by reversibility but the CLI
# hook lets a *present human* handle them via the normal prompt — hence they
# live in the SDK subset, not L3_BASH. See RA-6882 spec §D3.
# ===========================================================================

# Per-segment rules: matched against each shell segment independently.
SEGMENT_RULES: list[tuple[str, re.Pattern[str]]] = [
    # RA-7387: a git alias definition hides its payload in an option VALUE,
    # where strip_git_global_opts cannot reach it. Denied as a shape rather
    # than parsed for what it carries — see swarm/nexus/autonomy_rules.py.
    ("git-alias-smuggle", re.compile(
        r"\bgit\b[^\n]*\s-c\s+alias\.", re.IGNORECASE)),
    ("rm-rf", re.compile(
        r"\brm\b(?=(?:[^\n]*\s-{1,2}[a-z-]*r))(?=(?:[^\n]*\s-{1,2}[a-z-]*f))",
        re.IGNORECASE)),
    ("find-delete", re.compile(r"\bfind\b[^\n]*\s-delete\b", re.IGNORECASE)),
    ("find-exec-rm", re.compile(r"\bfind\b[^\n]*-exec\s+rm\b", re.IGNORECASE)),

    # --- Work-discard family (RA-7384) --------------------------------------
    # Irrecoverably discards uncommitted or stashed work. These belong HERE and
    # not in _L3_BASH, for the reason this section's header gives: they are
    # locally destructive with no undo path, so the unattended loop must not
    # self-authorize them, while a PRESENT human is the right judge and keeps
    # the normal permission prompt. `classify()` therefore still returns L1 for
    # them by design — the tier is not the control, this denylist is.
    #
    # The gap this closes: `git reset --hard` was reachable by the unattended
    # generator with no gate of any kind, though it destroys uncommitted work
    # unconditionally — while `git merge --abort`, which only undoes an
    # in-progress merge, sat at L3 needing human approval. The dangerous command
    # was the ungated one.
    #
    # Each rule denies only the destroying spelling. Modes that leave the
    # worktree intact (`reset --soft/--mixed`, `restore --staged`, `clean -n`)
    # or that git itself refuses when work would be lost (`reset --keep`, a
    # plain `checkout <branch>`) stay allowed: this must not cost the loop
    # ordinary git.
    ("git-reset-discard", re.compile(
        r"\bgit\s+reset\b[^\n]*\s--(?:hard|merge)\b", re.IGNORECASE)),
    # `--force(?![-\w])` so `git switch --force-create` (branch creation) is not
    # swept up; `-p` cannot work unattended anyway and still discards.
    ("git-checkout-discard", re.compile(
        r"\bgit\s+(?:checkout|switch)\b[^\n]*"
        r"(?:\s--(?:force|discard-changes)(?![-\w])|\s-[a-z]*f\b"
        r"|\s--\s|\s\.\s*$|\s-p\b|\s--patch\b)",
        re.IGNORECASE)),
    # `git checkout <tree-ish> <pathspec>` restores files over the worktree
    # without any of the markers above — `git checkout HEAD src/app.py`. Two
    # non-option operands is the discriminator; the branch-creating spellings
    # (`-b`, `-B`, `--track`, `--orphan`) legitimately take two and are excluded.
    # Both operands must be non-option, or `git checkout -q main` backtracks
    # into a match.
    ("git-checkout-pathspec", re.compile(
        r"\bgit\s+checkout\b(?![^\n]*\s-[bB]\b)"
        r"(?![^\n]*\s--(?:track|no-track|orphan)\b)"
        r"(?:\s+-\S+)*\s+[^-\s]\S*\s+[^-\s]\S*",
        re.IGNORECASE)),
    ("git-restore-worktree", re.compile(
        r"\bgit\s+restore\b(?:(?![^\n]*\s--staged\b)|[^\n]*\s--worktree\b)",
        re.IGNORECASE)),
    ("git-clean-force", re.compile(
        r"\bgit\s+clean\b[^\n]*\s(?:--force\b|-[a-z]*f[a-z]*\b)", re.IGNORECASE)),
    ("git-stash-discard", re.compile(
        r"\bgit\s+stash\s+(?:drop|clear)\b", re.IGNORECASE)),
    ("git-force-push", re.compile(
        r"\bgit\s+push\b[^\n]*\s(?:--force\b|--force-with-lease\b|-[a-z]*f\b|\+[\w./-]+)",
        re.IGNORECASE)),
    ("sql-drop", re.compile(r"\bDROP\s+(?:TABLE|DATABASE|SCHEMA)\b", re.IGNORECASE)),
    ("sql-truncate", re.compile(r"\bTRUNCATE\s+(?:TABLE\s+)?\w", re.IGNORECASE)),
    ("sql-delete-no-where", re.compile(
        r"\bDELETE\s+FROM\b(?![\s\S]*\bWHERE\b)", re.IGNORECASE)),
    ("vercel-prod", re.compile(r"\bvercel\b[^\n]*--prod\b", re.IGNORECASE)),
    ("supabase-db-push", re.compile(r"\bsupabase\s+db\s+push\b", re.IGNORECASE)),
    ("prisma-migrate", re.compile(r"\bprisma\s+migrate\s+(?:deploy|reset)\b", re.IGNORECASE)),
    ("npm-publish", re.compile(r"\bnpm\s+publish\b", re.IGNORECASE)),
    ("gh-release", re.compile(r"\bgh\s+release\s+create\b", re.IGNORECASE)),
    ("terraform", re.compile(r"\bterraform\s+(?:apply|destroy)\b", re.IGNORECASE)),
    ("kubectl-delete", re.compile(r"\bkubectl\s+delete\b", re.IGNORECASE)),
    ("mkfs", re.compile(r"\bmkfs\b", re.IGNORECASE)),
    ("dd-to-device", re.compile(r"\bdd\b[^\n]*\bof=/dev/", re.IGNORECASE)),
]

# Whole-command rules: inherently cross-segment (a pipe IS the payload).
WHOLE_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("pipe-to-shell", re.compile(
        r"(?:curl|wget|fetch|base64)\b[^\n]*\|\s*(?:sudo\s+)?(?:ba)?sh\b", re.IGNORECASE)),
    ("eval-exec", re.compile(r"\beval\s+[\"'$]", re.IGNORECASE)),
    ("interpreter-delete", re.compile(
        r"\b(?:python3?|node|ruby|perl)\b[^\n]*\s-[ce]\b[^\n]*"
        r"(?:rmtree|os\.remove|os\.unlink|unlinkSync|rmSync|File\.delete)",
        re.IGNORECASE)),
]

# Split on shell command separators — but NOT a bare pipe, so pipelines stay
# intact (handled by WHOLE_RULES) and `find ... | xargs rm` is not severed.
