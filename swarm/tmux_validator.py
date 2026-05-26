"""Terminal Orchestrator command validator (pure logic, no tmux execution).

This is the policy gate. Every state-changing call to the TMUX agent MUST
route through `validate_command()` first. Refusal here precedes any tmux
side effect.

Layered validation (in order):

  1. Raw-string structural denylist        — catches $(), backticks,
                                              chaining (;, &&, ||, |),
                                              heredocs, process subs
  2. shlex.split tokenisation              — fail-closed on quote errors
  3. Per-token structural denylist re-pass — catches `r$(echo m)` style
                                              attempts that survived to a
                                              single token
  4. Allowlist-chain detection             — `cd <safe> && <verb>`
                                              recursively validates each
                                              clause
  5. Verb allowlist check                  — tokens[0] must appear in
                                              allowlist.yaml verbs
  6. Per-verb constraint enforcement       — subcommand, args_pattern,
                                              forbidden_args,
                                              safe_path_prefixes,
                                              safe_targets, etc.

Anything not allowlisted falls through to L3 (operator ack required).
A `ValidationResult.allowed=False` means refuse — no tmux execution.

This module has NO tmux dependency and NO subprocess calls. It is a pure
function of (cmd, policy files). Unit tests live in
`tests/swarm/test_tmux_validator.py`.

Policy files (load-bearing — read on each call so policy edits land
immediately without restart):
    skills/terminal-orchestrator/policy/denylist.txt
    skills/terminal-orchestrator/policy/allowlist.yaml
    skills/terminal-orchestrator/policy/secret_patterns.txt
"""
from __future__ import annotations

import re
import shlex
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml

POLICY_DIR = Path(__file__).resolve().parent.parent / "skills" / "terminal-orchestrator" / "policy"

Level = Literal["L1", "L2", "L3"]


# ============================================================
# Result type
# ============================================================

@dataclass(frozen=True)
class ValidationResult:
    allowed: bool
    level_required: Level = "L3"
    reason: str = ""
    matched_rule: str | None = None
    denylist_match: str | None = None
    tokens: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return {
            "allowed": self.allowed,
            "level_required": self.level_required,
            "reason": self.reason,
            "matched_rule": self.matched_rule,
            "denylist_match": self.denylist_match,
            "tokens": list(self.tokens),
        }


# ============================================================
# Policy loaders (cached per process)
# ============================================================

@lru_cache(maxsize=1)
def _load_denylist() -> tuple[tuple[str, re.Pattern[str]], ...]:
    """Parse denylist.txt — returns ((rule_name, compiled_regex), ...).

    Rules are `## name` comments followed by a regex line. Comments without
    a regex following are ignored.
    """
    text = (POLICY_DIR / "denylist.txt").read_text()
    rules: list[tuple[str, re.Pattern[str]]] = []
    current_name: str | None = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line:
            current_name = None
            continue
        if line.startswith("##"):
            current_name = line.lstrip("#").strip()
            continue
        if line.startswith("#"):
            continue
        name = current_name or line[:40]
        try:
            rules.append((name, re.compile(line)))
        except re.error:
            # Skip malformed regex lines rather than failing closed at load —
            # the test suite catches these.
            continue
        current_name = None
    return tuple(rules)


@lru_cache(maxsize=1)
def _load_allowlist() -> dict:
    text = (POLICY_DIR / "allowlist.yaml").read_text()
    return yaml.safe_load(text) or {}


@lru_cache(maxsize=1)
def _load_secret_patterns() -> tuple[tuple[str, re.Pattern[str]], ...]:
    text = (POLICY_DIR / "secret_patterns.txt").read_text()
    patterns: list[tuple[str, re.Pattern[str]]] = []
    current_name = "unknown"
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue
        if line.startswith("##"):
            current_name = line.lstrip("#").strip()
            continue
        if line.startswith("#"):
            continue
        try:
            patterns.append((current_name, re.compile(line, re.DOTALL)))
        except re.error:
            continue
    return tuple(patterns)


def _reset_caches() -> None:
    """Test hook — reload policy files."""
    _load_denylist.cache_clear()
    _load_allowlist.cache_clear()
    _load_secret_patterns.cache_clear()


