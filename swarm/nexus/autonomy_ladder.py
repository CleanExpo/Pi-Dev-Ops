"""swarm/nexus/autonomy_ladder.py — single source of truth for the autonomy ladder.

RA-6882: two safety gates enforce the autonomy ladder on two disjoint surfaces —

  * ``app/server/tool_gate.py``   — SDK ``can_use_tool`` callback for the *unattended*
    autonomous loop. Posture: **allowlist / default-deny**; Bash inspected against a
    destructive **denylist**.
  * ``swarm/nexus/autonomy_gate.py`` — ``PreToolUse`` hook for the *interactive*
    human-driven CLI. Posture: **denylist of genuine L3**; L0-L2 pass through to the
    normal permission prompt.

Before RA-6882 each gate carried its own copy of the destructive-command regexes and
its own tier logic, so the two drifted independently. This module now owns ALL of it:
the tier constants, the named signature registry (every regex defined ONCE), and the
canonical :func:`classify`. Both gates import from here.

The two gates keep their *different dispositions* on purpose (unattended → default-deny;
human-present → deny-only-L3). That divergence is intentional and documented per RA-6882
acceptance criterion #2 — what is NO LONGER allowed to diverge is the pattern set and the
tier of any given call. :func:`classify` is that shared tier; a parity test asserts both
gates agree on it.

Pure: no I/O, no SDK import.
"""
from __future__ import annotations

import re
from typing import Any, Optional

# --- Tiers (DeepMind AGI→ASI continuum mapped to autonomy-ladder L0-L3) ------
TIER_READ = 0          # L0 — read-only / advise
TIER_LOCAL = 1         # L1 — reversible single-domain act
TIER_OUTWARD = 2       # L2 — cross-domain / outward-facing, still reversible
TIER_IRREVERSIBLE = 3  # L3 — irreversible / strategic — STOP for human/Board

# ===========================================================================
# Signature registry — every destructive/strategic regex defined ONCE.
# Consumers select the named subset they enforce; see the per-gate imports.
# ===========================================================================

# --- Read-only signatures (L0) ---------------------------------------------
READ_ONLY_TOOLS = frozenset({
    "Read", "Grep", "Glob", "WebFetch", "WebSearch", "NotebookRead",
    "ListMcpResourcesTool", "ReadMcpResourceTool", "TaskList", "TaskGet",
})
READ_ONLY_BASH = re.compile(
    r"^\s*(cat|ls|pwd|echo|grep|rg|find|head|tail|wc|which|stat|"
    r"git\s+(status|log|diff|show|branch|remote|fetch|rev-parse|ls-files|ls-tree)|"
    r"gh\s+pr\s+(view|checks|list|diff)|gh\s+(issue|run)\s+(view|list))\b"
)

# --- L2: cross-domain / outward-facing but reversible ----------------------
# A feat/* push or a PR-open — outward but undoable. Explicitly NOT a push to a
# protected branch (that is L3, matched first).
L2_BASH = re.compile(
    r"\bgh\s+pr\s+create\b|"
    r"\bgit\s+push\b(?![^\n]*\b(main|master|prod|production)\b)"
)

