# Tier-gate — autonomy-ladder enforcement at the PreToolUse hook

Replaces the brittle hardcoded `settings.json` matcher regex with a tested,
reviewable classifier. The gate now prompts the human (Telegram, fail-closed)
**only for L3** — irreversible / secret / prod / destructive — and lets L0–L2
run automatically. This is the enforcement the `autonomy-ladder` skill specified.

## Files
- `tier_classifier.py` — pure classifier: `classify(tool_name, tool_input) -> (tier, rule)`. No I/O, fail-safe (errors → L3).
- `pretooluse_gate.py` — now calls the classifier; `tier < 3` returns 0 (auto-allow, logged to stderr for the audit trail); `tier == 3` runs the existing Telegram approval flow with the matched rule in the reason.
- `test_tier_classifier.py` — 9 tests incl. legacy no-regression + 38 adversary-confirmed bypass regressions. Run: `python3 test_tier_classifier.py`.

## Hardening (Opus adversary, 2026-07-06 — all Top-5 + mediums landed)
Whitespace-normalized matching (kills newline evasion); `find -delete`/`xargs rm`/`truncate`/`shred`/`rsync --delete`/`>`-overwrite; verb-independent credential-file gating + env/printenv/scp/base64/`| sh` exfil; non-Vercel deploy (netlify/fly/wrangler/firebase/terraform/kubectl); DB drops (mongosh/redis/dropdb/mysqladmin); `gh workflow run`/`secret set`/mutating `gh api`; git working-tree loss (`checkout .`/`restore`/`stash clear`/`--mirror`).

## Activation (two steps, both yours — the agent does not self-apply)
1. **Deploy to live:** `cp claude-hooks-mirror/phone/{tier_classifier.py,pretooluse_gate.py} ~/.claude/hooks/phone/` (reverse of the nightly `claude_hooks_sync.sh`; after this, live == mirror so the next sync is a no-op).
2. **Broaden the matcher** in `~/.claude/settings.json` `hooks.PreToolUse[].matcher` so the classifier sees every call (it filters, not the regex):
   ```
   "matcher": "Bash|Write|Edit|MultiEdit|NotebookEdit"
   ```
   Until step 2, behavior is unchanged — the narrow legacy matcher still feeds the hook, and every legacy pattern classifies L3, so nothing regresses.

## Safety properties
- Behavior-preserving under the current narrow matcher (no live change until you broaden it).
- Fail-safe: classifier import/exec error → gate (L3), never silent-allow.
- Defense-in-depth: L2 actions remain human-visible (PRs, pushes) and every decision is logged; the control's job is to prevent **silent** auto-allow of clearly-destructive ops, which the 38 regression tests lock down.