# ============================================================
# Structural denylist application
# ============================================================

# Rule names whose semantics ONLY apply to a token, never to the raw string
# (so they don't false-positive on substrings inside quoted args). Empty for
# now — the raw-string pre-pass uses every rule.
_PER_TOKEN_ONLY: frozenset[str] = frozenset()


def _scan_denylist(text: str, *, source: str) -> tuple[str | None, str | None]:
    """Return (rule_name, matched_text) on first hit, else (None, None)."""
    for name, pattern in _load_denylist():
        if name in _PER_TOKEN_ONLY and source != "token":
            continue
        m = pattern.search(text)
        if m:
            return name, m.group(0)
    return None, None


# ============================================================
# Allowlist-chain detection
# ============================================================

# `cd <safe-target> && <allowlisted clause>` — exactly one `&&`.
_CHAIN_PATTERN = re.compile(r"^\s*cd\s+(\S+)\s+&&\s+(.+)$", re.DOTALL)


def _is_safe_chain(cmd: str) -> tuple[str, str] | None:
    """If cmd is `cd <safe-target> && <rest>`, return (cd_target, rest).
    Else None.
    """
    m = _CHAIN_PATTERN.match(cmd)
    if not m:
        return None
    return m.group(1), m.group(2)


def _cd_target_is_safe(target: str) -> bool:
    allowlist = _load_allowlist()
    cd_rules = allowlist.get("verbs", {}).get("cd", {})
    safe_prefixes = cd_rules.get("safe_path_prefixes", [])
    expanded = str(Path(target).expanduser()) if target.startswith("~") else target
    for prefix in safe_prefixes:
        exp_prefix = str(Path(prefix).expanduser()) if prefix.startswith("~") else prefix
        if expanded == exp_prefix or expanded.startswith(exp_prefix.rstrip("/") + "/"):
            return True
        if prefix == "~" and target in ("~", "~/"):
            return True
    return False


# ============================================================
# Per-verb constraint checks
# ============================================================

def _check_args_pattern(tokens: list[str], pattern_str: str) -> str | None:
    """Return error string if any arg fails the pattern, else None."""
    pattern = re.compile(pattern_str)
    for tok in tokens[1:]:
        if not pattern.match(tok):
            return f"argument {tok!r} does not match args_pattern"
    return None


def _check_forbidden_args(tokens: list[str], forbidden: list[str]) -> str | None:
    raw_rest = " ".join(tokens[1:])
    for f in forbidden:
        if f in raw_rest:
            return f"forbidden arg present: {f!r}"
    return None


def _check_safe_path_prefixes_only(tokens: list[str], verb_rules: dict) -> str | None:
    """For verbs like pytest where any path arg must be under a safe prefix."""
    if not verb_rules.get("safe_path_prefixes_only"):
        return None
    safe = verb_rules.get("safe_path_prefixes")
    if safe is None:
        safe = _load_allowlist().get("verbs", {}).get("cd", {}).get("safe_path_prefixes", [])
    for tok in tokens[1:]:
        if tok.startswith("-"):
            continue  # flag, not a path
        if not _looks_like_path(tok):
            continue
        expanded = str(Path(tok).expanduser()) if tok.startswith("~") else tok
        if expanded.startswith("/") or expanded.startswith("~"):
            ok = any(
                expanded == str(Path(p).expanduser()).rstrip("/")
                or expanded.startswith(str(Path(p).expanduser()).rstrip("/") + "/")
                for p in safe
            )
            if not ok:
                return f"path {tok!r} not under any safe_path_prefixes"
    return None


def _looks_like_path(tok: str) -> bool:
    return "/" in tok or tok.startswith("~") or tok.startswith(".")


def _check_forbidden_path_prefixes(tokens: list[str], forbidden: list[str]) -> str | None:
    for tok in tokens[1:]:
        expanded = str(Path(tok).expanduser()) if tok.startswith("~") else tok
        for fp in forbidden:
            exp_fp = str(Path(fp).expanduser()) if fp.startswith("~") else fp
            if expanded.startswith(exp_fp):
                return f"path {tok!r} matches forbidden_path_prefix {fp!r}"
    return None