# --- L3: strategic / irreversible — Bash signatures ------------------------
# Precise signatures: narrow enough that an L2 feat/* push or PR-open does NOT
# match. Any match => L3. This is the CLI hook's L3 set (interactive surface):
# merge/deploy/migrate/secret/env/provision/branch-strategy — genuine
# "stop for a human/Board" actions, all rare in an interactive session.
#
# The push rules deliberately keep a WHOLE-LINE `[^\n]*` gap, and the cost is
# known: a feature-branch push chained with a read-only `git rev-parse
# origin/main` is classified L3 even though nothing touches a protected ref.
# That is a false positive on a fail-closed gate — lost capability, one
# redundant approval prompt — and it is the cheaper failure. Three attempts to
# narrow it all opened real bypasses (RA-7382); see the rejected designs below
# and `tests/test_autonomy_ladder_l3_segments.py`.
#
# Rejected, in order, each killed by a measured leak against a bash oracle:
#   1. Split the command on shell separators, test each segment. Quote-blind: a
#      separator inside a quoted ARGUMENT severs the signature and neither half
#      matches. 59-75 leaks, including a production `vercel -e CSP="...; ..."
#      --prod` and a branch-protection DELETE.
#   2. Mask quoted spans, then split. Closed part of it; escaped quotes,
#      backticks, `${...}`, ANSI-C `$'...'` and a bare `a\;b` still leaked 75. A
#      hand-rolled scanner tracking quote and nesting depth still leaked 15.
#   3. Constrain the gap to a repetition of one shell-argument-shaped unit, so
#      it cannot traverse a BARE separator. This one looked airtight and was
#      shipped before review caught it: a quoted span is consumed WHOLE, so when
#      the protected ref is itself quoted the gap swallows it and the trailing
#      `(main|master|prod|production)` can never match. `git push origin "main"`
#      — an ordinary command needing no adversarial intent — dropped L3 to L1,
#      with 18 in the same class. Letting the gap traverse quote characters
#      fixes the leak and makes the pattern catastrophically backtracking:
#      42 s on 18 quoted arguments, a DoS in a PreToolUse hook.
#
# A narrowing that fails CLOSED (fall back to the whole line whenever the parse
# is uncertain) is the only safe shape left, and it has to be computed in code
# with a bound, not spelled as a regex. Tracked separately; do not retry a
# regex tweak here.
_L3_BASH = [
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

# --- L3: strategic / irreversible — non-Bash tool-name signatures ----------
# MCP + built-in tool names that are inherently L3.
L3_TOOL_RE = re.compile(
    r"(deploy_to_vercel|apply_migration|deploy_edge_function|create_project"
    r"|pause_project|restore_project|delete_branch|merge_branch|db_push)",
    re.IGNORECASE,
)
# Destructive/strategic verbs in an otherwise-unknown tool name -> higher tier.
L3_VERB_RE = re.compile(r"(rotate|charge|payout|transfer|drop_)", re.IGNORECASE)


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
SHELL_SEP = re.compile(r"&&|\|\||;|\n")

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


# Allowlist (default-deny) for the unattended SDK generator.
ALLOWED_TOOLS: frozenset[str] = frozenset({
    "Bash", "bash", "BashOutput",
    "Read", "Edit", "Write", "MultiEdit",
    "Glob", "Grep", "LS",
    "NotebookEdit", "NotebookRead", "TodoWrite",
})

# MCP tools whose name alone implies an irreversible/production effect.
MCP_DESTRUCTIVE_NAME = re.compile(
    r"mcp__.*(?:apply_migration|delete_branch|delete_project|pause_project|"
    r"reset_branch|deploy_to_vercel|delete_event|delete_|merge_branch)", re.IGNORECASE)

# MCP tools that only read — safe to allow under the default-deny posture.
MCP_READONLY_NAME = re.compile(
    r"mcp__.*(?:list_|get_|search|read_|fetch|check_|status|describe|"
    r"download_|find_|suggest|complete_authentication|authenticate)", re.IGNORECASE)


# ===========================================================================
# Canonical classifier — the single source of truth for the autonomy tier.
# ===========================================================================
def classify(tool_name: str, tool_input: Optional[dict[str, Any]]) -> int:
    """Return the autonomy tier (0-3) for a pending tool call.

    Decision rule (autonomy-ladder): rate by reversibility x domain breadth; the
    HIGHER wins; when genuinely unsure between two tiers, take the higher.

    This is the shared tier both gates agree on (RA-6882). Each gate then applies
    its own *disposition* to that tier: the SDK loop denies by default-deny
    allowlist (and additionally refuses SDK-subset local-destructive commands);
    the CLI hook denies only tier == L3 and passes L0-L2 to the human.
    """
    tool_input = tool_input or {}
    name = tool_name or ""

    # Tool-name L3 (MCP prod deploys / migrations / destructive verbs) — first.
    if L3_TOOL_RE.search(name) or L3_VERB_RE.search(name):
        return TIER_IRREVERSIBLE

    if name == "Bash":
        cmd = str(tool_input.get("command", ""))
        # RA-7386: also test the form with git's global options stripped, so
        # `git -C . push origin main` cannot duck the L3 rules. Original OR
        # normalised, so this can only ever RAISE the tier — and deliberately
        # NOT applied to READ_ONLY_BASH, where a hit LOWERS it.
        norm = strip_git_global_opts(cmd)
        if L3_BASH_RE.search(cmd) or L3_BASH_RE.search(norm):
            return TIER_IRREVERSIBLE
        if READ_ONLY_BASH.search(cmd):
            return TIER_READ
        if L2_BASH.search(cmd) or L2_BASH.search(norm):
            return TIER_OUTWARD
        return TIER_LOCAL

    if name in READ_ONLY_TOOLS:
        return TIER_READ

    if name in {"Edit", "Write", "MultiEdit", "NotebookEdit"}:
        return TIER_LOCAL

    # Unknown tools default to L1 (local/reversible) — do NOT over-block; the
    # destructive-verb / tool-name guards above already lift the dangerous ones.
    return TIER_LOCAL


__all__ = [
    "TIER_READ", "TIER_LOCAL", "TIER_OUTWARD", "TIER_IRREVERSIBLE",
    "READ_ONLY_TOOLS", "READ_ONLY_BASH", "L2_BASH", "L3_BASH_RE",
    "L3_TOOL_RE", "L3_VERB_RE",
    "SEGMENT_RULES", "WHOLE_RULES", "SHELL_SEP",
    "GIT_GLOBAL_OPT", "strip_git_global_opts",
    "ALLOWED_TOOLS", "MCP_DESTRUCTIVE_NAME", "MCP_READONLY_NAME",
    "classify",
]
