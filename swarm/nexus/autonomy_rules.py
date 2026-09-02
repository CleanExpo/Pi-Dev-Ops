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

# RA-7383: the two target-based push rules, and everything else, derived by
# IDENTITY from `_L3_BASH` rather than restated — a second copy would drift from
# the first, and a drifted copy here would silently stop protecting whichever
# rule fell out of it. The assert is the tripwire for that drift.
#
# `autonomy_ladder.classify` decides every non-push L3 signature on this
# expression FIRST and never reconsiders it, so the push narrowing in
# `push_targets` can only ever touch a push verdict. See that module for why the
# narrowing subtracts from an authoritative match instead of replacing it.
_PUSH_TARGET_PATTERNS = [p for p in _L3_BASH if r"\bgit\s+push\b" in p]
_L3_BASH_OTHER = [p for p in _L3_BASH if p not in _PUSH_TARGET_PATTERNS]
if len(_PUSH_TARGET_PATTERNS) != 2:
    # `raise`, not `assert`: `python -O` strips asserts, and a drift tripwire that
    # disappears under a flag is the same "check that cannot fail" shape this
    # ticket family exists to stop. If a third push rule is added, decide
    # deliberately whether the narrowing may subtract from it — do not widen this
    # count to make the import succeed.
    raise RuntimeError(
        f"push-rule identification drifted from _L3_BASH: expected 2 target-based "
        f"push patterns, found {len(_PUSH_TARGET_PATTERNS)}"
    )
L3_BASH_EXCLUDING_PUSH_TARGET_RE = re.compile("|".join(_L3_BASH_OTHER), re.IGNORECASE)

# Re-exported so `autonomy_ladder` keeps a single rules import. The by-path
# fallback mirrors the one in that module: this file is loaded by path in tests
# and by the hook, where `swarm.nexus` is not an importable package.
try:
    from .push_targets import push_targets_are_all_unprotected  # noqa: F401
except ImportError:  # pragma: no cover - exercised by the by-path test loader
    import importlib.util as _ilu
    from pathlib import Path as _Path

    _spec = _ilu.spec_from_file_location(
        "swarm_nexus_push_targets", _Path(__file__).with_name("push_targets.py")
    )
    _pt = _ilu.module_from_spec(_spec)
    assert _spec.loader is not None
    _spec.loader.exec_module(_pt)
    push_targets_are_all_unprotected = _pt.push_targets_are_all_unprotected

# --- Git global options (RA-7386) ------------------------------------------
# Every git rule here anchors on `git <subcommand>`, but git accepts global
# options in between, so `git -C /repo reset --hard` reached none of them and
# `git -C . push origin main` fell L3 -> L1.
#
# CONTRACT — read before calling. Callers MUST test the ORIGINAL string too and
# deny (or raise the tier) if EITHER form hits. The rewrite can then only ever
# ADD a match, never remove one: a bug here over-denies instead of opening a
# bypass. That is a property of the construction, not of corpus coverage — which
# matters, because four designs on this file have leaked and each passed its own
# author's corpus. Two corollaries:
#   * never match on the normalised form ALONE;
#   * never normalise for a pattern whose hit LOWERS the tier (READ_ONLY_BASH),
#     which would turn a raise into a drop — `git -C . status` must stay L1.
#
# The option list is what git 2.43 actually runs a subcommand after, checked by
# running each one: `--exec-path` (bare), `--html-path`, `--man-path`,
# `--info-path`, `-v` and `-h` print and exit, so they are not vectors.
GIT_GLOBAL_OPT = re.compile(
    r"""[ \t]+(?:
          -[cC][ \t]+\S+                      # -c name=value, -C <path>
        | --(?:git-dir|work-tree|namespace|super-prefix|attr-source
             |config-env)(?:=\S*|[ \t]+\S+)
        | --exec-path(?:=\S*)?
        | --(?:no-pager|paginate|bare|no-replace-objects|no-optional-locks
             |no-lazy-fetch|literal-pathspecs|glob-pathspecs|noglob-pathspecs
             |icase-pathspecs)
        | -[pP]
    )(?=[ \t]|\Z)""",
    re.VERBOSE | re.IGNORECASE,
)
_GIT_TOKEN = re.compile(r"\bgit(?=[ \t])", re.IGNORECASE)


def strip_git_global_opts(text: str) -> str:
    """Drop git's global options so `git <subcommand>` is adjacent again.

    ``git -C /repo reset --hard`` -> ``git reset --hard``. A quoted option value
    containing spaces is only partly consumed, leaving a harmless fragment; that
    is why the caller must still match the original. See the CONTRACT above.

    Deliberately NOT capped at a fixed option count: a cap hands back a bypass one
    option past it, and repeating ``-C`` is valid git. No cap is needed, because
    ``.match(text, cursor)`` anchors each attempt at the cursor and every match
    begins with ``[ \\t]+``, so each one advances. Spans never overlap, leaving the
    rewrite linear — it runs inside a PreToolUse hook, where a hang is a DoS.
    """
    out: list[str] = []
    pos = 0
    for m in _GIT_TOKEN.finditer(text):
        if m.start() < pos:
            continue  # already consumed as a preceding option's value
        out.append(text[pos:m.end()])
        cursor = m.end()
        while True:
            opt = GIT_GLOBAL_OPT.match(text, cursor)
            if opt is None or opt.end() <= cursor:
                break
            cursor = opt.end()
        pos = cursor
    out.append(text[pos:])
    return "".join(out)

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