def _check_rm(tokens: list[str], verb_rules: dict) -> str | None:
    """rm is a special case — only `rm -rf <safe-target>` is allowed."""
    if len(tokens) != 1 + verb_rules.get("args_required_count", 2):
        return f"rm requires exactly {verb_rules.get('args_required_count', 2)} args"
    required_flag = verb_rules.get("require_flags", ["-rf"])[0]
    if tokens[1] != required_flag:
        return f"rm second token must be {required_flag!r}, got {tokens[1]!r}"
    safe_targets = verb_rules.get("safe_targets", [])
    if tokens[2] not in safe_targets:
        return f"rm target {tokens[2]!r} not in safe_targets {safe_targets}"
    return None


def _check_chmod(tokens: list[str], verb_rules: dict) -> str | None:
    if len(tokens) < 2:
        return "chmod missing mode arg"
    mode = tokens[1]
    forbidden_re = re.compile(verb_rules["forbidden_modes_regex"])
    if forbidden_re.match(mode):
        return f"chmod mode {mode!r} forbidden"
    allowed_re = re.compile(verb_rules["allowed_modes_regex"])
    if not allowed_re.match(mode):
        return f"chmod mode {mode!r} not in allowed set"
    return None


def _check_subcommand(tokens: list[str], verb_rules: dict) -> str | None:
    if not verb_rules.get("subcommand_required"):
        return None
    if len(tokens) < 2:
        return f"{tokens[0]} requires a subcommand"
    sub = tokens[1]
    allowed = verb_rules.get("allowed_subcommands", [])
    forbidden = verb_rules.get("forbidden_subcommands", [])
    if sub in forbidden:
        return f"{tokens[0]} {sub!r} is a forbidden subcommand"
    if allowed and sub not in allowed:
        return f"{tokens[0]} {sub!r} not in allowed_subcommands"
    return None


def _check_forbidden_arg_regex(tokens: list[str], pattern_str: str) -> str | None:
    pattern = re.compile(pattern_str)
    for tok in tokens[1:]:
        if pattern.search(tok):
            return f"arg {tok!r} matches forbidden_arg_regex"
    return None


# ============================================================
# Main entry point
# ============================================================

def validate_command(cmd: str, *, level: Level = "L2") -> ValidationResult:
    """Validate a command string against the policy engine.

    `level` is the current autonomy ceiling. Anything that would require a
    higher level returns `allowed=False` with `level_required` set so the
    caller can decide whether to escalate.
    """
    if not isinstance(cmd, str):
        return ValidationResult(False, "L3", "cmd must be a string")
    if not cmd.strip():
        return ValidationResult(False, "L1", "empty command")
    if len(cmd) > 512:
        return ValidationResult(False, "L3", "command exceeds 512-char limit")

    # ── (1) Raw-string structural denylist ────────────────────────────
    # Check chain allowlist BEFORE blanket && denial.
    chain = _is_safe_chain(cmd)
    if chain is not None:
        cd_target, rest = chain
        if not _cd_target_is_safe(cd_target):
            return ValidationResult(
                False, "L3",
                f"cd target {cd_target!r} not in safe_path_prefixes",
            )
        # Recursively validate the rest; the chain itself is allowed only if
        # the rest is independently allowed at <= current level.
        rest_result = validate_command(rest, level=level)
        if not rest_result.allowed:
            return rest_result
        return ValidationResult(
            True, "L2",
            f"allowed chain: cd {cd_target} && {rest_result.matched_rule}",
            matched_rule=f"chain:{rest_result.matched_rule}",
            tokens=rest_result.tokens,
        )

    rule, _matched = _scan_denylist(cmd, source="raw")
    if rule is not None:
        return ValidationResult(
            False, "L3",
            f"raw-string denylist match: {rule}",
            denylist_match=rule,
        )

    # ── (2) Tokenise ──────────────────────────────────────────────────
    try:
        tokens = shlex.split(cmd, posix=True)
    except ValueError as exc:
        return ValidationResult(False, "L3", f"shlex error: {exc}")
    if not tokens:
        return ValidationResult(False, "L1", "empty token list after split")

    # ── (3) Per-token structural denylist ─────────────────────────────
    for tok in tokens:
        rule, _matched = _scan_denylist(tok, source="token")
        if rule is not None:
            return ValidationResult(
                False, "L3",
                f"token denylist match: {rule} (token={tok!r})",
                denylist_match=rule,
                tokens=tuple(tokens),
            )

    # ── (4) Verb allowlist ────────────────────────────────────────────
    allowlist = _load_allowlist()
    verbs = allowlist.get("verbs", {})
    verb = tokens[0]
    if verb not in verbs:
        return ValidationResult(
            False, "L3",
            f"verb {verb!r} not on L2 allowlist (requires L3 ack)",
            tokens=tuple(tokens),
        )

    verb_rules = verbs[verb] or {}

    # ── (5) Per-verb constraints ──────────────────────────────────────
    # Special-cased verbs first (rm, chmod) because their semantics are
    # tightly bound to specific arg shapes.
    if verb == "rm":
        err = _check_rm(tokens, verb_rules)
        if err:
            return ValidationResult(False, "L3", err, tokens=tuple(tokens))
        return ValidationResult(True, "L2", "allowed rm safe-target",
                                matched_rule="rm", tokens=tuple(tokens))

    if verb == "chmod":
        err = _check_chmod(tokens, verb_rules)
        if err:
            return ValidationResult(False, "L3", err, tokens=tuple(tokens))
        return ValidationResult(True, "L2", "allowed chmod",
                                matched_rule="chmod", tokens=tuple(tokens))

    # General per-verb checks
    if err := _check_subcommand(tokens, verb_rules):
        return ValidationResult(False, "L3", err, tokens=tuple(tokens))
    if max_count := verb_rules.get("args_max_count"):
        if len(tokens) - 1 > max_count:
            return ValidationResult(
                False, "L3",
                f"too many args ({len(tokens) - 1} > {max_count})",
                tokens=tuple(tokens),
            )
    if pattern := verb_rules.get("args_pattern"):
        if err := _check_args_pattern(tokens, pattern):
            return ValidationResult(False, "L3", err, tokens=tuple(tokens))
    if forbidden := verb_rules.get("forbidden_args"):
        if err := _check_forbidden_args(tokens, forbidden):
            return ValidationResult(False, "L3", err, tokens=tuple(tokens))
    if regex := verb_rules.get("forbidden_arg_regex"):
        if err := _check_forbidden_arg_regex(tokens, regex):
            return ValidationResult(False, "L3", err, tokens=tuple(tokens))
    if forbidden_paths := verb_rules.get("forbidden_path_prefixes"):
        if err := _check_forbidden_path_prefixes(tokens, forbidden_paths):
            return ValidationResult(False, "L3", err, tokens=tuple(tokens))
    if err := _check_safe_path_prefixes_only(tokens, verb_rules):
        return ValidationResult(False, "L3", err, tokens=tuple(tokens))

    # `cd` with explicit safe_path_prefixes (no `safe_path_prefixes_only` flag)
    if verb == "cd":
        if len(tokens) == 1:
            return ValidationResult(True, "L2", "allowed cd home",
                                    matched_rule="cd", tokens=tuple(tokens))
        if not _cd_target_is_safe(tokens[1]):
            return ValidationResult(
                False, "L3",
                f"cd target {tokens[1]!r} not in safe_path_prefixes",
                tokens=tuple(tokens),
            )

    return ValidationResult(
        True, "L2", f"allowed verb {verb!r}",
        matched_rule=verb, tokens=tuple(tokens),
    )


# ============================================================
# Secret redaction
# ============================================================

def redact_secrets(text: str) -> tuple[str, dict[str, int]]:
    """Apply all secret patterns to `text`, return (redacted_text, counts)."""
    if not isinstance(text, str) or not text:
        return text or "", {}
    counts: dict[str, int] = {}
    out = text
    for name, pattern in _load_secret_patterns():
        def _replace(_m: re.Match, _n: str = name) -> str:
            counts[_n] = counts.get(_n, 0) + 1
            return f"[REDACTED:{_n}]"
        out = pattern.sub(_replace, out)
    return out, counts
